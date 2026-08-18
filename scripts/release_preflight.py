from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

import jsonschema


RELEASE_SCHEMA = Path("evals/schema/release-preflight.schema.json")
BUNDLED_RELEASE_SCHEMA = Path("schemas/release-preflight.schema.json")
REQUIRED_RELEASE_CHECKS = frozenset(
    {
        "candidate",
        "build",
        "tests",
        "security",
        "performance",
        "compatibility",
        "monitoring",
        "rollback",
        "approvals",
    }
)
DEFAULT_MAX_EVIDENCE_AGE = dt.timedelta(days=7)
MAX_FUTURE_SKEW = dt.timedelta(minutes=5)
PLACEHOLDERS = frozenset(
    {
        "dummy",
        "example",
        "fill-me",
        "n/a",
        "na",
        "none",
        "placeholder",
        "replace-me",
        "tbd",
        "todo",
        "unknown",
        "unset",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_path() -> Path:
    script = Path(__file__).resolve()
    bundled = script.parent.parent / BUNDLED_RELEASE_SCHEMA
    if bundled.is_file():
        return bundled
    for parent in script.parents:
        candidate = parent / RELEASE_SCHEMA
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"release preflight schema is unavailable: {RELEASE_SCHEMA}")


def load_release_preflight_schema(path: Path | str | None = None) -> dict[str, Any]:
    path = Path(path).resolve() if path is not None else _schema_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator.check_schema(payload)
    except jsonschema.SchemaError as error:
        raise ValueError(f"invalid release preflight schema: {error.message}") from error
    return payload


def _schema_errors(payload: object) -> list[str]:
    try:
        schema = load_release_preflight_schema()
    except (OSError, ValueError, jsonschema.SchemaError) as error:
        return [f"release preflight schema unavailable or invalid: {error}"]
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    result = []
    for error in errors:
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        result.append(f"{location}: {error.message}")
    return result


def _parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _is_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized in PLACEHOLDERS
        or normalized.startswith("todo:")
        or normalized.startswith("tbd:")
        or (normalized.startswith("<") and normalized.endswith(">"))
    )


def _resolve_evidence(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("evidence path must be a non-empty string")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        pure.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not pure.parts
        or "." in pure.parts
        or ".." in pure.parts
    ):
        raise ValueError(f"unsafe evidence path: {value}")
    target = root.joinpath(*pure.parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError(f"evidence path escapes approved root: {value}") from error
    if not target.is_file():
        raise ValueError(f"evidence file does not exist: {value}")
    return target


def _normalized_evidence_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("evidence path must be a non-empty string")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        pure.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not pure.parts
        or "." in pure.parts
        or ".." in pure.parts
    ):
        raise ValueError(f"unsafe evidence path: {value}")
    return pure.as_posix().casefold()


def _has_substance(path: Path) -> bool:
    raw = path.read_bytes()
    if not raw or not raw.strip():
        return False
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return True
    if _is_placeholder(text):
        return False
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return True
    return payload not in ({}, [], None, "")


def _validate_artifact(
    artifact: object,
    *,
    root: Path,
    label: str,
) -> list[str]:
    if not isinstance(artifact, dict):
        return [f"{label}: artifact must be an object"]
    errors: list[str] = []
    try:
        path = _resolve_evidence(root, artifact.get("path"))
    except ValueError as error:
        return [f"{label}: {error}"]
    digest = artifact.get("sha256")
    if not isinstance(digest, str) or _sha256(path) != digest:
        errors.append(f"{label}: artifact hash mismatch: {artifact.get('path')}")
    if not _has_substance(path):
        errors.append(f"{label}: artifact is semantically empty: {artifact.get('path')}")
    return errors


def _validate_resolution_artifact(
    artifact: object,
    *,
    root: Path,
    defect_id: str,
    candidate_id: str | None,
    verification_command: object,
    verification_exit_code: object,
) -> list[str]:
    label = f"{defect_id}.resolution.artifact"
    errors = _validate_artifact(artifact, root=root, label=label)
    if errors:
        return errors
    try:
        path = _resolve_evidence(root, artifact.get("path") if isinstance(artifact, dict) else None)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return [f"{label}: resolution artifact must be a JSON object: {error}"]
    if not isinstance(payload, dict):
        return [f"{label}: resolution artifact must be a JSON object"]
    expected = {
        "candidate_id": candidate_id,
        "defect_id": defect_id,
        "status": "RESOLVED",
        "verification_command": verification_command,
        "verification_exit_code": verification_exit_code,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"{label}: {field} does not match resolved defect evidence")
    return errors


