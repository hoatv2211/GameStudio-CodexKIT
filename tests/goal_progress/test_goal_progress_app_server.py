from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path

from tests.goal_progress.support import EPOCH_ID, GOAL_ID, THREAD_ID


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SUPPORTED_FIXTURE = FIXTURE_DIR / "app-server-supported.jsonl"
UNKNOWN_FIXTURE = FIXTURE_DIR / "app-server-unknown.jsonl"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class GoalProgressAppServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_server = importlib.import_module("scripts.goal_progress_app_server")

    def make_binding(self, *, transport: object | None) -> dict[str, object]:
        binding: dict[str, object] = {
            "goal_id": GOAL_ID,
            "plan_version": 1,
            "writer_epoch_id": EPOCH_ID,
            "thread_id": THREAD_ID,
        }
        if transport is not None:
            binding["transport"] = transport
        return binding

    def initialized_transport(self) -> dict[str, object]:
        return {
            "kind": "codex_app_server",
            "id": "transport-demo",
            "initialized": True,
        }

    def test_build_initialize_request_uses_canonical_client_identity(self) -> None:
        request = self.app_server.build_initialize_request(7, "0.9.0")

        self.assertEqual("2.0", request["jsonrpc"])
        self.assertEqual(7, request["id"])
        self.assertEqual("initialize", request["method"])

        params = request["params"]
        self.assertEqual(
            {
                "name": "gamestudio_codexkit",
                "title": "GameStudio-CodexKIT Goal Progress",
                "version": "0.9.0",
            },
            params["clientInfo"],
        )
        self.assertNotIn("experimentalApi", params.get("capabilities", {}))

    def test_build_initialized_notification_is_notification_only(self) -> None:
        notification = self.app_server.build_initialized_notification()

        self.assertEqual("2.0", notification["jsonrpc"])
        self.assertNotIn("id", notification)
        self.assertEqual("initialized", notification["method"])
        self.assertEqual({}, notification["params"])

    def test_normalize_supported_notifications_are_informational_only(self) -> None:
        self.assertTrue(SUPPORTED_FIXTURE.exists(), f"missing fixture: {SUPPORTED_FIXTURE}")
        binding = self.make_binding(transport=self.initialized_transport())
        seen_methods: list[str] = []

        for message in load_jsonl(SUPPORTED_FIXTURE):
            normalized = self.app_server.normalize_notification(message, binding)
            self.assertGreaterEqual(len(normalized), 1, message)
            seen_methods.append(message["method"])

            for candidate in normalized:
                self.assertEqual("codex_app_server", candidate["source"])
                self.assertTrue(candidate["informational"])
                self.assertIsNone(candidate["authority"])
                self.assertNotEqual("packet.verified", candidate["event_type"])
                self.assertIn("summary", candidate)
                self.assertNotIn("secret payload 123", json.dumps(candidate))

        self.assertIn("item/completed", seen_methods)

    def test_consume_notifications_without_transport_blocks_desktop_thread_only_calls(self) -> None:
        status_binding = self.make_binding(transport=None)

        candidates, status = self.app_server.consume_notifications(
            [],
            status_binding,
            runtime_version="codex-2026.09.04",
        )

        self.assertEqual([], candidates)
        self.assertEqual(
            {
                "status": "BLOCKED",
                "reason": "desktop_transport_unavailable",
                "portable_progress_available": True,
            },
            status,
        )

    def test_consume_notifications_keeps_prior_candidates_then_blocks_on_unknown_shapes(self) -> None:
        self.assertTrue(UNKNOWN_FIXTURE.exists(), f"missing fixture: {UNKNOWN_FIXTURE}")
        binding = self.make_binding(transport=self.initialized_transport())

        candidates, status = self.app_server.consume_notifications(
            UNKNOWN_FIXTURE.read_text(encoding="utf-8").splitlines(),
            binding,
            runtime_version="codex-2026.09.04",
        )

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual("codex_app_server", candidates[0]["source"])
        self.assertIsNone(candidates[0]["authority"])
        self.assertNotEqual("packet.verified", candidates[0]["event_type"])
        self.assertEqual("BLOCKED", status["status"])
        self.assertEqual("unsupported_app_server_message", status["reason"])
        self.assertEqual("codex-2026.09.04", status["runtime_version"])
        self.assertEqual(["thread/started"], status["recognized_methods"])
        self.assertTrue(status["portable_progress_available"])

    def test_normalize_accepts_current_allowlisted_optional_fields(self) -> None:
        binding = self.make_binding(transport=self.initialized_transport())
        messages = [
            {
                "jsonrpc": "2.0",
                "method": "warning",
                "params": {"message": "A warning", "threadId": THREAD_ID},
            },
            {
                "jsonrpc": "2.0",
                "method": "configWarning",
                "params": {"summary": "A config warning", "details": "secret payload 123"},
            },
        ]

        for message in messages:
            with self.subTest(method=message["method"]):
                candidates = self.app_server.normalize_notification(message, binding)
                self.assertEqual(1, len(candidates))
                self.assertTrue(candidates[0]["informational"])
                self.assertNotIn("secret payload 123", json.dumps(candidates))

    def test_consume_notifications_rejects_invalid_present_transport_bindings(self) -> None:
        invalid_transports = {
            "uninitialized": {
                "kind": "codex_app_server",
                "id": "transport-demo",
                "initialized": False,
            },
            "opaque": object(),
            "unknown-field": {
                "kind": "codex_app_server",
                "id": "transport-demo",
                "initialized": True,
                "extra": True,
            },
            "invalid-identity": {
                "kind": "codex_app_server",
                "id": " ",
                "initialized": True,
            },
        }
        valid_line = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "warning",
                "params": {"message": "must not be consumed"},
            }
        )

        for label, transport in invalid_transports.items():
            with self.subTest(label=label):
                candidates, status = self.app_server.consume_notifications(
                    [valid_line],
                    self.make_binding(transport=transport),
                    runtime_version="codex-2026.09.04",
                )
                self.assertEqual([], candidates)
                self.assertEqual(
                    {
                        "status": "BLOCKED",
                        "reason": "desktop_transport_unavailable",
                        "portable_progress_available": True,
                    },
                    status,
                )


if __name__ == "__main__":
    unittest.main()
