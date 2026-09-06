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

    def test_ignores_root_superpowers_without_hiding_distributable_content(self) -> None:
        from scripts.secret_scan import scan_repository

        with temporary_directory() as temp:
            root = Path(temp)
            local_report = root / ".superpowers" / "sdd" / "report.md"
            distributed = root / "skills" / "demo" / ".superpowers" / "fixture.md"
            local_report.parent.mkdir(parents=True)
            distributed.parent.mkdir(parents=True)
            secret = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz" + "1234567890"
            local_report.write_text(secret, encoding="utf-8")
            distributed.write_text(secret, encoding="utf-8")

            findings = scan_repository(root)

            self.assertEqual(1, len(findings))
            self.assertEqual(
                "skills/demo/.superpowers/fixture.md", findings[0].path.as_posix()
            )

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

    def test_detects_unquoted_dotenv_and_yaml_high_entropy_assignments(self) -> None:
        from scripts.secret_scan import scan_text

        value = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/="
        text = f"API_KEY={value}\napi_key: {value} # deployment key\n"
        findings = scan_text(text, Path(".env"))
        self.assertEqual(2, len(findings))
        self.assertEqual({"high-entropy-secret"}, {finding.kind for finding in findings})

    def test_detects_complete_secret_identifier_assignments(self) -> None:
        from scripts.secret_scan import scan_text

        value = "AbCdEfGhIjKlMnOp" + "QrStUvWxYz0123456789"
        access_identifier = "access" + "_token"
        aws_identifier = "AWS_SECRET" + "_ACCESS_KEY"
        text = f"{access_identifier}={value}\n{aws_identifier}={value}\n"

        findings = scan_text(text, Path(".env"))

        self.assertEqual(2, len(findings))
        self.assertEqual([1, 2], [finding.line for finding in findings])
        self.assertEqual({"high-entropy-secret"}, {finding.kind for finding in findings})

    def test_ignores_runtime_generators_but_detects_literal_assignments(self) -> None:
        from scripts.secret_scan import scan_text

        urlsafe_call = "secrets." + "token_urlsafe(24)"
        hex_call = "secrets." + "token_hex(32)"
        literal = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/="
        wrapped_literal = "crypto." + f'decrypt("{literal}")'
        text = (
            f"token = {urlsafe_call}\n"
            f"api_key = {hex_call}\n"
            f"client_secret = {literal}\n"
            f"password = {wrapped_literal}\n"
        )

        findings = scan_text(text, Path("scripts/runtime.py"))

        self.assertEqual(2, len(findings))
        self.assertEqual({"high-entropy-secret"}, {finding.kind for finding in findings})
        self.assertEqual([3, 4], [finding.line for finding in findings])

    def test_detects_high_entropy_arguments_inside_runtime_calls(self) -> None:
        from scripts.secret_scan import scan_text

        secret = "AbCdEfGhIjKlMnOp" + "QrStUvWxYz0123456789"
        text = (
            "token = " + f"vault.unwrap({secret})\n"
            "api_key = " + f"vault.unwrap([{secret}])\n"
        )

        findings = scan_text(text, Path("scripts/runtime.py"))

        self.assertEqual(2, len(findings))
        self.assertEqual([1, 2], [finding.line for finding in findings])
        self.assertEqual({"high-entropy-secret"}, {finding.kind for finding in findings})

    def test_ignores_runtime_generator_with_multiple_decimal_arguments(self) -> None:
        from scripts.secret_scan import scan_text

        text = "token = " + "secrets.generate_token_bytes(24,32)\n"

        self.assertEqual([], scan_text(text, Path("scripts/runtime.py")))

    def test_detects_mixed_decimal_and_high_entropy_runtime_arguments(self) -> None:
        from scripts.secret_scan import scan_text

        secret = "AbCdEfGhIjKlMnOp" + "QrStUvWxYz0123456789"
        text = (
            "token = " + f"vault.unwrap(24,{secret})\n"
            "api_key = " + f"vault.unwrap(24,{secret[:20]} + {secret[20:]})\n"
        )

        findings = scan_text(text, Path("scripts/runtime.py"))

        self.assertEqual(2, len(findings))
        self.assertEqual({"high-entropy-secret"}, {finding.kind for finding in findings})
        self.assertEqual([1, 2], [finding.line for finding in findings])

    def test_detects_mixed_runtime_argument_with_placeholder_callable_segment(self) -> None:
        from scripts.secret_scan import scan_text

        secret = "AbCdEfGhIjKlMnOp" + "QrStUvWxYz0123456789"
        text = "token = " + f"example.vault.unwrap(24,{secret})\n"

        findings = scan_text(text, Path("scripts/runtime.py"))

        self.assertEqual(1, len(findings))
        self.assertEqual("high-entropy-secret", findings[0].kind)
        self.assertEqual(1, findings[0].line)

    def test_detects_mixed_runtime_argument_with_trailing_placeholder(self) -> None:
        from scripts.secret_scan import scan_text

        secret = "AbCdEfGhIjKlMnOp" + "QrStUvWxYz0123456789"
        text = "token = " + f"vault.unwrap(24,{secret},example)\n"

        findings = scan_text(text, Path("scripts/runtime.py"))

        self.assertEqual(1, len(findings))
        self.assertEqual("high-entropy-secret", findings[0].kind)
        self.assertEqual(1, findings[0].line)

    def test_allows_documented_placeholders_inside_runtime_calls(self) -> None:
        from scripts.secret_scan import scan_text

        text = (
            "token = " + 'vault.unwrap("<REDACTED>")\n'
            "api_key = " + 'vault.unwrap("${TOKEN}")\n'
            "client_secret = " + 'vault.unwrap("example")\n'
        )

        self.assertEqual([], scan_text(text, Path("scripts/runtime.py")))


if __name__ == "__main__":
    unittest.main()
