from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.context_brief import (
    ContextProjectionError,
    PROJECTION_LIMITS,
    build_projection,
    validate_projection,
    write_projections,
)
from scripts.goal_progress_core import GoalProgressError, reduce_events
from tests.goal_progress.support import (
    PACKET_ID,
    context_facts_payload,
    context_refreshed_event,
    evidence_observed_event,
    packet_definition,
    packet_event,
    started_event,
    valid_manifest,
)


EXACT_LITERALS = (
    "D:/work/game/Assets/UI/HUD.prefab",
    'python -B scripts/validate.py .',
    "Shader.Find returned null",
    "do NOT edit Assets/Production",
    "150 ms",
    "BLOCKED",
)


def make_schema_valid_inputs(
    *,
    packet_status: str = "running",
    context_payload: dict[str, object] | None = None,
    scope: list[str] | None = None,
    do_not_touch: list[str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    manifest = valid_manifest()
    manifest["scope"] = list(
        scope
        or [
            "D:/work/game/Assets/UI/HUD.prefab",
            "do NOT edit Assets/Production",
        ]
    )
    manifest["do_not_touch"] = list(
        ["Assets/Production"] if do_not_touch is None else do_not_touch
    )
    manifest["packets"] = [
        packet_definition("packet-prerequisite", progress_weight=1),
        packet_definition(
            PACKET_ID,
            progress_weight=3,
            dependencies=["packet-prerequisite"],
        ),
    ]
    events = [
        started_event(manifest=manifest),
        packet_event(
            "packet.started",
            sequence=2,
            packet_id="packet-prerequisite",
            state="running",
            expected_prior_state="queued",
        ),
        evidence_observed_event(
            sequence=3,
            packet_id="packet-prerequisite",
            evidence_id="evidence-prerequisite",
        ),
        packet_event(
            "packet.verified",
            sequence=4,
            packet_id="packet-prerequisite",
            state="verified",
            expected_prior_state="running",
            payload_updates={"evidence_ids": ["evidence-prerequisite"]},
        ),
        packet_event(
            "packet.started",
            sequence=5,
            state="running",
            expected_prior_state="queued",
            summary="python -B scripts/validate.py .",
        ),
    ]
    sequence = 6
    if packet_status != "running":
        event_type = {
            "waiting_input": "packet.waiting_input",
            "blocked": "packet.blocked",
            "failed": "packet.failed",
        }[packet_status]
        events.append(
            packet_event(
                event_type,
                sequence=sequence,
                state=packet_status,
                expected_prior_state="running",
            )
        )
        sequence += 1
    events.append(
        context_refreshed_event(sequence=sequence, payload=context_payload)
    )
    try:
        state = reduce_events(events, now_utc="2026-09-04T02:02:00Z")
    except GoalProgressError as exc:
        raise AssertionError(f"schema-valid context fixture was rejected: {exc}") from exc
    return state, manifest


def make_state() -> dict[str, object]:
    return make_schema_valid_inputs()[0]


def make_manifest() -> dict[str, object]:
    return make_schema_valid_inputs()[1]


class ContextBriefTests(unittest.TestCase):
    def test_projection_limits_and_error_type_are_fixed(self) -> None:
        self.assertEqual(
            {
                "brief": (150, 300),
                "working": (800, 1200),
                "resume": (1600, 2400),
            },
            PROJECTION_LIMITS,
        )
        self.assertTrue(issubclass(ContextProjectionError, ValueError))

    def test_build_projection_preserves_priority_and_literals(self) -> None:
        projection = build_projection(make_state(), make_manifest(), "working")

        self.assertEqual("working", projection["projection"])
        self.assertEqual("READY", projection["status"])
        self.assertEqual("utf8_byte_fallback", projection["count_kind"])
        self.assertEqual("Unverified", projection["evidence_label"])
        self.assertLessEqual(projection["count"], projection["hard_cap"])
        self.assertEqual(projection["count"], len(projection["text"].encode("utf-8")))

        text = projection["text"]
        for literal in EXACT_LITERALS:
            self.assertIn(literal, text)

        self.assertLess(text.index("Safety/scope:"), text.index("Active packet:"))
        self.assertLess(text.index("do NOT edit Assets/Production"), text.index("Blocker:"))
        self.assertLess(text.index("Active packet:"), text.index("Next action:"))
        self.assertLess(text.index("Next action:"), text.index("Changed file:"))
        self.assertLess(text.index("Changed file:"), text.index("Path:"))
        self.assertLess(text.index("Path:"), text.index("Command:"))
        self.assertLess(text.index("Command:"), text.index("Failure:"))
        self.assertLess(text.index("Failure:"), text.index("Evidence label:"))
        self.assertLess(text.index("Evidence label:"), text.index("Decision:"))
        self.assertLess(text.index("Decision:"), text.index("Dependency:"))
        self.assertIn(
            "Changed file: D:/work/game/Assets/Generated/Context Projection.md",
            text,
        )

        self.assertIn("Keep deterministic ordering.", text)
        self.assertEqual(
            [
                "manifest#scope",
                "state#context_facts#blockers[0]",
                "goal-demo-001#packet-contract",
                "state#next_action",
                "state#context_facts#changed_files[0]",
                "state#context_facts#changed_files[1]",
                "D:/work/game/Assets/UI/HUD.prefab",
                "manifest#paths[0]",
                "manifest#paths[1]",
                "manifest#paths[2]",
                "state#context_facts#commands[0]",
                "state#context_facts#timing[0]",
                "state#context_facts#failures[0]",
                "state#evidence[0]#label",
                "state#evidence[0]",
                "state#context_facts#decisions[0]",
                "state#context_facts#dependencies[0]",
            ],
            projection["required_fact_refs"],
        )

    def test_schema_valid_reduced_state_preserves_context_and_active_packet_statuses(self) -> None:
        for status in ("running", "waiting_input", "blocked", "failed"):
            with self.subTest(status=status):
                state, manifest = make_schema_valid_inputs(packet_status=status)
                projection = build_projection(state, manifest, "working")

                self.assertIn(
                    f"Active packet: {PACKET_ID} | {status}",
                    projection["text"],
                )
                self.assertIn("Blocker: BLOCKED: reviewer approval is required.", projection["text"])
                self.assertIn("Failure: Shader.Find returned null", projection["text"])
                self.assertIn("Changed file: scripts/context_brief.py", projection["text"])
                self.assertIn("Decision: Keep deterministic ordering.", projection["text"])
                self.assertIn("Command: python -B scripts/validate.py .", projection["text"])
                self.assertIn("Timing: 150 ms", projection["text"])
                self.assertIn("Evidence label: Verified", projection["text"])
                self.assertIn("Path: D:/work/game/Assets/UI/HUD.prefab", projection["text"])
                self.assertIn("Dependency: packet-prerequisite", projection["text"])

    def test_brief_projection_blocks_on_single_indivisible_overflow(self) -> None:
        long_path = "D:/work/game/" + ("a" * 337)
        second_long_path = "D:/work/game/" + ("b" * 337)
        payload = context_facts_payload()
        payload["indivisible_paths"] = [long_path, second_long_path]
        payload["blockers"] = [long_path]
        state, manifest = make_schema_valid_inputs(context_payload=payload)

        projection = build_projection(state, manifest, "brief")

        self.assertEqual("BLOCKED", projection["status"])
        self.assertEqual("", projection["text"])
        self.assertTrue(projection["required_fact_refs"])
        self.assertEqual(
            [
                "manifest#scope",
                "state#context_facts#blockers[0]",
                long_path,
                second_long_path,
            ],
            projection["required_fact_refs"],
        )

    def test_brief_blocks_when_required_safety_scope_cannot_fit(self) -> None:
        state, manifest = make_schema_valid_inputs(
            scope=["do NOT edit " + ("Assets/Production/" * 20)],
            do_not_touch=[],
        )

        projection = build_projection(state, manifest, "brief")

        self.assertEqual("BLOCKED", projection["status"])
        self.assertEqual("", projection["text"])
        self.assertEqual(
            ["manifest#scope", "state#context_facts#blockers[0]"],
            projection["required_fact_refs"],
        )

    def test_brief_blocks_when_required_priority_zero_facts_overflow_together(self) -> None:
        payload = context_facts_payload()
        payload["blockers"] = ["BLOCKED: " + ("b" * 115)]
        state, manifest = make_schema_valid_inputs(
            context_payload=payload,
            scope=["D:/work/game/" + ("s" * 155)],
            do_not_touch=[],
        )

        projection = build_projection(state, manifest, "brief")

        self.assertEqual("BLOCKED", projection["status"])
        self.assertEqual("", projection["text"])
        self.assertEqual(
            ["manifest#scope", "state#context_facts#blockers[0]"],
            projection["required_fact_refs"],
        )

    def test_projects_context_evidence_labels_in_deduplicated_order(self) -> None:
        payload = context_facts_payload()
        payload["evidence_labels"] = ["Verified", "Snapshot", "Verified"]
        state, manifest = make_schema_valid_inputs(context_payload=payload)

        projection = build_projection(state, manifest, "working")
        text = projection["text"]

        self.assertLess(text.index("Failure:"), text.index("Evidence label: Verified"))
        self.assertLess(
            text.index("Evidence label: Verified"),
            text.index("Evidence label: Snapshot"),
        )
        self.assertLess(text.index("Evidence label: Snapshot"), text.index("Decision:"))
        self.assertEqual(1, text.count("Evidence label: Verified"))
        self.assertEqual(
            [
                "state#evidence[0]#label",
                "state#context_facts#evidence_labels[1]",
            ],
            [
                ref
                for ref in projection["required_fact_refs"]
                if "#label" in ref or "#evidence_labels" in ref
            ],
        )

    def test_resume_projection_preserves_closed_plan_revision_history(self) -> None:
        state, manifest = make_schema_valid_inputs()
        revision = {
            "event_id": "event-plan-revised-7",
            "sequence": 7,
            "previous_plan_version": 1,
            "plan_version": 2,
            "revision_reason": "Approved scope correction.",
            "approval_ref": "reviewer:MAD",
            "previous_manifest_hash": "a" * 64,
            "new_manifest_hash": "b" * 64,
            "progress_recalculated": True,
            "eta_recalculated": True,
        }
        state["revision_history"] = [revision, dict(revision)]
        schema = json.loads(
            (Path(__file__).resolve().parents[2] / "evals" / "schema" / "studio-goal-state.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(schema).validate(state)

        projection = build_projection(state, manifest, "resume")

        history = (
            "History: event event-plan-revised-7 | sequence 7 | plan 1 to 2 | "
            "reason Approved scope correction. | approval reviewer:MAD | "
            f"previous manifest SHA-256 {'a' * 64} | new manifest SHA-256 {'b' * 64} | "
            "Progress recalculated | ETA recalculated"
        )
        self.assertIn(history, projection["text"])
        self.assertEqual(1, projection["text"].count(history))
        self.assertEqual(
            ["state#revision_history[0]"],
            [
                ref
                for ref in projection["required_fact_refs"]
                if ref.startswith("state#revision_history[")
            ],
        )

    def test_exact_tokenizer_and_fallback_counts_validate_strictly(self) -> None:
        tokenizer = lambda text: sum(1 for chunk in text.split() if chunk)

        exact = build_projection(make_state(), make_manifest(), "resume", tokenizer=tokenizer)
        self.assertEqual("exact_tokenizer", exact["count_kind"])
        self.assertEqual(tokenizer(exact["text"]), exact["count"])
        validate_projection(exact, tokenizer=tokenizer)

        for kind, cap in (("brief", 300), ("working", 1200), ("resume", 2400)):
            with self.subTest(kind=kind):
                fallback = build_projection(make_state(), make_manifest(), kind)
                self.assertEqual("utf8_byte_fallback", fallback["count_kind"])
                self.assertLessEqual(fallback["count"], cap)
                self.assertLessEqual(fallback["count"], fallback["hard_cap"])
                self.assertEqual(fallback["count"], len(fallback["text"].encode("utf-8")))
                self.assertEqual("Unverified", fallback["evidence_label"])
                validate_projection(fallback)

    def test_validate_projection_rejects_tampered_count_and_cap(self) -> None:
        projection = build_projection(make_state(), make_manifest(), "brief")
        tampered_count = dict(projection)
        tampered_count["count"] = projection["count"] + 1
        with self.assertRaises(ContextProjectionError):
            validate_projection(tampered_count)

        tampered_cap = dict(projection)
        tampered_cap["hard_cap"] = max(0, projection["count"] - 1)
        with self.assertRaises(ContextProjectionError):
            validate_projection(tampered_cap)

    def test_write_projections_creates_atomic_json_and_markdown_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir)
            (goal_root / "state.json").write_text(
                json.dumps(make_state(), indent=2),
                encoding="utf-8",
            )
            (goal_root / "goal.json").write_text(
                json.dumps(make_manifest(), indent=2),
                encoding="utf-8",
            )

            paths = write_projections(goal_root)

            self.assertEqual(
                [
                    goal_root / "context" / "brief.json",
                    goal_root / "context" / "brief.md",
                    goal_root / "context" / "working.json",
                    goal_root / "context" / "working.md",
                    goal_root / "context" / "resume.json",
                    goal_root / "context" / "resume.md",
                ],
                paths,
            )

            for path in paths:
                self.assertTrue(path.exists(), path)

            brief = json.loads((goal_root / "context" / "brief.json").read_text(encoding="utf-8"))
            self.assertIn("projection", brief)
            self.assertIn("text", (goal_root / "context" / "brief.md").read_text(encoding="utf-8"))
            self.assertIn(
                "studio-handoff must refresh Git state, commands, restore information, and the reactivation prompt before durable transfer.",
                (goal_root / "context" / "resume.md").read_text(encoding="utf-8"),
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "scripts/context_brief.py",
                    "--goal-root",
                    str(goal_root),
                    "--projection",
                    "all",
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                json.loads(completed.stdout),
                [str(path) for path in paths],
            )


if __name__ == "__main__":
    unittest.main()
