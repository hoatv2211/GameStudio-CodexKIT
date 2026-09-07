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


class ProjectAdapterUninstallTests(PackagingTestCase):
    def test_project_adapter_uninstall_tracks_nested_resources_and_preserves_drift(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )
            helper = project / ".agents" / "skills" / "studio-project-scaffold" / "scripts" / "project_scaffold.py"
            helper.write_text(helper.read_text(encoding="utf-8") + "# local note\n", encoding="utf-8")

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(helper.is_file())
            self.assertEqual("PARTIAL", report["status"])
            self.assertIn(
                ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py",
                report["preserved_drift"],
            )
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            remaining = {item["path"] for item in registry["kit_adapter"]["files"]}
            self.assertIn(
                ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py",
                remaining,
            )

    def test_project_adapter_uninstall_preserves_drifted_stale_owned_resource(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            source_root = temp_root / "source"
            skill_root = source_root / "skills" / "sample-skill"
            (source_root / "registry").mkdir(parents=True)
            (skill_root / "scripts").mkdir(parents=True)
            (source_root / "registry" / "capabilities.yaml").write_text(
                "schema_version: 1\n"
                "capabilities:\n"
                "- id: sample-skill\n"
                "  path: skills/sample-skill/SKILL.md\n",
                encoding="utf-8",
            )
            (skill_root / "SKILL.md").write_text("---\nname: sample-skill\n---\n", encoding="utf-8")
            stale_source = skill_root / "scripts" / "stale.py"
            stale_source.write_text("print('stale')\n", encoding="utf-8")
            project = temp_root / "project"
            backup_root = project / ".adapter-backup"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=backup_root,
            )
            stale_relative = ".agents/skills/sample-skill/scripts/stale.py"
            stale_target = project / stale_relative
            stale_source.unlink()
            stale_target.write_text(
                stale_target.read_text(encoding="utf-8") + "# local note\n",
                encoding="utf-8",
            )

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup-2",
            )
            report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(report)
            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(stale_target.is_file())
            self.assertIn(stale_relative, report["preserved_drift"])
            self.assertIn(stale_relative, {item["path"] for item in report["remaining_owned"]})

    def test_project_adapter_uninstall_is_atomic_when_manifest_entry_is_malformed(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        malformed_entries = [
            None,
            {},
            {"path": 123, "sha256": "0" * 64},
            {"path": ".agents/skills/bad/SKILL.md"},
            {"path": ".agents/skills/bad/SKILL.md", "sha256": 123},
            {"path": ".agents/skills/bad/SKILL.md", "sha256": "not-a-sha256"},
            {"path": ".agents/skills/bad/../../escape", "sha256": "0" * 64},
        ]
        with temporary_directory() as temp:
            temp_root = Path(temp)
            for index, malformed in enumerate(malformed_entries):
                with self.subTest(malformed=malformed):
                    project = temp_root / f"project-{index}"
                    owned_relative = ".agents/skills/valid/SKILL.md"
                    owned = project / owned_relative
                    owned.parent.mkdir(parents=True)
                    owned.write_text("owned\n", encoding="utf-8")
                    valid = {
                        "path": owned_relative,
                        "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
                    }
                    registry_path = project / ".agents" / "registry.json"
                    registry = {
                        "schema_version": 1,
                        "skills": ["valid"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [valid, malformed],
                        },
                    }
                    registry_path.write_text(
                        json.dumps(registry, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    before_registry = registry_path.read_bytes()
                    before_owned = owned.read_bytes()

                    report = uninstall_project_adapter(project)

                    self.assert_uninstall_report_disjoint(report)

                    self.assert_recovery_journal_truthful(project, report)

                    self.assertEqual(
                        {"status", "removed", "preserved_drift", "remaining_owned"},
                        set(report),
                    )
                    self.assertEqual("PARTIAL", report["status"])
                    self.assertEqual([], report["removed"])
                    self.assertEqual([valid, malformed], report["remaining_owned"])
                    self.assertEqual(before_owned, owned.read_bytes())
                    self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_preserves_unknown_adapter_version(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/future/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("future-owned\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry = {
                "schema_version": 1,
                "skills": ["future"],
                "kit_adapter": {
                    "adapter_id": "GameStudio-CodexKIT/per-project/v3",
                    "files": [ownership],
                },
            }
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            before_registry = registry_path.read_bytes()

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual(
                {"status", "removed", "preserved_drift", "remaining_owned"},
                set(report),
            )
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertTrue(owned.is_file())
            self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_cleanup_leaves_unmanaged_empty_directories(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/owned/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned\n", encoding="utf-8")
            unmanaged_empty = project / ".agents" / "skills" / "local-empty" / "nested"
            unmanaged_empty.mkdir(parents=True)
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["owned"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [
                                {
                                    "path": owned_relative,
                                    "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
                                }
                            ],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual(
                {"status", "removed", "preserved_drift", "remaining_owned"},
                set(report),
            )
            self.assertEqual("PASS", report["status"])
            self.assertEqual([], report["remaining_owned"])
            self.assertTrue(unmanaged_empty.is_dir())
            self.assertFalse(owned.exists())

    def test_project_adapter_uninstall_skill_membership_requires_complete_removal(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            partial_skill = project / ".agents" / "skills" / "partial"
            full_skill = project / ".agents" / "skills" / "full"
            partial_skill.mkdir(parents=True)
            full_skill.mkdir(parents=True)
            partial_removed = partial_skill / "SKILL.md"
            partial_remaining = partial_skill / "scripts" / "helper.py"
            partial_remaining.parent.mkdir(parents=True)
            full_removed = full_skill / "SKILL.md"
            partial_removed.write_text("owned partial\n", encoding="utf-8")
            partial_remaining.write_text("owned helper\nlocal drift\n", encoding="utf-8")
            full_removed.write_text("owned full\n", encoding="utf-8")
            ownership = [
                {
                    "path": ".agents/skills/partial/SKILL.md",
                    "sha256": hashlib.sha256(partial_removed.read_bytes()).hexdigest(),
                },
                {
                    "path": ".agents/skills/partial/scripts/helper.py",
                    "sha256": hashlib.sha256(b"owned helper\n").hexdigest(),
                },
                {
                    "path": ".agents/skills/full/SKILL.md",
                    "sha256": hashlib.sha256(full_removed.read_bytes()).hexdigest(),
                },
            ]
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["partial", "full"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": ownership,
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual(
                {"status", "removed", "preserved_drift", "remaining_owned"},
                set(report),
            )
            self.assertEqual("PARTIAL", report["status"])
            self.assertNotIn("partial", report)
            self.assertIn("full", report)
            self.assertFalse(partial_removed.exists())
            self.assertTrue(partial_remaining.is_file())
            self.assertFalse(full_removed.exists())

    @unittest.skipUnless(os.name == "nt", "Windows path alias semantics")
    def test_project_adapter_uninstall_rejects_windows_destination_aliases_atomically(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned = project / ".agents" / "skills" / "Mixed" / "SKILL.md"
            owned.parent.mkdir(parents=True)
            owned.write_text("owned alias\n", encoding="utf-8")
            digest = hashlib.sha256(owned.read_bytes()).hexdigest()
            ownership = [
                {"path": ".agents/skills/Mixed/SKILL.md", "sha256": digest},
                {"path": ".agents/skills/mixed/SKILL.md", "sha256": digest},
            ]
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["Mixed"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": ownership,
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            before_owned = owned.read_bytes()

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual(ownership, report["remaining_owned"])
            self.assertEqual(before_owned, owned.read_bytes())
            self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_preserves_concurrent_hash_replacement(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/race/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned before race\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["race"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_replace = Path.replace
            raced = False

            def racing_replace(path: Path, target: Path) -> Path:
                nonlocal raced
                if path == owned and not raced:
                    raced = True
                    path.write_text("concurrent replacement\n", encoding="utf-8")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=racing_replace):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(raced)
            self.assertEqual("concurrent replacement\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertIn(owned_relative, report["preserved_drift"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_cleans_owned_quarantine_on_rollback_conflict(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/conflict/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned conflict\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["conflict"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_replace = Path.replace
            conflicted = False
            mapped_before_raise = False

            def conflicting_replace(path: Path, target: Path) -> Path:
                nonlocal conflicted, mapped_before_raise
                if path == owned and not conflicted:
                    conflicted = True
                    result = original_replace(path, target)
                    mapped_before_raise = (target.parent / "recovery.json").is_file()
                    path.write_text("concurrent destination\n", encoding="utf-8")
                    raise OSError("simulated post-move failure")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=conflicting_replace):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(conflicted)
            self.assertTrue(mapped_before_raise)
            self.assertEqual("concurrent destination\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    def test_project_adapter_uninstall_keyboard_interrupt_leaves_predeclared_recoverable_journal(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/interrupt/SKILL.md"
            second_relative = ".agents/skills/interrupt/scripts/helper.py"
            owned = project / owned_relative
            second = project / second_relative
            second.parent.mkdir(parents=True)
            owned.write_text("owned interrupt\n", encoding="utf-8")
            second.write_text("owned helper\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            second_ownership = {
                "path": second_relative,
                "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["interrupt"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership, second_ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_replace = Path.replace
            interrupted = False

            def interrupting_replace(path: Path, target: Path) -> Path:
                nonlocal interrupted
                if path == owned and not interrupted:
                    interrupted = True
                    result = original_replace(path, target)
                    raise KeyboardInterrupt("simulated crash after first move")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=interrupting_replace):
                with self.assertRaises(KeyboardInterrupt):
                    uninstall_project_adapter(project)

            self.assertTrue(interrupted)
            self.assertFalse(owned.exists())
            quarantine_roots = list(
                (project / ".agents").glob(".adapter-uninstall-quarantine-*")
            )
            self.assertEqual(1, len(quarantine_roots))
            recovery_path = quarantine_roots[0] / "recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertTrue(recovery["transaction_id"])
            self.assertEqual("prepared", recovery["state"])
            self.assertEqual(2, len(recovery["files"]))
            self.assertEqual(owned_relative, recovery["files"][0]["path"])
            self.assertEqual(ownership["sha256"], recovery["files"][0]["sha256"])
            self.assertEqual(second_relative, recovery["files"][1]["path"])
            self.assertEqual(second_ownership["sha256"], recovery["files"][1]["sha256"])
            quarantined = project / recovery["files"][0]["quarantine_path"]
            second_quarantine = project / recovery["files"][1]["quarantine_path"]
            self.assertTrue(quarantined.is_file())
            self.assertFalse(second_quarantine.exists())
            self.assertEqual("owned helper\n", second.read_text(encoding="utf-8"))

            with mock.patch(
                "scripts.generate_adapters._write_registry_atomically",
                side_effect=OSError("stop after stale recovery"),
            ):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("owned interrupt\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("owned helper\n", second.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([ownership, second_ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertNotIn("recovery_manifest", report)
            self.assertNotIn("recovery_owned", report)
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_project_adapter_uninstall_rejects_junction_stale_quarantine_without_traversal(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            project = temp_root / "project"
            agents_root = project / ".agents"
            agents_root.mkdir(parents=True)
            registry_path = agents_root / "registry.json"
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            transaction_id = "externaljunction"
            quarantine_name = f".adapter-uninstall-quarantine-{transaction_id}"
            junction = agents_root / quarantine_name
            external = temp_root / "external-recovery"
            external.mkdir()
            external_owned = external / "00000000.owned"
            external_owned.write_bytes(b"external owned bytes\n")
            external_recovery = external / "recovery.json"
            external_recovery.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "registry_committed",
                        "files": [
                            {
                                "path": ".agents/skills/external/SKILL.md",
                                "quarantine_path": (
                                    f".agents/{quarantine_name}/00000000.owned"
                                ),
                                "sha256": hashlib.sha256(
                                    external_owned.read_bytes()
                                ).hexdigest(),
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_owned = external_owned.read_bytes()
            before_recovery = external_recovery.read_bytes()
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                self.skipTest(
                    f"junction creation unavailable: {completed.stderr or completed.stdout}"
                )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(junction.relative_to(project).as_posix(), report["unsafe_recovery"])
            self.assertNotIn("recovery_manifest", report)
            self.assertNotIn("recovery_owned", report)
            self.assertTrue(os.path.lexists(junction))
            self.assertEqual(before_owned, external_owned.read_bytes())
            self.assertEqual(before_recovery, external_recovery.read_bytes())

    def test_project_adapter_uninstall_removes_empty_journal_less_quarantine_root(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            agents_root = project / ".agents"
            agents_root.mkdir(parents=True)
            registry_path = agents_root / "registry.json"
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            orphan = agents_root / ".adapter-uninstall-quarantine-emptyorphan"
            orphan.mkdir()

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(first_report)
            self.assert_recovery_journal_truthful(project, first_report)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PASS", first_report["status"])
            self.assertFalse(os.path.lexists(orphan))
            self.assertNotIn("recovery_manifest", first_report)
            self.assertNotIn("unsafe_recovery", first_report)
            self.assertEqual("PASS", second_report["status"])
            self.assertNotIn("recovery_manifest", second_report)
            self.assertNotIn("unsafe_recovery", second_report)

    def test_project_adapter_uninstall_preserves_nonempty_journal_less_quarantine_root(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            agents_root = project / ".agents"
            agents_root.mkdir(parents=True)
            registry_path = agents_root / "registry.json"
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            orphan = agents_root / ".adapter-uninstall-quarantine-nonemptyorphan"
            orphan.mkdir()
            unknown = orphan / "unknown.bin"
            unknown.write_bytes(b"unknown recovery bytes\n")
            before = unknown.read_bytes()
            unsafe_relative = orphan.relative_to(project).as_posix()

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(first_report)
            self.assert_recovery_journal_truthful(project, first_report)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            for report in (first_report, second_report):
                self.assertEqual("PARTIAL", report["status"])
                self.assertEqual(unsafe_relative, report["unsafe_recovery"])
                self.assertNotIn("recovery_manifest", report)
                self.assertNotIn("recovery_owned", report)
            self.assertTrue(os.path.lexists(orphan))
            self.assertEqual(before, unknown.read_bytes())

    def test_project_adapter_uninstall_stale_journal_preserves_concurrent_destination(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/stale-concurrent/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("concurrent destination\n", encoding="utf-8")
            expected_content = b"owned stale journal\n"
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(expected_content).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["stale-concurrent"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            transaction_id = "staleconcurrent"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir()
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            recovery_relative = recovery_path.relative_to(project).as_posix()
            quarantine_relative = quarantined.relative_to(project).as_posix()
            recovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantine_relative,
                                "sha256": ownership["sha256"],
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("concurrent destination\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual(
                [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership["sha256"],
                    }
                ],
                report["recovery_owned"],
            )
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertTrue(quarantined.is_file())
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertNotIn("stale-concurrent", report)

    def test_project_adapter_uninstall_stale_journal_without_registry_requires_manual_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/missing-registry/SKILL.md"
            expected_content = b"owned missing registry\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "missingregistry"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            quarantine_relative = quarantined.relative_to(project).as_posix()
            recovery_relative = recovery_path.relative_to(project).as_posix()
            recovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantine_relative,
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual(
                [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership_hash,
                    }
                ],
                report["recovery_owned"],
            )
            self.assertTrue(quarantined.is_file())

    def test_project_adapter_uninstall_registry_failure_restores_quarantined_target(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/registry-failure/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned registry failure\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["registry-failure"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()

            with mock.patch(
                "scripts.generate_adapters._write_registry_atomically",
                side_effect=OSError("simulated registry commit failure"),
            ):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("owned registry failure\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    def test_project_adapter_uninstall_cleanup_failure_preserves_durable_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/cleanup-failure/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned cleanup\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["cleanup-failure"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_unlink = Path.unlink
            cleanup_failed = False

            def failing_unlink(path: Path, *args: object, **kwargs: object) -> None:
                nonlocal cleanup_failed
                if (
                    path.parent.name.startswith(".adapter-uninstall-quarantine-")
                    and path.suffix == ".owned"
                ):
                    cleanup_failed = True
                    raise OSError("simulated quarantine cleanup failure")
                original_unlink(path, *args, **kwargs)

            with mock.patch.object(Path, "unlink", new=failing_unlink):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(cleanup_failed)
            self.assertFalse(owned.exists())
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([], report["remaining_owned"])
            self.assertNotEqual(before_registry, registry_path.read_bytes())
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertNotIn("kit_adapter", registry)
            quarantine_roots = list(
                (project / ".agents").glob(".adapter-uninstall-quarantine-*")
            )
            self.assertEqual(1, len(quarantine_roots))
            recovery_path = quarantine_roots[0] / "recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            recovery_relative = recovery_path.relative_to(project).as_posix()
            quarantine_relative = recovery["files"][0]["quarantine_path"]
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual(
                [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership["sha256"],
                    }
                ],
                report["recovery_owned"],
            )
            self.assertEqual("GameStudio-CodexKIT/per-project/v2", recovery["adapter_id"])
            self.assertEqual(1, recovery["schema_version"])
            self.assertEqual(owned_relative, recovery["files"][0]["path"])
            self.assertEqual(ownership["sha256"], recovery["files"][0]["sha256"])
            quarantined = project / quarantine_relative
            self.assertTrue(quarantined.is_file())
            self.assertEqual(ownership["sha256"], hashlib.sha256(quarantined.read_bytes()).hexdigest())

    def test_project_adapter_uninstall_deduplicates_root_and_durable_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/duplicate-recovery/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned duplicate recovery\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["duplicate-recovery"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            original_unlink = Path.unlink
            unlink_failed = False

            def deny_canonical_replacement(path: Path, target: Path) -> Path:
                if target.name == "recovery.json" and target.exists():
                    raise PermissionError(13, "simulated recovery replace denial")
                return original_replace(path, target)

            def fail_one_internal_generation_unlink(
                path: Path, *args: object, **kwargs: object
            ) -> None:
                nonlocal unlink_failed
                if (
                    not unlink_failed
                    and path.parent.name.startswith(".adapter-uninstall-quarantine-")
                    and path.name.startswith("recovery.")
                    and path.name != "recovery.json"
                    and path.name.endswith(".json")
                ):
                    unlink_failed = True
                    raise OSError("simulated internal recovery generation unlink failure")
                original_unlink(path, *args, **kwargs)

            with mock.patch.object(
                Path, "replace", new=deny_canonical_replacement
            ), mock.patch.object(
                Path, "unlink", new=fail_one_internal_generation_unlink
            ):
                first_report = uninstall_project_adapter(project)

            self.assertTrue(unlink_failed)
            self.assertEqual("PARTIAL", first_report["status"])
            first_manifest = project / first_report["recovery_manifest"]
            self.assertTrue(first_manifest.is_file())
            quarantine_roots = [
                path
                for path in (project / ".agents").glob(
                    ".adapter-uninstall-quarantine-*"
                )
                if path.is_dir()
            ]
            durable_siblings = list(
                (project / ".agents").glob(
                    ".adapter-uninstall-quarantine-*.recovery.json"
                )
            )
            self.assertEqual(1, len(quarantine_roots))
            self.assertEqual(1, len(durable_siblings))
            self.assertGreaterEqual(
                len(list(quarantine_roots[0].glob("recovery.*.json"))),
                1,
            )

            second_report = uninstall_project_adapter(project)

            self.assertEqual("PASS", second_report["status"])
            self.assertNotIn("recovery_manifest", second_report)
            self.assertNotIn("unsafe_recovery", second_report)
            self.assertEqual(
                [],
                list(
                    (project / ".agents").glob(
                        ".adapter-uninstall-quarantine-*"
                    )
                ),
            )

            third_report = uninstall_project_adapter(project)

            self.assertEqual("PASS", third_report["status"])
            self.assertEqual([], third_report["removed"])
            self.assertNotIn("recovery_manifest", third_report)
            self.assertNotIn("unsafe_recovery", third_report)

    def test_project_adapter_uninstall_reports_newer_invalid_durable_sibling(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/newer-invalid-sibling/SKILL.md"
            expected_content = b"owned newer invalid sibling\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "newerinvalidsibling"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            quarantine_relative = quarantined.relative_to(project).as_posix()
            base_recovery = {
                "schema_version": 1,
                "transaction_id": transaction_id,
                "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                "state": "prepared",
                "files": [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership_hash,
                        "state": "moved",
                    }
                ],
            }
            recovery_path.write_text(
                json.dumps(
                    {
                        **base_recovery,
                        "revision": 2,
                        "generation": 2,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            durable = quarantine_root.with_name(
                f"{quarantine_root.name}.recovery.json"
            )
            durable_payload = {
                **base_recovery,
                "revision": 999,
                "generation": 999,
                "files": [
                    {
                        **base_recovery["files"][0],
                        "state": "removed",
                        "artifact_present": False,
                    }
                ],
            }
            durable_bytes = (
                json.dumps(durable_payload, indent=2) + "\n"
            ).encode("utf-8")
            durable.write_bytes(durable_bytes)

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)

            for report in (first_report, second_report):
                self.assertEqual("PARTIAL", report["status"])
                self.assertEqual(
                    recovery_path.relative_to(project).as_posix(),
                    report["recovery_manifest"],
                )
                self.assertEqual(
                    durable.relative_to(project).as_posix(),
                    report["unsafe_recovery"],
                )
                self.assertEqual(
                    [
                        {
                            "path": owned_relative,
                            "quarantine_path": quarantine_relative,
                            "sha256": ownership_hash,
                        }
                    ],
                    report["recovery_owned"],
                )
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(durable_bytes, durable.read_bytes())

    def test_project_adapter_uninstall_reports_malformed_durable_sibling_once(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/malformed-sibling/SKILL.md"
            expected_content = b"owned malformed sibling\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "malformedsibling"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            recovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 2,
                        "generation": 2,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantined.relative_to(project).as_posix(),
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            durable = quarantine_root.with_name(
                f"{quarantine_root.name}.recovery.json"
            )
            malformed_bytes = b'{"schema_version": 1, "revision":'
            durable.write_bytes(malformed_bytes)

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)

            for report in (first_report, second_report):
                self.assertEqual("PARTIAL", report["status"])
                self.assertEqual(
                    recovery_path.relative_to(project).as_posix(),
                    report["recovery_manifest"],
                )
                self.assertEqual(
                    durable.relative_to(project).as_posix(),
                    report["unsafe_recovery"],
                )
                self.assertEqual(
                    [owned_relative],
                    [item["path"] for item in report["recovery_owned"]],
                )
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(malformed_bytes, durable.read_bytes())

    def test_project_adapter_uninstall_root_cleanup_failure_preserves_durable_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/root-cleanup/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned root cleanup\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["root-cleanup"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_rmdir = Path.rmdir

            def failing_rmdir(path: Path) -> None:
                if path.name.startswith(".adapter-uninstall-quarantine-"):
                    raise OSError("simulated quarantine root cleanup failure")
                original_rmdir(path)

            with mock.patch.object(Path, "rmdir", new=failing_rmdir):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertFalse(owned.exists())
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([owned_relative], report["removed"])
            self.assertEqual([], report["preserved_drift"])
            self.assertEqual([], report["remaining_owned"])
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertNotIn("kit_adapter", registry)
            recovery_paths = list(
                (project / ".agents").glob(
                    ".adapter-uninstall-quarantine-*.recovery.json"
                )
            )
            self.assertEqual(1, len(recovery_paths))
            recovery_relative = recovery_paths[0].relative_to(project).as_posix()
            recovery = json.loads(recovery_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual([], report["recovery_owned"])
            self.assertEqual(owned_relative, recovery["files"][0]["path"])
            self.assertEqual(ownership["sha256"], recovery["files"][0]["sha256"])
            self.assertEqual("removed", recovery["files"][0]["state"])
            quarantined = project / recovery["files"][0]["quarantine_path"]
            self.assertFalse(os.path.lexists(quarantined))

            second_report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PASS", second_report["status"])
            self.assertEqual([], second_report["removed"])
            self.assertNotIn("recovery_manifest", second_report)
            self.assertFalse(recovery_paths[0].exists())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    def test_project_adapter_uninstall_survives_windows_recovery_replace_denial(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/replace-denial/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned replace denial\n", encoding="utf-8")
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["replace-denial"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [
                                {
                                    "path": owned_relative,
                                    "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
                                }
                            ],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            denied = False

            def deny_existing_recovery_replace(path: Path, target: Path) -> Path:
                nonlocal denied
                if target.name == "recovery.json" and target.exists():
                    denied = True
                    raise PermissionError(13, "simulated Windows recovery replace denial")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=deny_existing_recovery_replace):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(denied)
            self.assertEqual("PASS", report["status"])
            self.assertEqual([owned_relative], report["removed"])
            self.assertFalse(owned.exists())
            self.assertNotIn("recovery_manifest", report)

    def test_project_adapter_uninstall_replace_denial_interruption_keeps_old_journal(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/interrupted-generation/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned interrupted generation\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["interrupted-generation"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            interrupted = False

            def interrupt_generation_publish(path: Path, target: Path) -> Path:
                nonlocal interrupted
                if target.name == "recovery.json" and target.exists():
                    raise PermissionError(13, "simulated recovery replace denial")
                if (
                    target.name != "recovery.json"
                    and target.name.startswith("recovery.")
                    and target.name.endswith(".json")
                ):
                    interrupted = True
                    target.write_bytes(b'{"partial":')
                    raise OSError("simulated interrupted generation publication")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=interrupt_generation_publish):
                first_report = adapters.uninstall_project_adapter(project)

            self.assertTrue(interrupted)
            quarantine_root = next(
                (project / ".agents").glob(".adapter-uninstall-quarantine-*")
            )
            canonical = quarantine_root / "recovery.json"
            canonical_payload = json.loads(canonical.read_text(encoding="utf-8"))
            self.assertEqual("prepared", canonical_payload["state"])
            self.assertEqual("PARTIAL", first_report["status"])
            self.assertEqual(
                canonical.relative_to(project).as_posix(),
                first_report["recovery_manifest"],
            )

            second_report = adapters.uninstall_project_adapter(project)

            self.assertEqual("PARTIAL", second_report["status"])
            self.assertEqual(
                canonical.relative_to(project).as_posix(),
                second_report["recovery_manifest"],
            )
            self.assertEqual(
                [owned_relative],
                [item["path"] for item in second_report["recovery_owned"]],
            )
            self.assertIn("unsafe_recovery", second_report)
            self.assertEqual(canonical_payload, json.loads(canonical.read_text(encoding="utf-8")))

    def test_project_adapter_uninstall_selects_newer_recovery_generation(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/newer-generation/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned newer generation\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["newer-generation"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            original_write = adapters._write_registry_atomically

            def deny_canonical_replace(path: Path, target: Path) -> Path:
                if target.name == "recovery.json" and target.exists():
                    raise PermissionError(13, "simulated recovery replace denial")
                return original_replace(path, target)

            def drift_after_commit(path: Path, registry: dict[str, object]) -> None:
                original_write(path, registry)
                quarantine_root = next(
                    (project / ".agents").glob(".adapter-uninstall-quarantine-*")
                )
                next(quarantine_root.glob("*.owned")).write_bytes(b"drifted generation\n")

            with mock.patch.object(Path, "replace", new=deny_canonical_replace), mock.patch.object(
                adapters,
                "_write_registry_atomically",
                side_effect=drift_after_commit,
            ):
                first_report = adapters.uninstall_project_adapter(project)

            selected = project / first_report["recovery_manifest"]
            selected_payload = json.loads(selected.read_text(encoding="utf-8"))
            self.assertRegex(selected.name, r"^recovery\.\d{8}\.json$")
            self.assertGreater(selected_payload["revision"], 0)
            self.assertEqual("drifted", selected_payload["files"][0]["state"])

            second_report = adapters.uninstall_project_adapter(project)

            self.assertEqual(first_report["recovery_manifest"], second_report["recovery_manifest"])
            self.assertEqual([owned_relative], second_report["preserved_drift"])

    def test_project_adapter_uninstall_invalid_newer_generation_keeps_valid_visibility(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/invalid-generation/SKILL.md"
            expected_content = b"owned invalid generation\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "invalidgeneration"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            canonical = quarantine_root / "recovery.json"
            canonical.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 0,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantined.relative_to(project).as_posix(),
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            invalid = quarantine_root / "recovery.99999999.json"
            invalid_bytes = b'{"schema_version": 1, "revision": 99999999'
            invalid.write_bytes(invalid_bytes)

            report = uninstall_project_adapter(project)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(canonical.relative_to(project).as_posix(), report["recovery_manifest"])
            self.assertEqual(invalid.relative_to(project).as_posix(), report["unsafe_recovery"])
            self.assertEqual(
                [owned_relative],
                [item["path"] for item in report["recovery_owned"]],
            )
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(invalid_bytes, invalid.read_bytes())

    def test_project_adapter_uninstall_structurally_invalid_older_generation_stays_unsafe(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/invalid-older-generation/SKILL.md"
            expected_content = b"owned invalid older generation\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "invalidoldergeneration"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            canonical = quarantine_root / "recovery.json"
            canonical.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 1,
                        "generation": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantined.relative_to(project).as_posix(),
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            invalid = quarantine_root / "recovery.00000000.json"
            invalid_bytes = (
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 0,
                        "generation": 0,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [{"path": owned_relative}],
                    },
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
            invalid.write_bytes(invalid_bytes)

            report = uninstall_project_adapter(project)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(canonical.relative_to(project).as_posix(), report["recovery_manifest"])
            self.assertEqual(invalid.relative_to(project).as_posix(), report["unsafe_recovery"])
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(invalid_bytes, invalid.read_bytes())

    def test_recovery_journal_writer_has_no_in_place_overwrite_fallback(self) -> None:
        import inspect
        from scripts import generate_adapters as adapters

        source = inspect.getsource(adapters._write_quarantine_recovery_manifest)

        self.assertNotIn('open("r+"', source)
        self.assertNotIn(".truncate()", source)

    def test_project_adapter_uninstall_records_missing_quarantine_after_registry_commit(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/missing-quarantine/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned missing quarantine\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["missing-quarantine"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_write = adapters._write_registry_atomically

            def delete_quarantine_after_commit(
                path: Path, registry: dict[str, object]
            ) -> None:
                original_write(path, registry)
                quarantine_root = next(
                    (project / ".agents").glob(".adapter-uninstall-quarantine-*")
                )
                next(quarantine_root.glob("*.owned")).unlink()

            with mock.patch.object(
                adapters,
                "_write_registry_atomically",
                side_effect=delete_quarantine_after_commit,
            ):
                report = adapters.uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([owned_relative], report["preserved_drift"])
            recovery_path = project / report["recovery_manifest"]
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertEqual("missing", recovery["files"][0]["state"])
            self.assertFalse(
                os.path.lexists(project / recovery["files"][0]["quarantine_path"])
            )

            second_report = adapters.uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PARTIAL", second_report["status"])
            self.assertEqual([], second_report["removed"])
            self.assertEqual([owned_relative], second_report["preserved_drift"])
            self.assertEqual(report["recovery_manifest"], second_report["recovery_manifest"])
            self.assertTrue(recovery_path.is_file())

    def test_project_adapter_uninstall_records_drifted_quarantine_after_registry_commit(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/drifted-quarantine/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned drifted quarantine\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["drifted-quarantine"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            drifted_bytes = b"concurrent quarantine replacement\n"
            original_write = adapters._write_registry_atomically

            def drift_quarantine_after_commit(
                path: Path, registry: dict[str, object]
            ) -> None:
                original_write(path, registry)
                quarantine_root = next(
                    (project / ".agents").glob(".adapter-uninstall-quarantine-*")
                )
                next(quarantine_root.glob("*.owned")).write_bytes(drifted_bytes)

            with mock.patch.object(
                adapters,
                "_write_registry_atomically",
                side_effect=drift_quarantine_after_commit,
            ):
                report = adapters.uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([owned_relative], report["preserved_drift"])
            recovery_path = project / report["recovery_manifest"]
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            record = recovery["files"][0]
            self.assertEqual("drifted", record["state"])
            self.assertEqual(
                hashlib.sha256(drifted_bytes).hexdigest(),
                record["observed_sha256"],
            )
            quarantined = project / record["quarantine_path"]
            self.assertEqual(drifted_bytes, quarantined.read_bytes())

            second_report = adapters.uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PARTIAL", second_report["status"])
            self.assertEqual([], second_report["removed"])
            self.assertEqual([owned_relative], second_report["preserved_drift"])
            self.assertEqual(report["recovery_manifest"], second_report["recovery_manifest"])
            self.assertEqual(drifted_bytes, quarantined.read_bytes())

    def test_project_adapter_uninstall_success_omits_recovery_fields_and_residue(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/success/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned success\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["success"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PASS", report["status"])
            self.assertEqual([owned_relative], report["removed"])
            self.assertNotIn("recovery_manifest", report)
            self.assertNotIn("recovery_owned", report)
            self.assertFalse(owned.exists())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-*")),
            )

    def test_project_adapter_uninstall_preserves_broken_owned_link(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/linked/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            try:
                os.symlink("missing-target", owned)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            ownership = {"path": owned_relative, "sha256": "0" * 64}
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["linked"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(os.path.lexists(owned))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertIn(owned_relative, report["preserved_drift"])
            self.assertEqual([ownership], report["remaining_owned"])

    def test_project_adapter_uninstall_rejects_registry_path_traversal(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )
            protected = project / "important.txt"
            protected.write_text("keep me\n", encoding="utf-8")
            registry_path = project / ".agents" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            malicious = {
                "path": ".agents/skills/fake/../../../important.txt",
                "sha256": hashlib.sha256(protected.read_bytes()).hexdigest(),
            }
            registry["kit_adapter"]["files"].append(malicious)
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

            uninstall_project_adapter(project)

            self.assertTrue(protected.is_file())
            remaining = json.loads(registry_path.read_text(encoding="utf-8"))["kit_adapter"]["files"]
            self.assertIn(malicious, remaining)


if __name__ == "__main__":
    unittest.main()
