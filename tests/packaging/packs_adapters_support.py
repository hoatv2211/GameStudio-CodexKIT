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

def temporary_directory() -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory(prefix="gamestudio-packaging-")
    directory.name = str(Path(directory.name).resolve())
    return directory

def tree_digest(root: Path) -> str:
    def add_field(hasher, value: bytes) -> None:
        hasher.update(len(value).to_bytes(8, "big"))
        hasher.update(value)

    def is_reparse(info: os.stat_result) -> bool:
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)

    try:
        root_info = root.lstat()
    except FileNotFoundError:
        root_info = None
    if root_info is not None and (root.is_symlink() or is_reparse(root_info)):
        raise RuntimeError(f"tree digest root is a symlink or reparse point: {root}")

    entries: list[tuple[bytes, bytes, bytes]] = []

    def collect(directory: Path) -> None:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                path = Path(entry.path)
                relative_text = path.relative_to(root).as_posix()
                relative = relative_text.encode("utf-8")
                info = entry.stat(follow_symlinks=False)
                is_link = entry.is_symlink()
                if is_link or is_reparse(info):
                    try:
                        target = os.fsencode(os.readlink(path))
                    except OSError:
                        raise RuntimeError(
                            f"tree digest cannot read reparse target: {relative_text}"
                        ) from None
                    entry_type = b"link" if is_link else b"reparse"
                    entries.append((relative, entry_type, target))
                elif stat.S_ISDIR(info.st_mode):
                    collect(path)
                elif stat.S_ISREG(info.st_mode):
                    entries.append((relative, b"file", path.read_bytes()))

    if root.is_dir():
        collect(root)

    hasher = hashlib.sha256()
    for relative, entry_type, content in sorted(entries):
        add_field(hasher, entry_type)
        add_field(hasher, relative)
        add_field(hasher, content)
    return hasher.hexdigest()

def apply_reviewed_project_adapter(
    source_root: Path,
    project: Path,
    *,
    reviewer: str,
    backup_root: Path,
) -> dict[str, object]:
    from scripts.generate_adapters import apply_project_adapter, report_project_adapter

    report = report_project_adapter(source_root, project)
    return apply_project_adapter(
        source_root,
        project,
        reviewer=reviewer,
        backup_root=backup_root,
        approved_plan_digest=report["plan_digest"],
    )

class PackagingTestCase(unittest.TestCase):
    def create_directory_alias(self, link: Path, target: Path) -> None:
        if os.name == "nt":
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                self.skipTest(
                    f"junction creation unavailable: {completed.stderr or completed.stdout}"
                )
            return
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

    def remove_directory_alias(self, link: Path) -> None:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()

    def assert_uninstall_report_disjoint(self, report: dict[str, object]) -> None:
        self.assertTrue(
            set(report["removed"]).isdisjoint(report["preserved_drift"]),
            report,
        )

    def assert_recovery_journal_truthful(
        self, project: Path, report: dict[str, object]
    ) -> None:
        recovery_relative = report.get("recovery_manifest")
        if not isinstance(recovery_relative, str):
            return
        recovery_path = project / recovery_relative
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        for record in recovery["files"]:
            artifact = project / record["quarantine_path"]
            if record["state"] in {"pending", "moved", "removing"}:
                self.assertTrue(artifact.is_file(), record)
                self.assertEqual(
                    record["sha256"],
                    hashlib.sha256(artifact.read_bytes()).hexdigest(),
                )
            elif record["state"] == "removed":
                self.assertFalse(os.path.lexists(artifact), record)
                self.assertIn(record["path"], report["removed"])
            elif record["state"] == "missing":
                self.assertFalse(os.path.lexists(artifact), record)
                self.assertIn(record["path"], report["preserved_drift"])
            elif record["state"] == "drifted":
                self.assertTrue(artifact.is_file(), record)
                observed = hashlib.sha256(artifact.read_bytes()).hexdigest()
                self.assertEqual(record["observed_sha256"], observed)
                self.assertNotEqual(record["sha256"], observed)
                self.assertIn(record["path"], report["preserved_drift"])
