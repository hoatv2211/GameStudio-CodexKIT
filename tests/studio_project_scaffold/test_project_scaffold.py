from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


class ProjectScaffoldTests(unittest.TestCase):
    def test_detects_subsystems_and_reports_without_writing_by_default(self) -> None:
        from scripts.project_scaffold import detect_subsystems, scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Client" / "Assets").mkdir(parents=True)
            (root / "Client" / "ProjectSettings").mkdir()
            (root / "Server").mkdir()
            (root / "Server" / "GameServer.csproj").write_text("<Project />", encoding="utf-8")
            (root / "Data").mkdir()
            (root / "Data" / "protocol.lua").write_text("return {}", encoding="utf-8")
            (root / "database").mkdir()
            (root / "database" / "schema.sql").write_text("-- schema", encoding="utf-8")

            self.assertEqual({"unity", "server", "lua", "database"}, detect_subsystems(root))
            result = scaffold_project(root)
            self.assertEqual("REPORT_ONLY", result["status"])
            for relative in (
                "AGENTS.md",
                "HANDOFF.md",
                ".agents/CONTRACT.md",
                ".agents/registry.json",
            ):
                self.assertFalse((root / relative).exists(), relative)
                self.assertIn(relative, result["proposed"])
            self.assertEqual(["database", "lua", "server", "unity"], result["subsystems"])

    def test_apply_requires_reviewer_and_uses_safe_mutation_manifest(self) -> None:
        from scripts.project_scaffold import apply_scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            local_skill = root / ".agents" / "skills" / "project-memory" / "SKILL.md"
            local_skill.parent.mkdir(parents=True)
            local_skill.write_text("local-owned\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_scaffold(root, reviewer="", backup_root=root / ".scaffold-backup")

            result = apply_scaffold(
                root,
                reviewer="Producer",
                backup_root=root / ".scaffold-backup",
            )
            self.assertEqual("PASS", result["status"])
            self.assertEqual("Producer", result["reviewer"])
            manifest = Path(result["manifest"])
            self.assertTrue(manifest.is_file())
            self.assertEqual(sys.executable, result["restore_argv"][0])
            self.assertEqual(
                Path(__file__).resolve().parents[2] / "scripts" / "safe_mutation.py",
                Path(result["restore_argv"][1]),
            )
            self.assertNotIn("restore", result)
            self.assertEqual("local-owned\n", local_skill.read_text(encoding="utf-8"))
            registry = json.loads((root / ".agents" / "registry.json").read_text(encoding="utf-8"))
            self.assertIn("project-memory", registry["skills"])


if __name__ == "__main__":
    unittest.main()
