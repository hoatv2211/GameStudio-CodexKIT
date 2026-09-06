from __future__ import annotations

import hashlib
import json
import unittest

from scripts.goal_progress_core import (
    GoalProgressError,
    calculate_eta,
    canonical_json,
    derive_stale,
    reduce_events,
    sanitize_summary,
    sha256_json,
    validate_accepted_event,
    validate_manifest,
)
from tests.goal_progress.support import (
    GOAL_ID,
    PACKET_ID,
    artifact_evidence,
    deep_copy,
    event_sequence_for_verified_packet,
    evidence_observed_event,
    goal_terminal_event,
    manifest_for_runtime,
    packet_definition,
    packet_event,
    plan_revised_event,
    runtime_authority,
    sha256_json_for_tests,
    started_event,
)


def manifest_with_estimates(*ranges: tuple[int, int], plan_version: int = 1) -> dict[str, object]:
    return manifest_for_runtime(
        plan_version=plan_version,
        packets=[
            packet_definition(
                f"p{index}",
                estimate_low=low,
                estimate_high=high,
            )
            for index, (low, high) in enumerate(ranges, start=1)
        ],
    )


class GoalProgressEtaTests(unittest.TestCase):
    def test_eta_uses_median_calibration_and_clips_factor(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates((60, 120), (120, 240)),
            packet_states={"p1": {"state": "verified"}, "p2": {"state": "queued"}},
            completed_timings=[
                {
                    "packet_id": "p1",
                    "actual_seconds": 450,
                    "estimated_midpoint_seconds": 90,
                }
            ],
            active_packet_count=0,
        )

        self.assertEqual(3.0, eta["calibration_factor"])
        self.assertEqual(360, eta["low_seconds"])
        self.assertEqual(720, eta["high_seconds"])
        self.assertEqual("low", eta["confidence"])

    def test_eta_uses_low_confidence_without_observations(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates((60, 120)),
            packet_states={"p1": {"state": "queued"}},
            completed_timings=[],
            active_packet_count=0,
        )

        self.assertEqual("Ready", eta["status"])
        self.assertEqual(1.0, eta["calibration_factor"])
        self.assertEqual("low", eta["confidence"])

    def test_eta_uses_medium_confidence_for_two_to_four_observations(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates((60, 120), (60, 120), (60, 120)),
            packet_states={
                "p1": {"state": "verified"},
                "p2": {"state": "verified"},
                "p3": {"state": "queued"},
            },
            completed_timings=[
                {"packet_id": "p1", "actual_seconds": 90, "estimated_midpoint_seconds": 90},
                {"packet_id": "p2", "actual_seconds": 90, "estimated_midpoint_seconds": 90},
            ],
            active_packet_count=0,
        )

        self.assertEqual("medium", eta["confidence"])

    def test_eta_uses_high_confidence_for_five_stable_observations(self) -> None:
        manifest = manifest_with_estimates(*((60, 120),) * 6)
        packet_states = {
            **{f"p{index}": {"state": "verified"} for index in range(1, 6)},
            "p6": {"state": "queued"},
        }
        timings = [
            {"packet_id": f"p{index}", "actual_seconds": 90, "estimated_midpoint_seconds": 90}
            for index in range(1, 6)
        ]

        self.assertEqual(
            "high",
            calculate_eta(manifest, packet_states, timings, active_packet_count=0)["confidence"],
        )

    def test_eta_uses_medium_confidence_for_high_dispersion(self) -> None:
        manifest = manifest_with_estimates(*((60, 120),) * 6)
        packet_states = {
            **{f"p{index}": {"state": "verified"} for index in range(1, 6)},
            "p6": {"state": "queued"},
        }
        timings = [
            {"packet_id": f"p{index}", "actual_seconds": seconds, "estimated_midpoint_seconds": 100}
            for index, seconds in enumerate((10, 10, 100, 400, 400), start=1)
        ]

        self.assertEqual(
            "medium",
            calculate_eta(manifest, packet_states, timings, active_packet_count=0)["confidence"],
        )

    def test_eta_pauses_for_waiting_blocked_or_stale_work(self) -> None:
        manifest = manifest_with_estimates((60, 120))
        cases = {
            "waiting_input": {"state": "waiting_input"},
            "blocked": {"state": "blocked"},
            "stale": {"state": "running", "stale": True},
        }

        for reason, state in cases.items():
            with self.subTest(reason=reason):
                eta = calculate_eta(
                    manifest,
                    packet_states={"p1": state},
                    completed_timings=[],
                    active_packet_count=1,
                )
                self.assertEqual("Paused", eta["status"])
                self.assertEqual(reason, eta["reason"])
                self.assertEqual("ETA paused", eta["summary"])

    def test_eta_warns_and_does_not_raise_confidence_from_epoch_gap(self) -> None:
        manifest = manifest_with_estimates(*((60, 120),) * 6)
        packet_states = {
            **{f"p{index}": {"state": "verified"} for index in range(1, 6)},
            "p6": {"state": "queued"},
        }
        timings = [
            {
                "packet_id": f"p{index}",
                "actual_seconds": 90,
                "estimated_midpoint_seconds": 90,
                "writer_epoch_id": "epoch-1",
                "cross_epoch_gap": index == 5,
            }
            for index in range(1, 6)
        ]

        eta = calculate_eta(manifest, packet_states, timings, active_packet_count=0)

        self.assertEqual("medium", eta["confidence"])
        self.assertIn("writer-epoch-gap", eta["warnings"])

    def test_eta_resets_calibration_confidence_after_plan_revision(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates((60, 120), plan_version=2),
            packet_states={"p1": {"state": "queued"}},
            completed_timings=[
                {
                    "packet_id": "p1",
                    "actual_seconds": 90,
                    "estimated_midpoint_seconds": 90,
                    "plan_version": 1,
                }
            ] * 5,
            active_packet_count=0,
        )

        self.assertEqual("low", eta["confidence"])
        self.assertIn("plan-revision-calibration-reset", eta["warnings"])

    def test_eta_discards_unversioned_timings_after_plan_revision(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates(*((60, 120),) * 6, plan_version=2),
            packet_states={
                **{f"p{index}": {"state": "verified"} for index in range(1, 6)},
                "p6": {"state": "queued"},
            },
            completed_timings=[
                {
                    "packet_id": f"p{index}",
                    "actual_seconds": 90,
                    "estimated_midpoint_seconds": 90,
                }
                for index in range(1, 6)
            ],
            active_packet_count=0,
        )

        self.assertEqual("low", eta["confidence"])
        self.assertEqual(1.0, eta["calibration_factor"])
        self.assertIn("plan-revision-unversioned-timing-discarded", eta["warnings"])

    def test_eta_calculates_when_no_remaining_estimate_exists(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates((0, 0)),
            packet_states={"p1": {"state": "queued"}},
            completed_timings=[],
            active_packet_count=0,
        )

        self.assertEqual("Calculating", eta["status"])
        self.assertEqual("Calculating...", eta["summary"])

    def test_eta_with_mixed_estimated_and_unestimated_remaining_work_is_calculating(self) -> None:
        manifest = manifest_with_estimates((60, 120), (120, 240))
        del manifest["packets"][1]["estimate_seconds"]

        eta = calculate_eta(
            manifest,
            packet_states={"p1": {"state": "queued"}, "p2": {"state": "queued"}},
            completed_timings=[],
            active_packet_count=0,
        )

        self.assertEqual(
            {"status": "Calculating", "summary": "Calculating..."},
            eta,
        )

    def test_eta_blocks_unsupported_parallel_timing(self) -> None:
        eta = calculate_eta(
            manifest_with_estimates((60, 120), (60, 120)),
            packet_states={"p1": {"state": "running"}, "p2": {"state": "running"}},
            completed_timings=[],
            active_packet_count=2,
        )

        self.assertEqual("BLOCKED", eta["status"])
        self.assertEqual("unsupported_parallel_timing", eta["reason"])

    def test_derive_stale_uses_active_estimate_freshness_and_utc_z_timestamps(self) -> None:
        manifest = manifest_with_estimates((60, 120))
        events = [
            started_event(manifest=manifest, emitted_at="2026-09-04T02:00:00Z"),
            packet_event(
                "packet.started",
                sequence=2,
                state="running",
                packet_id="p1",
                emitted_at="2026-09-04T02:00:00Z",
                expected_prior_state="queued",
            ),
        ]

        self.assertEqual(
            (False, None),
            derive_stale(manifest, events, now_utc="2026-09-04T02:15:00Z"),
        )
        self.assertEqual(
            (True, "stale"),
            derive_stale(manifest, events, now_utc="2026-09-04T02:15:01Z"),
        )
        with self.assertRaisesRegex(GoalProgressError, "UTC Z"):
            derive_stale(manifest, events, now_utc="2026-09-04T02:15:01+00:00")


