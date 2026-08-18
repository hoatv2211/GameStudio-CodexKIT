from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

from scripts.common import parse_frontmatter

ROOT = Path(__file__).resolve().parents[2]
SKILL_ID = "codexkit-repository-maintenance"
AGENT_ID = "codexkit-maintainer"


class RepositoryMaintenanceBundleTests(unittest.TestCase):
    def test_internal_bundle_is_complete_and_activated(self) -> None:
        skill_path = ROOT / ".agents" / "skills" / SKILL_ID / "SKILL.md"
        agent_path = ROOT / ".codex" / "agents" / f"{AGENT_ID}.toml"
        config_path = ROOT / ".codex" / "config.toml"
        workflow_path = ROOT / "workflows" / "repository-maintenance.md"

        for path in (skill_path, agent_path, config_path, workflow_path):
            self.assertTrue(path.is_file(), path)

        frontmatter, _body = parse_frontmatter(skill_path)
        self.assertEqual(SKILL_ID, frontmatter["name"])
        self.assertTrue(str(frontmatter["description"]).startswith("Use when "))

        agent = tomllib.loads(agent_path.read_text(encoding="utf-8"))
        self.assertEqual(AGENT_ID, agent["name"])
        self.assertEqual("workspace-write", agent["sandbox_mode"])

        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        activation = config["agents"][AGENT_ID]
        self.assertEqual(f"./agents/{AGENT_ID}.toml", activation["config_file"])

    def test_internal_bundle_contains_identity_and_evidence_guards(self) -> None:
        skill = (ROOT / ".agents" / "skills" / SKILL_ID / "SKILL.md").read_text(
            encoding="utf-8"
        )
        workflow = (ROOT / "workflows" / "repository-maintenance.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            ".codex-plugin/plugin.json",
            "game-studio-codex-kit",
            "registry/capabilities.yaml",
            "scripts/validate.py",
            "BLOCKED: repository identity mismatch",
        ):
            self.assertIn(marker, skill)
        for stage in ("Intake", "Root cause", "Canonical edit", "Local gates", "Handoff"):
            self.assertIn(stage, workflow)

    def test_internal_bundle_is_absent_from_distributed_surfaces(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("./skills/", manifest["skills"])

        for relative in (
            "registry/capabilities.yaml",
            "registry/packs.yaml",
            "registry/agent-roles.yaml",
            "registry/skill-resources.yaml",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(SKILL_ID, text, relative)
            self.assertNotIn(AGENT_ID, text, relative)

        scaffold = ROOT / "skills" / "studio-project-scaffold" / "templates"
        for path in scaffold.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(SKILL_ID, text, path)
                self.assertNotIn(AGENT_ID, text, path)


if __name__ == "__main__":
    unittest.main()
