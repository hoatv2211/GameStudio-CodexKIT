from __future__ import annotations

import tomllib
import tempfile
import unittest
from pathlib import Path

import yaml


SPECIALIST_IDS = {
    "unity-csharp-client",
    "csharp-backend",
    "cpp-game-server",
    "golang-services",
    "lua-gameplay",
    "game-data-engineer",
    "technical-artist",
    "ui-motion-artist",
    "ui-localization-specialist",
    "systems-game-designer",
    "qa-automation",
    "build-release-engineer",
    "liveops-sre",
    "game-security-engineer",
    "producer",
    "level-content-designer",
    "narrative-designer",
    "asset-pipeline-specialist",
    "audio-engineer",
    "product-analyst",
    "game-showcase-capture-producer",
}


class SpecialistAgentCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        registry = yaml.safe_load(
            (self.root / "registry" / "agent-roles.yaml").read_text(encoding="utf-8")
        )
        self.roles = {entry["id"]: entry for entry in registry["agent_roles"]}

    def test_registry_contains_all_opt_in_specialists(self) -> None:
        self.assertEqual(SPECIALIST_IDS, set(self.roles) - {"investigator", "implementer", "verifier"})
        for role_id in SPECIALIST_IDS:
            self.assertEqual("specialist", self.roles[role_id]["kind"])

    def test_ui_motion_artist_owns_ui_art_only_and_keeps_runtime_gate(self) -> None:
        role = self.roles["ui-motion-artist"]
        self.assertEqual(
            [
                "unity-ui-art-and-motion-production",
                "art-asset-pipeline-preflight",
                "unity-asset-guid-meta-audit",
                "build-and-runtime-verification",
            ],
            role["required_skills"],
        )
        self.assertIn("install animation or tween packages", role["forbidden_actions"])
        self.assertIn("approve own runtime verdict", role["forbidden_actions"])

    def test_game_showcase_capture_producer_stays_within_capture_and_packaging_scope(self) -> None:
        role = self.roles["game-showcase-capture-producer"]
        self.assertEqual(
            [
                "game-screenshot-showcase-and-store-packaging",
                "playtest-evidence",
                "build-and-runtime-verification",
                "store-submission-checklist",
            ],
            role["required_skills"],
        )
        self.assertEqual("Game screenshot showcase production", role["discipline"])
        self.assertEqual("workspace-write", role["sandbox_mode"])
        self.assertEqual("high", role["reasoning_effort"])
        self.assertIn("showcase/**", role["owned_scope_patterns"])
        self.assertIn("tests/**", role["read_scope_patterns"])
        self.assertIn("credential access", role["forbidden_actions"])
        self.assertIn("evidence deletion", role["forbidden_actions"])
        self.assertEqual(
            [
                "focused helper tests",
                "Unity PlayMode evidence",
                "artifact integrity",
            ],
            role["validation_commands"],
        )
        self.assertEqual("screenshot-showcase-writer", role["concurrency_group"])

    def test_specialist_metadata_and_templates_match(self) -> None:
        for role_id in SPECIALIST_IDS:
            role = self.roles[role_id]
            template_path = self.root / role["path"]
            self.assertTrue(template_path.is_file(), role_id)
            template = tomllib.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(role_id, template["name"])
            for field in (
                "discipline",
                "required_skills",
                "owned_scope_patterns",
                "read_scope_patterns",
                "forbidden_actions",
                "validation_commands",
                "concurrency_group",
            ):
                self.assertEqual(role[field], template[field], f"{role_id}: {field}")

    def test_specialist_templates_are_packaged_as_opt_in_resources(self) -> None:
        resources = yaml.safe_load(
            (self.root / "registry" / "skill-resources.yaml").read_text(encoding="utf-8")
        )
        entries = resources["bundled"]["studio-project-scaffold"]
        destinations = {entry["destination"] for entry in entries if isinstance(entry, dict)}
        for role_id in SPECIALIST_IDS:
            self.assertIn(f"templates/specialists/{role_id}.toml", destinations)

    def test_overlay_uses_canonical_template_only_when_profile_activates_it(self) -> None:
        from scripts.agent_overlay import plan_agent_overlay

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "workspace": {"name": "sample", "root_git": False, "default_concurrency": 1},
                        "repositories": [
                            {
                                "id": "client",
                                "path": "client",
                                "git_root": True,
                                "subsystems": ["unity"],
                                "owner_skill": "studio-project-intake",
                                "validation": [],
                            }
                        ],
                        "exclusions": [],
                        "agents": {
                            "specialists": [
                                {
                                    "id": "unity-csharp-client",
                                    "repository": "client",
                                    "reasoning_effort": "high",
                                    "constraints": ["own only the client repository"],
                                }
                            ]
                        },
                        "cross_project_contracts": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            plan = plan_agent_overlay(
                project,
                template_root=self.root / "skills" / "studio-project-scaffold" / "templates" / "agents",
                profile_path=profile_path,
                known_skills={"studio-project-intake"},
            )

        operations = {item["path"]: item["content"] for item in plan["operations"]}
        template = tomllib.loads(operations[".codex/agents/unity-csharp-client.toml"])
        self.assertEqual("Unity client engineering", template["discipline"])
        self.assertIn("unity-ui-rendering-debugging", template["required_skills"])
        self.assertIn("own only the client repository", template["developer_instructions"])
        self.assertNotIn(".codex/agents/cpp-game-server.toml", operations)


if __name__ == "__main__":
    unittest.main()
