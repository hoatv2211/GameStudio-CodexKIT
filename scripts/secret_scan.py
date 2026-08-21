from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    path: Path
    line: int
    preview: str


PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret)\b"
    r"\s*[:=]\s*(?:['\"](?P<quoted>[^'\"]{20,})['\"]|(?P<unquoted>[^\s#;,]{20,}))"
)
PLACEHOLDER_MARKERS = ("example", "redacted", "placeholder", "changeme", "dummy", "sample")
PLACEHOLDER_SYNTAX = re.compile(r"(?:\$\{[^}]+\}|\{[^{}]+\}|<[^>]+>)")
EXCLUDED_DIRECTORY_NAMES = {
    ".archive",
    ".git",
    ".research",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "adapters",
    "dist",
    "node_modules",
}


def _entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_placeholder(value: str) -> bool:
    folded = value.casefold()
    return any(marker in folded for marker in PLACEHOLDER_MARKERS) or bool(
        PLACEHOLDER_SYNTAX.search(value)
    )


def _preview(line: str) -> str:
    stripped = line.strip()
    return stripped[:12] + "...[redacted]" if len(stripped) > 12 else "[redacted]"


def scan_text(text: str, path: Path) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    seen: set[tuple[str, int]] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        specific_match = False
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                if _is_placeholder(value):
                    continue
                specific_match = True
                key = (kind, line_number)
                if key not in seen:
                    findings.append(SecretFinding(kind, path, line_number, _preview(line)))
                    seen.add(key)
        if specific_match:
            continue
        for match in ASSIGNMENT_PATTERN.finditer(line):
            value = match.group("quoted") or match.group("unquoted") or ""
            if _is_placeholder(value) or _entropy(value) < 3.5:
                continue
            key = ("high-entropy-secret", line_number)
            if key not in seen:
                findings.append(SecretFinding("high-entropy-secret", path, line_number, _preview(line)))
                seen.add(key)
    return findings


def scan_repository(root: Path | str) -> list[SecretFinding]:
    root_path = Path(root).resolve()
    findings: list[SecretFinding] = []
    for path in sorted(
        item for item in root_path.rglob("*") if item.is_file() and not item.is_symlink()
    ):
        relative = path.relative_to(root_path)
        parts = relative.parts
        if any(part in EXCLUDED_DIRECTORY_NAMES or part.startswith(".tmp-") for part in parts[:-1]):
            continue
        if len(parts) >= 2 and parts[0] == "evidence" and parts[1] == "local":
            continue
        try:
            data = path.read_bytes()
            if b"\x00" in data:
                continue
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(text, relative))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan governed repository paths for likely secrets.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    findings = scan_repository(Path(args.root))
    for finding in findings:
        print(f"SECRET {finding.kind} {finding.path}:{finding.line} {finding.preview}")
    print(f"secret-scan: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
