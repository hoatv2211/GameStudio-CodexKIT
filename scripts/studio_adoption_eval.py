from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import jsonschema


BENCHMARK_PATH = Path("evals/adoption/studio-role-golden-paths.json")
RESULT_SCHEMA_PATH = Path("evals/schema/studio-adoption-result.schema.json")
TARGET_FIELDS = {
    "routing_success_rate",
    "max_question_count",
    "onboarding_time_to_verdict_seconds",
    "dependency_failures",
    "unauthorized_writes",
}


def _load_benchmark_payload(root: Path | str) -> dict[str, Any]:
    payload = json.loads((Path(root).resolve() / BENCHMARK_PATH).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("adoption benchmark requires schema_version 1 and cases")
    targets = payload.get("targets")
    if not isinstance(targets, dict) or set(targets) != TARGET_FIELDS:
        raise ValueError("adoption benchmark requires the exact target fields")
    routing_target = targets["routing_success_rate"]
    if (
        isinstance(routing_target, bool)
        or not isinstance(routing_target, (int, float))
        or not 0 <= routing_target <= 1
    ):
        raise ValueError("routing_success_rate target must be between 0 and 1")
    for field in TARGET_FIELDS - {"routing_success_rate"}:
        value = targets[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field} target must be a non-negative integer")
    ids = [str(case.get("id", "")) for case in payload["cases"]]
    if any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("adoption benchmark requires unique non-empty ids")
    if sum(bool(case.get("onboarding")) for case in payload["cases"]) != 1:
        raise ValueError("adoption benchmark requires exactly one onboarding case")
    return payload


def load_benchmark(root: Path | str) -> list[dict[str, Any]]:
    return [dict(case) for case in _load_benchmark_payload(root)["cases"]]


def load_targets(root: Path | str) -> dict[str, int | float]:
    return dict(_load_benchmark_payload(root)["targets"])


def _timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("adoption timestamps require timezone offsets")
    return parsed


def _blocked(total: int, reason: str) -> dict[str, Any]:
    return {
        "verdict": "BLOCKED",
        "total": total,
        "failures": [reason],
        "metrics": {
            "routing_success_rate": None,
            "max_question_count": None,
            "median_time_to_verdict_seconds": None,
            "onboarding_time_to_verdict_seconds": None,
            "dependency_failures": None,
            "unauthorized_writes": None,
        },
    }


def _artifact_failures(root: Path, case_id: str, run: dict[str, Any]) -> list[str]:
    artifact = Path(run["artifact"])
    if artifact.is_absolute():
        return [f"{case_id}: artifact must be repository-relative"]
    resolved = (root / artifact).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return [f"{case_id}: artifact escapes repository root"]
    if not resolved.is_file():
        return [f"{case_id}: artifact file does not exist: {run['artifact']}"]
    try:
        observed_sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as error:
        return [f"{case_id}: artifact could not be read: {error}"]
    if observed_sha256 != run["artifact_sha256"]:
        return [f"{case_id}: artifact sha256 mismatch"]
    return []


def evaluate_adoption(
    root: Path | str, results_path: Path | str | None = None
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    cases = load_benchmark(root_path)
    targets = load_targets(root_path)
    if results_path is None:
        return _blocked(len(cases), "No governed studio adoption results were supplied")

    schema = json.loads((root_path / RESULT_SCHEMA_PATH).read_text(encoding="utf-8"))
    try:
        payload = json.loads(Path(results_path).read_text(encoding="utf-8"))
    except OSError as error:
        return {
            **_blocked(len(cases), "Adoption results could not be read"),
            "verdict": "FAIL",
            "failures": [
                f"adoption results could not be read: {error.__class__.__name__}"
            ],
        }
    except json.JSONDecodeError as error:
        return {
            **_blocked(len(cases), "Adoption results file is invalid JSON"),
            "verdict": "FAIL",
            "failures": [
                "adoption results file is invalid JSON at "
                f"line {error.lineno} column {error.colno}"
            ],
        }
    try:
        jsonschema.validate(payload, schema, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as error:
        return {
            **_blocked(len(cases), "Invalid adoption result schema"),
            "verdict": "FAIL",
            "failures": [f"result schema: {error.message}"],
        }

    case_by_id = {case["id"]: case for case in cases}
    run_by_id = {run["id"]: run for run in payload["runs"]}
    failures: list[str] = []
    if len(run_by_id) != len(payload["runs"]):
        failures.append("duplicate adoption result ids")
    missing = sorted(set(case_by_id) - set(run_by_id))
    unknown = sorted(set(run_by_id) - set(case_by_id))
    if missing:
        failures.append(f"missing adoption result ids: {missing}")
    if unknown:
        failures.append(f"unknown adoption result ids: {unknown}")
    if failures:
        return {
            **_blocked(len(cases), failures[0]),
            "verdict": "FAIL",
            "failures": failures,
        }

    durations: list[float] = []
    route_successes = 0
    max_questions = 0
    dependency_failures = 0
    unauthorized_writes = 0
    onboarding_seconds: float | None = None
    non_pass_verdicts: list[str] = []
    for case_id, case in case_by_id.items():
        run = run_by_id[case_id]
        failures.extend(_artifact_failures(root_path, case_id, run))
        if run["task_verdict"] != "PASS":
            non_pass_verdicts.append(f"{case_id}={run['task_verdict']}")
        started = _timestamp(run["started_at"])
        finished = _timestamp(run["verdict_at"])
        duration = (finished - started).total_seconds()
        if duration < 0:
            failures.append(f"{case_id}: verdict_at precedes started_at")
            continue
        durations.append(duration)
        if run["selected_golden_path"] == case["expected_golden_path"]:
            route_successes += 1
        max_questions = max(max_questions, int(run["question_count"]))
        dependency_failures += int(bool(run["dependency_failure"]))
        unauthorized_writes += int(run["unauthorized_writes"])
        if case["onboarding"]:
            onboarding_seconds = duration

    if non_pass_verdicts:
        failures.append(f"task verdicts not PASS: {non_pass_verdicts}")

    routing_success = route_successes / len(cases)
    metrics = {
        "routing_success_rate": routing_success,
        "max_question_count": max_questions,
        "median_time_to_verdict_seconds": statistics.median(durations) if durations else None,
        "onboarding_time_to_verdict_seconds": onboarding_seconds,
        "dependency_failures": dependency_failures,
        "unauthorized_writes": unauthorized_writes,
    }
    routing_target = float(targets["routing_success_rate"])
    question_target = int(targets["max_question_count"])
    onboarding_target = int(targets["onboarding_time_to_verdict_seconds"])
    dependency_target = int(targets["dependency_failures"])
    mutation_target = int(targets["unauthorized_writes"])
    if routing_success < routing_target:
        failures.append(
            f"routing success {routing_success:.3f} is below {routing_target:.3f}"
        )
    if max_questions > question_target:
        failures.append(f"question count {max_questions} exceeds {question_target}")
    if onboarding_seconds is None or onboarding_seconds > onboarding_target:
        failures.append(
            f"install-to-first-use time {onboarding_seconds} exceeds "
            f"{onboarding_target} seconds"
        )
    if dependency_failures > dependency_target:
        failures.append(
            f"dependency failures observed: {dependency_failures} exceeds "
            f"{dependency_target}"
        )
    if unauthorized_writes > mutation_target:
        failures.append(
            f"unauthorized writes observed: {unauthorized_writes} exceeds "
            f"{mutation_target}"
        )
    return {
        "verdict": "FAIL" if failures else "PASS",
        "total": len(cases),
        "failures": failures,
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate governed Role UX adoption metrics.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--status", type=Path)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.export:
        cases = load_benchmark(root)
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text(
            "".join(json.dumps(case, sort_keys=True, ensure_ascii=False) + "\n" for case in cases),
            encoding="utf-8",
        )
        print(f"studio-adoption-export: {len(cases)} cases")
    if args.status:
        args.status.parent.mkdir(parents=True, exist_ok=True)
        args.status.write_text(
            json.dumps(_blocked(len(load_benchmark(root)), "No governed studio adoption results were supplied"), indent=2) + "\n",
            encoding="utf-8",
        )
        print(args.status)
    if args.results:
        report = evaluate_adoption(root, args.results)
    elif args.export or args.status:
        return 0
    else:
        report = evaluate_adoption(root)
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "PASS" else 2 if report["verdict"] == "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
