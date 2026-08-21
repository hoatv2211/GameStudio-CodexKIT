from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
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

    def test_apply_requires_reviewer_digest_and_nonoverlapping_backup(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            local_skill = root / ".agents" / "skills" / "project-memory" / "SKILL.md"
            local_skill.parent.mkdir(parents=True)
            local_skill.write_text("local-owned\n", encoding="utf-8")
            report = scaffold.scaffold_project(root)

            with self.subTest("reviewer"):
                with self.assertRaisesRegex(ValueError, "reviewer"):
                    scaffold.apply_scaffold(
                        root,
                        reviewer="",
                        backup_root=root / ".scaffold-backup",
                        approved_plan_digest=report["plan_digest"],
                    )
                self.assertFalse((root / "AGENTS.md").exists())

            with self.subTest("approved plan digest"):
                with self.assertRaisesRegex(ValueError, "approved plan digest"):
                    scaffold.apply_scaffold(
                        root,
                        reviewer="Producer",
                        backup_root=root / ".scaffold-backup",
                        approved_plan_digest="",
                    )
                self.assertFalse((root / "AGENTS.md").exists())

            with self.subTest("backup root"):
                with mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before backup validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(ValueError, "backup root is required"):
                        scaffold.apply_scaffold(
                            root,
                            reviewer="Producer",
                            backup_root="",
                            approved_plan_digest=report["plan_digest"],
                        )
                    apply_mutation.assert_not_called()
                self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

            with self.subTest("blank Path backup root"):
                with mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before backup validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(ValueError, "backup root is required"):
                        scaffold.apply_scaffold(
                            root,
                            reviewer="Producer",
                            backup_root=Path("   "),
                            approved_plan_digest=report["plan_digest"],
                        )
                    apply_mutation.assert_not_called()
                self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

            with self.subTest("overlapping backup"):
                with mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before backup validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(
                        ValueError,
                        "scaffold backup root overlaps scaffold output",
                    ):
                        scaffold.apply_scaffold(
                            root,
                            reviewer="Producer",
                            backup_root=root / ".agents" / "backup",
                            approved_plan_digest=report["plan_digest"],
                        )
                    apply_mutation.assert_not_called()
                self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

            result = scaffold.apply_scaffold(
                root,
                reviewer="Producer",
                backup_root=root / ".scaffold-backup",
                approved_plan_digest=report["plan_digest"],
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

    def test_uninit_refuses_owned_symlink_without_deleting_external_target(self) -> None:
        from unittest import mock

        from scripts.project_scaffold import scaffold_project, uninit_scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold_project(root)
            result = self._apply_scaffold_for_test(root, report)
            self.assertEqual("PASS", result["status"])

            external = root.parent / f"{root.name}-external-owned.txt"
            self.addCleanup(external.unlink, missing_ok=True)
            external.write_text((root / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")
            owned = root / "AGENTS.md"
            owned.unlink()
            try:
                os.symlink(external, owned)
            except (OSError, NotImplementedError):
                owned.write_text(external.read_text(encoding="utf-8"), encoding="utf-8")
                original_resolve = Path.resolve

                def resolve(path: Path, *args: object, **kwargs: object) -> Path:
                    if path == owned:
                        return external
                    return original_resolve(path, *args, **kwargs)

                resolve_patch = mock.patch.object(Path, "resolve", autospec=True, side_effect=resolve)
            else:
                resolve_patch = mock.patch.object(Path, "resolve", wraps=Path.resolve)

            with mock.patch(
                "scripts.project_scaffold._is_reparse_point",
                side_effect=lambda path: Path(path) == owned,
            ):
                preview = uninit_scaffold(root)
            self.assertIn("AGENTS.md", preview["preserved_drift"])
            self.assertNotIn("AGENTS.md", preview["removable"])

            backup_root = root.parent / f"{root.name}-uninit-backup"
            self.addCleanup(shutil.rmtree, backup_root, ignore_errors=True)
            with mock.patch(
                "scripts.project_scaffold._is_reparse_point",
                side_effect=lambda path: Path(path) == owned,
            ), resolve_patch:
                applied = uninit_scaffold(
                    root,
                    apply=True,
                    reviewer="Producer",
                    backup_root=backup_root,
                )
            self.assertNotIn("AGENTS.md", applied["removed"])
            self.assertTrue(external.is_file())

    def test_uninit_rejects_manifest_path_escape(self) -> None:
        from scripts.project_scaffold import scaffold_project, uninit_scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold_project(root)
            result = self._apply_scaffold_for_test(root, report)
            self.assertEqual("PASS", result["status"])
            external = root.parent / f"{root.name}-external-owned.txt"
            self.addCleanup(external.unlink, missing_ok=True)
            external.write_text("external\n", encoding="utf-8")
            manifest_path = root / ".agents" / "gamestudio-install.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["path"] = "../" + external.name
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "escapes project root"):
                uninit_scaffold(root)
            with self.assertRaisesRegex(ValueError, "escapes project root"):
                uninit_scaffold(
                    root,
                    apply=True,
                    reviewer="Producer",
                    backup_root=root.parent / f"{root.name}-uninit-backup",
                )
            self.assertTrue(external.is_file())

    @staticmethod
    def _apply_scaffold_for_test(root: Path, report: dict[str, object]) -> dict[str, object]:
        from scripts.project_scaffold import apply_scaffold

        return apply_scaffold(
            root,
            reviewer="Producer",
            backup_root=root / ".scaffold-backup",
            approved_plan_digest=report["plan_digest"],
        )

    def test_apply_type_checks_and_normalizes_approval_metadata(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold.scaffold_project(root)

            with self.subTest("reviewer type"):
                with mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before approval validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(ValueError, "reviewer"):
                        scaffold.apply_scaffold(
                            root,
                            reviewer=123,
                            backup_root=root / ".scaffold-backup",
                            approved_plan_digest=report["plan_digest"],
                        )
                    apply_mutation.assert_not_called()

            with self.subTest("approved plan digest type"):
                with mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before approval validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(ValueError, "approved plan digest"):
                        scaffold.apply_scaffold(
                            root,
                            reviewer="Producer",
                            backup_root=root / ".scaffold-backup",
                            approved_plan_digest=123,
                        )
                    apply_mutation.assert_not_called()

            result = scaffold.apply_scaffold(
                root,
                reviewer="  Producer  ",
                backup_root=root / ".scaffold-backup",
                approved_plan_digest=f"  {report['plan_digest']}  ",
            )

            self.assertEqual("PASS", result["status"])
            self.assertEqual("Producer", result["reviewer"])

    def test_apply_rejects_stale_plan_without_mutation(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold.scaffold_project(root)
            agents = root / "AGENTS.md"
            agents.write_text("local owner\n", encoding="utf-8")

            with mock.patch.object(
                scaffold,
                "apply_mutation",
                side_effect=AssertionError("mutation attempted with stale approval"),
            ) as apply_mutation:
                with self.assertRaisesRegex(ValueError, "scaffold plan changed"):
                    scaffold.apply_scaffold(
                        root,
                        reviewer="Producer",
                        backup_root=root / ".scaffold-backup",
                        approved_plan_digest=report["plan_digest"],
                    )
                apply_mutation.assert_not_called()

            self.assertEqual("local owner\n", agents.read_text(encoding="utf-8"))
            self.assertFalse((root / "HANDOFF.md").exists())
            self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

    def test_apply_rejects_unsafe_backup_locations_before_mutation(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold.scaffold_project(root)
            cases = (
                ("external", root.parent / f"{root.name}-external-backup", "inside the project root"),
                ("project root", root, "below the project root"),
                ("exact output", root / "AGENTS.md", "overlaps scaffold output"),
                ("output descendant", root / "AGENTS.md" / "backup", "overlaps scaffold output"),
                ("output ancestor", root / ".agents", "overlaps scaffold output"),
            )

            for name, backup_root, message in cases:
                with self.subTest(name=name), mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before backup validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(ValueError, message):
                        scaffold.apply_scaffold(
                            root,
                            reviewer="Producer",
                            backup_root=backup_root,
                            approved_plan_digest=report["plan_digest"],
                        )
                    apply_mutation.assert_not_called()

            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows reparse containment coverage")
    def test_apply_rejects_backup_reparse_point_resolving_outside_root(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            workspace = Path(temp)
            root = workspace / "project"
            outside = workspace / "outside"
            root.mkdir()
            outside.mkdir()
            backup_link = root / ".scaffold-backup"
            try:
                backup_link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"directory symlink unavailable: {error}")
            report = scaffold.scaffold_project(root)

            with mock.patch.object(
                scaffold,
                "apply_mutation",
                side_effect=AssertionError("mutation attempted through reparse point"),
            ) as apply_mutation:
                with self.assertRaisesRegex(ValueError, "inside the project root"):
                    scaffold.apply_scaffold(
                        root,
                        reviewer="Producer",
                        backup_root=backup_link,
                        approved_plan_digest=report["plan_digest"],
                    )
                apply_mutation.assert_not_called()

            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((outside / "manifest.json").exists())

    def test_apply_forwards_expected_operations_to_safe_mutation(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            backup_root = root / ".scaffold-backup"
            report = scaffold.scaffold_project(root)
            manifest = backup_root / "manifest.json"

            with mock.patch.object(
                scaffold,
                "apply_mutation",
                return_value=manifest,
            ) as apply_mutation:
                result = scaffold.apply_scaffold(
                    root,
                    reviewer="Producer",
                    backup_root=backup_root,
                    approved_plan_digest=report["plan_digest"],
                )

            self.assertEqual(str(manifest), result["manifest"])
            self.assertEqual(
                report["mutation_report"]["operations"],
                apply_mutation.call_args.kwargs["expected_operations"],
            )
            self.assertEqual(root.resolve(), apply_mutation.call_args.args[0])
            self.assertEqual(backup_root.resolve(), apply_mutation.call_args.args[2])

    def test_standalone_apply_requires_and_forwards_plan_digest(self) -> None:
        from unittest import mock

        import scripts.project_scaffold as scaffold

        with temporary_directory() as temp:
            root = Path(temp)
            backup_root = root / ".scaffold-backup"
            with mock.patch.object(
                scaffold,
                "apply_scaffold",
                return_value={"status": "PASS"},
            ) as apply_scaffold:
                with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                    scaffold.main([
                        str(root),
                        "--apply",
                        "--reviewer",
                        "Producer",
                        "--backup-root",
                        str(backup_root),
                    ])
                apply_scaffold.assert_not_called()

                output = StringIO()
                with redirect_stdout(output):
                    exit_code = scaffold.main([
                        str(root),
                        "--apply",
                        "--reviewer",
                        "Producer",
                        "--backup-root",
                        str(backup_root),
                        "--plan-digest",
                        "approved-digest",
                    ])

            self.assertEqual(0, exit_code)
            self.assertEqual("PASS", json.loads(output.getvalue())["status"])
            apply_scaffold.assert_called_once_with(
                root,
                reviewer="Producer",
                backup_root=backup_root,
                approved_plan_digest="approved-digest",
            )

            report = scaffold.scaffold_project(root)
            with mock.patch.object(
                scaffold,
                "apply_mutation",
                side_effect=AssertionError("mutation attempted before backup validation"),
            ) as apply_mutation:
                with self.assertRaisesRegex(ValueError, "backup root is required"):
                    scaffold.main([
                        str(root),
                        "--apply",
                        "--reviewer",
                        "Producer",
                        "--backup-root",
                        "   ",
                        "--plan-digest",
                        report["plan_digest"],
                    ])
                apply_mutation.assert_not_called()
            self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

            approval_cases = (
                ("reviewer", "   ", report["plan_digest"], "reviewer"),
                ("approved digest", "Producer", "   ", "approved plan digest"),
                ("wrong digest", "Producer", "0" * 64, "scaffold plan changed"),
            )
            for name, reviewer, plan_digest, message in approval_cases:
                with self.subTest(name=name), mock.patch.object(
                    scaffold,
                    "apply_mutation",
                    side_effect=AssertionError("mutation attempted before approval validation"),
                ) as apply_mutation:
                    with self.assertRaisesRegex(ValueError, message):
                        scaffold.main([
                            str(root),
                            "--apply",
                            "--reviewer",
                            reviewer,
                            "--backup-root",
                            str(backup_root),
                            "--plan-digest",
                            plan_digest,
                        ])
                    apply_mutation.assert_not_called()
            self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())


if __name__ == "__main__":
    unittest.main()