def _validate_check_evidence_envelope(
    artifact: object,
    *,
    root: Path,
    check: dict[str, Any],
    candidate: dict[str, Any],
    now: dt.datetime,
    max_age: dt.timedelta,
) -> list[str]:
    check_id = str(check.get("id"))
    label = f"{check_id}.evidence envelope"
    try:
        path = _resolve_evidence(root, artifact.get("path") if isinstance(artifact, dict) else None)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return [f"{label}: must be a strict JSON object: {error}"]
    if not isinstance(payload, dict):
        return [f"{label}: must be a strict JSON object"]
    schema = load_release_preflight_schema().get("$defs", {}).get("checkEvidenceEnvelope")
    if not isinstance(schema, dict):
        return [f"{label}: schema is unavailable"]
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        errors.append(f"{label} {location}: {error.message}")
    expected = {
        "candidate_id": candidate.get("id"),
        "candidate_version": candidate.get("version"),
        "source_snapshot": candidate.get("source_snapshot"),
        "build_id": candidate.get("build_id"),
        "primary_artifact_sha256": (
            candidate.get("primary_artifact", {}).get("sha256")
            if isinstance(candidate.get("primary_artifact"), dict)
            else None
        ),
        "check_id": check.get("id"),
        "kind": check.get("id"),
        "command": check.get("command"),
        "exit_code": check.get("exit_code"),
        "timestamp": check.get("timestamp"),
        "owner": check.get("owner"),
        "status": check.get("status"),
        "details": check.get("details", {}),
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"{label}: {field} does not match check metadata")
    freshness = _freshness_error(
        payload.get("timestamp"),
        now=now,
        max_age=max_age,
        label=label,
    )
    if freshness:
        errors.append(freshness)
    for field in (
        "candidate_id",
        "candidate_version",
        "source_snapshot",
        "build_id",
        "primary_artifact_sha256",
        "check_id",
        "kind",
        "command",
        "owner",
    ):
        if _is_placeholder(payload.get(field)):
            errors.append(f"{label}: {field} is missing or placeholder")
    return errors


def _freshness_error(
    value: object,
    *,
    now: dt.datetime,
    max_age: dt.timedelta,
    label: str,
) -> str | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return f"{label}: timestamp must be timezone-aware ISO-8601"
    current = now.astimezone(dt.timezone.utc)
    observed = parsed.astimezone(dt.timezone.utc)
    if observed > current + MAX_FUTURE_SKEW:
        return f"{label}: timestamp is in the future"
    if current - observed > max_age:
        return f"{label}: evidence timestamp is stale"
    return None


def _duplicate_ids(records: object) -> list[str]:
    if not isinstance(records, list):
        return []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            continue
        record_id = record["id"]
        if record_id in seen:
            duplicates.add(record_id)
        seen.add(record_id)
    return sorted(duplicates)


