from __future__ import annotations

import copy
import hashlib
import io
import json
import threading
import time
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

FIXED_UTC = "2026-09-04T02:00:00Z"
GOAL_ID = "goal-demo-001"
EPOCH_ID = "epoch-demo-001"
THREAD_ID = "thread-demo"
SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
WORKFLOW_ID = "studio-goal-progress"
PACKET_ID = "packet-contract"


def run_cli(
    main: Callable[[list[str]], int], argv: list[str]
) -> tuple[int, dict[str, object], str]:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = main(argv)
    raw = output.getvalue()
    return exit_code, json.loads(raw), raw


@contextmanager
def running_private_runtime(
    goal_root: Path,
    *,
    capability: str = "test-submission-secret",
    idle_timeout_seconds: int = 1800,
) -> Iterator[tuple[object, Path, dict[str, object], threading.Thread]]:
    from scripts.goal_progress_server import GoalProgressRuntime

    runtime_dir = goal_root / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    token_file = runtime_dir / "submission-token"
    token_file.write_text(capability, encoding="utf-8")
    runtime = GoalProgressRuntime(
        goal_root,
        capability,
        idle_timeout_seconds=idle_timeout_seconds,
    )
    thread = threading.Thread(target=runtime.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3.0
    writer_info = runtime_dir / "writer-info.json"
    while time.monotonic() < deadline:
        if writer_info.is_file():
            info = json.loads(writer_info.read_text(encoding="utf-8"))
            break
        if not thread.is_alive():
            raise AssertionError("private runtime stopped before readiness")
        time.sleep(0.01)
    else:
        runtime.request_stop()
        thread.join(timeout=3.0)
        raise AssertionError("private runtime did not become ready")
    try:
        yield runtime, token_file, info, thread
    finally:
        runtime.request_stop()
        thread.join(timeout=3.0)
        if thread.is_alive():
            raise AssertionError("private runtime thread did not stop")


class FakeClock:
    def __init__(
        self,
        *,
        utc_now: str = FIXED_UTC,
        monotonic: float = 100.0,
    ) -> None:
        self._utc_now = datetime.strptime(utc_now, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self._monotonic = monotonic

    def utc_now(self) -> str:
        return self._utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._utc_now += timedelta(seconds=seconds)
        self._monotonic += seconds


def deep_copy(value: dict[str, object]) -> dict[str, object]:
    return copy.deepcopy(value)


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "goal_id": GOAL_ID,
        "title": "Verify the progress contract",
        "repository_root": "D:/work/game",
        "repository_snapshot": "dev@0123456789abcdef0123456789abcdef01234567",
        "created_at": FIXED_UTC,
        "plan_version": 1,
        "scope": ["scripts/goal_progress_core.py"],
        "do_not_touch": ["Assets/Production"],
        "packets": [
            {
                "id": PACKET_ID,
                "workflow_id": WORKFLOW_ID,
                "owner": "main-thread",
                "objective": "Verify the event contract",
                "progress_weight": 3,
                "dependencies": [],
                "completion_criteria": ["Focused contract tests pass"],
                "required_evidence": ["test-command"],
                "estimate_seconds": {"low": 60, "high": 120},
                "owned_paths": ["scripts/goal_progress_core.py"],
                "excluded_paths": ["Assets/Production"],
            }
        ],
        "final_verification_required": ["repository-gates"],
        "runtime_bindings": [{"kind": "codex_thread", "id": THREAD_ID}],
        "timing_policy": {"max_active_timed_packets": 1},
    }


def started_candidate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": "event-demo-started",
        "goal_id": GOAL_ID,
        "plan_version": 1,
        "sequence": 1,
        "emitted_at": FIXED_UTC,
        "writer_epoch_id": EPOCH_ID,
        "monotonic_offset_ms": 0,
        "source": "kit_workflow",
        "event_type": "goal.started",
        "packet_id": None,
        "payload": {"manifest": valid_manifest()},
        "authority": None,
        "summary": "Goal started from the canonical manifest.",
        "evidence": [],
        "raw_log_ref": None,
        "record_hash": SHA256,
    }


def accepted_started_event() -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": "event-demo-accepted",
        "goal_id": GOAL_ID,
        "plan_version": 1,
        "sequence": 2,
        "emitted_at": FIXED_UTC,
        "writer_epoch_id": EPOCH_ID,
        "monotonic_offset_ms": 5,
        "source": "kit_workflow",
        "event_type": "packet.started",
        "packet_id": PACKET_ID,
        "payload": {
            "packet_id": PACKET_ID,
            "state": "running",
        },
        "authority": {"kind": "codex_thread", "id": THREAD_ID},
        "summary": "Packet started for focused contract validation.",
        "evidence": [
            {
                "id": "evidence-demo-001",
                "label": "Verified",
                "kind": "command",
                "summary": "Focused contract tests passed.",
                "command": "python -B -m unittest discover -s tests/goal_progress -p \"test_goal_progress_schemas.py\" -v",
                "exit_code": 0,
                "artifact_path": None,
                "sha256": None,
            }
        ],
        "raw_log_ref": None,
        "record_hash": SHA256,
    }


