from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable


MANIFEST_FIELDS = {"schema_version", "mode", "operation_id", "root", "backup_root", "operations"}
OPERATION_FIELDS = {
    "path",
    "action",
    "before_sha256",
    "after_sha256",
    "backup",
    "restore",
}
RESTORE_PROGRESS_FIELDS = {
    "schema_version",
    "operation_id",
    "manifest_digest",
    "mode",
    "completed",
}
RESTORE_RECOVERY_FIELDS = {
    "schema_version",
    "mode",
    "operation_id",
    "manifest_digest",
    "issues",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str | None:
    return _sha256_bytes(path.read_bytes()) if path.is_file() else None


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _assert_safe_components(root: Path, target: Path) -> None:
    root_resolved = root.resolve()
    try:
        relative = target.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"path escapes approved root: {target}") from error
    current = root_resolved
    if _is_reparse_point(current):
        raise ValueError(f"approved root is a symlink or reparse point: {current}")
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_reparse_point(current):
            raise ValueError(f"symlink or reparse point is not allowed: {current}")


def _target(root: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/")
    if not normalized or Path(normalized).is_absolute():
        raise ValueError(f"mutation path must be relative: {relative!r}")
    root_resolved = root.resolve()
    candidate = root_resolved / normalized
    _assert_safe_components(root_resolved, candidate)
    target = candidate.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"mutation path escapes root: {relative}") from error
    return target


