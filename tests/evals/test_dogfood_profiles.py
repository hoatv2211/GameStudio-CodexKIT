from __future__ import annotations

import json
import unittest
from pathlib import Path


class DogfoodProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]

    def test_fpc_static_selects_only_two_cases(self) -> None:
        from scripts.dogfood_eval import load_cases, load_profile

        profile = load_profile(self.root, "fpc-global-localization-static")
        cases = load_cases(self.root, profile="fpc-global-localization-static")

        self.assertEqual(
            ["fpc-global-residue-authority", "fpc-localization-doctor"],
            profile["case_ids"],
        )
        self.assertEqual(profile["case_ids"], [case["id"] for case in cases])
        self.assertEqual(["file-audit"], profile["runner_capabilities"])
        self.assertEqual(["Codex App/CLI"], profile["runtime_targets"])
        self.assertEqual(30, profile["max_evidence_age_days"])

    def test_runtime_profile_requires_unity_mcp_and_play_mode(self) -> None:
        from scripts.dogfood_eval import load_profile

        profile = load_profile(self.root, "fpc-global-localization-runtime")

        self.assertEqual(3, len(profile["case_ids"]))
        self.assertIn("unity-mcp", profile["runner_capabilities"])
        self.assertIn("play-mode", profile["runner_capabilities"])
        self.assertEqual(["Codex App/CLI"], profile["runtime_targets"])
        self.assertEqual(7, profile["max_evidence_age_days"])
        runtime_case = next(
            case for case in profile["cases"] if case["id"] == "fpc-unity-localization-runtime"
        )
        self.assertEqual(
            {
                "command-log",
                "project-snapshot",
                "runtime-audit",
                "mcp-transcript",
                "editor-state",
                "editmode-result",
                "playmode-result",
                "console-report",
                "runtime-assertion",
                "verdict",
            },
            set(runtime_case["required_artifacts"]),
        )
        self.assertEqual(
            [
                {
                    "artifact_kind": "editor-state",
                    "tool": "read_mcp_resource",
                    "operation": "mcpforunity://editor/state",
                },
                {
                    "artifact_kind": "editmode-result",
                    "tool": "run_tests",
                    "operation": "EditMode",
                },
                {
                    "artifact_kind": "editmode-result",
                    "tool": "get_test_job",
                    "operation": "EditMode",
                },
                {
                    "artifact_kind": "playmode-result",
                    "tool": "run_tests",
                    "operation": "PlayMode",
                },
                {
                    "artifact_kind": "playmode-result",
                    "tool": "get_test_job",
                    "operation": "PlayMode",
                },
                {
                    "artifact_kind": "console-report",
                    "tool": "read_console",
                    "operation": "get",
                },
                {
                    "artifact_kind": "runtime-assertion",
                    "tool": "execute_code",
                    "operation": "execute",
                },
            ],
            runtime_case["required_mcp_operations"],
        )

    def test_authorized_jx_static_profile_selects_three_read_only_cases(self) -> None:
        from scripts.dogfood_eval import load_cases, load_profile

        profile = load_profile(self.root, "authorized-jx-multirepo-static")
        cases = load_cases(self.root, profile="authorized-jx-multirepo-static")

        self.assertEqual(
            [
                "jx-multirepo-route-static",
                "jx-unity-guid-meta-static",
                "jx-citywar-authority-static",
            ],
            profile["case_ids"],
        )
        self.assertEqual(profile["case_ids"], [case["id"] for case in cases])
        self.assertTrue(all(case["allow_mutation"] is False for case in cases))
        self.assertEqual(
            ["file-audit", "git-snapshot", "static-source-review"],
            profile["runner_capabilities"],
        )
        self.assertEqual(
            [
                "studio-workspace-routing",
                "unity-asset-guid-meta-audit",
                "network-authority-and-exploit-review",
            ],
            profile["promotion_scope"],
        )

    def test_unknown_profile_is_rejected(self) -> None:
        from scripts.dogfood_eval import load_profile

        with self.assertRaisesRegex(ValueError, "unknown dogfood profile"):
            load_profile(self.root, "not-a-profile")

    def test_profile_schema_is_strict(self) -> None:
        import jsonschema

        schema = json.loads(
            (self.root / "evals" / "schema" / "dogfood-profile.schema.json").read_text(
                encoding="utf-8"
            )
        )
        profile = json.loads(
            (
                self.root
                / "evals"
                / "dogfood"
                / "profiles"
                / "fpc-global-localization-static.json"
            ).read_text(encoding="utf-8")
        )

        jsonschema.validate(profile, schema)


if __name__ == "__main__":
    unittest.main()
