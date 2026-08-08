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

    def test_rejects_paths_outside_root(self) -> None:
        from scripts.safe_mutation import report_mutation

        with temporary_directory() as temp:
            with self.assertRaises(ValueError):
                report_mutation(Path(temp), [{"path": "../escape.txt", "content": "bad"}])


if __name__ == "__main__":
    unittest.main()