def _normalized_operations(root: Path, operations: list[dict[str, str]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in operations:
        if set(operation) != {"path", "content"}:
            raise ValueError("each operation requires only path and content")
        relative = operation["path"].replace("\\", "/")
        collision_key = relative.casefold()
        if collision_key in seen:
            raise ValueError(f"duplicate mutation path: {relative}")
        seen.add(collision_key)
        target = _target(root, relative)
        if target.exists() and not target.is_file():
            raise ValueError(f"mutation target must be a regular file: {relative}")
        content = operation["content"].encode("utf-8")
        normalized.append(
            {
                "path": relative,
                "target": target,
                "content": content,
                "before_exists": target.exists(),
                "before_sha256": _sha256_path(target),
                "after_sha256": _sha256_bytes(content),
            }
        )
    return normalized


def _operation_precondition(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": item["path"],
        "action": "update" if item["before_exists"] else "create",
        "before_sha256": item["before_sha256"],
        "after_sha256": item["after_sha256"],
    }


def _normalized_expected_operations(
    expected_operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    required = {"path", "action", "before_sha256", "after_sha256"}
    allowed = required | {"restore"}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in expected_operations:
        if (
            not isinstance(operation, dict)
            or not required.issubset(operation)
            or not set(operation).issubset(allowed)
        ):
            raise ValueError(
                "expected operations require path, action, before_sha256, and after_sha256"
            )
        relative = str(operation["path"]).replace("\\", "/")
        collision_key = relative.casefold()
        if collision_key in seen:
            raise ValueError(f"duplicate expected mutation path: {relative}")
        seen.add(collision_key)
        action = operation["action"]
        if action not in {"create", "update"}:
            raise ValueError(f"invalid expected mutation action: {action}")
        normalized.append(
            {
                "path": relative,
                "action": action,
                "before_sha256": operation["before_sha256"],
                "after_sha256": operation["after_sha256"],
            }
        )
    return sorted(normalized, key=lambda operation: operation["path"])


def _assert_target_pre_state(item: dict[str, Any]) -> None:
    target: Path = item["target"]
    exists = target.exists()
    current_sha256 = _sha256_path(target)
    if exists != item["before_exists"] or current_sha256 != item["before_sha256"]:
        raise ValueError(f"target pre-state changed before mutation: {item['path']}")


def report_mutation(root: Path | str, operations: list[dict[str, str]]) -> dict[str, Any]:
    root_path = Path(root).resolve()
    normalized = _normalized_operations(root_path, operations)
    report = {
        "mode": "report-only",
        "root": str(root_path),
        "operations": [
            {
                "path": item["path"],
                "action": "update" if item["before_exists"] else "create",
                "before_sha256": item["before_sha256"],
                "after_sha256": item["after_sha256"],
                "restore": "restore backup" if item["before_exists"] else "remove created file",
            }
            for item in normalized
        ],
    }
    report["plan_digest"] = _mutation_plan_digest(report)
    return report


def _mutation_plan_digest(report: dict[str, Any]) -> str:
    payload = {
        "root": report["root"],
        "operations": report["operations"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _serialized_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


_ATOMIC_REPLACE = os.replace
_REPLACE_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.05


def _replace_with_retry(
    replace: Callable[[Path, Path], None],
    source: Path,
    target: Path,
    *,
    before_attempt: Callable[[], None] | None = None,
) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        if before_attempt is not None:
            before_attempt()
        try:
            replace(source, target)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    payload = _serialized_json_bytes(manifest)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(_ATOMIC_REPLACE, temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if not path.is_file() or path.read_bytes() != _serialized_json_bytes(manifest):
        raise RuntimeError(f"manifest verification failed: {path}")


def _write_owned_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_manifest(path, payload)
    _verify_manifest(path, payload)


def _ownership_digest(manifest: dict[str, Any]) -> str:
    payload = {
        "operation_id": manifest["operation_id"],
        "root": manifest["root"],
        "backup_root": manifest["backup_root"],
        "operations": manifest["operations"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ownership_sidecar_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": manifest["operation_id"],
        "manifest_digest": _ownership_digest(manifest),
    }


def _write_ownership_sidecar(backup_root: Path, manifest: dict[str, Any]) -> None:
    (backup_root / "ownership.json").write_bytes(
        _serialized_json_bytes(_ownership_sidecar_payload(manifest))
    )


def _trusted_journal_path(root: Path, operation_id: str) -> Path:
    root_key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "GameStudio-CodexKIT-safe-mutation" / root_key / f"{operation_id}.json"


def _trusted_journal_payload(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": manifest["operation_id"],
        "root": str(root.resolve()),
        "manifest_digest": _ownership_digest(manifest),
    }


def _trusted_completion_path(root: Path, operation_id: str) -> Path:
    journal_path = _trusted_journal_path(root, operation_id)
    return journal_path.with_name(f"{operation_id}.restored.json")


def _trusted_completion_payload(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "restored",
        "operation_id": manifest["operation_id"],
        "root": str(root.resolve()),
        "manifest_digest": _ownership_digest(manifest),
    }


def _write_trusted_journal(root: Path, manifest: dict[str, Any]) -> None:
    journal_path = _trusted_journal_path(root, manifest["operation_id"])
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_bytes(
        _serialized_json_bytes(_trusted_journal_payload(root, manifest))
    )


def _mkdir_tracked(path: Path, created_directories: list[Path]) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    path.mkdir(parents=True, exist_ok=True)
    created_directories.extend(reversed(missing))


def _register_expected_owned_file(
    path: Path,
    expected_hash: str,
    owned_files: dict[Path, str],
) -> str | None:
    if not path.exists():
        return None
    if not path.is_file() or _sha256_path(path) != expected_hash:
        return f"preserved unowned preparation artifact at expected path: {path}"
    owned_files[path] = expected_hash
    return None


def _cleanup_preparation_artifacts(
    owned_files: dict[Path, str],
    created_directories: list[Path],
) -> list[str]:
    issues: list[str] = []
    for path, expected_hash in reversed(list(owned_files.items())):
        try:
            if not path.exists():
                continue
            if not path.is_file() or _sha256_path(path) != expected_hash:
                issues.append(f"preserved changed preparation artifact: {path}")
                continue
            path.unlink()
        except BaseException as error:
            issues.append(f"failed to remove preparation artifact {path}: {error}")
    for directory in sorted(set(created_directories), key=lambda item: len(item.parts), reverse=True):
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        except BaseException as error:
            issues.append(f"failed to remove preparation directory {directory}: {error}")
    return issues


def _rollback_applied(
    root: Path,
    backup_root: Path,
    operations: list[dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    for operation in reversed(operations):
        try:
            target = _target(root, operation["path"])
            if _sha256_path(target) != operation["after_sha256"]:
                issues.append(
                    f"preserved drifted applied target {operation['path']}; manual recovery required"
                )
                continue
            if operation["action"] == "create":
                target.unlink()
                continue
            backup = (backup_root / str(operation["backup"])).resolve()
            backup.relative_to(backup_root)
            if _sha256_path(backup) != operation["before_sha256"]:
                issues.append(
                    f"backup hash mismatched for {operation['path']}; manual recovery required"
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
            if _sha256_path(target) != operation["before_sha256"]:
                issues.append(
                    f"rollback verification failed for {operation['path']}; manual recovery required"
                )
        except BaseException as error:
            issues.append(f"rollback failed for {operation['path']}: {error}")
    return issues


def apply_mutation(
    root: Path | str,
    operations: list[dict[str, str]],
    backup_root: Path | str,
    *,
    expected_operations: list[dict[str, Any]] | None = None,
) -> Path:
    root_path = Path(root).resolve()
    backup_path = Path(backup_root).resolve()
    try:
        backup_path.relative_to(root_path)
    except ValueError as error:
        raise ValueError("backup root must remain inside the approved root") from error
    _assert_safe_components(root_path, backup_path)
    normalized = _normalized_operations(root_path, operations)
    if expected_operations is not None:
        expected = _normalized_expected_operations(expected_operations)
        actual = sorted(
            (_operation_precondition(item) for item in normalized),
            key=lambda operation: operation["path"],
        )
        if actual != expected:
            raise ValueError(
                "approved mutation precondition mismatch; report and target state changed before apply"
            )
    if backup_path.exists() and any(backup_path.iterdir()):
        raise ValueError(f"backup root must be empty: {backup_path}")

    owned_preparation_files: dict[Path, str] = {}
    preparation_ownership_issues: list[str] = []
    created_preparation_directories: list[Path] = []
    manifest_operations: list[dict[str, Any]] = []
    manifest: dict[str, Any]
    manifest_path: Path
    journal_path: Path
    try:
        files_root = backup_path / "files"
        _mkdir_tracked(files_root, created_preparation_directories)
        for item in normalized:
            _assert_target_pre_state(item)
            backup_relative: str | None = None
            if item["before_exists"]:
                backup_file = files_root / item["path"]
                _mkdir_tracked(backup_file.parent, created_preparation_directories)
                expected_backup_hash = str(item["before_sha256"])
                try:
                    shutil.copy2(item["target"], backup_file)
                finally:
                    ownership_issue = _register_expected_owned_file(
                        backup_file,
                        expected_backup_hash,
                        owned_preparation_files,
                    )
                    if ownership_issue:
                        preparation_ownership_issues.append(ownership_issue)
                if preparation_ownership_issues:
                    raise ValueError(preparation_ownership_issues[-1])
                _assert_target_pre_state(item)
                backup_relative = backup_file.relative_to(backup_path).as_posix()
            manifest_operations.append(
                {
                    "path": item["path"],
                    "action": "update" if item["before_exists"] else "create",
                    "before_sha256": item["before_sha256"],
                    "after_sha256": item["after_sha256"],
                    "backup": backup_relative,
                    "restore": "copy backup" if item["before_exists"] else "remove created file",
                }
            )

        manifest = {
            "schema_version": 1,
            "mode": "prepared",
            "operation_id": uuid.uuid4().hex,
            "root": str(root_path),
            "backup_root": str(backup_path),
            "operations": manifest_operations,
        }
        manifest_path = backup_path / "manifest.json"
        expected_manifest_hash = _sha256_bytes(_serialized_json_bytes(manifest))
        try:
            _write_manifest(manifest_path, manifest)
        finally:
            ownership_issue = _register_expected_owned_file(
                manifest_path,
                expected_manifest_hash,
                owned_preparation_files,
            )
            if ownership_issue:
                preparation_ownership_issues.append(ownership_issue)
        if preparation_ownership_issues:
            raise ValueError(preparation_ownership_issues[-1])

        sidecar_path = backup_path / "ownership.json"
        expected_sidecar_hash = _sha256_bytes(
            _serialized_json_bytes(_ownership_sidecar_payload(manifest))
        )
        try:
            _write_ownership_sidecar(backup_path, manifest)
        finally:
            ownership_issue = _register_expected_owned_file(
                sidecar_path,
                expected_sidecar_hash,
                owned_preparation_files,
            )
            if ownership_issue:
                preparation_ownership_issues.append(ownership_issue)
        if preparation_ownership_issues:
            raise ValueError(preparation_ownership_issues[-1])

        journal_path = _trusted_journal_path(root_path, manifest["operation_id"])
        missing_journal_directories: list[Path] = []
        current = journal_path.parent
        while not current.exists():
            missing_journal_directories.append(current)
            current = current.parent
        expected_journal_hash = _sha256_bytes(
            _serialized_json_bytes(_trusted_journal_payload(root_path, manifest))
        )
        try:
            _write_trusted_journal(root_path, manifest)
        finally:
            created_preparation_directories.extend(
                directory
                for directory in reversed(missing_journal_directories)
                if directory.exists()
            )
            ownership_issue = _register_expected_owned_file(
                journal_path,
                expected_journal_hash,
                owned_preparation_files,
            )
            if ownership_issue:
                preparation_ownership_issues.append(ownership_issue)
        if preparation_ownership_issues:
            raise ValueError(preparation_ownership_issues[-1])
    except BaseException as preparation_error:
        cleanup_issues = preparation_ownership_issues + _cleanup_preparation_artifacts(
            owned_preparation_files,
            created_preparation_directories,
        )
        if cleanup_issues:
            raise RuntimeError(
                "preparation cleanup incomplete; manual recovery required: "
                + "; ".join(cleanup_issues)
            ) from preparation_error
        raise

    applied: list[dict[str, Any]] = []
    try:
        for item, manifest_operation in zip(normalized, manifest_operations, strict=True):
            target: Path = item["target"]
            _assert_safe_components(root_path, target)
            _assert_target_pre_state(item)
            target.parent.mkdir(parents=True, exist_ok=True)
            _assert_safe_components(root_path, target)
            _assert_target_pre_state(item)
            fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(item["content"])
                    handle.flush()
                    os.fsync(handle.fileno())

                def validate_target_pre_state() -> None:
                    _assert_safe_components(root_path, target)
                    _assert_target_pre_state(item)

                _replace_with_retry(
                    os.replace,
                    temporary,
                    target,
                    before_attempt=validate_target_pre_state,
                )
            finally:
                if temporary.exists():
                    temporary.unlink()
            applied.append(manifest_operation)
            if _sha256_path(target) != item["after_sha256"]:
                raise RuntimeError(f"post-write hash mismatch: {item['path']}")
        manifest["mode"] = "applied"
        _write_manifest(manifest_path, manifest)
        _verify_manifest(manifest_path, manifest)
        return manifest_path
    except BaseException as mutation_error:
        rollback_issues = _rollback_applied(root_path, backup_path, applied)
        manifest["mode"] = (
            "rollback-incomplete-manual-recovery"
            if rollback_issues
            else "rolled-back"
        )
        try:
            _write_manifest(manifest_path, manifest)
        except BaseException as recording_error:
            rollback_issues.append(f"failed to record rollback state: {recording_error}")
            recovery_path = backup_path / "rollback-recovery.json"
            try:
                recovery_path.write_text(
                    json.dumps(
                        {
                            "mode": "rollback-incomplete-manual-recovery",
                            "operation_id": manifest["operation_id"],
                            "issues": rollback_issues,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except BaseException as recovery_error:
                rollback_issues.append(
                    f"failed to write rollback recovery evidence: {recovery_error}"
                )
        if rollback_issues:
            raise RuntimeError(
                "rollback incomplete; manual recovery required: "
                + "; ".join(rollback_issues)
            ) from mutation_error
        if journal_path.exists():
            journal_path.unlink()
        raise

def _validate_manifest(path: Path, approved_root: Path) -> tuple[dict[str, Any], Path, Path]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise ValueError("manifest has invalid or unknown fields")
    if manifest["schema_version"] != 1 or manifest["mode"] not in {"applied", "restored"}:
        raise ValueError("manifest must be schema version 1 in applied or restored mode")
    if not isinstance(manifest["operation_id"], str) or not manifest["operation_id"]:
        raise ValueError("manifest operation_id is required")
    root = Path(manifest["root"]).resolve()
    backup_root = Path(manifest["backup_root"]).resolve()
    if root != approved_root.resolve():
        raise ValueError(f"manifest root does not match approved root: {root}")
    if path != backup_root / "manifest.json":
        raise ValueError("manifest must be the canonical backup_root/manifest.json")
    try:
        path.relative_to(root)
        backup_root.relative_to(root)
    except ValueError as error:
        raise ValueError("manifest and backup root must remain inside the approved root") from error
    _assert_safe_components(root, backup_root)
    sidecar_path = backup_root / "ownership.json"
    if not sidecar_path.is_file():
        raise ValueError("manifest ownership sidecar is missing")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if not isinstance(sidecar, dict) or set(sidecar) != {
        "schema_version",
        "operation_id",
        "manifest_digest",
    }:
        raise ValueError("manifest ownership sidecar is invalid")
    if (
        sidecar["schema_version"] != 1
        or sidecar["operation_id"] != manifest["operation_id"]
        or sidecar["manifest_digest"] != _ownership_digest(manifest)
    ):
        raise ValueError("manifest ownership sidecar does not match manifest")
    journal_path = _trusted_journal_path(root, manifest["operation_id"])
    if journal_path.is_file():
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if not isinstance(journal, dict) or set(journal) != {
            "schema_version",
            "operation_id",
            "root",
            "manifest_digest",
        }:
            raise ValueError("trusted mutation journal is invalid")
        if (
            journal["schema_version"] != 1
            or journal["operation_id"] != manifest["operation_id"]
            or Path(journal["root"]).resolve() != root
            or journal["manifest_digest"] != _ownership_digest(manifest)
        ):
            raise ValueError("trusted mutation journal does not match manifest")
    elif manifest["mode"] == "restored":
        _validate_trusted_completion(root, manifest)
    else:
        raise ValueError("trusted mutation journal is missing")
    if not isinstance(manifest["operations"], list):
        raise ValueError("manifest operations must be a list")
    for operation in manifest["operations"]:
        if not isinstance(operation, dict) or set(operation) != OPERATION_FIELDS:
            raise ValueError("manifest operation has invalid or unknown fields")
        if operation["action"] not in {"create", "update"}:
            raise ValueError("manifest operation action is invalid")
        if operation["action"] == "update" and not operation["backup"]:
            raise ValueError("updated files require a backup path")
        if operation["action"] == "create" and operation["backup"] is not None:
            raise ValueError("created files cannot have a backup path")
    return manifest, root, backup_root


def _restore_progress_path(backup_root: Path) -> Path:
    return backup_root / "restore-progress.json"


def _restore_quarantine_root(backup_root: Path) -> Path:
    return backup_root / "restore-quarantine"


def _restore_quarantine_path(backup_root: Path, index: int) -> Path:
    return _restore_quarantine_root(backup_root) / f"{index:04d}.applied"


def _restore_rollback_path(backup_root: Path, index: int) -> Path:
    return _restore_quarantine_root(backup_root) / f"{index:04d}.restored"


def _restore_recovery_path(backup_root: Path) -> Path:
    return backup_root / "restore-recovery.json"


def _restore_progress_payload(
    manifest: dict[str, Any],
    mode: str,
    completed: list[int],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": manifest["operation_id"],
        "manifest_digest": _ownership_digest(manifest),
        "mode": mode,
        "completed": completed,
    }


def _restore_recovery_payload(
    manifest: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "restore-incomplete-manual-recovery",
        "operation_id": manifest["operation_id"],
        "manifest_digest": _ownership_digest(manifest),
        "issues": issues,
    }


def _load_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{description} is unreadable: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return payload


def _validate_trusted_completion(root: Path, manifest: dict[str, Any]) -> None:
    completion_path = _trusted_completion_path(root, manifest["operation_id"])
    if not completion_path.is_file():
        raise ValueError("trusted completion receipt is missing")
    completion = _load_json_object(completion_path, "trusted completion receipt")
    if set(completion) != {
        "schema_version",
        "mode",
        "operation_id",
        "root",
        "manifest_digest",
    }:
        raise ValueError("trusted completion receipt is invalid")
    if completion != _trusted_completion_payload(root, manifest):
        raise ValueError("trusted completion receipt does not match manifest")


def _validate_restore_recovery(
    backup_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    recovery_path = _restore_recovery_path(backup_root)
    if not recovery_path.exists():
        return None
    if not recovery_path.is_file():
        raise ValueError("restore recovery evidence is not a regular file")
    recovery = _load_json_object(recovery_path, "restore recovery evidence")
    if set(recovery) != RESTORE_RECOVERY_FIELDS:
        raise ValueError("restore recovery evidence has invalid or unknown fields")
    if (
        recovery["schema_version"] != 1
        or recovery["mode"] != "restore-incomplete-manual-recovery"
        or recovery["operation_id"] != manifest["operation_id"]
        or recovery["manifest_digest"] != _ownership_digest(manifest)
        or not isinstance(recovery["issues"], list)
        or not recovery["issues"]
        or not all(isinstance(issue, str) and issue for issue in recovery["issues"])
    ):
        raise ValueError("restore recovery evidence does not match trusted manifest ownership")
    return recovery


def _load_restore_progress(
    backup_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    progress_path = _restore_progress_path(backup_root)
    recovery = _validate_restore_recovery(backup_root, manifest)
    if not progress_path.exists():
        if recovery is not None or _restore_quarantine_root(backup_root).exists():
            raise ValueError("restore artifacts exist without trusted restore progress")
        return None
    if not progress_path.is_file():
        raise ValueError("restore progress is not a regular file")
    progress = _load_json_object(progress_path, "restore progress")
    if set(progress) != RESTORE_PROGRESS_FIELDS:
        raise ValueError("restore progress has invalid or unknown fields")
    completed = progress["completed"]
    if (
        progress["schema_version"] != 1
        or progress["operation_id"] != manifest["operation_id"]
        or progress["manifest_digest"] != _ownership_digest(manifest)
        or progress["mode"]
        not in {"restoring", "rolling-back", "restore-incomplete-manual-recovery"}
        or not isinstance(completed, list)
        or not all(type(index) is int for index in completed)
        or completed != list(range(len(completed)))
        or len(completed) > len(manifest["operations"])
    ):
        raise ValueError("restore progress does not match trusted manifest ownership")
    if progress["mode"] == "restore-incomplete-manual-recovery":
        if recovery is None:
            raise ValueError("manual-recovery progress is missing recovery evidence")
        raise RuntimeError(
            "restore incomplete; manual recovery required: "
            + "; ".join(recovery["issues"])
        )
    if recovery is not None:
        raise RuntimeError(
            "restore incomplete; manual recovery required: "
            + "; ".join(recovery["issues"])
        )
    return progress


def _restore_backup_path(
    root: Path,
    backup_root: Path,
    operation: dict[str, Any],
) -> Path:
    backup = (backup_root / str(operation["backup"])).resolve()
    try:
        backup.relative_to(backup_root)
    except ValueError as error:
        raise ValueError(f"backup path escapes backup root: {operation['backup']}") from error
    _assert_safe_components(root, backup)
    return backup


def _target_is_restored(target: Path, operation: dict[str, Any]) -> bool:
    if operation["action"] == "create":
        return not target.exists()
    return target.is_file() and _sha256_path(target) == operation["before_sha256"]


def _path_evidence(path: Path) -> str:
    if not path.exists():
        return f"{path} (absent)"
    if not path.is_file():
        return f"{path} (not a regular file)"
    return f"{path} (sha256={_sha256_path(path)})"


def _restore_issue(
    index: int,
    operation: dict[str, Any],
    target: Path,
    quarantine: Path,
    reason: str,
) -> str:
    return (
        f"operation {index} {operation['path']}: {reason}; "
        f"target={_path_evidence(target)}; quarantine={_path_evidence(quarantine)}"
    )


def _atomic_rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename without replacing a destination that appears concurrently."""
    if os.name == "nt":
        # Windows rename is atomic and fails when the destination already exists.
        os.rename(source, destination)
        return

    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                -100,
                os.fsencode(source),
                -100,
                os.fsencode(destination),
                1,
            )
            if result == 0:
                return
            error_number = ctypes.get_errno()
            if error_number != errno.ENOSYS:
                raise OSError(error_number, os.strerror(error_number), str(destination))

    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renameatx_np = getattr(libc, "renameatx_np", None)
        if renameatx_np is not None:
            renameatx_np.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            renameatx_np.restype = ctypes.c_int
            result = renameatx_np(
                -2,
                os.fsencode(source),
                -2,
                os.fsencode(destination),
                0x4,
            )
            if result == 0:
                return
            error_number = ctypes.get_errno()
            if error_number != errno.ENOSYS:
                raise OSError(error_number, os.strerror(error_number), str(destination))

    raise RuntimeError(
        f"no atomic no-replace rename primitive is available for {sys.platform}"
    )


def _rename_no_clobber(
    root: Path,
    source: Path,
    destination: Path,
    *,
    expected_source_sha256: str,
) -> None:
    def validate_paths() -> None:
        _assert_safe_components(root, source)
        _assert_safe_components(root, destination)
        if not source.is_file() or _sha256_path(source) != expected_source_sha256:
            raise RuntimeError(f"atomic rename source changed: {source}")
        if destination.exists():
            raise RuntimeError(f"atomic rename refused to overwrite existing path: {destination}")

    _replace_with_retry(
        _atomic_rename_no_replace,
        source,
        destination,
        before_attempt=validate_paths,
    )


def _validate_restore_state(
    root: Path,
    backup_root: Path,
    operations: list[dict[str, Any]],
    progress: dict[str, Any],
) -> None:
    completed_count = len(progress["completed"])
    quarantine_root = _restore_quarantine_root(backup_root)
    actual_names: set[str] = set()
    if quarantine_root.exists():
        _assert_safe_components(root, quarantine_root)
        if not quarantine_root.is_dir():
            raise ValueError("restore quarantine is not a directory")
        for child in quarantine_root.iterdir():
            if not child.is_file():
                raise ValueError(f"restore quarantine contains an invalid entry: {child}")
            actual_names.add(child.name)
    allowed_names = {f"{index:04d}.applied" for index in range(completed_count)}
    allowed_names.update(f"{index:04d}.restored" for index in range(completed_count))
    if completed_count < len(operations):
        allowed_names.add(f"{completed_count:04d}.applied")
    unexpected_names = actual_names - allowed_names
    if unexpected_names:
        raise ValueError(
            "restore quarantine contains unowned entries: "
            + ", ".join(sorted(unexpected_names))
        )

    for index, operation in enumerate(operations):
        target = _target(root, operation["path"])
        quarantine = _restore_quarantine_path(backup_root, index)
        rollback_copy = _restore_rollback_path(backup_root, index)
        if index < completed_count:
            if not quarantine.is_file() or _sha256_path(quarantine) != operation["after_sha256"]:
                raise ValueError(
                    f"completed restore progress has no matching quarantine: {operation['path']}"
                )
            if rollback_copy.exists() and (
                not rollback_copy.is_file()
                or _sha256_path(rollback_copy) != operation["before_sha256"]
            ):
                raise ValueError(
                    f"restore rollback staging has an invalid backup: {operation['path']}"
                )
            if not _target_is_restored(target, operation):
                raise ValueError(
                    f"completed restore progress has an invalid target state: {operation['path']}"
                )
            continue
        if index == completed_count and quarantine.exists():
            if not quarantine.is_file() or _sha256_path(quarantine) != operation["after_sha256"]:
                raise RuntimeError(
                    _restore_issue(
                        index,
                        operation,
                        target,
                        quarantine,
                        "in-flight quarantine hash does not match the applied hash",
                    )
                )
            if target.exists() and not _target_is_restored(target, operation):
                raise RuntimeError(
                    _restore_issue(
                        index,
                        operation,
                        target,
                        quarantine,
                        "in-flight target changed during restore",
                    )
                )
            continue
        if quarantine.exists():
            raise ValueError(f"remaining restore operation has unexpected quarantine: {operation['path']}")
        if not target.is_file() or _sha256_path(target) != operation["after_sha256"]:
            raise RuntimeError(f"restore refused because target drifted after apply: {operation['path']}")


def _resume_restore_rollback_staging(
    root: Path,
    backup_root: Path,
    operations: list[dict[str, Any]],
    progress: dict[str, Any],
) -> None:
    for index in progress["completed"]:
        operation = operations[index]
        target = _target(root, operation["path"])
        quarantine = _restore_quarantine_path(backup_root, index)
        rollback_copy = _restore_rollback_path(backup_root, index)
        if not rollback_copy.exists():
            continue
        expected_before = str(operation["before_sha256"])
        if not rollback_copy.is_file() or _sha256_path(rollback_copy) != expected_before:
            raise RuntimeError(
                _restore_issue(
                    index,
                    operation,
                    target,
                    rollback_copy,
                    "rollback staging changed before resume",
                )
            )
        if quarantine.exists():
            if target.exists():
                if not _target_is_restored(target, operation):
                    raise RuntimeError(
                        _restore_issue(
                            index,
                            operation,
                            target,
                            rollback_copy,
                            "target changed while rollback staging was in flight",
                        )
                    )
                rollback_copy.unlink()
            else:
                _rename_no_clobber(
                    root,
                    rollback_copy,
                    target,
                    expected_source_sha256=expected_before,
                )
            continue
        if target.is_file() and _sha256_path(target) == operation["after_sha256"]:
            _rename_no_clobber(
                root,
                target,
                quarantine,
                expected_source_sha256=str(operation["after_sha256"]),
            )
            _rename_no_clobber(
                root,
                rollback_copy,
                target,
                expected_source_sha256=expected_before,
            )
            continue
        if target.exists() and not _target_is_restored(target, operation):
            raise RuntimeError(
                _restore_issue(
                    index,
                    operation,
                    target,
                    rollback_copy,
                    "target changed while rollback staging was in flight",
                )
            )
        rollback_copy.unlink()


def _install_verified_restore_backup(
    root: Path,
    backup_root: Path,
    operation: dict[str, Any],
    target: Path,
) -> None:
    backup = _restore_backup_path(root, backup_root, operation)
    expected_hash = str(operation["before_sha256"])
    if not backup.is_file() or _sha256_path(backup) != expected_hash:
        raise RuntimeError(f"backup hash mismatch: {operation['path']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_components(root, target)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.restore.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(backup, temporary)
        if _sha256_path(temporary) != expected_hash:
            raise RuntimeError(f"temporary restore hash mismatch: {operation['path']}")
        if _sha256_path(backup) != expected_hash:
            raise RuntimeError(f"backup changed during restore: {operation['path']}")
        _rename_no_clobber(
            root,
            temporary,
            target,
            expected_source_sha256=expected_hash,
        )
    finally:
        if temporary.exists():
            temporary.unlink()
    if _sha256_path(target) != expected_hash:
        raise RuntimeError(f"restore hash mismatch: {operation['path']}")


def _restore_one_operation(
    root: Path,
    backup_root: Path,
    index: int,
    operation: dict[str, Any],
) -> None:
    target = _target(root, operation["path"])
    quarantine = _restore_quarantine_path(backup_root, index)
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_components(root, quarantine)
    if not quarantine.exists():
        if not target.is_file() or _sha256_path(target) != operation["after_sha256"]:
            raise RuntimeError(f"restore refused because target drifted after apply: {operation['path']}")
        _rename_no_clobber(
            root,
            target,
            quarantine,
            expected_source_sha256=str(operation["after_sha256"]),
        )
        moved_hash = _sha256_path(quarantine)
        if moved_hash != operation["after_sha256"]:
            if moved_hash is not None and not target.exists():
                _rename_no_clobber(
                    root,
                    quarantine,
                    target,
                    expected_source_sha256=moved_hash,
                )
            raise RuntimeError(
                f"restore refused because target drifted during atomic quarantine: {operation['path']}"
            )
    if not quarantine.is_file() or _sha256_path(quarantine) != operation["after_sha256"]:
        raise RuntimeError(
            _restore_issue(
                index,
                operation,
                target,
                quarantine,
                "quarantine does not contain the applied bytes",
            )
        )
    if operation["action"] == "create":
        if target.exists():
            raise RuntimeError(
                _restore_issue(
                    index,
                    operation,
                    target,
                    quarantine,
                    "created target reappeared during restore",
                )
            )
        return
    if _target_is_restored(target, operation):
        return
    if target.exists():
        raise RuntimeError(
            _restore_issue(
                index,
                operation,
                target,
                quarantine,
                "updated target changed before backup installation",
            )
        )
    _install_verified_restore_backup(root, backup_root, operation, target)


def _rollback_restore(
    root: Path,
    backup_root: Path,
    operations: list[dict[str, Any]],
    progress: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    completed = set(progress["completed"])
    for index in range(len(operations) - 1, -1, -1):
        operation = operations[index]
        target = _target(root, operation["path"])
        quarantine = _restore_quarantine_path(backup_root, index)
        rollback_copy = _restore_rollback_path(backup_root, index)
        if not quarantine.exists():
            if index in completed:
                if (
                    not rollback_copy.exists()
                    and target.is_file()
                    and _sha256_path(target) == operation["after_sha256"]
                ):
                    # A restart may observe the applied bytes after rollback moved
                    # the quarantine back but before cleanup removed progress.
                    continue
                issues.append(
                    _restore_issue(
                        index,
                        operation,
                        target,
                        quarantine,
                        "completed restore operation lost its applied quarantine",
                    )
                )
            continue
        if not quarantine.is_file() or _sha256_path(quarantine) != operation["after_sha256"]:
            issues.append(
                _restore_issue(
                    index,
                    operation,
                    target,
                    quarantine,
                    "cannot roll back an unverified quarantine",
                )
            )
            continue
        try:
            if operation["action"] == "update" and _target_is_restored(target, operation):
                _rename_no_clobber(
                    root,
                    target,
                    rollback_copy,
                    expected_source_sha256=str(operation["before_sha256"]),
                )
            elif target.exists():
                issues.append(
                    _restore_issue(
                        index,
                        operation,
                        target,
                        quarantine,
                        "preserved target changed during restore rollback",
                    )
                )
                continue
            _rename_no_clobber(
                root,
                quarantine,
                target,
                expected_source_sha256=str(operation["after_sha256"]),
            )
            if _sha256_path(target) != operation["after_sha256"]:
                issues.append(
                    _restore_issue(
                        index,
                        operation,
                        target,
                        quarantine,
                        "applied target verification failed after restore rollback",
                    )
                )
                continue
            if rollback_copy.exists():
                if (
                    not rollback_copy.is_file()
                    or _sha256_path(rollback_copy) != operation["before_sha256"]
                ):
                    issues.append(
                        _restore_issue(
                            index,
                            operation,
                            target,
                            rollback_copy,
                            "preserved changed rollback copy",
                        )
                    )
                else:
                    rollback_copy.unlink()
        except BaseException as error:
            issues.append(
                _restore_issue(
                    index,
                    operation,
                    target,
                    quarantine,
                    f"restore rollback failed: {error}",
                )
            )
    return issues


def _cleanup_restore_artifacts(
    root: Path,
    backup_root: Path,
    manifest: dict[str, Any],
    operations: list[dict[str, Any]],
    progress: dict[str, Any] | None,
    *,
    restored: bool,
) -> list[str]:
    issues: list[str] = []
    quarantine_root = _restore_quarantine_root(backup_root)
    if quarantine_root.exists():
        expected_names = {f"{index:04d}.applied" for index in range(len(operations))}
        for child in list(quarantine_root.iterdir()):
            if child.name not in expected_names:
                issues.append(f"preserved unexpected restore artifact: {_path_evidence(child)}")
                continue
            index = int(child.name[:4])
            expected_hash = operations[index]["after_sha256"]
            if not child.is_file() or _sha256_path(child) != expected_hash:
                issues.append(f"preserved changed restore quarantine: {_path_evidence(child)}")
                continue
            child.unlink()
        if not issues and quarantine_root.is_dir() and not any(quarantine_root.iterdir()):
            quarantine_root.rmdir()
    recovery_path = _restore_recovery_path(backup_root)
    if recovery_path.exists():
        issues.append(f"preserved restore recovery evidence: {_path_evidence(recovery_path)}")
    progress_path = _restore_progress_path(backup_root)
    if not issues and progress_path.exists():
        if progress is None:
            issues.append(f"preserved unexpected restore progress: {_path_evidence(progress_path)}")
        else:
            current = _load_json_object(progress_path, "restore progress")
            if current != progress:
                issues.append(f"preserved changed restore progress: {_path_evidence(progress_path)}")
            else:
                progress_path.unlink()
    if not issues and restored:
        journal_path = _trusted_journal_path(root, manifest["operation_id"])
        expected_journal = _trusted_journal_payload(root, manifest)
        if not journal_path.is_file():
            issues.append(f"trusted mutation journal disappeared before restore cleanup: {journal_path}")
        else:
            current_journal = _load_json_object(journal_path, "trusted mutation journal")
            if current_journal != expected_journal:
                issues.append(f"preserved changed trusted mutation journal: {journal_path}")
            else:
                completion_path = _trusted_completion_path(root, manifest["operation_id"])
                expected_completion = _trusted_completion_payload(root, manifest)
                try:
                    if completion_path.exists():
                        current_completion = _load_json_object(
                            completion_path,
                            "trusted completion receipt",
                        )
                        if current_completion != expected_completion:
                            issues.append(
                                f"preserved changed trusted completion receipt: {completion_path}"
                            )
                    else:
                        _write_owned_json(completion_path, expected_completion)
                except BaseException as error:
                    issues.append(
                        f"failed to persist trusted completion receipt "
                        f"{completion_path}: {error}"
                    )
                if not issues:
                    journal_path.unlink()
    return issues


def _record_restore_manual_recovery(
    backup_root: Path,
    manifest: dict[str, Any],
    progress: dict[str, Any],
    issues: list[str],
) -> list[str]:
    recorded_issues = list(issues)
    recovery_path = _restore_recovery_path(backup_root)
    recovery = _restore_recovery_payload(manifest, recorded_issues)
    try:
        _write_owned_json(recovery_path, recovery)
    except BaseException as error:
        recorded_issues.append(f"failed to write restore recovery evidence {recovery_path}: {error}")
    manual_progress = _restore_progress_payload(
        manifest,
        "restore-incomplete-manual-recovery",
        list(progress["completed"]),
    )
    try:
        _write_owned_json(_restore_progress_path(backup_root), manual_progress)
    except BaseException as error:
        recorded_issues.append(
            f"failed to write manual-recovery restore progress "
            f"{_restore_progress_path(backup_root)}: {error}"
        )
    return recorded_issues


def _validate_fully_restored_targets(
    root: Path,
    operations: list[dict[str, Any]],
) -> None:
    for operation in operations:
        target = _target(root, operation["path"])
        if not _target_is_restored(target, operation):
            raise RuntimeError(f"restored manifest target state is invalid: {operation['path']}")


def restore_mutation(manifest_path: Path | str, approved_root: Path | str) -> None:
    path = Path(manifest_path).resolve()
    manifest, root, backup_root = _validate_manifest(path, Path(approved_root))
    operations = list(reversed(manifest["operations"]))
    progress = _load_restore_progress(backup_root, manifest)

    if manifest["mode"] == "restored":
        journal_path = _trusted_journal_path(root, manifest["operation_id"])
        if progress is not None and not journal_path.is_file():
            raise ValueError("restored cleanup progress requires the trusted mutation journal")
        _validate_fully_restored_targets(root, operations)
        if progress is None and not journal_path.exists():
            return
        cleanup_issues = _cleanup_restore_artifacts(
            root,
            backup_root,
            manifest,
            operations,
            progress,
            restored=True,
        )
        if cleanup_issues:
            raise RuntimeError(
                "restore cleanup incomplete; manual recovery required: "
                + "; ".join(cleanup_issues)
            )
        return

    if progress is not None and progress["mode"] == "rolling-back":
        rollback_issues = _rollback_restore(root, backup_root, operations, progress)
        if not rollback_issues:
            rollback_issues.extend(
                _cleanup_restore_artifacts(
                    root,
                    backup_root,
                    manifest,
                    operations,
                    progress,
                    restored=False,
                )
            )
        if rollback_issues:
            recovery_issues = _record_restore_manual_recovery(
                backup_root,
                manifest,
                progress,
                rollback_issues,
            )
            raise RuntimeError(
                "restore rollback incomplete; manual recovery required: "
                + "; ".join(recovery_issues)
            )
        progress = None

    if progress is None:
        for operation in operations:
            target = _target(root, operation["path"])
            if not target.is_file() or _sha256_path(target) != operation["after_sha256"]:
                raise RuntimeError(
                    f"restore refused because target drifted after apply: {operation['path']}"
                )
            if operation["action"] == "update":
                backup = _restore_backup_path(root, backup_root, operation)
                if not backup.is_file() or _sha256_path(backup) != operation["before_sha256"]:
                    raise RuntimeError(f"backup hash mismatch: {operation['path']}")
        progress = _restore_progress_payload(manifest, "restoring", [])
        _write_owned_json(_restore_progress_path(backup_root), progress)
    else:
        _resume_restore_rollback_staging(root, backup_root, operations, progress)
        _validate_restore_state(root, backup_root, operations, progress)

    try:
        for index in range(len(progress["completed"]), len(operations)):
            operation = operations[index]
            _restore_one_operation(root, backup_root, index, operation)
            progress = _restore_progress_payload(
                manifest,
                "restoring",
                list(range(index + 1)),
            )
            _write_owned_json(_restore_progress_path(backup_root), progress)
        _validate_fully_restored_targets(root, operations)
        manifest["mode"] = "restored"
        _write_manifest(path, manifest)
        _verify_manifest(path, manifest)
        cleanup_issues = _cleanup_restore_artifacts(
            root,
            backup_root,
            manifest,
            operations,
            progress,
            restored=True,
        )
        if cleanup_issues:
            recovery_issues = _record_restore_manual_recovery(
                backup_root,
                manifest,
                progress,
                cleanup_issues,
            )
            raise RuntimeError(
                "restore cleanup incomplete; manual recovery required: "
                + "; ".join(recovery_issues)
            )
    except BaseException as restore_error:
        if manifest["mode"] == "restored":
            raise
        progress = _restore_progress_payload(
            manifest,
            "rolling-back",
            list(progress["completed"]),
        )
        try:
            _write_owned_json(_restore_progress_path(backup_root), progress)
        except BaseException as progress_error:
            raise RuntimeError(
                "restore failed before durable rollback progress could be recorded; "
                "resume from the existing restore progress"
            ) from progress_error
        rollback_issues = _rollback_restore(root, backup_root, operations, progress)
        if not rollback_issues:
            cleanup_issues = _cleanup_restore_artifacts(
                root,
                backup_root,
                manifest,
                operations,
                progress,
                restored=False,
            )
            rollback_issues.extend(cleanup_issues)
        if rollback_issues:
            recovery_issues = _record_restore_manual_recovery(
                backup_root,
                manifest,
                progress,
                rollback_issues,
            )
            raise RuntimeError(
                "restore rollback incomplete; manual recovery required: "
                + "; ".join(recovery_issues)
            ) from restore_error
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report, apply, or restore scoped file mutations.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--operations", help="JSON file containing [{path, content}]")
    parser.add_argument("--mode", choices=["report", "apply", "restore"], default="report")
    parser.add_argument("--backup-root")
    parser.add_argument("--manifest")
    parser.add_argument("--reviewer")
    parser.add_argument("--reviewed-manifest")
    parser.add_argument("--plan-digest")
    args = parser.parse_args(argv)
    if args.mode == "restore":
        if args.reviewer or args.reviewed_manifest or args.plan_digest:
            parser.error("approval arguments are only supported with --mode apply")
        if not args.manifest:
            parser.error("--manifest is required for restore")
        restore_mutation(args.manifest, args.root)
        print("restore: PASS")
        return 0
    if not args.operations:
        parser.error("--operations is required")
    operations = json.loads(Path(args.operations).read_text(encoding="utf-8"))
    if args.mode == "report":
        if args.reviewer or args.reviewed_manifest or args.plan_digest:
            parser.error("approval arguments require --mode apply")
        print(json.dumps(report_mutation(Path(args.root), operations), indent=2))
        return 0
    if not args.backup_root:
        parser.error("--backup-root is required for apply")
    if not args.reviewer or not args.reviewer.strip():
        parser.error("--reviewer is required for apply")
    if not args.reviewed_manifest:
        parser.error("--reviewed-manifest is required for apply")
    if not args.plan_digest or not args.plan_digest.strip():
        parser.error("--plan-digest is required for apply")
    root_path = Path(args.root).resolve()
    report = report_mutation(root_path, operations)
    expected_digest = _mutation_plan_digest(report)
    if args.plan_digest.strip() != expected_digest:
        parser.error("approved mutation plan digest does not match current report")
    try:
        reviewed = json.loads(Path(args.reviewed_manifest).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        parser.error(f"cannot read reviewed manifest: {error}")
    if (
        not isinstance(reviewed, dict)
        or reviewed.get("mode") != "report-only"
        or reviewed.get("root") != str(root_path)
        or reviewed.get("operations") != report["operations"]
        or reviewed.get("plan_digest") != expected_digest
        or reviewed.get("reviewer") != args.reviewer.strip()
    ):
        parser.error("reviewed manifest does not match the current approved mutation plan")
    print(
        apply_mutation(
            root_path,
            operations,
            Path(args.backup_root),
            expected_operations=report["operations"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
