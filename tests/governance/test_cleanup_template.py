from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import yaml

from tests._meta.support import temporary_directory


class CleanupTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = temporary_directory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_upstream_registry(self, repo: Path, commit: str) -> None:
        registry = self.root / "registry"
        registry.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "observed_at": "2026-08-08",
            "restore_root": ".research/repos",
            "sources": [
                {
                    "id": "fixture",
                    "remote": "https://example.invalid/fixture.git",
                    "commit": commit,
                    "license": "MIT",
                    "license_path": "LICENSE",
                    "restore_path": repo.relative_to(self.root).as_posix(),
                    "snapshot_clean": True,
                    "provenance_use": "fixture",
                }
            ],
        }
        (registry / "upstream-sources.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
        )

    def init_clean_research_repo(self) -> tuple[Path, str]:
        repo = self.root / ".research" / "repos" / "fixture"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (repo / "source.txt").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-q",
                "-m",
                "fixture",
            ],
            check=True,
        )
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        self.write_upstream_registry(repo, commit)
        return repo, commit

    def test_report_only_discovers_exact_categories_without_deleting(self) -> None:
        from scripts.cleanup_template import build_cleanup_report

        fixtures = {
            ".hermes/state.json": "{}\n",
            "reports/history.md": "history\n",
            "evidence/20260807-old/verdict.md": "old\n",
            "scripts/__pycache__/helper.pyc": "cache\n",
            "evidence/local/tier-b-cases.jsonl": "{}\n",
            "ordinary/keep.txt": "keep\n",
            "evidence/example/keep.txt": "example\n",
        }
        for relative, content in fixtures.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (self.root / ".test-tmp").mkdir()
        (self.root / ".tmp-test-fixture").mkdir()

        report = build_cleanup_report(self.root)

        self.assertEqual("REPORT_ONLY", report["mode"])
        self.assertEqual("QA Lead", report["required_reviewer"])
        self.assertTrue(report["approval_token"].startswith("APPLY-CLEAN-TEMPLATE-"))
        self.assertEqual(
            {
                ".hermes",
                "reports",
                "evidence/20260807-old",
                "scripts/__pycache__",
                "evidence/local/tier-b-cases.jsonl",
                ".test-tmp",
                ".tmp-test-fixture",
            },
            {target["path"] for target in report["targets"]},
        )
        for target in report["targets"]:
            self.assertEqual(64, len(target["sha256"]))
            self.assertGreaterEqual(target["bytes"], 0)
        self.assertTrue((self.root / "ordinary" / "keep.txt").exists())
        self.assertTrue((self.root / ".hermes" / "state.json").exists())

    def test_rejects_escape_and_reparse_targets(self) -> None:
        from scripts.cleanup_template import CleanupBlocked, apply_cleanup, build_cleanup_report

        (self.root / "reports").mkdir()
        report = build_cleanup_report(self.root)
        report["targets"][0]["path"] = "../outside"
        with self.assertRaises(CleanupBlocked):
            apply_cleanup(
                self.root,
                report,
                reviewer="QA Lead",
                approval_token=report["approval_token"],
            )

        external = self.root / "ordinary"
        external.mkdir()
        link = self.root / ".hermes"
        try:
            os.symlink(external, link, target_is_directory=True)
        except OSError:
            link.mkdir()
            with mock.patch(
                "scripts.cleanup_template._is_reparse",
                side_effect=lambda path: Path(path).name == ".hermes",
            ):
                with self.assertRaises(CleanupBlocked):
                    build_cleanup_report(self.root)
            return
        with self.assertRaises(CleanupBlocked):
            build_cleanup_report(self.root)

    def test_research_requires_clean_repo_and_records_restore_data(self) -> None:
        from scripts.cleanup_template import CleanupBlocked, build_cleanup_report

        repo, commit = self.init_clean_research_repo()
        report = build_cleanup_report(self.root)
        research = next(target for target in report["targets"] if target["path"] == ".research")
        self.assertEqual(commit, research["repositories"][0]["commit"])
        self.assertEqual("https://example.invalid/fixture.git", research["repositories"][0]["remote"])
        self.assertEqual("LICENSE", research["repositories"][0]["license_path"])
        self.assertTrue(research["repositories"][0]["clean"])

        (repo / "source.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaises(CleanupBlocked):
            build_cleanup_report(self.root)

    def test_apply_requires_reviewer_token_and_backup_then_removes_only_manifest(self) -> None:
        from scripts.cleanup_template import (
            CleanupBlocked,
            apply_cleanup,
            build_cleanup_report,
            create_backup_archive,
            write_manifest,
        )

        (self.root / "reports").mkdir()
        (self.root / "reports" / "history.md").write_text("history\n", encoding="utf-8")
        (self.root / ".test-tmp").mkdir()
        (self.root / "ordinary").mkdir()
        (self.root / "ordinary" / "keep.txt").write_text("keep\n", encoding="utf-8")
        report = build_cleanup_report(self.root)
        backup = self.root / "backup" / "history.zip"
        create_backup_archive(self.root, report, backup)
        manifest_path = self.root / "evidence" / "template-verification" / "cleanup-summary.json"
        write_manifest(report, manifest_path)
        persisted = json.loads(manifest_path.read_text(encoding="utf-8"))

        with self.assertRaises(CleanupBlocked):
            apply_cleanup(self.root, persisted, reviewer="", approval_token=persisted["approval_token"])
        with self.assertRaises(CleanupBlocked):
            apply_cleanup(self.root, persisted, reviewer="QA Lead", approval_token="wrong")

        result = apply_cleanup(
            self.root,
            persisted,
            reviewer="QA Lead",
            approval_token=persisted["approval_token"],
        )
        self.assertEqual("APPLIED", result["status"])
        self.assertFalse((self.root / "reports").exists())
        self.assertFalse((self.root / ".test-tmp").exists())
        self.assertTrue((self.root / "ordinary" / "keep.txt").exists())
        self.assertTrue(backup.exists())
        self.assertEqual(64, len(persisted["backup"]["sha256"]))


if __name__ == "__main__":
    unittest.main()
