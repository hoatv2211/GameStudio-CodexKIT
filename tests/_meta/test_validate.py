from __future__ import annotations

import json
import os
import subprocess
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import yaml

from tests._meta.support import (
    REQUIRED_BODY,
    temporary_directory,
    write_plugin_package,
    write_registries,
    write_skill,
)


class ValidateRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = temporary_directory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def issues(self) -> list[object]:
        from scripts.validate import validate_repository

        return validate_repository(self.root)

    def codes(self) -> set[str]:
        return {issue.code for issue in self.issues()}

    def make_valid(self, name: str = "example-skill") -> None:
        write_skill(self.root, name)
        write_registries(self.root, [name])
        resource_path = self.root / "registry" / "skill-resources.yaml"
        resources = yaml.safe_load(resource_path.read_text(encoding="utf-8"))
        resources["schema_version"] = 2
        resource_path.write_text(yaml.safe_dump(resources, sort_keys=False), encoding="utf-8")
        write_plugin_package(self.root)

    def test_accepts_a_valid_repository(self) -> None:
        self.make_valid()
        self.assertEqual([], self.issues())

    def test_rejects_missing_plugin_manifest(self) -> None:
        self.make_valid()
        (self.root / ".codex-plugin" / "plugin.json").unlink()
        self.assertIn("plugin.manifest.missing", self.codes())

    def test_rejects_missing_plugin_marketplace(self) -> None:
        self.make_valid()
        (self.root / ".claude-plugin" / "marketplace.json").unlink()
        self.assertIn("plugin.marketplace.missing", self.codes())

    def test_rejects_missing_skill_resource_registry(self) -> None:
        self.make_valid()
        (self.root / "registry" / "skill-resources.yaml").unlink()
        self.assertIn("skill.resources.registry_missing", self.codes())

    def test_rejects_generated_skill_resource_drift(self) -> None:
        self.make_valid()
        source = self.root / "scripts" / "fixture_helper.py"
        source.parent.mkdir(parents=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        resource_registry = {
            "schema_version": 2,
            "bundled": {"example-skill": ["fixture_helper.py"]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(resource_registry, sort_keys=False), encoding="utf-8"
        )
        generated = self.root / "skills" / "example-skill" / "scripts" / "fixture_helper.py"
        generated.parent.mkdir()
        generated.write_text("# stale generated helper\n", encoding="utf-8")

        self.assertIn("skill.resources.drift", self.codes())

    def test_rejects_invalid_repository_only_resource_mapping(self) -> None:
        self.make_valid()
        resource_path = self.root / "registry" / "skill-resources.yaml"
        resource_registry = yaml.safe_load(resource_path.read_text(encoding="utf-8"))
        resource_registry["repository_only"] = ["validate.py"]
        resource_path.write_text(
            yaml.safe_dump(resource_registry, sort_keys=False), encoding="utf-8"
        )

        self.assertIn("skill.resources.registry_invalid", self.codes())

    def test_sync_supports_nested_mapping_resources(self) -> None:
        from scripts.sync_skill_resources import GENERATED_HEADER, sync_skill_resources

        self.make_valid()
        source = self.root / "agents" / "investigator.toml"
        source.write_text("name = 'investigator'\n", encoding="utf-8")
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "agents/investigator.toml",
                "destination": "templates/agents/investigator.toml",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )
        destination = self.root / "skills" / "example-skill" / "templates" / "agents" / "investigator.toml"

        self.assertEqual([destination], sync_skill_resources(self.root))
        self.assertEqual(
            GENERATED_HEADER + source.read_text(encoding="utf-8"),
            destination.read_text(encoding="utf-8"),
        )

        unmanaged = destination.parent / "local.toml"
        unmanaged.write_text("name = 'local'\n", encoding="utf-8")
        self.assertEqual([], sync_skill_resources(self.root, check=True))

        unexpected = destination.parent / "unexpected.toml"
        unexpected.write_text(GENERATED_HEADER + "name = 'unexpected'\n", encoding="utf-8")
        self.assertEqual([unexpected], sync_skill_resources(self.root, check=True))
        self.assertTrue(unmanaged.is_file())

    def test_sync_supports_format_aware_text_resources(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        self.make_valid()
        hash_marker = "# Generated by scripts/sync_skill_resources.py. Do not edit manually."
        html_marker = "<!-- Generated by scripts/sync_skill_resources.py. Do not edit manually. -->"
        fixtures = {
            "fixtures/sample.py": ("scripts/sample.py", "print('python')\n", hash_marker),
            "fixtures/sample.toml": ("templates/sample.toml", "name = 'sample'\n", hash_marker),
            "fixtures/sample.yaml": ("templates/sample.yaml", "name: sample\n", hash_marker),
            "fixtures/sample.yml": ("templates/sample.yml", "name: sample\n", hash_marker),
            "fixtures/sample.ps1": ("scripts/sample.ps1", "Write-Output 'sample'\n", hash_marker),
            "fixtures/sample.sh": ("scripts/sample.sh", "printf 'sample\\n'\n", hash_marker),
            "fixtures/sample.md": ("templates/sample.md", "# Sample\n", html_marker),
            "fixtures/sample.txt": ("templates/sample.txt", "Sample text\n", html_marker),
        }
        mappings = []
        for source_name, (destination_name, content, _marker) in fixtures.items():
            source = self.root / source_name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content, encoding="utf-8", newline="")
            mappings.append({"source": source_name, "destination": destination_name})
        registry_path = self.root / "registry" / "skill-resources.yaml"
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": mappings},
            "repository_only": {},
        }
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

        generated = sync_skill_resources(self.root)
        self.assertEqual(len(fixtures), len(generated))
        first_bytes = {}
        for source_name, (destination_name, content, marker) in fixtures.items():
            with self.subTest(source=source_name):
                destination = self.root / "skills" / "example-skill" / destination_name
                text = destination.read_text(encoding="utf-8")
                self.assertEqual(marker, text.splitlines()[0])
                self.assertEqual(content, text.split("\n\n", 1)[1])
                self.assertEqual(1, text.count(marker))
                first_bytes[destination] = destination.read_bytes()

        self.assertEqual([], sync_skill_resources(self.root))
        self.assertEqual(first_bytes, {path: path.read_bytes() for path in first_bytes})
        self.assertEqual([], self.issues())

        stale = self.root / "skills" / "example-skill" / "templates" / "sample.md"
        stale.write_text(html_marker + "\n\nstale\n", encoding="utf-8", newline="")
        self.assertEqual([stale], sync_skill_resources(self.root, check=True))
        self.assertIn("skill.resources.drift", self.codes())
        sync_skill_resources(self.root)
        stale_owned = self.root / "skills" / "example-skill" / "templates" / "sample.txt"
        stale_owned.write_text(html_marker + "\nstale without separator\n", encoding="utf-8")

        unmanaged_hash = self.root / "skills" / "example-skill" / "scripts" / "local.py"
        unmanaged_hash.write_text("print('local')\n" + hash_marker + "\n", encoding="utf-8")
        unmanaged_html = self.root / "skills" / "example-skill" / "templates" / "local.md"
        unmanaged_html.write_text("Local\n" + html_marker + "\n", encoding="utf-8")
        registry["bundled"] = {}
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

        removed = sync_skill_resources(self.root)
        self.assertEqual(sorted(first_bytes), removed)
        self.assertTrue(unmanaged_hash.is_file())
        self.assertTrue(unmanaged_html.is_file())

    def test_sync_rejects_binary_content_in_supported_text_format(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        self.make_valid()
        source = self.root / "fixtures" / "binary.txt"
        source.parent.mkdir()
        source.write_bytes(b"text\x00binary\xff")
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "fixtures/binary.txt",
                "destination": "templates/binary.txt",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "binary or non-UTF-8"):
            sync_skill_resources(self.root, check=True)

    def test_sync_rejects_invalid_generalized_resource_records(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        cases = {
            "absolute source": {"source": "C:/outside/investigator.toml", "destination": "templates/agents/investigator.toml"},
            "destination traversal": {"source": "agents/investigator.toml", "destination": "templates/../investigator.toml"},
            "unsupported suffix": {"source": "agents/investigator.toml", "destination": "templates/agents/investigator.png"},
            "missing source": {"source": "agents/missing.toml", "destination": "templates/agents/investigator.toml"},
            "invalid mapping shape": {"source": "agents/investigator.toml"},
        }

        for label, record in cases.items():
            with self.subTest(label=label):
                self.make_valid()
                registry = {
                    "schema_version": 2,
                    "bundled": {"example-skill": [record]},
                    "repository_only": {},
                }
                (self.root / "registry" / "skill-resources.yaml").write_text(
                    yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
                )
                with self.assertRaises(ValueError):
                    sync_skill_resources(self.root, check=True)

    def test_sync_rejects_nonportable_source_and_destination_components(self) -> None:
        from scripts.sync_skill_resources import load_skill_resources

        invalid_components = (
            "control\x01name",
            "bad<name",
            "bad>name",
            "bad:name",
            "bad\"name",
            "bad|name",
            "bad?name",
            "bad*name",
            "trailing.",
            "trailing ",
            "CON",
            "con.txt",
            "NUL",
            "COM1",
            "LPT9",
            "COM¹",
            "LPT³",
            "CONIN$",
            "CONOUT$",
            "victim.py:generated.py",
        )
        for field in ("source", "destination"):
            for component in invalid_components:
                with self.subTest(field=field, component=component):
                    self.make_valid()
                    record = {
                        "source": "agents/investigator.toml",
                        "destination": "templates/agents/investigator.toml",
                    }
                    record[field] = f"{component}/investigator.toml"
                    registry = {
                        "schema_version": 2,
                        "bundled": {"example-skill": [record]},
                        "repository_only": {},
                    }
                    (self.root / "registry" / "skill-resources.yaml").write_text(
                        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(ValueError, "unsafe .* component"):
                        load_skill_resources(self.root)

    def test_sync_rejects_invalid_skill_ids_before_skill_path_lookup(self) -> None:
        from scripts.sync_skill_resources import load_skill_resources

        invalid_skill_ids = (
            "alias/../example-skill",
            "alias\\..\\example-skill",
            "Example-Skill",
        )
        for skill_id in invalid_skill_ids:
            with self.subTest(skill_id=skill_id):
                self.make_valid()
                registry = {
                    "schema_version": 2,
                    "bundled": {skill_id: ["fixture_helper.py"]},
                    "repository_only": {},
                }
                registry_path = self.root / "registry" / "skill-resources.yaml"
                registry_path.write_text(
                    yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
                )
                with mock.patch.object(
                    Path,
                    "is_file",
                    side_effect=AssertionError("skill path lookup occurred"),
                ):
                    with self.assertRaisesRegex(ValueError, "invalid skill id"):
                        load_skill_resources(self.root)

    def test_sync_rejects_duplicate_destinations_and_reparse_components(self) -> None:
        import scripts.sync_skill_resources as resources

        self.make_valid()
        (self.root / "agents" / "investigator.toml").write_text(
            "name = 'investigator'\n", encoding="utf-8"
        )
        helper = self.root / "scripts" / "fixture_helper.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("VALUE = 1\n", encoding="utf-8")
        duplicate_source = self.root / "scripts" / "duplicate_helper.py"
        duplicate_source.write_text("VALUE = 2\n", encoding="utf-8")
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [
                "fixture_helper.py",
                {
                    "source": "scripts/duplicate_helper.py",
                    "destination": "scripts/fixture_helper.py",
                },
            ]},
            "repository_only": {},
        }
        registry_path = self.root / "registry" / "skill-resources.yaml"
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate.*destination"):
            resources.sync_skill_resources(self.root, check=True)

        registry["bundled"]["example-skill"] = [{
            "source": "agents/investigator.toml",
            "destination": "templates/agents/investigator.toml",
        }]
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
        reparse_component = self.root / "skills" / "example-skill" / "templates"
        reparse_component.mkdir()
        with mock.patch.object(
            resources,
            "_is_reparse_point",
            side_effect=lambda path: path == reparse_component,
        ):
            with self.assertRaisesRegex(ValueError, "symlink or reparse point"):
                resources.sync_skill_resources(self.root, check=True)

    def test_sync_rejects_missing_final_destination_reported_as_reparse(self) -> None:
        import scripts.sync_skill_resources as resources

        self.make_valid()
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "agents/investigator.toml",
                "destination": "templates/agents/investigator.toml",
            }]},
            "repository_only": {},
        }
        registry_path = self.root / "registry" / "skill-resources.yaml"
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
        destination = self.root / "skills" / "example-skill" / "templates" / "agents" / "investigator.toml"
        self.assertFalse(destination.exists())

        with mock.patch.object(
            resources,
            "_is_reparse_point",
            side_effect=lambda path: path == destination,
        ):
            with self.assertRaisesRegex(ValueError, "symlink or reparse point"):
                resources.sync_skill_resources(self.root, check=True)

        skills_root = self.root / "skills"
        with mock.patch.object(
            resources,
            "_is_reparse_point",
            side_effect=lambda path: path == skills_root,
        ):
            with self.assertRaisesRegex(ValueError, "symlink or reparse point"):
                resources.sync_skill_resources(self.root, check=True)

    def test_rejects_packaged_toml_template_parse_and_name_mismatch(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        self.make_valid()
        source = self.root / "agents" / "investigator.toml"
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "agents/investigator.toml",
                "destination": "templates/agents/investigator.toml",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )

        source.write_text("name = [\n", encoding="utf-8")
        sync_skill_resources(self.root)
        self.assertIn("skill.resources.toml_parse", self.codes())

        source.write_text("name = 'wrong-name'\n", encoding="utf-8")
        sync_skill_resources(self.root)
        self.assertIn("skill.resources.toml_name", self.codes())
        template_path = self.root / "skills" / "example-skill" / "templates" / "agents" / "investigator.toml"
        self.assertEqual("wrong-name", tomllib.loads(template_path.read_text(encoding="utf-8"))["name"])

    def test_rejects_packaged_agent_toml_with_empty_required_strings(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        self.make_valid()
        source = self.root / "agents" / "investigator.toml"
        source.write_text(
            "\n".join(
                [
                    "name = 'investigator'",
                    "description = '   '",
                    "model_reasoning_effort = 'high'",
                    "sandbox_mode = 'read-only'",
                    "developer_instructions = ''",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "agents/investigator.toml",
                "destination": "templates/agents/investigator.toml",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )
        sync_skill_resources(self.root)

        self.assertIn("skill.resources.toml_required", self.codes())

    def test_ignores_malformed_non_agent_toml_resource(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        self.make_valid()
        source = self.root / "configs" / "settings.toml"
        source.parent.mkdir()
        source.write_text("[tool\n", encoding="utf-8")
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "configs/settings.toml",
                "destination": "templates/config/settings.toml",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )
        sync_skill_resources(self.root)

        codes = self.codes()
        self.assertNotIn("skill.resources.toml_parse", codes)
        self.assertNotIn("skill.resources.toml_name", codes)
        self.assertNotIn("skill.resources.toml_required", codes)

    def test_accepts_valid_non_agent_toml_resource_without_name(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        self.make_valid()
        source = self.root / "configs" / "settings.toml"
        source.parent.mkdir()
        source.write_text("[tool]\nenabled = true\n", encoding="utf-8")
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "configs/settings.toml",
                "destination": "templates/config/settings.toml",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )

        sync_skill_resources(self.root)

        self.assertEqual([], self.issues())

    def test_rejects_each_non_mapping_agent_role_entry_with_index(self) -> None:
        self.make_valid()
        registry_path = self.root / "registry" / "agent-roles.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["agent_roles"].extend(["invalid", None, ["also-invalid"]])
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

        issues = [
            issue
            for issue in self.issues()
            if issue.code == "registry.agent_role.schema"
        ]
        self.assertEqual(3, len(issues))
        messages = {issue.message for issue in issues}
        self.assertTrue(any("agent_roles[1]" in message for message in messages))
        self.assertTrue(any("agent_roles[2]" in message for message in messages))
        self.assertTrue(any("agent_roles[3]" in message for message in messages))

    def test_rejects_invalid_bytes_in_canonical_agent_role_toml(self) -> None:
        self.make_valid()
        (self.root / "agents" / "investigator.toml").write_bytes(b"name = '\xff'\n")

        self.assertIn("registry.agent_role.toml", self.codes())

    def test_rejects_invalid_bytes_in_packaged_agent_toml(self) -> None:
        from scripts.sync_skill_resources import load_skill_resources, sync_skill_resources

        self.make_valid()
        source = self.root / "agents" / "packaged.toml"
        source.write_text("name = 'packaged'\n", encoding="utf-8")
        registry = {
            "schema_version": 2,
            "bundled": {"example-skill": [{
                "source": "agents/packaged.toml",
                "destination": "templates/agents/packaged.toml",
            }]},
            "repository_only": {},
        }
        (self.root / "registry" / "skill-resources.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )
        sync_skill_resources(self.root)
        packaged = (
            self.root
            / "skills"
            / "example-skill"
            / "templates"
            / "agents"
            / "packaged.toml"
        )
        packaged.write_bytes(b"name = '\xff'\n")

        with (
            mock.patch("scripts.validate.load_skill_resources", side_effect=load_skill_resources),
            mock.patch("scripts.validate.sync_skill_resources", return_value=[]),
        ):
            self.assertIn("skill.resources.toml_parse", self.codes())

    def test_rejects_agent_role_path_when_agents_root_is_reparse(self) -> None:
        self.make_valid()
        agents_root = self.root / "agents"

        with mock.patch(
            "scripts.validate._is_reparse_point",
            side_effect=lambda path: path == agents_root,
        ):
            issues = [
                issue
                for issue in self.issues()
                if issue.code == "registry.agent_role.path"
            ]

        self.assertTrue(issues)
        self.assertTrue(any("symlink or reparse point" in issue.message for issue in issues))

    def test_rejects_agent_role_path_through_directory_symlink(self) -> None:
        self.make_valid()
        outside = self.root / "outside-agents"
        outside.mkdir()
        (outside / "investigator.toml").write_text(
            (self.root / "agents" / "investigator.toml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        link = self.root / "agents" / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"directory symlink creation unavailable: {error}")
        registry_path = self.root / "registry" / "agent-roles.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["agent_roles"][0]["path"] = "agents/linked/investigator.toml"
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

        issues = [issue for issue in self.issues() if issue.code == "registry.agent_role.path"]
        self.assertTrue(issues)
        self.assertTrue(any("symlink or reparse point" in issue.message for issue in issues))

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_rejects_agent_role_path_through_windows_junction(self) -> None:
        self.make_valid()
        outside = self.root / "outside-junction-agents"
        outside.mkdir()
        (outside / "investigator.toml").write_text(
            (self.root / "agents" / "investigator.toml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        junction = self.root / "agents" / "junction"
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            self.skipTest(f"junction creation unavailable: {completed.stderr or completed.stdout}")
        registry_path = self.root / "registry" / "agent-roles.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["agent_roles"][0]["path"] = "agents/junction/investigator.toml"
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

        issues = [issue for issue in self.issues() if issue.code == "registry.agent_role.path"]
        self.assertTrue(issues)
        self.assertTrue(any("symlink or reparse point" in issue.message for issue in issues))

    def test_rejects_agent_role_with_missing_template(self) -> None:
        self.make_valid()
        registry_path = self.root / "registry" / "agent-roles.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["agent_roles"][0]["path"] = "agents/missing.toml"
        registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

        self.assertIn("registry.agent_role.path", self.codes())

    def test_rejects_plugin_skill_catalog_drift(self) -> None:
        self.make_valid()
        manifest_path = self.root / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skills"] = "./other-skills/"
        (self.root / "other-skills").mkdir()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.assertIn("plugin.skills.catalog_mismatch", self.codes())

    def test_rejects_unknown_frontmatter_fields(self) -> None:
        write_skill(self.root, "example-skill", extra_top_level="unexpected: true")
        write_registries(self.root, ["example-skill"])
        self.assertIn("skill.frontmatter.unknown", self.codes())

    def test_rejects_name_folder_mismatch(self) -> None:
        path = write_skill(self.root, "example-skill")
        path.write_text(path.read_text(encoding="utf-8").replace("name: example-skill", "name: other-skill"), encoding="utf-8")
        write_registries(self.root, ["example-skill"])
        self.assertIn("skill.name.folder_mismatch", self.codes())

    def test_root_skill_requires_negative_scope(self) -> None:
        write_skill(self.root, "root-skill", skill_type="root", body=REQUIRED_BODY)
        write_registries(self.root, ["root-skill"])
        self.assertIn("skill.root.negative_scope", self.codes())

    def test_medium_risk_requires_reviewer(self) -> None:
        write_skill(self.root, "risky-skill", risk_level="medium", reviewer=None)
        write_registries(self.root, ["risky-skill"])
        self.assertIn("skill.risk.reviewer", self.codes())

    def test_copied_text_requires_permissive_complete_provenance(self) -> None:
        write_skill(
            self.root,
            "copied-skill",
            copied_text="workflow structure",
            derived_from={
                "repo": "example/source",
                "path": "SKILL.md",
                "commit": "abc123",
                "license": "CC BY-NC-SA 4.0",
            },
        )
        write_registries(self.root, ["copied-skill"])
        self.assertIn("skill.provenance.non_permissive", self.codes())

    def test_rejects_unknown_derived_from_fields_and_fake_permissive_license(self) -> None:
        path = write_skill(
            self.root,
            "copied-skill",
            copied_text="workflow structure",
            derived_from={
                "repo": "example/source",
                "path": "SKILL.md",
                "commit": "abc123",
                "license": "NOT-MIT-NONCOMMERCIAL",
                "unexpected": "field",
            },
        )
        write_registries(self.root, ["copied-skill"])
        codes = self.codes()
        self.assertIn("skill.provenance.derived_unknown", codes)
        self.assertIn("skill.provenance.non_permissive", codes)

    def test_rejects_registry_frontmatter_drift(self) -> None:
        self.make_valid()
        capabilities_path = self.root / "registry" / "capabilities.yaml"
        data = yaml.safe_load(capabilities_path.read_text(encoding="utf-8"))
        data["capabilities"][0]["type"] = "diagnostic"
        data["capabilities"][0]["risk_level"] = "medium"
        data["capabilities"][0]["maturity"] = "beta"
        data["capabilities"][0]["packs"] = ["other-pack"]
        capabilities_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        self.assertIn("registry.skill.mismatch", self.codes())

    def test_each_numbered_workflow_step_requires_its_own_completion_criterion(self) -> None:
        body = REQUIRED_BODY.replace(
            "1. Inspect the fixture.\n   Completion criterion: the fixture is understood.",
            "1. Inspect the fixture.\n   Completion criterion: the fixture is understood.\n2. Produce the report.",
        )
        write_skill(self.root, "example-skill", body=body)
        write_registries(self.root, ["example-skill"])
        self.assertIn("skill.workflow.completion", self.codes())

    def test_rejects_invalid_frontmatter_value_types_and_formats(self) -> None:
        path = write_skill(self.root, "example-skill")
        data = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
        data["version"] = "version-one"
        data["author"] = 42
        data["license"] = []
        data["compatibility"]["engines"] = "unity"
        data["metadata"]["studio"]["owner"] = ""
        data["metadata"]["studio"]["artifact"] = []
        data["metadata"]["studio"]["last_reviewed"] = "not-a-date"
        body = path.read_text(encoding="utf-8").split("---", 2)[2]
        path.write_text(f"---\n{yaml.safe_dump(data, sort_keys=False).rstrip()}\n---{body}", encoding="utf-8")
        write_registries(self.root, ["example-skill"])
        self.assertIn("skill.frontmatter.value", self.codes())

    def test_rejects_registry_missing_references_and_cycles(self) -> None:
        self.make_valid("alpha")
        capabilities_path = self.root / "registry" / "capabilities.yaml"
        data = yaml.safe_load(capabilities_path.read_text(encoding="utf-8"))
        data["capabilities"].append(
            {
                "id": "beta",
                "path": "skills/beta/SKILL.md",
                "type": "workflow",
                "packs": ["missing-pack"],
                "risk_level": "read-only",
                "maturity": "draft",
                "depends_on": ["alpha"],
            }
        )
        data["capabilities"][0]["depends_on"] = ["beta"]
        capabilities_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        codes = self.codes()
        self.assertIn("registry.reference.missing", codes)
        self.assertIn("registry.dependency.cycle", codes)

    def test_rejects_broken_local_markdown_links(self) -> None:
        path = write_skill(self.root, "example-skill")
        path.write_text(path.read_text(encoding="utf-8").replace("references/example.md", "references/missing.md"), encoding="utf-8")
        write_registries(self.root, ["example-skill"])
        self.assertIn("skill.link.missing", self.codes())

    def test_rejects_personas_with_workflow_bodies(self) -> None:
        self.make_valid()
        persona_dir = self.root / "personas" / "qa-lead"
        persona_dir.mkdir(parents=True)
        (persona_dir / "PERSONA.md").write_text("# QA Lead\n\n## Workflow\n1. Mutate files.\n", encoding="utf-8")
        personas_path = self.root / "registry" / "personas.yaml"
        personas_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "personas": [
                        {
                            "id": "qa-lead",
                            "path": "personas/qa-lead/PERSONA.md",
                            "description": "Quality lens",
                            "routes": ["example-skill"],
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.assertIn("persona.workflow_body", self.codes())

    def test_rejects_completed_roadmap_at_repository_root(self) -> None:
        self.make_valid()
        (self.root / "PLAN_final.md").write_text("completed roadmap\n", encoding="utf-8")
        self.assertIn("template.roadmap.active", self.codes())

    def test_rejects_active_skill_body_reference_to_completed_roadmap(self) -> None:
        self.make_valid()
        path = self.root / "skills" / "example-skill" / "SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nLoad `PLAN_final.md` before continuing.\n",
            encoding="utf-8",
        )
        self.assertIn("skill.roadmap.active_reference", self.codes())

    def test_rejects_active_entry_document_reference_to_completed_roadmap(self) -> None:
        self.make_valid()
        (self.root / "README.md").write_text("Use PLAN_final.md as the active roadmap.\n", encoding="utf-8")
        self.assertIn("template.roadmap.active_reference", self.codes())


if __name__ == "__main__":
    unittest.main()
