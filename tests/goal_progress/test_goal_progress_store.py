from __future__ import annotations

import json
import hashlib
import os
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import scripts.goal_progress_store as goal_progress_store
from scripts.goal_progress_core import GoalProgressError, canonical_json, sha256_json
from scripts.goal_progress_store import (
    GoalLock,
    GoalPaths,
    ProgressWriter,
    atomic_write_json,
    replay_goal,
)
from tests.goal_progress.support import (
    FIXED_UTC,
    GOAL_ID,
    PACKET_ID,
    FakeClock,
    command_evidence,
    deep_copy,
    evidence_observed_event,
    manifest_for_runtime,
    packet_definition,
    packet_event,
    plan_revised_event,
    sha256_json_for_tests,
    started_event,
)


class GoalProgressStoreTests(unittest.TestCase):
    def make_root(self, directory: str) -> Path:
        root = Path(directory) / "goal-demo"
        root.mkdir()
        return root

    def quarantine_files(self, paths: GoalPaths) -> list[Path]:
        return sorted(path for path in paths.quarantine.iterdir() if path.is_file())

    def test_goal_lock_refuses_a_second_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = self.make_root(tmpdir) / "runtime" / "writer.lock"
            first = GoalLock(lock_path)
            try:
                with self.assertRaises(TimeoutError):
                    GoalLock(lock_path, timeout_seconds=0.05)
            finally:
                first.close()

    def test_writer_stamps_sequential_records_and_flushes_derived_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            clock = FakeClock()
            with ProgressWriter(root, "submit-secret", clock) as writer:
                first = writer.accept(
                    started_event(sequence=1), presented_capability="submit-secret"
                )
                clock.advance(2.5)
                second = writer.accept(
                    packet_event(
                        "packet.started",
                        sequence=2,
                        state="running",
                        expected_prior_state="queued",
                    ),
                    presented_capability="submit-secret",
                )

            paths = GoalPaths.from_root(root)
            records = [json.loads(line) for line in paths.progress.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([1, 2], [record["sequence"] for record in records])
            self.assertEqual([0, 2500], [record["monotonic_offset_ms"] for record in records])
            self.assertEqual(first["writer_epoch_id"], second["writer_epoch_id"])
            self.assertEqual(FIXED_UTC, first["emitted_at"])
            self.assertEqual(
                second["record_hash"],
                sha256_json(second, omit=frozenset({"record_hash"})),
            )
            self.assertEqual(GOAL_ID, json.loads(paths.goal.read_text(encoding="utf-8"))["goal_id"])
            self.assertEqual("running", json.loads(paths.state.read_text(encoding="utf-8"))["goal_state"])

    def test_writer_accepts_running_packet_without_estimate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            manifest = manifest_for_runtime()
            del manifest["packets"][0]["estimate_seconds"]
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(
                    started_event(manifest=manifest, sequence=1),
                    presented_capability="submit-secret",
                )
                writer.accept(
                    packet_event(
                        "packet.started",
                        sequence=2,
                        state="running",
                        expected_prior_state="queued",
                    ),
                    presented_capability="submit-secret",
                )
                writer.accept(
                    evidence_observed_event(sequence=3),
                    presented_capability="submit-secret",
                )
                writer.accept(
                    packet_event(
                        "packet.verified",
                        sequence=4,
                        state="verified",
                        expected_prior_state="running",
                        evidence=[command_evidence("evidence-observed-001")],
                        payload_updates={"evidence_ids": ["evidence-observed-001"]},
                    ),
                    presented_capability="submit-secret",
                )

            state = json.loads(GoalPaths.from_root(root).state.read_text(encoding="utf-8"))
            self.assertEqual("running", state["goal_state"])
            self.assertEqual("Calculating", state["eta"]["status"])

    def test_writer_rejects_wrong_capability_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                with self.assertRaisesRegex(PermissionError, "capability"):
                    writer.accept(
                        started_event(sequence=1), presented_capability="wrong-secret"
                    )
            self.assertFalse(GoalPaths.from_root(root).progress.exists())

    def test_writer_rejects_stale_expected_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(started_event(sequence=1), "submit-secret")
                stale = packet_event(
                    "packet.started",
                    sequence=1,
                    state="running",
                    expected_prior_state="queued",
                )
                with self.assertRaisesRegex(GoalProgressError, "expected sequence"):
                    writer.accept(stale, "submit-secret")
            self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))

    def test_exact_duplicate_event_id_is_idempotent_with_one_physical_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            candidate = started_event(sequence=1)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                first = writer.accept(candidate, presented_capability="submit-secret")
                second = writer.accept(candidate, presented_capability="submit-secret")
            self.assertEqual(first, second)
            self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))

    def test_conflicting_duplicate_is_quarantined_without_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            candidate = started_event(sequence=1)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(candidate, "submit-secret")
                conflict = deep_copy(candidate)
                conflict["summary"] = "Conflicting duplicate content."
                with self.assertRaisesRegex(GoalProgressError, "conflicting event_id"):
                    writer.accept(conflict, "submit-secret")
            self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))
            quarantine = self.quarantine_files(paths)
            self.assertEqual(1, len(quarantine))
            self.assertEqual("conflicting-event-id", json.loads(quarantine[0].read_text(encoding="utf-8"))["reason"])

    def test_quarantine_records_bounded_candidate_metadata_without_raw_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            candidate = started_event(sequence=1)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(candidate, "submit-secret")
                conflict = deep_copy(candidate)
                secret = "candidate-" "secret-value"
                conflict["summary"] = f"api_key={secret} " + "x" * 5000
                with self.assertRaisesRegex(GoalProgressError, "conflicting event_id"):
                    writer.accept(conflict, "submit-secret")

            artifact = self.quarantine_files(paths)[0]
            metadata = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(
                {"reason", "line_number", "event_id", "content_sha256"},
                set(metadata),
            )
            self.assertEqual(candidate["event_id"], metadata["event_id"])
            self.assertRegex(metadata["content_sha256"], r"^[a-f0-9]{64}$")
            self.assertNotIn(secret, artifact.read_text(encoding="utf-8"))
            self.assertLess(artifact.stat().st_size, 1024)

    def test_replay_quarantine_hashes_raw_line_without_persisting_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            secret = "raw-line-secret-value"
            paths.progress.write_text(
                f'{{"api_key":"{secret}"\n', encoding="utf-8"
            )

            with self.assertRaisesRegex(GoalProgressError, "contains invalid JSON"):
                replay_goal(root, now_utc=FIXED_UTC)

            artifact = self.quarantine_files(paths)[0]
            metadata = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertIn("content_sha256", metadata)
            self.assertEqual(
                hashlib.sha256(
                    f'{{"api_key":"{secret}"'.encode("utf-8")
                ).hexdigest(),
                metadata["content_sha256"],
            )
            self.assertIsNone(metadata["event_id"])
            self.assertNotIn(secret, artifact.read_text(encoding="utf-8"))

    def test_writer_sanitizes_all_summary_fields_before_durable_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            evidence = evidence_observed_event(sequence=3)
            evidence["summary"] = "Authorization: Bearer event-summary-secret"
            evidence["evidence"][0]["summary"] = "api_key=evidence-" "summary-secret"

            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(started_event(sequence=1), "submit-secret")
                writer.accept(
                    packet_event(
                        "packet.started", sequence=2, state="running"
                    ),
                    "submit-secret",
                )
                writer.accept(evidence, "submit-secret")

            durable = paths.progress.read_text(encoding="utf-8")
            self.assertNotIn("event-summary-secret", durable)
            self.assertNotIn("evidence-summary-secret", durable)
            stored = json.loads(durable.splitlines()[-1])
            self.assertIn("[REDACTED]", stored["summary"])
            self.assertIn("[REDACTED]", stored["evidence"][0]["summary"])

    def test_replay_quarantines_a_truncated_final_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            paths.progress.write_text(canonical_json(started_event(sequence=1))[:-8], encoding="utf-8")
            with self.assertRaisesRegex(GoalProgressError, "truncated final line"):
                replay_goal(root, now_utc=FIXED_UTC)
            self.assertEqual("truncated-final-line", json.loads(self.quarantine_files(paths)[0].read_text(encoding="utf-8"))["reason"])

    def test_replay_quarantines_invalid_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            paths.progress.write_text('{"not":\n', encoding="utf-8")
            with self.assertRaisesRegex(GoalProgressError, "invalid JSON"):
                replay_goal(root, now_utc=FIXED_UTC)
            self.assertEqual("invalid-json", json.loads(self.quarantine_files(paths)[0].read_text(encoding="utf-8"))["reason"])

    def test_invalid_transition_is_quarantined_without_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(started_event(sequence=1), "submit-secret")
                invalid = packet_event(
                    "packet.verified",
                    sequence=2,
                    state="verified",
                    expected_prior_state="running",
                    evidence=[command_evidence("evidence-invalid")],
                    payload_updates={"evidence_ids": ["evidence-invalid"]},
                )
                with self.assertRaises(GoalProgressError):
                    writer.accept(invalid, "submit-secret")
            self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))
            self.assertEqual("invalid-event", json.loads(self.quarantine_files(paths)[0].read_text(encoding="utf-8"))["reason"])

    def test_replay_rejects_and_quarantines_wrong_record_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            event = started_event(sequence=1)
            event["summary"] = "Tampered after hashing."
            paths.progress.write_text(canonical_json(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(GoalProgressError, "record_hash"):
                replay_goal(root, now_utc=FIXED_UTC)
            self.assertEqual("invalid-event", json.loads(self.quarantine_files(paths)[0].read_text(encoding="utf-8"))["reason"])

    def test_append_is_durable_before_atomic_derived_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            atomic_write_json(paths.goal, {"old": "goal"})
            atomic_write_json(paths.state, {"old": "state"})
            real_replace = os.replace

            def fail_state_replace(source: str | bytes, destination: str | bytes) -> None:
                if Path(destination) == paths.state:
                    raise OSError("injected state replacement failure")
                real_replace(source, destination)

            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                with mock.patch("scripts.goal_progress_store.os.replace", side_effect=fail_state_replace):
                    with self.assertRaisesRegex(OSError, "injected state"):
                        writer.accept(started_event(sequence=1), "submit-secret")

                retried = writer.accept(started_event(sequence=1), "submit-secret")

            self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(1, retried["sequence"])
            self.assertEqual(GOAL_ID, json.loads(paths.state.read_text(encoding="utf-8"))["goal_id"])
            self.assertFalse(any(path.name.endswith(".tmp") for path in root.rglob("*")))

    def test_replay_rebuilds_deleted_goal_and_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                writer.accept(started_event(sequence=1), "submit-secret")
                writer.accept(
                    packet_event(
                        "packet.started",
                        sequence=2,
                        state="running",
                        expected_prior_state="queued",
                    ),
                    "submit-secret",
                )
            paths.goal.unlink()
            paths.state.unlink()

            rebuilt = replay_goal(root, now_utc=FIXED_UTC)

            self.assertTrue(paths.goal.is_file())
            self.assertTrue(paths.state.is_file())
            self.assertEqual(rebuilt, json.loads(paths.state.read_text(encoding="utf-8")))
            self.assertEqual("running", rebuilt["goal_state"])

    def test_public_replay_waits_for_writer_and_cannot_overwrite_newer_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            writer = ProgressWriter(root, "submit-secret", FakeClock())
            replay_read = threading.Event()
            allow_replay_write = threading.Event()
            replay_result: list[dict[str, object]] = []
            replay_errors: list[BaseException] = []
            replay_thread: threading.Thread | None = None
            real_read_progress = goal_progress_store._read_progress

            def pause_after_read(*args: object, **kwargs: object) -> list[dict[str, object]]:
                events = real_read_progress(*args, **kwargs)
                replay_read.set()
                if not allow_replay_write.wait(3.0):
                    raise AssertionError("replay test timed out before derived write")
                return events

            def run_replay() -> None:
                try:
                    replay_result.append(replay_goal(root, now_utc=FIXED_UTC))
                except BaseException as exc:
                    replay_errors.append(exc)

            try:
                writer.accept(started_event(sequence=1), "submit-secret")
                with mock.patch(
                    "scripts.goal_progress_store._read_progress",
                    side_effect=pause_after_read,
                ):
                    replay_thread = threading.Thread(target=run_replay)
                    replay_thread.start()
                    replay_entered_while_writer_locked = replay_read.wait(0.2)
                    writer.accept(
                        packet_event(
                            "packet.started",
                            sequence=2,
                            state="running",
                            expected_prior_state="queued",
                        ),
                        "submit-secret",
                    )
                    writer.close()
                    allow_replay_write.set()
                    replay_thread.join(timeout=4.0)
            finally:
                allow_replay_write.set()
                writer.close()
                if replay_thread is not None:
                    replay_thread.join(timeout=4.0)

            self.assertFalse(replay_entered_while_writer_locked)
            self.assertFalse(replay_errors)
            self.assertEqual("running", replay_result[0]["goal_state"])
            self.assertEqual(
                "running",
                json.loads(paths.state.read_text(encoding="utf-8"))["goal_state"],
            )
            self.assertEqual(2, len(paths.progress.read_text(encoding="utf-8").splitlines()))

    def test_post_fsync_reported_failure_reconciles_exact_retry_without_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            paths = GoalPaths.from_root(root)
            candidate = started_event(sequence=1)
            with ProgressWriter(root, "submit-secret", FakeClock()) as writer:
                real_append = writer._append

                def append_then_report_failure(accepted: dict[str, object]) -> None:
                    real_append(accepted)
                    raise OSError("injected post-fsync reported failure")

                with mock.patch.object(
                    writer, "_append", side_effect=append_then_report_failure
                ):
                    with self.assertRaisesRegex(OSError, "post-fsync"):
                        writer.accept(candidate, "submit-secret")

                retried = writer.accept(candidate, "submit-secret")
                self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))
                self.assertEqual(1, retried["sequence"])
                writer.accept(
                    packet_event(
                        "packet.started",
                        sequence=2,
                        state="running",
                        expected_prior_state="queued",
                    ),
                    "submit-secret",
                )

            self.assertEqual(2, len(paths.progress.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(
                "running",
                json.loads(paths.state.read_text(encoding="utf-8"))["goal_state"],
            )

    def test_restart_marks_epoch_gap_without_counting_downtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            manifest = manifest_for_runtime(
                packets=[
                    packet_definition("p1", estimate_low=80, estimate_high=120),
                    packet_definition("p2", dependencies=["p1"], estimate_low=80, estimate_high=120),
                ]
            )
            first_clock = FakeClock(monotonic=10.0)
            with ProgressWriter(root, "submit-secret", first_clock) as writer:
                writer.accept(started_event(manifest=manifest, sequence=1), "submit-secret")
                first_clock.advance(5)
                writer.accept(
                    packet_event(
                        "packet.started",
                        packet_id="p1",
                        sequence=2,
                        state="running",
                        expected_prior_state="queued",
                    ),
                    "submit-secret",
                )

            second_clock = FakeClock(monotonic=50_000.0)
            with ProgressWriter(root, "submit-secret", second_clock) as writer:
                writer.accept(
                    evidence_observed_event(sequence=3, packet_id="p1"),
                    "submit-secret",
                )
                second_clock.advance(4_000)
                verified = packet_event(
                    "packet.verified",
                    packet_id="p1",
                    sequence=4,
                    state="verified",
                    expected_prior_state="running",
                    evidence=[command_evidence("evidence-observed-001")],
                    payload_updates={"evidence_ids": ["evidence-observed-001"]},
                )
                state = writer.accept(verified, "submit-secret")

            derived = json.loads(GoalPaths.from_root(root).state.read_text(encoding="utf-8"))
            self.assertEqual("packet.verified", state["event_type"])
            self.assertEqual(1.0, derived["eta"]["calibration_factor"])
            self.assertIn("writer-epoch-gap", derived["eta"]["warnings"])

    def test_completed_timings_carry_active_plan_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self.make_root(tmpdir)
            packets = [
                packet_definition("p1", estimate_low=100, estimate_high=100),
                packet_definition("p2", estimate_low=100, estimate_high=100),
                packet_definition("p3", dependencies=["p2"], estimate_low=100, estimate_high=100),
            ]
            manifest_v1 = manifest_for_runtime(packets=packets, plan_version=1)
            clock = FakeClock()
            with ProgressWriter(root, "submit-secret", clock) as writer:
                writer.accept(started_event(manifest=manifest_v1, sequence=1), "submit-secret")
                writer.accept(packet_event("packet.started", packet_id="p1", sequence=2, state="running"), "submit-secret")
                clock.advance(300)
                writer.accept(evidence_observed_event(sequence=3, packet_id="p1", evidence_id="ev-p1"), "submit-secret")
                writer.accept(
                    packet_event(
                        "packet.verified",
                        packet_id="p1",
                        sequence=4,
                        state="verified",
                        expected_prior_state="running",
                        evidence=[command_evidence("ev-p1")],
                        payload_updates={"evidence_ids": ["ev-p1"]},
                    ),
                    "submit-secret",
                )
                manifest_v2 = manifest_for_runtime(packets=packets, plan_version=2)
                writer.accept(
                    plan_revised_event(
                        manifest_v2,
                        sequence=5,
                        previous_manifest_hash=sha256_json_for_tests(manifest_v1),
                        expected_prior_state="running",
                    ),
                    "submit-secret",
                )
                writer.accept(
                    packet_event(
                        "packet.started",
                        packet_id="p2",
                        plan_version=2,
                        sequence=6,
                        state="running",
                    ),
                    "submit-secret",
                )
                clock.advance(50)
                observed = evidence_observed_event(
                    sequence=7,
                    packet_id="p2",
                    plan_version=2,
                    evidence_id="ev-p2",
                )
                writer.accept(observed, "submit-secret")
                writer.accept(
                    packet_event(
                        "packet.verified",
                        packet_id="p2",
                        plan_version=2,
                        sequence=8,
                        state="verified",
                        expected_prior_state="running",
                        evidence=[command_evidence("ev-p2")],
                        payload_updates={"evidence_ids": ["ev-p2"]},
                    ),
                    "submit-secret",
                )

            eta = json.loads(GoalPaths.from_root(root).state.read_text(encoding="utf-8"))["eta"]
            self.assertEqual(0.5, eta["calibration_factor"])
            self.assertIn("plan-revision-mismatched-timing-discarded", eta["warnings"])


class GoalPathSafetyTests(unittest.TestCase):
    def test_missing_and_traversal_roots_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with self.assertRaises(GoalProgressError):
                GoalPaths.from_root(base / "missing")
            (base / "goal").mkdir()
            with self.assertRaisesRegex(GoalProgressError, "traversal"):
                GoalPaths.from_root(base / "goal" / ".." / "goal")

    def test_symlink_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            target = base / "target"
            target.mkdir()
            link = base / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            with self.assertRaisesRegex(GoalProgressError, "symlink|reparse"):
                GoalPaths.from_root(link)

    def test_symlink_metadata_is_rejected_before_sensitive_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "goal"
            root.mkdir()
            real_lstat = os.lstat

            def mark_goal_as_symlink(value: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> os.stat_result:
                metadata = real_lstat(value)
                if Path(value) != root:
                    return metadata
                values = list(metadata)
                values[0] = stat.S_IFLNK | 0o777
                return os.stat_result(values)

            with mock.patch("scripts.goal_progress_store.os.lstat", side_effect=mark_goal_as_symlink):
                with self.assertRaisesRegex(GoalProgressError, "symlink"):
                    GoalPaths.from_root(root)

    @unittest.skipUnless(os.name == "nt", "Windows junction contract")
    def test_windows_junction_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            target = base / "target"
            target.mkdir()
            junction = base / "junction"
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(f"junction creation unavailable: {result.stderr}")
            try:
                with self.assertRaisesRegex(GoalProgressError, "reparse"):
                    GoalPaths.from_root(junction)
            finally:
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "Windows reparse escape contract")
    def test_windows_junction_escape_is_rejected_before_sensitive_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            root = base / "goal"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            junction = root / "quarantine"
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(f"junction creation unavailable: {result.stderr}")
            try:
                with self.assertRaisesRegex(GoalProgressError, "reparse"):
                    replay_goal(root, now_utc=FIXED_UTC)
                self.assertEqual([], list(outside.iterdir()))
            finally:
                os.rmdir(junction)

    def test_mount_point_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "goal"
            root.mkdir()
            real_ismount = os.path.ismount

            def mark_goal_as_mount(value: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> bool:
                return Path(value) == root or real_ismount(value)

            with mock.patch("scripts.goal_progress_store.os.path.ismount", side_effect=mark_goal_as_mount):
                with self.assertRaisesRegex(GoalProgressError, "mount point"):
                    GoalPaths.from_root(root)

    def test_atomic_write_rejects_reparse_target_before_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            outside = base / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            link = base / "linked.json"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"file symlink unavailable: {exc}")
            with self.assertRaisesRegex(GoalProgressError, "symlink|reparse"):
                atomic_write_json(link, {"escaped": True})
            self.assertEqual("{}", outside.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
