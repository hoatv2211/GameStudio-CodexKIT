from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import struct
import sys
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


PASS_EXIT = 0
FAIL_EXIT = 1
BLOCKED_EXIT = 2

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_MAX_IMAGE_FILE_BYTES = 64 * 1024 * 1024
_PNG_MAX_COMPRESSED_IDAT_BYTES = 16 * 1024 * 1024
_PNG_MAX_DECOMPRESSED_IDAT_BYTES = 128 * 1024 * 1024
_PNG_VALIDATION_SLACK_BYTES = 1024
_PATH_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9_-][A-Za-z0-9._-]*)(?:/(?:[A-Za-z0-9_-][A-Za-z0-9._-]*))*$"
)
_LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
_PLATFORM_DEVICE = {
    "steam": {"preset": "desktop-hd", "width": 1920, "height": 1080, "scale": 1, "format": "png"},
    "android": {
        "preset": "mobile-portrait-1080x1920",
        "width": 1080,
        "height": 1920,
        "scale": 1,
        "format": "png",
    },
    "ios": {
        "preset": "mobile-portrait-1080x1920",
        "width": 1080,
        "height": 1920,
        "scale": 1,
        "format": "png",
    },
    "webgl": {"preset": "webgl-1080p", "width": 1920, "height": 1080, "scale": 1, "format": "png"},
}
_PLATFORM_SLOTS = {
    "steam": ("hero", "detail"),
    "android": ("hero", "portrait", "detail"),
    "ios": ("hero", "portrait", "detail"),
    "webgl": ("hero", "thumbnail"),
}
_IMAGE_FORMAT_RULES = {
    "image/png": ("png", {".png"}),
    "image/jpeg": ("jpeg", {".jpg", ".jpeg"}),
}


def _schema_candidates(schema_name: str) -> list[Path]:
    file_name = f"{schema_name}.schema.json"
    script_dir = Path(__file__).resolve().parent
    return [
        script_dir.parent / "evals" / "schema" / file_name,
        script_dir.parent / "schemas" / file_name,
        script_dir / "schemas" / file_name,
        script_dir / file_name,
    ]


def _load_schema(schema_name: str) -> tuple[dict[str, Any] | None, str | None]:
    schema_path = next((candidate for candidate in _schema_candidates(schema_name) if candidate.is_file()), None)
    if schema_path is None:
        return None, f"$: schema not found for {schema_name}"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as error:
        return None, f"$: schema load failed for {schema_name}: {error}"
    if not isinstance(schema, dict):
        return None, f"$: schema root must be an object for {schema_name}"
    return schema, None


def _json_path(parts: Iterable[object]) -> str:
    collected = [str(part) for part in parts]
    return "/".join(collected) if collected else "$"


def _sorted_errors(errors: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(errors))


