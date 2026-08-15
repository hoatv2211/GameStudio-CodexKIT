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
                ".agents/project-profile.yaml",
                ".agents/references/validation-matrix.md",
                ".agents/references/workspace-map.md",
                ".agents/registry.json",
            ):
                self.assertFalse((root / relative).exists(), relative)
                self.assertIn(relative, result["proposed"])
            self.assertEqual(["database", "lua", "server", "unity"], result["subsystems"])

    def test_prunes_generated_cache_and_dependency_trees(self) -> None:
        from scripts.project_scaffold import detect_subsystems

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Library" / "Fake" / "Assets").mkdir(parents=True)
            (root / "Library" / "Fake" / "ProjectSettings").mkdir()
            (root / "Temp").mkdir()
            (root / "Temp" / "FakeServer.csproj").write_text("<Project />", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "fake.lua").write_text("return {}", encoding="utf-8")
            (root / "Logs").mkdir()
            (root / "Logs" / "schema.sql").write_text("-- generated", encoding="utf-8")

            self.assertEqual(set(), detect_subsystems(root))

    def test_reports_nested_git_roots_without_descending_into_git_data(self) -> None:
        from scripts.project_scaffold import scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            for repository in ("Client", "Server"):
                (root / repository / ".git" / "objects").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )
                (root / repository / ".git" / "objects" / "ignored.lua").write_text(
                    "return {}", encoding="utf-8"
                )
            (root / "Client" / "Assets").mkdir()
            (root / "Client" / "ProjectSettings").mkdir()
            (root / "Server" / "GameServer.csproj").write_text("<Project />", encoding="utf-8")

            result = scaffold_project(root)

            self.assertEqual(["Client", "Server"], result["git_roots"])
    def test_sanitized_multi_repository_fixture_builds_profile(self) -> None:
        from scripts.project_scaffold import draft_project_profile

        fixture_path = Path(__file__).with_name("fixtures") / "sabo-shaped-workspace.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        with temporary_directory() as temp:
            root = Path(temp)
            for relative in fixture["directories"]:
                (root / relative).mkdir(parents=True, exist_ok=True)
            for relative, content in fixture["files"].items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            profile = draft_project_profile(root)

            self.assertEqual(fixture["expected_git_roots"], [item["path"] for item in profile["repositories"]])
            observed = {item["path"]: item["subsystems"] for item in profile["repositories"]}
            self.assertEqual(fixture["expected_repositories"], observed)

    def test_ignores_stale_git_markers(self) -> None:
        from scripts.project_scaffold import detect_git_roots

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Valid" / ".git").mkdir(parents=True)
            (root / "Valid" / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
            (root / "StaleDirectory" / ".git").mkdir(parents=True)
            (root / "StaleGitfile").mkdir()
            (root / "StaleGitfile" / ".git").write_text(
                "gitdir: ../missing-module", encoding="utf-8"
            )

            self.assertEqual(["Valid"], detect_git_roots(root))

    def test_scaffold_reuses_one_discovery_snapshot(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            for repository in ("Client", "Server"):
                (root / repository / ".git").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )
            (root / "Client" / "Assets").mkdir()
            (root / "Client" / "ProjectSettings").mkdir()
            (root / "Server" / "GameServer.csproj").write_text("<Project />", encoding="utf-8")

            with mock.patch.object(
                scaffold, "detect_git_roots", wraps=scaffold.detect_git_roots
            ) as git_roots, mock.patch.object(
                scaffold, "detect_subsystems", wraps=scaffold.detect_subsystems
            ) as subsystems:
                scaffold.scaffold_project(root)

            self.assertEqual(1, git_roots.call_count)
            self.assertEqual(2, subsystems.call_count)

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
            from scripts.project_profile import load_project_profile

            profile = load_project_profile(
                root / ".agents" / "project-profile.yaml",
                known_skills={"studio-project-intake"},
            )
            self.assertEqual(root.name, profile["workspace"]["name"])
            self.assertTrue((root / ".agents" / "references" / "workspace-map.md").is_file())
            self.assertTrue((root / ".agents" / "references" / "validation-matrix.md").is_file())


if __name__ == "__main__":
    unittest.main()
