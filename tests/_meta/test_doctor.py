from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory, write_plugin_package


def install_reviewed_project_adapter(source_root: Path, project: Path) -> dict[str, object]:
    from scripts.doctor import install_adapter

    report = install_adapter(source_root, "per-project", project)
    return install_adapter(
        source_root,
        "per-project",
        project,
        apply=True,
        reviewer="QA Lead",
        backup_root=project / ".adapter-backup",
        approved_plan_digest=report["plan_digest"],
    )

class DoctorTests(unittest.TestCase):
    def test_health_checks_disable_bytecode_and_leave_no_cache(self) -> None:
        from scripts.doctor import health

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            root = Path(temp)
            ignore_generated = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
            for directory in ("scripts", "skills", "agents", "registry", "personas", "evals"):
                shutil.copytree(
                    source_root / directory,
                    root / directory,
                    ignore=ignore_generated,
                )
            self.assertEqual([], list(root.rglob("__pycache__")))
            write_plugin_package(root)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)

            result = health(root)

            self.assertEqual("PASS", result["status"])
            for check in result["checks"]:
                self.assertEqual("-B", check["command"][1])
            self.assertEqual([], list(root.rglob("__pycache__")))

    def test_installs_hook_and_invalid_skill_blocks_commit(self) -> None:
        from scripts.doctor import install_hook

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            root = Path(temp)
            git_environment = os.environ.copy()
            git_environment["GIT_CEILING_DIRECTORIES"] = str(root.parent)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                env=git_environment,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
            shutil.copytree(source_root / "scripts", root / "scripts")
            (root / "skills" / "broken").mkdir(parents=True)
            (root / "skills" / "broken" / "SKILL.md").write_text("---\nname: wrong\n---\n", encoding="utf-8")
            install_hook(root, python_executable=sys.executable)
            hook = root / ".git" / "hooks" / "pre-commit"
            self.assertTrue(hook.exists())
            if os.name != "nt":
                self.assertTrue(hook.stat().st_mode & stat.S_IXUSR)
            self.assertIn('[sys.executable, "-B",', hook.read_text(encoding="utf-8"))
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            result = subprocess.run(
                ["git", "commit", "-m", "invalid skill"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            count = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, count.returncode)

    def test_adapter_install_per_project_defaults_to_report_only(self) -> None:
        from scripts.doctor import install_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"

            report = install_adapter(source_root, "per-project", project)

            self.assertEqual("REPORT_ONLY", report["status"])
            self.assertIn(".agents/registry.json", report["proposed"])
            self.assertFalse(project.exists())

    def test_adapter_install_per_project_apply_requires_review_inputs(self) -> None:
        from scripts.doctor import install_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            with self.assertRaisesRegex(ValueError, "reviewer"):
                install_adapter(
                    source_root,
                    "per-project",
                    project,
                    apply=True,
                    reviewer="   ",
                    backup_root=project / ".adapter-backup",
                )
            with self.assertRaisesRegex(ValueError, "backup_root"):
                install_adapter(
                    source_root,
                    "per-project",
                    project,
                    apply=True,
                    reviewer="QA Lead",
                )
            self.assertFalse(project.exists())

    def test_doctor_cli_per_project_defaults_to_report_and_enforces_apply_args(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"
            base = [
                sys.executable,
                "-B",
                str(source_root / "scripts" / "doctor.py"),
                "--root",
                str(source_root),
                "--install-adapter",
                "per-project",
                "--destination",
                str(project),
            ]
            report = subprocess.run(base, cwd=source_root, check=False, capture_output=True, text=True)
            missing_args = subprocess.run(
                [*base, "--apply"],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, report.returncode, report.stderr)
            self.assertEqual("REPORT_ONLY", json.loads(report.stdout)["status"])
            self.assertNotEqual(0, missing_args.returncode)
            self.assertIn("--reviewer", missing_args.stderr)
            self.assertFalse(project.exists())

    def test_doctor_adapter_apply_requires_approved_plan_digest(self) -> None:
        from scripts.doctor import install_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            report = install_adapter(source_root, "per-project", project)

            with self.assertRaisesRegex(ValueError, "approved_plan_digest"):
                install_adapter(
                    source_root,
                    "per-project",
                    project,
                    apply=True,
                    reviewer="QA Lead",
                    backup_root=project / ".adapter-backup",
                )

            self.assertFalse(project.exists())
            self.assertTrue(report["plan_digest"])

    def test_doctor_cli_requires_plan_digest_and_rejects_uninstall_review_args(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            script = str(source_root / "scripts" / "doctor.py")
            base = [
                sys.executable,
                "-B",
                script,
                "--root",
                str(source_root),
                "--destination",
                str(project),
            ]
            missing_digest = subprocess.run(
                [
                    *base,
                    "--install-adapter",
                    "per-project",
                    "--apply",
                    "--reviewer",
                    "QA Lead",
                    "--backup-root",
                    str(project / ".adapter-backup"),
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            uninstall_with_digest = subprocess.run(
                [
                    *base,
                    "--uninstall-adapter",
                    "--plan-digest",
                    "0" * 64,
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, missing_digest.returncode)
            self.assertIn("--plan-digest", missing_digest.stderr)
            self.assertNotEqual(0, uninstall_with_digest.returncode)
            self.assertIn("cannot be used with --uninstall-adapter", uninstall_with_digest.stderr)
            self.assertFalse(project.exists())

    def test_adapter_install_and_uninstall_preserve_project_local_skills(self) -> None:
        from scripts.doctor import install_adapter, uninstall_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp)
            local_skill = project / ".agents" / "skills" / "project-memory" / "SKILL.md"
            local_skill.parent.mkdir(parents=True)
            local_skill.write_text("local-owned\n", encoding="utf-8")
            install_reviewed_project_adapter(source_root, project)
            generated = project / ".agents" / "skills" / "studio-project-intake" / "SKILL.md"
            self.assertTrue(generated.exists())
            removed = uninstall_adapter(project)
            self.assertIn("studio-project-intake", removed)
            self.assertFalse(generated.exists())
            self.assertEqual("local-owned\n", local_skill.read_text(encoding="utf-8"))

    def test_adapter_uninstall_does_not_trust_marker_substrings(self) -> None:
        from scripts.doctor import install_adapter, uninstall_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp)
            install_reviewed_project_adapter(source_root, project)
            local_skill = project / ".agents" / "skills" / "local-notes" / "SKILL.md"
            local_skill.parent.mkdir(parents=True)
            local_skill.write_text(
                "Local notes mention Generated by scripts/generate_adapters.py. Do not edit manually.\n",
                encoding="utf-8",
            )
            removed = uninstall_adapter(project)
            self.assertNotIn("local-notes", removed)
            self.assertTrue(local_skill.exists())

    def test_adapter_uninstall_refuses_to_remove_drifted_generated_skill(self) -> None:
        from scripts.doctor import install_adapter, uninstall_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp)
            install_reviewed_project_adapter(source_root, project)
            generated = project / ".agents" / "skills" / "studio-project-intake" / "SKILL.md"
            generated.write_text(generated.read_text(encoding="utf-8") + "local drift\n", encoding="utf-8")
            removed = uninstall_adapter(project)
            self.assertNotIn("studio-project-intake", removed)
            self.assertTrue(generated.exists())
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            remaining = registry["kit_adapter"]["files"]
            self.assertEqual(
                [".agents/skills/studio-project-intake/SKILL.md"],
                [entry["path"] for entry in remaining],
            )


if __name__ == "__main__":
    unittest.main()
