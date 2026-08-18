# Governed Dogfood

Dogfood evidence must come from a named real game-project snapshot and a governed Hermes or Codex run. The reusable template ships cases and validation logic, not fabricated PASS artifacts.

## Prepare

Export the twelve scenarios and an explicit local BLOCKED status:

```bash
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
```

Select projects that the reviewer is authorized to inspect. Record repository or package identity, branch or build, engine and service versions, do-not-touch scope, and allowed mutations before invoking a runner.

## Runner result

Return one strict JSON object containing one result per exported case. Every declared property is present so Codex Structured Outputs can enforce the contract; fields unavailable for `BLOCKED` or `FAIL` use `null`.

```json
{
  "results": [
    {
      "id": "cpp-access-violation",
      "workflow": "cpp-server-crash-triage",
      "verdict": "PASS",
      "evidence_label": "Verified",
      "command": "hermes run governed-dogfood",
      "exit_code": 0,
      "artifacts": [
        {
          "kind": "command-log",
          "path": "artifacts/cpp-access-violation/command.log",
          "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        {
          "kind": "project-snapshot",
          "path": "artifacts/cpp-access-violation/project-snapshot.json",
          "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        },
        {
          "kind": "crash-signature",
          "path": "artifacts/cpp-access-violation/crash-signature.txt",
          "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
        },
        {
          "kind": "verdict",
          "path": "artifacts/cpp-access-violation/verdict.json",
          "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        }
      ],
      "project_snapshot": "game-server@abc123",
      "reviewer": "Server Lead",
      "timestamp": "2026-08-09T12:00:00+07:00",
      "unauthorized_write": false,
      "restore": "No mutation performed",
      "reason": null
    }
  ]
}
```

`PASS` requires exact case coverage, the expected workflow, `Verified`, exit code zero, every required artifact kind with a relative path and matching SHA-256, a project snapshot, reviewer, timestamp, no unauthorized write, and restore information. Use `BLOCKED` with `evidence_label: BLOCKED`, empty artifacts, nullable unavailable fields, and a reason when the runner, project, permission, or dependency is unavailable.

### Unity MCP runtime transcript pairs

Runtime transcripts accept only these normalized `tool / operation -> artifact` pairs. A recorded tool may use the full `mcp__unityMCP__<tool>` name; validation strips that prefix before matching.

| Artifact | Accepted tool / operation pairs |
|---|---|
| `editor-state` | `read_mcp_resource / mcpforunity://editor/state`, `resources/read / mcpforunity://editor/state` |
| `editmode-result` | `run_tests / EditMode`, `get_test_job / EditMode` |
| `playmode-result` | `run_tests / PlayMode`, `get_test_job / PlayMode`; optional controlled `manage_editor / play` and `manage_editor / stop` calls may accompany them |
| `console-report` | `read_console / get` |
| `runtime-assertion` | `execute_custom_tool / assert_localization`, `execute_code / execute` |

Editor readiness must come from the canonical MCP resource read; `manage_editor` has no state-read action. `run_tests` records only the asynchronous start, so each EditMode and PlayMode result requires exactly one matching `get_test_job` completion. The start and completion calls share a substantive `job_id`, the two modes use distinct jobs, and play/stop controls cannot substitute for a completed PlayMode result.

Every call must also bind the same case, editor instance, source snapshot, artifact path, and SHA-256 as the strict runtime result. Non-test calls use a null `job_id`. Unknown tools, impossible actions, mismatched test jobs, or a valid operation paired with the wrong tool fail validation.

## Validate

```bash
python -B scripts/dogfood_eval.py . \
  --results evidence/local/dogfood-results.json \
  --artifact-root evidence/local \
  --summary-dir evidence/local/dogfood
```

Only a complete strict-wrapper PASS result set generates `dogfood-summary.json` files. Relative artifact paths must stay below `--artifact-root`; absolute paths, traversal, missing files, and digest drift fail validation. Legacy result arrays remain readable for BLOCKED diagnostics but cannot generate promotion evidence. Run `scripts/catalog_audit.py` afterward; it rechecks artifact existence and hashes, and promotion also requires governed behavior, pressure, Tier-B, and session-history evidence covering the workflow.

Keep raw logs and local summaries under ignored `evidence/local/` or attach them to the target project or release. Do not commit private game data, credentials, dumps, database contents, or player information into this template.
