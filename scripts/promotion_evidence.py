from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

import jsonschema
import yaml

try:
    from scripts.dogfood_eval import evaluate_results, load_profile
except ModuleNotFoundError:
    from dogfood_eval import evaluate_results, load_profile


MATURITY_ORDER = ("experimental", "beta", "stable", "release")
RECORD_FIELDS = {
    "id",
    "skill_id",
    "from_maturity",
    "target_maturity",
    "profile",
    "case_ids",
    "evidence",
    "owner",
    "reviewer",
    "reviewed_at",
    "runtime_targets",
    "restore",
    "limitations",
    "expires_at",
}
ARTIFACT_FIELDS = {"kind", "path", "sha256"}
PROMOTION_SCHEMA = Path("evals/schema/promotion-evidence.schema.json")
LIFECYCLE_KINDS = frozenset(
    {"tier-b", "behavior", "pressure", "runtime-matrix", "session-history"}
)
MAX_LIFECYCLE_EVIDENCE_AGE = dt.timedelta(days=30)
MAX_REVIEW_LAG_DAYS = 7
LIFECYCLE_FIELDS = {
    "schema_version",
    "kind",
    "skill_id",
    "profile",
    "runtime_targets",
    "runtime_target",
    "verdict",
    "command",
    "exit_code",
    "runner",
    "source_snapshot",
    "timestamp",
    "owner",
    "reviewer",
    "artifacts",
    "details",
}
LIFECYCLE_NESTED_ARTIFACT_FIELDS = {"kind", "path", "sha256"}
LIFECYCLE_RUNNER_FIELDS = {
    "schema_version",
    "kind",
    "evidence_kind",
    "skill_id",
    "profile",
    "runtime_target",
    "source_snapshot",
    "command",
    "exit_code",
    "timestamp",
    "status",
    "details",
}
LIFECYCLE_MANIFEST_FIELDS = {
    "schema_version",
    "kind",
    "evidence_kind",
    "skill_id",
    "profile",
    "source_snapshot",
    "timestamp",
    "items",
}
LIFECYCLE_MANIFEST_KIND = {
    "tier-b": "case-manifest",
    "behavior": "case-manifest",
    "pressure": "scenario-manifest",
    "runtime-matrix": "runtime-manifest",
    "session-history": "session-manifest",
}
PLACEHOLDERS = frozenset(
    {"dummy", "example", "n/a", "na", "none", "placeholder", "tbd", "todo", "unknown", "unset"}
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_date(value: object, field: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{field} must be ISO-8601 date")
        return
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be ISO-8601 date")


def _is_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().casefold()
    return (
        not normalized
        or normalized in PLACEHOLDERS
        or normalized.startswith("todo:")
        or normalized.startswith("tbd:")
        or (normalized.startswith("<") and normalized.endswith(">"))
    )


def _is_exact_int(value: object) -> bool:
    return type(value) is int


def _is_unit_rate(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and 0.0 <= value <= 1.0


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


def _normalized_artifact_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("artifact path must be a non-empty string")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if pure.is_absolute() or windows.is_absolute() or windows.drive or "." in pure.parts or ".." in pure.parts:
        raise ValueError(f"unsafe promotion artifact path: {value}")
    return pure.as_posix().casefold()


def _artifact_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("artifact path must be a non-empty string")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if pure.is_absolute() or windows.is_absolute() or windows.drive or "." in pure.parts or ".." in pure.parts:
        raise ValueError(f"unsafe promotion artifact path: {value}")
    target = (root / pure).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"promotion artifact escapes root: {value}") from error
    return target


def _repository_root() -> Path:
    script = Path(__file__).resolve()
    for parent in script.parents:
        if (parent / "evals" / "schema" / "dogfood-result.schema.json").is_file():
            return parent
    raise ValueError("repository root with strict dogfood schemas is unavailable")


def _lifecycle_timestamp(
    value: object,
    *,
    label: str,
    now: dt.datetime,
    errors: list[str],
) -> dt.datetime | None:
    observed = _parse_timestamp(value)
    if observed is None:
        errors.append(f"{label} timestamp must be timezone-aware ISO-8601")
        return None
    observed = observed.astimezone(dt.timezone.utc)
    current = now.astimezone(dt.timezone.utc)
    if observed > current:
        errors.append(f"{label} timestamp is in the future")
    elif current - observed > MAX_LIFECYCLE_EVIDENCE_AGE:
        errors.append(f"{label} timestamp is stale")
    return observed


def _validate_lifecycle_details(
    details: object,
    *,
    kind: str,
    record: dict[str, Any],
    label: str,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    manifest_items: list[str] = []
    if not isinstance(details, dict):
        return [f"{label} details must be an object"], manifest_items
    if kind == "tier-b":
        expected_fields = {"cases_total", "cases_passed", "case_ids"}
        if set(details) != expected_fields:
            errors.append(f"{label} details must contain exactly {sorted(expected_fields)}")
        total = details.get("cases_total")
        passed = details.get("cases_passed")
        case_ids = details.get("case_ids")
        valid_total = _is_exact_int(total) and total > 0
        valid_passed = (
            _is_exact_int(passed)
            and passed >= 0
            and (not valid_total or passed <= total)
        )
        if not valid_total:
            errors.append(f"{label} cases_total must be a positive integer")
        if not valid_passed:
            errors.append(f"{label} cases_passed must be an integer from zero to cases_total")
        elif valid_total and passed != total:
            errors.append(f"{label} requires all tier-b cases to pass")
        valid_case_ids = (
            isinstance(case_ids, list)
            and all(isinstance(item, str) and not _is_placeholder(item) for item in case_ids)
        )
        if (
            not valid_case_ids
            or len(case_ids) != total
            or len(set(case_ids)) != len(case_ids)
        ):
            errors.append(f"{label} requires distinct substantive case_ids")
        else:
            manifest_items = list(case_ids)
    elif kind in {"behavior", "pressure"}:
        prefix = "cases" if kind == "behavior" else "scenarios"
        total_field = f"{prefix}_total"
        passed_field = f"{prefix}_passed"
        expected_fields = {total_field, passed_field, "pass_rate"}
        if set(details) != expected_fields:
            errors.append(f"{label} details must contain exactly {sorted(expected_fields)}")
        total = details.get(total_field)
        passed = details.get(passed_field)
        pass_rate = details.get("pass_rate")
        valid_total = _is_exact_int(total) and total > 0
        valid_passed = (
            _is_exact_int(passed)
            and passed >= 0
            and (not valid_total or passed <= total)
        )
        if not valid_total:
            errors.append(f"{label} {total_field} must be a positive integer")
        if not valid_passed:
            errors.append(
                f"{label} {passed_field} must be an integer from zero to {total_field}"
            )
        elif valid_total and passed != total:
            errors.append(f"{label} requires every observed case to pass")
        if not _is_unit_rate(pass_rate):
            errors.append(f"{label} pass_rate must be a finite number from 0.0 to 1.0")
        elif pass_rate != 1.0:
            errors.append(f"{label} pass_rate must be 1.0")
    elif kind == "runtime-matrix":
        expected_fields = {"targets", "passed_targets"}
        if set(details) != expected_fields:
            errors.append(f"{label} details must contain exactly {sorted(expected_fields)}")
        expected_targets = record.get("runtime_targets")
        if details.get("targets") != expected_targets or details.get("passed_targets") != expected_targets:
            errors.append(f"{label} must pass the complete promotion runtime matrix")
        elif isinstance(expected_targets, list):
            manifest_items = list(expected_targets)
    elif kind == "session-history":
        expected_fields = {
            "sessions_total",
            "pass_with_evidence",
            "unauthorized_writes",
            "retry_over_three_without_escalation",
        }
        if set(details) != expected_fields:
            errors.append(f"{label} details must contain exactly {sorted(expected_fields)}")
        total = details.get("sessions_total")
        pass_with_evidence = details.get("pass_with_evidence")
        unauthorized_writes = details.get("unauthorized_writes")
        retries = details.get("retry_over_three_without_escalation")
        if not _is_exact_int(total) or total <= 0:
            errors.append(f"{label} sessions_total must be a positive integer")
        if not _is_unit_rate(pass_with_evidence):
            errors.append(
                f"{label} pass_with_evidence must be a finite number from 0.0 to 1.0"
            )
        elif pass_with_evidence != 1.0:
            errors.append(f"{label} pass_with_evidence must be 1.0")
        if not _is_exact_int(unauthorized_writes) or unauthorized_writes < 0:
            errors.append(f"{label} unauthorized_writes must be a non-negative integer")
        elif unauthorized_writes != 0:
            errors.append(f"{label} unauthorized_writes must be 0")
        if not _is_exact_int(retries) or retries < 0:
            errors.append(
                f"{label} retry_over_three_without_escalation must be a non-negative integer"
            )
        elif retries != 0:
            errors.append(f"{label} retry_over_three_without_escalation must be 0")
    return errors, manifest_items


def _validate_lifecycle_artifact(
    path: Path,
    *,
    kind: str,
    record: dict[str, Any],
    now: dt.datetime,
    source_snapshots: set[str],
) -> tuple[list[str], list[dt.datetime]]:
    label = f"lifecycle evidence {kind}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"{label} must be a strict JSON envelope: {error}"], []
    if not isinstance(payload, dict) or set(payload) != LIFECYCLE_FIELDS:
        return [f"{label} must contain exactly {sorted(LIFECYCLE_FIELDS)}"], []
    errors: list[str] = []
    timestamps: list[dt.datetime] = []
    if not _is_exact_int(payload.get("schema_version")) or payload.get("schema_version") != 1:
        errors.append(f"{label} schema_version must be 1")
    expected = {
        "kind": kind,
        "skill_id": record.get("skill_id"),
        "profile": record.get("profile"),
        "runtime_targets": record.get("runtime_targets"),
        "verdict": "PASS",
        "owner": record.get("owner"),
        "reviewer": record.get("reviewer"),
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"{label} {field} does not match promotion record")
    runtime_targets = record.get("runtime_targets")
    if not isinstance(runtime_targets, list) or payload.get("runtime_target") not in runtime_targets:
        errors.append(f"{label} runtime_target is not selected by the promotion record")
    if payload.get("source_snapshot") not in source_snapshots:
        errors.append(f"{label} source_snapshot does not match selected dogfood evidence")
    if not _is_exact_int(payload.get("exit_code")) or payload.get("exit_code") != 0:
        errors.append(f"{label} exit_code must be 0")
    for field in (
        "kind",
        "skill_id",
        "profile",
        "runtime_target",
        "command",
        "runner",
        "source_snapshot",
        "owner",
        "reviewer",
    ):
        if _is_placeholder(payload.get(field)):
            errors.append(f"{label} {field} is missing or placeholder")
    observed = _lifecycle_timestamp(payload.get("timestamp"), label=label, now=now, errors=errors)
    if observed is not None:
        timestamps.append(observed)
    details = payload.get("details")
    detail_errors, expected_manifest_items = _validate_lifecycle_details(
        details,
        kind=kind,
        record=record,
        label=label,
    )
    errors.extend(detail_errors)

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append(f"{label} artifacts must contain runner provenance")
        return errors, timestamps
    expected_manifest_kind = LIFECYCLE_MANIFEST_KIND[kind]
    expected_kinds = {"runner-output", expected_manifest_kind}
    seen_kinds: set[str] = set()
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    nested_payloads: dict[str, dict[str, Any]] = {}
    for index, artifact in enumerate(artifacts):
        nested_label = f"{label} artifacts[{index}]"
        if not isinstance(artifact, dict) or set(artifact) != LIFECYCLE_NESTED_ARTIFACT_FIELDS:
            errors.append(f"{nested_label} must contain kind, path, and sha256")
            continue
        artifact_kind = artifact.get("kind")
        if artifact_kind in seen_kinds:
            errors.append(f"{label} has duplicate nested artifact kind: {artifact_kind}")
        elif isinstance(artifact_kind, str):
            seen_kinds.add(artifact_kind)
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            errors.append(f"{nested_label} sha256 must be lowercase hex")
            continue
        if digest in seen_hashes:
            errors.append(f"{label} nested artifacts must use distinct hashes")
        seen_hashes.add(digest)
        try:
            normalized = _normalized_artifact_path(artifact.get("path"))
            if normalized in seen_paths:
                errors.append(f"{label} has duplicate nested artifact path: {artifact.get('path')}")
            seen_paths.add(normalized)
            nested_path = _artifact_path(path.parent, artifact.get("path"))
        except ValueError as error:
            errors.append(f"{nested_label}: {error}")
            continue
        if not nested_path.is_file():
            errors.append(f"{nested_label} does not exist: {artifact.get('path')}")
            continue
        if _sha256(nested_path) != digest:
            errors.append(f"{nested_label} hash mismatch: {artifact.get('path')}")
            continue
        try:
            nested_payload = json.loads(nested_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"{nested_label} must be a JSON object: {error}")
            continue
        if not isinstance(nested_payload, dict):
            errors.append(f"{nested_label} must be a JSON object")
            continue
        if isinstance(artifact_kind, str):
            nested_payloads[artifact_kind] = nested_payload
    if seen_kinds != expected_kinds:
        errors.append(f"{label} artifacts must contain exactly {sorted(expected_kinds)}")

    runner_output = nested_payloads.get("runner-output")
    if runner_output is not None:
        if set(runner_output) != LIFECYCLE_RUNNER_FIELDS:
            errors.append(f"{label} runner-output must contain exact provenance fields")
        if (
            not _is_exact_int(runner_output.get("schema_version"))
            or runner_output.get("schema_version") != 1
        ):
            errors.append(f"{label} runner-output schema_version must be 1")
        if (
            not _is_exact_int(runner_output.get("exit_code"))
            or runner_output.get("exit_code") != 0
        ):
            errors.append(f"{label} runner-output exit_code must be 0")
        runner_expected = {
            "schema_version": 1,
            "kind": "runner-output",
            "evidence_kind": kind,
            "skill_id": record.get("skill_id"),
            "profile": record.get("profile"),
            "runtime_target": payload.get("runtime_target"),
            "source_snapshot": payload.get("source_snapshot"),
            "command": payload.get("command"),
            "exit_code": 0,
            "status": "PASS",
            "details": details,
        }
        for field, value in runner_expected.items():
            if runner_output.get(field) != value:
                errors.append(f"{label} runner-output {field} does not match envelope")
        runner_timestamp = _lifecycle_timestamp(
            runner_output.get("timestamp"),
            label=f"{label} runner-output",
            now=now,
            errors=errors,
        )
        if runner_timestamp is not None:
            timestamps.append(runner_timestamp)

    manifest = nested_payloads.get(expected_manifest_kind)
    if manifest is not None:
        if set(manifest) != LIFECYCLE_MANIFEST_FIELDS:
            errors.append(f"{label} {expected_manifest_kind} must contain exact provenance fields")
        if not _is_exact_int(manifest.get("schema_version")) or manifest.get("schema_version") != 1:
            errors.append(f"{label} {expected_manifest_kind} schema_version must be 1")
        manifest_expected = {
            "schema_version": 1,
            "kind": expected_manifest_kind,
            "evidence_kind": kind,
            "skill_id": record.get("skill_id"),
            "profile": record.get("profile"),
            "source_snapshot": payload.get("source_snapshot"),
        }
        for field, value in manifest_expected.items():
            if manifest.get(field) != value:
                errors.append(f"{label} {expected_manifest_kind} {field} does not match envelope")
        items = manifest.get("items")
        valid_items = (
            isinstance(items, list)
            and all(isinstance(item, str) and not _is_placeholder(item) for item in items)
        )
        if not valid_items or len(set(items)) != len(items):
            errors.append(f"{label} {expected_manifest_kind} items must be distinct substantive strings")
        elif kind in {"tier-b", "runtime-matrix"} and items != expected_manifest_items:
            errors.append(f"{label} {expected_manifest_kind} items do not match details")
        elif (
            kind == "behavior"
            and isinstance(details, dict)
            and len(items) != details.get("cases_total")
        ):
            errors.append(f"{label} case-manifest count does not match behavior details")
        elif (
            kind == "pressure"
            and isinstance(details, dict)
            and len(items) != details.get("scenarios_total")
        ):
            errors.append(f"{label} scenario-manifest count does not match pressure details")
        elif (
            kind == "session-history"
            and isinstance(details, dict)
            and len(items) != details.get("sessions_total")
        ):
            errors.append(f"{label} session-manifest count does not match session details")
        manifest_timestamp = _lifecycle_timestamp(
            manifest.get("timestamp"),
            label=f"{label} {expected_manifest_kind}",
            now=now,
            errors=errors,
        )
        if manifest_timestamp is not None:
            timestamps.append(manifest_timestamp)
    return errors, timestamps


def _validate_dogfood_result_artifact(
    path: Path,
    case_ids: list[str],
    *,
    profile: str,
    repository_root: Path,
) -> tuple[list[str], set[str], list[dt.datetime], set[str]]:
    report = evaluate_results(
        repository_root,
        path,
        artifact_root=path.parent,
        profile=profile,
    )
    if report["verdict"] != "PASS":
        reasons = [*report.get("failures", []), *report.get("blocked", [])]
        detail = "; ".join(str(reason) for reason in reasons) or "no verified PASS result"
        return [f"strict dogfood verdict is {report['verdict']}: {detail}"], set(), [], set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"dogfood result is not valid JSON: {error}"], set(), [], set()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return ["dogfood result must be a strict object with a results array"], set(), [], set()
    by_id: dict[str, dict[str, Any]] = {}
    for result in payload["results"]:
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            return ["dogfood result contains an invalid result entry"], set(), [], set()
        if result["id"] in by_id:
            return [f"dogfood result contains duplicate case: {result['id']}"], set(), [], set()
        by_id[result["id"]] = result
    errors: list[str] = []
    runtime_targets: set[str] = set()
    timestamps: list[dt.datetime] = []
    source_snapshots: set[str] = set()
    for case_id in case_ids:
        result = by_id.get(case_id)
        if result is None:
            errors.append(f"dogfood result is missing selected case: {case_id}")
            continue
        if result.get("verdict") != "PASS" or result.get("evidence_label") != "Verified" or result.get("exit_code") != 0:
            errors.append(f"strict dogfood result case is not verified PASS: {case_id}")
        runtime_target = result.get("runtime_target")
        if not isinstance(runtime_target, str) or _is_placeholder(runtime_target):
            errors.append(f"strict dogfood result case has invalid runtime_target: {case_id}")
        else:
            runtime_targets.add(runtime_target)
        timestamp = _parse_timestamp(result.get("timestamp"))
        if timestamp is None:
            errors.append(f"strict dogfood result case has invalid timestamp: {case_id}")
        else:
            timestamps.append(timestamp)
        source_snapshot = result.get("project_snapshot")
        if not isinstance(source_snapshot, str) or _is_placeholder(source_snapshot):
            errors.append(f"strict dogfood result case has invalid project_snapshot: {case_id}")
        else:
            source_snapshots.add(source_snapshot)
    if len(source_snapshots) > 1:
        errors.append("selected dogfood cases do not share one source_snapshot")
    return errors, runtime_targets, timestamps, source_snapshots


def validate_promotion_record(
    record: object,
    *,
    known_skills: Iterable[str],
    known_profiles: Iterable[str],
    profile_cases: dict[str, set[str]],
    artifact_root: Path | str | None = None,
    repository_root: Path | str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["promotion record must be a mapping"]
    if set(record) != RECORD_FIELDS:
        errors.append(f"promotion record fields must be {sorted(RECORD_FIELDS)}")
    known_skill_set = set(known_skills)
    known_profile_set = set(known_profiles)
    skill_id = record.get("skill_id")
    if skill_id not in known_skill_set:
        errors.append(f"unknown promotion skill: {skill_id}")
    source = record.get("from_maturity")
    target = record.get("target_maturity")
    if source not in MATURITY_ORDER or target not in MATURITY_ORDER:
        errors.append("promotion maturities must be experimental, beta, stable, or release")
    elif MATURITY_ORDER.index(target) != MATURITY_ORDER.index(source) + 1:
        errors.append(f"cannot skip maturity from {source} to {target}")
    profile = record.get("profile")
    if profile not in known_profile_set:
        errors.append(f"unknown promotion profile: {profile}")
    resolved_repository_root: Path | None = None
    if isinstance(profile, str) and profile in known_profile_set:
        try:
            resolved_repository_root = (
                Path(repository_root).resolve()
                if repository_root is not None
                else _repository_root()
            )
            profile_data = load_profile(resolved_repository_root, profile)
            promotion_scope = profile_data.get("promotion_scope")
            if not isinstance(promotion_scope, list) or skill_id not in promotion_scope:
                errors.append(
                    f"promotion skill {skill_id} is not selected by profile promotion_scope: {profile}"
                )
        except (OSError, ValueError) as error:
            errors.append(f"promotion profile validation unavailable: {error}")
    case_ids = record.get("case_ids")
    selected_case_ids: list[str] = []
    if not isinstance(case_ids, list) or not case_ids or not all(isinstance(item, str) and item.strip() for item in case_ids):
        errors.append("promotion case_ids must be a non-empty string list")
    else:
        selected_case_ids = case_ids
        if len(set(case_ids)) != len(case_ids):
            errors.append("promotion case_ids must not contain duplicates")
        if profile in profile_cases and not set(case_ids).issubset(profile_cases[profile]):
            errors.append(f"promotion case_ids are not selected by profile: {profile}")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("promotion evidence must be a non-empty list")
        evidence = []
    kinds: set[str] = set()
    dogfood_results = 0
    observed_runtime_targets: set[str] = set()
    selected_evidence_timestamps: list[dt.datetime] = []
    selected_source_snapshots: set[str] = set()
    pending_lifecycle: list[tuple[Path, str]] = []
    evidence_paths: set[str] = set()
    evidence_hashes: set[str] = set()
    current_time = dt.datetime.now(dt.timezone.utc)
    for index, artifact in enumerate(evidence):
        if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS:
            errors.append(f"promotion evidence[{index}] must contain kind, path, and sha256")
            continue
        kind = artifact.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            errors.append(f"promotion evidence[{index}] kind is required")
        elif kind in kinds:
            errors.append(f"duplicate promotion evidence kind: {kind}")
        else:
            kinds.add(kind)
            if kind == "dogfood-result":
                dogfood_results += 1
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            errors.append(f"promotion evidence[{index}] sha256 must be lowercase hex")
        else:
            if digest in evidence_hashes:
                errors.append(f"duplicate promotion evidence hash: {digest}")
            evidence_hashes.add(digest)
        try:
            normalized_path = _normalized_artifact_path(artifact.get("path"))
            if normalized_path in evidence_paths:
                errors.append(f"duplicate promotion evidence path: {artifact.get('path')}")
            evidence_paths.add(normalized_path)
        except ValueError as error:
            errors.append(str(error))
        if artifact_root is not None:
            try:
                target_path = _artifact_path(Path(artifact_root).resolve(), artifact.get("path"))
                if not target_path.is_file():
                    errors.append(f"promotion artifact does not exist: {artifact.get('path')}")
                elif _sha256(target_path) != digest:
                    errors.append(f"promotion artifact hash mismatch: {artifact.get('path')}")
                elif kind == "dogfood-result":
                    try:
                        repo_root = resolved_repository_root or _repository_root()
                        (
                            dogfood_errors,
                            runtime_targets,
                            evidence_timestamps,
                            source_snapshots,
                        ) = _validate_dogfood_result_artifact(
                            target_path,
                            selected_case_ids,
                            profile=str(profile),
                            repository_root=repo_root,
                        )
                        errors.extend(dogfood_errors)
                        observed_runtime_targets.update(runtime_targets)
                        selected_evidence_timestamps.extend(evidence_timestamps)
                        selected_source_snapshots.update(source_snapshots)
                    except (OSError, ValueError) as error:
                        errors.append(f"strict dogfood evaluation unavailable: {error}")
                elif kind in LIFECYCLE_KINDS:
                    pending_lifecycle.append((target_path, kind))
            except ValueError as error:
                errors.append(str(error))
    if dogfood_results != 1:
        errors.append("promotion evidence requires exactly one dogfood-result artifact")
    for lifecycle_path, lifecycle_kind in pending_lifecycle:
        lifecycle_errors, lifecycle_timestamps = _validate_lifecycle_artifact(
            lifecycle_path,
            kind=lifecycle_kind,
            record=record,
            now=current_time,
            source_snapshots=selected_source_snapshots,
        )
        errors.extend(lifecycle_errors)
        selected_evidence_timestamps.extend(lifecycle_timestamps)
    for field in ("owner", "reviewer"):
        if not isinstance(record.get(field), str) or _is_placeholder(record.get(field)):
            errors.append(f"promotion {field} is required and must not be a placeholder")
    if not isinstance(record.get("restore"), str) or _is_placeholder(record.get("restore")):
        errors.append("promotion restore is required and must not be a placeholder")
    parsed_dates: dict[str, dt.date] = {}
    for field in ("reviewed_at", "expires_at"):
        before = len(errors)
        _parse_date(record.get(field), field, errors)
        if len(errors) == before:
            parsed_dates[field] = dt.date.fromisoformat(str(record[field]))
    today = dt.date.today()
    if "reviewed_at" in parsed_dates and parsed_dates["reviewed_at"] > today:
        errors.append(f"promotion reviewed_at is in the future: {record['reviewed_at']}")
    if (
        "reviewed_at" in parsed_dates
        and "expires_at" in parsed_dates
        and parsed_dates["expires_at"] <= parsed_dates["reviewed_at"]
    ):
        errors.append("promotion expires_at must be after reviewed_at")
    if "expires_at" in parsed_dates and parsed_dates["expires_at"] < today:
        errors.append(f"promotion expires_at is expired: {record['expires_at']}")
    reviewed_at = parsed_dates.get("reviewed_at")
    if reviewed_at is not None:
        review_end = dt.datetime.combine(reviewed_at, dt.time.max, tzinfo=dt.timezone.utc)
        for observed in selected_evidence_timestamps:
            observed_utc = observed.astimezone(dt.timezone.utc)
            if observed_utc > review_end:
                errors.append("promotion evidence timestamp is after reviewed_at end-of-day")
                continue
            evidence_date = observed_utc.date()
            lag = (reviewed_at - evidence_date).days
            if lag < 0 or lag > MAX_REVIEW_LAG_DAYS:
                errors.append(
                    "promotion reviewed_at must be within "
                    f"{MAX_REVIEW_LAG_DAYS} days after selected promotion evidence"
                )
    runtime_targets = record.get("runtime_targets")
    if (
        not isinstance(runtime_targets, list)
        or not runtime_targets
        or not all(isinstance(item, str) and not _is_placeholder(item) for item in runtime_targets)
        or len(set(runtime_targets)) != len(runtime_targets)
    ):
        errors.append("promotion runtime_targets must be a unique non-placeholder string list")
    elif dogfood_results == 1 and not set(runtime_targets).issubset(observed_runtime_targets):
        errors.append(
            "promotion runtime_targets must be a subset of observed selected case runtime_targets"
        )
    limitations = record.get("limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        errors.append("promotion limitations must be a string list")
    if target == "stable" and not {"tier-b", "behavior", "pressure"}.issubset(kinds):
        errors.append("stable promotion requires tier-b, behavior, and pressure evidence")
    if target == "release" and not {"tier-b", "behavior", "pressure", "runtime-matrix", "session-history"}.issubset(kinds):
        errors.append("release promotion requires tier-b, behavior, pressure, runtime-matrix, and session-history evidence")
    return errors


def load_promotion_records(path: Path | str) -> list[dict[str, Any]]:
    registry_path = Path(path).resolve()
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("records"), list):
        raise ValueError("promotion evidence registry must contain schema_version 1 and records")
    schema_path = registry_path.parent.parent / PROMOTION_SCHEMA
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        )
        validation_errors = sorted(
            validator.iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as error:
        raise ValueError(f"promotion evidence schema is unavailable or invalid: {error}") from error
    if validation_errors:
        messages = []
        for error in validation_errors:
            location = "/".join(str(item) for item in error.absolute_path) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ValueError("promotion evidence schema validation failed: " + "; ".join(messages))
    return [record for record in payload["records"] if isinstance(record, dict)]
