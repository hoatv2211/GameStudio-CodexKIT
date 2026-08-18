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

if __name__ == "__main__":
    unittest.main()
