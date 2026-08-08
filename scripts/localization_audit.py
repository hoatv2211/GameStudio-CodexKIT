from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def audit_localization(
    authority: dict[str, str], copies: dict[str, dict[str, str]]
) -> dict[str, object]:
    authority_keys = set(authority)
    reports: dict[str, dict[str, list[str]]] = {}
    for name, copy in sorted(copies.items()):
        copy_keys = set(copy)
        reports[name] = {
            "missing": sorted(authority_keys - copy_keys),
            "extra": sorted(copy_keys - authority_keys),
            "mismatched": sorted(
                key for key in authority_keys.intersection(copy_keys) if authority[key] != copy[key]
            ),
        }
    status = "PASS" if all(not values for report in reports.values() for values in report.values()) else "FAIL"
    return {"status": status, "authority_keys": len(authority), "copies": reports}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit localization copies against an authority map.")
    parser.add_argument("authority", type=Path)
    parser.add_argument("copies", type=Path)
    args = parser.parse_args(argv)
    report = audit_localization(
        json.loads(args.authority.read_text(encoding="utf-8")),
        json.loads(args.copies.read_text(encoding="utf-8")),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
