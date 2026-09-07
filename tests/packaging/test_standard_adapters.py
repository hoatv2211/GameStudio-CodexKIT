from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.packaging.packs_adapters_support import (
    PackagingTestCase,
    apply_reviewed_project_adapter,
    temporary_directory,
    tree_digest,
)


class StandardAdapterTests(PackagingTestCase):
    def test_standard_adapter_rejects_output_nested_in_skill_source_before_mutation(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = skill / "generated"
            before = tree_digest(skill)

            with self.assertRaisesRegex(ValueError, "overlaps"):
                generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(skill))
            self.assertFalse(output.exists())

    def test_standard_adapter_rejects_unsafe_capability_id_before_mutation(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: ../../escaped\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = temp_root / "adapter"
            escaped = temp_root / "escaped"

            with self.assertRaisesRegex(ValueError, "unsafe capability id"):
                generate_adapter(root, "hermes", output)

            self.assertFalse(output.exists())
            self.assertFalse(escaped.exists())

    def test_standard_adapter_rejects_capability_path_outside_skills(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            outside = root / "outside" / "demo"
            outside.mkdir(parents=True)
            (outside / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: outside/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"

            with self.assertRaisesRegex(ValueError, "canonical skills"):
                generate_adapter(root, "hermes", output)

            self.assertFalse(output.exists())

    def test_standard_adapter_rejects_output_alias_without_touching_external_target(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external-adapter"
            generate_adapter(root, "hermes", external)
            before = tree_digest(external)
            alias = temp_root / "adapter-alias"
            if os.name == "nt":
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(external)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    self.skipTest(
                        f"junction creation unavailable: {completed.stderr or completed.stdout}"
                    )
            else:
                try:
                    alias.symlink_to(external, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"symlink creation unavailable: {error}")
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "symlink or reparse point"):
                generate_adapter(root, "hermes", alias)

            self.assertEqual(before, tree_digest(external))
            self.assertTrue(os.path.lexists(alias))

    def test_standard_adapter_rejects_output_in_unselected_canonical_skills_sibling(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            skills_root = root / "skills"
            before = tree_digest(skills_root)

            with self.assertRaisesRegex(ValueError, "canonical skills"):
                generate_adapter(root, "hermes", skills_root / "generated-adapter")

            self.assertEqual(before, tree_digest(skills_root))

    def test_standard_adapter_source_swap_after_walk_never_packages_external_content(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            resources = skill / "resources"
            resources.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (resources / "note.txt").write_text("trusted source\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            backup = skill / "resources.original"
            output = temp_root / "adapter"
            original_walk = adapters._walk_adapter_files
            swapped = False

            def swap_after_walk(path: Path, **kwargs: object) -> object:
                nonlocal swapped
                walked = original_walk(path, **kwargs)
                if path == skill and kwargs.get("ignore_runtime_cache") and not swapped:
                    resources.rename(backup)
                    self.create_directory_alias(resources, external)
                    swapped = True
                return walked

            try:
                with mock.patch.object(
                    adapters,
                    "_walk_adapter_files",
                    side_effect=swap_after_walk,
                ):
                    adapters.generate_adapter(root, "hermes", output)
            finally:
                if os.path.lexists(resources) and swapped:
                    self.remove_directory_alias(resources)
                if backup.exists():
                    backup.rename(resources)

            generated = (
                output / "skills" / "demo" / "resources" / "note.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("trusted source", generated)
            self.assertNotIn("external payload", generated)

    def test_standard_adapter_rejects_nested_directory_replaced_after_parent_scan(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            nested = skill / "resources"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (nested / "note.txt").write_text("trusted source\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            external_before = tree_digest(external)
            backup = skill / "resources.original"
            output = temp_root / "adapter"
            original_scandir = adapters.os.scandir
            swapped = False

            class SwapOnDirectoryCheck:
                def __init__(self, entry: os.DirEntry[str]) -> None:
                    self._entry = entry

                def __getattr__(self, name: str) -> object:
                    return getattr(self._entry, name)

                def is_dir(self, *, follow_symlinks: bool = True) -> bool:
                    nonlocal swapped
                    result = self._entry.is_dir(follow_symlinks=follow_symlinks)
                    if Path(self._entry.path) == nested and result and not swapped:
                        nested.rename(backup)
                        self_outer.create_directory_alias(nested, external)
                        swapped = True
                    return result

            self_outer = self

            def scanning(path: str | os.PathLike[str]) -> object:
                entries = list(original_scandir(path))
                if Path(path) == skill:
                    return iter(SwapOnDirectoryCheck(entry) for entry in entries)
                return iter(entries)

            try:
                with mock.patch.object(adapters.os, "scandir", side_effect=scanning):
                    with self.assertRaisesRegex(ValueError, "reparse point|changed"):
                        adapters.generate_adapter(root, "hermes", output)
            finally:
                if os.path.lexists(nested) and swapped:
                    self.remove_directory_alias(nested)
                if backup.exists():
                    backup.rename(nested)

            self.assertFalse(output.exists())
            self.assertEqual(external_before, tree_digest(external))

    def test_standard_adapter_rejects_directory_replaced_inside_scandir(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            nested = skill / "resources"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (nested / "note.txt").write_text("trusted source\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            external_before = tree_digest(external)
            backup = skill / "resources.original"
            output = temp_root / "adapter"
            original_scandir = adapters.os.scandir
            swapped = False

            def swap_inside_scan(path: str | os.PathLike[str]) -> object:
                nonlocal swapped
                if Path(path) == nested and not swapped:
                    nested.rename(backup)
                    self.create_directory_alias(nested, external)
                    swapped = True
                return original_scandir(path)

            try:
                with mock.patch.object(adapters.os, "scandir", side_effect=swap_inside_scan):
                    with self.assertRaisesRegex(ValueError, "reparse point|changed"):
                        adapters.generate_adapter(root, "hermes", output)
            finally:
                if os.path.lexists(nested) and swapped:
                    self.remove_directory_alias(nested)
                if backup.exists():
                    backup.rename(nested)

            self.assertFalse(output.exists())
            self.assertEqual(external_before, tree_digest(external))

    def test_standard_adapter_render_failure_preserves_previous_output(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            before_siblings = sorted(path.name for path in output.parent.iterdir())
            (skill / "unsupported.bin").write_bytes(b"unsupported\n")

            with self.assertRaisesRegex(ValueError, "unsupported skill resource"):
                generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertEqual(
                before_siblings,
                sorted(path.name for path in output.parent.iterdir()),
            )

    def test_standard_adapter_swap_failure_restores_previous_output(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_stage_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            recovery = json.loads(
                (output.parent / ".adapter.swap-recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(recovery["stage"]).is_dir())

    def test_standard_adapter_publication_journal_exists_before_stage_rename(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            original_rename = adapters._rename_standard_directory
            journal_seen = False

            def observe_before_publish(source: Path, target: Path) -> Path:
                nonlocal journal_seen
                if source.name.endswith(".stage"):
                    journal_seen = (output.parent / ".adapter.swap-recovery.json").is_file()
                    raise OSError("stop at publication boundary")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=observe_before_publish,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertTrue(journal_seen)

    def test_standard_adapter_recovery_journal_tracks_prepared_and_output_moved_states(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            recovery_path = output.parent / ".adapter.swap-recovery.json"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            original_rename = adapters._rename_standard_directory
            observed_states: list[str] = []

            def observe_transition(source: Path, target: Path) -> Path:
                if source == output or source.name.endswith(".stage"):
                    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
                    observed_states.append(recovery["state"])
                if source.name.endswith(".stage"):
                    raise OSError("stop after output move")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=observe_transition,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(["prepared", "output-moved"], observed_states)

    def test_standard_adapter_prejournal_failure_keeps_output_visible_without_rename(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            rename_calls = 0

            def count_rename(source: Path, target: Path) -> Path:
                nonlocal rename_calls
                rename_calls += 1
                return target

            with mock.patch.object(
                adapters,
                "_write_standard_recovery",
                side_effect=OSError("injected prejournal failure"),
            ), mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=count_rename,
            ):
                with self.assertRaisesRegex(OSError, "injected prejournal failure"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(0, rename_calls)
            self.assertEqual(before, tree_digest(output))
            self.assertEqual(1, len(list(output.parent.glob(".adapter.*.stage"))))

    def test_standard_adapter_first_swap_rename_failure_preserves_previous_output(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory

            def fail_old_output_rename(source: Path, target: Path) -> Path:
                if source == output:
                    raise OSError("injected old-output rename failure")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_old_output_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            recovery = json.loads(
                (output.parent / ".adapter.swap-recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(recovery["stage"]).is_dir())

    def test_standard_adapter_concurrent_edit_before_old_output_rename_is_restored_visible(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            generated_skill = output / "skills" / "demo" / "SKILL.md"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# New staged content\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            injected = False

            def edit_before_rename(source: Path, target: Path) -> Path:
                nonlocal injected
                if source == output and not injected:
                    generated_skill.write_text(
                        generated_skill.read_text(encoding="utf-8")
                        + "\n# concurrent user edit\n",
                        encoding="utf-8",
                    )
                    injected = True
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=edit_before_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery|changed"):
                    adapters.generate_adapter(root, "hermes", output)

            visible = generated_skill.read_text(encoding="utf-8")
            self.assertIn("# Demo", visible)
            self.assertIn("concurrent user edit", visible)
            self.assertNotIn("New staged content", visible)
            self.assertEqual(1, len(list(output.parent.glob(".adapter.*.stage"))))
            self.assertTrue((output.parent / ".adapter.swap-recovery.json").is_file())

    def test_standard_adapter_cleanup_preserves_concurrent_stage_replacement(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            original_validate = adapters._validate_standard_temp
            foreign_path: Path | None = None

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            def replace_before_validation(
                path: Path,
                output_path: Path,
                suffix: str,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal foreign_path
                if suffix == "stage" and foreign_path is None:
                    shutil.rmtree(path)
                    path.mkdir()
                    foreign_path = path / "foreign.txt"
                    foreign_path.write_text("concurrent owner\n", encoding="utf-8")
                original_validate(path, output_path, suffix, *args, **kwargs)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_stage_rename,
            ), mock.patch.object(
                adapters,
                "_validate_standard_temp",
                side_effect=replace_before_validation,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertIsNotNone(foreign_path)
            assert foreign_path is not None
            self.assertEqual("concurrent owner\n", foreign_path.read_text(encoding="utf-8"))

    def test_standard_adapter_failure_cleanup_preserves_snapshot_boundary_replacement(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            original_snapshot = adapters._standard_tree_snapshot
            stage_snapshot_count = 0
            foreign_path: Path | None = None

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            def replace_after_snapshot(path: Path):
                nonlocal stage_snapshot_count, foreign_path
                snapshot = original_snapshot(path)
                if path.name.endswith(".stage"):
                    stage_snapshot_count += 1
                    if stage_snapshot_count == 2:
                        shutil.rmtree(path)
                        path.mkdir()
                        foreign_path = path / "foreign.txt"
                        foreign_path.write_text("snapshot-boundary owner\n", encoding="utf-8")
                return snapshot

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_stage_rename,
            ), mock.patch.object(
                adapters,
                "_standard_tree_snapshot",
                side_effect=replace_after_snapshot,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertIsNotNone(foreign_path)
            assert foreign_path is not None
            self.assertEqual(
                "snapshot-boundary owner\n",
                foreign_path.read_text(encoding="utf-8"),
            )
            recovery_path = output.parent / ".adapter.swap-recovery.json"
            self.assertTrue(recovery_path.is_file())

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                adapters.generate_adapter(root, "hermes", output)
            self.assertEqual(
                "snapshot-boundary owner\n",
                foreign_path.read_text(encoding="utf-8"),
            )

    def test_standard_adapter_publish_no_clobber_preserves_concurrent_output_and_stage(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            foreign_file = output / "foreign.txt"
            injected = False

            def create_concurrent_output(source: Path, target: Path) -> Path:
                nonlocal injected
                if source.name.endswith(".stage") and target == output and not injected:
                    output.mkdir()
                    foreign_file.write_text("concurrent output\n", encoding="utf-8")
                    injected = True
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=create_concurrent_output,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual("concurrent output\n", foreign_file.read_text(encoding="utf-8"))
            recovery_path = output.parent / ".adapter.swap-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertTrue(Path(recovery["stage"]).is_dir())
            self.assertTrue(Path(recovery["rollback"]).is_dir())

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                adapters.generate_adapter(root, "hermes", output)
            self.assertEqual("concurrent output\n", foreign_file.read_text(encoding="utf-8"))

    def test_standard_adapter_success_preserves_hash_bound_completion_without_duplicate_retry(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            adapters.generate_adapter(root, "hermes", output)

            completion_paths = list(
                output.parent.glob(".adapter.*.swap-completion.json")
            )
            self.assertEqual(1, len(completion_paths))
            completion = json.loads(completion_paths[0].read_text(encoding="utf-8"))
            self.assertEqual("adapter-output-swap-completion", completion["kind"])
            self.assertEqual("published", completion["status"])
            self.assertTrue(Path(completion["rollback"]).is_dir())
            before_siblings = sorted(path.name for path in output.parent.iterdir())

            adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(
                before_siblings,
                sorted(path.name for path in output.parent.iterdir()),
            )

    def test_standard_adapter_double_swap_failure_persists_and_resumes_recovery(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            initial_recovery_count = len(
                list(output.parent.glob(".adapter.*.swap-recovery.json"))
            )
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory

            def fail_publish_and_restore(source: Path, target: Path) -> Path:
                if source.name.endswith((".stage", ".rollback")):
                    raise OSError("injected double rename failure")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_publish_and_restore,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            recovery_path = output.parent / ".adapter.swap-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertEqual(str(output), recovery["output"])
            rollback = Path(recovery["rollback"])
            stage = Path(recovery["stage"])
            self.assertTrue(rollback.is_dir())
            self.assertTrue(stage.is_dir())
            self.assertFalse(output.exists())

            with mock.patch.object(
                adapters,
                "_generated_resource",
                side_effect=ValueError("stop after recovery"),
            ):
                with self.assertRaisesRegex(ValueError, "stop after recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertFalse(recovery_path.exists())
            self.assertFalse(rollback.exists())
            self.assertTrue(stage.is_dir())
            self.assertEqual(
                initial_recovery_count + 1,
                len(list(output.parent.glob(".adapter.*.swap-recovery.json"))),
            )

    def test_standard_adapter_regeneration_refuses_and_preserves_unmanaged_empty_directory(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            generate_adapter(root, "hermes", output)
            unmanaged = output / "local-empty"
            unmanaged.mkdir()
            before = tree_digest(output)

            with self.assertRaisesRegex(RuntimeError, "unmanaged.*directory"):
                generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertTrue(unmanaged.is_dir())

    def test_standard_adapters_are_generated_on_demand_and_ignored(self) -> None:
        from scripts.generate_adapters import generate_adapter

        source_root = Path(__file__).resolve().parents[2]
        ignore_entries = {
            line.strip()
            for line in (source_root / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("adapters/", ignore_entries)
        source_file_count = len(
            [
                path
                for path in (source_root / "skills").rglob("*")
                if path.is_file()
                and path.suffix.casefold() != ".pyc"
                and "__pycache__" not in path.parts
            ]
        )
        with temporary_directory() as temp:
            for target in ("hermes", "codex"):
                adapter = Path(temp) / target
                generate_adapter(source_root, target, adapter)
                files = [path for path in adapter.rglob("*") if path.is_file()]
                self.assertEqual(source_file_count + 1, len(files), target)
                registry = json.loads((adapter / "registry.json").read_text(encoding="utf-8"))
                self.assertEqual(52, len(registry["skills"]), target)
                first_digest = tree_digest(adapter)
                generate_adapter(source_root, target, adapter)
                self.assertEqual(first_digest, tree_digest(adapter), target)


if __name__ == "__main__":
    unittest.main()
