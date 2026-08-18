from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

try:
    from scripts.dogfood_eval import evaluate_results, load_cases, load_profile
except ModuleNotFoundError:
    from dogfood_eval import evaluate_results, load_cases, load_profile


FPC_SCOPES = (
    "client/LineRWebGL/Assets/Game/RunTimeRes",
    "client/LineRWebGL/Assets/Game/Lua",
    "tools/localization",
    "tests/localization",
)
RUNTIME_CASE = "fpc-unity-localization-runtime"
RUNTIME_MANIFEST_NAME = "runtime-evidence-manifest.json"
RUNTIME_MANIFEST_FIELDS = {
    "schema_version",
    "case_id",
    "profile",
    "workflow",
    "runtime_target",
    "command",
    "exit_code",
    "reviewer",
    "timestamp",
    "unauthorized_write",
    "restore",
    "project_snapshot",
    "artifacts",
}
RUNTIME_ARTIFACT_FIELDS = {"kind", "path", "sha256"}
RUNTIME_REQUIRED_CALLS = {
    ("read_mcp_resource", "mcpforunity://editor/state"),
    ("run_tests", "editmode"),
    ("get_test_job", "editmode"),
    ("run_tests", "playmode"),
    ("get_test_job", "playmode"),
    ("read_console", "get"),
}
RUNTIME_ASSERTION_CALLS = {
    ("execute_code", "execute"),
    ("execute_custom_tool", "assert_localization"),
}


class RuntimeEvidenceUnavailable(ValueError):
    """The governed runtime collection is absent or incomplete."""


