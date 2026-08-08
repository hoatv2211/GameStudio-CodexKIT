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


if __name__ == "__main__":
    unittest.main()