def evaluate_release_preflight(
    payload: object,
    *,
    evidence_root: Path | str | None = None,
    required_checks: Iterable[str] = REQUIRED_RELEASE_CHECKS,
    now: dt.datetime | None = None,
    max_evidence_age: dt.timedelta = DEFAULT_MAX_EVIDENCE_AGE,
) -> dict[str, Any]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    required = {str(item) for item in required_checks}
    schema_errors = _schema_errors(payload)
    data = payload if isinstance(payload, dict) else {}
    candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
    candidate_id = candidate.get("id") if isinstance(candidate.get("id"), str) else None
    candidate_snapshot = candidate.get("source_snapshot")
    candidate_build_id = candidate.get("build_id")
    primary_artifact = (
        candidate.get("primary_artifact")
        if isinstance(candidate.get("primary_artifact"), dict)
        else {}
    )
    primary_digest = primary_artifact.get("sha256")
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    defects = data.get("defects") if isinstance(data.get("defects"), list) else []
    waivers = data.get("waivers") if isinstance(data.get("waivers"), list) else []
    root = Path(evidence_root).resolve() if evidence_root is not None else None
    root_ready = root is not None and root.is_dir()

    failed: list[str] = []
    blocked: list[str] = []
    missing_evidence: list[str] = []
    invalid_checks: list[str] = []
    duplicate_checks = _duplicate_ids(checks)
    blocking_defects: list[str] = []
    active_waivers: list[str] = []
    expired_waivers: list[str] = []
    global_artifact_paths: dict[str, str] = {}

    for field in ("id", "version", "source_snapshot", "build_id"):
        if _is_placeholder(candidate.get(field)):
            invalid_checks.append(f"candidate.{field}: placeholder value is not release evidence")
    if root_ready:
        artifact_errors = _validate_artifact(
            candidate.get("primary_artifact"),
            root=root,
            label="candidate.primary_artifact",
        )
        invalid_checks.extend(artifact_errors)
        if any("does not exist" in error for error in artifact_errors):
            missing_evidence.append("candidate.primary_artifact")
    elif candidate:
        blocked.append("<evidence-root>")

    observed_ids: set[str] = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            continue
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id.strip():
            continue
        observed_ids.add(check_id)
        if check_id not in required:
            invalid_checks.append(f"{check_id}: unknown release check")
        if candidate_id is not None and check.get("candidate_id") != candidate_id:
            invalid_checks.append(f"{check_id}: candidate_id does not match candidate.id")
        if check.get("source_snapshot") != candidate_snapshot:
            invalid_checks.append(
                f"{check_id}: source_snapshot does not match candidate.source_snapshot"
            )
        if check.get("build_id") != candidate_build_id:
            invalid_checks.append(f"{check_id}: build_id does not match candidate.build_id")
        if check.get("primary_artifact_sha256") != primary_digest:
            invalid_checks.append(
                f"{check_id}: primary_artifact_sha256 does not match candidate primary artifact"
            )
        status = check.get("status")
        if status == "FAIL":
            failed.append(check_id)
        elif status == "BLOCKED":
            blocked.append(check_id)
        elif status == "PASS":
            freshness = _freshness_error(
                check.get("timestamp"),
                now=current,
                max_age=max_evidence_age,
                label=check_id,
            )
            if freshness:
                invalid_checks.append(freshness)
            for field in ("command", "owner"):
                if _is_placeholder(check.get(field)):
                    invalid_checks.append(f"{check_id}: {field} contains a placeholder")
            artifacts = check.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                missing_evidence.append(check_id)
            elif root_ready:
                artifact_paths: set[str] = set()
                for artifact_index, artifact in enumerate(artifacts):
                    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
                        try:
                            normalized_path = _normalized_evidence_path(artifact["path"])
                        except ValueError as error:
                            invalid_checks.append(f"{check_id}: {error}")
                            normalized_path = artifact["path"].casefold()
                        if normalized_path in artifact_paths:
                            invalid_checks.append(
                                f"{check_id}: duplicate artifact path: {artifact['path']}"
                            )
                        artifact_paths.add(normalized_path)
                        prior_check = global_artifact_paths.get(normalized_path)
                        if prior_check is not None and prior_check != check_id:
                            invalid_checks.append(
                                f"{check_id}: shared artifact path with {prior_check}: {artifact['path']}"
                            )
                        else:
                            global_artifact_paths[normalized_path] = check_id
                    artifact_errors = _validate_artifact(
                        artifact,
                        root=root,
                        label=f"{check_id}.artifacts[{artifact_index}]",
                    )
                    invalid_checks.extend(artifact_errors)
                    if any("does not exist" in error for error in artifact_errors):
                        missing_evidence.append(check_id)
                    if not artifact_errors:
                        invalid_checks.extend(
                            _validate_check_evidence_envelope(
                                artifact,
                                root=root,
                                check=check,
                                candidate=candidate,
                                now=current,
                                max_age=max_evidence_age,
                            )
                        )
            details = check.get("details")
            detail_values = details.values() if isinstance(details, dict) else ()
            for value in detail_values:
                values = value if isinstance(value, list) else [value]
                if any(_is_placeholder(item) for item in values if isinstance(item, str)):
                    invalid_checks.append(f"{check_id}: details contain a placeholder")
        else:
            invalid_checks.append(f"check {index}: invalid status")

        if check_id == "approvals" and status == "PASS":
            details = check.get("details") if isinstance(check.get("details"), dict) else {}
            approvers = details.get("approvers") if isinstance(details.get("approvers"), list) else []
            for approval_index, approval in enumerate(approvers):
                if not isinstance(approval, dict):
                    continue
                for field in ("name", "role"):
                    if _is_placeholder(approval.get(field)):
                        invalid_checks.append(
                            f"approvals[{approval_index}].{field}: approval owner is missing or placeholder"
                        )
                freshness = _freshness_error(
                    approval.get("timestamp"),
                    now=current,
                    max_age=max_evidence_age,
                    label=f"approvals[{approval_index}]",
                )
                if freshness:
                    invalid_checks.append(freshness)

    missing_checks = sorted(required - observed_ids)

    defect_ids = {
        defect.get("id")
        for defect in defects
        if isinstance(defect, dict) and isinstance(defect.get("id"), str)
    }
    duplicate_defects = _duplicate_ids(defects)
    if duplicate_defects:
        invalid_checks.extend(f"duplicate defect id: {item}" for item in duplicate_defects)
    for defect in defects:
        if not isinstance(defect, dict) or not isinstance(defect.get("id"), str):
            continue
        defect_id = defect["id"]
        for field in ("id", "owner", "summary"):
            if _is_placeholder(defect.get(field)):
                invalid_checks.append(
                    f"{defect_id}.defect.{field}: missing or placeholder"
                )
        if candidate_id is not None and defect.get("candidate_id") != candidate_id:
            invalid_checks.append(f"{defect_id}: defect candidate_id does not match candidate.id")
        if defect.get("blocks_release") is True and defect.get("status") != "RESOLVED":
            blocking_defects.append(defect_id)
        if defect.get("status") == "RESOLVED" and defect.get("severity") in {"P1", "P2"}:
            resolution = defect.get("resolution")
            if not isinstance(resolution, dict):
                invalid_checks.append(
                    f"{defect_id}: resolved P1/P2 defect requires resolution evidence"
                )
                continue
            for field in ("owner", "summary", "verification_command"):
                if _is_placeholder(resolution.get(field)):
                    invalid_checks.append(
                        f"{defect_id}.resolution.{field}: missing or placeholder"
                    )
            resolved_at = _parse_timestamp(resolution.get("resolved_at"))
            if resolved_at is None:
                invalid_checks.append(
                    f"{defect_id}.resolution.resolved_at: must be timezone-aware ISO-8601"
                )
            elif resolved_at.astimezone(dt.timezone.utc) > current.astimezone(dt.timezone.utc):
                invalid_checks.append(f"{defect_id}.resolution.resolved_at: is in the future")
            if resolution.get("verification_exit_code") != 0:
                invalid_checks.append(
                    f"{defect_id}.resolution.verification_exit_code: must be 0"
                )
            if root_ready:
                resolution_errors = _validate_resolution_artifact(
                    resolution.get("artifact"),
                    root=root,
                    defect_id=defect_id,
                    candidate_id=candidate_id,
                    verification_command=resolution.get("verification_command"),
                    verification_exit_code=resolution.get("verification_exit_code"),
                )
                invalid_checks.extend(resolution_errors)
                if any("does not exist" in error for error in resolution_errors):
                    missing_evidence.append(f"{defect_id}.resolution.artifact")
            else:
                blocked.append(f"{defect_id}.resolution.artifact")

    duplicate_waivers = _duplicate_ids(waivers)
    if duplicate_waivers:
        invalid_checks.extend(f"duplicate waiver id: {item}" for item in duplicate_waivers)
    for waiver in waivers:
        if not isinstance(waiver, dict) or not isinstance(waiver.get("id"), str):
            continue
        waiver_id = waiver["id"]
        if candidate_id is not None and waiver.get("candidate_id") != candidate_id:
            invalid_checks.append(f"{waiver_id}: waiver candidate_id does not match candidate.id")
        defect_id = waiver.get("defect_id")
        if defect_id is not None and defect_id not in defect_ids:
            invalid_checks.append(f"{waiver_id}: waiver references an unknown defect")
        for field in ("approved_by", "reason", "scope", "mitigation"):
            if _is_placeholder(waiver.get(field)):
                invalid_checks.append(f"{waiver_id}: {field} is missing or placeholder")
        expires_at = _parse_timestamp(waiver.get("expires_at"))
        if expires_at is None:
            invalid_checks.append(f"{waiver_id}: expires_at must be timezone-aware ISO-8601")
        elif expires_at <= current:
            expired_waivers.append(waiver_id)
        else:
            active_waivers.append(waiver_id)

    invalid_checks = sorted(set(invalid_checks))
    failed = sorted(set(failed))
    blocked = sorted(set(blocked))
    blocking_defects = sorted(set(blocking_defects))
    active_waivers = sorted(set(active_waivers))
    expired_waivers = sorted(set(expired_waivers))
    if schema_errors or failed or invalid_checks or duplicate_checks or missing_evidence or blocking_defects or expired_waivers:
        verdict = "FAIL"
    elif blocked or missing_checks or active_waivers:
        verdict = "BLOCKED"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict,
        "candidate_id": candidate_id,
        "failed": failed,
        "blocked": blocked,
        "blocking_defects": blocking_defects,
        "active_waivers": active_waivers,
        "expired_waivers": expired_waivers,
        "missing_evidence": sorted(set(missing_evidence)),
        "missing_checks": missing_checks,
        "duplicate_checks": duplicate_checks,
        "invalid_checks": invalid_checks,
        "schema_errors": schema_errors,
        "checks": checks,
    }