def _coerce_mapping(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _coerce_list(value: object) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _safe_relative_path(value: str) -> tuple[PurePosixPath | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, "path must be a non-empty string"
    if not _PATH_PATTERN.fullmatch(value):
        return None, "path must stay relative and normalized"
    pure = PurePosixPath(value)
    if pure.is_absolute():
        return None, "path must stay relative and normalized"
    if any(part in {"", ".", ".."} for part in pure.parts):
        return None, "path must stay relative and normalized"
    return pure, None


def _contains_reparse_point(path: Path) -> bool:
    try:
        stat_result = path.lstat()
    except OSError:
        return False
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT) or path.is_symlink()


def _path_anchor(path: Path) -> Path:
    absolute = path if path.is_absolute() else path.absolute()
    return Path(absolute.anchor) if absolute.anchor else absolute


def _path_identity(path: Path) -> str:
    """Compare filesystem paths after expanding aliases such as Windows 8.3 names."""
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _split_missing_ancestors(path: Path) -> tuple[Path, list[Path]]:
    current = path if path.is_absolute() else path.absolute()
    missing: list[Path] = []
    while True:
        try:
            current.lstat()
            return current, list(reversed(missing))
        except OSError:
            missing.append(current)
            if current.parent == current:
                raise ValueError(f"path has no existing anchor: {path}")
            current = current.parent


def _check_existing_path_chain(path: Path, boundary: Path) -> str | None:
    boundary_resolved = boundary.resolve(strict=False)
    boundary_identity = _path_identity(boundary_resolved)
    current = path if path.is_absolute() else path.absolute()
    while True:
        if _contains_reparse_point(current):
            return f"reparse point is not allowed: {current}"
        if _path_identity(current) == boundary_identity:
            return None
        if current.parent == current:
            return f"path escapes boundary: {path}"
        current = current.parent


def _resolve_within(root: Path, relative_path: str, *, require_exists: bool) -> tuple[Path | None, str | None]:
    normalized, error = _safe_relative_path(relative_path)
    if error:
        return None, error
    root_resolved = root.resolve(strict=False)
    candidate = root_resolved.joinpath(*normalized.parts)
    if not candidate.is_relative_to(root_resolved):
        return None, f"path escapes root: {relative_path}"
    chain_error = _check_existing_path_chain(candidate, root_resolved)
    if chain_error:
        return None, chain_error
    if not require_exists:
        return candidate, None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        return None, str(error)
    if not resolved.is_relative_to(root_resolved):
        return None, f"path escapes root: {relative_path}"
    chain_error = _check_existing_path_chain(resolved, root_resolved)
    if chain_error:
        return None, chain_error
    return resolved, None


def _write_text_output(path: Path, content: str) -> str | None:
    write_error: OSError | None = None
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            try:
                handle.write(content)
            except OSError as error:
                write_error = error
    except FileExistsError:
        return f"output already exists: {path}"
    except OSError as error:
        return f"cannot write output: {error}"
    if write_error is not None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        try:
            raise write_error
        except OSError as error:
            return f"cannot write output: {error}"
    return None


def _format_validator_error(error: ValidationError) -> str:
    return f"{_json_path(error.absolute_path)}: {error.message}"


def _semantic_capture_plan_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    flows = _coerce_list(payload.get("flows"))
    if flows is None:
        return errors
    flow_ids: dict[str, int] = {}
    orders: dict[int, int] = {}
    for index, flow_value in enumerate(flows):
        flow = _coerce_mapping(flow_value)
        if flow is None:
            continue
        flow_id = flow.get("flow_id")
        order = flow.get("order")
        if isinstance(flow_id, str):
            if flow_id in flow_ids:
                errors.append(
                    f"flows/{index}/flow_id: duplicate flow_id '{flow_id}' also used at flows/{flow_ids[flow_id]}/flow_id"
                )
            else:
                flow_ids[flow_id] = index
        if isinstance(order, int):
            if order in orders:
                errors.append(
                    f"flows/{index}/order: duplicate order {order} also used at flows/{orders[order]}/order"
                )
            else:
                orders[order] = index
    return errors


def _semantic_store_manifest_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    outputs = _coerce_list(payload.get("outputs"))
    if outputs is None:
        return errors
    slots: dict[str, int] = {}
    for index, output_value in enumerate(outputs):
        output = _coerce_mapping(output_value)
        if output is None:
            continue
        slot = output.get("slot")
        if isinstance(slot, str):
            if slot in slots:
                errors.append(
                    f"outputs/{index}/slot: duplicate slot '{slot}' also used at outputs/{slots[slot]}/slot"
                )
            else:
                slots[slot] = index
    return errors


def validate_payload(schema_name: str, payload: object) -> list[str]:
    schema, schema_error = _load_schema(schema_name)
    if schema_error:
        return [schema_error]
    validator = Draft202012Validator(schema)
    errors = [_format_validator_error(error) for error in validator.iter_errors(payload)]
    if isinstance(payload, dict):
        if schema_name == "capture-plan":
            errors.extend(_semantic_capture_plan_errors(payload))
        elif schema_name == "store-export-manifest":
            errors.extend(_semantic_store_manifest_errors(payload))
    return _sorted_errors(errors)


def _schema_object_view(schema_name: str, payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    schema, _ = _load_schema(schema_name)
    if not schema:
        return payload
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return payload
    return {key: value for key, value in payload.items() if key in properties}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_image_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read image: {path}: {error}") from error


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("unsupported image format")
    if len(data) < 33:
        raise ValueError("truncated PNG header")
    length = struct.unpack(">I", data[8:12])[0]
    chunk_type = data[12:16]
    if length != 13 or chunk_type != b"IHDR":
        raise ValueError("invalid PNG header")
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        raise ValueError("invalid PNG dimensions")
    bit_depth = data[24]
    color_type = data[25]
    channels_by_color = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    valid_bit_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    channel_count = channels_by_color.get(color_type)
    if channel_count is None or bit_depth not in valid_bit_depths[color_type]:
        raise ValueError("unsupported PNG color type")
    bits_per_row = width * channel_count * bit_depth
    row_bytes = (bits_per_row + 7) // 8
    expected_scanline_bytes = height * (1 + row_bytes)
    allowed_scanline_bytes = min(
        _PNG_MAX_DECOMPRESSED_IDAT_BYTES,
        expected_scanline_bytes + _PNG_VALIDATION_SLACK_BYTES,
    )
    if expected_scanline_bytes > _PNG_MAX_DECOMPRESSED_IDAT_BYTES:
        raise ValueError("PNG image data exceeds decompressed limit")
    offset = 8
    decompressor = zlib.decompressobj()
    compressed_total = 0
    decoded_total = 0
    saw_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        chunk_length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(data):
            raise ValueError("truncated PNG chunk")
        chunk_data = data[offset + 8 : offset + 8 + chunk_length]
        if chunk_type == b"IDAT":
            compressed_total += len(chunk_data)
            if compressed_total > _PNG_MAX_COMPRESSED_IDAT_BYTES:
                raise ValueError("PNG image data exceeds compressed limit")
            while True:
                remaining = allowed_scanline_bytes - decoded_total
                decoded = decompressor.decompress(chunk_data, remaining + 1)
                decoded_total += len(decoded)
                if decoded_total > allowed_scanline_bytes:
                    raise ValueError("PNG image data exceeds expected scanline data")
                if decoded_total > _PNG_MAX_DECOMPRESSED_IDAT_BYTES:
                    raise ValueError("PNG image data exceeds decompressed limit")
                if decompressor.unconsumed_tail:
                    chunk_data = decompressor.unconsumed_tail
                    continue
                break
        elif chunk_type == b"IEND":
            saw_iend = True
            break
        offset = chunk_end
    if compressed_total == 0 or not saw_iend:
        raise ValueError("PNG is missing required data chunks")
    try:
        final = decompressor.flush(allowed_scanline_bytes - decoded_total + 1)
    except zlib.error as error:
        raise ValueError("PNG image data cannot be decoded") from error
    decoded_total += len(final)
    if decoded_total < expected_scanline_bytes:
        raise ValueError("PNG image data is truncated")
    if decoded_total > allowed_scanline_bytes:
        raise ValueError("PNG image data exceeds expected scanline data")
    return width, height


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xFF\xD8"):
        raise ValueError("unsupported image format")
    offset = 2
    dimensions: tuple[int, int] | None = None
    saw_scan = False
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError("invalid JPEG marker")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise ValueError("truncated JPEG marker")
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            break
        if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            raise ValueError("truncated JPEG segment length")
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(data):
            raise ValueError("truncated JPEG segment")
        segment = data[offset + 2 : offset + segment_length]
        if marker in JPEG_SOF_MARKERS:
            if len(segment) < 6:
                raise ValueError("invalid JPEG frame header")
            height, width = struct.unpack(">HH", segment[1:5])
            if width < 1 or height < 1:
                raise ValueError("invalid JPEG dimensions")
            dimensions = (width, height)
        if marker == 0xDA:
            saw_scan = True
            break
        offset += segment_length
    if dimensions is None or not saw_scan or not data.endswith(b"\xFF\xD9"):
        raise ValueError("JPEG is missing a complete frame or EOI")
    return dimensions


def image_dimensions(path: Path) -> tuple[int, int]:
    data = _read_image_bytes(path)
    image_format = _detect_image_format(data)
    if image_format == "png":
        return _png_dimensions(data)
    if image_format == "jpeg":
        return _jpeg_dimensions(data)
    raise ValueError("unsupported image format")


def _detect_image_format(data: bytes) -> str:
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data.startswith(b"\xFF\xD8"):
        return "jpeg"
    raise ValueError("unsupported image format")


def _stat_identity_tuple(stat_result: os.stat_result) -> tuple[int | None, int | None, int]:
    return (
        getattr(stat_result, "st_dev", None),
        getattr(stat_result, "st_ino", None),
        stat_result.st_size,
    )


def _read_image_verification_data(path: Path) -> tuple[bytes, int, str]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total_bytes = 0
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
            total_bytes += len(chunk)
            if total_bytes > _MAX_IMAGE_FILE_BYTES:
                raise ValueError("image exceeds verification size limit")
        after = os.fstat(handle.fileno())
    if _stat_identity_tuple(before) != _stat_identity_tuple(after):
        raise ValueError("image changed during verification")
    return b"".join(chunks), before.st_size, digest.hexdigest()


def verify_capture_record(project_root: Path, record: object) -> dict[str, object]:
    failures = validate_payload("capture-record", record)
    if failures:
        return {"verdict": "FAIL", "failures": failures}
    assert isinstance(record, dict)
    project_root = Path(project_root)
    raw_image_path = str(record["raw_image_path"])
    image_path, path_error = _resolve_within(project_root, raw_image_path, require_exists=True)
    if path_error:
        return {"verdict": "FAIL", "failures": [f"raw_image_path: {path_error}"]}
    if image_path is None or not image_path.is_file():
        return {"verdict": "FAIL", "failures": [f"raw_image_path: missing file: {raw_image_path}"]}

    mime_type = str(record["mime_type"])
    mime_rule = _IMAGE_FORMAT_RULES.get(mime_type)
    if mime_rule is None:
        return {"verdict": "BLOCKED", "failures": [f"mime_type: unsupported image type: {mime_type}"]}
    expected_format, allowed_suffixes = mime_rule

    failures = []
    recorded_dimensions = _coerce_mapping(record.get("dimensions")) or {}
    try:
        image_bytes, actual_size, actual_hash = _read_image_verification_data(image_path)
        actual_format = _detect_image_format(image_bytes)
        if actual_format != expected_format:
            return {
                "verdict": "FAIL",
                "failures": [
                    f"mime_type: expected {mime_type} but detected {actual_format.upper()} bytes"
                ],
            }
        suffix = image_path.suffix.casefold()
        if suffix not in allowed_suffixes:
            allowed_text = " or ".join(sorted(allowed_suffixes))
            return {
                "verdict": "FAIL",
                "failures": [
                    f"raw_image_path: expected {allowed_text} file for {mime_type}"
                ],
            }
        if actual_format == "png":
            actual_dimensions = _png_dimensions(image_bytes)
        elif actual_format == "jpeg":
            actual_dimensions = _jpeg_dimensions(image_bytes)
        else:
            raise ValueError("unsupported image format")
    except ValueError as error:
        verdict = "BLOCKED" if "unsupported image format" in str(error) else "FAIL"
        return {"verdict": verdict, "failures": [f"raw_image_path: {error}"]}
    if actual_dimensions != (
        int(recorded_dimensions.get("width", -1)),
        int(recorded_dimensions.get("height", -1)),
    ):
        failures.append(
            "dimensions: recorded dimensions do not match the decoded image"
        )
    if actual_size != int(record["byte_size"]):
        failures.append(f"byte_size: recorded {record['byte_size']} but found {actual_size}")
    if actual_hash != record["sha256"]:
        failures.append("sha256: recorded hash does not match file contents")
    verdict = "PASS" if not failures else "FAIL"
    return {
        "verdict": verdict,
        "failures": failures,
        "artifact_path": str(image_path),
        "byte_size": actual_size,
        "dimensions": {"width": actual_dimensions[0], "height": actual_dimensions[1]},
        "sha256": actual_hash,
    }


def _ensure_output_path(path: Path) -> tuple[Path | None, str | None]:
    path = Path(path)
    if path.exists():
        return None, f"output already exists: {path}"
    try:
        existing_ancestor, missing_directories = _split_missing_ancestors(path.parent)
    except ValueError as error:
        return None, str(error)
    chain_error = _check_existing_path_chain(existing_ancestor, _path_anchor(existing_ancestor))
    if chain_error:
        return None, chain_error
    try:
        for directory in missing_directories:
            directory.mkdir()
            if _contains_reparse_point(directory):
                return None, f"reparse point is not allowed: {directory}"
    except OSError as error:
        return None, f"cannot create output directory: {error}"
    try:
        verified_parent = path.parent.resolve(strict=True)
    except OSError as error:
        return None, f"cannot resolve output directory: {error}"
    chain_error = _check_existing_path_chain(verified_parent, _path_anchor(verified_parent))
    if chain_error:
        return None, chain_error
    return verified_parent / path.name, None


def build_contact_sheet(records: list[dict[str, object]], output: Path) -> dict[str, object]:
    ordered_records = sorted(
        records,
        key=lambda item: (
            int(item.get("order")) if isinstance(item.get("order"), int) else 2**31 - 1,
            str(item.get("capture_id", "")),
        ),
    )
    output_path, output_error = _ensure_output_path(Path(output))
    if output_error or output_path is None:
        return {"verdict": "BLOCKED", "failures": [output_error or "cannot prepare output"], "records": ordered_records}

    cards: list[str] = []
    for record in ordered_records:
        capture_id = html.escape(str(record.get("capture_id", "unknown")))
        raw_path = html.escape(str(record.get("raw_image_path", "")))
        runtime_result = html.escape(str(record.get("runtime_result", "unknown")))
        visual_review = _coerce_mapping(record.get("visual_review")) or {}
        visual_status = html.escape(str(visual_review.get("status", "unknown")))
        sha256_value = html.escape(str(record.get("sha256", "")))
        rejection_reason = record.get("rejection_reason")
        rejection_text = (
            html.escape(str(rejection_reason))
            if rejection_reason not in {None, ""}
            else "None"
        )
        cards.append(
            "\n".join(
                [
                    '    <article class="card">',
                    f"      <h2>{capture_id}</h2>",
                    f'      <img alt="{capture_id}" src="{raw_path}" loading="lazy" />',
                    "      <dl>",
                    f"        <dt>Order</dt><dd>{html.escape(str(record.get('order', '')))}</dd>",
                    f"        <dt>Runtime</dt><dd>{runtime_result}</dd>",
                    f"        <dt>Visual</dt><dd>{visual_status}</dd>",
                    f"        <dt>Path</dt><dd><code>{raw_path}</code></dd>",
                    f"        <dt>SHA-256</dt><dd><code>{sha256_value}</code></dd>",
                    f"        <dt>Rejection</dt><dd>{rejection_text}</dd>",
                    "      </dl>",
                    "    </article>",
                ]
            )
        )
    page = "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            "  <title>Screenshot Review</title>",
            "  <style>",
            "    body { background: #111827; color: #f3f4f6; font-family: Arial, sans-serif; margin: 0; padding: 24px; }",
            "    h1 { margin-top: 0; }",
            "    .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    .card { background: #1f2937; border: 1px solid #374151; border-radius: 12px; padding: 16px; }",
            "    img { display: block; width: 100%; height: auto; border-radius: 8px; background: #0f172a; }",
            "    dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 10px; margin: 12px 0 0; }",
            "    dt { color: #cbd5e1; font-weight: 700; }",
            "    dd { margin: 0; overflow-wrap: anywhere; }",
            "    code { color: #fde68a; }",
            "  </style>",
            "</head>",
            "<body>",
            f"  <h1>Screenshot Review ({len(ordered_records)} records)</h1>",
            '  <section class="grid">',
            *cards,
            "  </section>",
            "</body>",
            "</html>",
            "",
        ]
    )
    write_error = _write_text_output(output_path, page)
    if write_error:
        return {"verdict": "BLOCKED", "failures": [write_error], "records": ordered_records}
    return {
        "verdict": "PASS",
        "failures": [],
        "artifact_path": str(output_path),
        "records": ordered_records,
    }


