from __future__ import annotations

import unittest
from pathlib import Path


class ExecutionReferenceTests(unittest.TestCase):
    def test_execution_heavy_skills_bundle_command_references(self) -> None:
        root = Path(__file__).resolve().parents[2]
        required = {
            "unity-batchmode-build-verification": ("-batchmode", "Editor.log", "artifact"),
            "game-database-migration-safety": ("mysql", "mysqldump", "restore"),
            "cpp-server-crash-triage": ("dump", "symbols", "stack"),
            "multi-service-local-environment-doctor": ("Get-NetTCPConnection", "ss -lntp", "port"),
            "build-and-runtime-verification": ("PIPESTATUS", "fresh", "artifact"),
            "liveops-incident-response": ("--data-urlencode", "data_keys", "BLOCKED"),
            "unity-client-offline-debugging": ("BeforeSceneLoad", "AfterSceneLoad", "timeout"),
            "unity-ui-rendering-debugging": ("mDepth:", "Resources.FindObjectsOfTypeAll", "active"),
        }
        for skill, tokens in required.items():
            with self.subTest(skill=skill):
                skill_path = root / "skills" / skill / "SKILL.md"
                reference_path = root / "skills" / skill / "references" / "commands.md"
                self.assertTrue(reference_path.exists(), reference_path)
                body = skill_path.read_text(encoding="utf-8")
                self.assertIn("references/commands.md", body)
                reference = reference_path.read_text(encoding="utf-8")
                for token in tokens:
                    self.assertIn(token, reference)
                self.assertIn("Evidence", reference)
                self.assertIn("Do not", reference)

    def test_goal_progress_open_reference_keeps_binding_and_service_gates(self) -> None:
        root = Path(__file__).resolve().parents[2]
        reference = (
            root / "skills" / "studio-goal-progress" / "references" / "commands.md"
        ).read_text(encoding="utf-8")

        for required in (
            "explicit Goal root or one unique nonterminal Goal from the caller's declared manifest runtime binding",
            "Reuse a healthy authenticated dashboard runtime without new service-control approval",
            "Starting a stopped or missing runtime requires immediate explicit service-control approval",
            "Without that approval, return `BLOCKED`",
            "one-time localhost URL",
            "separate server, panel, and browser statuses",
            "the host agent opens the Codex panel when available or instructs manual browser use",
        ):
            self.assertIn(required, reference)
        self.assertNotIn("does not resolve manifest runtime bindings", reference)
        self.assertNotIn("do not start one from `open`", reference)


if __name__ == "__main__":
    unittest.main()
