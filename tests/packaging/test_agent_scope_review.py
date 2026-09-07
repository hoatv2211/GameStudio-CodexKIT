from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path

import yaml


class AgentScopeReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.template_root = (
            self.root / "skills" / "studio-project-scaffold" / "templates" / "agents"
        )

    def profile(self, specialists: list[dict[str, object]]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "workspace": {
                "name": "scope-review",
                "root_git": False,
                "default_concurrency": 2,
            },
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
            "agents": {"specialists": specialists},
            "cross_project_contracts": [],
        }

    def specialist(self, role_id: str, effort: str = "high") -> dict[str, object]:
        return {
            "id": role_id,
            "repository": "client",
            "reasoning_effort": effort,
            "constraints": ["own only assigned files"],
        }

    def plan(self, profile, *, assignments=None, project_skills=()):
        from scripts.agent_overlay import plan_agent_overlay

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            return plan_agent_overlay(
                project,
                template_root=self.template_root,
                profile=profile,
                known_skills={"studio-project-intake"},
                project_skills=project_skills,
                active_assignments=assignments,
            )

    def test_explicit_project_effort_overrides_canonical_default(self) -> None:
        plan = self.plan(self.profile([self.specialist("cpp-game-server", "low")]))
        operations = {item["path"]: item["content"] for item in plan["operations"]}
        generated = tomllib.loads(operations[".codex/agents/cpp-game-server.toml"])
        self.assertEqual("low", generated["model_reasoning_effort"])

    def test_resolved_template_capability_overlap_is_advisory(self) -> None:
        plan = self.plan(
            self.profile(
                [
                    self.specialist("unity-csharp-client"),
                    self.specialist("technical-artist"),
                ]
            )
        )
        review = plan["scope_review"]
        self.assertEqual("PASS", review["status"])
        self.assertEqual("NOT_PROVIDED", review["assignment_status"])
        self.assertEqual(
            [["technical-artist", "unity-csharp-client"]],
            [item["roles"] for item in review["capability_overlaps"]],
        )
        self.assertEqual([], review["assignment_conflicts"])

    def test_inferred_and_configured_scopes_are_reviewed_after_resolution(self) -> None:
        plan = self.plan(
            self.profile([self.specialist("technical-artist")]),
            project_skills=[
                {"id": "project-unity-client", "repositories": ["client"]}
            ],
        )
        review = plan["scope_review"]
        pairs = [item["roles"] for item in review["capability_overlaps"]]
        self.assertIn(["technical-artist", "unity-csharp-client"], pairs)
        self.assertIn("resolved_scopes", review)
        resolved = {item["role_id"]: item for item in review["resolved_scopes"]}
        self.assertEqual(
            {"technical-artist", "unity-csharp-client"}, set(resolved)
        )
        self.assertIn(
            "client/**/Assets/**/*.prefab",
            resolved["technical-artist"]["owned_scope_patterns"],
        )
        self.assertIn(
            "client/Assets/**",
            resolved["unity-csharp-client"]["owned_scope_patterns"],
        )

    def test_disjoint_simultaneous_file_assignments_remain_allowed(self) -> None:
        plan = self.plan(
            self.profile(
                [
                    self.specialist("unity-csharp-client"),
                    self.specialist("technical-artist"),
                ]
            ),
            assignments=[
                {
                    "role_id": "unity-csharp-client",
                    "write_paths": ["client/Game/Assets/UI/menu.prefab"],
                },
                {
                    "role_id": "technical-artist",
                    "write_paths": ["client/Game/Assets/FX/smoke.shader"],
                },
            ],
        )
        review = plan["scope_review"]
        self.assertEqual("PASS", review["assignment_status"])
        self.assertEqual([], review["assignment_conflicts"])
        self.assertTrue(review["capability_overlaps"])

    def test_same_simultaneous_file_assignment_is_blocked(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "simultaneous agent write assignment conflict"
        ):
            self.plan(
                self.profile(
                    [
                        self.specialist("unity-csharp-client"),
                        self.specialist("technical-artist"),
                    ]
                ),
                assignments=[
                    {
                        "role_id": "unity-csharp-client",
                        "write_paths": ["client/Game/Assets/UI/menu.prefab"],
                    },
                    {
                        "role_id": "technical-artist",
                        "write_paths": ["client/Game/Assets/UI/menu.prefab"],
                    },
                ],
            )

    def test_assignment_outside_effective_scope_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside effective owned scope"):
            self.plan(
                self.profile([self.specialist("technical-artist")]),
                assignments=[
                    {
                        "role_id": "technical-artist",
                        "write_paths": ["client/Game/Scripts/Combat.cs"],
                    }
                ],
            )

    def test_project_adapter_report_exposes_resolved_scope_review(self) -> None:
        from scripts.generate_adapters import report_project_adapter

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                yaml.safe_dump(
                    self.profile(
                        [
                            self.specialist("unity-csharp-client"),
                            self.specialist("technical-artist"),
                        ]
                    ),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            report = report_project_adapter(self.root, project)

        self.assertEqual("PASS", report["scope_review"]["status"])
        self.assertTrue(report["scope_review"]["capability_overlaps"])


if __name__ == "__main__":
    unittest.main()
