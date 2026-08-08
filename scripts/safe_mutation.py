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


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _ownership_digest(manifest: dict[str, Any]) -> str:
    payload = {
        "operation_id": manifest["operation_id"],
        "root": manifest["root"],
        "backup_root": manifest["backup_root"],
        "operations": manifest["operations"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_ownership_sidecar(backup_root: Path, manifest: dict[str, Any]) -> None:
    sidecar = {
        "schema_version": 1,
        "operation_id": manifest["operation_id"],
        "manifest_digest": _ownership_digest(manifest),
    }
    (backup_root / "ownership.json").write_text(
        json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
    )


def _trusted_journal_path(root: Path, operation_id: str) -> Path:
    root_key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "GameStudio-CodexKIT-safe-mutation" / root_key / f"{operation_id}.json"


def _write_trusted_journal(root: Path, manifest: dict[str, Any]) -> None:
    journal_path = _trusted_journal_path(root, manifest["operation_id"])
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "operation_id": manifest["operation_id"],
        "root": str(root.resolve()),
        "manifest_digest": _ownership_digest(manifest),
    }
    journal_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _rollback_applied(root: Path, backup_root: Path, operations: list[dict[str, Any]]) -> None:
    for operation in reversed(operations):
        target = _target(root, operation["path"])
        if operation["action"] == "create":
            if target.exists():
                target.unlink()
            continue
        backup = (backup_root / str(operation["backup"])).resolve()
        backup.relative_to(backup_root)
        if _sha256_path(backup) != operation["before_sha256"]:
            raise RuntimeError(f"cannot rollback because backup hash mismatched: {operation['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)


def apply_mutation(root: Path | str, operations: list[dict[str, str]], backup_root: Path | str) -> Path:
    root_path = Path(root).resolve()
    backup_path = Path(backup_root).resolve()
    try:
        backup_path.relative_to(root_path)
    except ValueError as error:
        raise ValueError("backup root must remain inside the approved root") from error
    _assert_safe_components(root_path, backup_path)
    normalized = _normalized_operations(root_path, operations)
    if backup_path.exists() and any(backup_path.iterdir()):
        raise ValueError(f"backup root must be empty: {backup_path}")

    files_root = backup_path / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    manifest_operations: list[dict[str, Any]] = []
    for item in normalized:
        backup_relative: str | None = None
        if item["before_exists"]:
            backup_file = files_root / item["path"]
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["target"], backup_file)
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
    _write_manifest(manifest_path, manifest)
    _write_ownership_sidecar(backup_path, manifest)
    _write_trusted_journal(root_path, manifest)
    applied: list[dict[str, Any]] = []
    try:
        for item, manifest_operation in zip(normalized, manifest_operations, strict=True):
            target: Path = item["target"]
            _assert_safe_components(root_path, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            _assert_safe_components(root_path, target)
            fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(item["content"])
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    temporary.unlink()
            applied.append(manifest_operation)
            if _sha256_path(target) != item["after_sha256"]:
                raise RuntimeError(f"post-write hash mismatch: {item['path']}")
    except BaseException:
        _rollback_applied(root_path, backup_path, applied)
        manifest["mode"] = "rolled-back"
        _write_manifest(manifest_path, manifest)
        journal_path = _trusted_journal_path(root_path, manifest["operation_id"])
        if journal_path.exists():
            journal_path.unlink()
        raise

    manifest["mode"] = "applied"
    _write_manifest(manifest_path, manifest)
    return manifest_path


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
