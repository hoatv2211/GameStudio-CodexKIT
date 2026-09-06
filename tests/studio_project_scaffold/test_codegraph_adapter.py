from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests._meta.support import temporary_directory


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    def __init__(self, result: FakeResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv: list[str], *, cwd: Path) -> FakeResult:
        self.calls.append((argv, cwd))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class CodeGraphAdapterTests(unittest.TestCase):
    def test_reports_unavailable_without_blocking_core_init(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        with temporary_directory() as temp:
            root = Path(temp)
            runner = FakeRunner(FileNotFoundError("codegraph"))

            result = inspect_codegraph(root, runner=runner)

        self.assertEqual("UNAVAILABLE", result.state)
        self.assertFalse(result.blocking)
        self.assertEqual(
            ["codegraph", "status", str(root.resolve()), "--json", "--no-color"],
            runner.calls[0][0],
        )

    def test_reports_available_not_initialized_from_structured_status(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        with temporary_directory() as temp:
            root = Path(temp)
            runner = FakeRunner(
                FakeResult(stdout=json.dumps({"initialized": False, "version": "1.5.0"}))
            )

            result = inspect_codegraph(root, runner=runner)

        self.assertEqual("AVAILABLE_NOT_INITIALIZED", result.state)
        self.assertEqual("1.5.0", result.version)
        self.assertFalse(result.blocking)

    def test_reports_healthy_stale_and_broken_initialized_states(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        healthy_payload = {
            "initialized": True,
            "version": "1.5.0",
            "pendingChanges": {"added": 0, "modified": 0, "removed": 0},
            "index": {"state": "complete", "reindexRecommended": False, "pendingRefs": 0},
        }
        stale_payload = {
            **healthy_payload,
            "pendingChanges": {"added": 1, "modified": 0, "removed": 0},
            "index": {"state": "complete", "reindexRecommended": True, "pendingRefs": 0},
        }
        broken_payload = {
            **healthy_payload,
            "index": {"state": "failed", "reindexRecommended": False, "pendingRefs": 0},
        }

        with temporary_directory() as temp:
            root = Path(temp)
            healthy = inspect_codegraph(root, runner=FakeRunner(FakeResult(stdout=json.dumps(healthy_payload))))
            stale = inspect_codegraph(root, runner=FakeRunner(FakeResult(stdout=json.dumps(stale_payload))))
            broken = inspect_codegraph(root, runner=FakeRunner(FakeResult(stdout=json.dumps(broken_payload))))

        self.assertEqual("INITIALIZED_HEALTHY", healthy.state)
        self.assertEqual("INITIALIZED_STALE", stale.state)
        self.assertEqual("INITIALIZED_BROKEN", broken.state)
        self.assertFalse(healthy.blocking)
        self.assertFalse(stale.blocking)
        self.assertFalse(broken.blocking)

    def test_legacy_status_maps_to_blocked_graph_lane_without_blocking_core_init(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        payload = {
            "initialized": True,
            "version": "1.5.0",
            "index": {"state": "stale", "reindexRecommended": True},
            "worktree": {},
        }
        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()
            legacy = inspect_codegraph(
                root,
                runner=FakeRunner(FakeResult(stdout=json.dumps(payload))),
            )
            normalized = to_code_intelligence_status(
                legacy,
                repository=root.resolve().as_posix(),
                revision="abc",
                worktree_identity="sha256:current",
                required_languages=("csharp",),
            )

        self.assertFalse(legacy.blocking)
        self.assertEqual("codegraph", normalized.provider)
        self.assertEqual("STALE_HEAD", normalized.index_state)

    def test_legacy_bridge_never_executes_payload_actions(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        action_values = (
            "powershell -Command Write-Host unsafe",
            {"argv": ["powershell", "-Command", "Write-Host unsafe"]},
            None,
            [{"action": {"argv": ["cmd", "/c", "echo unsafe"]}}],
        )
        with temporary_directory() as temp:
            root = Path(temp)
            expected_argv = [
                "codegraph",
                "status",
                str(root.resolve()),
                "--json",
                "--no-color",
            ]
            for actions in action_values:
                with self.subTest(actions=actions):
                    payload = {
                        "initialized": True,
                        "version": "1.5.0",
                        "index": {"state": "complete"},
                        "worktree": {},
                        "actions": actions,
                    }
                    runner = FakeRunner(FakeResult(stdout=json.dumps(payload)))
                    inspect_codegraph(root, runner=runner)

                    self.assertEqual(1, len(runner.calls))
                    self.assertEqual(expected_argv, runner.calls[0][0])

    def test_legacy_healthy_status_without_language_evidence_is_partial(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        payload = {
            "initialized": True,
            "version": "1.5.0",
            "revision": "abc",
            "worktreeIdentity": "sha256:current",
            "index": {"state": "complete"},
            "worktree": {},
        }
        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()
            legacy = inspect_codegraph(
                root,
                runner=FakeRunner(FakeResult(stdout=json.dumps(payload))),
            )
            normalized = to_code_intelligence_status(
                legacy,
                repository=root.resolve().as_posix(),
                revision="abc",
                worktree_identity="sha256:current",
                required_languages=("csharp",),
            )

        self.assertEqual("PARTIAL_LANGUAGE", normalized.index_state)
        self.assertEqual(("csharp",), normalized.missing_languages)

    def test_legacy_complete_identity_mismatches_fail_closed(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        cases = (
            (
                {
                    "index": {"state": "complete", "revision": "old"},
                    "worktree": {"identity": "sha256:current"},
                },
                "STALE_HEAD",
                "revision",
            ),
            (
                {
                    "index": {"state": "complete", "revision": "abc"},
                    "worktree": {"digest": "sha256:old"},
                },
                "STALE_WORKTREE",
                "worktree",
            ),
        )
        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()
            for identity_fields, expected, limitation in cases:
                with self.subTest(expected=expected):
                    payload = {
                        "initialized": True,
                        "version": "1.5.0",
                        **identity_fields,
                        "languages": ["CSharp"],
                    }
                    legacy = inspect_codegraph(
                        root,
                        runner=FakeRunner(FakeResult(stdout=json.dumps(payload))),
                    )
                    normalized = to_code_intelligence_status(
                        legacy,
                        repository=root.resolve().as_posix(),
                        revision="abc",
                        worktree_identity="sha256:current",
                        required_languages=("csharp",),
                    )

                    self.assertEqual(expected, normalized.index_state)
                    self.assertIn(
                        limitation,
                        " ".join(normalized.limitations).casefold(),
                    )

    def test_legacy_languages_normalize_or_fail_closed(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        invalid_languages = (
            "csharp",
            {"csharp": True},
            [],
            ["   "],
            ["csharp", 1],
        )
        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()
            base = {
                "initialized": True,
                "version": "1.5.0",
                "revision": "abc",
                "worktreeIdentity": "sha256:current",
                "index": {"state": "complete"},
                "worktree": {},
            }
            for languages in invalid_languages:
                with self.subTest(languages=languages):
                    legacy = inspect_codegraph(
                        root,
                        runner=FakeRunner(
                            FakeResult(stdout=json.dumps({**base, "languages": languages}))
                        ),
                    )
                    normalized = to_code_intelligence_status(
                        legacy,
                        repository=root.resolve().as_posix(),
                        revision="abc",
                        worktree_identity="sha256:current",
                        required_languages=(" CSharp ",),
                    )
                    self.assertEqual("PARTIAL_LANGUAGE", normalized.index_state)
                    self.assertEqual((), normalized.supported_languages)
                    self.assertEqual(("csharp",), normalized.missing_languages)

            valid = inspect_codegraph(
                root,
                runner=FakeRunner(
                    FakeResult(
                        stdout=json.dumps(
                            {**base, "languages": [" CSharp ", "csharp", "LUA"]}
                        )
                    )
                ),
            )
            normalized = to_code_intelligence_status(
                valid,
                repository=root.resolve().as_posix(),
                revision="abc",
                worktree_identity="sha256:current",
                required_languages=("Lua", " csharp ", "LUA"),
            )

        self.assertEqual("FRESH", normalized.index_state)
        self.assertEqual(("csharp", "lua"), normalized.supported_languages)
        self.assertEqual(("lua", "csharp"), normalized.required_languages)
        self.assertEqual((), normalized.missing_languages)

    def test_legacy_invalid_identity_types_fail_closed_without_crashing(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        cases = (
            ({"revision": ["abc"], "worktreeIdentity": "sha256:current"}, "STALE_HEAD"),
            ({"revision": "abc", "worktreeIdentity": {"digest": "sha256:current"}}, "STALE_WORKTREE"),
        )
        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()
            for identity, expected in cases:
                with self.subTest(identity=identity):
                    payload = {
                        "initialized": True,
                        "version": "1.5.0",
                        "index": {"state": "complete"},
                        "worktree": {},
                        "languages": ["csharp"],
                        **identity,
                    }
                    legacy = inspect_codegraph(
                        root,
                        runner=FakeRunner(FakeResult(stdout=json.dumps(payload))),
                    )
                    normalized = to_code_intelligence_status(
                        legacy,
                        repository=root.resolve().as_posix(),
                        revision="abc",
                        worktree_identity="sha256:current",
                        required_languages=("csharp",),
                    )

                    self.assertEqual(expected, normalized.index_state)
                    self.assertNotEqual("FRESH", normalized.index_state)

    def test_legacy_fresh_status_requires_version_and_existing_index_artifact(self) -> None:
        from scripts.codegraph_adapter import CodeGraphStatus, to_code_intelligence_status

        base = {
            "state": "INITIALIZED_HEALTHY",
            "blocking": False,
            "detail": "healthy",
            "index_ownership": "USER_OWNED",
            "status_argv": ("codegraph", "status"),
            "raw_status": {
                "revision": "abc",
                "worktreeIdentity": "sha256:current",
                "languages": ["csharp"],
            },
        }
        cases = (
            ({"version": None, "existing_index": True}, "BROKEN"),
            ({"version": "1.5.0", "existing_index": False}, "NOT_INITIALIZED"),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                normalized = to_code_intelligence_status(
                    CodeGraphStatus(**{**base, **overrides}),
                    repository="repo://game",
                    revision="abc",
                    worktree_identity="sha256:current",
                    required_languages=("csharp",),
                )

                self.assertEqual(expected, normalized.index_state)
                self.assertNotEqual("FRESH", normalized.index_state)

    def test_invalid_json_and_failed_status_are_broken_not_exceptions(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        with temporary_directory() as temp:
            root = Path(temp)
            invalid = inspect_codegraph(root, runner=FakeRunner(FakeResult(stdout="not-json")))
            failed = inspect_codegraph(
                root,
                runner=FakeRunner(FakeResult(returncode=1, stderr="database is locked")),
            )

        self.assertEqual("INITIALIZED_BROKEN", invalid.state)
        self.assertEqual("INITIALIZED_BROKEN", failed.state)
        self.assertIn("database is locked", failed.detail)

    def test_never_suggest_preference_disables_probe(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        with temporary_directory() as temp:
            root = Path(temp)
            runner = FakeRunner(AssertionError("runner must not be called"))

            result = inspect_codegraph(root, runner=runner, preference="never_suggest")

        self.assertEqual("USER_DISABLED", result.state)
        self.assertEqual([], runner.calls)
        self.assertFalse(result.blocking)

    def test_existing_index_is_always_reported_as_user_owned(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()

            result = inspect_codegraph(
                root,
                runner=FakeRunner(FileNotFoundError("codegraph")),
            )

        self.assertTrue(result.existing_index)
        self.assertEqual("USER_OWNED", result.index_ownership)
        self.assertEqual("UNAVAILABLE", result.state)

    def test_install_plan_requires_reviewer_and_has_expiry_digest_and_restore(self) -> None:
        from scripts.codegraph_adapter import create_install_plan, verify_install_plan

        now = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        with temporary_directory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                create_install_plan(root, reviewer="", now=now)

            plan = create_install_plan(root, reviewer="Tech Lead", now=now)

        self.assertEqual("CODEGRAPH_INSTALL", plan["kind"])
        self.assertEqual("Tech Lead", plan["reviewer"])
        self.assertEqual("2026-08-18T10:30:00+00:00", plan["expires_at"])
        self.assertEqual(64, len(plan["digest"]))
        self.assertIn(["codegraph", "uninit", str(root.resolve()), "--force"], plan["restore_argv"])
        verified = verify_install_plan(
            plan,
            reviewer="Tech Lead",
            digest=plan["digest"],
            now=now + timedelta(minutes=10),
        )
        self.assertEqual(plan, verified)

    def test_install_plan_preserves_existing_index_and_rejects_bad_gates(self) -> None:
        from scripts.codegraph_adapter import create_install_plan, verify_install_plan

        now = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        with temporary_directory() as temp:
            root = Path(temp)
            (root / ".codegraph").mkdir()
            plan = create_install_plan(root, reviewer="Tech Lead", now=now)

        self.assertTrue(plan["existing_index"])
        self.assertNotIn(["codegraph", "uninit", str(root.resolve()), "--force"], plan["restore_argv"])
        for reviewer, digest, verify_now in (
            ("Other", plan["digest"], now),
            ("Tech Lead", "0" * 64, now),
            ("Tech Lead", plan["digest"], now + timedelta(minutes=31)),
        ):
            with self.subTest(reviewer=reviewer, digest=digest, now=verify_now):
                with self.assertRaises(ValueError):
                    verify_install_plan(
                        plan,
                        reviewer=reviewer,
                        digest=digest,
                        now=verify_now,
                    )


    def test_preference_plan_targets_owned_state_and_preserves_unmanaged_collision(self) -> None:
        from scripts.codegraph_adapter import plan_codegraph_preference

        with temporary_directory() as temp:
            root = Path(temp)
            operation = plan_codegraph_preference(root, "skip_once")
            self.assertEqual(".agents/gamestudio-state.json", operation["path"])
            state = json.loads(operation["content"])
            self.assertEqual("skip_once", state["codegraph_advice"]["mode"])
            self.assertEqual(1, state["codegraph_advice"]["remaining_runs"])
            self.assertFalse((root / operation["path"]).exists())

            target = root / operation["path"]
            target.parent.mkdir(parents=True)
            target.write_text('{"local": true}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                plan_codegraph_preference(root, "never_suggest")

    def test_scaffold_reports_codegraph_absence_without_blocking(self) -> None:
        from scripts.project_scaffold import scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            runner = FakeRunner(FileNotFoundError("codegraph"))

            report = scaffold_project(root, codegraph_runner=runner)

        self.assertEqual("REPORT_ONLY", report["status"])
        self.assertEqual("UNAVAILABLE", report["codegraph"]["state"])
        self.assertFalse(report["codegraph"]["blocking"])

    def test_apply_install_plan_requires_verified_gates_and_uses_argv_runner(self) -> None:
        from scripts.codegraph_adapter import apply_install_plan, create_install_plan

        now = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        with temporary_directory() as temp:
            root = Path(temp)
            plan = create_install_plan(root, reviewer="Tech Lead", now=now)
            runner = FakeRunner(FakeResult())
            result = apply_install_plan(
                plan,
                reviewer="Tech Lead",
                digest=plan["digest"],
                now=now + timedelta(minutes=5),
                runner=runner,
            )

        self.assertEqual("PASS", result["status"])
        self.assertEqual([action["argv"] for action in plan["actions"]], [call[0] for call in runner.calls])
        self.assertEqual(plan["restore_argv"], result["restore_argv"])

    def test_verify_install_plan_rejects_recomputed_digest_with_noncanonical_argv(self) -> None:
        import scripts.codegraph_adapter as adapter

        now = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        with temporary_directory() as temp:
            root = Path(temp)
            plan = adapter.create_install_plan(root, reviewer="Tech Lead", now=now)
            plan["actions"][0]["argv"] = ["fake-executable", "--malicious"]
            plan["digest"] = adapter._plan_digest(plan)

        with self.assertRaisesRegex(ValueError, "canonical"):
            adapter.verify_install_plan(
                plan,
                reviewer="Tech Lead",
                digest=plan["digest"],
                now=now + timedelta(minutes=5),
            )

if __name__ == "__main__":
    unittest.main()
