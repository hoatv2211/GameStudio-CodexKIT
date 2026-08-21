from __future__ import annotations

import copy
import json
import io
import os
import binascii
import struct
import subprocess
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "evals" / "schema"

try:
    from scripts import screenshot_showcase as screenshot_showcase
except ImportError:  # pragma: no cover - intentional red-state guard
    screenshot_showcase = None


VALID_HASH_A = "a" * 64
VALID_HASH_B = "b" * 64
REQUIRED_HELPER_API = (
    "validate_payload",
    "sha256_file",
    "image_dimensions",
    "build_contact_sheet",
    "build_store_export_manifest",
)

VALID_CAPTURE_PLAN = {
    "schema_version": 1,
    "plan_id": "capture-plan-001",
    "project": {
        "name": "Crystal Harbor",
        "root": "projects/CrystalHarbor",
        "source_revision": "9f3c1d2a",
    },
    "flows": [
        {
            "order": 1,
            "flow_id": "main-menu-to-hub",
            "scene_path": "Assets/Scenes/MainMenu.unity",
            "entry_point": "MainMenuStart",
            "checkpoint": "hub-visible",
        },
        {
            "order": 2,
            "flow_id": "hub-to-combat",
            "scene_path": "Assets/Scenes/Combat.unity",
            "entry_point": "CombatStart",
            "checkpoint": "combat-ui-ready",
        },
    ],
    "scene_path": "Assets/Scenes/MainMenu.unity",
    "entry_point": "MainMenuStart",
    "checkpoint": "hub-visible",
    "viewport": {"width": 1920, "height": 1080},
    "locale": "en-US",
    "timeout_seconds": 120,
    "reviewer_approval": {
        "approved": True,
        "reviewer": "QA Lead",
        "approved_at": "2026-08-21T10:15:00+07:00",
    },
}

VALID_CAPTURE_RECORD = {
    "schema_version": 1,
    "capture_id": "capture-001",
    "plan_id": "capture-plan-001",
    "raw_image_path": "artifacts/captures/capture-001.png",
    "mime_type": "image/png",
    "dimensions": {"width": 1920, "height": 1080},
    "byte_size": 512000,
    "sha256": VALID_HASH_A,
    "build_snapshot": {
        "unity_version": "2022.3.21f1",
        "editor_state": "PlayMode",
        "project_revision": "9f3c1d2a",
        "build_target": "StandaloneWindows64",
    },
    "runtime_result": "PASS",
    "visual_review": {
        "status": "approved",
        "reviewer": "QA Lead",
        "reviewed_at": "2026-08-21T10:20:00+07:00",
        "reason": "Frame is clean.",
    },
    "limitations": ["Captured from PlayMode."],
    "rejection_reason": None,
    "derived_artifacts": [],
}

VALID_SHOWCASE_DECK = {
    "schema_version": 1,
    "deck_id": "showcase-deck-001",
    "source_capture_id": "capture-001",
    "source_capture_sha256": VALID_HASH_A,
    "source_capture_review": {
        "status": "approved",
        "reviewer": "QA Lead",
        "reviewed_at": "2026-08-21T10:25:00+07:00",
    },
    "outcome": "The combat HUD stays readable during the boss intro.",
    "message": "The capture shows the enemy silhouette, skill bar, and health bar together.",
    "crop": {"x": 120, "y": 80, "width": 1680, "height": 920},
    "focal": {"x": 960, "y": 540, "radius": 260},
    "layout": {
        "background": "stone",
        "frame": "desktop",
        "caption_position": "bottom",
        "safe_area": True,
    },
    "locale": "en-US",
    "direction": "ltr",
    "alt_text": "Combat HUD with boss silhouette and ability bar visible.",
    "approval": {
        "status": "approved",
        "reviewer": "Art Director",
        "approved_at": "2026-08-21T10:28:00+07:00",
    },
}

VALID_EXPORT_DECK_INPUT = {
    **VALID_SHOWCASE_DECK,
    "requirement_snapshot": {
        "source": "store-submission-checklist",
        "captured_at": "2026-08-21T10:30:00+07:00",
        "reference": "steam-hub-2026-08-21",
    },
    "human_approval": {
        "status": "approved",
        "approved_by": "Release Manager",
        "approved_at": "2026-08-21T10:35:00+07:00",
    },
}

