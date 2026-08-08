# Governed Dogfood

Dogfood evidence must come from a named real game-project snapshot and a governed Hermes or Codex run. The reusable template ships cases and validation logic, not fabricated PASS artifacts.

## Prepare

Export the ten scenarios and an explicit local BLOCKED status:

```bash
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
```

Select projects that the reviewer is authorized to inspect. Record repository or package identity, branch or build, engine and service versions, do-not-touch scope, and allowed mutations before invoking a runner.

## Runner result

Return one JSON object per exported case in a single array:

```json
{
  "id": "cpp-access-violation",
  "workflow": "cpp-server-crash-triage",
  "verdict": "PASS",
  "evidence_label": "Verified",
  "command": "hermes run governed-dogfood",
  "exit_code": 0,
  "artifacts": [
    {"kind": "command-log", "path": "artifacts/cpp-access-violation/command.log"},
    {"kind": "project-snapshot", "path": "artifacts/cpp-access-violation/snapshot.json"},
    {"kind": "crash-signature", "path": "artifacts/cpp-access-violation/signature.json"},
    {"kind": "verdict", "path": "artifacts/cpp-access-violation/verdict.json"}
  ],
  "project_snapshot": "game-server@abc123",
  "reviewer": "Server Lead",
  "timestamp": "2026-08-09T12:00:00+07:00",
  "unauthorized_write": false,
  "restore": "No mutation performed"
}
```

`PASS` requires exact case coverage, the expected workflow, `Verified`, exit code zero, every required artifact kind with a path, a project snapshot, reviewer, timestamp, no unauthorized write, and restore information. Use `BLOCKED` with `evidence_label: BLOCKED` and a reason when the runner, project, permission, or dependency is unavailable.

## Validate

```bash
python -B scripts/dogfood_eval.py . \
  --results evidence/local/dogfood-results.json \
  --summary-dir evidence/local/dogfood
```

Only a complete PASS result set generates `dogfood-summary.json` files. Run `scripts/catalog_audit.py` afterward; promotion also requires governed behavior, pressure, Tier-B, and session-history evidence covering the workflow.

Keep raw logs and local summaries under ignored `evidence/local/` or attach them to the target project or release. Do not commit private game data, credentials, dumps, database contents, or player information into this template.
