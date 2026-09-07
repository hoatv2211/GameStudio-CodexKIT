from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts.adapter_sources import (
    MARKER,
    _CapturedSource,
    _assert_no_reparse_path,
    _capabilities,
    _capture_source_file,
    _generated_resource,
    _is_reparse_info,
    _is_reparse_point,
    _listing_identity,
    _safe_component,
    _skill_files,
    _stat_identity,
    _validated_capability,
    _walk_adapter_files,
    )
    from scripts.generated_resources import (
        is_generated_resource as _is_owned_generated_resource,
    )
    from scripts.safe_mutation import _atomic_rename_no_replace, _write_manifest
except ModuleNotFoundError:
    from adapter_sources import (
    MARKER,
    _CapturedSource,
    _assert_no_reparse_path,
    _capabilities,
    _capture_source_file,
    _generated_resource,
    _is_reparse_info,
    _is_reparse_point,
    _listing_identity,
    _safe_component,
    _skill_files,
    _stat_identity,
    _validated_capability,
    _walk_adapter_files,
    )
    from generated_resources import (
        is_generated_resource as _is_owned_generated_resource,
    )
    from safe_mutation import _atomic_rename_no_replace, _write_manifest


@dataclass(frozen=True)
class _TreeSnapshot:
    files: tuple[tuple[str, str], ...]

class _ManualRecoveryRequired(RuntimeError):
    pass

def _assert_disjoint_output(output: Path, source_roots: list[Path]) -> None:
    resolved_output = output.resolve()
    for source_root in source_roots:
        resolved_source = source_root.resolve()
        if (
            resolved_output == resolved_source
            or resolved_output.is_relative_to(resolved_source)
            or resolved_source.is_relative_to(resolved_output)
        ):
            raise ValueError(
                f"adapter output overlaps canonical skills: {resolved_output} and {resolved_source}"
            )

def _safe_standard_destination(base: Path, relative: PurePosixPath | str) -> Path:
    relative_path = PurePosixPath(str(relative).replace("\\", "/"))
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        raise ValueError(f"unsafe standard adapter destination: {relative}")
    _assert_no_reparse_path(base)
    current = base
    for part in relative_path.parts:
        current = current / part
        if _is_reparse_point(current):
            raise ValueError(f"symlink or reparse point is not allowed: {current}")
    try:
        current.resolve().relative_to(base.resolve())
    except ValueError as error:
        raise ValueError(f"standard adapter destination escapes its stage: {relative}") from error
    return current

def _is_standard_generated_artifact(path: Path, text: str) -> bool:
    return _is_owned_generated_resource(
        path,
        text,
        marker=MARKER,
        metadata_names=("registry.json",),
    )

def _standard_tree_snapshot(path: Path) -> _TreeSnapshot:
    files = _walk_adapter_files(path, reject_empty_directories=True)
    assert all(isinstance(file, Path) for file in files)
    return _TreeSnapshot(
        files=tuple(
            sorted(
                (
                    file.relative_to(path).as_posix(),
                    hashlib.sha256(file.read_bytes()).hexdigest(),
                )
                for file in files
            )
        )
    )

def _standard_snapshot_from_contents(contents: list[tuple[str, str]]) -> _TreeSnapshot:
    return _TreeSnapshot(
        files=tuple(
            sorted(
                (relative, hashlib.sha256(content.encode("utf-8")).hexdigest())
                for relative, content in contents
            )
        )
    )

def _standard_snapshot_payload(snapshot: _TreeSnapshot) -> list[dict[str, str]]:
    return [{"path": path, "sha256": digest} for path, digest in snapshot.files]

