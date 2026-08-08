from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = {
    "command",
    "exit_code",
    "log_path",
    "artifact_path",
    "artifact_exists",
    "limitations",
}


def validate_build_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        reasons.append(f"missing fields: {missing}")
    for field in ("command", "log_path", "artifact_path"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            reasons.append(f"{field} is required")
    if payload.get("exit_code") != 0:
        reasons.append("build exit_code is not zero")
    if payload.get("artifact_exists") is not True:
        reasons.append("expected artifact was not observed")
    if not isinstance(payload.get("limitations"), list):
        reasons.append("limitations must be a list")
    return {
        "verdict": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "command": payload.get("command"),
        "exit_code": payload.get("exit_code"),
        "log_path": payload.get("log_path"),
        "artifact_path": payload.get("artifact_path"),
        "limitations": payload.get("limitations", []),
    }