def _platform_slots(platform: str) -> tuple[str, ...]:
    return _PLATFORM_SLOTS.get(platform, ("hero", "detail"))


def _slug_identifier(*parts: object) -> str:
    values: list[str] = []
    for part in parts:
        text = str(part).strip().casefold()
        if text:
            values.append(re.sub(r"[^a-z0-9]+", "-", text).strip("-"))
    return "-".join(value for value in values if value)


def _load_existing_output(output_path: Path, slot: str, output_root: Path) -> tuple[dict[str, object] | None, str | None]:
    if not output_path.exists():
        return None, f"missing slot asset: {slot}"
    if not output_path.is_file():
        return None, f"slot asset is not a file: {slot}"
    chain_error = _check_existing_path_chain(output_path, output_root.resolve(strict=False))
    if chain_error:
        return None, chain_error
    try:
        dimensions = image_dimensions(output_path)
    except ValueError as error:
        return None, f"{slot}: {error}"
    relative_path = output_path.resolve(strict=True).relative_to(output_root.resolve(strict=False)).as_posix()
    return {
        "slot": slot,
        "path": relative_path,
        "sha256": sha256_file(output_path),
        "bytes": output_path.stat().st_size,
        "dimensions": {"width": dimensions[0], "height": dimensions[1]},
    }, None