VALID_STORE_EXPORT_MANIFEST = {
    "schema_version": 1,
    "manifest_id": "store-export-001",
    "platform": "steam",
    "requirement_snapshot": {
        "source": "store-submission-checklist",
        "captured_at": "2026-08-21T10:30:00+07:00",
        "reference": "steam-hub-2026-08-21",
    },
    "locale": "en-US",
    "device": {
        "preset": "desktop-hd",
        "width": 1920,
        "height": 1080,
        "scale": 1,
        "format": "png",
    },
    "outputs": [
        {
            "slot": "hero",
            "path": "exports/steam/en-US/hero.png",
            "sha256": VALID_HASH_A,
            "bytes": 512000,
            "source_capture_id": "capture-001",
        },
        {
            "slot": "detail",
            "path": "exports/steam/en-US/detail.png",
            "sha256": VALID_HASH_B,
            "bytes": 256000,
            "source_capture_id": "capture-002",
        },
    ],
    "source_capture_ids": ["capture-001", "capture-002"],
    "missing_slots": [],
    "rejected_slots": [],
    "reviewer": "Release Manager",
    "human_approval": {
        "status": "approved",
        "approved_by": "Release Manager",
        "approved_at": "2026-08-21T10:35:00+07:00",
    },
}


def make_png_bytes(*, width: int = 1, height: int = 1, rgb: tuple[int, int, int] = (255, 0, 0), extra_scanline_bytes: bytes = b"") -> bytes:
    raw_scanlines = bytearray()
    pixel_row = bytes(rgb) * width
    for _ in range(height):
        raw_scanlines.extend(b"\x00")
        raw_scanlines.extend(pixel_row)
    raw_scanlines.extend(extra_scanline_bytes)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
        crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)

    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", ihdr),
            png_chunk(b"IDAT", zlib.compress(bytes(raw_scanlines), level=9)),
            png_chunk(b"IEND", b""),
        ]
    )


def make_jpeg_bytes(*, width: int = 1, height: int = 1) -> bytes:
    return bytes.fromhex(
        "ffd8"
        "ffc0001108"
        f"{height:04x}{width:04x}"
        "03"
        "011100021100031100"
        "ffda000c03010002110311003f00"
        "ffd9"
    )


def make_dir_reparse_point(link_path: Path, target_path: Path) -> None:
    try:
        os.symlink(target_path, link_path, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise unittest.SkipTest(f"cannot create directory reparse point: {result.stderr.strip() or result.stdout.strip()}")


class SwappingBinaryReader:
    def __init__(self, handle: object, swap_once: callable) -> None:
        self._handle = handle
        self._swap_once = swap_once

    def read(self, *args: object, **kwargs: object) -> bytes:
        data = self._handle.read(*args, **kwargs)
        self._swap_once()
        return data

    def __enter__(self) -> "SwappingBinaryReader":
        self._handle.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> object:
        return self._handle.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str) -> object:
        return getattr(self._handle, name)


