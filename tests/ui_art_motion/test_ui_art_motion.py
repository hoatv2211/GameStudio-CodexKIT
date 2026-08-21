from __future__ import annotations

import copy
import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def _validator(name: str) -> Draft202012Validator:
    payload = json.loads(
        (ROOT / "evals" / "schema" / name).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(payload)
    return Draft202012Validator(payload)


def asset_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "ui_stack": "ugui",
        "figma": {
            "file_id": "game-ui",
            "page_id": "hud",
            "source_revision": "rev-42",
            "captured_at": "2026-08-21T10:00:00+07:00",
        },
        "assets": [
            {
                "id": "hud-frame",
                "node_id": "10:20",
                "ai_provenance": {
                    "provider": "configured-image-tool",
                    "model": "approved-model",
                    "prompt": "bronze fantasy HUD frame",
                    "reference_sha256": [],
                    "output_sha256": "a" * 64,
                    "reviewer": "Art Lead",
                },
                "export_path": "art/ui/export/hud-frame.png",
                "export_sha256": "a" * 64,
                "unity_target": "client/Assets/UI/HUD/hud-frame.png",
                "kind": "nine-slice",
                "format": "png",
                "width": 512,
                "height": 256,
                "scale": 1,
                "alpha": True,
                "color_space": "srgb",
                "pixels_per_unit": 100,
                "pivot": [0.5, 0.5],
                "borders": [24, 24, 24, 24],
                "atlas_group": "hud",
                "compression": "project-default",
                "owner": "UI Artist",
                "reviewer": "Art Lead",
                "limitations": [],
                "restore_source": "Figma game-ui rev-42 node 10:20",
            }
        ],
    }


def motion_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "ui_stack": "ugui",
        "source_revision": "rev-42",
        "motions": [
            {
                "id": "hud-enter",
                "target": "hud-root",
                "trigger": "show",
                "interruption": "restart",
                "start_state": {"alpha": 0.0, "scale": [0.96, 0.96]},
                "end_state": {"alpha": 1.0, "scale": [1.0, 1.0]},
                "duration_ms": 220,
                "easing": "ease-out-cubic",
                "reverse": True,
                "reduced_motion": "snap-to-end",
                "driver": "animator",
                "dependency_evidence": [],
                "unity_target": "client/Assets/UI/HUD/Hud.controller",
                "verification": ["show", "hide", "interrupt"],
                "budget_ms": 0.25,
            }
        ],
    }


def _write_fixture(root: Path) -> tuple[Path, Path]:
    export = root / "art/ui/export/hud-frame.png"
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_bytes(b"ui-frame")
    assets = asset_manifest()
    assets["assets"][0]["export_sha256"] = hashlib.sha256(export.read_bytes()).hexdigest()
    assets["assets"][0]["ai_provenance"]["output_sha256"] = assets["assets"][0]["export_sha256"]
    asset_path = root / "ui-asset-manifest.json"
    motion_path = root / "ui-motion-manifest.json"
    asset_path.write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")
    motion_path.write_text(json.dumps(motion_manifest(), indent=2) + "\n", encoding="utf-8")
    return asset_path, motion_path


def design_brief() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "hud-bronze-v1",
        "source_revision": "rev-42",
        "goal": {
            "screen": "combat-hud",
            "audience": "action-rpg player",
            "success_criteria": ["readable health state", "fast target recognition"],
        },
        "format": {
            "width": 512,
            "height": 256,
            "scale": 1,
            "safe_margins": [24, 24, 24, 24],
        },
        "layout": {
            "grid": "8px",
            "hierarchy": ["health", "mana", "status"],
        },
        "type_system": {
            "font_family": "project-ui-font",
            "font_weights": [400, 700],
            "leading": 1.1,
            "tracking": 0,
        },
        "color_material": {
            "background": "#17120f",
            "text": "#fff3d6",
            "accent": "#c58a3a",
            "texture": "subtle parchment grain",
        },
        "imagery": {
            "style_lane": "dark stone and bronze fantasy",
            "reference_ids": ["figma:game-ui:10:20"],
            "material_language": "worn bronze edge with restrained glow",
        },
        "copy": {
            "lines": [],
            "text_policy": "typeset-in-figma",
        },
        "constraints": {
            "must_keep": ["approved bronze palette", "nine-slice-safe corners"],
            "change_only": ["texture intensity"],
            "negative": ["no watermark", "no extra text", "no rainbow gradients"],
        },
        "variants": [
            {"id": "base", "change": "none", "status": "approved"},
            {"id": "grain-light", "change": "texture intensity", "status": "candidate"},
        ],
        "owner": "UI Artist",
        "reviewer": "Art Lead",
    }


def _write_png_fixture(root: Path) -> Path:
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    export = root / "art/ui/export/hud-frame.png"
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_bytes(image)
    return export


class UiArtMotionSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        for name in ("ui-asset-manifest.schema.json", "ui-motion-manifest.schema.json"):
            self.assertTrue((ROOT / "evals" / "schema" / name).is_file(), name)

    def test_representative_manifests_validate(self) -> None:
        _validator("ui-asset-manifest.schema.json").validate(asset_manifest())
        _validator("ui-motion-manifest.schema.json").validate(motion_manifest())

    def test_asset_manifest_rejects_extra_fields_and_unsafe_paths(self) -> None:
        payload = asset_manifest()
        payload["extra"] = True
        self.assertTrue(
            list(_validator("ui-asset-manifest.schema.json").iter_errors(payload))
        )
        payload = asset_manifest()
        payload["assets"][0]["unity_target"] = "../outside.png"
        self.assertTrue(
            list(_validator("ui-asset-manifest.schema.json").iter_errors(payload))
        )

    def test_motion_manifest_rejects_unknown_stack_and_driver(self) -> None:
        payload = motion_manifest()
        payload["ui_stack"] = "unknown"
        self.assertTrue(
            list(_validator("ui-motion-manifest.schema.json").iter_errors(payload))
        )
        payload = motion_manifest()
        payload["motions"][0]["driver"] = "invented-tween"
        self.assertTrue(
            list(_validator("ui-motion-manifest.schema.json").iter_errors(payload))
        )


class UiArtMotionPlannerTests(unittest.TestCase):
    def test_plan_is_deterministic_and_report_only(self) -> None:
        from scripts.ui_art_motion import build_import_plan

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_path, motion_path = _write_fixture(root)
            first = build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
            second = build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
            self.assertEqual(first, second)
            self.assertEqual("report-only", first["mode"])
            self.assertEqual([], first["conflicts"])
            self.assertEqual(64, len(first["plan_digest"]))
            self.assertFalse((root / "client/Assets/UI/HUD/hud-frame.png").exists())

    def test_path_escape_and_export_hash_mismatch_fail_closed(self) -> None:
        from scripts.ui_art_motion import build_import_plan

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_path, motion_path = _write_fixture(root)
            payload = json.loads(asset_path.read_text(encoding="utf-8"))
            payload["assets"][0]["unity_target"] = "../outside.png"
            asset_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path escapes|unsafe relative path"):
                build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
            payload["assets"][0]["unity_target"] = "client/Assets/UI/HUD/hud-frame.png"
            payload["assets"][0]["export_sha256"] = "0" * 64
            asset_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "export hash mismatch"):
                build_import_plan(root, asset_path, motion_path, requested_stack="ugui")

    def test_ambiguous_stack_requires_explicit_selection(self) -> None:
        from scripts.ui_art_motion import detect_ui_stacks

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Assets/NGUI").mkdir(parents=True)
            (root / "Assets/UI").mkdir(parents=True)
            (root / "Assets/UI/panel.uxml").write_text("<ui:UXML />", encoding="utf-8")
            self.assertEqual({"ngui", "ui-toolkit"}, detect_ui_stacks(root))

    def test_external_tween_requires_declared_dependency(self) -> None:
        from scripts.ui_art_motion import build_import_plan

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_path, motion_path = _write_fixture(root)
            payload = motion_manifest()
            payload["motions"][0]["driver"] = "dotween"
            motion_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DOTween dependency evidence"):
                build_import_plan(root, asset_path, motion_path, requested_stack="ugui")

    def test_verify_rejects_changed_baseline_or_missing_outputs(self) -> None:
        from scripts.ui_art_motion import build_import_plan, verify_import_plan

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_path, motion_path = _write_fixture(root)
            plan = build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
            report = verify_import_plan(root, plan)
            self.assertEqual("BLOCKED", report["verdict"])
            self.assertIn("missing planned output", report["failures"][0])


