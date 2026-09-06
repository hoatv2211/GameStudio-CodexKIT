from __future__ import annotations

import http.cookiejar
import http.client
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest import mock

from scripts import goal_progress_server
from scripts.goal_progress import main
from scripts.goal_progress_server import discover_dashboard_assets, request_private_json
from scripts.goal_progress_store import GoalPaths
from tests.goal_progress.support import (
    packet_event,
    run_cli,
    running_private_runtime,
    started_candidate,
)


SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; font-src 'none'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
}


class RecordingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        self.locations: list[str] = []
        self.responses: list[object] = []

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        self.locations.append(str(newurl))
        self.responses.append(headers)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GoalProgressServerTests(unittest.TestCase):
    def assert_security_headers(self, headers: object) -> None:
        for name, expected in SECURITY_HEADERS.items():
            self.assertEqual(expected, headers.get(name), name)  # type: ignore[attr-defined]

    def test_public_revision_projection_excludes_ordinary_events_and_sanitizes_metadata(self) -> None:
        project_revision = getattr(goal_progress_server, "_public_revision", None)
        self.assertIsNotNone(project_revision)
        self.assertIsNone(
            project_revision({"event_id": "event-packet-started", "sequence": 2})
        )

        revision = project_revision(
            {
                "event_id": "event-plan-revised-5",
                "sequence": 5,
                "previous_plan_version": 1,
                "plan_version": 2,
                "revision_reason": (
                    "Approved scope update; api_key=abcdefghijklmnop"
                    "qrstuvwxyz123456"
                ),
                "approval_ref": "reviewer:MAD",
                "previous_manifest_hash": "a" * 64,
                "new_manifest_hash": "b" * 64,
                "progress_recalculated": True,
                "eta_recalculated": True,
                "private_revision": "PRIVATE_REVISION_MARKER",
            }
        )

        self.assertEqual(
            {
                "event_id": "event-plan-revised-5",
                "sequence": 5,
                "previous_plan_version": 1,
                "plan_version": 2,
                "revision_reason": "Approved scope update; api_key=[REDACTED]",
                "approval_ref": "reviewer:MAD",
                "previous_manifest_hash": "a" * 64,
                "new_manifest_hash": "b" * 64,
                "progress_recalculated": True,
                "eta_recalculated": True,
            },
            revision,
        )
        self.assertNotIn("PRIVATE_REVISION_MARKER", json.dumps(revision))

    @contextmanager
    def running_dashboard(
        self,
    ) -> Iterator[tuple[Path, dict[str, object], str]]:
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
                request_private_json(
                    info,
                    capability,
                    "POST",
                    "/events",
                    started_candidate(),
                )
                paths = GoalPaths.from_root(goal_root)
                for projection in ("brief", "working", "resume"):
                    (paths.context / f"{projection}.json").write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "goal_id": "goal-demo-001",
                                "projection": projection,
                                "status": "READY",
                                "count_kind": "utf8_byte_fallback",
                                "count": 24,
                                "target": 150,
                                "hard_cap": 300,
                                "text": f"<{projection}> & ready",
                                "required_fact_refs": [
                                    "goal-demo-001#packet-contract"
                                ],
                                "evidence_label": "Unverified",
                            }
                        ),
                        encoding="utf-8",
                    )
                paths.integration_status.write_text(
                    json.dumps(
                        {
                            "status": "BLOCKED",
                            "reason": "desktop_transport_unavailable",
                            "portable_progress_available": True,
                        }
                    ),
                    encoding="utf-8",
                )
                paths.logs.mkdir(exist_ok=True)
                yield goal_root, info, capability

    def mint_url(
        self, info: dict[str, object], capability: str, view: str = "full"
    ) -> str:
        response = request_private_json(
            info,
            capability,
            "POST",
            "/dashboard/open",
            {"view": view},
        )
        self.assertEqual("READY", response["status"])
        return str(response["url"])

    def authenticated_opener(
        self, info: dict[str, object], capability: str, view: str = "full"
    ) -> tuple[urllib.request.OpenerDirector, RecordingRedirectHandler, str]:
        jar = http.cookiejar.CookieJar()
        redirects = RecordingRedirectHandler()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), redirects
        )
        url = self.mint_url(info, capability, view)
        with opener.open(url, timeout=2.0) as response:
            self.assertEqual(f"/{view}", urllib.parse.urlparse(response.url).path)
            self.assert_security_headers(response.headers)
        return opener, redirects, url

    def test_bootstrap_is_single_use_sets_strict_cookie_and_mints_fresh_urls(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            first_url = self.mint_url(info, capability, "compact")
            second_url = self.mint_url(info, capability, "compact")
            self.assertNotEqual(first_url, second_url)

            jar = http.cookiejar.CookieJar()
            redirects = RecordingRedirectHandler()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar), redirects
            )
            with opener.open(first_url, timeout=2.0) as response:
                self.assertEqual("/compact", urllib.parse.urlparse(response.url).path)

            token_values = urllib.parse.parse_qs(
                urllib.parse.urlsplit(first_url).query
            )["token"]
            self.assertEqual(1, len(token_values))
            cookies = list(jar)
            self.assertEqual(1, len(cookies))
            self.assertNotEqual(token_values[0], cookies[0].value)

            self.assertEqual(
                ["/compact"],
                [urllib.parse.urlparse(location).path for location in redirects.locations],
            )
            self.assertNotIn("token", redirects.locations[0])
            bootstrap_headers = redirects.responses[0]
            self.assert_security_headers(bootstrap_headers)
            cookie = bootstrap_headers.get("Set-Cookie")
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.assertIn("Path=/", cookie)

            with self.assertRaises(urllib.error.HTTPError) as reused:
                opener.open(first_url, timeout=2.0)
            self.assertEqual(401, reused.exception.code)
            self.assert_security_headers(reused.exception.headers)

    def test_cli_open_mints_fresh_urls_without_persisting_bootstrap_tokens(self) -> None:
        with self.running_dashboard() as (goal_root, _info, _capability):
            first_code, first, first_raw = run_cli(
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
            second_code, second, second_raw = run_cli(
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

            self.assertEqual(0, first_code, first_raw)
            self.assertEqual(0, second_code, second_raw)
            self.assertNotEqual(first["url"], second["url"])
            server_info = (goal_root / "runtime" / "server-info.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("token", server_info)
            self.assertNotIn("/open?", server_info)

    def test_public_routes_require_cookie_and_every_response_has_security_headers(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            base = urllib.parse.urlunsplit(
                ("http", f"127.0.0.1:{info['public_port']}", "", "", "")
            )
            with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                urllib.request.urlopen(f"{base}/api/state", timeout=2.0)
            self.assertEqual(401, unauthorized.exception.code)
            self.assert_security_headers(unauthorized.exception.headers)

            opener, _redirects, _url = self.authenticated_opener(info, capability)
            for route in (
                "/full",
                "/compact",
                "/assets/styles.css",
                "/assets/app.js",
                "/api/state",
            ):
                with self.subTest(route=route), opener.open(
                    f"{base}{route}", timeout=2.0
                ) as response:
                    self.assertEqual(200, response.status)
                    self.assert_security_headers(response.headers)

            for method in ("POST", "PUT", "PATCH", "DELETE"):
                request = urllib.request.Request(
                    f"{base}/api/state", method=method, data=b""
                )
                with self.subTest(method=method), self.assertRaises(
                    urllib.error.HTTPError
                ) as rejected:
                    opener.open(request, timeout=2.0)
                self.assertEqual(405, rejected.exception.code)
                self.assertEqual("GET", rejected.exception.headers.get("Allow"))
                self.assert_security_headers(rejected.exception.headers)

    def test_dashboard_shell_is_semantic_local_and_accessible(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            html = opener.open(f"{base}/full", timeout=2.0).read().decode("utf-8")

            self.assertIn('data-view="full"', html)
            self.assertIn('role="status"', html)
            self.assertIn("<table", html)
            self.assertIn('id="timeline"', html)
            self.assertIn('id="eta-basis"', html)
            self.assertIn('role="tablist"', html)
            self.assertIn('aria-controls="context-content"', html)
            self.assertIn('tabindex="-1"', html)
            self.assertIn('id="integration-status"', html)
            self.assertIn('href="/assets/styles.css"', html)
            self.assertIn('src="/assets/app.js"', html)
            self.assertNotIn("<script>", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)

            script = opener.open(f"{base}/assets/app.js", timeout=2.0).read().decode(
                "utf-8"
            )
            self.assertIn('addEventListener("keydown"', script)
            self.assertIn('event.key === "ArrowRight"', script)
            self.assertIn('event.key === "ArrowLeft"', script)
            self.assertIn('revision.previous_plan_version', script)
            self.assertIn('revision.plan_version', script)
            self.assertIn('revision.revision_reason', script)
            self.assertIn('revision.approval_ref', script)
            self.assertIn('revision.previous_manifest_hash', script)
            self.assertIn('revision.new_manifest_hash', script)
            self.assertIn('Progress recalculated', script)
            self.assertIn('ETA recalculated', script)

    def test_state_api_returns_reduced_public_data_and_inert_hostile_strings(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            state = json.loads(paths.state.read_text(encoding="utf-8"))
            state["private_state"] = "PRIVATE_STATE_MARKER"
            state["revision_history"] = [
                {
                    "event_id": "event-public-revision",
                    "sequence": 1,
                    "private_revision": "PRIVATE_REVISION_MARKER",
                }
            ]
            state["latest_evidence"] = [
                {
                    "command": "PRIVATE_COMMAND_MARKER",
                    "artifact_path": "PRIVATE_ARTIFACT_MARKER",
                }
            ]
            paths.state.write_text(json.dumps(state), encoding="utf-8")
            for projection in ("brief", "working", "resume"):
                context_path = paths.context / f"{projection}.json"
                context = json.loads(context_path.read_text(encoding="utf-8"))
                context["private_context"] = "PRIVATE_CONTEXT_MARKER"
                context_path.write_text(json.dumps(context), encoding="utf-8")
            integration = json.loads(
                paths.integration_status.read_text(encoding="utf-8")
            )
            integration["private_integration"] = "PRIVATE_INTEGRATION_MARKER"
            paths.integration_status.write_text(
                json.dumps(integration), encoding="utf-8"
            )

            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            with opener.open(f"{base}/api/state", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual("application/json; charset=utf-8", response.headers["Content-Type"])

            self.assertEqual(
                {
                    "session",
                    "state",
                    "events",
                    "history_window",
                    "context",
                    "integration",
                },
                set(payload),
            )
            self.assertEqual(
                {"goal_id", "title", "repository_snapshot", "updated_at"},
                set(payload["session"]),
            )
            self.assertEqual(
                {
                    "goal_state",
                    "plan_version",
                    "packets",
                    "progress",
                    "eta",
                    "revision_history",
                    "latest_evidence",
                    "next_action",
                    "stale",
                    "warnings",
                    "diagnostics",
                    "eta_recent_trigger_history",
                },
                set(payload["state"]),
            )
            self.assertEqual(
                {
                    "id",
                    "objective",
                    "owner",
                    "status",
                    "progress_weight",
                    "order",
                    "attempt",
                    "elapsed_seconds",
                    "evidence",
                    "history_status",
                    "history_warning",
                },
                set(payload["state"]["packets"][0]),
            )
            self.assertEqual(
                {
                    "verified_weight",
                    "active_planned_weight",
                    "percent",
                    "display_percent",
                },
                set(payload["state"]["progress"]),
            )
            self.assertEqual(
                {
                    "status",
                    "summary",
                    "low_seconds",
                    "high_seconds",
                    "calibration_factor",
                    "confidence",
                    "warnings",
                },
                set(payload["state"]["eta"]),
            )
            self.assertEqual(
                {
                    "sequence",
                    "emitted_at",
                    "event_type",
                    "summary",
                    "packet_id",
                    "plan_version",
                },
                set(payload["events"][0]),
            )
            for projection in ("brief", "working", "resume"):
                self.assertEqual(
                    {
                        "status",
                        "count_kind",
                        "count",
                        "target",
                        "hard_cap",
                        "text",
                        "required_fact_refs",
                        "evidence_label",
                        "standalone_safe",
                        "presentation_warning",
                    },
                    set(payload["context"][projection]),
                )
            self.assertEqual(
                {"status", "reason", "portable_progress_available"},
                set(payload["integration"]),
            )
            self.assertEqual("planned", payload["state"]["goal_state"])
            self.assertEqual("Verify the progress contract", payload["session"]["title"])
            self.assertEqual("<brief> & ready", payload["context"]["brief"]["text"])
            self.assertEqual("BLOCKED", payload["integration"]["status"])
            self.assertEqual("goal.started", payload["events"][0]["event_type"])
            public_json = json.dumps(payload)
            for private_marker in (
                "submission-token",
                "PRIVATE_STATE_MARKER",
                "PRIVATE_REVISION_MARKER",
                "PRIVATE_COMMAND_MARKER",
                "PRIVATE_ARTIFACT_MARKER",
                "PRIVATE_CONTEXT_MARKER",
                "PRIVATE_INTEGRATION_MARKER",
            ):
                self.assertNotIn(private_marker, public_json)

    def test_full_projection_derives_strict_packet_evidence_and_eta_history(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            state = json.loads(paths.state.read_text(encoding="utf-8"))
            state["revision_history"] = [
                {
                    "event_id": "event-plan-revised",
                    "sequence": 2,
                    "previous_plan_version": 1,
                    "plan_version": 2,
                    "revision_reason": "Approved follow-up packet.",
                    "approval_ref": "reviewer:MAD",
                    "previous_manifest_hash": "a" * 64,
                    "new_manifest_hash": "b" * 64,
                    "progress_recalculated": True,
                    "eta_recalculated": True,
                    "private_revision": "PRIVATE_REVISION_DETAIL",
                },
            ]
            state["latest_evidence"] = [
                {
                    "id": "evidence-command",
                    "label": "Verified",
                    "kind": "command",
                    "summary": "Focused command completed.",
                    "command": "python verify.py authorization=Bearer-secret-value",
                    "exit_code": 0,
                    "artifact_path": None,
                    "sha256": None,
                    "private_evidence": "PRIVATE_EVIDENCE_DETAIL",
                },
                {
                    "id": "evidence-artifact",
                    "label": "Snapshot",
                    "kind": "artifact",
                    "summary": "Bounded public artifact.",
                    "command": None,
                    "exit_code": None,
                    "artifact_path": "logs/public-result.json",
                    "sha256": "0" * 64,
                },
                {
                    "id": "evidence-private-artifact",
                    "label": "Snapshot",
                    "kind": "artifact",
                    "summary": "Private runtime artifact.",
                    "command": None,
                    "exit_code": None,
                    "artifact_path": "runtime/submission-token",
                    "sha256": "1" * 64,
                },
            ]
            state["private_state"] = "PRIVATE_STATE_DETAIL"
            state["eta"]["private_eta"] = "PRIVATE_ETA_DETAIL"
            paths.state.write_text(json.dumps(state), encoding="utf-8")
            (paths.logs / "public-result.json").write_text(
                '{"result":"ok"}', encoding="utf-8"
            )

            original_progress = paths.progress.read_bytes()
            events = [
                {
                    "sequence": 1,
                    "emitted_at": "2026-09-04T02:00:00Z",
                    "writer_epoch_id": "epoch-public",
                    "monotonic_offset_ms": 0,
                    "plan_version": 1,
                    "event_type": "goal.started",
                    "packet_id": None,
                    "summary": "Goal started.",
                    "evidence": [],
                    "payload": {"private": "PRIVATE_EVENT_PAYLOAD"},
                    "raw_log_ref": "PRIVATE_RAW_LOG",
                },
                {
                    "sequence": 2,
                    "emitted_at": "2026-09-04T02:00:01Z",
                    "writer_epoch_id": "epoch-public",
                    "monotonic_offset_ms": 1000,
                    "plan_version": 1,
                    "event_type": "packet.started",
                    "packet_id": "packet-contract",
                    "summary": "Packet started.",
                    "evidence": [state["latest_evidence"][0]],
                    "payload": {"private": "PRIVATE_EVENT_PAYLOAD"},
                    "raw_log_ref": "PRIVATE_RAW_LOG",
                },
                {
                    "sequence": 3,
                    "emitted_at": "2026-09-04T02:00:04Z",
                    "writer_epoch_id": "epoch-public",
                    "monotonic_offset_ms": 4000,
                    "plan_version": 1,
                    "event_type": "runtime.heartbeat",
                    "packet_id": None,
                    "summary": "Runtime heartbeat.",
                    "evidence": [],
                    "payload": {"private": "PRIVATE_EVENT_PAYLOAD"},
                    "raw_log_ref": "PRIVATE_RAW_LOG",
                },
            ]
            paths.progress.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            try:
                opener, _redirects, _url = self.authenticated_opener(
                    info, capability
                )
                base = f"http://127.0.0.1:{info['public_port']}"
                with opener.open(f"{base}/api/state", timeout=2.0) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                paths.progress.write_bytes(original_progress)

            public_state = payload["state"]
            self.assertEqual(1, public_state["plan_version"])
            self.assertEqual(
                {
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
                },
                set(public_state["revision_history"][0]),
            )
            packet = public_state["packets"][0]
            self.assertEqual(
                {
                    "id",
                    "objective",
                    "owner",
                    "status",
                    "progress_weight",
                    "order",
                    "attempt",
                    "elapsed_seconds",
                    "evidence",
                    "history_status",
                    "history_warning",
                },
                set(packet),
            )
            self.assertEqual(1, packet["order"])
            self.assertEqual(1, packet["attempt"])
            self.assertEqual(3.0, packet["elapsed_seconds"])
            self.assertEqual("evidence-command", packet["evidence"][0]["id"])
            command = public_state["latest_evidence"][0]
            self.assertEqual(
                {"id", "label", "kind", "summary", "command", "exit_code"},
                set(command),
            )
            self.assertIn("[REDACTED]", command["command"])
            artifact = public_state["latest_evidence"][1]
            self.assertEqual(
                {"id", "label", "kind", "summary", "artifact_path", "artifact_href", "sha256"},
                set(artifact),
            )
            self.assertEqual(
                "/artifact?path=logs%2Fpublic-result.json", artifact["artifact_href"]
            )
            private_artifact = public_state["latest_evidence"][2]
            self.assertNotIn("artifact_path", private_artifact)
            self.assertNotIn("artifact_href", private_artifact)
            self.assertEqual(
                [
                    {"sequence": 1, "emitted_at": "2026-09-04T02:00:00Z", "plan_version": 1, "trigger": "goal.started"},
                    {"sequence": 2, "emitted_at": "2026-09-04T02:00:01Z", "plan_version": 1, "trigger": "packet.started"},
                    {"sequence": 3, "emitted_at": "2026-09-04T02:00:04Z", "plan_version": 1, "trigger": "runtime.heartbeat"},
                ],
                public_state["eta_recent_trigger_history"]["entries"],
            )
            self.assertEqual(
                {
                    "kind",
                    "history_status",
                    "historical_range_snapshots_available",
                    "warning",
                    "entries",
                },
                set(public_state["eta_recent_trigger_history"]),
            )
            self.assertEqual(
                "recent_trigger_history",
                public_state["eta_recent_trigger_history"]["kind"],
            )
            self.assertEqual(
                "complete",
                public_state["eta_recent_trigger_history"]["history_status"],
            )
            self.assertFalse(
                public_state["eta_recent_trigger_history"][
                    "historical_range_snapshots_available"
                ]
            )
            self.assertIn(
                "Historical ETA range snapshots are not recorded",
                public_state["eta_recent_trigger_history"]["warning"],
            )
            public_json = json.dumps(payload)
            for marker in (
                "PRIVATE_STATE_DETAIL",
                "PRIVATE_REVISION_DETAIL",
                "PRIVATE_EVIDENCE_DETAIL",
                "PRIVATE_ETA_DETAIL",
                "PRIVATE_EVENT_PAYLOAD",
                "PRIVATE_RAW_LOG",
                "Bearer-secret-value",
                "runtime/submission-token",
            ):
                self.assertNotIn(marker, public_json)

    def test_context_projection_exposes_budget_and_blocked_presentation_metadata(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            blocked = {
                "schema_version": 1,
                "goal_id": "goal-demo-001",
                "projection": "resume",
                "status": "BLOCKED",
                "count_kind": "utf8_byte_fallback",
                "count": 2400,
                "target": 1600,
                "hard_cap": 2400,
                "text": "Required safety fact cannot fit.",
                "required_fact_refs": ["goal-demo-001#safety-critical"],
                "evidence_label": "BLOCKED",
                "private_context": "PRIVATE_CONTEXT_DETAIL",
            }
            (paths.context / "resume.json").write_text(
                json.dumps(blocked), encoding="utf-8"
            )
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            with opener.open(f"{base}/api/state", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))

            ready = payload["context"]["brief"]
            blocked_public = payload["context"]["resume"]
            expected = {
                "status",
                "count_kind",
                "count",
                "target",
                "hard_cap",
                "text",
                "required_fact_refs",
                "evidence_label",
                "standalone_safe",
                "presentation_warning",
            }
            self.assertEqual(expected, set(ready))
            self.assertTrue(ready["standalone_safe"])
            self.assertIsNone(ready["presentation_warning"])
            self.assertEqual(expected, set(blocked_public))
            self.assertFalse(blocked_public["standalone_safe"])
            self.assertIn("must not be used as standalone context", blocked_public["presentation_warning"])
            self.assertNotIn("PRIVATE_CONTEXT_DETAIL", json.dumps(payload))

    def test_public_commands_redact_separated_and_structured_credentials(self) -> None:
        hostile_commands = [
            (
                "tool --token token-secret-value",
                "tool --token [REDACTED]",
                ("token-secret-value",),
            ),
            (
                "tool --api-key 'quoted api secret'",
                "tool --api-key '[REDACTED]'",
                ("quoted api secret",),
            ),
            (
                'tool --client-secret "quoted client secret"',
                'tool --client-secret "[REDACTED]"',
                ("quoted client secret",),
            ),
            (
                "tool --ToKeN MiXeDSecret",
                "tool --ToKeN [REDACTED]",
                ("MiXeDSecret",),
            ),
            (
                "tool --authorization Bearer bearer-secret --safe yes",
                "tool --authorization Bearer [REDACTED] --safe yes",
                ("bearer-secret",),
            ),
            (
                'tool --token "unterminated-secret',
                "[REDACTED: command omitted]",
                ("unterminated-secret",),
            ),
            (
                "TOKEN=env-secret tool",
                "TOKEN=[REDACTED] tool",
                ("env-secret",),
            ),
            (
                "OPENAI_API_KEY=openai-secret tool",
                "OPENAI_API_KEY=[REDACTED] tool",
                ("openai-secret",),
            ),
            (
                "AWS_SECRET_ACCESS_KEY=aws-secret tool",
                "AWS_SECRET_ACCESS_KEY=[REDACTED] tool",
                ("aws-secret",),
            ),
            (
                "GITHUB_TOKEN=github-secret tool",
                "GITHUB_TOKEN=[REDACTED] tool",
                ("github-secret",),
            ),
            (
                "tool --API_KEY=assigned-secret",
                "tool --API_KEY=[REDACTED]",
                ("assigned-secret",),
            ),
            (
                "tool key=legacy-key-secret --safe yes",
                "tool key=[REDACTED] --safe yes",
                ("legacy-key-secret",),
            ),
            (
                'curl -H "Authorization: Bearer header-secret"',
                'curl -H "Authorization: Bearer [REDACTED]"',
                ("header-secret",),
            ),
            (
                'curl -H "X-Api-Key: x-api-secret"',
                'curl -H "X-Api-Key: [REDACTED]"',
                ("x-api-secret",),
            ),
            (
                "curl 'https://example.invalid/?token="
                "query-secret&safe=1'",
                "curl 'https://example.invalid/?token=[REDACTED]&safe=1'",
                ("query-secret",),
            ),
            (
                "$env:CLIENT_SECRET='powershell-secret'; tool",
                "$env:CLIENT_SECRET='[REDACTED]'; tool",
                ("powershell-secret",),
            ),
            (
                'tool --token "abc\\"def" --safe yes',
                'tool --token "[REDACTED]" --safe yes',
                ("abc", "def"),
            ),
            (
                "tool --token 'abc''def' --safe yes",
                "tool --token '[REDACTED]' --safe yes",
                ("abc", "def"),
            ),
            (
                "tool --token 'abc'\\''def' --safe yes",
                "tool --token '[REDACTED]' --safe yes",
                ("abc", "def"),
            ),
            (
                'tool "--token" quoted-option-secret --safe yes',
                'tool "--token" [REDACTED] --safe yes',
                ("quoted-option-secret",),
            ),
            (
                '''tool --headers '{"Authorization":"Bearer json-secret"}' --safe yes''',
                '''tool --headers '{"Authorization":"Bearer [REDACTED]"}' --safe yes''',
                ("json-secret",),
            ),
            (
                'tool --headers "{\\"Authorization\\":\\"Bearer escaped-json-secret\\"}" --safe yes',
                "[REDACTED: command omitted]",
                ("escaped-json-secret",),
            ),
        ]
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            state = json.loads(paths.state.read_text(encoding="utf-8"))
            state["latest_evidence"] = [
                {
                    "id": f"command-{index}",
                    "label": "Verified",
                    "kind": "command",
                    "summary": "Credential-bearing command completed.",
                    "command": command,
                    "exit_code": 0,
                    "artifact_path": None,
                    "sha256": None,
                }
                for index, (command, _expected, _secrets) in enumerate(
                    hostile_commands, start=1
                )
            ]
            paths.state.write_text(json.dumps(state), encoding="utf-8")

            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            with opener.open(f"{base}/api/state", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))

            commands = [
                record["command"] for record in payload["state"]["latest_evidence"]
            ]
            self.assertEqual(
                [expected for _command, expected, _secrets in hostile_commands],
                commands,
            )
            for transformed, (_command, _expected, secrets) in zip(
                commands, hostile_commands
            ):
                for secret in secrets:
                    self.assertNotIn(secret, transformed)
            self.assertTrue(any(command.endswith('" --safe yes') for command in commands))
            self.assertTrue(any(command.endswith("' --safe yes") for command in commands))
            self.assertTrue(any(command.endswith("}' --safe yes") for command in commands))
            self.assertTrue(any("&safe=1'" in command for command in commands))

        safe_commands = (
            "tool --safe yes --tokenizer sentencepiece --api-key-file public.json",
            "curl 'https://example.invalid/?safe_token_count=2&safe=1' --safe yes",
            'tool "--tokenizer" sentencepiece --safe yes',
            "tool '--api-key-file' public.json --safe yes",
            'tool "--to"kenizer sentencepiece --safe yes',
            "tool SAFE_TO'KEN'_COUNT=2 --safe yes",
        )
        for command in safe_commands:
            with self.subTest(command=command):
                self.assertEqual(command, goal_progress_server._public_command(command))

        self.assertEqual(
            "[OMITTED: command exceeds public limit]",
            goal_progress_server._public_command("tool --safe yes " + "x" * 600),
        )
        self.assertLessEqual(
            len(goal_progress_server._public_command("tool " + "x" * 600) or ""),
            500,
        )

    def test_public_commands_fail_closed_for_malformed_and_quote_split_credentials(
        self,
    ) -> None:
        commands = (
            ("tool --token --api-key second-secret --safe yes", ("second-secret",)),
            (
                "tool --token Bearer --api-key second-secret --safe yes",
                ("second-secret",),
            ),
            ("tool --token= --safe yes", ()),
            (
                'tool --to"ken"=split-mid-secret --safe yes',
                ("split-mid-secret",),
            ),
            ("tool TO'KEN'=split-env-secret --safe yes", ("split-env-secret",)),
            (
                'tool --token "--api-key" SYNTHETIC_CREDENTIAL_7F4A --safe yes',
                ("SYNTHETIC_CREDENTIAL_7F4A",),
            ),
            (
                "tool --token '--api-key' SYNTHETIC_CREDENTIAL_7F4A --safe yes",
                ("SYNTHETIC_CREDENTIAL_7F4A",),
            ),
            (
                'tool --token Bearer "--api-key" SYNTHETIC_CREDENTIAL_7F4A --safe yes',
                ("SYNTHETIC_CREDENTIAL_7F4A",),
            ),
            (
                'tool "--to"ken SYNTHETIC_CREDENTIAL_7F4A --safe yes',
                ("SYNTHETIC_CREDENTIAL_7F4A",),
            ),
            (
                "tool '--to'ken SYNTHETIC_CREDENTIAL_7F4A --safe yes",
                ("SYNTHETIC_CREDENTIAL_7F4A",),
            ),
            (
                "tool ''TO'KEN'=SYNTHETIC_CREDENTIAL_R1_9D2A'' --safe yes",
                ("SYNTHETIC_CREDENTIAL_R1_9D2A",),
            ),
            (
                "tool 'TO'KEN'=SYNTHETIC_CREDENTIAL_R1_9D2A' --safe yes",
                ("SYNTHETIC_CREDENTIAL_R1_9D2A",),
            ),
            (
                'tool "TO"KEN"=SYNTHETIC_CREDENTIAL_R1_9D2A" --safe yes',
                ("SYNTHETIC_CREDENTIAL_R1_9D2A",),
            ),
        )

        for command, secrets in commands:
            with self.subTest(command=command):
                transformed = goal_progress_server._public_command(command)
                self.assertEqual("[REDACTED: command omitted]", transformed)
                for secret in secrets:
                    self.assertNotIn(secret, transformed or "")

    def test_public_command_scanner_has_linear_bounded_character_work(self) -> None:
        class CountingCommand(str):
            def __new__(cls, value: str) -> "CountingCommand":
                instance = super().__new__(cls, value)
                instance.character_reads = 0
                return instance

            def __getitem__(self, key: object) -> str:
                if isinstance(key, slice):
                    start, stop, step = key.indices(len(self))
                    self.character_reads += len(range(start, stop, step))
                else:
                    self.character_reads += 1
                return super().__getitem__(key)  # type: ignore[index]

        adversarial = CountingCommand(("a''" * 1365) + "a")
        self.assertEqual(4096, len(adversarial))

        redacted = goal_progress_server._redact_public_command(adversarial)

        self.assertEqual(str(adversarial), redacted)
        self.assertLessEqual(adversarial.character_reads, 262_144)

    def test_public_state_preserves_complete_latest_evidence_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            goal_root = Path(tmpdir) / "goal"
            goal_root.mkdir()
            paths = GoalPaths.from_root(goal_root)
            state = {
                "goal_state": "running",
                "packets": [],
                "progress": {},
                "eta": {},
                "revision_history": [],
                "latest_evidence": [
                    {
                        "id": f"evidence-{index:03d}",
                        "label": "Verified",
                        "kind": "command",
                        "summary": "Bounded command evidence.",
                        "command": "tool --safe yes",
                        "exit_code": 0,
                    }
                    for index in range(150)
                ],
                "warnings": [],
            }

            projected = goal_progress_server._public_state_projection(
                state,
                [],
                paths,
                {"partial": False},
            )

        evidence = projected["latest_evidence"]
        self.assertEqual(150, len(evidence))
        self.assertEqual("evidence-000", evidence[0]["id"])
        self.assertEqual("evidence-149", evidence[-1]["id"])

    def test_compact_shell_renders_stale_evidence_and_failure_diagnostics(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            html = opener.open(f"{base}/compact", timeout=2.0).read().decode("utf-8")
            script = opener.open(f"{base}/assets/app.js", timeout=2.0).read().decode("utf-8")

            for element_id in (
                "last-updated",
                "stale-status",
                "latest-evidence",
                "diagnostics",
            ):
                self.assertIn(f'id="{element_id}"', html)
                self.assertIn(f'#{element_id}', script)
            self.assertIn("waiting_input", script)
            self.assertIn("blocked", script)
            self.assertIn("failed", script)
            self.assertNotIn("innerHTML", script)

    def test_full_table_preserves_canonical_order_and_compact_promotes_active(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            state = json.loads(paths.state.read_text(encoding="utf-8"))
            state["packets"] = [
                {
                    "id": "packet-first",
                    "status": "queued",
                    "owner": "planner",
                    "objective": "First canonical packet",
                    "progress_weight": 1,
                },
                {
                    "id": "packet-later-active",
                    "status": "running",
                    "owner": "worker",
                    "objective": "Later active packet",
                    "progress_weight": 2,
                },
            ]
            paths.state.write_text(json.dumps(state), encoding="utf-8")
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            with opener.open(f"{base}/api/state", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            script = opener.open(f"{base}/assets/app.js", timeout=2.0).read().decode("utf-8")

            packets = payload["state"]["packets"]
            self.assertEqual(["packet-first", "packet-later-active"], [item["id"] for item in packets])
            self.assertEqual([1, 2], [item["order"] for item in packets])
            self.assertIn('dashboard.dataset.view === "compact"', script)
            self.assertIn('matchMedia("(max-width: 720px)")', script)
            self.assertNotIn("const ordered = [...packets].sort", script)

    def test_public_state_reads_do_not_hold_the_private_writer_mutex(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            read_started = threading.Event()
            allow_read = threading.Event()
            state_errors: list[BaseException] = []
            event_result: list[dict[str, object]] = []
            event_errors: list[BaseException] = []
            real_read_public_json = goal_progress_server._read_public_json

            def slow_state_read(path: Path, label: str) -> dict[str, object] | None:
                if Path(path) == paths.state:
                    read_started.set()
                    if not allow_read.wait(3.0):
                        raise AssertionError("test did not release public state read")
                return real_read_public_json(path, label)

            def read_state() -> None:
                try:
                    with opener.open(f"{base}/api/state", timeout=4.0) as response:
                        response.read()
                except BaseException as exc:
                    state_errors.append(exc)

            def post_event() -> None:
                try:
                    event_result.append(
                        request_private_json(
                            info,
                            capability,
                            "POST",
                            "/events",
                            packet_event(
                                "packet.started", sequence=2, state="running"
                            ),
                        )
                    )
                except BaseException as exc:
                    event_errors.append(exc)

            state_thread = threading.Thread(target=read_state)
            event_thread = threading.Thread(target=post_event)
            try:
                with mock.patch(
                    "scripts.goal_progress_server._read_public_json",
                    side_effect=slow_state_read,
                ):
                    state_thread.start()
                    self.assertTrue(read_started.wait(2.0))
                    event_thread.start()
                    event_thread.join(timeout=1.5)
                    self.assertFalse(
                        event_thread.is_alive(),
                        "private event POST waited on public filesystem reads",
                    )
            finally:
                allow_read.set()
                state_thread.join(timeout=5.0)
                event_thread.join(timeout=5.0)

            self.assertFalse(state_errors)
            self.assertFalse(event_errors)
            self.assertEqual(2, event_result[0]["accepted"]["sequence"])

    def test_public_event_summaries_use_a_bounded_tail_window(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            original_progress = paths.progress.read_bytes()
            prefix = b"x" * (3 * 1024 * 1024) + b"\n"
            recent = []
            for sequence in range(1, 121):
                recent.append(
                    json.dumps(
                        {
                            "sequence": sequence,
                            "emitted_at": "2026-09-04T02:00:00Z",
                            "event_type": "runtime.heartbeat",
                            "packet_id": None,
                            "summary": f"Recent event {sequence}",
                        },
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
            paths.progress.write_bytes(prefix + b"".join(recent))
            try:
                opener, _redirects, _url = self.authenticated_opener(
                    info, capability
                )
                base = f"http://127.0.0.1:{info['public_port']}"
                with opener.open(f"{base}/api/state", timeout=2.0) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                paths.progress.write_bytes(original_progress)

            self.assertEqual(100, len(payload["events"]))
            self.assertEqual(21, payload["events"][0]["sequence"])
            self.assertEqual(120, payload["events"][-1]["sequence"])

    def test_bounded_history_labels_runtime_details_and_recent_triggers_partial(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            original_progress = paths.progress.read_bytes()
            state = json.loads(paths.state.read_text(encoding="utf-8"))
            state["packets"][0]["status"] = "running"
            paths.state.write_text(json.dumps(state), encoding="utf-8")
            command_evidence = {
                "id": "evidence-before-window",
                "label": "Verified",
                "kind": "command",
                "summary": "Evidence existed before the public history window.",
                "command": "python verify.py",
                "exit_code": 0,
                "artifact_path": None,
                "sha256": None,
            }
            early_events = [
                {
                    "sequence": 1,
                    "emitted_at": "2026-09-04T02:00:00Z",
                    "writer_epoch_id": "epoch-partial",
                    "monotonic_offset_ms": 0,
                    "plan_version": 1,
                    "event_type": "packet.started",
                    "packet_id": "packet-contract",
                    "summary": "First attempt started.",
                    "evidence": [],
                },
                {
                    "sequence": 2,
                    "emitted_at": "2026-09-04T02:00:01Z",
                    "writer_epoch_id": "epoch-partial",
                    "monotonic_offset_ms": 1000,
                    "plan_version": 1,
                    "event_type": "packet.retry_started",
                    "packet_id": "packet-contract",
                    "summary": "Second attempt and evidence.",
                    "evidence": [command_evidence],
                },
            ]
            large_events = [
                {
                    "sequence": sequence,
                    "emitted_at": "2026-09-04T02:00:02Z",
                    "event_type": "runtime.heartbeat",
                    "packet_id": None,
                    "summary": "x" * (230 * 1024),
                }
                for sequence in range(3, 13)
            ]
            recent_events = [
                {
                    "sequence": sequence,
                    "emitted_at": "2026-09-04T02:00:03Z",
                    "event_type": "runtime.heartbeat",
                    "packet_id": None,
                    "plan_version": 1,
                    "summary": f"Recent trigger {sequence}",
                }
                for sequence in range(13, 133)
            ]
            all_events = early_events + large_events + recent_events
            paths.progress.write_text(
                "".join(json.dumps(event) + "\n" for event in all_events),
                encoding="utf-8",
            )
            try:
                opener, _redirects, _url = self.authenticated_opener(
                    info, capability
                )
                base = f"http://127.0.0.1:{info['public_port']}"
                with opener.open(f"{base}/api/state", timeout=2.0) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                html = opener.open(f"{base}/full", timeout=2.0).read().decode(
                    "utf-8"
                )
                script = opener.open(f"{base}/assets/app.js", timeout=2.0).read().decode(
                    "utf-8"
                )
            finally:
                paths.progress.write_bytes(original_progress)

            window = payload["history_window"]
            self.assertEqual(
                {
                    "max_events",
                    "max_bytes",
                    "available_events",
                    "partial",
                    "truncated",
                    "truncated_by",
                    "first_available_sequence",
                    "last_available_sequence",
                },
                set(window),
            )
            self.assertEqual(100, window["max_events"])
            self.assertEqual(2 * 1024 * 1024, window["max_bytes"])
            self.assertTrue(window["partial"])
            self.assertTrue(window["truncated"])
            self.assertEqual(["bytes", "events"], window["truncated_by"])
            self.assertEqual(33, window["first_available_sequence"])
            self.assertEqual(132, window["last_available_sequence"])
            packet = payload["state"]["packets"][0]
            self.assertIsNone(packet["attempt"])
            self.assertIsNone(packet["elapsed_seconds"])
            self.assertEqual([], packet["evidence"])
            self.assertEqual("partial", packet["history_status"])
            self.assertIn("Earlier events are excluded", packet["history_warning"])
            eta_history = payload["state"]["eta_recent_trigger_history"]
            self.assertEqual("recent_trigger_history", eta_history["kind"])
            self.assertEqual("partial", eta_history["history_status"])
            self.assertFalse(eta_history["historical_range_snapshots_available"])
            self.assertEqual(100, len(eta_history["entries"]))
            self.assertIn("bounded public history window", eta_history["warning"])
            self.assertIn('id="history-warning"', html)
            self.assertIn("Recent ETA trigger history", html)
            self.assertIn("historical ETA range snapshots are not recorded", html)
            self.assertIn('id="active-attempt">Unavailable</dd>', html)
            self.assertIn('id="active-elapsed">Unavailable</dd>', html)
            self.assertIn("history_window", script)
            self.assertIn("Unavailable (history partial)", script)

    def test_simultaneous_runtimes_use_distinct_cookie_names_and_secrets(self) -> None:
        with self.running_dashboard() as (_root_a, info_a, capability_a), self.running_dashboard() as (
            _root_b,
            info_b,
            capability_b,
        ):
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar)
            )
            with opener.open(self.mint_url(info_a, capability_a), timeout=2.0):
                pass
            with opener.open(self.mint_url(info_b, capability_b), timeout=2.0):
                pass

            cookies = list(jar)
            self.assertEqual(2, len(cookies))
            self.assertEqual(2, len({cookie.name for cookie in cookies}))
            self.assertEqual(2, len({cookie.value for cookie in cookies}))
            for info in (info_a, info_b):
                base = f"http://127.0.0.1:{info['public_port']}"
                with opener.open(f"{base}/api/state", timeout=2.0) as response:
                    self.assertEqual(200, response.status)

    def test_artifacts_reject_traversal_and_serve_hostile_types_inertly(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            hostile = {
                "report.html": b"<script>alert(1)</script>",
                "vector.svg": b"<svg onload='alert(1)'></svg>",
                "data.json": b'{"value":"<script>alert(1)</script>"}',
                "runtime.log": b"<script>alert(1)</script>\n",
            }
            for name, body in hostile.items():
                (paths.logs / name).write_bytes(body)

            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            traversal = (
                "../outside.txt",
                "%2e%2e/outside.txt",
                "..%5coutside.txt",
                "C:%5cWindows%5cwin.ini",
                "runtime/submission-token",
                "runtime./submission-token",
            )
            for candidate in traversal:
                with self.subTest(candidate=candidate), self.assertRaises(
                    urllib.error.HTTPError
                ) as forbidden:
                    opener.open(
                        f"{base}/artifact?path={candidate}", timeout=2.0
                    )
                self.assertEqual(403, forbidden.exception.code)
                self.assert_security_headers(forbidden.exception.headers)

            for name, body in hostile.items():
                route = f"{base}/artifact?path={urllib.parse.quote(f'logs/{name}')}"
                with self.subTest(name=name), opener.open(route, timeout=2.0) as response:
                    self.assertEqual(body, response.read())
                    self.assert_security_headers(response.headers)
                    if name.endswith((".html", ".svg")):
                        self.assertEqual(
                            "application/octet-stream", response.headers["Content-Type"]
                        )
                        self.assertTrue(
                            response.headers["Content-Disposition"].startswith("attachment;")
                        )
                    else:
                        self.assertEqual(
                            "text/plain; charset=utf-8", response.headers["Content-Type"]
                        )

    def test_artifact_reparse_component_is_forbidden(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            paths = GoalPaths.from_root(goal_root)
            outside = goal_root.parent / "outside.log"
            outside.write_text("outside", encoding="utf-8")
            link = paths.logs / "linked.log"
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"real symlink/reparse creation unavailable: {exc}")

            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            with self.assertRaises(urllib.error.HTTPError) as forbidden:
                opener.open(f"{base}/artifact?path=logs/linked.log", timeout=2.0)
            self.assertEqual(403, forbidden.exception.code)

    def test_artifacts_reject_short_name_alias_shapes_portably(self) -> None:
        with self.running_dashboard() as (goal_root, info, capability):
            alias = goal_root / "PRIVAT~1"
            alias.mkdir()
            (alias / "secret.log").write_text("private", encoding="utf-8")
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"

            with self.assertRaises(urllib.error.HTTPError) as forbidden:
                opener.open(
                    f"{base}/artifact?path=PRIVAT~1/secret.log", timeout=2.0
                )

            self.assertEqual(403, forbidden.exception.code)
            self.assert_security_headers(forbidden.exception.headers)

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 aliases are Windows-only")
    def test_artifacts_reject_real_quarantine_short_alias_when_available(self) -> None:
        import ctypes

        with self.running_dashboard() as (goal_root, info, capability):
            quarantine = goal_root / "quarantine"
            quarantine.mkdir(exist_ok=True)
            (quarantine / "secret.log").write_text("private", encoding="utf-8")
            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(  # type: ignore[attr-defined]
                str(quarantine), buffer, len(buffer)
            )
            if length == 0 or length >= len(buffer):
                self.skipTest("8.3 short-name lookup is unavailable")
            alias_name = Path(buffer.value).name
            if alias_name.casefold() == quarantine.name.casefold():
                self.skipTest("8.3 alias generation is disabled on this volume")

            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            with self.assertRaises(urllib.error.HTTPError) as forbidden:
                opener.open(
                    f"{base}/artifact?path={urllib.parse.quote(alias_name)}/secret.log",
                    timeout=2.0,
                )
            self.assertEqual(403, forbidden.exception.code)

    def test_attachment_disposition_blocks_header_injection_and_unicode_crashes(self) -> None:
        class FakeArtifact:
            def __init__(self, name: str) -> None:
                self.name = name

            def read_bytes(self) -> bytes:
                return b"artifact"

        with self.running_dashboard() as (_goal_root, info, capability):
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            names = (
                "report\r\nX-Injected: yes.txt",
                "studio-\u96ea-report.txt",
            )
            for name in names:
                with self.subTest(name=name), mock.patch(
                    "scripts.goal_progress_server._artifact_target",
                    return_value=(FakeArtifact(name), "application/octet-stream", True),
                ):
                    try:
                        with opener.open(
                            f"{base}/artifact?path=logs/report.txt", timeout=2.0
                        ) as response:
                            disposition = response.headers["Content-Disposition"]
                            self.assertEqual(b"artifact", response.read())
                    except (UnicodeEncodeError, http.client.RemoteDisconnected) as exc:
                        self.fail(f"attachment header serialization failed: {exc}")
                    self.assertNotIn("X-Injected", response.headers)
                    self.assertNotIn("\r", disposition)
                    self.assertNotIn("\n", disposition)
                    self.assertIn("filename=", disposition)
                    self.assertIn("filename*=UTF-8''", disposition)

    def test_head_options_and_handler_errors_keep_security_headers(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            for method in ("HEAD", "OPTIONS"):
                request = urllib.request.Request(f"{base}/api/state", method=method)
                with self.subTest(method=method), self.assertRaises(
                    urllib.error.HTTPError
                ) as rejected:
                    opener.open(request, timeout=2.0)
                self.assertEqual(405, rejected.exception.code)
                self.assert_security_headers(rejected.exception.headers)

            trace = urllib.request.Request(f"{base}/api/state", method="TRACE")
            with self.assertRaises(urllib.error.HTTPError) as unsupported:
                opener.open(trace, timeout=2.0)
            self.assertEqual(501, unsupported.exception.code)
            self.assert_security_headers(unsupported.exception.headers)

            client = socket.create_connection(
                ("127.0.0.1", int(info["public_port"])), timeout=1.0
            )
            try:
                client.sendall(
                    b"GET /api/state HTTP/1.1\r\nX-Long: "
                    + b"a" * 65537
                    + b"\r\n\r\n"
                )
                client.settimeout(2.0)
                raw = bytearray()
                while b"\r\n\r\n" not in raw:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    raw.extend(chunk)
            finally:
                client.close()
            header_text = raw.decode("latin-1")
            self.assertIn(" 431 ", header_text.split("\r\n", 1)[0])
            for name, expected in SECURITY_HEADERS.items():
                self.assertIn(f"{name}: {expected}\r\n", header_text)

    def test_bootstrap_token_expires_after_sixty_seconds(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            before_mint = time.monotonic()
            url = self.mint_url(info, capability)
            with mock.patch(
                "scripts.goal_progress_server.time.monotonic",
                return_value=before_mint + 61.0,
            ):
                with self.assertRaises(urllib.error.HTTPError) as expired:
                    urllib.request.urlopen(url, timeout=2.0)
            self.assertEqual(401, expired.exception.code)
            self.assert_security_headers(expired.exception.headers)

    def test_bundled_asset_discovery_uses_the_owning_skill_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = Path(tmpdir) / "goal-progress-skill"
            scripts = skill / "scripts"
            assets = skill / "assets"
            scripts.mkdir(parents=True)
            assets.mkdir()
            script = scripts / "goal_progress_server.py"
            script.write_text("# bundled", encoding="utf-8")
            for name in ("index.html", "styles.css", "app.js"):
                (assets / name).write_text(name, encoding="utf-8")

            self.assertEqual(assets.resolve(), discover_dashboard_assets(script))

    def test_non_reading_sse_socket_does_not_block_private_writer(self) -> None:
        sse_entered = threading.Event()
        original_serve_events = goal_progress_server._PublicHandler._serve_events

        def synchronized_serve_events(handler: object) -> None:
            sse_entered.set()
            original_serve_events(handler)  # type: ignore[arg-type]

        with mock.patch.object(
            goal_progress_server._PublicHandler,
            "_serve_events",
            synchronized_serve_events,
        ), mock.patch.object(
            goal_progress_server._BoundedThreadingHTTPServer,
            "handle_error",
        ) as server_error:
            with self.running_dashboard() as (_goal_root, info, capability):
                jar = http.cookiejar.CookieJar()
                opener = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(jar)
                )
                with opener.open(self.mint_url(info, capability), timeout=2.0):
                    pass
                cookie_header = "; ".join(
                    f"{cookie.name}={cookie.value}" for cookie in jar
                )
                client = socket.create_connection(
                    ("127.0.0.1", int(info["public_port"])), timeout=1.0
                )
                client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256)
                request = (
                    "GET /api/events HTTP/1.0\r\n"
                    f"Host: 127.0.0.1:{info['public_port']}\r\n"
                    f"Cookie: {cookie_header}\r\n"
                    "\r\n"
                ).encode("ascii")
                try:
                    with mock.patch(
                        "scripts.goal_progress_server.PUBLIC_EVENT_HEARTBEAT_SECONDS",
                        0.0,
                    ), mock.patch(
                        "scripts.goal_progress_server.PUBLIC_EVENT_POLL_SECONDS", 0.0
                    ):
                        client.sendall(request)
                        self.assertTrue(
                            sse_entered.wait(2.0),
                            "public handler did not enter the SSE response path",
                        )
                        started = time.monotonic()
                        accepted = request_private_json(
                            info,
                            capability,
                            "POST",
                            "/events",
                            packet_event(
                                "packet.started", sequence=2, state="running"
                            ),
                        )
                    self.assertEqual(2, accepted["accepted"]["sequence"])
                    self.assertLess(time.monotonic() - started, 1.0)
                finally:
                    client.close()
            time.sleep(0.1)
            server_error.assert_not_called()

    def test_sse_disconnect_and_slow_reader_do_not_block_private_writer(self) -> None:
        with self.running_dashboard() as (_goal_root, info, capability):
            opener, _redirects, _url = self.authenticated_opener(info, capability)
            base = f"http://127.0.0.1:{info['public_port']}"
            response = opener.open(f"{base}/api/events", timeout=2.0)
            self.assertEqual("text/event-stream; charset=utf-8", response.headers["Content-Type"])
            self.assert_security_headers(response.headers)
            self.assertEqual(b"event: state\n", response.readline())
            data_line = response.readline()
            self.assertTrue(data_line.startswith(b"data: "))
            signal_payload = json.loads(data_line.removeprefix(b"data: "))
            self.assertEqual({"sequence": 1}, signal_payload)

            started = time.monotonic()
            accepted = request_private_json(
                info,
                capability,
                "POST",
                "/events",
                packet_event("packet.started", sequence=2, state="running"),
            )
            self.assertEqual(2, accepted["accepted"]["sequence"])
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertEqual(b"\n", response.readline())
            self.assertEqual(b"event: state\n", response.readline())
            update_payload = json.loads(
                response.readline().removeprefix(b"data: ")
            )
            self.assertEqual({"sequence": 2}, update_payload)
            response.close()

            with opener.open(f"{base}/api/state", timeout=2.0) as state_response:
                state = json.loads(state_response.read().decode("utf-8"))
            self.assertEqual("running", state["state"]["goal_state"])


if __name__ == "__main__":
    unittest.main()