def valid_state() -> dict[str, object]:
    return {
        "schema_version": 1,
        "goal_id": GOAL_ID,
        "plan_version": 1,
        "manifest_hash": SHA256,
        "goal_state": "planned",
        "packets": [
            {
                "id": "packet-contract",
                "status": "queued",
                "owner": "main-thread",
                "objective": "Verify the event contract",
                "progress_weight": 3,
            }
        ],
        "progress": {
            "verified_weight": 0,
            "active_planned_weight": 3,
            "percent": 0.0,
            "display_percent": 0,
        },
        "eta": {"status": "Ready", "summary": "About one minute remaining."},
        "revision_history": [
            {
                "event_id": "event-plan-revised-2",
                "sequence": 2,
                "previous_plan_version": 1,
                "plan_version": 2,
                "revision_reason": "Add the reviewed follow-up packet.",
                "approval_ref": "reviewer:MAD",
                "previous_manifest_hash": "a" * 64,
                "new_manifest_hash": "b" * 64,
                "progress_recalculated": True,
                "eta_recalculated": True,
            },
        ],
        "context_facts": {
            "blockers": [],
            "failures": [],
            "changed_files": [],
            "decisions": [],
            "commands": [],
            "timing": [],
            "evidence_labels": [],
            "indivisible_paths": [],
            "dependencies": [],
        },
        "latest_evidence": [
            {
                "id": "evidence-demo-001",
                "label": "Verified",
                "kind": "command",
                "summary": "Focused contract tests passed.",
                "command": "python -B -m unittest discover -s tests/goal_progress -p \"test_goal_progress_schemas.py\" -v",
                "exit_code": 0,
                "artifact_path": None,
                "sha256": None,
            }
        ],
        "next_action": "Continue the focused contract tests.",
        "updated_at": FIXED_UTC,
        "stale": False,
        "warnings": [],
    }


def valid_projection() -> dict[str, object]:
    return {
        "schema_version": 1,
        "goal_id": GOAL_ID,
        "projection": "brief",
        "status": "READY",
        "count_kind": "utf8_byte_fallback",
        "count": 1,
        "target": 1,
        "hard_cap": 2,
        "text": "1 fact ready for verification.",
        "required_fact_refs": ["goal-demo-001#packet-contract"],
        "evidence_label": "Snapshot",
    }


