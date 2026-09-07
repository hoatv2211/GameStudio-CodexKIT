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


class TreeDigestTests(unittest.TestCase):
    def test_tree_digest_frames_paths_and_contents_without_legacy_collision(self) -> None:
        def legacy_tree_digest(root: Path) -> str:
            hasher = hashlib.sha256()
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
                hasher.update(path.read_bytes())
            return hasher.hexdigest()

        with temporary_directory() as temp:
            temp_root = Path(temp)
            first = temp_root / "first"
            second = temp_root / "second"
            first.mkdir()
            second.mkdir()
            (first / "a").write_bytes(b"bc")
            (second / "ab").write_bytes(b"c")

            self.assertEqual(legacy_tree_digest(first), legacy_tree_digest(second))
            self.assertNotEqual(tree_digest(first), tree_digest(second))

    def test_tree_digest_frames_symlink_target_without_traversal(self) -> None:
        with temporary_directory() as temp:
            temp_root = Path(temp)
            first = temp_root / "first"
            second = temp_root / "second"
            first.mkdir()
            second.mkdir()
            first_target = temp_root / "first-target.bin"
            second_target = temp_root / "second-target.bin"
            first_target.write_bytes(b"same external content")
            second_target.write_bytes(b"same external content")
            try:
                (first / "link").symlink_to(first_target)
                (second / "link").symlink_to(second_target)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            first_digest = tree_digest(first)
            self.assertNotEqual(first_digest, tree_digest(second))
            first_target.write_bytes(b"changed outside tree")
            self.assertEqual(first_digest, tree_digest(first))

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_tree_digest_frames_junction_target_without_traversal(self) -> None:
        with temporary_directory() as temp:
            temp_root = Path(temp)
            first = temp_root / "first"
            second = temp_root / "second"
            first.mkdir()
            second.mkdir()
            first_target = temp_root / "first-target"
            second_target = temp_root / "second-target"
            first_target.mkdir()
            second_target.mkdir()
            (first_target / "external.bin").write_bytes(b"same external content")
            (second_target / "external.bin").write_bytes(b"same external content")

            for link, target in (
                (first / "junction", first_target),
                (second / "junction", second_target),
            ):
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

            first_digest = tree_digest(first)
            self.assertNotEqual(first_digest, tree_digest(second))
            (first_target / "external.bin").write_bytes(b"changed outside tree")
            self.assertEqual(first_digest, tree_digest(first))


if __name__ == "__main__":
    unittest.main()
