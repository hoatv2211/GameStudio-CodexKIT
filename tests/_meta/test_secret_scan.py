from __future__ import annotations

import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


class SecretScanTests(unittest.TestCase):
    def test_detects_credentials_and_private_keys(self) -> None:
        from scripts.secret_scan import scan_text

        github_token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz" + "1234567890"
        private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
        text = f"token = '{github_token}'\n{private_key_header}\n"
        findings = scan_text(text, Path("skills/example/SKILL.md"))
        self.assertEqual({"github-token", "private-key"}, {finding.kind for finding in findings})

    def test_allows_documented_placeholders(self) -> None:
        from scripts.secret_scan import scan_text

        text = "aws_key = 'AKIAIOSFODNN7EXAMPLE'\npassword = '<REDACTED>'\n"
        self.assertEqual([], scan_text(text, Path("docs/example.md")))

    def test_scans_all_distributable_text_and_ignores_local_or_generated_trees(self) -> None:
        from scripts.secret_scan import scan_repository

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            (root / ".research").mkdir()
            (root / ".archive").mkdir()
            (root / "adapters").mkdir()
            (root / "evidence" / "local").mkdir(parents=True)
            secret = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz" + "1234567890"
            (root / "docs" / "release.md").write_text(secret, encoding="utf-8")
            for ignored in (
                root / ".research" / "ignored.txt",
                root / ".archive" / "ignored.txt",
                root / "adapters" / "ignored.txt",
                root / "evidence" / "local" / "ignored.txt",
            ):
                ignored.write_text(secret, encoding="utf-8")
            findings = scan_repository(root)
            self.assertEqual(1, len(findings))
            self.assertEqual("docs/release.md", findings[0].path.as_posix())

    def test_scans_common_secret_files_without_allowlisted_suffixes(self) -> None:
        from scripts.secret_scan import scan_repository

        with temporary_directory() as temp:
            root = Path(temp)
            github_token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz" + "1234567890"
            private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
            (root / ".env").write_text(f"TOKEN={github_token}\n", encoding="utf-8")
            (root / "deploy.key").write_text(private_key_header + "\n", encoding="utf-8")

            findings = scan_repository(root)

            self.assertEqual(
                {("github-token", ".env"), ("private-key", "deploy.key")},
                {(finding.kind, finding.path.as_posix()) for finding in findings},
            )


if __name__ == "__main__":
    unittest.main()
