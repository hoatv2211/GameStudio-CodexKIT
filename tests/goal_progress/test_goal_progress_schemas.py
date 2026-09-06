from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from scripts.goal_progress_core import (
    GoalProgressError,
    reduce_events,
    validate_accepted_event,
)
from tests.goal_progress.support import (
    context_facts_payload,
    context_refreshed_event,
    deep_copy,
    evidence_observed_event,
    event_sequence_for_verified_packet,
    goal_terminal_event,
    manifest_for_runtime,
    packet_event,
    plan_revised_event,
    sha256_json_for_tests,
    started_event,
    valid_manifest,
    valid_projection,
    valid_state,
    started_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "evals" / "schema"
MANIFEST_SCHEMA = SCHEMA_DIR / "studio-goal-manifest.schema.json"
EVENT_SCHEMA = SCHEMA_DIR / "studio-goal-event.schema.json"
STATE_SCHEMA = SCHEMA_DIR / "studio-goal-state.schema.json"
PROJECTION_SCHEMA = SCHEMA_DIR / "studio-context-projection.schema.json"


def load_validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    registry = Registry()
    for candidate in (
        MANIFEST_SCHEMA,
        EVENT_SCHEMA,
        STATE_SCHEMA,
        PROJECTION_SCHEMA,
    ):
        candidate_schema = json.loads(candidate.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            candidate_schema["$id"],
            Resource.from_contents(candidate_schema),
        )
    return Draft202012Validator(schema, registry=registry)


class GoalProgressSchemaTests(unittest.TestCase):
    def assert_invalid(self, path: Path, payload: dict[str, object]) -> None:
        self.assertTrue(path.exists(), f"missing schema: {path}")
        with self.assertRaises(ValidationError):
            load_validator(path).validate(payload)

    def assert_valid(self, path: Path, payload: dict[str, object]) -> None:
        self.assertTrue(path.exists(), f"missing schema: {path}")
        load_validator(path).validate(payload)

    def test_manifest_schema_is_closed_and_rejects_invalid_mutations(self) -> None:
        self.assertTrue(MANIFEST_SCHEMA.exists(), f"missing schema: {MANIFEST_SCHEMA}")
        schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/studio-goal-manifest.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            [
                "schema_version",
                "goal_id",
                "title",
                "repository_root",
                "repository_snapshot",
                "created_at",
                "plan_version",
                "scope",
                "do_not_touch",
                "packets",
                "final_verification_required",
                "timing_policy",
            ],
            schema["required"],
        )

        self.assert_valid(MANIFEST_SCHEMA, valid_manifest())

        hermes = deep_copy(valid_manifest())
        hermes["runtime_bindings"] = [
            {"kind": "hermes_session", "id": "hermes-session-demo"}
        ]
        self.assert_valid(MANIFEST_SCHEMA, hermes)

        absent_bindings = deep_copy(valid_manifest())
        del absent_bindings["runtime_bindings"]
        self.assert_valid(MANIFEST_SCHEMA, absent_bindings)

        empty_bindings = deep_copy(valid_manifest())
        empty_bindings["runtime_bindings"] = []
        self.assert_valid(MANIFEST_SCHEMA, empty_bindings)

        absent_estimate = deep_copy(valid_manifest())
        del absent_estimate["packets"][0]["estimate_seconds"]
        self.assert_valid(MANIFEST_SCHEMA, absent_estimate)

        null_estimate = deep_copy(valid_manifest())
        null_estimate["packets"][0]["estimate_seconds"] = None
        self.assert_valid(MANIFEST_SCHEMA, null_estimate)

        invalid = deep_copy(valid_manifest())
        invalid["unexpected"] = True
        self.assert_invalid(MANIFEST_SCHEMA, invalid)

        invalid = deep_copy(valid_manifest())
        invalid["packets"][0]["progress_weight"] = 0
        self.assert_invalid(MANIFEST_SCHEMA, invalid)

        invalid = deep_copy(valid_manifest())
        invalid["timing_policy"]["max_active_timed_packets"] = 2
        self.assert_invalid(MANIFEST_SCHEMA, invalid)

    def test_event_schema_is_closed_and_rejects_invalid_event_cases(self) -> None:
        self.assertTrue(EVENT_SCHEMA.exists(), f"missing schema: {EVENT_SCHEMA}")
        schema = json.loads(EVENT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/studio-goal-event.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            ["kit_workflow", "codex_app_server", "operator_note"],
            schema["properties"]["source"]["enum"],
        )
        self.assertEqual(
            [
                "goal.started",
                "plan.revised",
                "packet.started",
                "packet.waiting_input",
                "packet.blocked",
                "packet.failed",
                "packet.retry_started",
                "packet.resumed",
                "evidence.observed",
                "packet.verified",
                "context.refreshed",
                "runtime.heartbeat",
                "goal.completed",
                "goal.cancelled",
            ],
            schema["properties"]["event_type"]["enum"],
        )

        self.assert_valid(EVENT_SCHEMA, started_candidate())
        accepted = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )
        self.assert_valid(EVENT_SCHEMA, accepted)

        invalid = deep_copy(started_candidate())
        invalid["source"] = "external"
        self.assert_invalid(EVENT_SCHEMA, invalid)

        invalid = deep_copy(started_candidate())
        invalid["event_type"] = "goal.paused"
        self.assert_invalid(EVENT_SCHEMA, invalid)

        invalid = deep_copy(started_candidate())
        invalid["sequence"] = 0
        self.assert_invalid(EVENT_SCHEMA, invalid)

        invalid = deep_copy(accepted)
        invalid["record_hash"] = "broken"
        self.assert_invalid(EVENT_SCHEMA, invalid)

        invalid = deep_copy(accepted)
        invalid["authority"] = None
        self.assert_invalid(EVENT_SCHEMA, invalid)

        revised = plan_revised_event(
            manifest_for_runtime(plan_version=2),
            sequence=2,
            previous_manifest_hash="a" * 64,
        )
        self.assert_valid(EVENT_SCHEMA, revised)
        revised_invalid = deep_copy(revised)
        revised_invalid["authority"] = None
        self.assert_invalid(EVENT_SCHEMA, revised_invalid)

        for event_type, packet_state, prior_state, payload_updates in (
            ("packet.started", "running", "queued", None),
            ("packet.waiting_input", "waiting_input", "running", None),
            ("packet.blocked", "blocked", "running", None),
            ("packet.failed", "failed", "running", None),
            ("packet.retry_started", "running", "failed", None),
            ("packet.resumed", "running", "waiting_input", None),
            (
                "packet.verified",
                "verified",
                "running",
                {"evidence_ids": ["evidence-observed-001"]},
            ),
        ):
            payload = packet_event(
                event_type,
                sequence=2,
                state=packet_state,
                expected_prior_state=prior_state,
                payload_updates=payload_updates,
            )
            with self.subTest(event_type=event_type):
                self.assert_valid(EVENT_SCHEMA, payload)
                invalid = deep_copy(payload)
                invalid["authority"] = None
                self.assert_invalid(EVENT_SCHEMA, invalid)

        for event_type in ("goal.completed", "goal.cancelled"):
            payload = goal_terminal_event(
                event_type,
                sequence=2,
                summary_text=f"{event_type} recorded.",
                final_verification_evidence_ids=(
                    ["repository-gates"] if event_type == "goal.completed" else None
                ),
            )
            self.assert_valid(EVENT_SCHEMA, payload)
            invalid = deep_copy(payload)
            invalid["authority"] = None
            self.assert_invalid(EVENT_SCHEMA, invalid)

        informational = deep_copy(started_candidate())
        self.assertIsNone(informational["authority"])
        self.assert_valid(EVENT_SCHEMA, informational)

    def test_event_schema_matches_runtime_for_portable_state_changing_events(self) -> None:
        codex_manifest = manifest_for_runtime()
        codex_event = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )

        hermes_manifest = manifest_for_runtime()
        hermes_binding = {"kind": "hermes_session", "id": "hermes-session-demo"}
        hermes_manifest["runtime_bindings"] = [hermes_binding]
        hermes_event = deep_copy(codex_event)
        hermes_event["authority"]["kind"] = "hermes_session"
        hermes_event["authority"]["id"] = "hermes-session-demo"
        hermes_event["authority"]["runtime_binding"] = hermes_binding
        hermes_event["record_hash"] = sha256_json_for_tests(
            hermes_event,
            omit=frozenset({"record_hash"}),
        )

        unbound_manifest = manifest_for_runtime()
        del unbound_manifest["runtime_bindings"]
        unbound_event = deep_copy(codex_event)

        for label, manifest, event in (
            ("codex", codex_manifest, codex_event),
            ("hermes", hermes_manifest, hermes_event),
            ("unbound", unbound_manifest, unbound_event),
        ):
            with self.subTest(label=label):
                validate_accepted_event(event)
                self.assert_valid(EVENT_SCHEMA, event)
                state = reduce_events(
                    [started_event(manifest=manifest), event],
                    now_utc="2026-09-04T02:02:00Z",
                )
                self.assertEqual("running", state["packets"][0]["status"])

        simplified = deep_copy(codex_event)
        simplified["authority"] = {"kind": "codex_thread", "id": "thread-demo"}
        simplified["record_hash"] = sha256_json_for_tests(
            simplified,
            omit=frozenset({"record_hash"}),
        )
        with self.assertRaisesRegex(GoalProgressError, "authority keys"):
            validate_accepted_event(simplified)
        self.assert_invalid(EVENT_SCHEMA, simplified)

    def test_event_schema_matches_runtime_payload_families(self) -> None:
        manifest_v2 = manifest_for_runtime(plan_version=2)
        revised = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash="a" * 64,
        )
        revised["payload"]["revision_reason"] = "Scope changed after review."
        revised["payload"]["approval_ref"] = "reviewer:MAD"
        revised["record_hash"] = sha256_json_for_tests(
            revised,
            omit=frozenset({"record_hash"}),
        )
        validate_accepted_event(revised)
        self.assert_valid(EVENT_SCHEMA, revised)

        missing_revision_hash = deep_copy(revised)
        del missing_revision_hash["payload"]["previous_manifest_hash"]
        missing_revision_hash["record_hash"] = sha256_json_for_tests(
            missing_revision_hash,
            omit=frozenset({"record_hash"}),
        )
        with self.assertRaisesRegex(GoalProgressError, "payload keys"):
            validate_accepted_event(missing_revision_hash)
        self.assert_invalid(EVENT_SCHEMA, missing_revision_hash)

        verified = packet_event(
            "packet.verified",
            sequence=4,
            state="verified",
            expected_prior_state="running",
            payload_updates={"evidence_ids": ["evidence-observed-001"]},
        )
        validate_accepted_event(verified)
        self.assert_valid(EVENT_SCHEMA, verified)

        missing_evidence_ids = deep_copy(verified)
        del missing_evidence_ids["payload"]["evidence_ids"]
        missing_evidence_ids["record_hash"] = sha256_json_for_tests(
            missing_evidence_ids,
            omit=frozenset({"record_hash"}),
        )
        with self.assertRaisesRegex(GoalProgressError, "payload keys"):
            validate_accepted_event(missing_evidence_ids)
        self.assert_invalid(EVENT_SCHEMA, missing_evidence_ids)

        observed = evidence_observed_event(sequence=3)
        validate_accepted_event(observed)
        self.assert_valid(EVENT_SCHEMA, observed)

        observed_without_evidence = deep_copy(observed)
        observed_without_evidence["evidence"] = []
        observed_without_evidence["record_hash"] = sha256_json_for_tests(
            observed_without_evidence,
            omit=frozenset({"record_hash"}),
        )
        with self.assertRaisesRegex(GoalProgressError, "must carry evidence"):
            validate_accepted_event(observed_without_evidence)
        self.assert_invalid(EVENT_SCHEMA, observed_without_evidence)

        completed = goal_terminal_event(
            "goal.completed",
            sequence=5,
            final_verification_evidence_ids=["repository-gates"],
        )
        validate_accepted_event(completed)
        self.assert_valid(EVENT_SCHEMA, completed)

        missing_final_ids = deep_copy(completed)
        del missing_final_ids["payload"]["final_verification_evidence_ids"]
        missing_final_ids["record_hash"] = sha256_json_for_tests(
            missing_final_ids,
            omit=frozenset({"record_hash"}),
        )
        with self.assertRaisesRegex(GoalProgressError, "payload keys"):
            validate_accepted_event(missing_final_ids)
        self.assert_invalid(EVENT_SCHEMA, missing_final_ids)

    def test_context_refreshed_schema_and_runtime_require_a_closed_bounded_snapshot(self) -> None:
        context_event = context_refreshed_event(sequence=2)
        try:
            validate_accepted_event(context_event)
        except GoalProgressError as exc:
            self.fail(f"canonical context.refreshed event was rejected: {exc}")
        self.assert_valid(EVENT_SCHEMA, context_event)

        for label, mutate in (
            ("extra field", lambda payload: payload.update(unexpected="value")),
            ("missing field", lambda payload: payload.pop("decisions")),
            (
                "unbounded item",
                lambda payload: payload["blockers"].__setitem__(0, "x" * 501),
            ),
        ):
            invalid = context_refreshed_event(sequence=2)
            mutate(invalid["payload"])
            invalid["record_hash"] = sha256_json_for_tests(
                invalid, omit=frozenset({"record_hash"})
            )
            with self.subTest(case=label):
                with self.assertRaises(GoalProgressError):
                    validate_accepted_event(invalid)
                self.assert_invalid(EVENT_SCHEMA, invalid)

        secret_bearing = context_refreshed_event(sequence=2)
        secret_bearing["payload"]["commands"] = [
            "python tool.py --api_key=abcdefghijklmnop" "qrstuvwxyz123456"
        ]
        secret_bearing["record_hash"] = sha256_json_for_tests(
            secret_bearing, omit=frozenset({"record_hash"})
        )
        with self.assertRaisesRegex(GoalProgressError, "sanitized"):
            validate_accepted_event(secret_bearing)

    def test_reduce_events_projects_context_snapshot_and_manifest_dependencies(self) -> None:
        manifest = valid_manifest()
        manifest["packets"][0]["dependencies"] = []
        context_event = context_refreshed_event(sequence=2)
        try:
            state = reduce_events(
                [started_event(manifest=manifest), context_event],
                now_utc="2026-09-04T02:02:00Z",
            )
        except GoalProgressError as exc:
            self.fail(f"canonical context snapshot could not be reduced: {exc}")

        self.assertIn("context_facts", state)
        self.assertEqual(
            {**context_facts_payload(), "dependencies": []},
            state["context_facts"],
        )
        self.assert_valid(STATE_SCHEMA, state)

    def test_state_schema_is_closed_and_rejects_invalid_progress_cases(self) -> None:
        self.assertTrue(STATE_SCHEMA.exists(), f"missing schema: {STATE_SCHEMA}")
        schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/studio-goal-state.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            ["planned", "running", "waiting_input", "blocked", "failed", "completed", "cancelled"],
            schema["properties"]["goal_state"]["enum"],
        )
        self.assertEqual(
            [
                "queued",
                "running",
                "waiting_input",
                "blocked",
                "failed",
                "verified",
                "skipped",
            ],
            schema["$defs"]["packet_state"]["properties"]["status"]["enum"],
        )
        self.assertEqual(
            ["Calculating", "Ready", "Paused", "BLOCKED"],
            [
                variant["properties"]["status"]["const"]
                for variant in schema["$defs"]["eta"]["oneOf"]
            ],
        )
        self.assertFalse(schema["$defs"]["progress"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["context_facts"]["additionalProperties"])
        self.assertEqual(
            [
                "event_id",
                "sequence",
                "previous_plan_version",
                "plan_version",
                "revision_reason",
                "approval_ref",
                "previous_manifest_hash",
                "new_manifest_hash",
                "progress_recalculated",
                "eta_recalculated",
            ],
            schema["$defs"]["revision_history_item"]["required"],
        )
        self.assertEqual(
            [
                "verified_weight",
                "active_planned_weight",
                "percent",
                "display_percent",
            ],
            schema["$defs"]["progress"]["required"],
        )

        calculating = deep_copy(valid_state())
        calculating["eta"] = {"status": "Calculating", "summary": "Calculating..."}
        self.assert_valid(STATE_SCHEMA, calculating)

        reduced = reduce_events(
            list(event_sequence_for_verified_packet()),
            now_utc="2026-09-04T02:02:00Z",
        )
        self.assert_valid(STATE_SCHEMA, reduced)

        running = reduce_events(
            [
                started_event(),
                packet_event(
                    "packet.started",
                    sequence=2,
                    state="running",
                    expected_prior_state="queued",
                ),
            ],
            now_utc="2026-09-04T02:02:00Z",
        )
        self.assert_valid(STATE_SCHEMA, running)
        self.assertEqual("Ready", running["eta"]["status"])
        self.assertEqual(60, running["eta"]["low_seconds"])
        self.assertEqual(120, running["eta"]["high_seconds"])
        self.assertEqual("low", running["eta"]["confidence"])

        paused = deep_copy(calculating)
        paused["eta"] = {
            "status": "Paused",
            "reason": "waiting_input",
            "summary": "ETA paused",
        }
        self.assert_valid(STATE_SCHEMA, paused)

        blocked = deep_copy(calculating)
        blocked["eta"] = {
            "status": "BLOCKED",
            "reason": "unsupported_parallel_timing",
            "summary": "ETA blocked: unsupported parallel timing.",
        }
        self.assert_valid(STATE_SCHEMA, blocked)

        completed = deep_copy(calculating)
        completed["goal_state"] = "completed"
        completed["packets"][0]["status"] = "verified"
        completed["progress"]["display_percent"] = 100
        self.assert_valid(STATE_SCHEMA, completed)

        invalid = deep_copy(calculating)
        invalid["progress"]["percent"] = 101
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(calculating)
        invalid["context_facts"]["unexpected"] = "value"
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(calculating)
        invalid["revision_history"] = [
            {"event_id": "event-packet-started", "sequence": 2}
        ]
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(calculating)
        del invalid["progress"]["verified_weight"]
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(calculating)
        invalid["progress"]["unexpected"] = 1
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(calculating)
        invalid["progress"]["display_percent"] = 100
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(calculating)
        invalid["eta"]["status"] = "PASS"
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(running)
        del invalid["eta"]["confidence"]
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(running)
        invalid["eta"]["unexpected"] = "value"
        self.assert_invalid(STATE_SCHEMA, invalid)

        invalid = deep_copy(paused)
        invalid["eta"]["reason"] = "unsupported_parallel_timing"
        self.assert_invalid(STATE_SCHEMA, invalid)

    def test_projection_schema_is_closed_and_rejects_invalid_projection_cases(self) -> None:
        self.assertTrue(
            PROJECTION_SCHEMA.exists(), f"missing schema: {PROJECTION_SCHEMA}"
        )
        schema = json.loads(PROJECTION_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/studio-context-projection.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(["brief", "working", "resume"], schema["properties"]["projection"]["enum"])
        self.assertEqual(
            ["exact_tokenizer", "utf8_byte_fallback"],
            schema["properties"]["count_kind"]["enum"],
        )
        self.assertEqual(["READY", "BLOCKED"], schema["properties"]["status"]["enum"])

        ready = valid_projection()
        ready["target"] = 150
        ready["hard_cap"] = 300
        ready["count"] = len(ready["text"].encode("utf-8"))
        ready["evidence_label"] = "Unverified"
        self.assert_valid(PROJECTION_SCHEMA, ready)

        blocked = deep_copy(ready)
        blocked["status"] = "BLOCKED"
        blocked["text"] = ""
        blocked["count"] = 0
        blocked["evidence_label"] = "BLOCKED"
        self.assert_valid(PROJECTION_SCHEMA, blocked)

        for label, mutate in (
            ("standalone text", lambda value: value.update(text="not safe")),
            ("nonzero count", lambda value: value.update(count=1)),
            ("empty refs", lambda value: value.update(required_fact_refs=[])),
            ("wrong evidence label", lambda value: value.update(evidence_label="Unverified")),
        ):
            invalid_blocked = deep_copy(blocked)
            mutate(invalid_blocked)
            with self.subTest(blocked_contract=label):
                self.assert_invalid(PROJECTION_SCHEMA, invalid_blocked)

        ready_without_measurement = deep_copy(ready)
        ready_without_measurement["count"] = 0
        self.assert_invalid(PROJECTION_SCHEMA, ready_without_measurement)

        missing_text = deep_copy(blocked)
        del missing_text["text"]
        self.assert_invalid(PROJECTION_SCHEMA, missing_text)

        invalid = deep_copy(ready)
        invalid["projection"] = "unknown-projection"
        self.assert_invalid(PROJECTION_SCHEMA, invalid)

        invalid = deep_copy(ready)
        invalid["status"] = "PASS"
        self.assert_invalid(PROJECTION_SCHEMA, invalid)


if __name__ == "__main__":
    unittest.main()