class RuntimeEvidenceInvalid(ValueError):
    """The supplied runtime collection violates integrity or provenance."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_git(project: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git command failed: {arguments}")
    return completed.stdout.strip()


def _scope_files(project: Path, scopes: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for scope in scopes:
        candidate = (project / PurePosixPath(scope)).resolve()
        try:
            candidate.relative_to(project.resolve())
        except ValueError as error:
            raise ValueError(f"scope escapes project: {scope}") from error
        if candidate.is_file():
            files.add(candidate)
            continue
        if not candidate.is_dir():
            continue
        for path in candidate.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    files.add(path.resolve())
            except OSError:
                continue
    return sorted(files, key=lambda path: path.relative_to(project).as_posix())


def scope_manifest_digest(project: Path | str, scopes: Iterable[str]) -> str:
    project_path = Path(project).resolve()
    entries: list[dict[str, str]] = []
    for path in _scope_files(project_path, scopes):
        relative = path.relative_to(project_path).as_posix()
        entries.append({"path": relative, "sha256": _sha256_file(path)})
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def snapshot_project(project: Path | str, scopes: Iterable[str] = FPC_SCOPES) -> dict[str, Any]:
    project_path = Path(project).resolve()
    try:
        branch = _run_git(project_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        head = _run_git(project_path, ["rev-parse", "HEAD"])
        status = _run_git(project_path, ["status", "--porcelain=v1", "--untracked-files=all"])
    except (OSError, RuntimeError) as error:
        branch = "unavailable"
        head = "unavailable"
        status = f"git-unavailable: {error}"
    return {
        "repository": project_path.name,
        "repository_path": str(project_path),
        "branch": branch,
        "head": head,
        "dirty": bool(status),
        "dirty_digest": _sha256_bytes(status.encode("utf-8")),
        "scope_paths": list(scopes),
        "scope_digest": scope_manifest_digest(project_path, scopes),
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def _write_artifact(output_root: Path, relative: str, content: str | bytes, kind: str) -> dict[str, str]:
    normalized = PurePosixPath(relative)
    if normalized.is_absolute() or ".." in normalized.parts or "." in normalized.parts:
        raise ValueError(f"unsafe evidence artifact path: {relative}")
    destination = output_root.joinpath(*normalized.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = content.encode("utf-8") if isinstance(content, str) else content
    destination.write_bytes(raw)
    return {
        "kind": kind,
        "path": normalized.as_posix(),
        "sha256": _sha256_file(destination),
    }


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _canonical_project_snapshot(snapshot: dict[str, Any]) -> str:
    repository = snapshot.get("repository")
    head = snapshot.get("head")
    dirty_digest = snapshot.get("dirty_digest")
    if (
        not isinstance(repository, str)
        or not repository.strip()
        or not isinstance(head, str)
        or len(head) < 7
        or any(character not in "0123456789abcdef" for character in head.casefold())
        or not isinstance(dirty_digest, str)
        or len(dirty_digest) != 64
        or any(character not in "0123456789abcdef" for character in dirty_digest.casefold())
    ):
        raise RuntimeEvidenceInvalid("current project snapshot has no canonical git identity")
    return f"{repository}@{head}+dirty:{dirty_digest[:12]}"


def _safe_artifact_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeEvidenceInvalid("runtime artifact path must be a non-empty string")
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
        raise RuntimeEvidenceInvalid(f"unsafe runtime artifact path: {value}")
    target = root.joinpath(*pure.parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeEvidenceInvalid(
            f"runtime artifact path escapes evidence root: {value}"
        ) from error
    return target


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeEvidenceInvalid(
            f"{label} must be a UTF-8 JSON object: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeEvidenceInvalid(f"{label} must be a UTF-8 JSON object")
    return payload


def _runtime_manifest_path(runtime_evidence: Path | str | None) -> Path:
    if runtime_evidence is None:
        raise RuntimeEvidenceUnavailable(
            "Unity MCP runtime evidence was not supplied; collect a governed runtime bundle"
        )
    supplied = Path(runtime_evidence).resolve()
    manifest = supplied / RUNTIME_MANIFEST_NAME if supplied.is_dir() else supplied
    if not manifest.is_file():
        raise RuntimeEvidenceUnavailable(
            f"runtime evidence manifest is unavailable: {manifest}"
        )
    return manifest


def _exact_fields(payload: dict[str, Any], expected: set[str], *, label: str) -> None:
    missing = sorted(expected - set(payload))
    unexpected = sorted(set(payload) - expected)
    failures: list[str] = []
    if missing:
        failures.append(f"missing fields {missing}")
    if unexpected:
        failures.append(f"unexpected fields {unexpected}")
    if failures:
        raise RuntimeEvidenceInvalid(f"{label} " + "; ".join(failures))


def _normalized_unity_tool(value: object) -> str:
    if not isinstance(value, str):
        return ""
    prefix = "mcp__unityMCP__"
    return value[len(prefix) :] if value.startswith(prefix) else value


def _require_completed_runtime_calls(transcript: dict[str, Any]) -> None:
    calls = transcript.get("tool_calls")
    if not isinstance(calls, list):
        raise RuntimeEvidenceUnavailable(
            "runtime evidence is incomplete: MCP transcript has no tool_calls list"
        )
    observed: set[tuple[str, str]] = set()
    for call in calls:
        if not isinstance(call, dict):
            continue
        tool = _normalized_unity_tool(call.get("tool"))
        operation = call.get("operation")
        if isinstance(operation, str):
            observed.add((tool, operation.casefold()))
    missing = sorted(RUNTIME_REQUIRED_CALLS - observed)
    if not observed.intersection(RUNTIME_ASSERTION_CALLS):
        missing.append(("execute_code or execute_custom_tool", "runtime assertion"))
    if missing:
        rendered = ", ".join(f"{tool}/{operation}" for tool, operation in missing)
        raise RuntimeEvidenceUnavailable(
            f"runtime evidence is incomplete; missing completed MCP calls: {rendered}"
        )


def _validate_runtime_project_snapshot(
    evidence_root: Path,
    artifacts: dict[str, tuple[dict[str, str], Path]],
    manifest: dict[str, Any],
    snapshot: dict[str, Any],
) -> None:
    _canonical_project_snapshot(snapshot)
    snapshot_entry = artifacts.get("project-snapshot")
    if snapshot_entry is None:
        raise RuntimeEvidenceUnavailable(
            "runtime evidence is incomplete: missing project-snapshot artifact"
        )
    payload = _json_object(snapshot_entry[1], label="runtime project-snapshot artifact")
    evidence_snapshot = _canonical_project_snapshot(payload)
    if manifest.get("project_snapshot") != evidence_snapshot:
        raise RuntimeEvidenceInvalid(
            "runtime evidence project_snapshot does not match current project snapshot"
        )
    for field in ("repository", "head", "scope_paths", "scope_digest"):
        if payload.get(field) != snapshot.get(field):
            raise RuntimeEvidenceInvalid(
                f"runtime project-snapshot {field} does not match current project"
            )
    repository_path = payload.get("repository_path")
    current_path = snapshot.get("repository_path")
    if (
        not isinstance(repository_path, str)
        or not repository_path.strip()
        or not Path(repository_path).is_absolute()
    ):
        raise RuntimeEvidenceInvalid(
            "runtime project-snapshot repository_path must be a canonical absolute path"
        )
    if (
        not isinstance(current_path, str)
        or not current_path.strip()
        or not Path(current_path).is_absolute()
    ):
        raise RuntimeEvidenceInvalid(
            "current project snapshot repository_path must be a canonical absolute path"
        )
    if Path(repository_path).resolve() != Path(current_path).resolve():
        raise RuntimeEvidenceInvalid(
            "runtime project-snapshot repository_path does not match current project"
        )


def _copy_runtime_artifacts(
    evidence_root: Path,
    output_root: Path,
    references: list[dict[str, str]],
) -> list[dict[str, str]]:
    validated: list[tuple[dict[str, str], Path, Path]] = []
    for reference in references:
        source = _safe_artifact_path(evidence_root, reference["path"])
        if not source.is_file():
            raise RuntimeEvidenceUnavailable(
                f"runtime evidence artifact is unavailable: {reference['path']}"
            )
        if source.is_symlink():
            raise RuntimeEvidenceInvalid(
                f"runtime evidence artifact must not be a symlink: {reference['path']}"
            )
        observed = _sha256_file(source)
        if observed != reference["sha256"]:
            raise RuntimeEvidenceInvalid(
                f"runtime evidence artifact sha256 mismatch: {reference['path']}"
            )
        destination = _safe_artifact_path(output_root, reference["path"])
        if destination.exists() and destination.resolve() != source.resolve():
            if not destination.is_file() or _sha256_file(destination) != observed:
                raise RuntimeEvidenceInvalid(
                    f"runtime evidence destination already contains different data: "
                    f"{reference['path']}"
                )
        validated.append((reference, source, destination))

    for _, source, destination in validated:
        if source.resolve() == destination.resolve() or destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return [dict(reference) for reference, _, _ in validated]


def load_runtime_result(
    runtime_evidence: Path | str | None,
    *,
    case: dict[str, Any],
    profile: str,
    output_root: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = _runtime_manifest_path(runtime_evidence)
    manifest = _json_object(manifest_path, label="runtime evidence manifest")
    _exact_fields(manifest, RUNTIME_MANIFEST_FIELDS, label="runtime evidence manifest")
    expected_values = {
        "schema_version": 1,
        "case_id": case["id"],
        "profile": profile,
        "workflow": case["workflow"],
        "exit_code": 0,
        "unauthorized_write": False,
    }
    for field, expected in expected_values.items():
        if manifest.get(field) != expected:
            raise RuntimeEvidenceInvalid(
                f"runtime evidence manifest {field} must be {expected!r}"
            )
    for field in ("runtime_target", "command", "reviewer", "timestamp", "restore"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise RuntimeEvidenceInvalid(
                f"runtime evidence manifest {field} must be substantive"
            )
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise RuntimeEvidenceUnavailable(
            "runtime evidence manifest has no artifact references"
        )
    references: list[dict[str, str]] = []
    artifacts: dict[str, tuple[dict[str, str], Path]] = {}
    paths: set[str] = set()
    evidence_root = manifest_path.parent.resolve()
    for index, raw in enumerate(raw_artifacts):
        if not isinstance(raw, dict):
            raise RuntimeEvidenceInvalid(
                f"runtime evidence artifact {index} must be an object"
            )
        _exact_fields(raw, RUNTIME_ARTIFACT_FIELDS, label=f"runtime evidence artifact {index}")
        kind = raw.get("kind")
        path_value = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(kind, str) or not kind.strip():
            raise RuntimeEvidenceInvalid(
                f"runtime evidence artifact {index} kind must be substantive"
            )
        if kind in artifacts:
            raise RuntimeEvidenceInvalid(f"duplicate runtime evidence artifact kind: {kind}")
        source = _safe_artifact_path(evidence_root, path_value)
        normalized_path = str(path_value).replace("\\", "/").casefold()
        if normalized_path in paths:
            raise RuntimeEvidenceInvalid(
                f"duplicate runtime evidence artifact path: {path_value}"
            )
        paths.add(normalized_path)
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise RuntimeEvidenceInvalid(
                f"runtime evidence artifact {index} sha256 must be lowercase sha256"
            )
        reference = {"kind": kind, "path": str(path_value), "sha256": digest}
        references.append(reference)
        artifacts[kind] = (reference, source)

    missing_kinds = sorted(set(case["required_artifacts"]) - set(artifacts))
    if missing_kinds:
        raise RuntimeEvidenceUnavailable(
            f"runtime evidence is incomplete; missing artifact kinds: {missing_kinds}"
        )
    for kind, (_, path) in artifacts.items():
        if not path.is_file():
            raise RuntimeEvidenceUnavailable(
                f"runtime evidence artifact is unavailable: {kind} ({path})"
            )
        observed = _sha256_file(path)
        if observed != artifacts[kind][0]["sha256"]:
            raise RuntimeEvidenceInvalid(
                f"runtime evidence artifact sha256 mismatch: {artifacts[kind][0]['path']}"
            )

    _validate_runtime_project_snapshot(evidence_root, artifacts, manifest, snapshot)
    transcript = _json_object(artifacts["mcp-transcript"][1], label="mcp-transcript artifact")
    _require_completed_runtime_calls(transcript)
    copied = _copy_runtime_artifacts(evidence_root, output_root, references)

    result = _base_result(case, snapshot, manifest["reviewer"])
    result.update(
        {
            "verdict": "PASS",
            "evidence_label": "Verified",
            "runtime_target": manifest["runtime_target"],
            "command": manifest["command"],
            "exit_code": manifest["exit_code"],
            "artifacts": copied,
            "project_snapshot": manifest["project_snapshot"],
            "reviewer": manifest["reviewer"],
            "timestamp": manifest["timestamp"],
            "unauthorized_write": manifest["unauthorized_write"],
            "restore": manifest["restore"],
            "reason": None,
        }
    )
    return result


def _base_result(
    case: dict[str, Any],
    snapshot: dict[str, Any],
    reviewer: str,
    runtime_target: str = "Codex App/CLI",
) -> dict[str, Any]:
    return {
        "id": case["id"],
        "workflow": case["workflow"],
        "verdict": "BLOCKED",
        "evidence_label": "BLOCKED",
        "runtime_target": runtime_target,
        "command": None,
        "exit_code": None,
        "artifacts": [],
        "project_snapshot": f"{snapshot['repository']}@{snapshot['head']}+dirty:{snapshot['dirty_digest'][:12]}",
        "reviewer": reviewer,
        "timestamp": _timestamp(),
        "unauthorized_write": False,
        "restore": "Certification-only; no FPC mutation was performed",
        "reason": None,
    }


def run_static_case(
    project: Path,
    case: dict[str, Any],
    output_root: Path,
    snapshot: dict[str, Any],
    *,
    reviewer: str = "Codex certification runner",
) -> dict[str, Any]:
    script = project / "tools" / "localization" / "audit_global_prefab_text.py"
    if not script.is_file():
        result = _base_result(case, snapshot, reviewer)
        result["reason"] = f"missing static localization audit: {script}"
        return result
    command = [sys.executable, "-B", str(script), "--profile", "global-webgl-beta"]
    if case["id"] == "fpc-localization-doctor":
        command.append("--strict")
    try:
        completed = subprocess.run(
            command,
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as error:
        result = _base_result(case, snapshot, reviewer)
        result["reason"] = f"static audit runner unavailable: {error}"
        return result

    result = _base_result(case, snapshot, reviewer)
    result["command"] = subprocess.list2cmdline(command)
    result["exit_code"] = completed.returncode
    report_kind = "doctor-report" if case["id"] == "fpc-localization-doctor" else "localization-report"
    report_content = completed.stdout + (
        "\nSTDERR:\n" + completed.stderr if completed.stderr else ""
    )
    if not report_content.strip():
        report_content = (
            f"command={subprocess.list2cmdline(command)}\n"
            f"exit_code={completed.returncode}\n"
        )
    result["artifacts"] = [
        {"kind": "project-snapshot", "path": "project-snapshot.json", "sha256": _sha256_file(output_root / "project-snapshot.json")},
        _write_artifact(
            output_root,
            f"{case['id']}/command-log.json",
            json.dumps(
                {
                    "command": subprocess.list2cmdline(command),
                    "cwd": str(project),
                    "exit_code": completed.returncode,
                    "runtime_target": result["runtime_target"],
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "captured_at": _timestamp(),
                },
                indent=2,
            )
            + "\n",
            "command-log",
        ),
        _write_artifact(
            output_root,
            f"{case['id']}/{report_kind}.txt",
            report_content,
            report_kind,
        ),
    ]
    if completed.returncode == 0:
        result["verdict"] = "PASS"
        result["evidence_label"] = "Verified"
    else:
        result["verdict"] = "FAIL"
        result["evidence_label"] = "Verified"
        result["reason"] = f"strict audit exit code {completed.returncode}; inspect {report_kind}"
    result["artifacts"].append(
        _write_artifact(
            output_root,
            f"{case['id']}/verdict.json",
            json.dumps({"verdict": result["verdict"], "reason": result["reason"]}, indent=2) + "\n",
            "verdict",
        )
    )
    return result


def certify(
    project: Path | str,
    *,
    profile: str,
    output_root: Path | str,
    runtime_evidence: Path | str | None = None,
    mcp_available: bool = False,
    reviewer: str = "Codex certification runner",
) -> Path:
    kit_root = Path(__file__).resolve().parents[1]
    profile_data = load_profile(kit_root, profile)
    cases = load_cases(kit_root, profile=profile)
    project_path = Path(project).resolve()
    output_path = Path(output_root).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_project(project_path)
    _write_artifact(output_path, "project-snapshot.json", json.dumps(snapshot, indent=2) + "\n", "project-snapshot")
    results: list[dict[str, Any]] = []
    for case in cases:
        if case["id"] == RUNTIME_CASE:
            try:
                result = load_runtime_result(
                    runtime_evidence,
                    case=case,
                    profile=profile,
                    output_root=output_path,
                    snapshot=snapshot,
                )
            except RuntimeEvidenceUnavailable as error:
                result = _base_result(case, snapshot, reviewer)
                prefix = (
                    "--mcp-available is deprecated as certification evidence; "
                    if mcp_available
                    else ""
                )
                result["reason"] = prefix + str(error)
            except RuntimeEvidenceInvalid as error:
                result = _base_result(case, snapshot, reviewer)
                result["verdict"] = "FAIL"
                result["evidence_label"] = "Verified"
                result["reason"] = str(error)
            results.append(result)
            continue
        base = _base_result(case, snapshot, reviewer)
        base.update(run_static_case(project_path, case, output_path, snapshot, reviewer=reviewer))
        results.append(base)
    results_path = output_path / "results.json"
    results_path.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    runtime_result = next((item for item in results if item["id"] == RUNTIME_CASE), None)
    if runtime_result is not None and runtime_result["verdict"] == "PASS":
        report = evaluate_results(
            kit_root,
            results_path,
            artifact_root=output_path,
            profile=profile,
        )
        if report["verdict"] != "PASS":
            details = report["failures"] or report["blocked"] or ["unknown validation error"]
            runtime_result["verdict"] = "FAIL" if report["verdict"] == "FAIL" else "BLOCKED"
            runtime_result["evidence_label"] = (
                "Verified" if runtime_result["verdict"] == "FAIL" else "BLOCKED"
            )
            runtime_result["reason"] = (
                f"strict offline dogfood validation {report['verdict']}: "
                + "; ".join(str(item) for item in details)
            )
            results_path.write_text(
                json.dumps({"results": results}, indent=2) + "\n",
                encoding="utf-8",
            )
    (output_path / "artifact-root.txt").write_text(str(output_path) + "\n", encoding="utf-8")
    return results_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run certification-only FPC localization dogfood.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--profile", default="fpc-global-localization-static")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--runtime-evidence",
        type=Path,
        help=(
            "Runtime evidence manifest, or a directory containing "
            f"{RUNTIME_MANIFEST_NAME}."
        ),
    )
    parser.add_argument(
        "--mcp-available",
        action="store_true",
        help="Deprecated diagnostic flag; it cannot produce a runtime PASS.",
    )
    args = parser.parse_args(argv)
    try:
        results_path = certify(
            args.project,
            profile=args.profile,
            output_root=args.output,
            runtime_evidence=args.runtime_evidence,
            mcp_available=args.mcp_available,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    report = evaluate_results(
        Path(__file__).resolve().parents[1],
        results_path,
        artifact_root=args.output,
        profile=args.profile,
    )
    print(results_path)
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "PASS" else 2 if report["verdict"] == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
