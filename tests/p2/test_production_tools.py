from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


class ProductionToolTests(unittest.TestCase):
    RELEASE_NOW = dt.datetime(2026, 8, 17, 12, 0, tzinfo=dt.timezone.utc)

    def _write_release_artifact(
        self,
        root: Path,
        relative: str,
        payload: object,
    ) -> dict[str, str]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _valid_release_payload(self, root: Path) -> dict[str, object]:
        from scripts.release_preflight import REQUIRED_RELEASE_CHECKS

        candidate_id = "fpc-1.4.0-d621e4d-windows-server-42"
        primary = self._write_release_artifact(
            root,
            "build/fpc-windows-server.zip",
            {"candidate_id": candidate_id, "build_id": "windows-server-42"},
        )
        checks = []
        for check_id in sorted(REQUIRED_RELEASE_CHECKS):
            check: dict[str, object] = {
                "id": check_id,
                "candidate_id": candidate_id,
                "source_snapshot": "d621e4db13246d3e6e4da9eb4e1608d162b45c9e",
                "build_id": "windows-server-42",
                "primary_artifact_sha256": primary["sha256"],
                "status": "PASS",
                "command": f"python -B verify_{check_id}.py --candidate {candidate_id}",
                "exit_code": 0,
                "timestamp": self.RELEASE_NOW.isoformat(),
                "owner": "Release QA",
                "artifacts": [],
                "reason": None,
            }
            if check_id == "monitoring":
                check["details"] = {
                    "owner": "LiveOps Lead",
                    "signals": ["server_error_rate", "login_success_rate"],
                    "alert_routes": ["on-call-primary"],
                    "validation_command": "python -B verify_monitoring.py --dry-run",
                }
            elif check_id == "rollback":
                check["details"] = {
                    "owner": "Release Engineer",
                    "target": "fpc-1.3.3-stable",
                    "trigger": "server_error_rate > 2% for 5m",
                    "command": "restore-approved-package --target fpc-1.3.3-stable",
                    "validation_command": "python -B verify_rollback.py --target fpc-1.3.3-stable",
                }
            elif check_id == "approvals":
                check["details"] = {
                    "approvers": [
                        {
                            "name": "Release Director",
                            "role": "Release Authority",
                            "decision": "APPROVED",
                            "timestamp": self.RELEASE_NOW.isoformat(),
                        }
                    ]
                }
            artifact = self._write_release_artifact(
                root,
                f"checks/{check_id}.json",
                {
                    "schema_version": 1,
                    "candidate_id": candidate_id,
                    "candidate_version": "1.4.0",
                    "source_snapshot": check["source_snapshot"],
                    "build_id": check["build_id"],
                    "primary_artifact_sha256": check["primary_artifact_sha256"],
                    "check_id": check_id,
                    "kind": check_id,
                    "command": check["command"],
                    "exit_code": check["exit_code"],
                    "timestamp": check["timestamp"],
                    "owner": check["owner"],
                    "status": check["status"],
                    "details": check.get("details", {}),
                },
            )
            check["artifacts"] = [artifact]
            checks.append(check)
        return {
            "candidate": {
                "id": candidate_id,
                "version": "1.4.0",
                "source_snapshot": "d621e4db13246d3e6e4da9eb4e1608d162b45c9e",
                "build_id": "windows-server-42",
                "primary_artifact": primary,
            },
            "checks": checks,
            "defects": [],
            "waivers": [],
        }

    def test_performance_budget_reports_exceeded_metrics(self) -> None:
        from scripts.performance_budget import evaluate_performance_budget

        report = evaluate_performance_budget(
            {"frame_ms_p95": 20.0, "memory_mb_peak": 900},
            {"frame_ms_p95": 16.7, "memory_mb_peak": 1024},
        )
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(["frame_ms_p95"], report["violations"])
        self.assertEqual(3.3, report["metrics"]["frame_ms_p95"]["delta"])

    def test_economy_model_flags_unsustainable_positive_net_flow(self) -> None:
        from scripts.economy_model import analyze_economy

        report = analyze_economy(
            [{"name": "quests", "amount": 1200}],
            [{"name": "repairs", "amount": 700}],
            max_positive_net=100,
        )
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(500, report["net_flow"])

    def test_balance_review_flags_changes_outside_declared_bounds(self) -> None:
        from scripts.balance_review import review_balance_change

        report = review_balance_change(
            {"sword_damage": 100, "potion_price": 50},
            {"sword_damage": 140, "potion_price": 55},
            {
                "sword_damage": {"max_abs_delta": 20},
                "potion_price": {"max_abs_delta": 10},
            },
        )
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(["sword_damage"], report["out_of_bounds"])

    def test_release_preflight_blocks_empty_checks(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        report = evaluate_release_preflight({}, now=self.RELEASE_NOW)

        self.assertNotEqual("PASS", report["verdict"])
        self.assertTrue(report["schema_errors"])

    def test_release_preflight_requires_candidate_bound_hashed_fresh_evidence(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            evidence_root = Path(temp)
            payload = self._valid_release_payload(evidence_root)
            report = evaluate_release_preflight(
                payload,
                evidence_root=evidence_root,
                now=self.RELEASE_NOW,
            )

        self.assertEqual("PASS", report["verdict"])
        self.assertEqual([], report["missing_checks"])
        self.assertEqual([], report["invalid_checks"])
        self.assertEqual([], report["schema_errors"])

    def test_release_preflight_rejects_semantically_empty_placeholder_evidence(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            artifact = root / payload["checks"][0]["artifacts"][0]["path"]
            artifact.write_text("{}\n", encoding="utf-8")
            payload["checks"][0]["artifacts"][0]["sha256"] = hashlib.sha256(
                artifact.read_bytes()
            ).hexdigest()
            payload["checks"][0]["command"] = "TODO"
            report = evaluate_release_preflight(payload, evidence_root=root, now=self.RELEASE_NOW)

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("placeholder" in item for item in report["invalid_checks"]))
        self.assertTrue(any("semantically empty" in item for item in report["invalid_checks"]))

    def test_release_preflight_rejects_cross_candidate_and_hash_drift(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            payload["checks"][0]["candidate_id"] = "different-candidate"
            primary = root / payload["candidate"]["primary_artifact"]["path"]
            primary.write_text("changed after build\n", encoding="utf-8")
            report = evaluate_release_preflight(payload, evidence_root=root, now=self.RELEASE_NOW)

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("candidate" in item for item in report["invalid_checks"]))
        self.assertTrue(any("hash mismatch" in item for item in report["invalid_checks"]))

    def test_release_preflight_rejects_cross_snapshot_build_and_primary_artifact_binding(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            payload["checks"][0]["source_snapshot"] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            payload["checks"][1]["build_id"] = "windows-server-41"
            payload["checks"][2]["primary_artifact_sha256"] = "0" * 64
            report = evaluate_release_preflight(payload, evidence_root=root, now=self.RELEASE_NOW)

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("source_snapshot" in item for item in report["invalid_checks"]))
        self.assertTrue(any("build_id" in item for item in report["invalid_checks"]))
        self.assertTrue(any("primary_artifact_sha256" in item for item in report["invalid_checks"]))

    def test_release_preflight_rejects_stale_duplicate_and_missing_gates(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            payload["checks"][0]["timestamp"] = "2026-07-01T00:00:00+00:00"
            payload["checks"].append(copy.deepcopy(payload["checks"][1]))
            payload["checks"] = [
                check for check in payload["checks"] if check["id"] != "security"
            ]
            report = evaluate_release_preflight(payload, evidence_root=root, now=self.RELEASE_NOW)

        self.assertNotEqual("PASS", report["verdict"])
        self.assertIn("security", report["missing_checks"])
        self.assertTrue(report["duplicate_checks"])
        self.assertTrue(any("stale" in item for item in report["invalid_checks"]))

    def test_release_preflight_requires_actionable_monitoring_rollback_and_approvals(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        mutations = {
            "monitoring": {"owner": "LiveOps Lead", "signals": [], "alert_routes": []},
            "rollback": {"owner": "Release Engineer", "target": "", "trigger": ""},
            "approvals": {
                "approvers": [
                    {
                        "name": "",
                        "role": "Release Authority",
                        "decision": "APPROVED",
                        "timestamp": self.RELEASE_NOW.isoformat(),
                    }
                ]
            },
        }
        for check_id, details in mutations.items():
            with self.subTest(check_id=check_id), temporary_directory() as temp:
                root = Path(temp)
                payload = self._valid_release_payload(root)
                next(check for check in payload["checks"] if check["id"] == check_id)[
                    "details"
                ] = details
                report = evaluate_release_preflight(
                    payload,
                    evidence_root=root,
                    now=self.RELEASE_NOW,
                )
                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(report["schema_errors"] or report["invalid_checks"])

    def test_release_preflight_fails_blocking_defects_and_never_passes_with_waivers(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            candidate_id = payload["candidate"]["id"]
            payload["defects"] = [
                {
                    "id": "FPC-9001",
                    "candidate_id": candidate_id,
                    "severity": "P1",
                    "status": "OPEN",
                    "owner": "Backend Lead",
                    "summary": "Login service can corrupt an active session.",
                    "blocks_release": True,
                }
            ]
            payload["waivers"] = [
                {
                    "id": "waiver-fpc-9001",
                    "defect_id": "FPC-9001",
                    "candidate_id": candidate_id,
                    "approved_by": "Studio Director",
                    "reason": "Limited internal rollout only.",
                    "scope": "internal-canary",
                    "mitigation": "Disable login rollout on first error spike.",
                    "expires_at": "2026-08-18T12:00:00+00:00",
                }
            ]
            report = evaluate_release_preflight(payload, evidence_root=root, now=self.RELEASE_NOW)

        self.assertEqual("FAIL", report["verdict"])
        self.assertEqual(["FPC-9001"], report["blocking_defects"])

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            candidate_id = payload["candidate"]["id"]
            payload["waivers"] = [
                {
                    "id": "waiver-compatibility",
                    "defect_id": None,
                    "candidate_id": candidate_id,
                    "approved_by": "Studio Director",
                    "reason": "Limited internal rollout only.",
                    "scope": "internal-canary",
                    "mitigation": "Disable rollout on first error spike.",
                    "expires_at": "2026-08-18T12:00:00+00:00",
                }
            ]
            report = evaluate_release_preflight(payload, evidence_root=root, now=self.RELEASE_NOW)

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertEqual(["waiver-compatibility"], report["active_waivers"])

    def test_release_preflight_rejects_expired_or_invalid_waivers(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        for label, waiver in {
            "expired": {
                "id": "expired-waiver",
                "defect_id": None,
                "candidate_id": "replace",
                "approved_by": "Studio Director",
                "reason": "Temporary exception.",
                "scope": "internal-canary",
                "mitigation": "Disable rollout.",
                "expires_at": "2026-08-16T12:00:00+00:00",
            },
            "invalid": {
                "id": "invalid-waiver",
                "defect_id": None,
                "candidate_id": "replace",
                "approved_by": "",
                "reason": "Temporary exception.",
                "scope": "internal-canary",
                "mitigation": "Disable rollout.",
                "expires_at": "2026-08-18T12:00:00+00:00",
            },
        }.items():
            with self.subTest(label=label), temporary_directory() as temp:
                root = Path(temp)
                payload = self._valid_release_payload(root)
                waiver["candidate_id"] = payload["candidate"]["id"]
                payload["waivers"] = [waiver]
                report = evaluate_release_preflight(
                    payload,
                    evidence_root=root,
                    now=self.RELEASE_NOW,
                )
                self.assertEqual("FAIL", report["verdict"])

    def test_release_preflight_rejects_resolved_p1_p2_without_resolution_evidence(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        for severity in ("P1", "P2"):
            with self.subTest(severity=severity), temporary_directory() as temp:
                root = Path(temp)
                payload = self._valid_release_payload(root)
                payload["defects"] = [
                    {
                        "id": f"FPC-{severity}-RESOLVED",
                        "candidate_id": payload["candidate"]["id"],
                        "severity": severity,
                        "status": "RESOLVED",
                        "owner": "Backend Lead",
                        "summary": "Candidate-bound defect was resolved.",
                        "blocks_release": True,
                    }
                ]

                report = evaluate_release_preflight(
                    payload,
                    evidence_root=root,
                    now=self.RELEASE_NOW,
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(
                    report["schema_errors"]
                    or any("resolution" in item for item in report["invalid_checks"])
                )

    def test_release_preflight_validates_resolved_defect_resolution_bundle(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            candidate_id = payload["candidate"]["id"]
            defect_id = "FPC-RESOLVED-9002"
            verification_command = "python -B verify_resolution.py --defect FPC-RESOLVED-9002"
            artifact = self._write_release_artifact(
                root,
                "defects/FPC-RESOLVED-9002.json",
                {
                    "candidate_id": candidate_id,
                    "defect_id": defect_id,
                    "status": "RESOLVED",
                    "verification_command": verification_command,
                    "verification_exit_code": 0,
                },
            )
            payload["defects"] = [
                {
                    "id": defect_id,
                    "candidate_id": candidate_id,
                    "severity": "P1",
                    "status": "RESOLVED",
                    "owner": "Backend Lead",
                    "summary": "Login session corruption is fixed.",
                    "blocks_release": True,
                    "resolution": {
                        "owner": "Release QA",
                        "summary": "Regression suite confirms the corrected session transition.",
                        "resolved_at": self.RELEASE_NOW.isoformat(),
                        "verification_command": verification_command,
                        "verification_exit_code": 0,
                        "artifact": artifact,
                    },
                }
            ]

            report = evaluate_release_preflight(
                payload,
                evidence_root=root,
                now=self.RELEASE_NOW,
            )

        self.assertEqual("PASS", report["verdict"])

    def test_release_preflight_rejects_invalid_resolved_defect_resolution_semantics(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        mutations = {
            "placeholder-owner": lambda resolution, artifact_payload: resolution.update(owner="TODO"),
            "placeholder-summary": lambda resolution, artifact_payload: resolution.update(summary="N/A"),
            "future-resolved-at": lambda resolution, artifact_payload: resolution.update(resolved_at="2026-08-18T12:00:00+00:00"),
            "naive-resolved-at": lambda resolution, artifact_payload: resolution.update(resolved_at="2026-08-17T12:00:00"),
            "failed-verification": lambda resolution, artifact_payload: resolution.update(verification_exit_code=1),
            "placeholder-command": lambda resolution, artifact_payload: resolution.update(verification_command="TBD"),
            "cross-candidate-artifact": lambda resolution, artifact_payload: artifact_payload.update(candidate_id="different-candidate"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), temporary_directory() as temp:
                root = Path(temp)
                payload = self._valid_release_payload(root)
                candidate_id = payload["candidate"]["id"]
                defect_id = "FPC-RESOLVED-9003"
                verification_command = "python -B verify_resolution.py --defect FPC-RESOLVED-9003"
                artifact_payload = {
                    "candidate_id": candidate_id,
                    "defect_id": defect_id,
                    "status": "RESOLVED",
                    "verification_command": verification_command,
                    "verification_exit_code": 0,
                }
                resolution = {
                    "owner": "Release QA",
                    "summary": "Regression suite confirms the correction.",
                    "resolved_at": self.RELEASE_NOW.isoformat(),
                    "verification_command": verification_command,
                    "verification_exit_code": 0,
                }
                mutate(resolution, artifact_payload)
                artifact = self._write_release_artifact(
                    root,
                    "defects/FPC-RESOLVED-9003.json",
                    artifact_payload,
                )
                resolution["artifact"] = artifact
                payload["defects"] = [
                    {
                        "id": defect_id,
                        "candidate_id": candidate_id,
                        "severity": "P2",
                        "status": "RESOLVED",
                        "owner": "Backend Lead",
                        "summary": "Candidate-bound defect was resolved.",
                        "blocks_release": True,
                        "resolution": resolution,
                    }
                ]

                report = evaluate_release_preflight(
                    payload,
                    evidence_root=root,
                    now=self.RELEASE_NOW,
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(
                    report["schema_errors"]
                    or any("resolution" in item or "resolved_at" in item for item in report["invalid_checks"])
                )

    def test_release_preflight_rejects_placeholder_defect_metadata_for_all_statuses(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        for status in ("OPEN", "RESOLVED"):
            for field, value in (("id", "TODO"), ("owner", "N/A"), ("summary", "placeholder")):
                with self.subTest(status=status, field=field), temporary_directory() as temp:
                    root = Path(temp)
                    payload = self._valid_release_payload(root)
                    candidate_id = payload["candidate"]["id"]
                    defect = {
                        "id": "FPC-P3-9004",
                        "candidate_id": candidate_id,
                        "severity": "P3",
                        "status": status,
                        "owner": "Gameplay Lead",
                        "summary": "Non-blocking visual defect.",
                        "blocks_release": False,
                    }
                    defect[field] = value
                    payload["defects"] = [defect]

                    report = evaluate_release_preflight(
                        payload,
                        evidence_root=root,
                        now=self.RELEASE_NOW,
                    )

                    self.assertEqual("FAIL", report["verdict"])
                    self.assertTrue(
                        any(field in item and "placeholder" in item for item in report["invalid_checks"])
                    )

    def test_release_preflight_rejects_non_envelope_check_artifact(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            artifact_ref = payload["checks"][0]["artifacts"][0]
            artifact = root / artifact_ref["path"]
            artifact.write_text('{"x": 1}\n', encoding="utf-8")
            artifact_ref["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()

            report = evaluate_release_preflight(
                payload,
                evidence_root=root,
                now=self.RELEASE_NOW,
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("evidence envelope" in item for item in report["invalid_checks"]))

    def test_release_preflight_rejects_cross_check_shared_artifact_path(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            payload["checks"][1]["artifacts"] = copy.deepcopy(
                payload["checks"][0]["artifacts"]
            )

            report = evaluate_release_preflight(
                payload,
                evidence_root=root,
                now=self.RELEASE_NOW,
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("shared artifact path" in item for item in report["invalid_checks"]))

    def test_release_preflight_binds_check_metadata_to_artifact_envelope(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        with temporary_directory() as temp:
            root = Path(temp)
            payload = self._valid_release_payload(root)
            check = payload["checks"][0]
            artifact_ref = check["artifacts"][0]
            artifact = root / artifact_ref["path"]
            artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "candidate_id": "different-candidate",
                        "candidate_version": payload["candidate"]["version"],
                        "source_snapshot": check["source_snapshot"],
                        "build_id": check["build_id"],
                        "primary_artifact_sha256": check["primary_artifact_sha256"],
                        "check_id": check["id"],
                        "kind": check["id"],
                        "command": check["command"],
                        "exit_code": check["exit_code"],
                        "timestamp": check["timestamp"],
                        "owner": check["owner"],
                        "status": check["status"],
                        "details": check.get("details", {}),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            artifact_ref["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()

            report = evaluate_release_preflight(
                payload,
                evidence_root=root,
                now=self.RELEASE_NOW,
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("candidate_id" in item for item in report["invalid_checks"]))

    def test_release_envelopes_bind_the_complete_candidate_identity(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        mutations = ("version", "source_snapshot", "build_id", "primary_artifact")
        for field in mutations:
            with self.subTest(field=field), temporary_directory() as temp:
                root = Path(temp)
                payload = self._valid_release_payload(root)
                candidate = payload["candidate"]
                if field == "version":
                    candidate["version"] = "1.4.1"
                elif field == "source_snapshot":
                    candidate["source_snapshot"] = "e" * 40
                    for check in payload["checks"]:
                        check["source_snapshot"] = candidate["source_snapshot"]
                elif field == "build_id":
                    candidate["build_id"] = "windows-server-43"
                    for check in payload["checks"]:
                        check["build_id"] = candidate["build_id"]
                else:
                    candidate["primary_artifact"] = self._write_release_artifact(
                        root,
                        "build/fpc-windows-server-43.zip",
                        {
                            "candidate_id": candidate["id"],
                            "build_id": candidate["build_id"],
                            "artifact_generation": 43,
                        },
                    )
                    for check in payload["checks"]:
                        check["primary_artifact_sha256"] = candidate["primary_artifact"]["sha256"]

                report = evaluate_release_preflight(
                    payload,
                    evidence_root=root,
                    now=self.RELEASE_NOW,
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(
                    any("evidence envelope" in item for item in report["invalid_checks"])
                )

    def test_telemetry_contract_rejects_duplicate_ids_and_type_changes(self) -> None:
        from scripts.telemetry_contract import validate_telemetry_contract

        previous = [
            {
                "id": "match_end",
                "required_properties": {"duration": "integer", "result": "string"},
            }
        ]
        current = [
            {
                "id": "match_end",
                "required_properties": {"duration": "string", "result": "string"},
            },
            {"id": "match_end", "required_properties": {"duration": "string"}},
        ]
        report = validate_telemetry_contract(current, previous)
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(["match_end"], report["duplicate_event_ids"])
        self.assertIn("match_end.duration", report["type_changes"])


if __name__ == "__main__":
    unittest.main()
