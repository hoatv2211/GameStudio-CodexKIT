from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests._meta.support import temporary_directory


class FakeUnavailableRunner:
    def __call__(self, argv: list[str], *, cwd: Path) -> object:
        raise FileNotFoundError("codegraph")


class GameStudioCliTests(unittest.TestCase):
    def test_init_is_report_only_and_cli_json_matches_shared_report(self) -> None:
        from scripts.gamestudio_cli import main

        with temporary_directory() as temp:
            root = Path(temp)
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["init", str(root), "--codegraph", "disabled"])
            report = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual("REPORT_ONLY", report["status"])
        self.assertEqual(64, len(report["plan_digest"]))
        self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

    def test_apply_requires_reviewer_backup_and_matching_digest(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold_project(
                root,
                codegraph_runner=FakeUnavailableRunner(),
                codegraph_preference="never_suggest",
            )
            with self.assertRaises(SystemExit):
                main(["init", str(root), "--apply"])
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "init", str(root), "--apply", "--reviewer", "Tech Lead",
                    "--backup-root", str(root / ".backup"),
                    "--plan-digest", report["plan_digest"], "--codegraph", "disabled",
                ])
            manifest_exists = (root / ".agents" / "gamestudio-install.json").is_file()

        self.assertEqual(0, exit_code)
        applied = json.loads(output.getvalue())
        self.assertEqual("PASS", applied["status"])
        self.assertTrue(manifest_exists)

    def test_status_and_hash_safe_uninit_preserve_drift(self) -> None:
        from scripts.project_scaffold import apply_scaffold, scaffold_project, scaffold_status, uninit_scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold_project(root, codegraph_runner=FakeUnavailableRunner())
            apply_scaffold(
                root,
                reviewer="Tech Lead",
                backup_root=root / ".backup",
                approved_plan_digest=report["plan_digest"],
                codegraph_runner=FakeUnavailableRunner(),
            )
            drifted = root / "AGENTS.md"
            drifted.write_text(drifted.read_text(encoding="utf-8") + "local drift\n", encoding="utf-8")

            status = scaffold_status(root)
            preview = uninit_scaffold(root)
            result = uninit_scaffold(
                root,
                apply=True,
                reviewer="Tech Lead",
                backup_root=root / ".uninit-backup",
            )
            drifted_exists = drifted.is_file()
            manifest_exists = (root / ".agents" / "gamestudio-install.json").exists()

        self.assertEqual("DRIFTED", status["status"])
        self.assertEqual("REPORT_ONLY", preview["status"])
        self.assertEqual("PARTIAL", result["status"])
        self.assertIn("AGENTS.md", result["preserved_drift"])
        self.assertTrue(drifted_exists)
        self.assertFalse(manifest_exists)

    def test_codegraph_install_selection_returns_plan_without_running_actions(self) -> None:
        from scripts.gamestudio_cli import main

        with temporary_directory() as temp:
            root = Path(temp)
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "init", str(root), "--codegraph", "plan-install",
                    "--reviewer", "Tech Lead",
                ])
            report = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual("CODEGRAPH_INSTALL", report["codegraph_install_plan"]["kind"])
        self.assertFalse((root / ".codegraph").exists())


if __name__ == "__main__":
    unittest.main()