def build_store_export_manifest(deck: dict[str, object], platform: str, locale: str, output_root: Path) -> dict[str, object]:
    failures = validate_payload("showcase-deck", _schema_object_view("showcase-deck", deck))
    if failures:
        return {"verdict": "FAIL", "failures": failures, "platform": platform, "locale": locale}
    if platform not in _PLATFORM_DEVICE:
        return {"verdict": "FAIL", "failures": [f"platform: unsupported platform: {platform}"], "platform": platform, "locale": locale}
    if not _LOCALE_PATTERN.fullmatch(locale):
        return {"verdict": "FAIL", "failures": [f"locale: unsupported locale format: {locale}"], "platform": platform, "locale": locale}

    output_root = Path(output_root)
    platform_root = output_root / platform / locale
    manifest_path = platform_root / "store-export-manifest.json"
    prepared_path, output_error = _ensure_output_path(manifest_path)
    if output_error or prepared_path is None:
        return {"verdict": "BLOCKED", "failures": [output_error or "cannot prepare output"], "platform": platform, "locale": locale}

    deck_locale = str(deck.get("locale", ""))
    if deck_locale != locale:
        failures.append(f"locale: requested {locale} but deck locale is {deck_locale}")

    approval = _coerce_mapping(deck.get("approval")) or {}
    if approval.get("status") != "approved":
        failures.append("approval: showcase deck is not approved")
    requirement_snapshot = _coerce_mapping(deck.get("requirement_snapshot"))
    human_approval = _coerce_mapping(deck.get("human_approval"))
    blocked_reasons: list[str] = []
    if requirement_snapshot is None:
        blocked_reasons.append("requirement_snapshot: missing explicit requirement snapshot input")
    if human_approval is None:
        blocked_reasons.append("human_approval: missing explicit human approval input")
    if human_approval is not None and human_approval.get("status") != "approved":
        blocked_reasons.append("human_approval: status must be approved")

    slots = _platform_slots(platform)
    outputs: list[dict[str, object]] = []
    missing_slots: list[str] = []
    rejected_slots: list[str] = []
    source_capture_id = str(deck.get("source_capture_id", ""))
    device = dict(_PLATFORM_DEVICE[platform])
    for slot in slots:
        output_path = platform_root / f"{slot}.{device['format']}"
        output_payload, output_failure = _load_existing_output(output_path, slot, output_root)
        if output_failure:
            missing_slots.append(slot)
            rejected_slots.append(slot) if "unsupported" in output_failure or "not a file" in output_failure else None
            continue
        assert output_payload is not None
        dimensions = _coerce_mapping(output_payload.pop("dimensions")) or {}
        if dimensions.get("width") != device["width"] or dimensions.get("height") != device["height"]:
            missing_slots.append(slot)
            rejected_slots.append(slot)
            continue
        output_payload["source_capture_id"] = source_capture_id
        outputs.append(output_payload)

    if not outputs:
        failures.append("outputs: no existing platform-sized exports were found")
    elif missing_slots:
        failures.append(f"outputs: missing or invalid required slots: {', '.join(missing_slots)}")
    manifest = {
        "schema_version": 1,
        "manifest_id": _slug_identifier(deck.get("deck_id", "showcase"), platform, locale),
        "platform": platform,
        "requirement_snapshot": requirement_snapshot or {},
        "locale": locale,
        "device": device,
        "outputs": outputs,
        "source_capture_ids": [source_capture_id] if source_capture_id else [],
        "missing_slots": missing_slots,
        "rejected_slots": rejected_slots,
        "reviewer": str((human_approval or {}).get("approved_by", "")),
        "human_approval": human_approval or {},
    }

    manifest_errors = validate_payload("store-export-manifest", manifest)
    verdict = "PASS"
    blocked_manifest_errors = [
        message
        for message in manifest_errors
        if message.startswith("human_approval") or message.startswith("requirement_snapshot") or message.startswith("reviewer")
    ]
    if blocked_reasons or blocked_manifest_errors:
        verdict = "BLOCKED"
    elif failures or manifest_errors:
        verdict = "FAIL"
    report = {
        "verdict": verdict,
        "failures": _sorted_errors([*blocked_reasons, *failures, *manifest_errors]),
        "artifact_path": str(prepared_path),
        "platform": platform,
        "locale": locale,
        "manifest": manifest,
    }
    write_error = _write_text_output(prepared_path, json.dumps(report, indent=2, sort_keys=True))
    if write_error:
        report["verdict"] = "BLOCKED"
        report["failures"] = _sorted_errors([*report["failures"], write_error])
    return report


