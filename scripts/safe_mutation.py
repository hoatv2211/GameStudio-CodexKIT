from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


MANIFEST_FIELDS = {"schema_version", "mode", "operation_id", "root", "backup_root", "operations"}
OPERATION_FIELDS = {
    "path",
    "action",
    "before_sha256",
    "after_sha256",
    "backup",
    "restore",
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
    return {
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


def _serialized_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


_ATOMIC_REPLACE = os.replace


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
        _ATOMIC_REPLACE(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if not path.is_file() or path.read_bytes() != _serialized_json_bytes(manifest):
        raise RuntimeError(f"manifest verification failed: {path}")


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
                _assert_target_pre_state(item)
                os.replace(temporary, target)
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
    if manifest["schema_version"] != 1 or manifest["mode"] != "applied":
        raise ValueError("manifest must be schema version 1 in applied mode")
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
    if not journal_path.is_file():
        raise ValueError("trusted mutation journal is missing")
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


def restore_mutation(manifest_path: Path | str, approved_root: Path | str) -> None:
    path = Path(manifest_path).resolve()
    manifest, root, backup_root = _validate_manifest(path, Path(approved_root))
    operations = list(reversed(manifest["operations"]))
    for operation in operations:
        target = _target(root, operation["path"])
        if _sha256_path(target) != operation["after_sha256"]:
            raise RuntimeError(f"restore refused because target drifted after apply: {operation['path']}")
        if operation["action"] == "update":
            backup = (backup_root / operation["backup"]).resolve()
            try:
                backup.relative_to(backup_root)
            except ValueError as error:
                raise ValueError(f"backup path escapes backup root: {operation['backup']}") from error
            if _sha256_path(backup) != operation["before_sha256"]:
                raise RuntimeError(f"backup hash mismatch: {operation['path']}")

    for operation in operations:
        target = _target(root, operation["path"])
        _assert_safe_components(root, target)
        if operation["action"] == "create":
            target.unlink()
            continue
        backup = (backup_root / operation["backup"]).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        if _sha256_path(target) != operation["before_sha256"]:
            raise RuntimeError(f"restore hash mismatch: {operation['path']}")
    manifest["mode"] = "restored"
    _write_manifest(path, manifest)
    journal_path = _trusted_journal_path(root, manifest["operation_id"])
    if journal_path.exists():
        journal_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report, apply, or restore scoped file mutations.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--operations", help="JSON file containing [{path, content}]")
    parser.add_argument("--mode", choices=["report", "apply", "restore"], default="report")
    parser.add_argument("--backup-root")
    parser.add_argument("--manifest")
    args = parser.parse_args(argv)
    if args.mode == "restore":
        if not args.manifest:
            parser.error("--manifest is required for restore")
        restore_mutation(args.manifest, args.root)
        print("restore: PASS")
        return 0
    if not args.operations:
        parser.error("--operations is required")
    operations = json.loads(Path(args.operations).read_text(encoding="utf-8"))
    if args.mode == "report":
        print(json.dumps(report_mutation(Path(args.root), operations), indent=2))
        return 0
    if not args.backup_root:
        parser.error("--backup-root is required for apply")
    print(apply_mutation(Path(args.root), operations, Path(args.backup_root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