class UiArtDesignBriefAndQcTests(unittest.TestCase):
    def _write_qc_fixture(
        self,
        root: Path,
        *,
        payload: bytes,
        export_name: str = "hud-frame.png",
        export_format: str = "png",
        width: int = 1,
        height: int = 1,
        alpha: bool = True,
    ) -> tuple[Path, Path]:
        export = root / "art/ui/export" / export_name
        export.parent.mkdir(parents=True, exist_ok=True)
        export.write_bytes(payload)
        assets = asset_manifest()
        item = assets["assets"][0]
        item["export_path"] = export.relative_to(root).as_posix()
        item["format"] = export_format
        item["width"] = width
        item["height"] = height
        item["alpha"] = alpha
        digest = hashlib.sha256(payload).hexdigest()
        item["export_sha256"] = digest
        item["ai_provenance"]["output_sha256"] = digest
        asset_path = root / "ui-asset-manifest.json"
        asset_path.write_text(json.dumps(assets), encoding="utf-8")
        brief_path = root / "ui-design-brief.json"
        brief_path.write_text(json.dumps(design_brief()), encoding="utf-8")
        return brief_path, asset_path

    def test_design_brief_and_static_qc_report_pass(self) -> None:
        from scripts.ui_art_qc import build_art_qc_report, load_design_brief

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            export = _write_png_fixture(root)
            assets = asset_manifest()
            assets["assets"][0]["width"] = 1
            assets["assets"][0]["height"] = 1
            assets["assets"][0]["alpha"] = True
            assets["assets"][0]["export_sha256"] = hashlib.sha256(export.read_bytes()).hexdigest()
            assets["assets"][0]["ai_provenance"]["output_sha256"] = assets["assets"][0]["export_sha256"]
            assets["assets"][0]["unity_target"] = "client/Assets/UI/HUD/hud-frame.png"
            asset_path = root / "ui-asset-manifest.json"
            asset_path.write_text(json.dumps(assets), encoding="utf-8")
            brief_path = root / "ui-design-brief.json"
            brief_path.write_text(json.dumps(design_brief()), encoding="utf-8")
            brief = load_design_brief(brief_path, ROOT / "evals/schema/ui-design-brief.schema.json")
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("PASS", report["verdict"])
            self.assertEqual("hud-bronze-v1", brief["id"])
            self.assertEqual([], report["failures"])
            _validator("ui-art-qc-report.schema.json").validate(report)

    def test_design_brief_rejects_extra_fields_and_qc_rejects_dimension_drift(self) -> None:
        from scripts.ui_art_qc import build_art_qc_report, load_design_brief

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            export = _write_png_fixture(root)
            brief = design_brief()
            brief["unexpected"] = True
            brief_path = root / "ui-design-brief.json"
            brief_path.write_text(json.dumps(brief), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "design brief validation failed"):
                load_design_brief(brief_path, ROOT / "evals/schema/ui-design-brief.schema.json")
            assets = asset_manifest()
            assets["assets"][0]["width"] = 2
            assets["assets"][0]["height"] = 1
            assets["assets"][0]["export_sha256"] = hashlib.sha256(export.read_bytes()).hexdigest()
            assets["assets"][0]["ai_provenance"]["output_sha256"] = assets["assets"][0]["export_sha256"]
            asset_path = root / "ui-asset-manifest.json"
            asset_path.write_text(json.dumps(assets), encoding="utf-8")
            brief_path.write_text(json.dumps(design_brief()), encoding="utf-8")
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("dimension mismatch" in item for item in report["failures"]))

    def test_static_qc_rejects_truncated_png_and_hash_drift(self) -> None:
        from scripts.ui_art_qc import build_art_qc_report

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                ),
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("PNG" in item for item in report["failures"]))

            payload = json.loads(asset_path.read_text(encoding="utf-8"))
            payload["assets"][0]["export_sha256"] = "0" * 64
            payload["assets"][0]["ai_provenance"]["output_sha256"] = "0" * 64
            asset_path.write_text(json.dumps(payload), encoding="utf-8")
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("hash mismatch" in item for item in report["failures"]))

    def test_static_qc_validates_jpeg_svg_and_exact_alpha(self) -> None:
        from scripts.ui_art_qc import build_art_qc_report

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=b"not a jpeg",
                export_name="hud-frame.jpg",
                export_format="jpg",
                alpha=False,
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("JPEG" in item for item in report["failures"]))

            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=b"not svg",
                export_name="hud-frame.svg",
                export_format="svg",
                width=512,
                height=256,
                alpha=False,
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("SVG" in item for item in report["failures"]))

            rgba = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=rgba,
                alpha=False,
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("unexpected alpha" in item for item in report["failures"]))

            valid_jpeg = (
                b"\xff\xd8\xff\xe0"
                + (16).to_bytes(2, "big")
                + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                + b"\xff\xc0"
                + (19).to_bytes(2, "big")
                + bytes([8, 0, 1, 0, 1, 3, 1, 0x11, 0, 2, 1, 0x11, 0, 3, 1, 0x11, 0])
                + b"\xff\xda"
                + (8).to_bytes(2, "big")
                + bytes([3, 1, 0, 2, 0, 3])
                + b"\x00\xff\xd9"
            )
            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=valid_jpeg,
                export_name="hud-frame.jpg",
                export_format="jpg",
                alpha=False,
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("PASS", report["verdict"])

            valid_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="256" />'
            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=valid_svg,
                export_name="hud-frame.svg",
                export_format="svg",
                width=512,
                height=256,
                alpha=False,
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("PASS", report["verdict"])

    def test_static_qc_rejects_symlinked_export_when_platform_allows_it(self) -> None:
        from scripts.ui_art_qc import build_art_qc_report

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root.parent / "qc-outside.png"
            outside.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            )
            export = root / "art/ui/export/hud-frame.png"
            export.parent.mkdir(parents=True)
            try:
                export.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            brief_path, asset_path = self._write_qc_fixture(
                root,
                payload=outside.read_bytes(),
            )
            report = build_art_qc_report(root, brief_path, asset_path)
            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(any("symlink or reparse" in item for item in report["failures"]))
