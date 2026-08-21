from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import yaml

from tests._meta.support import temporary_directory


ISOLATED_INSTALLED_CLI_BOOTSTRAP = r"""
import importlib.util
import runpy
import sys
import types
from pathlib import Path

script_path = Path(sys.argv[1]).resolve(strict=True)
repository_root = Path(sys.argv[2]).resolve(strict=True)
scripts_root = script_path.parent

def resolved_path(entry):
    try:
        return Path(entry).resolve(strict=True)
    except (OSError, RuntimeError):
        return None

sys.path[:] = [
    entry
    for entry in sys.path
    if (resolved := resolved_path(entry)) is None
    or not resolved.is_relative_to(repository_root)
]
sys.path.insert(0, str(scripts_root))
for entry in sys.path[1:]:
    resolved = resolved_path(entry)
    if resolved is not None and resolved.is_relative_to(repository_root):
        raise RuntimeError(f"repository path leaked into isolated sys.path: {resolved}")

required_helpers = (
    "agent_overlay",
    "codegraph_adapter",
    "project_complexity",
    "project_profile",
    "project_scaffold",
    "project_skill_overlay",
    "safe_mutation",
    "studio_experience",
)
for module_name in required_helpers:
    spec = importlib.util.find_spec(module_name)
    origin = (
        Path(spec.origin).resolve(strict=True)
        if spec is not None and spec.origin is not None
        else None
    )
    if origin is None or not origin.is_relative_to(scripts_root):
        raise ImportError(
            f"bundled helper {module_name!r} did not resolve under {scripts_root}: "
            f"{origin}"
        )

# Force the copied CLI through its documented direct-module fallback imports,
# even if an unrelated global package happens to use the name ``scripts``.
scripts_namespace = types.ModuleType("scripts")
scripts_namespace.__path__ = []
sys.modules["scripts"] = scripts_namespace
sys.argv = [str(script_path), *sys.argv[3:]]
runpy.run_path(str(script_path), run_name="__main__")
"""


class FakeUnavailableRunner:
    def __call__(self, argv: list[str], *, cwd: Path) -> object:
        raise FileNotFoundError("codegraph")