def _load_json(path: Path) -> tuple[object | None, str | None]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, str(error)


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _exit_code(verdict: str) -> int:
    return {"PASS": PASS_EXIT, "FAIL": FAIL_EXIT, "BLOCKED": BLOCKED_EXIT}.get(verdict, FAIL_EXIT)


def _command_verify_capture(args: argparse.Namespace) -> int:
    record_payload, error = _load_json(Path(args.record))
    if error:
        _print_json({"verdict": "FAIL", "failures": [f"record: {error}"]})
        return FAIL_EXIT
    result = verify_capture_record(Path(args.project_root), record_payload)
    _print_json(result)
    return _exit_code(str(result["verdict"]))


def _command_contact_sheet(args: argparse.Namespace) -> int:
    records_payload, error = _load_json(Path(args.records))
    if error:
        _print_json({"verdict": "FAIL", "failures": [f"records: {error}"]})
        return FAIL_EXIT
    if not isinstance(records_payload, list) or not all(isinstance(item, dict) for item in records_payload):
        _print_json({"verdict": "FAIL", "failures": ["records: expected a JSON array of objects"]})
        return FAIL_EXIT
    result = build_contact_sheet(records_payload, Path(args.output))
    _print_json(result)
    return _exit_code(str(result["verdict"]))


