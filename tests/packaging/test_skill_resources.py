from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

from scripts.common import load_yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REFERENCE = re.compile(r"scripts/([A-Za-z0-9_.-]+\.py)")
SUPPORTED_SUFFIXES = {".json", ".py", ".toml"}


def normalize_resource(entry: object) -> tuple[str, str]:
    if isinstance(entry, str):
        return f"scripts/{entry}", f"scripts/{entry}"
    if isinstance(entry, dict):
        if set(entry) != {"source", "destination"}:
            raise AssertionError(f"invalid resource mapping: {entry}")
        source = entry["source"]
        destination = entry["destination"]
        if not isinstance(source, str) or not isinstance(destination, str):
            raise AssertionError(f"resource paths must be strings: {entry}")
        return source, destination
    raise AssertionError(f"invalid resource entry: {entry}")


def assert_safe_relative_path(test: unittest.TestCase, value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    raw_parts = normalized.split("/")
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(value)
    test.assertTrue(value, "resource path must not be empty")
    test.assertFalse(path.is_absolute(), value)
    test.assertFalse(windows_path.is_absolute() or windows_path.drive, value)
    test.assertFalse(any(part in {"", ".", ".."} for part in raw_parts), value)
    return path


class SkillResourcePackagingTests(unittest.TestCase):
    def test_generated_skill_resources_are_in_sync(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", "scripts/sync_skill_resources.py", ".", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_isolated_release_preflight_skill_loads_its_bundled_schema(self) -> None:
        source = ROOT / "skills" / "release-candidate-preflight"
        with tempfile.TemporaryDirectory() as temp:
            isolated = Path(temp) / "release-candidate-preflight"
            shutil.copytree(source, isolated)
            script = isolated / "scripts" / "release_preflight.py"
            schema = isolated / "schemas" / "release-preflight.schema.json"
            self.assertTrue(schema.is_file(), schema)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "import importlib.util, pathlib, sys; "
                        "path=pathlib.Path(sys.argv[1]); "
                        "spec=importlib.util.spec_from_file_location('isolated_release_preflight', path); "
                        "module=importlib.util.module_from_spec(spec); "
                        "spec.loader.exec_module(module); "
                        "print(module.load_release_preflight_schema()['$id'])"
                    ),
                    str(script),
                ],
                cwd=isolated,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("release-preflight.schema.json", result.stdout)

    def test_isolated_ui_art_motion_skill_loads_bundled_schemas(self) -> None:
        source = ROOT / "skills" / "unity-ui-art-and-motion-production"
        with tempfile.TemporaryDirectory() as temp:
            isolated = Path(temp) / source.name
            shutil.copytree(source, isolated)
            script = isolated / "scripts" / "ui_art_motion.py"
            self.assertTrue((isolated / "schemas" / "ui-asset-manifest.schema.json").is_file())
            self.assertTrue((isolated / "schemas" / "ui-motion-manifest.schema.json").is_file())
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "import importlib.util, pathlib, sys; "
                        "path=pathlib.Path(sys.argv[1]); "
                        "spec=importlib.util.spec_from_file_location('isolated_ui_art_motion', path); "
                        "module=importlib.util.module_from_spec(spec); "
                        "spec.loader.exec_module(module); "
                        "paths=module.schema_paths(); "
                        "assert all(item.is_file() for item in paths.values()), paths; "
                        "print(paths)"
                    ),
                    str(script),
                ],
                cwd=isolated,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ui-asset-manifest.schema.json", result.stdout)
        self.assertIn("ui-motion-manifest.schema.json", result.stdout)

    def test_isolated_ui_art_qc_skill_loads_bundled_helper(self) -> None:
        source = ROOT / "skills" / "unity-ui-art-and-motion-production"
        with tempfile.TemporaryDirectory() as temp:
            isolated = Path(temp) / source.name
            shutil.copytree(source, isolated)
            script = isolated / "scripts" / "ui_art_qc.py"
            self.assertTrue((isolated / "schemas" / "ui-design-brief.schema.json").is_file())
            self.assertTrue((isolated / "schemas" / "ui-art-qc-report.schema.json").is_file())
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "import importlib.util, pathlib, sys; "
                        "path=pathlib.Path(sys.argv[1]); "
                        "spec=importlib.util.spec_from_file_location('isolated_ui_art_qc', path); "
                        "module=importlib.util.module_from_spec(spec); "
                        "spec.loader.exec_module(module); "
                        "candidates=module._schema_candidates(pathlib.Path('missing/ui-design-brief.schema.json')); "
                        "schema=next(item for item in candidates if item.is_file()); "
                        "print(schema)"
                    ),
                    str(script),
                ],
                cwd=isolated,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ui-design-brief.schema.json", result.stdout)

    def test_isolated_screenshot_showcase_skill_loads_bundled_schemas(self) -> None:
        source = ROOT / "skills" / "game-screenshot-showcase-and-store-packaging"
        with tempfile.TemporaryDirectory() as temp:
            isolated = Path(temp) / source.name
            shutil.copytree(source, isolated)
            script = isolated / "scripts" / "screenshot_showcase.py"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "import importlib.util, pathlib, sys; "
                        "path=pathlib.Path(sys.argv[1]); "
                        "spec=importlib.util.spec_from_file_location('isolated_screenshot_showcase', path); "
                        "module=importlib.util.module_from_spec(spec); "
                        "spec.loader.exec_module(module); "
                        "names=['capture-plan','capture-record','showcase-deck','store-export-manifest']; "
                        "loaded={name: module._load_schema(name)[0]['$id'] for name in names}; "
                        "print(loaded)"
                    ),
                    str(script),
                ],
                cwd=isolated,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("capture-plan.schema.json", result.stdout)
        self.assertIn("store-export-manifest.schema.json", result.stdout)

    def test_release_preflight_skill_documents_helper_dependencies(self) -> None:
        skill = (
            ROOT / "skills" / "release-candidate-preflight" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Python 3.11+", skill)
        self.assertIn("jsonschema", skill)

    def test_standalone_router_does_not_require_repository_only_indexes(self) -> None:
        router = (ROOT / "skills" / "using-game-studio-skills" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        workflow = re.search(r"^## Workflow\s*$\n(.*?)(?=^## |\Z)", router, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(workflow)
        self.assertNotIn("registry/", workflow.group(1))
        self.assertNotIn("docs/", workflow.group(1))

    def test_standalone_skill_bodies_make_repository_indexes_optional(self) -> None:
        for skill_path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            body = skill_path.read_text(encoding="utf-8").split("---", 2)[-1]
            if "registry/" not in body:
                continue
            self.assertTrue(
                "when present" in body or "full repository clone" in body,
                skill_path,
            )

    def test_readme_marks_root_script_workflows_as_full_clone_maintenance(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = re.search(
            r"^## Use in a game project\s*$\n(.*?)(?=^## |\Z)",
            readme,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section)
        self.assertIn("full repository clone", section.group(1))

    def test_screenshot_showcase_capability_pack_and_resources_are_registered(self) -> None:
        capabilities = load_yaml(ROOT / "registry" / "capabilities.yaml")["capabilities"]
        capability = next(
            item
            for item in capabilities
            if item["id"] == "game-screenshot-showcase-and-store-packaging"
        )
        self.assertEqual(
            {
                "id": "game-screenshot-showcase-and-store-packaging",
                "path": "skills/game-screenshot-showcase-and-store-packaging/SKILL.md",
                "type": "workflow",
                "packs": ["content-production"],
                "risk_level": "medium",
                "maturity": "experimental",
                "depends_on": [
                    "playtest-evidence",
                    "build-and-runtime-verification",
                    "store-submission-checklist",
                ],
            },
            capability,
        )

        packs = {item["id"]: item for item in load_yaml(ROOT / "registry" / "packs.yaml")["packs"]}
        self.assertIn(
            "game-screenshot-showcase-and-store-packaging",
            packs["content-production"]["skills"],
        )

        registry = load_yaml(ROOT / "registry" / "skill-resources.yaml")
        self.assertEqual(
            [
                "screenshot_showcase.py",
                {
                    "source": "evals/schema/capture-plan.schema.json",
                    "destination": "schemas/capture-plan.schema.json",
                },
                {
                    "source": "evals/schema/capture-record.schema.json",
                    "destination": "schemas/capture-record.schema.json",
                },
                {
                    "source": "evals/schema/showcase-deck.schema.json",
                    "destination": "schemas/showcase-deck.schema.json",
                },
                {
                    "source": "evals/schema/store-export-manifest.schema.json",
                    "destination": "schemas/store-export-manifest.schema.json",
                },
            ],
            registry["bundled"]["game-screenshot-showcase-and-store-packaging"],
        )
        self.assertIn(
            {
                "source": "agents/game-showcase-capture-producer.toml",
                "destination": "templates/specialists/game-showcase-capture-producer.toml",
            },
            registry["bundled"]["studio-project-scaffold"],
        )

    def test_referenced_helpers_are_bundled_or_declared_repository_only(self) -> None:
        from scripts.sync_skill_resources import render_generated_resource

        registry_path = ROOT / "registry" / "skill-resources.yaml"
        self.assertTrue(registry_path.is_file(), registry_path)
        registry = load_yaml(registry_path)
        self.assertEqual({"schema_version", "bundled", "repository_only"}, set(registry))
        self.assertEqual(2, registry["schema_version"])

        bundled = registry["bundled"]
        repository_only = registry["repository_only"]
        self.assertIsInstance(bundled, dict)
        self.assertIsInstance(repository_only, dict)

        for skill_path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            skill_id = skill_path.parent.name
            body = skill_path.read_text(encoding="utf-8")
            referenced = set(SCRIPT_REFERENCE.findall(body))
            bundled_resources = [normalize_resource(entry) for entry in bundled.get(skill_id, [])]
            repository_resources = [
                normalize_resource(entry) for entry in repository_only.get(skill_id, [])
            ]
            declared_bundled = {
                source.parts[1]
                for source_value, _destination in bundled_resources
                if (source := PurePosixPath(source_value)).parts[:1] == ("scripts",)
                and len(source.parts) == 2
                and source.suffix == ".py"
            }
            declared_repository_only = {
                source.parts[1]
                for source_value, _destination in repository_resources
                if (source := PurePosixPath(source_value)).parts[:1] == ("scripts",)
                and len(source.parts) == 2
                and source.suffix == ".py"
            }

            self.assertEqual(
                referenced,
                declared_bundled | declared_repository_only,
                f"resource registry mismatch for {skill_id}",
            )
            if declared_repository_only:
                self.assertIn("full repository clone", body)

            for source_value, destination_value in bundled_resources:
                source = ROOT.joinpath(*PurePosixPath(source_value).parts)
                generated = skill_path.parent.joinpath(*PurePosixPath(destination_value).parts)
                self.assertTrue(source.is_file(), source)
                self.assertTrue(generated.is_file(), generated)
                self.assertEqual(
                    render_generated_resource(
                        generated,
                        source.read_text(encoding="utf-8"),
                    ),
                    generated.read_text(encoding="utf-8"),
                    generated,
                )

    def test_resource_registry_only_names_known_skills_and_scripts(self) -> None:
        registry = load_yaml(ROOT / "registry" / "skill-resources.yaml")
        known_skills = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
        declared_destinations: set[tuple[str, str]] = set()

        for section in ("bundled", "repository_only"):
            mapping = registry[section]
            self.assertTrue(set(mapping).issubset(known_skills))
            for skill_id, entries in mapping.items():
                self.assertIsInstance(entries, list, skill_id)
                normalized = [normalize_resource(entry) for entry in entries]
                self.assertEqual(len(normalized), len(set(normalized)), skill_id)
                for entry, (source_value, destination_value) in zip(entries, normalized):
                    if isinstance(entry, str):
                        self.assertRegex(entry, r"^[a-z0-9_]+\.py$")
                    source_path = assert_safe_relative_path(self, source_value)
                    destination_path = assert_safe_relative_path(self, destination_value)
                    self.assertIn(source_path.suffix.casefold(), SUPPORTED_SUFFIXES, source_value)
                    self.assertEqual(source_path.suffix.casefold(), destination_path.suffix.casefold())

                    source = ROOT.joinpath(*source_path.parts)
                    self.assertTrue(source.is_file(), source)

                    destination_key = (skill_id, destination_path.as_posix())
                    self.assertNotIn(destination_key, declared_destinations, destination_key)
                    declared_destinations.add(destination_key)


if __name__ == "__main__":
    unittest.main()