def canonical_json_for_tests(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json_for_tests(
    value: object, *, omit: frozenset[str] = frozenset()
) -> str:
    payload = value
    if isinstance(value, dict) and omit:
        payload = {key: item for key, item in value.items() if key not in omit}
    return hashlib.sha256(canonical_json_for_tests(payload).encode("utf-8")).hexdigest()


def packet_definition(
    packet_id: str,
    *,
    workflow_id: str = WORKFLOW_ID,
    owner: str = "main-thread",
    objective: str = "Verify the event contract",
    progress_weight: int = 3,
    dependencies: list[str] | None = None,
    required_evidence: list[str] | None = None,
    estimate_low: int = 60,
    estimate_high: int = 120,
) -> dict[str, object]:
    return {
        "id": packet_id,
        "workflow_id": workflow_id,
        "owner": owner,
        "objective": objective,
        "progress_weight": progress_weight,
        "dependencies": list(dependencies or []),
        "completion_criteria": ["Focused contract tests pass"],
        "required_evidence": list(required_evidence or ["test-command"]),
        "estimate_seconds": {"low": estimate_low, "high": estimate_high},
        "owned_paths": ["scripts/goal_progress_core.py"],
        "excluded_paths": ["Assets/Production"],
    }


def manifest_for_runtime(
    *,
    packets: list[dict[str, object]] | None = None,
    plan_version: int = 1,
    final_verification_required: list[str] | None = None,
) -> dict[str, object]:
    manifest = deep_copy(valid_manifest())
    manifest["plan_version"] = plan_version
    manifest["packets"] = list(
        packets or [packet_definition(PACKET_ID, progress_weight=3)]
    )
    manifest["final_verification_required"] = list(
        final_verification_required or ["repository-gates"]
    )
    return manifest


def runtime_authority(
    *,
    packet_id: str = PACKET_ID,
    workflow_id: str = WORKFLOW_ID,
    owner: str = "main-thread",
    runtime_binding: dict[str, str] | None = None,
    expected_prior_state: str = "queued",
) -> dict[str, object]:
    return {
        "kind": "codex_thread",
        "id": THREAD_ID,
        "workflow_id": workflow_id,
        "owner": owner,
        "runtime_binding": deep_copy(runtime_binding or {"kind": "codex_thread", "id": THREAD_ID}),
        "packet_id": packet_id,
        "expected_prior_state": expected_prior_state,
    }


def _accepted_event_record(
    event: dict[str, object],
) -> dict[str, object]:
    accepted = deep_copy(event)
    accepted["record_hash"] = sha256_json_for_tests(accepted, omit=frozenset({"record_hash"}))
    return accepted


def started_event(
    *,
    manifest: dict[str, object] | None = None,
    event_id: str = "event-goal-started",
    sequence: int = 1,
    emitted_at: str = FIXED_UTC,
) -> dict[str, object]:
    return _accepted_event_record(
        {
            "schema_version": 1,
            "event_id": event_id,
            "goal_id": GOAL_ID,
            "plan_version": int((manifest or valid_manifest())["plan_version"]),
            "sequence": sequence,
            "emitted_at": emitted_at,
            "writer_epoch_id": EPOCH_ID,
            "monotonic_offset_ms": 0,
            "source": "kit_workflow",
            "event_type": "goal.started",
            "packet_id": None,
            "payload": {"manifest": deep_copy(manifest or valid_manifest())},
            "authority": None,
            "summary": "Goal started from the canonical manifest.",
            "evidence": [],
            "raw_log_ref": None,
            "record_hash": "",
        }
    )


def command_evidence(
    evidence_id: str,
    *,
    summary: str = "Focused contract tests passed.",
    command: str = 'python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_schemas.py" -v',
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "label": "Verified",
        "kind": "command",
        "summary": summary,
        "command": command,
        "exit_code": 0,
        "artifact_path": None,
        "sha256": None,
    }


def artifact_evidence(
    evidence_id: str,
    *,
    summary: str = "Final repository gates artifact recorded.",
    artifact_path: str = "evidence/local/repository-gates.json",
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "label": "Verified",
        "kind": "artifact",
        "summary": summary,
        "command": None,
        "exit_code": None,
        "artifact_path": artifact_path,
        "sha256": SHA256,
    }


def packet_event(
    event_type: str,
    *,
    sequence: int,
    state: str,
    packet_id: str = PACKET_ID,
    plan_version: int = 1,
    event_id: str | None = None,
    emitted_at: str = FIXED_UTC,
    summary: str | None = None,
    expected_prior_state: str = "queued",
    evidence: list[dict[str, object]] | None = None,
    payload_updates: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {"packet_id": packet_id, "state": state}
    if payload_updates:
        payload.update(payload_updates)
    return _accepted_event_record(
        {
            "schema_version": 1,
            "event_id": event_id or f"event-{event_type.replace('.', '-')}-{sequence}",
            "goal_id": GOAL_ID,
            "plan_version": plan_version,
            "sequence": sequence,
            "emitted_at": emitted_at,
            "writer_epoch_id": EPOCH_ID,
            "monotonic_offset_ms": sequence * 5,
            "source": "kit_workflow",
            "event_type": event_type,
            "packet_id": packet_id,
            "payload": payload,
            "authority": runtime_authority(
                packet_id=packet_id,
                expected_prior_state=expected_prior_state,
            ),
            "summary": summary or f"{packet_id} moved to {state}.",
            "evidence": list(evidence or []),
            "raw_log_ref": None,
            "record_hash": "",
        }
    )


def evidence_observed_event(
    *,
    sequence: int,
    packet_id: str = PACKET_ID,
    workflow_id: str = WORKFLOW_ID,
    plan_version: int = 1,
    required_kind: str = "test-command",
    evidence_id: str = "evidence-observed-001",
    event_id: str | None = None,
) -> dict[str, object]:
    return _accepted_event_record(
        {
            "schema_version": 1,
            "event_id": event_id or f"event-evidence-observed-{sequence}",
            "goal_id": GOAL_ID,
            "plan_version": plan_version,
            "sequence": sequence,
            "emitted_at": FIXED_UTC,
            "writer_epoch_id": EPOCH_ID,
            "monotonic_offset_ms": sequence * 5,
            "source": "kit_workflow",
            "event_type": "evidence.observed",
            "packet_id": packet_id,
            "payload": {
                "workflow_id": workflow_id,
                "packet_id": packet_id,
                "runtime_binding": {"kind": "codex_thread", "id": THREAD_ID},
                "required_evidence_kind": required_kind,
            },
            "authority": None,
            "summary": "Observed verification evidence for the packet.",
            "evidence": [command_evidence(evidence_id)],
            "raw_log_ref": None,
            "record_hash": "",
        }
    )


def context_facts_payload() -> dict[str, object]:
    return {
        "blockers": ["BLOCKED: reviewer approval is required."],
        "failures": [
            {
                "summary": "Shader.Find returned null",
                "artifact_path": "D:/work/game/Assets/UI/HUD.prefab",
            }
        ],
        "changed_files": [
            "scripts/context_brief.py",
            "D:/work/game/Assets/Generated/Context Projection.md",
        ],
        "decisions": ["Keep deterministic ordering."],
        "commands": ["python -B scripts/validate.py ."],
        "timing": ["150 ms"],
        "evidence_labels": ["Verified"],
        "indivisible_paths": ["D:/work/game/Assets/UI/HUD.prefab"],
    }


def context_refreshed_event(
    *,
    sequence: int,
    payload: dict[str, object] | None = None,
    plan_version: int = 1,
    event_id: str | None = None,
) -> dict[str, object]:
    return _accepted_event_record(
        {
            "schema_version": 1,
            "event_id": event_id or f"event-context-refreshed-{sequence}",
            "goal_id": GOAL_ID,
            "plan_version": plan_version,
            "sequence": sequence,
            "emitted_at": FIXED_UTC,
            "writer_epoch_id": EPOCH_ID,
            "monotonic_offset_ms": sequence * 5,
            "source": "kit_workflow",
            "event_type": "context.refreshed",
            "packet_id": None,
            "payload": deep_copy(payload or context_facts_payload()),
            "authority": None,
            "summary": "Structured context facts refreshed.",
            "evidence": [],
            "raw_log_ref": None,
            "record_hash": "",
        }
    )


def plan_revised_event(
    manifest: dict[str, object],
    *,
    sequence: int,
    previous_manifest_hash: str,
    new_manifest_hash: str | None = None,
    expected_prior_state: str = "planned",
    event_id: str | None = None,
) -> dict[str, object]:
    return _accepted_event_record(
        {
            "schema_version": 1,
            "event_id": event_id or f"event-plan-revised-{sequence}",
            "goal_id": GOAL_ID,
            "plan_version": int(manifest["plan_version"]),
            "sequence": sequence,
            "emitted_at": FIXED_UTC,
            "writer_epoch_id": EPOCH_ID,
            "monotonic_offset_ms": sequence * 5,
            "source": "kit_workflow",
            "event_type": "plan.revised",
            "packet_id": None,
            "payload": {
                "manifest": deep_copy(manifest),
                "previous_manifest_hash": previous_manifest_hash,
                "new_manifest_hash": new_manifest_hash
                or sha256_json_for_tests(manifest),
            },
            "authority": runtime_authority(
                packet_id="plan",
                expected_prior_state=expected_prior_state,
            ),
            "summary": "Plan revised with an updated manifest.",
            "evidence": [],
            "raw_log_ref": None,
            "record_hash": "",
        }
    )


def goal_terminal_event(
    event_type: str,
    *,
    sequence: int,
    plan_version: int = 1,
    summary_text: str = "Goal completed after final verification.",
    final_verification_evidence_ids: list[str] | None = None,
    evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return _accepted_event_record(
        {
            "schema_version": 1,
            "event_id": f"event-{event_type.replace('.', '-')}-{sequence}",
            "goal_id": GOAL_ID,
            "plan_version": plan_version,
            "sequence": sequence,
            "emitted_at": FIXED_UTC,
            "writer_epoch_id": EPOCH_ID,
            "monotonic_offset_ms": sequence * 5,
            "source": "kit_workflow",
            "event_type": event_type,
            "packet_id": None,
            "payload": {
                "summary": summary_text,
                "final_verification_evidence_ids": list(
                    final_verification_evidence_ids or []
                ),
            },
            "authority": runtime_authority(
                packet_id="goal",
                expected_prior_state="running",
            ),
            "summary": summary_text,
            "evidence": list(evidence or []),
            "raw_log_ref": None,
            "record_hash": "",
        }
    )


def event_sequence_for_verified_packet() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    manifest = manifest_for_runtime()
    started = started_event(manifest=manifest, sequence=1)
    running = packet_event(
        "packet.started",
        sequence=2,
        state="running",
        expected_prior_state="queued",
    )
    observed = evidence_observed_event(sequence=3)
    verified = packet_event(
        "packet.verified",
        sequence=4,
        state="verified",
        expected_prior_state="running",
        payload_updates={"evidence_ids": ["evidence-observed-001"]},
    )
    return started, running, observed, verified
