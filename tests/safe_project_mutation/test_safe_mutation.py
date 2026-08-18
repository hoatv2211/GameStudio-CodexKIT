from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from tests._meta.support import temporary_directory


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SafeMutationTests(unittest.TestCase):
    def test_report_mode_does_not_mutate_and_apply_is_restorable(self) -> None:
        from scripts.safe_mutation import apply_mutation, report_mutation, restore_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            before = digest(target)
            operations = [
                {"path": "config.txt", "content": "after\n"},
                {"path": "created.txt", "content": "new\n"},
            ]
            report = report_mutation(root, operations)
            self.assertEqual("report-only", report["mode"])
            self.assertEqual(before, digest(target))
            self.assertFalse((root / "created.txt").exists())

            manifest_path = apply_mutation(root, operations, root / ".backup")
            self.assertEqual("after\n", target.read_text(encoding="utf-8"))
            self.assertTrue((root / "created.txt").exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue((root / ".backup" / "files" / "config.txt").exists())

            restore_mutation(manifest_path, root)
            self.assertEqual(before, digest(target))
            self.assertFalse((root / "created.txt").exists())
            restored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("restored", restored_manifest["mode"])
            self.assertFalse((root / ".backup" / "restore-progress.json").exists())
            self.assertFalse((root / ".backup" / "restore-quarantine").exists())

    def test_restore_preserves_create_target_changed_after_preflight(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            created = root / "created.txt"
            manifest_path = safe_mutation.apply_mutation(
                root,
                [{"path": "created.txt", "content": "applied\n"}],
                root / ".backup",
            )
            applied_hash = digest(created)
            real_sha256_path = safe_mutation._sha256_path
            drifted = False

            def drift_after_verified_hash(path: Path) -> str | None:
                nonlocal drifted
                result = real_sha256_path(path)
                if Path(path) == created and result == applied_hash and not drifted:
                    drifted = True
                    created.write_text("concurrent-owner\n", encoding="utf-8")
                return result

            with mock.patch.object(
                safe_mutation,
                "_sha256_path",
                side_effect=drift_after_verified_hash,
            ):
                with self.assertRaisesRegex(RuntimeError, "drifted"):
                    safe_mutation.restore_mutation(manifest_path, root)

            self.assertTrue(drifted)
            self.assertEqual("concurrent-owner\n", created.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("applied", manifest["mode"])

    def test_restore_failure_rolls_back_completed_operations(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [
                    {"path": "first.txt", "content": "first-applied\n"},
                    {"path": "second.txt", "content": "second-applied\n"},
                ],
                root / ".backup",
            )
            real_copy = safe_mutation.shutil.copy2
            restore_copies = 0

            def fail_second_restore_copy(source: object, destination: object) -> object:
                nonlocal restore_copies
                if Path(source).is_relative_to(root / ".backup" / "files"):
                    restore_copies += 1
                    if restore_copies == 2:
                        raise OSError("injected second restore failure")
                return real_copy(source, destination)

            with mock.patch.object(
                safe_mutation.shutil,
                "copy2",
                side_effect=fail_second_restore_copy,
            ):
                with self.assertRaisesRegex(OSError, "second restore failure"):
                    safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("first-applied\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-applied\n", second.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("applied", manifest["mode"])
            self.assertFalse((root / ".backup" / "restore-progress.json").exists())
            self.assertFalse((root / ".backup" / "restore-quarantine").exists())

    def test_restore_resumes_after_interruption_between_rollback_and_cleanup(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [
                    {"path": "first.txt", "content": "first-applied\n"},
                    {"path": "second.txt", "content": "second-applied\n"},
                ],
                root / ".backup",
            )
            real_copy = safe_mutation.shutil.copy2
            restore_copies = 0

            def fail_second_restore_copy(source: object, destination: object) -> object:
                nonlocal restore_copies
                if Path(source).is_relative_to(root / ".backup" / "files"):
                    restore_copies += 1
                    if restore_copies == 2:
                        raise OSError("injected second restore failure")
                return real_copy(source, destination)

            with (
                mock.patch.object(
                    safe_mutation.shutil,
                    "copy2",
                    side_effect=fail_second_restore_copy,
                ),
                mock.patch.object(
                    safe_mutation,
                    "_cleanup_restore_artifacts",
                    side_effect=KeyboardInterrupt("injected rollback cleanup interruption"),
                ),
            ):
                with self.assertRaisesRegex(KeyboardInterrupt, "cleanup interruption"):
                    safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("first-applied\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-applied\n", second.read_text(encoding="utf-8"))
            interrupted_progress = json.loads(
                (root / ".backup" / "restore-progress.json").read_text(encoding="utf-8")
            )
            self.assertEqual("rolling-back", interrupted_progress["mode"])

            safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("first-before\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-before\n", second.read_text(encoding="utf-8"))
            self.assertEqual(
                "restored",
                json.loads(manifest_path.read_text(encoding="utf-8"))["mode"],
            )
            self.assertFalse((root / ".backup" / "restore-progress.json").exists())

    def test_restore_recovers_create_drift_moved_during_atomic_quarantine(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            created = root / "created.txt"
            manifest_path = safe_mutation.apply_mutation(
                root,
                [{"path": "created.txt", "content": "applied\n"}],
                root / ".backup",
            )
            real_rename = safe_mutation.os.rename
            raced = False

            def drift_during_quarantine(source: object, destination: object) -> None:
                nonlocal raced
                if Path(source) == created and str(destination).endswith(".applied"):
                    raced = True
                    created.write_text("concurrent-owner\n", encoding="utf-8")
                real_rename(source, destination)

            with mock.patch.object(
                safe_mutation.os,
                "rename",
                side_effect=drift_during_quarantine,
            ):
                with self.assertRaisesRegex(RuntimeError, "drifted"):
                    safe_mutation.restore_mutation(manifest_path, root)

            self.assertTrue(raced)
            self.assertEqual("concurrent-owner\n", created.read_text(encoding="utf-8"))
            self.assertFalse((root / ".backup" / "restore-progress.json").exists())
            self.assertFalse((root / ".backup" / "restore-quarantine").exists())

    def test_restore_can_resume_owned_interrupted_progress(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [
                    {"path": "first.txt", "content": "first-applied\n"},
                    {"path": "second.txt", "content": "second-applied\n"},
                ],
                root / ".backup",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            backup_root = root / ".backup"
            progress_path = backup_root / "restore-progress.json"
            quarantine = backup_root / "restore-quarantine" / "0000.applied"
            quarantine.parent.mkdir()
            second.replace(quarantine)
            second.write_bytes((backup_root / "files" / "second.txt").read_bytes())
            progress_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operation_id": manifest["operation_id"],
                        "manifest_digest": safe_mutation._ownership_digest(manifest),
                        "mode": "restoring",
                        "completed": [0],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("first-before\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-before\n", second.read_text(encoding="utf-8"))
            restored = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("restored", restored["mode"])
            self.assertFalse(progress_path.exists())
            self.assertFalse(quarantine.parent.exists())
            journal = safe_mutation._trusted_journal_path(root, manifest["operation_id"])
            self.assertFalse(journal.exists())

    def test_restore_resumes_owned_interrupted_rollback_staging(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [{"path": "target.txt", "content": "applied\n"}],
                root / ".backup",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            backup_root = root / ".backup"
            quarantine_root = backup_root / "restore-quarantine"
            quarantine_root.mkdir()
            target.replace(quarantine_root / "0000.applied")
            target.write_bytes((backup_root / "files" / "target.txt").read_bytes())
            target.replace(quarantine_root / "0000.restored")
            (backup_root / "restore-progress.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operation_id": manifest["operation_id"],
                        "manifest_digest": safe_mutation._ownership_digest(manifest),
                        "mode": "restoring",
                        "completed": [0],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertEqual(
                "restored",
                json.loads(manifest_path.read_text(encoding="utf-8"))["mode"],
            )
            self.assertFalse(quarantine_root.exists())

    def test_restore_rejects_progress_not_owned_by_the_trusted_manifest(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [{"path": "target.txt", "content": "applied\n"}],
                root / ".backup",
            )
            progress_path = root / ".backup" / "restore-progress.json"
            progress_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operation_id": "another-operation",
                        "manifest_digest": "0" * 64,
                        "mode": "restoring",
                        "completed": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "progress"):
                safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("applied\n", target.read_text(encoding="utf-8"))
            self.assertTrue(progress_path.is_file())

    def test_restore_rejects_completed_progress_without_matching_quarantine(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [{"path": "target.txt", "content": "applied\n"}],
                root / ".backup",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            progress_path = root / ".backup" / "restore-progress.json"
            progress_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operation_id": manifest["operation_id"],
                        "manifest_digest": safe_mutation._ownership_digest(manifest),
                        "mode": "restoring",
                        "completed": [0],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "completed restore progress"):
                safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("applied\n", target.read_text(encoding="utf-8"))

    def test_restore_rollback_failure_records_exact_manual_recovery_evidence(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [
                    {"path": "first.txt", "content": "first-applied\n"},
                    {"path": "second.txt", "content": "second-applied\n"},
                ],
                root / ".backup",
            )
            real_copy = safe_mutation.shutil.copy2
            restore_copies = 0

            def drift_completed_then_fail(source: object, destination: object) -> object:
                nonlocal restore_copies
                if Path(source).is_relative_to(root / ".backup" / "files"):
                    restore_copies += 1
                    if restore_copies == 2:
                        second.write_text("second-concurrent\n", encoding="utf-8")
                        raise OSError("injected restore failure")
                return real_copy(source, destination)

            with mock.patch.object(
                safe_mutation.shutil,
                "copy2",
                side_effect=drift_completed_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("first-applied\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-concurrent\n", second.read_text(encoding="utf-8"))
            progress = json.loads(
                (root / ".backup" / "restore-progress.json").read_text(encoding="utf-8")
            )
            self.assertEqual("restore-incomplete-manual-recovery", progress["mode"])
            recovery_path = root / ".backup" / "restore-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            evidence = "\n".join(recovery["issues"])
            self.assertIn(str(second), evidence)
            self.assertIn("0000.applied", evidence)
            self.assertIn(digest(second), evidence)

    def test_restore_refuses_to_overwrite_post_apply_drift(self) -> None:
        from scripts.safe_mutation import apply_mutation, restore_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = apply_mutation(
                root,
                [{"path": "config.txt", "content": "after\n"}],
                root / ".backup",
            )
            target.write_text("changed-by-another-owner\n", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                restore_mutation(manifest_path, root)
            self.assertEqual("changed-by-another-owner\n", target.read_text(encoding="utf-8"))

    def test_completed_restore_can_be_retried_after_trusted_journal_cleanup(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [
                    {"path": "target.txt", "content": "applied\n"},
                    {"path": "created.txt", "content": "created\n"},
                ],
                root / ".backup",
            )
            operation_id = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )["operation_id"]

            safe_mutation.restore_mutation(manifest_path, root)
            journal = safe_mutation._trusted_journal_path(root, operation_id)
            self.assertFalse(journal.exists())
            completion = safe_mutation._trusted_completion_path(root, operation_id)
            self.assertTrue(completion.is_file())

            safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertFalse((root / "created.txt").exists())
            self.assertEqual(
                "restored",
                json.loads(manifest_path.read_text(encoding="utf-8"))["mode"],
            )

    def test_completed_restore_retry_rejects_final_target_drift(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = safe_mutation.apply_mutation(
                root,
                [{"path": "target.txt", "content": "applied\n"}],
                root / ".backup",
            )
            safe_mutation.restore_mutation(manifest_path, root)
            target.write_text("post-restore-concurrent\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "restored manifest target state"):
                safe_mutation.restore_mutation(manifest_path, root)

            self.assertEqual("post-restore-concurrent\n", target.read_text(encoding="utf-8"))

    def test_no_clobber_preserves_destination_created_at_atomic_boundary(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            destination = root / "destination.txt"
            source.write_text("owned-source\n", encoding="utf-8")

            def inject_atomic_collision(source_path: object, destination_path: object) -> None:
                Path(destination_path).write_text("concurrent-owner\n", encoding="utf-8")
                raise FileExistsError("injected atomic destination collision")

            with mock.patch.object(
                safe_mutation,
                "_atomic_rename_no_replace",
                side_effect=inject_atomic_collision,
                create=True,
            ):
                with self.assertRaisesRegex(FileExistsError, "destination collision"):
                    safe_mutation._rename_no_clobber(
                        root,
                        source,
                        destination,
                        expected_source_sha256=digest(source),
                    )

            self.assertEqual("owned-source\n", source.read_text(encoding="utf-8"))
            self.assertEqual("concurrent-owner\n", destination.read_text(encoding="utf-8"))

    def test_no_clobber_fails_closed_without_native_no_replace_primitive(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            destination = root / "destination.txt"
            source.write_text("owned-source\n", encoding="utf-8")

            with (
                mock.patch.object(safe_mutation.os, "name", "posix"),
                mock.patch.object(safe_mutation.sys, "platform", "freebsd"),
            ):
                with self.assertRaisesRegex(RuntimeError, "no atomic no-replace"):
                    safe_mutation._atomic_rename_no_replace(source, destination)

            self.assertEqual("owned-source\n", source.read_text(encoding="utf-8"))
            self.assertFalse(destination.exists())

    def test_restore_rejects_manifest_for_another_approved_root(self) -> None:
        from scripts.safe_mutation import apply_mutation, restore_mutation

        with temporary_directory() as temp:
            workspace = Path(temp)
            actual_root = workspace / "actual"
            approved_root = workspace / "approved"
            actual_root.mkdir()
            approved_root.mkdir()
            target = actual_root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = apply_mutation(
                actual_root,
                [{"path": "config.txt", "content": "after\n"}],
                actual_root / ".backup",
            )

            with self.assertRaises(ValueError):
                restore_mutation(manifest_path, approved_root)
            self.assertEqual("after\n", target.read_text(encoding="utf-8"))

    def test_restore_rejects_malformed_or_relocated_manifest(self) -> None:
        from scripts.safe_mutation import apply_mutation, restore_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            manifest_path = apply_mutation(
                root,
                [{"path": "config.txt", "content": "after\n"}],
                root / ".backup",
            )
            relocated = root / "relocated.json"
            relocated.write_bytes(manifest_path.read_bytes())
            with self.assertRaises(ValueError):
                restore_mutation(relocated, root)

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["unexpected"] = True
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                restore_mutation(manifest_path, root)
            self.assertEqual("after\n", target.read_text(encoding="utf-8"))

    def test_restore_rejects_forged_manifest_and_matching_sidecar_without_trusted_journal(self) -> None:
        from scripts.safe_mutation import _ownership_digest, restore_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            victim = root / "victim.txt"
            victim.write_text("keep\n", encoding="utf-8")
            backup_root = root / ".forged-backup"
            backup_root.mkdir()
            forged = {
                "schema_version": 1,
                "mode": "applied",
                "operation_id": "forged-operation",
                "root": str(root.resolve()),
                "backup_root": str(backup_root.resolve()),
                "operations": [
                    {
                        "path": "victim.txt",
                        "action": "create",
                        "before_sha256": None,
                        "after_sha256": digest(victim),
                        "backup": None,
                        "restore": "remove created file",
                    }
                ],
            }
            manifest_path = backup_root / "manifest.json"
            manifest_path.write_text(json.dumps(forged), encoding="utf-8")
            (backup_root / "ownership.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operation_id": forged["operation_id"],
                        "manifest_digest": _ownership_digest(forged),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                restore_mutation(manifest_path, root)
            self.assertEqual("keep\n", victim.read_text(encoding="utf-8"))

    def test_restore_rejects_forged_restored_manifest_without_trusted_completion(self) -> None:
        from scripts.safe_mutation import _ownership_digest, restore_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            victim = root / "victim.txt"
            victim.write_text("keep\n", encoding="utf-8")
            backup_root = root / ".forged-restored-backup"
            backup_root.mkdir()
            forged = {
                "schema_version": 1,
                "mode": "restored",
                "operation_id": "forged-restored-operation",
                "root": str(root.resolve()),
                "backup_root": str(backup_root.resolve()),
                "operations": [
                    {
                        "path": "victim.txt",
                        "action": "update",
                        "before_sha256": digest(victim),
                        "after_sha256": "0" * 64,
                        "backup": "files/victim.txt",
                        "restore": "copy backup",
                    }
                ],
            }
            manifest_path = backup_root / "manifest.json"
            manifest_path.write_text(json.dumps(forged), encoding="utf-8")
            (backup_root / "ownership.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operation_id": forged["operation_id"],
                        "manifest_digest": _ownership_digest(forged),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "trusted completion"):
                restore_mutation(manifest_path, root)

            self.assertEqual("keep\n", victim.read_text(encoding="utf-8"))

    def test_apply_rolls_back_when_a_later_atomic_replace_fails(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            real_replace = safe_mutation.os.replace
            calls = 0

            def fail_second_replace(source: object, destination: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected replace failure")
                real_replace(source, destination)

            with mock.patch.object(safe_mutation.os, "replace", side_effect=fail_second_replace):
                with self.assertRaises(OSError):
                    safe_mutation.apply_mutation(
                        root,
                        [
                            {"path": "first.txt", "content": "first-after\n"},
                            {"path": "second.txt", "content": "second-after\n"},
                        ],
                        root / ".backup",
                    )

            self.assertEqual("first-before\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-before\n", second.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rolled-back", manifest["mode"])

    def test_apply_retries_a_transient_permission_error_during_atomic_replace(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            real_replace = safe_mutation.os.replace
            calls = 0

            def transient_permission_error(source: object, destination: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError(13, "simulated transient replace contention")
                real_replace(source, destination)

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=transient_permission_error,
            ):
                try:
                    manifest_path = safe_mutation.apply_mutation(
                        root,
                        [{"path": "config.txt", "content": "after\n"}],
                        root / ".backup",
                    )
                except PermissionError as error:
                    self.fail(f"transient replace contention was not retried: {error}")

            self.assertEqual(2, calls)
            self.assertEqual("after\n", target.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("applied", manifest["mode"])

    def test_apply_refuses_update_drift_during_atomic_replace_retry(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            real_replace = safe_mutation.os.replace
            calls = 0

            def concurrent_update(source: object, destination: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    target.write_text("concurrent-owner\n", encoding="utf-8")
                    raise PermissionError(13, "simulated transient replace contention")
                real_replace(source, destination)

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=concurrent_update,
            ):
                with self.assertRaisesRegex(ValueError, "target pre-state changed"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "config.txt", "content": "after\n"}],
                        root / ".backup",
                    )

            self.assertEqual(1, calls)
            self.assertEqual("concurrent-owner\n", target.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rolled-back", manifest["mode"])

    def test_apply_refuses_create_drift_during_atomic_replace_retry(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "created.txt"
            real_replace = safe_mutation.os.replace
            calls = 0

            def concurrent_create(source: object, destination: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    target.write_text("concurrent-owner\n", encoding="utf-8")
                    raise PermissionError(13, "simulated transient replace contention")
                real_replace(source, destination)

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=concurrent_create,
            ):
                with self.assertRaisesRegex(ValueError, "target pre-state changed"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "created.txt", "content": "after\n"}],
                        root / ".backup",
                    )

            self.assertEqual(1, calls)
            self.assertEqual("concurrent-owner\n", target.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rolled-back", manifest["mode"])

    def test_apply_retries_transient_manifest_replace_contention(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            real_replace = safe_mutation._ATOMIC_REPLACE
            failed_applied_write = False

            def transient_manifest_contention(source: object, destination: object) -> None:
                nonlocal failed_applied_write
                payload = json.loads(Path(source).read_text(encoding="utf-8"))
                if payload.get("mode") == "applied" and not failed_applied_write:
                    failed_applied_write = True
                    raise PermissionError(13, "simulated transient manifest contention")
                real_replace(source, destination)

            with mock.patch.object(
                safe_mutation,
                "_ATOMIC_REPLACE",
                side_effect=transient_manifest_contention,
            ):
                manifest_path = safe_mutation.apply_mutation(
                    root,
                    [{"path": "config.txt", "content": "after\n"}],
                    root / ".backup",
                )

            self.assertTrue(failed_applied_write)
            self.assertEqual("after\n", target.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("applied", manifest["mode"])

    def test_apply_rejects_stale_approved_operations_before_backup_artifacts(self) -> None:
        from scripts.safe_mutation import apply_mutation, report_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "config.txt"
            target.write_text("before\n", encoding="utf-8")
            operations = [{"path": "config.txt", "content": "after\n"}]
            approved = report_mutation(root, operations)["operations"]
            target.write_text("raced\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "approved mutation precondition"):
                apply_mutation(
                    root,
                    operations,
                    root / ".backup",
                    expected_operations=approved,
                )

            self.assertEqual("raced\n", target.read_text(encoding="utf-8"))
            self.assertFalse((root / ".backup").exists())

    def test_apply_rolls_back_when_later_target_changes_after_earlier_write(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            operations = [
                {"path": "first.txt", "content": "first-after\n"},
                {"path": "second.txt", "content": "second-after\n"},
            ]
            approved = safe_mutation.report_mutation(root, operations)["operations"]
            real_replace = safe_mutation.os.replace

            def race_second_after_first(source: object, destination: object) -> None:
                real_replace(source, destination)
                if Path(destination) == first:
                    second.write_text("second-raced\n", encoding="utf-8")

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=race_second_after_first,
            ):
                with self.assertRaisesRegex(ValueError, "target pre-state changed"):
                    safe_mutation.apply_mutation(
                        root,
                        operations,
                        root / ".backup",
                        expected_operations=approved,
                    )

            self.assertEqual("first-before\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-raced\n", second.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rolled-back", manifest["mode"])

    def test_rollback_preserves_drifted_updated_target_and_records_manual_recovery(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            operations = [
                {"path": "first.txt", "content": "first-after\n"},
                {"path": "second.txt", "content": "second-after\n"},
            ]
            approved = safe_mutation.report_mutation(root, operations)["operations"]
            real_replace = safe_mutation.os.replace

            def drift_first_then_fail_second(source: object, destination: object) -> None:
                destination_path = Path(destination)
                if destination_path == second:
                    raise OSError("injected second replace failure")
                real_replace(source, destination)
                if destination_path == first:
                    first.write_text("first-concurrent\n", encoding="utf-8")

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=drift_first_then_fail_second,
            ):
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    safe_mutation.apply_mutation(
                        root,
                        operations,
                        root / ".backup",
                        expected_operations=approved,
                    )

            self.assertEqual("first-concurrent\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-before\n", second.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rollback-incomplete-manual-recovery", manifest["mode"])
            self.assertTrue((root / ".backup" / "files" / "first.txt").is_file())

    def test_rollback_preserves_drifted_created_target_and_records_manual_recovery(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            created = root / "created.txt"
            second = root / "second.txt"
            second.write_text("second-before\n", encoding="utf-8")
            operations = [
                {"path": "created.txt", "content": "created-after\n"},
                {"path": "second.txt", "content": "second-after\n"},
            ]
            approved = safe_mutation.report_mutation(root, operations)["operations"]
            real_replace = safe_mutation.os.replace

            def drift_created_then_fail_second(source: object, destination: object) -> None:
                destination_path = Path(destination)
                if destination_path == second:
                    raise OSError("injected second replace failure")
                real_replace(source, destination)
                if destination_path == created:
                    created.write_text("created-concurrent\n", encoding="utf-8")

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=drift_created_then_fail_second,
            ):
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    safe_mutation.apply_mutation(
                        root,
                        operations,
                        root / ".backup",
                        expected_operations=approved,
                    )

            self.assertEqual("created-concurrent\n", created.read_text(encoding="utf-8"))
            self.assertEqual("second-before\n", second.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rollback-incomplete-manual-recovery", manifest["mode"])

    def test_manifest_write_failure_cleans_owned_artifacts_and_keeps_preexisting_root(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            backup_root = root / ".backup"
            backup_root.mkdir()
            real_write_manifest = safe_mutation._write_manifest

            def write_then_fail(path: Path, manifest: dict[str, object]) -> None:
                real_write_manifest(path, manifest)
                raise OSError("injected manifest failure")

            with mock.patch.object(
                safe_mutation,
                "_write_manifest",
                side_effect=write_then_fail,
            ):
                with self.assertRaisesRegex(OSError, "manifest failure"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        backup_root,
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertTrue(backup_root.is_dir())
            self.assertEqual([], list(backup_root.iterdir()))

    def test_sidecar_write_failure_preserves_concurrent_backup_content(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            backup_root = root / ".backup"
            real_write_sidecar = safe_mutation._write_ownership_sidecar

            def write_concurrent_then_fail(
                destination: Path,
                manifest: dict[str, object],
            ) -> None:
                real_write_sidecar(destination, manifest)
                (destination / "concurrent.txt").write_text("keep\n", encoding="utf-8")
                raise OSError("injected sidecar failure")

            with mock.patch.object(
                safe_mutation,
                "_write_ownership_sidecar",
                side_effect=write_concurrent_then_fail,
            ):
                with self.assertRaisesRegex(OSError, "sidecar failure"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        backup_root,
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertEqual("keep\n", (backup_root / "concurrent.txt").read_text(encoding="utf-8"))
            self.assertEqual(["concurrent.txt"], sorted(path.name for path in backup_root.iterdir()))

    def test_trusted_journal_write_failure_cleans_backup_and_journal_artifacts(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            backup_root = root / ".backup"
            journal_paths: list[Path] = []
            real_write_journal = safe_mutation._write_trusted_journal

            def write_then_fail(approved_root: Path, manifest: dict[str, object]) -> None:
                real_write_journal(approved_root, manifest)
                journal_paths.append(
                    safe_mutation._trusted_journal_path(
                        approved_root,
                        str(manifest["operation_id"]),
                    )
                )
                raise OSError("injected journal failure")

            with mock.patch.object(
                safe_mutation,
                "_write_trusted_journal",
                side_effect=write_then_fail,
            ):
                with self.assertRaisesRegex(OSError, "journal failure"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        backup_root,
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertFalse(backup_root.exists())
            self.assertEqual(1, len(journal_paths))
            self.assertFalse(journal_paths[0].exists())

    def test_preparation_preserves_exact_backup_path_replaced_before_tracking(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            backup_root = root / ".backup"
            backup_file = backup_root / "files" / "target.txt"
            real_copy = safe_mutation.shutil.copy2

            def copy_then_replace(source: object, destination: object) -> object:
                result = real_copy(source, destination)
                if Path(destination) == backup_file:
                    backup_file.write_text("concurrent-backup\n", encoding="utf-8")
                return result

            with mock.patch.object(
                safe_mutation.shutil,
                "copy2",
                side_effect=copy_then_replace,
            ):
                with self.assertRaisesRegex(RuntimeError, "preparation cleanup incomplete"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        backup_root,
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertEqual("concurrent-backup\n", backup_file.read_text(encoding="utf-8"))

    def test_preparation_preserves_exact_manifest_path_replaced_before_tracking(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            backup_root = root / ".backup"
            manifest_path = backup_root / "manifest.json"
            real_write_manifest = safe_mutation._write_manifest

            def write_replace_then_fail(path: Path, manifest: dict[str, object]) -> None:
                real_write_manifest(path, manifest)
                path.write_text("concurrent-manifest\n", encoding="utf-8")
                raise OSError("injected manifest replacement failure")

            with mock.patch.object(
                safe_mutation,
                "_write_manifest",
                side_effect=write_replace_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "preparation cleanup incomplete"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        backup_root,
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            self.assertEqual("concurrent-manifest\n", manifest_path.read_text(encoding="utf-8"))

    def test_three_operation_rollback_preserves_drifted_middle_and_restores_earlier(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            middle = root / "middle.txt"
            later = root / "later.txt"
            first.write_text("first-before\n", encoding="utf-8")
            middle.write_text("middle-before\n", encoding="utf-8")
            later.write_text("later-before\n", encoding="utf-8")
            operations = [
                {"path": "first.txt", "content": "first-after\n"},
                {"path": "middle.txt", "content": "middle-after\n"},
                {"path": "later.txt", "content": "later-after\n"},
            ]
            approved = safe_mutation.report_mutation(root, operations)["operations"]
            real_replace = safe_mutation.os.replace

            def drift_middle_then_fail_later(source: object, destination: object) -> None:
                destination_path = Path(destination)
                if destination_path == later:
                    middle.write_text("middle-concurrent\n", encoding="utf-8")
                    raise OSError("injected later replace failure")
                real_replace(source, destination)

            with mock.patch.object(
                safe_mutation.os,
                "replace",
                side_effect=drift_middle_then_fail_later,
            ):
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    safe_mutation.apply_mutation(
                        root,
                        operations,
                        root / ".backup",
                        expected_operations=approved,
                    )

            self.assertEqual("first-before\n", first.read_text(encoding="utf-8"))
            self.assertEqual("middle-concurrent\n", middle.read_text(encoding="utf-8"))
            self.assertEqual("later-before\n", later.read_text(encoding="utf-8"))
            manifest = json.loads((root / ".backup" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("rollback-incomplete-manual-recovery", manifest["mode"])

    def test_rollback_state_manifest_failure_writes_recovery_and_retains_evidence(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first-before\n", encoding="utf-8")
            second.write_text("second-before\n", encoding="utf-8")
            operations = [
                {"path": "first.txt", "content": "first-after\n"},
                {"path": "second.txt", "content": "second-after\n"},
            ]
            approved = safe_mutation.report_mutation(root, operations)["operations"]
            real_replace = safe_mutation.os.replace
            real_write_manifest = safe_mutation._write_manifest
            manifest_writes = 0

            def fail_second_replace(source: object, destination: object) -> None:
                if Path(destination) == second:
                    raise OSError("injected replace failure")
                real_replace(source, destination)

            def fail_rollback_state_write(path: Path, manifest: dict[str, object]) -> None:
                nonlocal manifest_writes
                manifest_writes += 1
                if manifest_writes == 2:
                    raise OSError("injected rollback manifest failure")
                real_write_manifest(path, manifest)

            with (
                mock.patch.object(safe_mutation.os, "replace", side_effect=fail_second_replace),
                mock.patch.object(
                    safe_mutation,
                    "_write_manifest",
                    side_effect=fail_rollback_state_write,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    safe_mutation.apply_mutation(
                        root,
                        operations,
                        root / ".backup",
                        expected_operations=approved,
                    )

            self.assertEqual("first-before\n", first.read_text(encoding="utf-8"))
            self.assertEqual("second-before\n", second.read_text(encoding="utf-8"))
            manifest_path = root / ".backup" / "manifest.json"
            prepared_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            recovery = json.loads(
                (root / ".backup" / "rollback-recovery.json").read_text(encoding="utf-8")
            )
            journal = safe_mutation._trusted_journal_path(
                root,
                prepared_manifest["operation_id"],
            )
            self.assertEqual("prepared", prepared_manifest["mode"])
            self.assertEqual("rollback-incomplete-manual-recovery", recovery["mode"])
            self.assertTrue(journal.is_file())
            self.assertTrue((root / ".backup" / "files" / "first.txt").is_file())

    def test_applied_manifest_write_failure_rolls_back_targets(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")
            real_write_manifest = safe_mutation._write_manifest
            manifest_writes = 0

            def fail_applied_manifest_write(path: Path, manifest: dict[str, object]) -> None:
                nonlocal manifest_writes
                manifest_writes += 1
                if manifest_writes == 2:
                    raise OSError("injected applied manifest failure")
                real_write_manifest(path, manifest)

            with mock.patch.object(
                safe_mutation,
                "_write_manifest",
                side_effect=fail_applied_manifest_write,
            ):
                with self.assertRaisesRegex(OSError, "applied manifest failure"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        root / ".backup",
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            manifest = json.loads(
                (root / ".backup" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("rolled-back", manifest["mode"])

    def test_applied_manifest_verification_failure_rolls_back_targets(self) -> None:
        from scripts import safe_mutation

        with temporary_directory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("before\n", encoding="utf-8")

            def fail_applied_verification(path: Path, manifest: dict[str, object]) -> None:
                if manifest["mode"] == "applied":
                    raise RuntimeError("injected applied manifest verification failure")

            with mock.patch.object(
                safe_mutation,
                "_verify_manifest",
                side_effect=fail_applied_verification,
                create=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "manifest verification failure"):
                    safe_mutation.apply_mutation(
                        root,
                        [{"path": "target.txt", "content": "after\n"}],
                        root / ".backup",
                    )

            self.assertEqual("before\n", target.read_text(encoding="utf-8"))
            manifest = json.loads(
                (root / ".backup" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("rolled-back", manifest["mode"])

    def test_rejects_paths_outside_root(self) -> None:
        from scripts.safe_mutation import report_mutation

        with temporary_directory() as temp:
            with self.assertRaises(ValueError):
                report_mutation(Path(temp), [{"path": "../escape.txt", "content": "bad"}])


if __name__ == "__main__":
    unittest.main()
