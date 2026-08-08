from __future__ import annotations

import json
import unittest
from pathlib import Path

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
            "schema_version": 1,
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
