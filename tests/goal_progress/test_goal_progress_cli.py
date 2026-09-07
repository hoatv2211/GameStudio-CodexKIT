from __future__ import annotations

import gc
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from unittest import mock

from scripts.goal_progress import main
from scripts.goal_progress_core import GoalProgressError
from scripts import goal_progress, goal_progress_server
from scripts.goal_progress_server import (
    GoalProgressRuntime,
    detached_process_options,
    request_private_json,
    runtime_is_reusable,
)
from scripts.goal_progress_store import GoalLock, GoalPaths
from tests.goal_progress.support import (
    GOAL_ID,
    PACKET_ID,
    deep_copy,
    packet_event,
    run_cli,
    running_private_runtime,
    valid_manifest,
)


class GoalProgressCliTests(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> Path:
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def wait_for_socket_close(self, client: socket.socket, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        client.settimeout(0.1)
        while time.monotonic() < deadline:
            try:
                if client.recv(4096) == b"":
                    return True
            except socket.timeout:
                continue
            except (ConnectionAbortedError, ConnectionResetError, OSError):
                return True
        return False

    def wait_for_active_requests(
        self, runtime: object, expected: int, timeout: float = 1.0
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if getattr(runtime, "active_request_count") == expected:
                return True
            time.sleep(0.01)
        return getattr(runtime, "active_request_count") == expected

    def test_pid_probe_treats_windows_system_error_as_not_running(self) -> None:
        with mock.patch(
            "scripts.goal_progress_server.os.kill",
            side_effect=SystemError("Windows process probe failed"),
        ):
            self.assertFalse(goal_progress_server._pid_is_running(24681357))

    def test_runtime_uses_base_python_executable_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_executable = Path(tmpdir) / "python.exe"
            base_executable.write_bytes(b"test executable")
            with mock.patch(
                "scripts.goal_progress_server.os.name", "nt"
            ), mock.patch.object(
                sys, "_base_executable", str(base_executable), create=True
            ):
                self.assertEqual(
                    str(base_executable),
                    goal_progress_server._runtime_python_executable(),
                )

    def test_runtime_uses_active_python_executable_off_windows(self) -> None:
        with mock.patch("scripts.goal_progress_server.os.name", "posix"):
            self.assertEqual(
                sys.executable,
                goal_progress_server._runtime_python_executable(),
            )

    def initialize_with_runtime(
        self, base: Path
    ) -> tuple[Path, Path, object, Path, dict[str, object], object]:
        goal_root = base / "evidence" / "local" / "goals" / GOAL_ID
        goal_root.parent.mkdir(parents=True)
        goal_root.mkdir()
        manifest_path = self.write_json(base / "manifest.json", valid_manifest())
        runtime_context = running_private_runtime(goal_root)
        runtime, token_file, info, thread = runtime_context.__enter__()
        try:
            exit_code, payload, raw = run_cli(
                main,
                [
                    "init",
                    "--manifest",
                    str(manifest_path),
                    "--goal-root",
                    str(goal_root),
                    "--json",
                ],
            )
            self.assertEqual(0, exit_code, raw)
        except BaseException:
            runtime_context.__exit__(None, None, None)
            raise
        return goal_root, manifest_path, runtime, token_file, info, runtime_context

    def assert_unconfirmed_restart_preserves_pending_identity(
        self, process: mock.Mock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            stale_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            stale_info["pid"] = 987654321
            self.write_json(paths.writer_info, stale_info)
            original_info = paths.writer_info.read_bytes()
            original_token = token_file.read_bytes()
            candidate_path = self.write_json(
                base / "candidate.json",
                packet_event("packet.started", sequence=2, state="running"),
            )

            process.pid = 24681357
            process_identity = {
                "process_creation_time": "boot-demo:12345",
                "process_fingerprint": "",
            }
            real_ensure_runtime = goal_progress_server.ensure_runtime

            def start_process(command: list[str], **_kwargs: object) -> mock.Mock:
                process_identity["process_fingerprint"] = (
                    goal_progress_server._command_fingerprint(command)
                )
                return process

            def ensure_without_readiness_wait(
                goal_root_arg: Path, **kwargs: object
            ) -> dict[str, object]:
                return real_ensure_runtime(
                    goal_root_arg,
                    readiness_timeout_seconds=0.0,
                    **kwargs,
                )

            with mock.patch(
                "scripts.goal_progress_server.subprocess.Popen",
                side_effect=start_process,
            ), mock.patch(
                "scripts.goal_progress_server._read_process_identity",
                create=True,
                return_value=process_identity,
            ), mock.patch(
                "scripts.goal_progress.ensure_runtime",
                side_effect=ensure_without_readiness_wait,
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "emit",
                        "--goal-root",
                        str(goal_root),
                        "--candidate",
                        str(candidate_path),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertEqual(
                "failed runtime process exit could not be confirmed",
                payload["reason"],
            )
            self.assertNotIn("injected-process-secret", raw)
            replacement_token = token_file.read_bytes()
            self.assertNotEqual(original_token, replacement_token)
            self.assertNotEqual(original_info, paths.writer_info.read_bytes())
            pending_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            self.assertEqual("pending-start", pending_info["recovery_state"])
            self.assertEqual(str(goal_root.resolve()), pending_info["goal_root"])
            self.assertEqual(process.pid, pending_info["pid"])
            self.assertEqual(
                process_identity["process_creation_time"],
                pending_info["process_creation_time"],
            )
            self.assertEqual(
                process_identity["process_fingerprint"],
                pending_info["process_fingerprint"],
            )
            self.assertEqual(
                hashlib.sha256(replacement_token).hexdigest(),
                pending_info["submission_token_sha256"],
            )
            self.assertEqual([], list(paths.runtime.glob(".*.tmp")))

    def test_preflight_is_report_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goals = base / "evidence" / "local" / "goals"
            goals.mkdir(parents=True)
            goal_root = goals / GOAL_ID
            manifest_path = self.write_json(base / "manifest.json", valid_manifest())

            first = run_cli(
                main,
                [
                    "preflight",
                    "--manifest",
                    str(manifest_path),
                    "--goal-root",
                    str(goal_root),
                    "--json",
                ],
            )
            second = run_cli(
                main,
                [
                    "preflight",
                    "--manifest",
                    str(manifest_path),
                    "--goal-root",
                    str(goal_root),
                    "--json",
                ],
            )

            self.assertEqual(0, first[0])
            self.assertEqual(first[2], second[2])
            self.assertEqual("READY", first[1]["status"])
            self.assertEqual(GOAL_ID, first[1]["goal_id"])
            self.assertEqual(str(goal_root.resolve()), first[1]["goal_root"])
            self.assertEqual("not-started", first[1]["writer_status"])
            self.assertFalse(goal_root.exists())

    def test_preflight_runs_through_the_direct_script_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root = base / "evidence" / "local" / "goals" / GOAL_ID
            goal_root.parent.mkdir(parents=True)
            manifest_path = self.write_json(base / "manifest.json", valid_manifest())
            repository_root = Path(__file__).resolve().parents[2]

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(repository_root / "scripts" / "goal_progress.py"),
                    "preflight",
                    "--manifest",
                    str(manifest_path),
                    "--goal-root",
                    str(goal_root),
                    "--json",
                ],
                cwd=repository_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("READY", payload["status"])
            self.assertEqual(str(goal_root.resolve()), payload["goal_root"])
            self.assertFalse(goal_root.exists())

    def test_init_defaults_idle_timeout_and_never_returns_capability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root = base / "goal"
            goal_root.mkdir()
            manifest_path = self.write_json(base / "manifest.json", valid_manifest())
            with running_private_runtime(goal_root) as (_runtime, _token, _info, _thread):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "init",
                        "--manifest",
                        str(manifest_path),
                        "--goal-root",
                        str(goal_root),
                        "--json",
                    ],
                )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual(
                {
                    "goal_id": GOAL_ID,
                    "goal_root": str(goal_root.resolve()),
                    "idle_timeout_seconds": 1800,
                    "status": "READY",
                    "writer_status": "reused",
                },
                payload,
            )
            lowered = raw.lower()
            self.assertNotIn("test-submission-secret", raw)
            self.assertNotIn("capability", lowered)
            self.assertNotIn("token", lowered)
            self.assertTrue(GoalPaths.from_root(goal_root).progress.is_file())

            with running_private_runtime(goal_root) as (_runtime, _token, _info, _thread):
                status_code, status, status_raw = run_cli(
                    main,
                    ["status", "--goal-root", str(goal_root), "--json"],
                )
            self.assertEqual(0, status_code, status_raw)
            self.assertEqual(GOAL_ID, status["state"]["goal_id"])
            self.assertEqual("running", status["writer_status"])

    def test_init_rejects_non_positive_idle_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            manifest_path = self.write_json(base / "manifest.json", valid_manifest())
            for value in ("0", "-1"):
                with self.subTest(value=value):
                    goal_root = base / f"goal-{value}"
                    exit_code, payload, _raw = run_cli(
                        main,
                        [
                            "init",
                            "--manifest",
                            str(manifest_path),
                            "--goal-root",
                            str(goal_root),
                            "--idle-timeout-seconds",
                            value,
                            "--json",
                        ],
                    )
                    self.assertEqual(2, exit_code)
                    self.assertEqual("FAIL", payload["status"])
                    self.assertIn("positive integer", payload["reason"])
                    self.assertFalse(goal_root.exists())

    def test_init_sanitizes_blocked_runtime_readiness_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goals = base / "goals"
            goals.mkdir()
            goal_root = goals / GOAL_ID
            manifest_path = self.write_json(base / "manifest.json", valid_manifest())
            with mock.patch(
                "scripts.goal_progress.ensure_runtime",
                side_effect=GoalProgressError(
                    "Authorization: Bearer reusable-readiness-secret"
                ),
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "init",
                        "--manifest",
                        str(manifest_path),
                        "--goal-root",
                        str(goal_root),
                        "--json",
                    ],
                )
            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertNotIn("reusable-readiness-secret", raw)
            self.assertIn("[REDACTED]", raw)

    def test_emit_rejects_wrong_goal_plan_and_authority(self) -> None:
        mutations = {
            "goal": lambda event: event.__setitem__("goal_id", "wrong-goal"),
            "plan": lambda event: event.__setitem__("plan_version", 2),
            "authority": lambda event: event["authority"].__setitem__(
                "owner", "wrong-owner"
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                base = Path(tmpdir)
                goal_root, _manifest, _runtime, _token, _info, context = (
                    self.initialize_with_runtime(base)
                )
                try:
                    candidate = packet_event(
                        "packet.started", sequence=2, state="running"
                    )
                    mutate(candidate)
                    candidate_path = self.write_json(base / "candidate.json", candidate)
                    exit_code, payload, raw = run_cli(
                        main,
                        [
                            "emit",
                            "--goal-root",
                            str(goal_root),
                            "--candidate",
                            str(candidate_path),
                            "--json",
                        ],
                    )
                    self.assertEqual(1, exit_code, raw)
                    self.assertEqual("FAIL", payload["status"])
                    self.assertEqual(
                        1,
                        len(
                            GoalPaths.from_root(goal_root)
                            .progress.read_text(encoding="utf-8")
                            .splitlines()
                        ),
                    )
                finally:
                    context.__exit__(None, None, None)

    def test_list_returns_only_twenty_recent_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository_root = Path(tmpdir)
            goals = repository_root / "evidence" / "local" / "goals"
            goals.mkdir(parents=True)
            for index in range(25):
                root = goals / f"goal-{index:02d}"
                root.mkdir()
                manifest = valid_manifest()
                manifest["goal_id"] = root.name
                state = {
                    "goal_id": root.name,
                    "goal_state": "running",
                    "updated_at": f"2026-09-04T02:{index:02d}:00Z",
                }
                self.write_json(root / "goal.json", manifest)
                self.write_json(root / "state.json", state)

            exit_code, payload, raw = run_cli(
                main,
                [
                    "list",
                    "--repository-root",
                    str(repository_root),
                    "--json",
                ],
            )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual("READY", payload["status"])
            self.assertEqual(20, len(payload["goals"]))
            self.assertEqual("goal-24", payload["goals"][0]["goal_id"])
            self.assertEqual("goal-05", payload["goals"][-1]["goal_id"])

    def test_open_refuses_ambiguous_active_goal_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository_root = Path(tmpdir)
            goals = repository_root / "evidence" / "local" / "goals"
            goals.mkdir(parents=True)
            for goal_id in ("goal-a", "goal-b"):
                root = goals / goal_id
                root.mkdir()
                manifest = valid_manifest()
                manifest["goal_id"] = goal_id
                self.write_json(root / "goal.json", manifest)
                self.write_json(
                    root / "state.json",
                    {
                        "goal_id": goal_id,
                        "goal_state": "running",
                        "updated_at": "2026-09-04T02:00:00Z",
                    },
                )

            exit_code, payload, raw = run_cli(
                main,
                [
                    "open",
                    "--goal-root",
                    str(repository_root),
                    "--view",
                    "compact",
                    "--json",
                ],
            )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertIn("ambiguous", payload["reason"])
            self.assertEqual(2, len(payload["goals"]))

    def test_open_scans_beyond_display_limit_for_ambiguous_active_goals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository_root = Path(tmpdir)
            goals = repository_root / "evidence" / "local" / "goals"
            goals.mkdir(parents=True)
            for index in range(21):
                goal_id = f"goal-{index:02d}"
                root = goals / goal_id
                root.mkdir()
                manifest = valid_manifest()
                manifest["goal_id"] = goal_id
                self.write_json(root / "goal.json", manifest)
                self.write_json(
                    root / "state.json",
                    {
                        "goal_id": goal_id,
                        "goal_state": (
                            "running" if index in {0, 20} else "completed"
                        ),
                        "updated_at": f"2026-09-04T02:{index:02d}:00Z",
                    },
                )

            exit_code, payload, raw = run_cli(
                main,
                [
                    "open",
                    "--goal-root",
                    str(repository_root),
                    "--view",
                    "compact",
                    "--json",
                ],
            )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertIn("ambiguous", payload["reason"])
            self.assertEqual(20, len(payload["goals"]))

    def test_open_resolves_active_goal_by_runtime_binding_before_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository_root = Path(tmpdir)
            goals = repository_root / "evidence" / "local" / "goals"
            goals.mkdir(parents=True)
            roots: dict[str, Path] = {}
            for goal_id, binding_id in (
                ("goal-matching", "thread-current"),
                ("goal-other", "thread-other"),
            ):
                root = goals / goal_id
                root.mkdir()
                roots[goal_id] = root
                manifest = valid_manifest()
                manifest["goal_id"] = goal_id
                manifest["runtime_bindings"] = [
                    {"kind": "codex_thread", "id": binding_id}
                ]
                self.write_json(root / "goal.json", manifest)
                self.write_json(
                    root / "state.json",
                    {
                        "goal_id": goal_id,
                        "goal_state": "running",
                        "updated_at": "2026-09-04T02:00:00Z",
                    },
                )

            runtime = {
                "goal_root": str(roots["goal-matching"].resolve()),
                "public_port": 43123,
                "writer_status": "started",
            }
            with mock.patch(
                "scripts.goal_progress.runtime_is_reusable", return_value=False
            ), mock.patch(
                "scripts.goal_progress.ensure_runtime", return_value=runtime
            ) as ensure, mock.patch(
                "scripts.goal_progress._private_request",
                return_value={"url": "http://127.0.0.1:43123/open?token=one-time"},
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "open",
                        "--goal-root",
                        str(repository_root),
                        "--runtime-binding-kind",
                        "codex_thread",
                        "--runtime-binding-id",
                        "thread-current",
                        "--approve-service-control",
                        "--view",
                        "compact",
                        "--json",
                    ],
                )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual(str(roots["goal-matching"].resolve()), payload["goal_root"])
            ensure.assert_called_once()
            self.assertEqual("started", payload["server"]["action"])
            self.assertEqual("READY", payload["server"]["status"])
            self.assertEqual("READY", payload["panel"]["status"])
            self.assertEqual("host_panel_required", payload["panel"]["action"])
            self.assertEqual("READY", payload["browser"]["status"])
            self.assertFalse(payload["browser"]["automatic_opened"])
            self.assertEqual("http://127.0.0.1:43123/open?token=one-time", payload["url"])

    def test_open_requires_service_control_approval_before_starting_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            self.write_json(goal_root / "goal.json", valid_manifest())
            self.write_json(
                goal_root / "state.json",
                {
                    "goal_id": GOAL_ID,
                    "goal_state": "running",
                    "updated_at": "2026-09-04T02:00:00Z",
                },
            )

            with mock.patch(
                "scripts.goal_progress.runtime_is_reusable", return_value=False
            ), mock.patch("scripts.goal_progress.ensure_runtime") as ensure:
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "open",
                        "--goal-root",
                        str(goal_root),
                        "--view",
                        "full",
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertIn("server", payload)
            self.assertEqual("BLOCKED", payload["server"]["status"])
            self.assertEqual("service_control_approval_required", payload["server"]["reason"])
            self.assertEqual("BLOCKED", payload["panel"]["status"])
            self.assertEqual("BLOCKED", payload["browser"]["status"])
            self.assertTrue(payload["portable_state_available"])
            ensure.assert_not_called()

    def test_session_scan_bounds_list_health_probes_and_open_uses_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository_root = Path(tmpdir)
            goals = repository_root / "evidence" / "local" / "goals"
            goals.mkdir(parents=True)
            for index in range(25):
                goal_id = f"goal-{index:02d}"
                root = goals / goal_id
                root.mkdir()
                manifest = valid_manifest()
                manifest["goal_id"] = goal_id
                self.write_json(root / "goal.json", manifest)
                self.write_json(
                    root / "state.json",
                    {
                        "goal_id": goal_id,
                        "goal_state": (
                            "running" if index in {0, 24} else "completed"
                        ),
                        "updated_at": f"2026-09-04T02:{index:02d}:00Z",
                    },
                )

            with mock.patch(
                "scripts.goal_progress.runtime_is_reusable",
                return_value=False,
            ) as health, mock.patch.object(
                goal_progress.time,
                "monotonic",
                side_effect=(100.0, 100.0, 100.2, 100.4, 100.6),
            ):
                list_code, listed, list_raw = run_cli(
                    main,
                    [
                        "list",
                        "--repository-root",
                        str(repository_root),
                        "--json",
                    ],
                )
                self.assertEqual(0, list_code, list_raw)
                self.assertEqual(20, len(listed["goals"]))
                self.assertEqual(3, health.call_count)
                for call in health.call_args_list:
                    timeout = call.kwargs["timeout_seconds"]
                    self.assertGreater(timeout, 0)
                    self.assertLessEqual(
                        timeout, goal_progress.SESSION_HEALTH_REQUEST_SECONDS
                    )

                health.reset_mock()
                open_code, opened, open_raw = run_cli(
                    main,
                    [
                        "open",
                        "--goal-root",
                        str(repository_root),
                        "--view",
                        "compact",
                        "--json",
                    ],
                )
                self.assertEqual(2, open_code, open_raw)
                self.assertIn("ambiguous", opened["reason"])
                self.assertEqual(0, health.call_count)

    def test_health_is_private_and_runtime_reuse_matches_full_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            with running_private_runtime(goal_root) as (
                _runtime,
                token_file,
                info,
                _thread,
            ):
                url = f"http://127.0.0.1:{info['private_port']}/health"
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(url, timeout=1.0)
                self.assertEqual(401, denied.exception.code)

                health = request_private_json(
                    info,
                    token_file.read_text(encoding="utf-8"),
                    "GET",
                    "/health",
                )
                self.assertEqual(
                    {"goal_root", "pid", "writer_epoch_id", "instance_nonce"},
                    set(health),
                )
                self.assertTrue(runtime_is_reusable(goal_root, token_file))

                writer_info = GoalPaths.from_root(goal_root).writer_info
                original = deep_copy(info)
                mismatches = {
                    "pid": int(info["pid"]) + 1,
                    "goal_root": str(goal_root.parent.resolve()),
                    "private_port": 1,
                    "writer_epoch_id": "wrong-epoch",
                    "instance_nonce": "wrong-nonce",
                }
                for key, value in mismatches.items():
                    with self.subTest(key=key):
                        changed = deep_copy(original)
                        changed[key] = value
                        self.write_json(writer_info, changed)
                        self.assertFalse(runtime_is_reusable(goal_root, token_file))
                self.write_json(writer_info, original)

    def test_private_events_reject_unknown_fields_and_oversized_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            with running_private_runtime(goal_root) as (
                _runtime,
                token_file,
                info,
                _thread,
            ):
                capability = token_file.read_text(encoding="utf-8")
                invalid = packet_event(
                    "packet.started", sequence=1, state="running"
                )
                invalid["unexpected"] = True
                with self.assertRaises(urllib.error.HTTPError) as unknown:
                    request_private_json(info, capability, "POST", "/events", invalid)
                self.assertEqual(400, unknown.exception.code)

                request = urllib.request.Request(
                    f"http://127.0.0.1:{info['private_port']}/events",
                    data=b"x" * (256 * 1024 + 1),
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {capability}",
                        "Content-Type": "application/json",
                    },
                )
                with self.assertRaises(urllib.error.HTTPError) as oversized:
                    urllib.request.urlopen(request, timeout=1.0)
                self.assertEqual(413, oversized.exception.code)
                self.assertFalse(GoalPaths.from_root(goal_root).progress.exists())

    def test_header_stalls_are_deadlined_and_request_concurrency_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            clients: list[socket.socket] = []
            with running_private_runtime(goal_root) as (
                runtime,
                _token_file,
                info,
                thread,
            ):
                try:
                    for _index in range(
                        goal_progress_server.MAX_CONCURRENT_REQUESTS + 3
                    ):
                        try:
                            client = socket.create_connection(
                                ("127.0.0.1", int(info["private_port"])),
                                timeout=0.5,
                            )
                        except OSError:
                            continue
                        clients.append(client)
                        client.sendall(b"POST /events HTTP/1.1\r\n")

                    deadline = time.monotonic() + 1.0
                    while (
                        runtime.active_request_count == 0
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    self.assertGreater(runtime.active_request_count, 0)
                    self.assertLessEqual(
                        runtime.active_request_count,
                        goal_progress_server.MAX_CONCURRENT_REQUESTS,
                    )
                    self.assertTrue(
                        all(
                            self.wait_for_socket_close(
                                client,
                                goal_progress_server.REQUEST_READ_DEADLINE_SECONDS
                                + 1.5,
                            )
                            for client in clients
                        )
                    )
                    runtime.request_stop()
                    thread.join(timeout=2.0)
                    self.assertFalse(thread.is_alive())
                    self.assertTrue(self.wait_for_active_requests(runtime, 0))
                finally:
                    for client in clients:
                        client.close()

    def test_partial_event_body_is_closed_at_read_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            with running_private_runtime(goal_root) as (
                runtime,
                token_file,
                info,
                _thread,
            ):
                capability = token_file.read_text(encoding="utf-8")
                client = socket.create_connection(
                    ("127.0.0.1", int(info["private_port"])), timeout=0.5
                )
                try:
                    client.sendall(
                        b"POST /events HTTP/1.1\r\n"
                        + f"Authorization: Bearer {capability}\r\n".encode("ascii")
                        + b"Content-Type: application/json\r\n"
                        + b"Content-Length: 100\r\n\r\n{"
                    )
                    self.assertTrue(
                        self.wait_for_socket_close(
                            client,
                            goal_progress_server.REQUEST_READ_DEADLINE_SECONDS + 1.5,
                        )
                    )
                    self.assertTrue(self.wait_for_active_requests(runtime, 0))
                    self.assertFalse(GoalPaths.from_root(goal_root).progress.exists())
                finally:
                    client.close()

    def test_slow_event_body_cannot_extend_absolute_read_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            with running_private_runtime(goal_root) as (
                runtime,
                token_file,
                info,
                _thread,
            ):
                capability = token_file.read_text(encoding="utf-8")
                client = socket.create_connection(
                    ("127.0.0.1", int(info["private_port"])), timeout=0.5
                )
                try:
                    client.sendall(
                        b"POST /events HTTP/1.1\r\n"
                        + f"Authorization: Bearer {capability}\r\n".encode("ascii")
                        + b"Content-Type: application/json\r\n"
                        + b"Content-Length: 100\r\n\r\n"
                    )
                    closed = False
                    deadline = (
                        time.monotonic()
                        + goal_progress_server.REQUEST_READ_DEADLINE_SECONDS
                        + 1.5
                    )
                    while time.monotonic() < deadline:
                        try:
                            client.sendall(b"x")
                        except OSError:
                            closed = True
                            break
                        time.sleep(0.15)
                    if not closed:
                        closed = self.wait_for_socket_close(client, 0.5)
                    self.assertTrue(closed)
                    self.assertTrue(self.wait_for_active_requests(runtime, 0))
                    self.assertFalse(GoalPaths.from_root(goal_root).progress.exists())
                finally:
                    client.close()

    def test_runtime_idle_timeout_closes_listener_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            with running_private_runtime(
                goal_root, idle_timeout_seconds=1
            ) as (_runtime, _token_file, info, thread):
                thread.join(timeout=2.0)
                self.assertFalse(thread.is_alive())
                with self.assertRaises(urllib.error.URLError):
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{info['private_port']}/health",
                        timeout=0.2,
                    )
                with GoalLock(
                    goal_root / "runtime" / "writer.lock", timeout_seconds=0.1
                ):
                    pass

    def test_stop_runtime_is_authenticated_evidence_preserving_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, info, context = (
                self.initialize_with_runtime(base)
            )
            try:
                paths = GoalPaths.from_root(goal_root)
                progress_before = paths.progress.read_bytes()
                goal_before = paths.goal.read_bytes()
                state_before = paths.state.read_bytes()
                expected_state = json.loads(state_before)

                token_file.write_text("wrong-submission-secret", encoding="utf-8")
                denied_code, denied, denied_raw = run_cli(
                    main,
                    [
                        "stop-runtime",
                        "--goal-root",
                        str(goal_root),
                        "--json",
                    ],
                )
                self.assertEqual(2, denied_code, denied_raw)
                self.assertEqual("BLOCKED", denied["status"])
                self.assertTrue(paths.writer_info.exists())
                token_file.write_text("test-submission-secret", encoding="utf-8")
                paths.state.unlink()

                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "stop-runtime",
                        "--goal-root",
                        str(goal_root),
                        "--json",
                    ],
                )
                self.assertEqual(0, exit_code, raw)
                self.assertEqual("stopped", payload["writer_status"])
                self.assertNotIn("test-submission-secret", raw)
                self.assertEqual(progress_before, paths.progress.read_bytes())
                self.assertEqual(goal_before, paths.goal.read_bytes())
                rebuilt_state = json.loads(paths.state.read_text(encoding="utf-8"))
                self.assertEqual(
                    expected_state["latest_evidence"], rebuilt_state["latest_evidence"]
                )
                expected_state.pop("updated_at")
                rebuilt_state.pop("updated_at")
                self.assertEqual(expected_state, rebuilt_state)
                self.assertFalse(token_file.exists())
                self.assertFalse(paths.writer_info.exists())
                self.assertFalse(paths.server_info.exists())
                with self.assertRaises(urllib.error.URLError):
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{info['private_port']}/health",
                        timeout=0.2,
                    )
                with GoalLock(paths.runtime / "writer.lock", timeout_seconds=0.1):
                    pass

                second_code, second, second_raw = run_cli(
                    main,
                    [
                        "stop-runtime",
                        "--goal-root",
                        str(goal_root),
                        "--json",
                    ],
                )
                self.assertEqual(0, second_code, second_raw)
                self.assertEqual("already-stopped", second["writer_status"])
            finally:
                context.__exit__(None, None, None)

    def test_shutdown_acknowledgement_is_sent_after_new_events_are_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, info, context = (
                self.initialize_with_runtime(base)
            )
            capability = token_file.read_text(encoding="utf-8")
            acknowledgement_written = threading.Event()
            release_shutdown_handler = threading.Event()
            shutdown_result: list[dict[str, object]] = []
            shutdown_errors: list[BaseException] = []
            real_send = goal_progress_server._PrivateHandler._send

            def held_send(
                handler: object, status: int, value: object
            ) -> None:
                real_send(handler, status, value)
                if getattr(handler, "path", None) == "/shutdown" and status == 200:
                    acknowledgement_written.set()
                    if not release_shutdown_handler.wait(3.0):
                        raise AssertionError("shutdown handler was not released")

            def request_shutdown() -> None:
                try:
                    shutdown_result.append(
                        request_private_json(
                            info, capability, "POST", "/shutdown"
                        )
                    )
                except BaseException as exc:
                    shutdown_errors.append(exc)

            shutdown_thread = threading.Thread(target=request_shutdown)
            try:
                with mock.patch.object(
                    goal_progress_server._PrivateHandler,
                    "_send",
                    autospec=True,
                    side_effect=held_send,
                ):
                    shutdown_thread.start()
                    self.assertTrue(acknowledgement_written.wait(2.0))
                    deadline = time.monotonic() + 2.0
                    while (
                        not shutdown_result
                        and not shutdown_errors
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    self.assertFalse(shutdown_errors)
                    self.assertEqual("stopping", shutdown_result[0]["writer_status"])

                    accepted_after_ack = True
                    try:
                        request_private_json(
                            info,
                            capability,
                            "POST",
                            "/events",
                            packet_event(
                                "packet.started", sequence=2, state="running"
                            ),
                        )
                    except (OSError, urllib.error.URLError):
                        accepted_after_ack = False
                    self.assertFalse(accepted_after_ack)
                    self.assertEqual(
                        1,
                        len(
                            GoalPaths.from_root(goal_root)
                            .progress.read_text(encoding="utf-8")
                            .splitlines()
                        ),
                    )
            finally:
                release_shutdown_handler.set()
                shutdown_thread.join(timeout=5.0)
                context.__exit__(None, None, None)

    def test_dead_runtime_cleanup_replays_deleted_derived_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            paths.goal.unlink()
            paths.state.unlink()

            exit_code, payload, raw = run_cli(
                main,
                ["stop-runtime", "--goal-root", str(goal_root), "--json"],
            )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual("already-stopped", payload["writer_status"])
            self.assertTrue(paths.goal.is_file())
            self.assertTrue(paths.state.is_file())
            self.assertFalse(token_file.exists())
            self.assertFalse(paths.writer_info.exists())

    def test_dead_runtime_cleanup_is_blocked_when_replay_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            paths.state.unlink()

            with mock.patch(
                "scripts.goal_progress_server.replay_goal",
                side_effect=TimeoutError("injected writer lock timeout"),
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    ["stop-runtime", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertTrue(token_file.is_file())
            self.assertTrue(paths.writer_info.is_file())

    def test_stopped_runtime_cleanup_preserves_interleaved_successor_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            old_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            successor_info = deep_copy(old_info)
            successor_info.update(
                {
                    "private_port": int(old_info["private_port"]) + 1,
                    "writer_epoch_id": "successor-epoch",
                    "instance_nonce": "successor-nonce",
                    "shutdown_complete": False,
                }
            )
            successor_token = "successor-submission-secret"
            real_replay = goal_progress_server.replay_goal

            def replay_then_start_successor(
                *args: object, **kwargs: object
            ) -> dict[str, object]:
                state = real_replay(*args, **kwargs)
                self.write_json(paths.writer_info, successor_info)
                token_file.write_text(successor_token, encoding="utf-8")
                return state

            with mock.patch(
                "scripts.goal_progress_server.replay_goal",
                side_effect=replay_then_start_successor,
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    ["stop-runtime", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual("already-stopped", payload["writer_status"])
            self.assertEqual(
                successor_info,
                json.loads(paths.writer_info.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                successor_token, token_file.read_text(encoding="utf-8")
            )

    def test_stale_runtime_restart_replay_failure_preserves_recovery_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest_path, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            stale_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            stale_info["pid"] = 987654321
            self.write_json(paths.writer_info, stale_info)
            stale_token = token_file.read_text(encoding="utf-8")
            paths.goal.unlink()
            paths.state.unlink()
            candidate_path = self.write_json(
                base / "candidate.json",
                packet_event("packet.started", sequence=2, state="running"),
            )

            with mock.patch(
                "scripts.goal_progress_server.replay_goal",
                side_effect=GoalProgressError(
                    "Authorization: Bearer injected-replay-secret"
                ),
            ), mock.patch("scripts.goal_progress_server.subprocess.Popen") as popen:
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "emit",
                        "--goal-root",
                        str(goal_root),
                        "--candidate",
                        str(candidate_path),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertNotIn("injected-replay-secret", raw)
            self.assertFalse(popen.called)
            self.assertEqual(
                stale_info,
                json.loads(paths.writer_info.read_text(encoding="utf-8")),
            )
            self.assertEqual(stale_token, token_file.read_text(encoding="utf-8"))
            self.assertTrue(paths.progress.is_file())

    def test_stale_runtime_restart_token_failure_preserves_recovery_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, manifest_path, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            stale_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            stale_info["pid"] = 987654321
            self.write_json(paths.writer_info, stale_info)
            stale_token = token_file.read_text(encoding="utf-8")

            with mock.patch(
                "scripts.goal_progress_server._write_new_capability",
                side_effect=OSError(
                    "Authorization: Bearer injected-token-secret"
                ),
            ), mock.patch("scripts.goal_progress_server.subprocess.Popen") as popen:
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "init",
                        "--manifest",
                        str(manifest_path),
                        "--goal-root",
                        str(goal_root),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertNotIn("injected-token-secret", raw)
            self.assertFalse(popen.called)
            self.assertEqual(
                stale_info,
                json.loads(paths.writer_info.read_text(encoding="utf-8")),
            )
            self.assertEqual(stale_token, token_file.read_text(encoding="utf-8"))

    def test_runtime_identity_lock_oserror_is_sanitized_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, _token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            candidate_path = self.write_json(
                base / "candidate.json",
                packet_event("packet.started", sequence=2, state="running"),
            )

            with mock.patch(
                "scripts.goal_progress_server.GoalLock",
                side_effect=OSError(
                    "Authorization: Bearer injected-lock-secret"
                ),
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "emit",
                        "--goal-root",
                        str(goal_root),
                        "--candidate",
                        str(candidate_path),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertNotIn("injected-lock-secret", raw)
            self.assertEqual("runtime identity is busy", payload["reason"])

    def test_stale_restart_popen_failure_restores_original_recovery_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            stale_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            stale_info["pid"] = 987654321
            self.write_json(paths.writer_info, stale_info)
            original_info = paths.writer_info.read_bytes()
            original_token = token_file.read_bytes()
            candidate_path = self.write_json(
                base / "candidate.json",
                packet_event("packet.started", sequence=2, state="running"),
            )

            with mock.patch(
                "scripts.goal_progress_server.subprocess.Popen",
                side_effect=OSError(
                    "Authorization: Bearer injected-popen-secret"
                ),
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "emit",
                        "--goal-root",
                        str(goal_root),
                        "--candidate",
                        str(candidate_path),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertNotIn("injected-popen-secret", raw)
            self.assertEqual(original_info, paths.writer_info.read_bytes())
            self.assertEqual(original_token, token_file.read_bytes())
            self.assertEqual([], list(paths.runtime.glob(".*.tmp")))

    def test_launch_journal_failure_blocks_before_popen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            stale_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            stale_info["pid"] = 987654321
            self.write_json(paths.writer_info, stale_info)
            original_info = paths.writer_info.read_bytes()
            original_token = token_file.read_bytes()
            candidate_path = self.write_json(
                base / "candidate.json",
                packet_event("packet.started", sequence=2, state="running"),
            )

            with mock.patch(
                "scripts.goal_progress_server._write_launch_journal",
                create=True,
                side_effect=OSError("injected journal persistence failure"),
            ) as journal, mock.patch(
                "scripts.goal_progress_server.subprocess.Popen"
            ) as popen:
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "emit",
                        "--goal-root",
                        str(goal_root),
                        "--candidate",
                        str(candidate_path),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertEqual(
                "runtime launch journal could not be created", payload["reason"]
            )
            journal.assert_called_once()
            popen.assert_not_called()
            self.assertEqual(original_info, paths.writer_info.read_bytes())
            self.assertEqual(original_token, token_file.read_bytes())

    def test_pending_pid_identity_mismatch_is_blocked_without_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            paths = GoalPaths.from_root(goal_root)
            paths.runtime.mkdir()
            token_file = paths.runtime / "submission-token"
            token = b"pending-" b"identity-" b"secret"
            token_file.write_bytes(token)
            self.write_json(
                paths.writer_info,
                {
                    "recovery_state": "pending-start",
                    "goal_root": str(goal_root.resolve()),
                    "pid": 24681357,
                    "submission_token_sha256": hashlib.sha256(token).hexdigest(),
                    "process_creation_time": "boot-demo:12345",
                    "process_fingerprint": "a" * 64,
                },
            )

            with mock.patch(
                "scripts.goal_progress_server._read_process_identity",
                create=True,
                return_value={
                    "process_creation_time": "boot-demo:99999",
                    "process_fingerprint": "b" * 64,
                },
            ), mock.patch("scripts.goal_progress_server.os.kill") as signal_pid:
                exit_code, payload, raw = run_cli(
                    main,
                    ["stop-runtime", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertEqual(
                "pending runtime process identity could not be verified",
                payload["reason"],
            )
            signal_pid.assert_not_called()

    def test_first_process_identity_must_match_intended_popen_command_before_signal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            paths = GoalPaths.from_root(goal_root)
            paths.runtime.mkdir()
            token_file = paths.runtime / "submission-token"
            token_file.write_text("trusted-runtime-token", encoding="utf-8")
            self.write_json(
                paths.writer_info,
                {
                    "goal_root": str(goal_root.resolve()),
                    "pid": 987654321,
                    "private_port": 43100,
                    "public_port": 43101,
                    "writer_epoch_id": "trusted-epoch",
                    "instance_nonce": "trusted-nonce",
                    "idle_timeout_seconds": 900,
                },
            )
            original_token = token_file.read_bytes()
            original_writer_info = paths.writer_info.read_bytes()
            process = mock.Mock()
            process.pid = 24681357
            process.poll.return_value = None

            with mock.patch(
                "scripts.goal_progress_server.subprocess.Popen",
                return_value=process,
            ), mock.patch(
                "scripts.goal_progress_server._read_process_identity",
                return_value={
                    "process_creation_time": "boot-demo:12345",
                    "process_fingerprint": "f" * 64,
                },
            ), mock.patch(
                "scripts.goal_progress_server.runtime_is_reusable",
                return_value=False,
            ), mock.patch(
                "scripts.goal_progress_server._pid_is_running",
                return_value=False,
            ), mock.patch(
                "scripts.goal_progress_server._replay_before_runtime_cleanup"
            ):
                with self.assertRaisesRegex(
                    GoalProgressError,
                    "pending runtime process identity could not be verified",
                ):
                    goal_progress_server.ensure_runtime(
                        goal_root,
                        readiness_timeout_seconds=0.0,
                    )

            process.terminate.assert_not_called()
            process.kill.assert_not_called()
            self.assertEqual(original_token, token_file.read_bytes())
            self.assertEqual(original_writer_info, paths.writer_info.read_bytes())
            self.assertTrue(token_file.is_file())
            self.assertTrue(paths.writer_info.is_file())

    def test_confirmed_death_cleanup_is_retryable_from_cleanup_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            real_unlink = Path.unlink
            failed_once = False

            def fail_token_unlink_once(path: Path, *args: object, **kwargs: object) -> None:
                nonlocal failed_once
                if Path(path) == token_file and not failed_once:
                    failed_once = True
                    raise OSError("injected cleanup failure")
                real_unlink(path, *args, **kwargs)

            with mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_token_unlink_once):
                first_code, first, first_raw = run_cli(
                    main,
                    ["stop-runtime", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(2, first_code, first_raw)
            self.assertEqual("BLOCKED", first["status"])
            cleanup_ready_path = paths.runtime / "recovery-journal.json"
            cleanup_ready = json.loads(cleanup_ready_path.read_text(encoding="utf-8"))
            self.assertEqual("cleanup-ready", cleanup_ready["recovery_state"])
            self.assertTrue(token_file.is_file())
            self.assertTrue(paths.progress.is_file())

            second_code, second, second_raw = run_cli(
                main,
                ["stop-runtime", "--goal-root", str(goal_root), "--json"],
            )
            self.assertEqual(0, second_code, second_raw)
            self.assertEqual("already-stopped", second["writer_status"])
            self.assertFalse(token_file.exists())
            self.assertFalse(paths.writer_info.exists())
            self.assertTrue(paths.progress.is_file())

    def test_stale_restart_readiness_failure_restores_original_recovery_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            context.__exit__(None, None, None)
            paths = GoalPaths.from_root(goal_root)
            stale_info = json.loads(paths.writer_info.read_text(encoding="utf-8"))
            stale_info["pid"] = 987654321
            self.write_json(paths.writer_info, stale_info)
            original_info = paths.writer_info.read_bytes()
            original_token = token_file.read_bytes()
            candidate_path = self.write_json(
                base / "candidate.json",
                packet_event("packet.started", sequence=2, state="running"),
            )
            failed_process = mock.Mock()
            failed_process.poll.return_value = 7

            with mock.patch(
                "scripts.goal_progress_server.subprocess.Popen",
                return_value=failed_process,
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "emit",
                        "--goal-root",
                        str(goal_root),
                        "--candidate",
                        str(candidate_path),
                        "--json",
                    ],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertEqual(original_info, paths.writer_info.read_bytes())
            self.assertEqual(original_token, token_file.read_bytes())
            self.assertEqual([], list(paths.runtime.glob(".*.tmp")))

    def test_stale_restart_terminate_error_preserves_pending_recovery_identity(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.terminate.side_effect = OSError(
            "Authorization: Bearer injected-process-secret"
        )

        self.assert_unconfirmed_restart_preserves_pending_identity(process)

    def test_stale_restart_kill_error_preserves_pending_recovery_identity(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("goal-runtime", 1.0)
        process.kill.side_effect = OSError(
            "Authorization: Bearer injected-process-secret"
        )

        self.assert_unconfirmed_restart_preserves_pending_identity(process)

    def test_stale_restart_unconfirmed_wait_preserves_pending_recovery_identity(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [None, None]

        self.assert_unconfirmed_restart_preserves_pending_identity(process)

    def test_stop_runtime_retries_and_cleans_pending_start_recovery_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            paths = GoalPaths.from_root(goal_root)
            paths.runtime.mkdir(parents=True)
            token_file = paths.runtime / "submission-token"
            token = b"replacement-" b"submission-" b"secret"
            token_file.write_bytes(token)
            pending_pid = 24681357
            self.write_json(
                paths.writer_info,
                {
                    "recovery_state": "pending-start",
                    "goal_root": str(goal_root.resolve()),
                    "pid": pending_pid,
                    "submission_token_sha256": hashlib.sha256(token).hexdigest(),
                    "process_creation_time": "boot-demo:12345",
                    "process_fingerprint": "a" * 64,
                },
            )
            process_live = True

            def pid_is_running(pid: object) -> bool:
                self.assertEqual(pending_pid, pid)
                return process_live

            def terminate_pid(pid: int, signal_number: int) -> None:
                nonlocal process_live
                self.assertEqual(pending_pid, pid)
                self.assertGreater(signal_number, 0)
                process_live = False

            with mock.patch(
                "scripts.goal_progress_server._pid_is_running",
                side_effect=pid_is_running,
            ), mock.patch(
                "scripts.goal_progress_server._read_process_identity",
                create=True,
                side_effect=lambda _pid: (
                    {
                        "process_creation_time": "boot-demo:12345",
                        "process_fingerprint": "a" * 64,
                    }
                    if process_live
                    else None
                ),
            ), mock.patch(
                "scripts.goal_progress_server.os.kill",
                side_effect=terminate_pid,
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    ["stop-runtime", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual("already-stopped", payload["writer_status"])
            self.assertFalse(token_file.exists())
            self.assertFalse(paths.writer_info.exists())

    def test_pending_journal_recovers_when_process_dies_before_writer_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            paths = GoalPaths.from_root(goal_root)
            paths.runtime.mkdir(parents=True)
            token_file = paths.runtime / "submission-token"
            token = b"pending-" b"journal-" b"submission-" b"secret"
            token_file.write_bytes(token)
            pending_pid = 24681357
            self.write_json(
                paths.runtime / "recovery-journal.json",
                {
                    "recovery_state": "pending-start",
                    "goal_root": str(goal_root.resolve()),
                    "submission_token_sha256": hashlib.sha256(token).hexdigest(),
                    "command_fingerprint": "c" * 64,
                    "pid": pending_pid,
                    "process_creation_time": "boot-demo:12345",
                    "process_fingerprint": "a" * 64,
                },
            )

            with mock.patch(
                "scripts.goal_progress_server._read_process_identity",
                return_value=None,
            ):
                exit_code, payload, raw = run_cli(
                    main,
                    ["stop-runtime", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual("already-stopped", payload["writer_status"])
            self.assertFalse(token_file.exists())
            self.assertFalse((paths.runtime / "recovery-journal.json").exists())

    def test_status_blocks_pending_start_identity_without_claiming_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            paths = GoalPaths.from_root(goal_root)
            paths.runtime.mkdir(parents=True)
            token_file = paths.runtime / "submission-token"
            token = b"pending-" b"status-" b"submission-" b"secret"
            token_file.write_bytes(token)
            self.write_json(paths.state, {"goal_id": GOAL_ID})
            self.write_json(
                paths.writer_info,
                {
                    "recovery_state": "pending-start",
                    "goal_root": str(goal_root.resolve()),
                    "pid": 24681357,
                    "submission_token_sha256": hashlib.sha256(token).hexdigest(),
                    "process_creation_time": "boot-demo:12345",
                    "process_fingerprint": "a" * 64,
                },
            )

            with mock.patch(
                "scripts.goal_progress.runtime_is_reusable"
            ) as health:
                exit_code, payload, raw = run_cli(
                    main,
                    ["status", "--goal-root", str(goal_root), "--json"],
                )

            self.assertEqual(2, exit_code, raw)
            self.assertEqual("BLOCKED", payload["status"])
            self.assertEqual("unknown", payload["writer_status"])
            self.assertEqual(
                "runtime process exit could not be confirmed", payload["reason"]
            )
            self.assertNotIn("pending-status-submission-secret", raw)
            health.assert_not_called()

    def test_list_marks_pending_start_identity_unknown_without_health_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository_root = Path(tmpdir)
            goal_root = (
                repository_root / "evidence" / "local" / "goals" / GOAL_ID
            )
            goal_root.mkdir(parents=True)
            paths = GoalPaths.from_root(goal_root)
            paths.runtime.mkdir(parents=True)
            token_file = paths.runtime / "submission-token"
            token = b"pending-" b"list-" b"submission-" b"secret"
            token_file.write_bytes(token)
            self.write_json(paths.goal, valid_manifest())
            self.write_json(
                paths.state,
                {
                    "goal_id": GOAL_ID,
                    "goal_state": "running",
                    "updated_at": "2026-09-04T02:00:00Z",
                },
            )
            self.write_json(
                paths.writer_info,
                {
                    "recovery_state": "pending-start",
                    "goal_root": str(goal_root.resolve()),
                    "pid": 24681357,
                    "submission_token_sha256": hashlib.sha256(token).hexdigest(),
                    "process_creation_time": "boot-demo:12345",
                    "process_fingerprint": "a" * 64,
                },
            )

            with mock.patch(
                "scripts.goal_progress.runtime_is_reusable"
            ) as health:
                exit_code, payload, raw = run_cli(
                    main,
                    [
                        "list",
                        "--repository-root",
                        str(repository_root),
                        "--json",
                    ],
                )

            self.assertEqual(0, exit_code, raw)
            self.assertEqual("READY", payload["status"])
            self.assertEqual(1, len(payload["goals"]))
            row = payload["goals"][0]
            self.assertEqual("unknown", row["writer_status"])
            self.assertEqual(
                "runtime process exit could not be confirmed", row["writer_reason"]
            )
            self.assertNotIn("pending-list-submission-secret", raw)
            health.assert_not_called()

    def test_stop_runtime_waits_for_replay_completion_before_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            goal_root, _manifest, _runtime, _token_file, _info, context = (
                self.initialize_with_runtime(base)
            )
            paths = GoalPaths.from_root(goal_root)
            paths.state.unlink()
            replay_entered = threading.Event()
            allow_replay = threading.Event()
            stop_result: list[tuple[int, dict[str, object], str]] = []
            real_replay = goal_progress_server.replay_goal

            def blocked_replay(*args: object, **kwargs: object) -> dict[str, object]:
                replay_entered.set()
                if not allow_replay.wait(3.0):
                    raise AssertionError("test did not release shutdown replay")
                return real_replay(*args, **kwargs)

            def run_stop() -> None:
                stop_result.append(
                    run_cli(
                        main,
                        [
                            "stop-runtime",
                            "--goal-root",
                            str(goal_root),
                            "--json",
                        ],
                    )
                )

            stop_thread = threading.Thread(target=run_stop)
            try:
                with mock.patch(
                    "scripts.goal_progress_server.replay_goal",
                    side_effect=blocked_replay,
                ):
                    stop_thread.start()
                    self.assertTrue(replay_entered.wait(2.0))
                    stop_thread.join(timeout=0.2)
                    self.assertTrue(
                        stop_thread.is_alive(),
                        "stop-runtime returned before shutdown replay completed",
                    )
                    allow_replay.set()
                    stop_thread.join(timeout=5.0)
            finally:
                allow_replay.set()
                stop_thread.join(timeout=5.0)
                context.__exit__(None, None, None)

            self.assertFalse(stop_thread.is_alive())
            self.assertEqual(1, len(stop_result))
            self.assertEqual(0, stop_result[0][0], stop_result[0][2])
            self.assertTrue(paths.state.is_file())

    def test_detached_process_options_are_noninteractive(self) -> None:
        options = detached_process_options()
        self.assertIs(subprocess.DEVNULL, options["stdout"])
        self.assertIs(subprocess.DEVNULL, options["stderr"])
        self.assertFalse(options["shell"])
        if os.name == "nt":
            expected = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            self.assertEqual(expected, options["creationflags"])
            self.assertNotIn("start_new_session", options)
        else:
            self.assertTrue(options["start_new_session"])
            self.assertNotIn("creationflags", options)

    def test_listener_bind_failure_releases_the_goal_writer_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            with mock.patch(
                "scripts.goal_progress_server._BoundedThreadingHTTPServer",
                side_effect=OSError("injected bind failure"),
            ):
                with warnings.catch_warnings(record=True) as observed:
                    warnings.simplefilter("always")
                    with self.assertRaisesRegex(OSError, "bind failure"):
                        GoalProgressRuntime(goal_root, "test-submission-secret")
                    gc.collect()
                self.assertFalse(
                    [item for item in observed if item.category is ResourceWarning]
                )
            with GoalLock(
                goal_root / "runtime" / "writer.lock", timeout_seconds=0.1
            ):
                pass


if __name__ == "__main__":
    unittest.main()
