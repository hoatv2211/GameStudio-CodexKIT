from __future__ import annotations

from typing import Any


def evaluate_release_preflight(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed: list[str] = []
    blocked: list[str] = []
    missing_evidence: list[str] = []
    for check in checks:
        check_id = str(check.get("id", "<unnamed>"))
        status = check.get("status")
        if status == "FAIL":
            failed.append(check_id)
        elif status == "BLOCKED":
            blocked.append(check_id)
        elif status != "PASS":
            blocked.append(check_id)
        evidence = check.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            missing_evidence.append(check_id)
    if failed:
        verdict = "FAIL"
    elif blocked:
        verdict = "BLOCKED"
    elif missing_evidence:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict,
        "failed": failed,
        "blocked": blocked,
        "missing_evidence": missing_evidence,
        "checks": checks,
    }
