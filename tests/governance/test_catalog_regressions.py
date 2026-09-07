from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import catalog_audit as audit
from tests._meta.support import temporary_directory


class CatalogRegressionTests(unittest.TestCase):
    def status(self, root: Path, **changes):
        payload = dict(
            verdict="PASS",
            runner="fixture-runtime/model/high",
            validation_command="fixture evaluate",
            exit_code=0,
            observed_cases=1,
            passed=1,
            pass_rate=1.0,
            unique_ids=1,
            covered_skills=["alpha"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        if hasattr(audit, "runner_input_digest"):
            payload["input_digest"] = audit.runner_input_digest(root)
        payload.update(changes)
        return payload

    def write_status(self, root, name, payload):
        path = root / "evidence" / name / "tier-b-status.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_new_failure_is_not_hidden_by_lexically_later_old_pass(self):
        with temporary_directory() as temp:
            root = Path(temp)
            self.write_status(
                root,
                "z-old",
                self.status(
                    root,
                    timestamp=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                ),
            )
            self.write_status(
                root,
                "a-new",
                self.status(
                    root,
                    verdict="FAIL",
                    exit_code=1,
                    passed=0,
                    pass_rate=0.0,
                ),
            )
            result = audit._runner_status(root, "tier-b")
            self.assertEqual("FAIL", result["verdict"])
            self.assertEqual("evidence/a-new/tier-b-status.json", result["path"])

    def test_governed_runner_input_drift_invalidates_pass(self):
        for relative in (
            "registry/capabilities.yaml",
            "skills/alpha/SKILL.md",
            "evals/routing/alpha.json",
            "scripts/runner_eval.py",
        ):
            with self.subTest(relative=relative), temporary_directory() as temp:
                root = Path(temp)
                source = root / relative
                source.parent.mkdir(parents=True)
                source.write_text("before", encoding="utf-8")
                self.write_status(root, "run", self.status(root))
                self.assertEqual("PASS", audit._runner_status(root, "tier-b")["verdict"])
                source.write_text("after", encoding="utf-8")
                self.assertEqual("BLOCKED", audit._runner_status(root, "tier-b")["verdict"])

    def test_missing_binding_old_future_naive_and_tied_evidence_blocks(self):
        variants = [
            {"input_digest": None},
            {"timestamp": "2000-01-01T00:00:00+00:00"},
            {
                "timestamp": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat()
            },
            {"timestamp": "2026-09-06T12:00:00"},
        ]
        for changes in variants:
            with self.subTest(changes=changes), temporary_directory() as temp:
                root=Path(temp)
                self.write_status(root, "run", self.status(root, **changes))
                self.assertEqual("BLOCKED", audit._runner_status(root, "tier-b")["verdict"])
        with temporary_directory() as temp:
            root=Path(temp)
            payload = self.status(root)
            self.write_status(root, "one", payload)
            self.write_status(root, "two", payload)
            self.assertEqual("BLOCKED", audit._runner_status(root, "tier-b")["verdict"])

    def test_invalid_candidate_cannot_be_silently_skipped(self):
        with temporary_directory() as temp:
            root=Path(temp)
            self.write_status(root, "z-pass", self.status(root))
            path = self.write_status(root, "a-broken", {})
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual("BLOCKED", audit._runner_status(root, "tier-b")["verdict"])

    def test_boolean_numeric_runner_fields_never_pass(self):
        for changes in ({"exit_code": False}, {"pass_rate": True}):
            with self.subTest(changes=changes), temporary_directory() as temp:
                root = Path(temp)
                self.write_status(root, "run", self.status(root, **changes))
                self.assertEqual(
                    "BLOCKED", audit._runner_status(root, "tier-b")["verdict"]
                )

    def test_blank_runner_identity_fields_never_pass(self):
        for changes in (
            {"runner": " "},
            {"validation_command": "\t"},
            {"covered_skills": [" "]},
        ):
            with self.subTest(changes=changes), temporary_directory() as temp:
                root = Path(temp)
                self.write_status(root, "run", self.status(root, **changes))
                self.assertEqual(
                    "BLOCKED", audit._runner_status(root, "tier-b")["verdict"]
                )

    def test_history_violations_fail_catalog_even_when_other_gates_pass(self):
        # Keep real history parsing and final verdict; isolate expensive repo/dogfood discovery.
        root = Path(__file__).resolve().parents[2]
        for changes in (
            {"unauthorized_write": True},
            {"retry_count": 9},
            {"outcome": "FAIL", "evidence_label": "Unverified"},
        ):
            with self.subTest(changes=changes):
                entry = dict(
                    timestamp="2026-09-06T00:00:00+00:00",
                    workflow="review-swarm",
                    outcome="PASS",
                    evidence_label="Verified",
                    retry_count=0,
                    unauthorized_write=False,
                    manual_pattern="",
                )
                entry.update(changes)
                history = audit.audit_session_history({"entries": [entry]})
                with patch.object(audit, "_history_report", return_value=history):
                    result = audit.audit_catalog(root)
                self.assertEqual("FAIL", result["status"])

    def test_blocked_history_remains_blocked_instead_of_becoming_failure(self):
        entry = dict(
            timestamp="2026-09-06T00:00:00+00:00",
            workflow="review-swarm",
            outcome="BLOCKED",
            evidence_label="BLOCKED",
            retry_count=0,
            unauthorized_write=False,
            manual_pattern="",
        )

        result = audit.audit_session_history({"entries": [entry]})

        self.assertEqual("BLOCKED", result["status"])
        self.assertIsNone(result["kpis"]["pass_with_evidence"])

    def test_malformed_history_never_passes(self):
        for entry in (
            {},
            None,
            {
                "outcome": "PASS",
                "evidence_label": "Verified",
                "unauthorized_write": "false",
                "retry_count": False,
            },
        ):
            with self.subTest(entry=entry):
                self.assertNotEqual(
                    "PASS",
                    audit.audit_session_history({"entries": [entry]})["status"],
                )


if __name__ == "__main__":
    unittest.main()
