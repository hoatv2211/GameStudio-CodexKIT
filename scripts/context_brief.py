from __future__ import annotations

"""Build bounded, deterministic goal-context projections without kit imports."""

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


class ContextProjectionError(ValueError):
    """Raised when a projection cannot preserve its bounded contract."""


ProjectionKind = Literal["brief", "working", "resume"]

PROJECTION_LIMITS: dict[ProjectionKind, tuple[int, int]] = {
    "brief": (150, 300),
    "working": (800, 1200),
    "resume": (1600, 2400),
}


@dataclass(frozen=True)
class ContextFact:
    ref: str
    priority: int
    order: int
    text: str
    indivisible: bool = False


def _as_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _as_text(item)) is not None]


def _mapping_strings(value: object, *keys: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [text for key in keys if (text := _as_text(value.get(key))) is not None]


def _goal_id(state: dict[str, object], manifest: dict[str, object]) -> str:
    goal_id = _as_text(state.get("goal_id")) or _as_text(manifest.get("goal_id"))
    if goal_id is None:
        raise ContextProjectionError("state or manifest must contain a goal_id")
    return goal_id


def _active_packet(state: dict[str, object]) -> dict[str, object] | None:
    for key in ("active_packet", "packet"):
        value = state.get(key)
        if isinstance(value, dict):
            return value
    packets = state.get("packets")
    if isinstance(packets, list):
        for packet in packets:
            if isinstance(packet, dict) and packet.get("status") in {
                "running",
                "waiting_input",
                "blocked",
                "failed",
            }:
                return packet
    return None


def _measure(text: str, tokenizer: Callable[[str], int] | None) -> int:
    if tokenizer is None:
        return len(text.encode("utf-8"))
    try:
        count = tokenizer(text)
    except Exception as exc:  # pragma: no cover - caller tokenizer failure
        raise ContextProjectionError("tokenizer failed") from exc
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ContextProjectionError("tokenizer must return a non-negative integer")
    return count


def _build_facts(state: dict[str, object], manifest: dict[str, object]) -> list[ContextFact]:
    goal_id = _goal_id(state, manifest)
    facts: list[ContextFact] = []
    context = state.get("context_facts")
    if not isinstance(context, dict):
        context = {}

    def add(ref: str, priority: int, text: str, *, indivisible: bool = False) -> None:
        facts.append(ContextFact(ref, priority, len(facts), text, indivisible))

    scope = _strings(manifest.get("scope")) + _strings(manifest.get("do_not_touch"))
    if scope:
        add("manifest#scope", 0, "Safety/scope: " + " | ".join(scope))
    for index, blocker in enumerate(_strings(context.get("blockers"))):
        add(f"state#context_facts#blockers[{index}]", 0, f"Blocker: {blocker}")

    active = _active_packet(state)
    if active is not None:
        packet_id = _as_text(active.get("id")) or "active"
        summary = _as_text(active.get("summary")) or _as_text(active.get("objective")) or ""
        status = _as_text(active.get("status"))
        detail = " | ".join(part for part in (packet_id, status, summary) if part)
        add(f"{goal_id}#{packet_id}", 1, f"Active packet: {detail}")
    if (next_action := _as_text(state.get("next_action"))) is not None:
        add("state#next_action", 1, f"Next action: {next_action}")

    for index, changed_file in enumerate(_strings(context.get("changed_files"))):
        add(f"state#context_facts#changed_files[{index}]", 2, f"Changed file: {changed_file}")
    for index, path in enumerate(_strings(context.get("indivisible_paths"))):
        add(path, 2, f"Path: {path}", indivisible=True)
    for index, path in enumerate(item for item in scope if "/" in item or "\\" in item):
        add(f"manifest#paths[{index}]", 2, f"Path: {path}")
    for index, command in enumerate(_strings(context.get("commands"))):
        add(f"state#context_facts#commands[{index}]", 2, f"Command: {command}")
    for index, timing in enumerate(_strings(context.get("timing"))):
        add(f"state#context_facts#timing[{index}]", 2, f"Timing: {timing}")
    failures = context.get("failures")
    if isinstance(failures, list):
        for index, failure in enumerate(failures):
            details = _mapping_strings(failure, "summary", "artifact_path", "command")
            if details:
                add(
                    f"state#context_facts#failures[{index}]",
                    2,
                    "Failure: " + " | ".join(details),
                )
    seen_evidence_labels: set[str] = set()

    def add_evidence_label(ref: str, label: str) -> None:
        if label not in seen_evidence_labels:
            seen_evidence_labels.add(label)
            add(ref, 2, f"Evidence label: {label}")

    evidence = state.get("evidence") or state.get("latest_evidence")
    if isinstance(evidence, list):
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                continue
            label = _as_text(item.get("label"))
            details = _mapping_strings(item, "summary", "command", "artifact_path")
            if label is not None:
                add_evidence_label(f"state#evidence[{index}]#label", label)
            if details:
                add(f"state#evidence[{index}]", 2, "Evidence: " + " | ".join(details))
    for index, label in enumerate(_strings(context.get("evidence_labels"))):
        add_evidence_label(f"state#context_facts#evidence_labels[{index}]", label)

    for index, decision in enumerate(_strings(context.get("decisions"))):
        add(f"state#context_facts#decisions[{index}]", 3, f"Decision: {decision}")
    for index, dependency in enumerate(_strings(context.get("dependencies"))):
        add(f"state#context_facts#dependencies[{index}]", 3, f"Dependency: {dependency}")
    history = state.get("revision_history")
    if isinstance(history, list):
        seen: set[str] = set()
        for index, event in enumerate(history):
            if not isinstance(event, dict):
                continue
            details: list[str] = []
            if (event_id := _as_text(event.get("event_id"))) is not None:
                details.append(f"event {event_id}")
            if (sequence := _as_text(event.get("sequence"))) is not None:
                details.append(f"sequence {sequence}")
            previous_plan = _as_text(event.get("previous_plan_version"))
            plan = _as_text(event.get("plan_version"))
            if previous_plan is not None and plan is not None:
                details.append(f"plan {previous_plan} to {plan}")
            if (reason := _as_text(event.get("revision_reason"))) is not None:
                details.append(f"reason {reason}")
            if (approval := _as_text(event.get("approval_ref"))) is not None:
                details.append(f"approval {approval}")
            if (previous_hash := _as_text(event.get("previous_manifest_hash"))) is not None:
                details.append(f"previous manifest SHA-256 {previous_hash}")
            if (new_hash := _as_text(event.get("new_manifest_hash"))) is not None:
                details.append(f"new manifest SHA-256 {new_hash}")
            if event.get("progress_recalculated") is True:
                details.append("Progress recalculated")
            if event.get("eta_recalculated") is True:
                details.append("ETA recalculated")
            if not details:
                continue
            text = "History: " + " | ".join(details)
            if text not in seen:
                seen.add(text)
                add(f"state#revision_history[{index}]", 3, text)
    return facts


def build_projection(
    state: dict[str, object],
    manifest: dict[str, object],
    kind: ProjectionKind,
    *,
    tokenizer: Callable[[str], int] | None = None,
) -> dict[str, object]:
    if kind not in PROJECTION_LIMITS:
        raise ContextProjectionError(f"unsupported projection kind: {kind}")
    if not isinstance(state, dict) or not isinstance(manifest, dict):
        raise ContextProjectionError("state and manifest must be dictionaries")
    target, hard_cap = PROJECTION_LIMITS[kind]
    facts = sorted(_build_facts(state, manifest), key=lambda fact: (fact.priority, fact.order))
    priority_zero_facts = [fact for fact in facts if fact.priority == 0]
    priority_zero_text = "\n".join(fact.text for fact in priority_zero_facts)
    priority_zero_overflows = (
        bool(priority_zero_facts)
        and _measure(priority_zero_text, tokenizer) > hard_cap
    )
    blocked_refs = [
        fact.ref
        for fact in facts
        if (
            (fact.priority == 0 and priority_zero_overflows)
            or (fact.indivisible and _measure(fact.text, tokenizer) > hard_cap)
        )
    ]
    if blocked_refs:
        return {
            "schema_version": 1,
            "goal_id": _goal_id(state, manifest),
            "projection": kind,
            "status": "BLOCKED",
            "count_kind": "exact_tokenizer" if tokenizer else "utf8_byte_fallback",
            "count": 0,
            "target": target,
            "hard_cap": hard_cap,
            "text": "",
            "required_fact_refs": list(dict.fromkeys(blocked_refs)),
            "evidence_label": "BLOCKED",
        }

    selected: list[ContextFact] = []
    text = ""
    for fact in facts:
        candidate = f"{text}\n{fact.text}" if text else fact.text
        if _measure(candidate, tokenizer) <= hard_cap:
            selected.append(fact)
            text = candidate
    if not text:
        raise ContextProjectionError("no context fact fits the projection hard cap")
    projection: dict[str, object] = {
        "schema_version": 1,
        "goal_id": _goal_id(state, manifest),
        "projection": kind,
        "status": "READY",
        "count_kind": "exact_tokenizer" if tokenizer else "utf8_byte_fallback",
        "count": _measure(text, tokenizer),
        "target": target,
        "hard_cap": hard_cap,
        "text": text,
        "required_fact_refs": list(dict.fromkeys(fact.ref for fact in selected)),
        "evidence_label": "Snapshot" if tokenizer else "Unverified",
    }
    validate_projection(projection, tokenizer=tokenizer)
    return projection


def validate_projection(
    projection: dict[str, object],
    *,
    tokenizer: Callable[[str], int] | None = None,
) -> None:
    if not isinstance(projection, dict):
        raise ContextProjectionError("projection must be a dictionary")
    required = {
        "schema_version", "goal_id", "projection", "status", "count_kind", "count",
        "target", "hard_cap", "text", "required_fact_refs", "evidence_label",
    }
    if set(projection) != required:
        raise ContextProjectionError("projection fields do not match the projection schema")
    kind = projection["projection"]
    if kind not in PROJECTION_LIMITS:
        raise ContextProjectionError("invalid projection kind")
    target, hard_cap = PROJECTION_LIMITS[kind]
    if projection["schema_version"] != 1 or projection["target"] != target or projection["hard_cap"] != hard_cap:
        raise ContextProjectionError("projection limits do not match its kind")
    if projection["status"] not in {"READY", "BLOCKED"}:
        raise ContextProjectionError("invalid projection status")
    expected_kind = "exact_tokenizer" if tokenizer else "utf8_byte_fallback"
    if projection["count_kind"] != expected_kind:
        raise ContextProjectionError("projection count_kind does not match its measurement")
    text = projection["text"]
    if not isinstance(text, str):
        raise ContextProjectionError("projection text must be a string")
    count = projection["count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ContextProjectionError("projection count must be a non-negative integer")
    if count != _measure(text, tokenizer) or count > hard_cap:
        raise ContextProjectionError("projection count does not match bounded text")
    refs = projection["required_fact_refs"]
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
        raise ContextProjectionError("projection must retain required fact references")
    if projection["status"] == "READY" and not text:
        raise ContextProjectionError("ready projection must contain text")
    if projection["status"] == "BLOCKED" and text:
        raise ContextProjectionError("blocked projection must not contain standalone text")
    if projection["status"] == "READY" and tokenizer is None and projection["evidence_label"] != "Unverified":
        raise ContextProjectionError("fallback projection target count is unverified")
    if projection["status"] == "BLOCKED" and projection["evidence_label"] != "BLOCKED":
        raise ContextProjectionError("blocked projection must carry a BLOCKED evidence label")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _markdown(projection: dict[str, object]) -> str:
    lines = [
        f"# Goal context: {projection['projection']}",
        "",
        f"Status: {projection['status']}",
        f"Measurement: {projection['count']} / {projection['hard_cap']} ({projection['count_kind']})",
        "",
        "## Projected text",
        str(projection["text"]) or "No standalone context can fit the hard cap.",
    ]
    if projection["projection"] == "resume":
        lines.extend([
            "",
            "studio-handoff must refresh Git state, commands, restore information, and the reactivation prompt before durable transfer.",
        ])
    return "\n".join(lines) + "\n"


def _write_projection(goal_root: Path, state: dict[str, object], manifest: dict[str, object], kind: ProjectionKind, tokenizer: Callable[[str], int] | None) -> list[Path]:
    projection = build_projection(state, manifest, kind, tokenizer=tokenizer)
    context_dir = goal_root / "context"
    json_path = context_dir / f"{kind}.json"
    markdown_path = context_dir / f"{kind}.md"
    _atomic_write(json_path, json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _atomic_write(markdown_path, _markdown(projection))
    return [json_path, markdown_path]


def write_projections(goal_root: Path, *, tokenizer: Callable[[str], int] | None = None) -> list[Path]:
    state_path = goal_root / "state.json"
    manifest_path = goal_root / "goal.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContextProjectionError("unable to load state.json and goal.json") from exc
    if not isinstance(state, dict) or not isinstance(manifest, dict):
        raise ContextProjectionError("state.json and goal.json must contain objects")
    paths: list[Path] = []
    for kind in ("brief", "working", "resume"):
        paths.extend(_write_projection(goal_root, state, manifest, kind, tokenizer))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write bounded goal-context projections.")
    parser.add_argument("--goal-root", type=Path, required=True)
    parser.add_argument("--projection", choices=("all", "brief", "working", "resume"), default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.projection == "all":
        paths = write_projections(args.goal_root)
    else:
        state = json.loads((args.goal_root / "state.json").read_text(encoding="utf-8"))
        manifest = json.loads((args.goal_root / "goal.json").read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(manifest, dict):
            raise ContextProjectionError("state.json and goal.json must contain objects")
        paths = _write_projection(args.goal_root, state, manifest, args.projection, None)
    rendered = [str(path) for path in paths]
    if args.json:
        print(json.dumps(rendered))
    else:
        print("\n".join(rendered))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