class GoalProgressCoreTests(unittest.TestCase):
    def test_canonical_json_is_deterministic_and_ascii(self) -> None:
        payload = {"z": "\u00e9", "a": [2, {"b": 1}]}

        self.assertEqual('{"a":[2,{"b":1}],"z":"\\u00e9"}', canonical_json(payload))

    def test_sha256_json_omits_requested_top_level_keys(self) -> None:
        payload = {"keep": 1, "omit": 2}
        expected = hashlib.sha256(
            json.dumps({"keep": 1}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()

        self.assertEqual(expected, sha256_json(payload, omit=frozenset({"omit"})))

    def test_sanitize_summary_collapses_whitespace_and_truncates(self) -> None:
        summary, warnings = sanitize_summary("  hello\tworld \n done  ", limit=10)

        self.assertEqual("hello worl", summary)
        self.assertEqual(["normalized-whitespace", "truncated"], warnings)

    def test_sanitize_summary_redacts_assignments_and_keeps_html_for_rendering(self) -> None:
        summary, warnings = sanitize_summary(
            "Authorization: Bearer secret\r\nTOKEN=abc\x00 <script>alert(1)</script>",
            limit=700,
        )

        self.assertEqual(
            "Authorization: [REDACTED] TOKEN=[REDACTED] <script>alert(1)</script>",
            summary,
        )
        self.assertEqual(
            ["normalized-whitespace", "redacted-secret"],
            warnings,
        )

    def test_sanitize_summary_redacts_common_credential_identifiers_and_separators(self) -> None:
        summary, warnings = sanitize_summary(
            "api_key=abcdefghijklmnop" "qrstuvwxyz123456 "
            "API-KEY: abcdefghijklmnop" "qrstuvwxyz123456 "
            "client_secret=abcdefghijklmnop" "qrstuvwxyz123456 "
            "Client.Secret: abcdefghijklmnop" "qrstuvwxyz123456 "
            "secret=abcdefghijklmnop" "qrstuvwxyz123456 "
            "PASSWD: abcdefghijklmnop" "qrstuvwxyz123456 "
            "access_token=abcdefghijklmnop" "qrstuvwxyz123456 "
            "AWS_SECRET_ACCESS_KEY=abcdefghijklmnop" "qrstuvwxyz123456",
            limit=500,
        )

        self.assertEqual(
            "api_key=[REDACTED] API-KEY: [REDACTED] "
            "client_secret=[REDACTED] Client.Secret: [REDACTED] "
            "secret=[REDACTED] PASSWD: [REDACTED] "
            "access_token=[REDACTED] AWS_SECRET_ACCESS_KEY=[REDACTED]",
            summary,
        )
        self.assertEqual(["redacted-secret"], warnings)

    def test_sanitize_summary_always_caps_stored_text_at_500_characters(self) -> None:
        summary, warnings = sanitize_summary("x" * 501, limit=700)

        self.assertEqual(500, len(summary))
        self.assertEqual(["truncated"], warnings)

    def test_validate_manifest_rejects_reversed_estimate_ranges(self) -> None:
        manifest = manifest_for_runtime()
        manifest["packets"][0]["estimate_seconds"] = {"low": 120, "high": 60}

        with self.assertRaisesRegex(
            GoalProgressError,
            "estimate_seconds.low.*estimate_seconds.high",
        ):
            validate_manifest(manifest)

    def test_validate_manifest_accepts_portable_optional_runtime_bindings(self) -> None:
        hermes = manifest_for_runtime()
        hermes["runtime_bindings"] = [
            {"kind": "hermes_session", "id": "hermes-session-demo"}
        ]
        absent = manifest_for_runtime()
        del absent["runtime_bindings"]
        empty = manifest_for_runtime()
        empty["runtime_bindings"] = []

        for label, manifest in (("hermes", hermes), ("absent", absent), ("empty", empty)):
            with self.subTest(label=label):
                validate_manifest(manifest)

    def test_optional_packet_estimate_yields_calculating_eta(self) -> None:
        for label, estimate in (("absent", "absent"), ("null", None)):
            manifest = manifest_for_runtime()
            if estimate == "absent":
                del manifest["packets"][0]["estimate_seconds"]
            else:
                manifest["packets"][0]["estimate_seconds"] = estimate

            with self.subTest(label=label):
                validate_manifest(manifest)
                eta = calculate_eta(
                    manifest,
                    packet_states={PACKET_ID: {"state": "queued"}},
                    completed_timings=[],
                    active_packet_count=0,
                )
                self.assertEqual(
                    {"status": "Calculating", "summary": "Calculating..."},
                    eta,
                )

    def test_runtime_authority_supports_hermes_and_unbound_goals(self) -> None:
        hermes_manifest = manifest_for_runtime()
        hermes_binding = {"kind": "hermes_session", "id": "hermes-session-demo"}
        hermes_manifest["runtime_bindings"] = [hermes_binding]
        hermes_started = started_event(manifest=hermes_manifest, sequence=1)
        hermes_running = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )
        hermes_running["authority"]["kind"] = "hermes_session"
        hermes_running["authority"]["id"] = "hermes-session-demo"
        hermes_running["authority"]["runtime_binding"] = hermes_binding
        hermes_running["record_hash"] = sha256_json_for_tests(
            hermes_running,
            omit=frozenset({"record_hash"}),
        )

        unbound_manifest = manifest_for_runtime()
        del unbound_manifest["runtime_bindings"]
        unbound_started = started_event(manifest=unbound_manifest, sequence=1)
        unbound_running = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )

        for label, events in (
            ("hermes", [hermes_started, hermes_running]),
            ("unbound", [unbound_started, unbound_running]),
        ):
            with self.subTest(label=label):
                state = reduce_events(events, now_utc="2026-09-04T02:02:00Z")
                self.assertEqual("running", state["packets"][0]["status"])

    def test_reduce_running_packet_without_estimate_uses_default_stale_window(self) -> None:
        manifest = manifest_for_runtime()
        del manifest["packets"][0]["estimate_seconds"]
        state = reduce_events(
            [
                started_event(manifest=manifest, sequence=1),
                packet_event(
                    "packet.started",
                    sequence=2,
                    state="running",
                    expected_prior_state="queued",
                ),
            ],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertFalse(state["stale"])
        self.assertEqual("Calculating", state["eta"]["status"])

    def test_validate_manifest_rejects_duplicate_packet_ids(self) -> None:
        manifest = manifest_for_runtime(
            packets=[
                packet_definition("packet-a", progress_weight=1),
                packet_definition("packet-a", progress_weight=2),
            ]
        )

        with self.assertRaisesRegex(GoalProgressError, "duplicate packet id"):
            validate_manifest(manifest)

    def test_validate_manifest_rejects_missing_dependency(self) -> None:
        manifest = manifest_for_runtime(
            packets=[
                packet_definition("packet-a", progress_weight=1, dependencies=["packet-missing"]),
            ]
        )

        with self.assertRaisesRegex(GoalProgressError, "missing dependency"):
            validate_manifest(manifest)

    def test_validate_manifest_rejects_dependency_cycle(self) -> None:
        manifest = manifest_for_runtime(
            packets=[
                packet_definition("packet-a", progress_weight=1, dependencies=["packet-b"]),
                packet_definition("packet-b", progress_weight=2, dependencies=["packet-a"]),
            ]
        )

        with self.assertRaisesRegex(GoalProgressError, "dependency cycle"):
            validate_manifest(manifest)

    def test_validate_manifest_rejects_unknown_keys_and_boolean_integers(self) -> None:
        unknown = manifest_for_runtime()
        unknown["unexpected"] = True
        with self.assertRaisesRegex(GoalProgressError, "manifest keys"):
            validate_manifest(unknown)

        boolean_weight = manifest_for_runtime()
        boolean_weight["packets"][0]["progress_weight"] = True
        with self.assertRaisesRegex(GoalProgressError, "progress_weight"):
            validate_manifest(boolean_weight)

    def test_validate_manifest_requires_final_verification_tokens(self) -> None:
        manifest = manifest_for_runtime()
        manifest["final_verification_required"] = []

        with self.assertRaisesRegex(GoalProgressError, "final_verification_required"):
            validate_manifest(manifest)

    def test_validate_accepted_event_rejects_illegal_queued_to_verified(self) -> None:
        event = packet_event(
            "packet.verified",
            sequence=2,
            state="verified",
            expected_prior_state="queued",
            payload_updates={"evidence_ids": ["evidence-observed-001"]},
        )

        with self.assertRaisesRegex(GoalProgressError, "expected_prior_state"):
            validate_accepted_event(event)

    def test_validate_accepted_event_rejects_wrong_expected_prior_state(self) -> None:
        event = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="blocked",
        )

        with self.assertRaisesRegex(GoalProgressError, "expected_prior_state"):
            validate_accepted_event(event)

    def test_validate_accepted_event_rejects_wrong_hash_and_incomplete_authority(self) -> None:
        wrong_hash = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )
        wrong_hash["record_hash"] = "f" * 64
        with self.assertRaisesRegex(GoalProgressError, "record_hash"):
            validate_accepted_event(wrong_hash)

        incomplete_authority = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )
        del incomplete_authority["authority"]["runtime_binding"]
        incomplete_authority["record_hash"] = sha256_json_for_tests(
            incomplete_authority,
            omit=frozenset({"record_hash"}),
        )
        with self.assertRaisesRegex(GoalProgressError, "authority keys"):
            validate_accepted_event(incomplete_authority)

    def test_reduce_events_rejects_wrong_plan_version(self) -> None:
        started = started_event(manifest=manifest_for_runtime(), sequence=1)
        running = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            plan_version=2,
            expected_prior_state="queued",
        )

        with self.assertRaisesRegex(GoalProgressError, "plan_version"):
            reduce_events([started, running], now_utc="2026-09-04T02:02:00Z")

    def test_reduce_events_rejects_conflicting_event_id(self) -> None:
        started = started_event(manifest=manifest_for_runtime(), sequence=1)
        running = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            event_id="event-conflict",
            expected_prior_state="queued",
        )
        conflicting = packet_event(
            "packet.waiting_input",
            sequence=3,
            state="waiting_input",
            event_id="event-conflict",
            expected_prior_state="running",
        )

        with self.assertRaisesRegex(GoalProgressError, "conflicting event_id"):
            reduce_events([started, running, conflicting], now_utc="2026-09-04T02:02:00Z")

    def test_reduce_events_rejects_plan_revision_with_wrong_previous_hash(self) -> None:
        manifest_v1 = manifest_for_runtime()
        started = started_event(manifest=manifest_v1, sequence=1)
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[packet_definition(PACKET_ID, progress_weight=5)],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash="f" * 64,
        )

        with self.assertRaisesRegex(GoalProgressError, "previous_manifest_hash"):
            reduce_events([started, revised], now_utc="2026-09-04T02:02:00Z")

    def test_reduce_events_rejects_plan_revision_with_wrong_new_hash(self) -> None:
        manifest_v1 = manifest_for_runtime()
        started = started_event(manifest=manifest_v1, sequence=1)
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[packet_definition(PACKET_ID, progress_weight=5)],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
            new_manifest_hash="f" * 64,
        )

        with self.assertRaisesRegex(GoalProgressError, "new_manifest_hash"):
            reduce_events([started, revised], now_utc="2026-09-04T02:02:00Z")

    def test_validate_accepted_revision_requires_both_manifest_hashes(self) -> None:
        manifest_v1 = manifest_for_runtime()
        manifest_v2 = manifest_for_runtime(plan_version=2)
        revised = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
        )
        del revised["payload"]["new_manifest_hash"]
        revised["record_hash"] = sha256_json_for_tests(
            revised,
            omit=frozenset({"record_hash"}),
        )

        with self.assertRaisesRegex(GoalProgressError, "new_manifest_hash"):
            validate_accepted_event(revised)

    def test_codex_app_server_plan_revision_remains_informational(self) -> None:
        manifest_v1 = manifest_for_runtime()
        started = started_event(manifest=manifest_v1, sequence=1)
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[packet_definition(PACKET_ID, progress_weight=5)],
        )
        observed_revision = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
        )
        observed_revision["source"] = "codex_app_server"
        observed_revision["record_hash"] = sha256_json_for_tests(
            observed_revision,
            omit=frozenset({"record_hash"}),
        )

        replayed = reduce_events(
            [started, observed_revision],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual(1, replayed["plan_version"])
        self.assertEqual(3, replayed["progress"]["active_planned_weight"])

    def test_codex_app_server_goal_started_cannot_initialize_authority(self) -> None:
        observed_start = started_event(sequence=1)
        observed_start["source"] = "codex_app_server"
        observed_start["record_hash"] = sha256_json_for_tests(
            observed_start,
            omit=frozenset({"record_hash"}),
        )

        with self.assertRaisesRegex(GoalProgressError, "authoritative goal.started"):
            reduce_events([observed_start], now_utc="2026-09-04T02:02:00Z")

    def test_state_changing_authority_identity_matches_runtime_binding(self) -> None:
        manifest_v1 = manifest_for_runtime()
        manifest_v2 = manifest_for_runtime(plan_version=2)
        events = [
            packet_event(
                "packet.started",
                sequence=2,
                state="running",
                expected_prior_state="queued",
            ),
            plan_revised_event(
                manifest_v2,
                sequence=2,
                previous_manifest_hash=sha256_json_for_tests(manifest_v1),
            ),
            goal_terminal_event("goal.completed", sequence=2),
            goal_terminal_event("goal.cancelled", sequence=2),
        ]
        for event in events:
            with self.subTest(event_type=event["event_type"]):
                event["authority"]["id"] = "forged-thread"
                event["record_hash"] = sha256_json_for_tests(
                    event,
                    omit=frozenset({"record_hash"}),
                )
                with self.assertRaisesRegex(GoalProgressError, "authority identity"):
                    validate_accepted_event(event)

    def test_reduce_events_rejects_second_goal_started(self) -> None:
        first = started_event(sequence=1)
        second = started_event(event_id="event-goal-started-again", sequence=2)

        with self.assertRaisesRegex(GoalProgressError, "goal.started"):
            reduce_events([first, second], now_utc="2026-09-04T02:02:00Z")

    def test_verified_weight_changes_only_after_packet_verified(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()

        before = reduce_events(
            [started, running, observed],
            now_utc="2026-09-04T02:02:00Z",
        )
        after = reduce_events(
            [started, running, observed, verified],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual(0, before["progress"]["verified_weight"])
        self.assertEqual(0.0, before["progress"]["percent"])
        self.assertEqual(3, after["progress"]["verified_weight"])
        self.assertEqual(100.0, after["progress"]["percent"])
        self.assertEqual(99, after["progress"]["display_percent"])

    def test_reduce_events_rejects_verified_event_without_matching_evidence_binding(self) -> None:
        started = started_event(manifest=manifest_for_runtime(), sequence=1)
        running = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
        )
        observed = evidence_observed_event(sequence=3, packet_id="other-packet")
        verified = packet_event(
            "packet.verified",
            sequence=4,
            state="verified",
            expected_prior_state="running",
            payload_updates={"evidence_ids": ["evidence-observed-001"]},
        )

        with self.assertRaisesRegex(GoalProgressError, "matching evidence"):
            reduce_events([started, running, observed, verified], now_utc="2026-09-04T02:02:00Z")

    def test_reduce_events_recalculates_revised_out_denominator(self) -> None:
        manifest_v1 = manifest_for_runtime(
            packets=[
                packet_definition("packet-a", progress_weight=2),
                packet_definition("packet-b", progress_weight=1),
            ]
        )
        started = started_event(manifest=manifest_v1, sequence=1)
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[packet_definition("packet-a", progress_weight=2)],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
        )

        replayed = reduce_events(
            [started, revised],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual(2, replayed["progress"]["active_planned_weight"])
        self.assertEqual(0.0, replayed["progress"]["percent"])

    def test_reduce_events_reopens_verified_work_as_a_new_plan_packet(self) -> None:
        manifest_v1 = manifest_for_runtime()
        started = started_event(manifest=manifest_v1, sequence=1)
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
        restart_same_plan = packet_event(
            "packet.started",
            sequence=5,
            state="running",
            expected_prior_state="queued",
        )

        with self.assertRaisesRegex(GoalProgressError, "new plan version"):
            reduce_events(
                [started, running, observed, verified, restart_same_plan],
                now_utc="2026-09-04T02:02:00Z",
            )

        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[
                packet_definition(PACKET_ID, progress_weight=3),
                packet_definition("packet-reopened", progress_weight=2),
            ],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=5,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
            expected_prior_state="running",
        )
        restart_new_plan = packet_event(
            "packet.started",
            sequence=6,
            state="running",
            packet_id="packet-reopened",
            plan_version=2,
            expected_prior_state="queued",
            event_id="event-packet-started-6",
        )

        replayed = reduce_events(
            [started, running, observed, verified, revised, restart_new_plan],
            now_utc="2026-09-04T02:02:00Z",
        )
        self.assertEqual(2, replayed["plan_version"])
        self.assertEqual("verified", replayed["packets"][0]["status"])
        self.assertEqual("running", replayed["packets"][1]["status"])
        self.assertEqual(3, replayed["progress"]["verified_weight"])
        self.assertEqual(5, replayed["progress"]["active_planned_weight"])

    def test_plan_revision_preserves_retained_verified_weight(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()
        manifest_v1 = started["payload"]["manifest"]
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[
                packet_definition(PACKET_ID, progress_weight=3),
                packet_definition("packet-new", progress_weight=2),
            ],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=5,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
            expected_prior_state="running",
        )

        replayed = reduce_events(
            [started, running, observed, verified, revised],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual("verified", replayed["packets"][0]["status"])
        self.assertEqual("queued", replayed["packets"][1]["status"])
        self.assertEqual(3, replayed["progress"]["verified_weight"])
        self.assertEqual(5, replayed["progress"]["active_planned_weight"])
        self.assertEqual(60.0, replayed["progress"]["percent"])

    def test_plan_revision_reopens_verified_packet_when_verification_contract_changes(self) -> None:
        mutations = {
            "workflow_id": lambda packet: packet.__setitem__("workflow_id", "alternate-workflow"),
            "owner": lambda packet: packet.__setitem__("owner", "alternate-owner"),
            "objective": lambda packet: packet.__setitem__("objective", "Verify the revised objective"),
            "dependencies": lambda packet: packet.__setitem__("dependencies", ["packet-dependency"]),
            "completion_criteria": lambda packet: packet.__setitem__("completion_criteria", ["Revised checks pass"]),
            "required_evidence": lambda packet: packet.__setitem__("required_evidence", ["revised-test-command"]),
            "owned_paths": lambda packet: packet.__setitem__("owned_paths", ["scripts/revised.py"]),
            "excluded_paths": lambda packet: packet.__setitem__("excluded_paths", ["Assets/Revised"]),
        }

        for field, mutate in mutations.items():
            with self.subTest(field=field):
                started, running, observed, verified = event_sequence_for_verified_packet()
                manifest_v1 = started["payload"]["manifest"]
                retained = packet_definition(PACKET_ID, progress_weight=3)
                mutate(retained)
                packets = [retained]
                if field == "dependencies":
                    packets.insert(0, packet_definition("packet-dependency", progress_weight=1))
                manifest_v2 = manifest_for_runtime(plan_version=2, packets=packets)
                revised = plan_revised_event(
                    manifest_v2,
                    sequence=5,
                    previous_manifest_hash=sha256_json_for_tests(manifest_v1),
                    expected_prior_state="running",
                )

                replayed = reduce_events(
                    [started, running, observed, verified, revised],
                    now_utc="2026-09-04T02:02:00Z",
                )
                retained_state = next(
                    packet for packet in replayed["packets"] if packet["id"] == PACKET_ID
                )
                self.assertEqual("queued", retained_state["status"])
                self.assertEqual(0, replayed["progress"]["verified_weight"])

    def test_plan_revision_rejects_weight_change_for_retained_verified_packet(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()
        manifest_v1 = started["payload"]["manifest"]
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[packet_definition(PACKET_ID, progress_weight=5)],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=5,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
            expected_prior_state="running",
        )

        with self.assertRaisesRegex(GoalProgressError, "verified.*progress_weight"):
            reduce_events(
                [started, running, observed, verified, revised],
                now_utc="2026-09-04T02:02:00Z",
            )

    def test_plan_revision_removal_drops_verified_weight_and_denominator(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()
        manifest_v1 = started["payload"]["manifest"]
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[packet_definition("packet-replacement", progress_weight=2)],
        )
        revised = plan_revised_event(
            manifest_v2,
            sequence=5,
            previous_manifest_hash=sha256_json_for_tests(manifest_v1),
            expected_prior_state="running",
        )

        replayed = reduce_events(
            [started, running, observed, verified, revised],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual(0, replayed["progress"]["verified_weight"])
        self.assertEqual(2, replayed["progress"]["active_planned_weight"])

    def test_reduce_events_requires_final_verification_before_goal_completed(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()
        completed = goal_terminal_event(
            "goal.completed",
            sequence=5,
            final_verification_evidence_ids=[],
        )

        with self.assertRaisesRegex(GoalProgressError, "final verification"):
            reduce_events(
                [started, running, observed, verified, completed],
                now_utc="2026-09-04T02:02:00Z",
            )

    def test_informational_evidence_cannot_satisfy_final_verification(self) -> None:
        for source in ("operator_note", "codex_app_server"):
            with self.subTest(source=source):
                started, running, observed, verified = event_sequence_for_verified_packet()
                informational = deep_copy(running)
                informational.update(
                    {
                        "event_id": f"event-{source}-informational",
                        "sequence": 5,
                        "source": source,
                        "event_type": "runtime.heartbeat",
                        "packet_id": None,
                        "payload": {},
                        "authority": None,
                        "summary": "Informational runtime observation only.",
                        "evidence": [artifact_evidence("repository-gates")],
                    }
                )
                informational["record_hash"] = sha256_json_for_tests(
                    informational, omit=frozenset({"record_hash"})
                )
                completed = goal_terminal_event(
                    "goal.completed",
                    sequence=6,
                    final_verification_evidence_ids=["repository-gates"],
                )

                with self.assertRaisesRegex(GoalProgressError, "final verification"):
                    reduce_events(
                        [started, running, observed, verified, informational, completed],
                        now_utc="2026-09-04T02:02:00Z",
                    )

    def test_informational_summary_does_not_replace_workflow_next_action(self) -> None:
        started = started_event(manifest=manifest_for_runtime(), sequence=1)
        running = packet_event(
            "packet.started",
            sequence=2,
            state="running",
            expected_prior_state="queued",
            summary="Run the workflow-owned verification command.",
        )
        informational = deep_copy(running)
        informational.update(
            {
                "event_id": "event-app-server-heartbeat",
                "sequence": 3,
                "source": "codex_app_server",
                "event_type": "runtime.heartbeat",
                "packet_id": None,
                "payload": {},
                "authority": None,
                "summary": "Runtime activity observed.",
                "evidence": [],
            }
        )
        informational["record_hash"] = sha256_json_for_tests(
            informational, omit=frozenset({"record_hash"})
        )

        state = reduce_events(
            [started, running, informational],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual("Run the workflow-owned verification command.", state["next_action"])

    def test_revision_history_contains_only_sanitized_plan_revision_metadata(self) -> None:
        manifest_v1 = manifest_for_runtime()
        started = started_event(manifest=manifest_v1, sequence=1)
        manifest_v2 = manifest_for_runtime(
            plan_version=2,
            packets=[
                packet_definition(PACKET_ID, progress_weight=3),
                packet_definition("packet-new", progress_weight=2),
            ],
        )
        previous_hash = sha256_json_for_tests(manifest_v1)
        new_hash = sha256_json_for_tests(manifest_v2)
        revised = plan_revised_event(
            manifest_v2,
            sequence=2,
            previous_manifest_hash=previous_hash,
        )
        revised["payload"]["revision_reason"] = (
            "Add packet after review; client_secret=abcdefghijklmnop"
            "qrstuvwxyz123456"
        )
        revised["payload"]["approval_ref"] = "reviewer:MAD"
        revised["record_hash"] = sha256_json_for_tests(
            revised, omit=frozenset({"record_hash"})
        )

        state = reduce_events([started, revised], now_utc="2026-09-04T02:02:00Z")

        self.assertEqual(
            [
                {
                    "event_id": revised["event_id"],
                    "sequence": 2,
                    "previous_plan_version": 1,
                    "plan_version": 2,
                    "revision_reason": "Add packet after review; client_secret=[REDACTED]",
                    "approval_ref": "reviewer:MAD",
                    "previous_manifest_hash": previous_hash,
                    "new_manifest_hash": new_hash,
                    "progress_recalculated": True,
                    "eta_recalculated": True,
                }
            ],
            state["revision_history"],
        )

    def test_goal_completed_requires_each_final_verification_token(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()
        completed = goal_terminal_event(
            "goal.completed",
            sequence=5,
            final_verification_evidence_ids=["evidence-final-001"],
            evidence=[artifact_evidence("evidence-final-001")],
        )

        with self.assertRaisesRegex(GoalProgressError, "repository-gates"):
            reduce_events(
                [started, running, observed, verified, completed],
                now_utc="2026-09-04T02:02:00Z",
            )

    def test_goal_completed_rejects_duplicate_ids_for_multiple_requirements(self) -> None:
        manifest = manifest_for_runtime(
            final_verification_required=["repository-gates", "security-gates"]
        )
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
        completed = goal_terminal_event(
            "goal.completed",
            sequence=5,
            final_verification_evidence_ids=["repository-gates", "repository-gates"],
            evidence=[artifact_evidence("repository-gates")],
        )

        with self.assertRaisesRegex(GoalProgressError, "duplicate final verification"):
            reduce_events(
                [started, running, observed, verified, completed],
                now_utc="2026-09-04T02:02:00Z",
            )

    def test_reduce_events_replays_after_derived_state_is_discarded(self) -> None:
        started, running, observed, verified = event_sequence_for_verified_packet()
        completed = goal_terminal_event(
            "goal.completed",
            sequence=5,
            final_verification_evidence_ids=["repository-gates"],
            evidence=[artifact_evidence("repository-gates")],
        )

        first = reduce_events(
            [started, running, observed, verified, completed],
            now_utc="2026-09-04T02:02:00Z",
        )
        first["packets"][0]["status"] = "blocked"
        replayed = reduce_events(
            [started, running, observed, verified, completed],
            now_utc="2026-09-04T02:02:00Z",
        )

        self.assertEqual(GOAL_ID, replayed["goal_id"])
        self.assertEqual("completed", replayed["goal_state"])
        self.assertEqual("verified", replayed["packets"][0]["status"])
        self.assertEqual(100, replayed["progress"]["display_percent"])
        self.assertEqual("Calculating", replayed["eta"]["status"])
        self.assertEqual("Goal completed after final verification.", replayed["next_action"])


if __name__ == "__main__":
    unittest.main()
