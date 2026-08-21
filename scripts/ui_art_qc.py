"""Deterministic static QC for Figma/UI art briefs and exported assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

try:
    from scripts.ui_art_motion import _safe_path, load_manifest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ui_art_motion import _safe_path, load_manifest


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_IMAGE_BYTES = 64 * 1024 * 1024
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_PNG_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}
_JPEG_SOF_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}
_SVG_NUMBER = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*$", re.IGNORECASE)


def _schema_candidates(schema_path: Path | str) -> list[Path]:
    supplied = Path(schema_path)
    name = supplied.name
    script_root = Path(__file__).resolve().parent
    return [
        supplied,
        script_root.parent / "schemas" / name,
        script_root / "schemas" / name,
        script_root.parent / "evals" / "schema" / name,
    ]


def load_design_brief(path: Path | str, schema_path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load design brief {path}: {error}") from error
    schema_file = next((candidate for candidate in _schema_candidates(schema_path) if candidate.is_file()), None)
    if schema_file is None:
        raise ValueError(f"cannot load design brief schema {schema_path}")
    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(payload),
            key=lambda item: (tuple(str(part) for part in item.absolute_path), item.message),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as error:
        raise ValueError(f"invalid design brief schema {schema_file}: {error}") from error
    if errors:
        location = "/".join(str(part) for part in errors[0].absolute_path) or "$"
        raise ValueError(f"design brief validation failed: {location}: {errors[0].message}")
    if not isinstance(payload, dict):
        raise ValueError("design brief must be an object")
    return payload


def _read_image(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read exported asset {path}: {error}") from error
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f"exported asset exceeds static QC size limit: {path}")
    return data


def _png_info(path: Path) -> dict[str, Any]:
    data = _read_image(path)
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"unsupported PNG signature: {path}")
    offset = len(PNG_SIGNATURE)
    ihdr: tuple[int, int, int, int, int, int, int] | None = None
    idat: list[bytes] = []
    has_transparency = False
    saw_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError(f"PNG chunk header is truncated: {path}")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise ValueError(f"PNG chunk is truncated: {path}")
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"PNG CRC mismatch in {chunk_type.decode('latin1')}: {path}")
        if ihdr is None and chunk_type != b"IHDR":
            raise ValueError(f"PNG is missing IHDR: {path}")
        if chunk_type == b"IHDR":
            if ihdr is not None or length != 13:
                raise ValueError(f"PNG IHDR is invalid: {path}")
            ihdr = struct.unpack(">IIBBBBB", chunk_data)
            width, height, bit_depth, color_type, compression, filter_method, interlace = ihdr
            if width < 1 or height < 1:
                raise ValueError(f"PNG dimensions are invalid: {path}")
            if color_type not in _PNG_CHANNELS or bit_depth not in _PNG_BIT_DEPTHS[color_type]:
                raise ValueError(f"PNG color type or bit depth is invalid: {path}")
            if compression != 0 or filter_method != 0:
                raise ValueError(f"PNG compression or filter method is unsupported: {path}")
            if interlace != 0:
                raise ValueError(f"interlaced PNG is unsupported by static QC: {path}")
        elif chunk_type == b"IDAT":
            idat.append(chunk_data)
        elif chunk_type == b"tRNS":
            has_transparency = True
        elif chunk_type == b"IEND":
            if length != 0:
                raise ValueError(f"PNG IEND is invalid: {path}")
            saw_iend = True
            offset = chunk_end
            if offset != len(data):
                raise ValueError(f"PNG has trailing bytes after IEND: {path}")
            break
        offset = chunk_end
    if ihdr is None or not idat or not saw_iend:
        raise ValueError(f"PNG is missing required chunks: {path}")
    width, height, bit_depth, color_type, _, _, _ = ihdr
    row_bytes = (width * _PNG_CHANNELS[color_type] * bit_depth + 7) // 8
    expected_raw_size = (row_bytes + 1) * height
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b"".join(idat), expected_raw_size + 1)
        if len(raw) <= expected_raw_size:
            raw += decoder.flush(expected_raw_size + 1 - len(raw))
    except zlib.error as error:
        raise ValueError(f"PNG image data cannot be decoded: {path}") from error
    if len(raw) != expected_raw_size or not decoder.eof or decoder.unused_data:
        raise ValueError(f"PNG image data is incomplete or oversized: {path}")
    if any(raw[index] > 4 for index in range(0, len(raw), row_bytes + 1)):
        raise ValueError(f"PNG contains an invalid scanline filter: {path}")
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "has_alpha": color_type in {4, 6} or has_transparency,
        "alpha_checked": True,
    }


def _jpeg_info(path: Path) -> dict[str, Any]:
    data = _read_image(path)
    if not data.startswith(b"\xFF\xD8"):
        raise ValueError(f"unsupported JPEG signature: {path}")
    offset = 2
    dimensions: tuple[int, int, int, int] | None = None
    saw_sos = False
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError(f"JPEG marker is invalid: {path}")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise ValueError(f"JPEG marker is truncated: {path}")
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            break
        if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            raise ValueError(f"JPEG segment length is truncated: {path}")
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(data):
            raise ValueError(f"JPEG segment is truncated: {path}")
        segment = data[offset + 2 : offset + segment_length]
        if marker in _JPEG_SOF_MARKERS:
            if len(segment) < 6:
                raise ValueError(f"JPEG frame header is invalid: {path}")
            precision = segment[0]
            height, width = struct.unpack(">HH", segment[1:5])
            components = segment[5]
            if width < 1 or height < 1 or components < 1:
                raise ValueError(f"JPEG dimensions are invalid: {path}")
            dimensions = (width, height, precision, components)
        if marker == 0xDA:
            saw_sos = True
            break
        offset += segment_length
    if not dimensions or not saw_sos or not data.endswith(b"\xFF\xD9"):
        raise ValueError(f"JPEG is missing a complete frame or EOI: {path}")
    width, height, precision, components = dimensions
    return {
        "width": width,
        "height": height,
        "precision": precision,
        "components": components,
        "has_alpha": False,
        "alpha_checked": True,
    }


def _svg_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = _SVG_NUMBER.fullmatch(value)
    return float(match.group(1)) if match else None


def _svg_info(path: Path) -> dict[str, Any]:
    data = _read_image(path)
    if b"<!DOCTYPE" in data.upper():
        raise ValueError(f"SVG DOCTYPE is not allowed by static QC: {path}")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(f"SVG XML cannot be parsed: {path}") from error
    if root.tag.rsplit("}", 1)[-1].casefold() != "svg":
        raise ValueError(f"SVG root element is invalid: {path}")
    width = _svg_number(root.attrib.get("width"))
    height = _svg_number(root.attrib.get("height"))
    view_box = root.attrib.get("viewBox", "").replace(",", " ").split()
    if (width is None or height is None) and len(view_box) == 4:
        try:
            width = float(view_box[2])
            height = float(view_box[3])
        except ValueError:
            width = height = None
    if width is None or height is None or width <= 0 or height <= 0:
        raise ValueError(f"SVG dimensions are missing or invalid: {path}")
    return {
        "width": width,
        "height": height,
        "has_alpha": None,
        "alpha_checked": False,
    }


def build_art_qc_report(
    project_root: Path | str,
    design_brief_path: Path | str,
    asset_manifest_path: Path | str,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    brief = load_design_brief(
        design_brief_path,
        root / "evals" / "schema" / "ui-design-brief.schema.json",
    )
    assets = load_manifest(
        asset_manifest_path,
        root / "evals" / "schema" / "ui-asset-manifest.schema.json",
    )
    failures: list[str] = []
    checks: list[dict[str, Any]] = []
    if brief["source_revision"] != assets["figma"]["source_revision"]:
        failures.append("source revision mismatch between design brief and asset manifest")
    variants = [variant["id"] for variant in brief["variants"]]
    if len(variants) != len(set(variants)):
        failures.append("duplicate design brief variant id")
    if brief["copy"]["lines"] and brief["copy"]["text_policy"] != "typeset-in-figma":
        failures.append("AI art copy must use typeset-in-figma policy")
    for asset in assets["assets"]:
        try:
            _, source = _safe_path(
                root,
                asset["export_path"],
                label=f"asset {asset['id']} export",
                must_exist=True,
            )
        except ValueError as error:
            failures.append(str(error))
            continue
        try:
            actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as error:
            failures.append(f"cannot hash exported asset {asset['id']}: {error}")
            continue
        if actual_hash != asset["export_sha256"]:
            failures.append(f"export hash mismatch for asset {asset['id']}")
        if asset["ai_provenance"]["output_sha256"] != asset["export_sha256"]:
            failures.append(f"AI output hash mismatch for asset {asset['id']}")
        try:
            if asset["format"] == "png":
                info = _png_info(source)
            elif asset["format"] == "jpg":
                info = _jpeg_info(source)
            elif asset["format"] == "svg":
                info = _svg_info(source)
            else:
                raise ValueError(f"unsupported static QC format: {asset['format']}")
        except (OSError, ValueError) as error:
            failures.append(str(error))
            continue
        if info["width"] != asset["width"] or info["height"] != asset["height"]:
            failures.append(
                f"dimension mismatch for {asset['id']}: manifest {asset['width']}x{asset['height']} vs file {info['width']}x{info['height']}"
            )
        if info["has_alpha"] is not None and bool(asset["alpha"]) != info["has_alpha"]:
            if asset["alpha"]:
                failures.append(f"alpha channel missing for {asset['id']}")
            else:
                failures.append(f"unexpected alpha channel for {asset['id']}")
        checks.append(
            {
                "asset_id": asset["id"],
                "format": asset["format"],
                "sha256": actual_hash,
                **info,
            }
        )
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "design_brief": brief["id"],
        "source_revision": brief["source_revision"],
        "asset_count": len(assets["assets"]),
        "checks": checks,
        "failures": failures,
        "limitations": [
            "static QC does not prove Figma visual approval or Unity runtime behavior",
            "SVG alpha is not pixel-decoded",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_art_qc_report(args.project_root, args.brief, args.assets)
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        report = {"verdict": "FAIL", "failures": [str(error)]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