def load_schema(schema_name: str) -> dict[str, object]:
    path = SCHEMA_DIR / f"{schema_name}.schema.json"
    if not path.is_file():
        raise AssertionError(f"missing schema file: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(schema_name))


class ScreenshotShowcaseSchemaTests(unittest.TestCase):
    def assert_valid(self, schema_name: str, payload: dict[str, object]) -> None:
        validator(schema_name).validate(payload)

    def assert_invalid(self, schema_name: str, payload: dict[str, object]) -> None:
        with self.assertRaises(ValidationError):
            validator(schema_name).validate(payload)

    def test_capture_plan_schema_is_closed_and_requires_approved_flow_metadata(self) -> None:
        schema = load_schema("capture-plan")
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
        )
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/capture-plan.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(VALID_CAPTURE_PLAN), schema["required"])
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        self.assert_valid("capture-plan", VALID_CAPTURE_PLAN)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["unexpected"] = True
        self.assert_invalid("capture-plan", invalid_plan)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["project"]["root"] = "/tmp/project"
        self.assert_invalid("capture-plan", invalid_plan)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["scene_path"] = "Assets/../MainMenu.unity"
        self.assert_invalid("capture-plan", invalid_plan)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["plan_id"] = ""
        self.assert_invalid("capture-plan", invalid_plan)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["reviewer_approval"]["approved"] = False
        self.assert_invalid("capture-plan", invalid_plan)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["reviewer_approval"]["reviewer"] = " QA Lead "
        self.assert_invalid("capture-plan", invalid_plan)

    def test_capture_plan_schema_rejects_empty_flow_identifiers(self) -> None:
        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["flows"][0]["flow_id"] = ""
        self.assert_invalid("capture-plan", invalid_plan)

    def test_capture_plan_schema_rejects_whitespace_and_crlf_in_text_fields(self) -> None:
        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["project"]["name"] = " Crystal Harbor "
        self.assert_invalid("capture-plan", invalid_plan)

        invalid_plan = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_plan["entry_point"] = "MainMenuStart\r\n"
        self.assert_invalid("capture-plan", invalid_plan)

    def test_capture_record_schema_is_closed_and_requires_review_metadata(self) -> None:
        schema = load_schema("capture-record")
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
        )
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/capture-record.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(VALID_CAPTURE_RECORD), schema["required"])
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        self.assert_valid("capture-record", VALID_CAPTURE_RECORD)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["plan_id"] = ""
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["raw_image_path"] = "/tmp/capture.png"
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["raw_image_path"] = "artifacts/../capture.png"
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["capture_id"] = ""
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["sha256"] = "not-a-hash"
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["dimensions"]["width"] = 0
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        del invalid_record["visual_review"]
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["visual_review"]["status"] = "pending"
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["build_snapshot"]["build_target"] = " StandaloneWindows64 "
        self.assert_invalid("capture-record", invalid_record)

    def test_capture_record_schema_rejects_whitespace_and_crlf_in_review_fields(self) -> None:
        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["visual_review"]["reviewer"] = " QA Lead "
        self.assert_invalid("capture-record", invalid_record)

        invalid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
        invalid_record["visual_review"]["reason"] = "Frame is clean.\r\n"
        self.assert_invalid("capture-record", invalid_record)

    def test_showcase_deck_schema_is_closed_and_requires_approved_source_capture(self) -> None:
        schema = load_schema("showcase-deck")
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
        )
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/showcase-deck.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(VALID_SHOWCASE_DECK), schema["required"])
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        self.assert_valid("showcase-deck", VALID_SHOWCASE_DECK)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["deck_id"] = ""
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["unexpected"] = True
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["source_capture_id"] = ""
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["source_capture_sha256"] = "broken"
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["source_capture_review"]["status"] = "rejected"
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["approval"]["status"] = "pending"
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["alt_text"] = ""
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["outcome"] = " The combat HUD stays readable during the boss intro. "
        self.assert_invalid("showcase-deck", invalid_deck)

    def test_showcase_deck_schema_rejects_whitespace_and_crlf_in_text_fields(self) -> None:
        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["source_capture_review"]["reviewer"] = " Art Director "
        self.assert_invalid("showcase-deck", invalid_deck)

        invalid_deck = copy.deepcopy(VALID_SHOWCASE_DECK)
        invalid_deck["alt_text"] = "Combat HUD with boss silhouette and ability bar visible.\r\n"
        self.assert_invalid("showcase-deck", invalid_deck)

    def test_store_export_manifest_schema_is_closed_and_requires_human_approval(self) -> None:
        schema = load_schema("store-export-manifest")
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
        )
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/store-export-manifest.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(VALID_STORE_EXPORT_MANIFEST), schema["required"])
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        self.assert_valid("store-export-manifest", VALID_STORE_EXPORT_MANIFEST)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["manifest_id"] = ""
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["unexpected"] = True
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["device"]["preset"] = "unsupported"
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["device"]["width"] = 1280
        invalid_manifest["device"]["height"] = 720
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["device"]["width"] = 1024
        invalid_manifest["device"]["height"] = 768
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["human_approval"]["status"] = "pending"
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        del invalid_manifest["human_approval"]
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["outputs"][0]["path"] = "/tmp/hero.png"
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["outputs"][0]["path"] = "exports/../hero.png"
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["outputs"][0]["sha256"] = "broken"
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["source_capture_ids"] = []
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["reviewer"] = " Release Manager "
        self.assert_invalid("store-export-manifest", invalid_manifest)

    def test_store_export_manifest_schema_rejects_whitespace_and_crlf_in_text_fields(self) -> None:
        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["requirement_snapshot"]["reference"] = "steam-hub-2026-08-21\r\n"
        self.assert_invalid("store-export-manifest", invalid_manifest)

        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["human_approval"]["approved_by"] = " Release Manager "
        self.assert_invalid("store-export-manifest", invalid_manifest)