def _standard_snapshot_from_payload(payload: object) -> _TreeSnapshot:
    if not isinstance(payload, list):
        raise ValueError("swap recovery snapshot must be a list")
    files: list[tuple[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("swap recovery snapshot entries must be objects")
        relative = item.get("path")
        digest = item.get("sha256")
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("swap recovery snapshot entry is invalid")
        files.append((relative, digest))
    if len({path for path, _digest in files}) != len(files):
        raise ValueError("swap recovery snapshot contains duplicate paths")
    return _TreeSnapshot(files=tuple(sorted(files)))

def _validate_standard_tree(
    path: Path,
    *,
    expected_files: list[str] | None = None,
    expected_snapshot: _TreeSnapshot | None = None,
) -> _TreeSnapshot:
    files = _walk_adapter_files(path, reject_empty_directories=True)
    assert all(isinstance(file, Path) for file in files)
    actual = sorted(file.relative_to(path).as_posix() for file in files)
    if "registry.json" not in actual:
        raise RuntimeError(f"generated adapter registry is missing: {path}")
    for file in files:
        text = file.read_text(encoding="utf-8", errors="replace")
        if not _is_standard_generated_artifact(file, text):
            raise RuntimeError(f"refusing to replace unmanaged adapter file: {file}")
    registry = json.loads((path / "registry.json").read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("_generated") != MARKER:
        raise RuntimeError(f"generated adapter registry is not owned: {path / 'registry.json'}")
    actual_without_registry = [item for item in actual if item != "registry.json"]
    declared = registry.get("files")
    if declared is not None and sorted(declared) != actual_without_registry:
        raise RuntimeError(
            f"generated adapter registry file ownership mismatch: {path / 'registry.json'}"
        )
    if expected_files is not None and sorted(expected_files) != actual_without_registry:
        raise RuntimeError(f"generated adapter render file set mismatch: {path}")
    snapshot = _standard_tree_snapshot(path)
    if expected_snapshot is not None and snapshot != expected_snapshot:
        raise RuntimeError(f"generated adapter render hash mismatch: {path}")
    return snapshot

def _prepare_managed_output(output: Path) -> _TreeSnapshot | None:
    if not output.exists() and not output.is_symlink():
        return None
    return _validate_standard_tree(output)

def _standard_temp_path(output: Path, suffix: str) -> Path:
    return output.parent / f".{output.name}.{uuid.uuid4().hex}.{suffix}"

def _is_standard_temp_path(path: Path, output: Path, suffix: str) -> bool:
    owned_name = re.compile(
        rf"^\.{re.escape(output.name)}\.[0-9a-f]{{32}}\.{re.escape(suffix)}$"
    )
    return path.parent == output.parent and owned_name.fullmatch(path.name) is not None

def _validate_standard_temp(
    path: Path,
    output: Path,
    suffix: str,
    expected_snapshot: _TreeSnapshot,
) -> None:
    if not _is_standard_temp_path(path, output, suffix):
        raise RuntimeError(f"refusing to remove unowned adapter temporary path: {path}")
    if path.exists() or path.is_symlink():
        try:
            _assert_no_reparse_path(path)
            if not path.is_dir() or _standard_tree_snapshot(path) != expected_snapshot:
                raise ValueError("snapshot mismatch")
        except (OSError, RuntimeError, ValueError) as error:
            raise _ManualRecoveryRequired(
                f"manual recovery required; preserving changed adapter temporary path: {path}"
            ) from error

def _standard_recovery_path(output: Path) -> Path:
    return output.parent / f".{output.name}.swap-recovery.json"

def _write_standard_recovery(
    output: Path,
    rollback: Path | None,
    stage: Path,
    previous_snapshot: _TreeSnapshot | None,
    staged_snapshot: _TreeSnapshot,
    *,
    state: str = "prepared",
) -> Path:
    recovery_path = _standard_recovery_path(output)
    payload = {
        "_generated": MARKER,
        "schema_version": 1,
        "kind": "adapter-output-swap-recovery",
        "state": state,
        "output": str(output),
        "rollback": str(rollback) if rollback is not None else None,
        "stage": str(stage),
        "previous_files": (
            _standard_snapshot_payload(previous_snapshot)
            if previous_snapshot is not None
            else None
        ),
        "staged_files": _standard_snapshot_payload(staged_snapshot),
    }
    encoded = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    try:
        with recovery_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if recovery_path.read_bytes() == encoded:
            return recovery_path
        raise _ManualRecoveryRequired(
            f"manual recovery required; adapter recovery evidence drifted: {recovery_path}"
        ) from None
    except OSError as error:
        raise _ManualRecoveryRequired(
            "swap recovery journal could not be persisted; "
            f"output={output} rollback={rollback} stage={stage}"
        ) from error
    return recovery_path

def _update_standard_recovery(
    output: Path,
    rollback: Path | None,
    stage: Path,
    previous_snapshot: _TreeSnapshot | None,
    staged_snapshot: _TreeSnapshot,
    *,
    expected_states: set[str],
    state: str,
) -> Path:
    recovery_path = _standard_recovery_path(output)
    try:
        current = json.loads(recovery_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("state") not in expected_states:
            raise ValueError("unexpected recovery state")
        identity_fields = {
            "_generated": MARKER,
            "schema_version": 1,
            "kind": "adapter-output-swap-recovery",
            "output": str(output),
            "rollback": str(rollback) if rollback is not None else None,
            "stage": str(stage),
            "previous_files": (
                _standard_snapshot_payload(previous_snapshot)
                if previous_snapshot is not None
                else None
            ),
            "staged_files": _standard_snapshot_payload(staged_snapshot),
        }
        if {key: current.get(key) for key in identity_fields} != identity_fields:
            raise ValueError("recovery identity changed")
        updated = {**current, "state": state}
        _write_manifest(recovery_path, updated)
        if json.loads(recovery_path.read_text(encoding="utf-8")) != updated:
            raise ValueError("recovery state verification failed")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise _ManualRecoveryRequired(
            f"manual recovery required; adapter recovery state update failed: {recovery_path}"
        ) from error
    return recovery_path

def _standard_completion_payload(
    output: Path,
    rollback: Path,
    stage: Path,
    previous_snapshot: _TreeSnapshot,
    staged_snapshot: _TreeSnapshot,
) -> dict[str, object]:
    return {
        "_generated": MARKER,
        "schema_version": 1,
        "kind": "adapter-output-swap-completion",
        "status": "published",
        "output": str(output),
        "rollback": str(rollback),
        "stage": str(stage),
        "previous_files": _standard_snapshot_payload(previous_snapshot),
        "staged_files": _standard_snapshot_payload(staged_snapshot),
    }

def _write_standard_completion(
    output: Path,
    rollback: Path,
    stage: Path,
    previous_snapshot: _TreeSnapshot,
    staged_snapshot: _TreeSnapshot,
) -> Path:
    payload = _standard_completion_payload(
        output,
        rollback,
        stage,
        previous_snapshot,
        staged_snapshot,
    )
    encoded = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    completion_path = output.parent / f".{output.name}.{digest}.swap-completion.json"
    try:
        with completion_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if completion_path.read_bytes() != encoded:
            raise _ManualRecoveryRequired(
                f"manual recovery required; adapter completion evidence drifted: {completion_path}"
            ) from None
    return completion_path

def _archive_standard_recovery(
    output: Path,
    recovery_path: Path,
    expected_bytes: bytes,
) -> Path:
    digest = hashlib.sha256(expected_bytes).hexdigest()
    archived = output.parent / f".{output.name}.{digest}.swap-recovery.json"
    try:
        if recovery_path.read_bytes() != expected_bytes:
            raise ValueError("recovery journal changed before archive")
        _atomic_rename_no_replace(recovery_path, archived)
        if archived.read_bytes() != expected_bytes:
            raise ValueError("recovery journal changed during archive")
    except (OSError, ValueError) as error:
        raise _ManualRecoveryRequired(
            f"manual recovery required; adapter recovery archive failed: {recovery_path}"
        ) from error
    return archived

def _preserve_standard_swap_failure(
    output: Path,
    rollback: Path | None,
    stage: Path,
    previous_snapshot: _TreeSnapshot | None,
    staged_snapshot: _TreeSnapshot,
    error: BaseException,
) -> None:
    # Failure cleanup is deliberately non-destructive: snapshot validation is not
    # a safe authority for a later recursive delete if another process swaps paths.
    try:
        _validate_standard_temp(stage, output, "stage", staged_snapshot)
    except _ManualRecoveryRequired:
        pass
    recovery_path = _standard_recovery_path(output)
    if not recovery_path.exists():
        recovery_path = _write_standard_recovery(
            output,
            rollback,
            stage,
            previous_snapshot,
            staged_snapshot,
        )
    raise _ManualRecoveryRequired(f"swap recovery required: {recovery_path}") from error

def _recover_standard_swap_if_needed(output: Path) -> None:
    recovery_path = _standard_recovery_path(output)
    if not recovery_path.exists():
        return
    try:
        recovery_bytes = recovery_path.read_bytes()
        recovery = json.loads(recovery_bytes.decode("utf-8"))
        if (
            not isinstance(recovery, dict)
            or recovery.get("_generated") != MARKER
            or recovery.get("kind") != "adapter-output-swap-recovery"
            or recovery.get("output") != str(output)
        ):
            raise ValueError("invalid recovery header")
        rollback_value = recovery.get("rollback")
        rollback = Path(rollback_value) if isinstance(rollback_value, str) else None
        stage = Path(str(recovery["stage"]))
        if (
            (
                rollback is not None
                and not _is_standard_temp_path(rollback, output, "rollback")
            )
            or not _is_standard_temp_path(stage, output, "stage")
        ):
            raise ValueError("recovery paths are outside owned scope")
        previous_payload = recovery.get("previous_files")
        previous_snapshot = (
            _standard_snapshot_from_payload(previous_payload)
            if previous_payload is not None
            else None
        )
        staged_snapshot = _standard_snapshot_from_payload(recovery.get("staged_files"))
        if (previous_snapshot is None) != (rollback is None):
            raise ValueError("recovery rollback and previous snapshot disagree")
        recovery_state = recovery.get("state")
        if recovery_state not in {"prepared", "output-moved", "restored", "published"}:
            raise ValueError("invalid recovery state")
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        raise _ManualRecoveryRequired(
            f"manual recovery required; invalid adapter swap recovery: {recovery_path}"
        ) from error

    def snapshot_or_manual(path: Path, label: str) -> _TreeSnapshot:
        try:
            return _standard_tree_snapshot(path)
        except Exception as error:
            raise _ManualRecoveryRequired(
                f"manual recovery required; {label} tree is missing or drifted: {path}"
            ) from error

    if previous_snapshot is None:
        if output.exists():
            output_snapshot = snapshot_or_manual(output, "adapter output")
            if output_snapshot != staged_snapshot or stage.exists():
                raise _ManualRecoveryRequired(
                    f"manual recovery required; adapter output drifted during recovery: {output}"
                )
            if recovery_state != "published":
                _update_standard_recovery(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                    expected_states={recovery_state},
                    state="published",
                )
                recovery_bytes = recovery_path.read_bytes()
        else:
            if not stage.exists():
                raise _ManualRecoveryRequired(
                    f"manual recovery required; adapter stage is missing: {stage}"
                )
            _validate_standard_temp(stage, output, "stage", staged_snapshot)
        _archive_standard_recovery(output, recovery_path, recovery_bytes)
        return

    assert rollback is not None
    if output.exists():
        output_snapshot = snapshot_or_manual(output, "adapter output")
        if output_snapshot == previous_snapshot:
            if rollback.exists():
                raise _ManualRecoveryRequired(
                    f"manual recovery required; duplicate previous adapter tree: {rollback}"
                )
            if stage.exists():
                _validate_standard_temp(stage, output, "stage", staged_snapshot)
            else:
                raise _ManualRecoveryRequired(
                    f"manual recovery required; adapter stage is missing: {stage}"
                )
            if recovery_state == "output-moved":
                _update_standard_recovery(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                    expected_states={"output-moved"},
                    state="restored",
                )
                recovery_bytes = recovery_path.read_bytes()
            _archive_standard_recovery(output, recovery_path, recovery_bytes)
            return
        elif output_snapshot == staged_snapshot:
            if stage.exists():
                raise _ManualRecoveryRequired(
                    f"manual recovery required; duplicate staged adapter tree: {stage}"
                )
            if rollback.exists():
                _validate_standard_temp(rollback, output, "rollback", previous_snapshot)
                _write_standard_completion(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                )
            else:
                raise _ManualRecoveryRequired(
                    f"manual recovery required; adapter rollback is missing: {rollback}"
                )
            if recovery_state != "published":
                _update_standard_recovery(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                    expected_states={recovery_state},
                    state="published",
                )
                recovery_bytes = recovery_path.read_bytes()
            _archive_standard_recovery(output, recovery_path, recovery_bytes)
            return
        else:
            raise _ManualRecoveryRequired(
                f"manual recovery required; adapter output drifted during recovery: {output}"
            )
    else:
        if not rollback.exists() or snapshot_or_manual(rollback, "adapter rollback") != previous_snapshot:
            raise _ManualRecoveryRequired(
                f"manual recovery required; adapter rollback is missing or drifted: {rollback}"
            )
        try:
            _rename_standard_directory(rollback, output)
        except OSError as error:
            raise _ManualRecoveryRequired(
                f"manual recovery required; adapter rollback restore failed: {rollback}"
            ) from error
        if snapshot_or_manual(output, "restored adapter output") != previous_snapshot:
            raise _ManualRecoveryRequired(
                f"manual recovery required; restored adapter output failed validation: {output}"
            )
        _update_standard_recovery(
            output,
            rollback,
            stage,
            previous_snapshot,
            staged_snapshot,
            expected_states={recovery_state},
            state="restored",
        )
        recovery_bytes = recovery_path.read_bytes()
        if stage.exists():
            _validate_standard_temp(stage, output, "stage", staged_snapshot)
        else:
            raise _ManualRecoveryRequired(
                f"manual recovery required; adapter stage is missing: {stage}"
            )
        _archive_standard_recovery(output, recovery_path, recovery_bytes)

def _standard_missing_ancestors(path: Path) -> list[Path]:
    missing: list[Path] = []
    cursor = Path(os.path.abspath(str(path)))
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    return missing

def _cleanup_standard_ancestors(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.rmdir()
        except OSError:
            break

def _rename_standard_directory(source: Path, target: Path) -> Path:
    _atomic_rename_no_replace(source, target)
    return target

def _swap_standard_stage(
    stage: Path,
    output: Path,
    staged_snapshot: _TreeSnapshot,
    previous_snapshot: _TreeSnapshot | None,
) -> None:
    # Keep the previous tree recoverable until the staged tree is visible.
    rollback = (
        _standard_temp_path(output, "rollback") if previous_snapshot is not None else None
    )
    recovery_path = _write_standard_recovery(
        output,
        rollback,
        stage,
        previous_snapshot,
        staged_snapshot,
        state="prepared",
    )
    if output.exists():
        if previous_snapshot is None:
            raise RuntimeError(f"managed adapter output snapshot is missing: {output}")
        assert rollback is not None
        try:
            _rename_standard_directory(output, rollback)
        except BaseException as rename_error:
            _preserve_standard_swap_failure(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                rename_error,
            )
        _update_standard_recovery(
            output,
            rollback,
            stage,
            previous_snapshot,
            staged_snapshot,
            expected_states={"prepared"},
            state="output-moved",
        )
        try:
            rollback_snapshot = _standard_tree_snapshot(rollback)
        except Exception as validation_error:
            try:
                _rename_standard_directory(rollback, output)
            except BaseException as restore_error:
                _preserve_standard_swap_failure(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                    restore_error,
                )
            _update_standard_recovery(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                expected_states={"output-moved"},
                state="restored",
            )
            _preserve_standard_swap_failure(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                validation_error,
            )
        if rollback_snapshot != previous_snapshot:
            try:
                _rename_standard_directory(rollback, output)
            except BaseException as restore_error:
                _preserve_standard_swap_failure(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                    restore_error,
                )
            _update_standard_recovery(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                expected_states={"output-moved"},
                state="restored",
            )
            _preserve_standard_swap_failure(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                RuntimeError(f"managed adapter output changed before swap: {output}"),
            )
    try:
        _rename_standard_directory(stage, output)
    except BaseException as publish_error:
        if rollback is not None and rollback.exists() and not output.exists():
            try:
                _rename_standard_directory(rollback, output)
            except BaseException as restore_error:
                _preserve_standard_swap_failure(
                    output,
                    rollback,
                    stage,
                    previous_snapshot,
                    staged_snapshot,
                    restore_error,
                )
            _update_standard_recovery(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                expected_states={"output-moved"},
                state="restored",
            )
        _preserve_standard_swap_failure(
            output,
            rollback,
            stage,
            previous_snapshot,
            staged_snapshot,
            publish_error,
        )
    _update_standard_recovery(
        output,
        rollback,
        stage,
        previous_snapshot,
        staged_snapshot,
        expected_states={"prepared", "output-moved"},
        state="published",
    )
    try:
        published_snapshot = _standard_tree_snapshot(output)
    except Exception as validation_error:
        raise _ManualRecoveryRequired(f"swap recovery required: {recovery_path}") from validation_error
    if published_snapshot != staged_snapshot:
        raise _ManualRecoveryRequired(
            f"swap recovery required: {recovery_path}"
        )
    if rollback is not None and rollback.exists():
        assert previous_snapshot is not None
        _validate_standard_temp(rollback, output, "rollback", previous_snapshot)
        try:
            _write_standard_completion(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
            )
        except BaseException as completion_error:
            raise _ManualRecoveryRequired(
                f"swap recovery required: {recovery_path}"
            ) from completion_error
    _archive_standard_recovery(output, recovery_path, recovery_path.read_bytes())

def _render_standard_stage(
    output: Path,
    generated: list[tuple[str, str]],
    registry: dict[str, Any],
    previous_snapshot: _TreeSnapshot | None,
) -> list[str]:
    registry_text = json.dumps(registry, indent=2) + "\n"
    staged_snapshot = _standard_snapshot_from_contents(
        [*generated, ("registry.json", registry_text)]
    )
    expected = [relative for relative, _content in generated]
    if previous_snapshot == staged_snapshot:
        return sorted([*expected, "registry.json"])
    stage = _standard_temp_path(output, "stage")
    stage.mkdir(parents=False, exist_ok=False)
    try:
        for relative, content in generated:
            destination = _safe_standard_destination(stage, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
        registry_path = _safe_standard_destination(stage, "registry.json")
        registry_path.write_text(registry_text, encoding="utf-8", newline="\n")
        _validate_standard_tree(
            stage,
            expected_files=expected,
            expected_snapshot=staged_snapshot,
        )
        _swap_standard_stage(stage, output, staged_snapshot, previous_snapshot)
        return sorted([*expected, "registry.json"])
    except _ManualRecoveryRequired:
        raise
    except BaseException as render_error:
        if stage.exists():
            rollback = (
                _standard_temp_path(output, "rollback")
                if previous_snapshot is not None
                else None
            )
            _preserve_standard_swap_failure(
                output,
                rollback,
                stage,
                previous_snapshot,
                staged_snapshot,
                render_error,
            )
        raise

def _write_standard_adapter(root: Path, target: str, output: Path) -> dict[str, object]:
    capabilities = _capabilities(root)
    _assert_no_reparse_path(output)
    _assert_disjoint_output(output, [root / "skills"])
    _recover_standard_swap_if_needed(output)
    previous_snapshot = _prepare_managed_output(output)
    generated: list[tuple[str, str]] = []
    for capability in capabilities:
        capability_id = _safe_component(capability["id"], "capability id")
        skill_file = root / capability["path"]
        for source in _skill_files(skill_file):
            relative_resource = source.path.relative_to(skill_file.parent)
            relative = PurePosixPath(
                "skills",
                capability_id,
                *relative_resource.parts,
            ).as_posix()
            generated.append((relative, _generated_resource(source)))
    generated = sorted(generated, key=lambda item: item[0])
    registry = {
        "_generated": MARKER,
        "schema_version": 1,
        "target": target,
        "skills": [capability["id"] for capability in capabilities],
        "files": [relative for relative, _content in generated],
    }
    created_parents = _standard_missing_ancestors(output.parent)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        created = _render_standard_stage(output, generated, registry, previous_snapshot)
    except BaseException:
        _cleanup_standard_ancestors(created_parents)
        raise
    return {"target": target, "created": created, "preserved": []}


def generate_adapter(
    root: Path | str,
    target: str,
    output: Path | str,
) -> dict[str, object]:
    if target not in {"hermes", "codex"}:
        raise ValueError(f"unsupported standard adapter target: {target}")
    root_path = Path(root).resolve()
    output_path = Path(os.path.abspath(str(output)))
    return _write_standard_adapter(root_path, target, output_path)