class GameStudioCliTests(unittest.TestCase):
    def create_link_or_skip(
        self,
        link: Path,
        target: Path,
        *,
        target_is_directory: bool,
    ) -> bool:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
            return False
        except (NotImplementedError, OSError) as error:
            if os.name != "nt" or not target_is_directory:
                self.skipTest(f"filesystem links unavailable: {error}")
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                text=True,
                timeout=20,
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest(
                    "filesystem links unavailable: "
                    f"{error}; junction failed: {completed.stderr.strip()}"
                )
            return True

    @staticmethod
    def project_tree(root: Path) -> list[tuple[str, str, bytes | None]]:
        return [
            (
                path.relative_to(root).as_posix(),
                "directory" if path.is_dir() else "file",
                None if path.is_dir() else path.read_bytes(),
            )
            for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        ]

    @staticmethod
    def write_profile(root: Path, profile: dict[str, object]) -> Path:
        profile_path = root / ".agents" / "project-profile.yaml"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            yaml.safe_dump(profile, sort_keys=False),
            encoding="utf-8",
        )
        return profile_path

    def assert_workflow_parser_error(
        self,
        argv: list[str],
        root: Path,
        *,
        output: io.StringIO,
        errors: io.StringIO,
    ) -> None:
        before = self.project_tree(root)
        with redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as context:
                from scripts.gamestudio_cli import main

                main(argv)
        self.assertEqual(2, context.exception.code)
        self.assertEqual("", output.getvalue())
        self.assertIn("--workflow requires --mode advanced", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertEqual(before, self.project_tree(root))

    def test_guide_workflow_requires_explicit_advanced_mode(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            output = io.StringIO()
            errors = io.StringIO()
            self.assert_workflow_parser_error(
                [
                    "guide",
                    str(root),
                    "--intent",
                    "verify",
                    "--mode",
                    "basic",
                    "--workflow",
                    "unity-asset-guid-meta-audit",
                ],
                root,
                output=output,
                errors=errors,
            )

    def test_guide_workflow_rejects_omitted_mode_even_when_profile_prefers_advanced(
        self,
    ) -> None:
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            profile = draft_project_profile(root)
            profile["studio_experience"]["preferred_mode"] = "advanced"
            self.write_profile(root, profile)
            output = io.StringIO()
            errors = io.StringIO()
            self.assert_workflow_parser_error(
                [
                    "guide",
                    str(root),
                    "--intent",
                    "verify",
                    "--workflow",
                    "unity-asset-guid-meta-audit",
                ],
                root,
                output=output,
                errors=errors,
            )

    def test_guide_advanced_workflow_selects_requested_unity_asset_audit_read_only(
        self,
    ) -> None:
        import scripts.gamestudio_cli as cli
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            profile = draft_project_profile(root)
            profile["repositories"][0]["subsystems"] = ["unity", "assets"]
            profile["studio_experience"]["default_role"] = "qa"
            profile["studio_experience"]["preferred_mode"] = "advanced"
            self.write_profile(root, profile)
            before = self.project_tree(root)
            output = io.StringIO()
            with mock.patch.multiple(
                cli,
                apply_install_plan=mock.DEFAULT,
                create_install_plan=mock.DEFAULT,
                apply_scaffold=mock.DEFAULT,
                scaffold_project=mock.DEFAULT,
                uninit_scaffold=mock.DEFAULT,
            ) as mutating_helpers:
                with redirect_stdout(output):
                    exit_code = cli.main(
                        [
                            "guide",
                            str(root),
                            "--intent",
                            "verify",
                            "--mode",
                            "advanced",
                            "--golden-path",
                            "unity-build-asset-integrity",
                            "--workflow",
                            "unity-asset-guid-meta-audit",
                        ]
                    )
            after = self.project_tree(root)

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("READY", report["status"])
        self.assertEqual("qa", report["role"])
        self.assertEqual("advanced", report["mode"])
        self.assertEqual("unity-build-asset-integrity", report["golden_path"])
        self.assertEqual(
            "unity-asset-guid-meta-audit", report["selected_workflow"]
        )
        self.assertEqual(
            ["unity-asset-guid-meta-audit"], report["workflow_candidates"]
        )
        self.assertEqual(before, after)
        for helper in mutating_helpers.values():
            helper.assert_not_called()

    def test_guide_advanced_unavailable_workflow_is_blocked_without_writes(self) -> None:
        import scripts.gamestudio_cli as cli
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            profile = draft_project_profile(root)
            profile["repositories"][0]["subsystems"] = ["unity", "assets"]
            profile["studio_experience"]["default_role"] = "qa"
            profile["studio_experience"]["preferred_mode"] = "advanced"
            self.write_profile(root, profile)
            before = self.project_tree(root)
            output = io.StringIO()
            with mock.patch.multiple(
                cli,
                apply_install_plan=mock.DEFAULT,
                create_install_plan=mock.DEFAULT,
                apply_scaffold=mock.DEFAULT,
                scaffold_project=mock.DEFAULT,
                uninit_scaffold=mock.DEFAULT,
            ) as mutating_helpers:
                with redirect_stdout(output):
                    exit_code = cli.main(
                        [
                            "guide",
                            str(root),
                            "--intent",
                            "verify",
                            "--mode",
                            "advanced",
                            "--golden-path",
                            "unity-build-asset-integrity",
                            "--workflow",
                            "workflow-not-installed",
                        ]
                    )
            after = self.project_tree(root)

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertIsNone(report["selected_workflow"])
        self.assertTrue(
            any("workflow-not-installed" in item for item in report["prerequisites"])
        )
        self.assertEqual(before, after)
        for helper in mutating_helpers.values():
            helper.assert_not_called()

    def test_guide_help_documents_workflow_advanced_requirement(self) -> None:
        from scripts.gamestudio_cli import main

        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as context:
                main(["guide", "--help"])

        self.assertEqual(0, context.exception.code)
        self.assertEqual("", errors.getvalue())
        self.assertIn("--workflow", output.getvalue())
        self.assertIn("advanced", output.getvalue().lower())

    def test_guide_existing_unity_profile_is_ready_and_read_only(self) -> None:
        import scripts.gamestudio_cli as cli
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            self.write_profile(root, draft_project_profile(root))
            before = self.project_tree(root)
            output = io.StringIO()
            with mock.patch.multiple(
                cli,
                apply_install_plan=mock.DEFAULT,
                create_install_plan=mock.DEFAULT,
                apply_scaffold=mock.DEFAULT,
                scaffold_project=mock.DEFAULT,
                uninit_scaffold=mock.DEFAULT,
            ) as mutating_helpers:
                with redirect_stdout(output):
                    exit_code = cli.main([
                        "guide",
                        str(root),
                        "--intent",
                        "diagnose",
                        "--golden-path",
                        "unity-client-entry-recovery",
                    ])
            after = self.project_tree(root)

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("READY", report["status"])
        self.assertEqual("developer", report["role"])
        self.assertEqual("basic", report["mode"])
        self.assertEqual(
            "unity-client-offline-debugging", report["selected_workflow"]
        )
        self.assertEqual(before, after)
        self.assertFalse(
            any(path == ".agents/gamestudio-install.json" for path, _, _ in after)
        )
        for helper in mutating_helpers.values():
            helper.assert_not_called()

    def test_repository_script_entrypoint_uses_local_fallback_imports_without_writes(
        self,
    ) -> None:
        from scripts.project_scaffold import draft_project_profile

        scripts_root = Path(__file__).resolve().parents[2] / "scripts"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            self.write_profile(root, draft_project_profile(root))
            before = self.project_tree(root)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "gamestudio_cli.py",
                    "guide",
                    str(root),
                    "--intent",
                    "diagnose",
                    "--golden-path",
                    "unity-client-entry-recovery",
                ],
                cwd=scripts_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                text=True,
                timeout=20,
                check=False,
            )
            after = self.project_tree(root)

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("READY", report["status"])
        self.assertEqual(
            "unity-client-offline-debugging", report["selected_workflow"]
        )
        self.assertEqual(before, after)
        self.assertFalse(
            any(path == ".agents/gamestudio-install.json" for path, _, _ in after)
        )

    def test_installed_skill_entrypoint_uses_bundled_fallbacks_and_blocks_without_workflow(
        self,
    ) -> None:
        source_skill = (
            Path(__file__).resolve().parents[2]
            / "skills"
            / "studio-project-scaffold"
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        with temporary_directory() as temp:
            temp_root = Path(temp)
            installed_skill = (
                temp_root / "installed" / "skills" / "studio-project-scaffold"
            )
            shutil.copytree(source_skill, installed_skill)
            project_root = temp_root / "project"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            leaked_cwd = temp_root / "cwd"
            leaked_workflow = leaked_cwd / "unity-client-offline-debugging"
            leaked_workflow.mkdir(parents=True)
            (leaked_workflow / "SKILL.md").write_text(
                "# Must not leak into installed discovery\n",
                encoding="utf-8",
            )
            project_before = self.project_tree(project_root)
            install_before = self.project_tree(temp_root / "installed")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    ISOLATED_INSTALLED_CLI_BOOTSTRAP,
                    str(installed_skill / "scripts" / "gamestudio_cli.py"),
                    str(Path(__file__).resolve().parents[2]),
                    "guide",
                    str(project_root),
                    "--intent",
                    "diagnose",
                    "--golden-path",
                    "unity-client-entry-recovery",
                ],
                cwd=leaked_cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                text=True,
                timeout=20,
                check=False,
            )
            project_after = self.project_tree(project_root)
            install_after = self.project_tree(temp_root / "installed")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual("unity-client-entry-recovery", report["golden_path"])
        self.assertIsNone(report["selected_workflow"])
        self.assertEqual(1, len(report["prerequisites"]))
        self.assertIn(
            "unity-client-offline-debugging", report["prerequisites"][0]
        )
        self.assertEqual(project_before, project_after)
        self.assertEqual(install_before, install_after)

    def test_bundled_discovery_lists_only_sibling_skills_with_skill_files(self) -> None:
        import scripts.gamestudio_cli as cli

        with temporary_directory() as temp:
            temp_root = Path(temp)
            catalog_root = temp_root / "installed" / "catalog"
            module_path = (
                catalog_root
                / "studio-project-scaffold"
                / "scripts"
                / "gamestudio_cli.py"
            )
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# bundled module location\n", encoding="utf-8")
            for skill_id in (
                "studio-project-scaffold",
                "unity-client-offline-debugging",
            ):
                skill_root = catalog_root / skill_id
                skill_root.mkdir(exist_ok=True)
                (skill_root / "SKILL.md").write_text(
                    f"# {skill_id}\n",
                    encoding="utf-8",
                )
            (catalog_root / "directory-without-skill-file").mkdir()
            leaked_cwd = temp_root / "cwd"
            leaked_skill = leaked_cwd / "cpp-server-crash-triage"
            leaked_skill.mkdir(parents=True)
            (leaked_skill / "SKILL.md").write_text(
                "# Must not be discovered\n",
                encoding="utf-8",
            )

            discover = getattr(cli, "_discover_available_skills", None)
            self.assertIsNotNone(discover)
            with mock.patch("pathlib.Path.cwd", return_value=leaked_cwd):
                available = discover(module_path=module_path)

        self.assertEqual(
            ("studio-project-scaffold", "unity-client-offline-debugging"),
            available,
        )

    def test_discovery_rejects_catalog_root_link_outside_expected_layout(self) -> None:
        import scripts.gamestudio_cli as cli

        with temporary_directory() as temp:
            temp_root = Path(temp)
            repository_root = temp_root / "repository"
            module_path = repository_root / "scripts" / "gamestudio_cli.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# canonical module location\n", encoding="utf-8")
            plugin_manifest = repository_root / ".codex-plugin" / "plugin.json"
            plugin_manifest.parent.mkdir()
            plugin_manifest.write_text("{}\n", encoding="utf-8")
            external_catalog = temp_root / "external-catalog"
            external_skill = external_catalog / "unity-client-offline-debugging"
            external_skill.mkdir(parents=True)
            (external_skill / "SKILL.md").write_text(
                "# External workflow\n",
                encoding="utf-8",
            )
            catalog_link = repository_root / "skills"
            created_junction = self.create_link_or_skip(
                catalog_link,
                external_catalog,
                target_is_directory=True,
            )

            try:
                available = cli._discover_available_skills(module_path=module_path)
            finally:
                if created_junction and catalog_link.exists():
                    catalog_link.rmdir()

        self.assertEqual((), available)

    def test_discovery_rejects_linked_skill_file(self) -> None:
        import scripts.gamestudio_cli as cli

        with temporary_directory() as temp:
            temp_root = Path(temp)
            catalog_root = temp_root / "installed" / "catalog"
            module_path = (
                catalog_root
                / "studio-project-scaffold"
                / "scripts"
                / "gamestudio_cli.py"
            )
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# bundled module location\n", encoding="utf-8")
            current_skill_file = catalog_root / "studio-project-scaffold" / "SKILL.md"
            current_skill_file.write_text("# Installed scaffold\n", encoding="utf-8")
            linked_skill_root = catalog_root / "unity-client-offline-debugging"
            linked_skill_root.mkdir()
            external_skill_file = temp_root / "external" / "SKILL.md"
            external_skill_file.parent.mkdir()
            external_skill_file.write_text("# External workflow\n", encoding="utf-8")
            self.create_link_or_skip(
                linked_skill_root / "SKILL.md",
                external_skill_file,
                target_is_directory=False,
            )

            available = cli._discover_available_skills(module_path=module_path)

        self.assertEqual(("studio-project-scaffold",), available)

    def test_guide_profile_with_absent_enabled_intents_uses_planner_default(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            profile = draft_project_profile(root)
            del profile["studio_experience"]["enabled_intents"]
            self.write_profile(root, profile)
            before = self.project_tree(root)
            output = io.StringIO()
            errors = io.StringIO()

            with redirect_stdout(output), redirect_stderr(errors):
                try:
                    exit_code = main([
                        "guide",
                        str(root),
                        "--intent",
                        "diagnose",
                        "--golden-path",
                        "unity-client-entry-recovery",
                    ])
                except SystemExit as error:
                    exit_code = error.code
            after = self.project_tree(root)

        self.assertEqual(0, exit_code, errors.getvalue())
        report = json.loads(output.getvalue())
        self.assertEqual("READY", report["status"])
        self.assertEqual(
            "unity-client-offline-debugging", report["selected_workflow"]
        )
        self.assertEqual(before, after)

    def test_guide_ambiguous_server_cpp_profile_does_not_prompt_or_write(self) -> None:
        import scripts.gamestudio_cli as cli
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            profile = draft_project_profile(root)
            profile["repositories"][0]["subsystems"] = ["server", "cpp"]
            self.write_profile(root, profile)
            before = self.project_tree(root)
            output = io.StringIO()
            with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
                with redirect_stdout(output):
                    exit_code = cli.main([
                        "guide", str(root), "--intent", "diagnose",
                    ])
            after = self.project_tree(root)

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("AMBIGUOUS", report["status"])
        self.assertEqual(1, len(report["questions"]))
        self.assertEqual(before, after)

    def test_guide_disabled_intent_is_concise_cli_error_without_writes(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            profile = draft_project_profile(root)
            profile["studio_experience"]["enabled_intents"] = ["verify"]
            self.write_profile(root, profile)
            before = self.project_tree(root)
            output = io.StringIO()
            errors = io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                with self.assertRaises(SystemExit) as context:
                    main(["guide", str(root), "--intent", "diagnose"])
            after = self.project_tree(root)

        self.assertEqual(2, context.exception.code)
        self.assertEqual("", output.getvalue())
        self.assertIn(
            "studio intent is not enabled: diagnose", errors.getvalue()
        )
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertEqual(before, after)

    def test_guide_malformed_yaml_is_concise_cli_error_without_writes(self) -> None:
        from scripts.gamestudio_cli import main

        with temporary_directory() as temp:
            root = Path(temp)
            profile_path = root / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("workspace: [\n", encoding="utf-8")
            before = self.project_tree(root)
            output = io.StringIO()
            errors = io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                with self.assertRaises(SystemExit) as context:
                    main(["guide", str(root), "--intent", "diagnose"])
            after = self.project_tree(root)

        self.assertEqual(2, context.exception.code)
        self.assertEqual("", output.getvalue())
        self.assertIn("guide failed:", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertEqual(before, after)

    def test_guide_explicit_role_and_mode_override_profile_defaults(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            profile = draft_project_profile(root)
            profile["studio_experience"]["default_role"] = "producer"
            profile["studio_experience"]["preferred_mode"] = "basic"
            self.write_profile(root, profile)
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "guide",
                    str(root),
                    "--role",
                    "qa",
                    "--intent",
                    "diagnose",
                    "--mode",
                    "advanced",
                    "--golden-path",
                    "unity-client-entry-recovery",
                ])

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("qa", report["role"])
        self.assertEqual("advanced", report["mode"])

    def test_guide_missing_profile_uses_draft_without_mutating_tree(self) -> None:
        from scripts.gamestudio_cli import main

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            sentinel = root / "README.md"
            sentinel.write_text("local project\n", encoding="utf-8")
            before = self.project_tree(root)
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "guide", str(root), "--intent", "diagnose",
                ])
            after = self.project_tree(root)

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("READY", report["status"])
        self.assertEqual("unity-client-offline-debugging", report["selected_workflow"])
        self.assertEqual(before, after)

    def test_guide_blocked_report_returns_zero_without_executing_workflow(self) -> None:
        import scripts.gamestudio_cli as cli
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            self.write_profile(root, draft_project_profile(root))
            output = io.StringIO()
            with mock.patch.multiple(
                cli,
                apply_install_plan=mock.DEFAULT,
                create_install_plan=mock.DEFAULT,
                apply_scaffold=mock.DEFAULT,
                scaffold_project=mock.DEFAULT,
                uninit_scaffold=mock.DEFAULT,
            ) as mutating_helpers:
                with redirect_stdout(output):
                    exit_code = cli.main([
                        "guide", str(root), "--intent", "ship",
                    ])

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertIsNone(report["selected_workflow"])
        for helper in mutating_helpers.values():
            helper.assert_not_called()

    def test_codegraph_report_only_does_not_require_root_argument(self) -> None:
        from scripts.gamestudio_cli import main

        with temporary_directory() as temp:
            plan_path = Path(temp) / "plan.json"
            plan_path.write_text(
                json.dumps({"kind": "CODEGRAPH_INSTALL", "actions": []}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["codegraph", str(plan_path)])

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("REPORT_ONLY", report["status"])
        self.assertEqual("CODEGRAPH_INSTALL", report["codegraph_install_plan"]["kind"])

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

    def test_init_apply_forwards_approved_plan_digest(self) -> None:
        import scripts.gamestudio_cli as cli

        with temporary_directory() as temp:
            root = Path(temp)
            backup_root = root / ".backup"
            with mock.patch.object(
                cli,
                "apply_scaffold",
                return_value={"status": "PASS"},
            ) as apply_scaffold:
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = cli.main([
                        "init",
                        str(root),
                        "--apply",
                        "--reviewer",
                        "Tech Lead",
                        "--backup-root",
                        str(backup_root),
                        "--plan-digest",
                        "approved-digest",
                        "--codegraph",
                        "disabled",
                    ])

            self.assertEqual(0, exit_code)
            self.assertEqual("PASS", json.loads(output.getvalue())["status"])
            apply_scaffold.assert_called_once_with(
                root,
                reviewer="Tech Lead",
                backup_root=backup_root,
                approved_plan_digest="approved-digest",
                codegraph_preference="never_suggest",
            )

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