class ScreenshotShowcaseHelperTests(unittest.TestCase):
    def require_helper_module(self) -> object:
        self.assertIsNotNone(
            screenshot_showcase,
            "scripts.screenshot_showcase is not implemented yet",
        )
        for name in REQUIRED_HELPER_API:
            self.assertTrue(
                hasattr(screenshot_showcase, name),
                f"scripts.screenshot_showcase is missing required symbol: {name}",
            )
        return screenshot_showcase

    def test_validate_payload_returns_sorted_error_messages(self) -> None:
        module = self.require_helper_module()
        invalid_payload = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_payload["project"]["root"] = "/tmp/project"
        invalid_payload["reviewer_approval"]["approved"] = False

        errors = module.validate_payload("capture-plan", invalid_payload)

        self.assertEqual(sorted(errors), errors)
        self.assertTrue(any("project" in error for error in errors))
        self.assertTrue(any("reviewer_approval" in error for error in errors))

    def test_validate_payload_rejects_duplicate_flow_ids_and_orders(self) -> None:
        module = self.require_helper_module()
        invalid_payload = copy.deepcopy(VALID_CAPTURE_PLAN)
        invalid_payload["flows"][1]["flow_id"] = invalid_payload["flows"][0]["flow_id"]
        invalid_payload["flows"][1]["order"] = invalid_payload["flows"][0]["order"]

        errors = module.validate_payload("capture-plan", invalid_payload)

        self.assertTrue(any("flow" in error.lower() for error in errors))
        self.assertTrue(any("order" in error.lower() for error in errors))

    def test_sha256_file_and_image_dimensions_work_on_supported_images(self) -> None:
        module = self.require_helper_module()

        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a"
            "0000000d4948445200000001000000010802000000907753de"
            "0000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082"
        )

        with TemporaryDirectory() as temp_dir:
            png_path = Path(temp_dir) / "pixel.png"
            png_path.write_bytes(png_bytes)

            self.assertEqual(
                "029f7c3cc50a84d1be8e14b7ccabf596f130b2b1c0390ef4b6062c8230f8de30",
                module.sha256_file(png_path),
            )
            self.assertEqual((1, 1), module.image_dimensions(png_path))

    def test_build_contact_sheet_and_store_export_manifest_are_report_only(self) -> None:
        module = self.require_helper_module()

        records = [
            {
                "capture_id": "capture-001",
                "order": 2,
                "runtime_result": "PASS",
                "visual_review": {"status": "approved"},
                "raw_image_path": "artifacts/captures/capture-001.png",
                "sha256": VALID_HASH_A,
                "rejection_reason": None,
            },
            {
                "capture_id": "capture-002",
                "order": 1,
                "runtime_result": "FAIL",
                "visual_review": {"status": "rejected"},
                "raw_image_path": "artifacts/captures/capture-002.png",
                "sha256": VALID_HASH_B,
                "rejection_reason": "UI clipped on the right edge.",
            },
        ]

        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            contact_sheet = temp_root / "review.html"
            deck = copy.deepcopy(VALID_EXPORT_DECK_INPUT)
            manifest = module.build_contact_sheet(records, contact_sheet)
            self.assertEqual("review.html", contact_sheet.name)
            self.assertEqual(contact_sheet, Path(manifest["artifact_path"]))
            self.assertEqual(2, len(manifest["records"]))

            export_root = temp_root / "exports"
            export_manifest = module.build_store_export_manifest(
                deck,
                platform="steam",
                locale="en-US",
                output_root=export_root,
            )
            self.assertEqual("steam", export_manifest["platform"])
            self.assertTrue(Path(export_manifest["artifact_path"]).is_relative_to(export_root))

    def test_build_contact_sheet_blocks_reparse_point_output_parent(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            trap_root = temp_root / "trap"
            trap_root.mkdir()
            output_parent = temp_root / "linked-output"
            make_dir_reparse_point(output_parent, trap_root)
            output_path = output_parent / "review.html"

            result = module.build_contact_sheet([], output_path)

            self.assertEqual("BLOCKED", result["verdict"])
            self.assertTrue(any("reparse point is not allowed" in item for item in result["failures"]))
            self.assertFalse((trap_root / "review.html").exists())

    def test_write_text_output_cleans_up_file_created_during_failed_write(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            output_path = temp_root / "review.html"
            sibling_path = temp_root / "keep.txt"
            sibling_path.write_text("keep me", encoding="utf-8")

            original_open = Path.open

            class FailingWriteHandle:
                def __init__(self, handle: object) -> None:
                    self._handle = handle

                def write(self, content: str) -> int:
                    raise OSError("simulated write failure")

                def __enter__(self) -> "FailingWriteHandle":
                    self._handle.__enter__()
                    return self

                def __exit__(self, exc_type: object, exc: object, tb: object) -> object:
                    return self._handle.__exit__(exc_type, exc, tb)

                def __getattr__(self, name: str) -> object:
                    return getattr(self._handle, name)

            def patched_open(path_obj: Path, *args: object, **kwargs: object) -> object:
                mode = args[0] if args else kwargs.get("mode", "r")
                handle = original_open(path_obj, *args, **kwargs)
                if Path(path_obj) == output_path and mode == "x":
                    return FailingWriteHandle(handle)
                return handle

            with mock.patch.object(Path, "open", autospec=True, side_effect=patched_open):
                error = module._write_text_output(output_path, "<html>broken</html>")

            self.assertEqual(f"cannot write output: simulated write failure", error)
            self.assertFalse(output_path.exists())
            self.assertEqual("keep me", sibling_path.read_text(encoding="utf-8"))

    def test_build_store_export_manifest_blocks_reparse_point_output_root(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            trap_root = temp_root / "trap"
            trap_root.mkdir()
            output_root = temp_root / "exports-link"
            make_dir_reparse_point(output_root, trap_root)

            result = module.build_store_export_manifest(
                copy.deepcopy(VALID_EXPORT_DECK_INPUT),
                platform="steam",
                locale="en-US",
                output_root=output_root,
            )

            self.assertEqual("BLOCKED", result["verdict"])
            self.assertTrue(any("reparse point is not allowed" in item for item in result["failures"]))
            self.assertFalse((trap_root / "steam" / "en-US" / "store-export-manifest.json").exists())

    def test_validate_payload_rejects_duplicate_output_slots(self) -> None:
        module = self.require_helper_module()
        invalid_manifest = copy.deepcopy(VALID_STORE_EXPORT_MANIFEST)
        invalid_manifest["outputs"][1]["slot"] = invalid_manifest["outputs"][0]["slot"]

        errors = module.validate_payload("store-export-manifest", invalid_manifest)

        self.assertTrue(any("slot" in error.lower() for error in errors))

    def test_verify_capture_record_pass_fail_and_blocked(self) -> None:
        module = self.require_helper_module()
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a"
            "0000000d4948445200000001000000010802000000907753de"
            "0000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082"
        )

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            capture_dir = project_root / "artifacts" / "captures"
            capture_dir.mkdir(parents=True)
            png_path = capture_dir / "capture-001.png"
            png_path.write_bytes(png_bytes)

            valid_record = copy.deepcopy(VALID_CAPTURE_RECORD)
            valid_record["dimensions"] = {"width": 1, "height": 1}
            valid_record["byte_size"] = png_path.stat().st_size
            valid_record["sha256"] = module.sha256_file(png_path)

            passed = module.verify_capture_record(project_root, valid_record)
            self.assertEqual("PASS", passed["verdict"])
            self.assertEqual([], passed["failures"])

            failed_record = copy.deepcopy(valid_record)
            failed_record["byte_size"] += 1
            failed = module.verify_capture_record(project_root, failed_record)
            self.assertEqual("FAIL", failed["verdict"])
            self.assertTrue(any("byte_size" in item for item in failed["failures"]))

            blocked_path = capture_dir / "capture-002.jpg"
            blocked_path.write_bytes(b"not-a-jpeg")
            blocked_record = copy.deepcopy(valid_record)
            blocked_record["capture_id"] = "capture-002"
            blocked_record["raw_image_path"] = "artifacts/captures/capture-002.jpg"
            blocked_record["mime_type"] = "image/jpeg"
            blocked_record["byte_size"] = blocked_path.stat().st_size
            blocked_record["sha256"] = module.sha256_file(blocked_path)
            blocked = module.verify_capture_record(project_root, blocked_record)
            self.assertEqual("BLOCKED", blocked["verdict"])
            self.assertTrue(any("unsupported image format" in item for item in blocked["failures"]))

    def test_verify_capture_record_rejects_png_bytes_recorded_as_jpeg(self) -> None:
        module = self.require_helper_module()
        png_bytes = make_png_bytes()

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            capture_dir = project_root / "artifacts" / "captures"
            capture_dir.mkdir(parents=True)
            capture_path = capture_dir / "capture-001.jpg"
            capture_path.write_bytes(png_bytes)

            record = copy.deepcopy(VALID_CAPTURE_RECORD)
            record["raw_image_path"] = "artifacts/captures/capture-001.jpg"
            record["mime_type"] = "image/jpeg"
            record["dimensions"] = {"width": 1, "height": 1}
            record["byte_size"] = capture_path.stat().st_size
            record["sha256"] = module.sha256_file(capture_path)

            result = module.verify_capture_record(project_root, record)

            self.assertEqual("FAIL", result["verdict"])
            self.assertTrue(any("mime_type" in item or "format" in item for item in result["failures"]))

    def test_verify_capture_record_rejects_jpeg_bytes_recorded_as_png(self) -> None:
        module = self.require_helper_module()
        jpeg_bytes = make_jpeg_bytes()

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            capture_dir = project_root / "artifacts" / "captures"
            capture_dir.mkdir(parents=True)
            capture_path = capture_dir / "capture-001.png"
            capture_path.write_bytes(jpeg_bytes)

            record = copy.deepcopy(VALID_CAPTURE_RECORD)
            record["raw_image_path"] = "artifacts/captures/capture-001.png"
            record["mime_type"] = "image/png"
            record["dimensions"] = {"width": 1, "height": 1}
            record["byte_size"] = capture_path.stat().st_size
            record["sha256"] = module.sha256_file(capture_path)

            result = module.verify_capture_record(project_root, record)

            self.assertEqual("FAIL", result["verdict"])
            self.assertTrue(any("mime_type" in item or "format" in item for item in result["failures"]))

    def test_verify_capture_record_rejects_dangling_symlink_path(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            target = project_root / "artifacts" / "captures" / "capture-001.png"
            target.parent.mkdir(parents=True)
            try:
                os.symlink(project_root / "missing.png", target)
            except (OSError, NotImplementedError):
                with mock.patch.object(module, "_contains_reparse_point", return_value=True):
                    result = module._check_existing_path_chain(target, project_root)
                self.assertIsNotNone(result)
                self.assertIn("reparse point is not allowed", result)
                return

            record = copy.deepcopy(VALID_CAPTURE_RECORD)
            record["dimensions"] = {"width": 1, "height": 1}
            record["byte_size"] = 1
            result = module.verify_capture_record(project_root, record)

            self.assertEqual("FAIL", result["verdict"])
            self.assertTrue(any("reparse point is not allowed" in item for item in result["failures"]))

    def test_verify_capture_record_uses_a_single_opened_file_view(self) -> None:
        module = self.require_helper_module()
        png_a = make_png_bytes(rgb=(255, 0, 0))
        png_b = make_png_bytes(rgb=(0, 255, 0))
        self.assertEqual(len(png_a), len(png_b))

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            capture_dir = project_root / "artifacts" / "captures"
            capture_dir.mkdir(parents=True)
            png_path = capture_dir / "capture-001.png"
            png_path.write_bytes(png_a)
            replacement_path = capture_dir / "capture-001-replacement.png"
            replacement_path.write_bytes(png_b)

            record = copy.deepcopy(VALID_CAPTURE_RECORD)
            record["dimensions"] = {"width": 1, "height": 1}
            record["byte_size"] = len(png_b)
            record["sha256"] = module.sha256_file(replacement_path)

            original_open = Path.open
            reads = {"count": 0}

            def patched_open(path_obj: Path, *args: object, **kwargs: object) -> object:
                mode = args[0] if args else kwargs.get("mode", "r")
                if Path(path_obj) == png_path and mode == "rb":
                    reads["count"] += 1
                    if reads["count"] == 1:
                        return original_open(path_obj, *args, **kwargs)
                    return original_open(replacement_path, *args, **kwargs)
                return original_open(path_obj, *args, **kwargs)

            with mock.patch.object(Path, "open", autospec=True, side_effect=patched_open):
                result = module.verify_capture_record(project_root, record)

            self.assertEqual("FAIL", result["verdict"])
            self.assertTrue(any("sha256" in item for item in result["failures"]))

    def test_build_store_export_manifest_requires_explicit_snapshot_and_approval(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            deck = copy.deepcopy(VALID_EXPORT_DECK_INPUT)
            deck.pop("requirement_snapshot")
            deck.pop("human_approval")

            result = module.build_store_export_manifest(
                deck,
                platform="steam",
                locale="en-US",
                output_root=temp_root / "exports",
            )

            self.assertEqual("BLOCKED", result["verdict"])
            self.assertTrue(any("requirement_snapshot" in item for item in result["failures"]))
            self.assertTrue(any("human_approval" in item for item in result["failures"]))

    def test_build_store_export_manifest_uses_explicit_snapshot_and_approval_inputs(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            export_root = temp_root / "exports"
            platform_root = export_root / "steam" / "en-US"
            platform_root.mkdir(parents=True)
            hero = platform_root / "hero.png"
            detail = platform_root / "detail.png"
            hero.write_bytes(b"hero")
            detail.write_bytes(b"detail")
            deck = copy.deepcopy(VALID_EXPORT_DECK_INPUT)
            deck["requirement_snapshot"] = {
                "source": "store-submission-checklist",
                "captured_at": "2026-08-30T09:00:00+07:00",
                "reference": "steam-2026-08-30-approved",
            }
            deck["human_approval"] = {
                "status": "approved",
                "approved_by": "Launch Director",
                "approved_at": "2026-08-30T09:05:00+07:00",
            }

            with mock.patch.object(module, "image_dimensions", return_value=(1920, 1080)), mock.patch.object(
                module, "sha256_file", side_effect=["1" * 64, "2" * 64]
            ):
                result = module.build_store_export_manifest(
                    deck,
                    platform="steam",
                    locale="en-US",
                    output_root=export_root,
                )

            self.assertEqual("PASS", result["verdict"])
            manifest = result["manifest"]
            self.assertEqual(deck["requirement_snapshot"], manifest["requirement_snapshot"])
            self.assertEqual(deck["human_approval"], manifest["human_approval"])
            self.assertEqual("Launch Director", manifest["reviewer"])

    def test_build_store_export_manifest_fails_partial_required_slots_and_retains_slot_lists(self) -> None:
        module = self.require_helper_module()
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            export_root = temp_root / "exports"
            platform_root = export_root / "steam" / "en-US"
            platform_root.mkdir(parents=True)
            hero = platform_root / "hero.png"
            detail = platform_root / "detail.png"
            hero_bytes = b"hero-export"
            detail_bytes = b"detail-export"
            hero.write_bytes(hero_bytes)
            detail.write_bytes(detail_bytes)
            deck = copy.deepcopy(VALID_EXPORT_DECK_INPUT)

            with mock.patch.object(
                module,
                "image_dimensions",
                side_effect=[(1920, 1080), (1280, 720)],
            ), mock.patch.object(module, "sha256_file", side_effect=["1" * 64, "2" * 64]):
                result = module.build_store_export_manifest(
                    deck,
                    platform="steam",
                    locale="en-US",
                    output_root=export_root,
                )

            self.assertEqual("FAIL", result["verdict"])
            self.assertEqual(["detail"], result["manifest"]["missing_slots"])
            self.assertEqual(["detail"], result["manifest"]["rejected_slots"])
            self.assertEqual(["hero"], [item["slot"] for item in result["manifest"]["outputs"]])
            self.assertEqual(hero_bytes, hero.read_bytes())
            self.assertEqual(detail_bytes, detail.read_bytes())

    def test_image_dimensions_rejects_png_with_oversized_decompressed_idat(self) -> None:
        module = self.require_helper_module()
        png_bytes = make_png_bytes(extra_scanline_bytes=b"\x00" * (256 * 1024))

        with TemporaryDirectory() as temp_dir:
            png_path = Path(temp_dir) / "bomb.png"
            png_path.write_bytes(png_bytes)

            with self.assertRaisesRegex(ValueError, "PNG image data exceeds"):
                module.image_dimensions(png_path)

    def test_cli_verify_capture_exit_codes_cover_pass_fail_and_blocked(self) -> None:
        module = self.require_helper_module()
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a"
            "0000000d4948445200000001000000010802000000907753de"
            "0000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082"
        )

        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "project"
            capture_dir = project_root / "artifacts" / "captures"
            capture_dir.mkdir(parents=True)
            png_path = capture_dir / "capture-001.png"
            png_path.write_bytes(png_bytes)
            jpg_path = capture_dir / "capture-002.jpg"
            jpg_path.write_bytes(b"bad-jpeg")

            pass_record = copy.deepcopy(VALID_CAPTURE_RECORD)
            pass_record["dimensions"] = {"width": 1, "height": 1}
            pass_record["byte_size"] = png_path.stat().st_size
            pass_record["sha256"] = module.sha256_file(png_path)
            fail_record = copy.deepcopy(pass_record)
            fail_record["byte_size"] += 1
            blocked_record = copy.deepcopy(pass_record)
            blocked_record["capture_id"] = "capture-002"
            blocked_record["raw_image_path"] = "artifacts/captures/capture-002.jpg"
            blocked_record["mime_type"] = "image/jpeg"
            blocked_record["byte_size"] = jpg_path.stat().st_size
            blocked_record["sha256"] = module.sha256_file(jpg_path)

            pass_path = temp_root / "pass.json"
            fail_path = temp_root / "fail.json"
            blocked_path = temp_root / "blocked.json"
            pass_path.write_text(json.dumps(pass_record), encoding="utf-8")
            fail_path.write_text(json.dumps(fail_record), encoding="utf-8")
            blocked_path.write_text(json.dumps(blocked_record), encoding="utf-8")

            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                pass_exit = module.main(
                    ["verify-capture", str(project_root), "--record", str(pass_path)]
                )
            self.assertEqual(0, pass_exit)
            self.assertEqual("PASS", json.loads(stdout.getvalue())["verdict"])

            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                fail_exit = module.main(
                    ["verify-capture", str(project_root), "--record", str(fail_path)]
                )
            self.assertEqual(1, fail_exit)
            self.assertEqual("FAIL", json.loads(stdout.getvalue())["verdict"])

            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                blocked_exit = module.main(
                    ["verify-capture", str(project_root), "--record", str(blocked_path)]
                )
            self.assertEqual(2, blocked_exit)
            self.assertEqual("BLOCKED", json.loads(stdout.getvalue())["verdict"])


if __name__ == "__main__":
    unittest.main()
