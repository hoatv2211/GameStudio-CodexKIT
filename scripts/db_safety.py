from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "project_owner",
    "database",
    "host",
    "port",
    "schema_version",
    "expected_schema",
    "migration_sha256",
    "backup_path",
    "restore_command",
    "reviewer",
    "human_approval",
    "maintenance_window",
    "validation_queries",
}


def plan_migration(config: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    missing_fields = sorted(REQUIRED_FIELDS - set(config))
    unknown_fields = sorted(set(config) - REQUIRED_FIELDS)
    if missing_fields:
        reasons.append(f"missing required fields: {missing_fields}")
    if unknown_fields:
        reasons.append(f"unknown fields: {unknown_fields}")

    values = {field: config.get(field) for field in REQUIRED_FIELDS}
    for field in (
        "project_owner",
        "database",
        "host",
        "schema_version",
        "expected_schema",
        "backup_path",
        "restore_command",
        "reviewer",
        "maintenance_window",
    ):
        if not isinstance(values.get(field), str) or not str(values[field]).strip():
            reasons.append(f"{field} is required")

    schema_version = str(values.get("schema_version") or "")
    expected_schema = str(values.get("expected_schema") or "")
    if not schema_version or schema_version.casefold() == "unknown":
        reasons.append("unknown schema version")
    elif schema_version != expected_schema:
        reasons.append(f"schema mismatch: observed {schema_version}, expected {expected_schema}")
    try:
        port = int(values.get("port"))
    except (TypeError, ValueError):
        port = -1
    if port not in {3306, 3307}:
        reasons.append("database port is not an approved isolated MySQL port (3306 or 3307)")
    migration_sha256 = str(values.get("migration_sha256") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", migration_sha256):
        reasons.append("migration_sha256 must be a 64-character hexadecimal digest")
    if not isinstance(values.get("human_approval"), bool) or not values.get("human_approval"):
        reasons.append("human approval is required")
    validation_queries = values.get("validation_queries")
    if (
        not isinstance(validation_queries, list)
        or not validation_queries
        or any(not isinstance(query, str) or not query.strip() for query in validation_queries)
    ):
        reasons.append("validation_queries requires at least one non-empty query")
    verdict = "BLOCKED" if reasons else "READY_FOR_REVIEW"
    return {
        "verdict": verdict,
        "dry_run": True,
        "project_owner": values.get("project_owner"),
        "database": values.get("database"),
        "host": values.get("host"),
        "port": port,
        "schema_version": schema_version,
        "expected_schema": expected_schema,
        "migration_sha256": migration_sha256,
        "backup_path": values.get("backup_path"),
        "restore_command": values.get("restore_command"),
        "reviewer": values.get("reviewer"),
        "human_approval": values.get("human_approval"),
        "maintenance_window": values.get("maintenance_window"),
        "validation_queries": validation_queries,
        "reasons": reasons,
        "limitations": ["No database connection or mutation was performed."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a no-write database migration safety plan.")
    parser.add_argument("config", type=Path)
    args = parser.parse_args(argv)
    report = plan_migration(json.loads(args.config.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "READY_FOR_REVIEW" else 2


if __name__ == "__main__":
    sys.exit(main())