def _command_export_manifest(args: argparse.Namespace) -> int:
    deck_payload, error = _load_json(Path(args.deck))
    if error:
        _print_json({"verdict": "FAIL", "failures": [f"deck: {error}"]})
        return FAIL_EXIT
    if not isinstance(deck_payload, dict):
        _print_json({"verdict": "FAIL", "failures": ["deck: expected a JSON object"]})
        return FAIL_EXIT
    result = build_store_export_manifest(deck_payload, args.platform, args.locale, Path(args.output_root))
    _print_json(result)
    return _exit_code(str(result["verdict"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report-only screenshot showcase helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify-capture", help="Verify a capture-record JSON file.")
    verify_parser.add_argument("project_root")
    verify_parser.add_argument("--record", required=True)
    verify_parser.set_defaults(handler=_command_verify_capture)

    contact_parser = subparsers.add_parser("contact-sheet", help="Create an HTML contact sheet from JSON records.")
    contact_parser.add_argument("--records", required=True)
    contact_parser.add_argument("--output", required=True)
    contact_parser.set_defaults(handler=_command_contact_sheet)

    export_parser = subparsers.add_parser("export-manifest", help="Build a report-only store export manifest.")
    export_parser.add_argument("--deck", required=True)
    export_parser.add_argument("--platform", required=True, choices=sorted(_PLATFORM_DEVICE))
    export_parser.add_argument("--locale", required=True)
    export_parser.add_argument("--output-root", required=True)
    export_parser.set_defaults(handler=_command_export_manifest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
