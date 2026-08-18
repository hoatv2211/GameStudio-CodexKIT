from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path


class PromotionEvidenceTests(unittest.TestCase):
    KIT_ROOT = Path(__file__).resolve().parents[2]
    PROFILE = "fpc-global-localization-static"

    def _write_lifecycle_artifact(
        self,
        root: Path,
        kind: str,
        *,
        skill_id: str = "localization-authority-audit",
        profile: str = PROFILE,
        runtime_targets: list[str] | None = None,
        timestamp: str = "2026-08-17T12:00:00+00:00",
        nested_timestamp: str | None = None,
    ) -> dict[str, str]:
        targets = runtime_targets or ["Codex App/CLI"]
        runtime_target = targets[0]
        source_snapshot = (
            "FlyingPhoenixChronicles@d621e4db13246d3e6e4da9eb4e1608d162b45c9e"
            "+dirty:0e96444cd494"
        )
        observed_at = nested_timestamp or timestamp
        details: dict[str, object]
        manifest_kind: str
        manifest_items: list[str]
        if kind == "tier-b":
            details = {"cases_total": 4, "cases_passed": 4, "case_ids": ["tb-1", "tb-2", "tb-3", "tb-4"]}
            manifest_kind = "case-manifest"
            manifest_items = list(details["case_ids"])
        elif kind == "behavior":
            details = {"cases_total": 10, "cases_passed": 10, "pass_rate": 1.0}
            manifest_kind = "case-manifest"
            manifest_items = [f"behavior-{index}" for index in range(10)]
        elif kind == "pressure":
            details = {"scenarios_total": 3, "scenarios_passed": 3, "pass_rate": 1.0}
            manifest_kind = "scenario-manifest"
            manifest_items = [f"pressure-{index}" for index in range(3)]
        elif kind == "runtime-matrix":
            details = {"targets": targets, "passed_targets": targets}
            manifest_kind = "runtime-manifest"
            manifest_items = list(targets)
        elif kind == "session-history":
            details = {
                "sessions_total": 5,
                "pass_with_evidence": 1.0,
                "unauthorized_writes": 0,
                "retry_over_three_without_escalation": 0,
            }
            manifest_kind = "session-manifest"
            manifest_items = [f"session-{index}" for index in range(5)]
        else:
            raise AssertionError(f"unsupported lifecycle kind: {kind}")
        bundle = root / "fpc" / kind
        bundle.mkdir(parents=True, exist_ok=True)
        command = f"python -B scripts/{kind}_eval.py --profile {profile}"
        runner_path = bundle / "runner-output.json"
        runner_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "runner-output",
                    "evidence_kind": kind,
                    "skill_id": skill_id,
                    "profile": profile,
                    "runtime_target": runtime_target,
                    "source_snapshot": source_snapshot,
                    "command": command,
                    "exit_code": 0,
                    "timestamp": observed_at,
                    "status": "PASS",
                    "details": details,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path = bundle / f"{manifest_kind}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": manifest_kind,
                    "evidence_kind": kind,
                    "skill_id": skill_id,
                    "profile": profile,
                    "source_snapshot": source_snapshot,
                    "timestamp": observed_at,
                    "items": manifest_items,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        nested_artifacts = [
            {
                "kind": "runner-output",
                "path": runner_path.name,
                "sha256": hashlib.sha256(runner_path.read_bytes()).hexdigest(),
            },
            {
                "kind": manifest_kind,
                "path": manifest_path.name,
                "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            },
        ]
        relative = f"fpc/{kind}/evidence.json"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": kind,
                    "skill_id": skill_id,
                    "profile": profile,
                    "runtime_targets": targets,
                    "runtime_target": runtime_target,
                    "verdict": "PASS",
                    "command": command,
                    "exit_code": 0,
                    "runner": "python",
                    "source_snapshot": source_snapshot,
                    "timestamp": timestamp,
                    "owner": "Localization Lead",
                    "reviewer": "QA Lead",
                    "artifacts": nested_artifacts,
                    "details": details,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "kind": kind,
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _write_strict_bundle(self, artifact_root: Path) -> Path:
        from scripts.dogfood_eval import load_cases

        bundle = artifact_root / "fpc"
        bundle.mkdir(parents=True, exist_ok=True)
        project_name = "FlyingPhoenixChronicles"
        head = "d621e4db13246d3e6e4da9eb4e1608d162b45c9e"
        dirty_digest = "0e96444cd494baf180dfdfae3890af36c0bed8080ee3ac64dbbfd36d33c4bd55"
        timestamp = "2026-08-17T12:00:00+00:00"
        snapshot = bundle / "project-snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "repository": project_name,
                    "head": head,
                    "dirty": True,
                    "dirty_digest": dirty_digest,
                    "scope_digest": "1" * 64,
                    "captured_at": timestamp,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        results = []
        for case in load_cases(self.KIT_ROOT, profile=self.PROFILE):
            command = f"python -B certify.py --case {case['id']}"
            artifacts = []
            for kind in case["required_artifacts"]:
                if kind == "project-snapshot":
                    relative = "project-snapshot.json"
                else:
                    suffix = ".txt" if kind == "report" or kind.endswith("-report") else ".json"
                    relative = f"{case['id']}/{kind}{suffix}"
                artifact = bundle / relative
                artifact.parent.mkdir(parents=True, exist_ok=True)
                if kind == "project-snapshot":
                    content = artifact.read_text(encoding="utf-8")
                elif kind == "command-log":
                    content = json.dumps(
                        {
                            "command": command,
                            "exit_code": 0,
                            "runtime_target": "Codex App/CLI",
                            "stdout": "certification completed",
                            "stderr": "",
                            "captured_at": timestamp,
                        }
                    ) + "\n"
                elif kind == "verdict":
                    content = json.dumps({"verdict": "PASS", "reason": None}) + "\n"
                elif kind == "report" or kind.endswith("-report"):
                    content = f"Verified certification report for {case['id']}.\n"
                else:
                    content = json.dumps({"case_id": case["id"], "kind": kind}) + "\n"
                artifact.write_text(content, encoding="utf-8")
                artifacts.append(
                    {
                        "kind": kind,
                        "path": relative,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                )
            results.append(
                {
                    "id": case["id"],
                    "workflow": case["workflow"],
                    "verdict": "PASS",
                    "evidence_label": "Verified",
                    "runtime_target": "Codex App/CLI",
                    "command": command,
                    "exit_code": 0,
                    "artifacts": artifacts,
                    "project_snapshot": f"{project_name}@{head}+dirty:{dirty_digest[:12]}",
                    "reviewer": "QA Lead",
                    "timestamp": "2026-08-17T12:00:00+00:00",
                    "unauthorized_write": False,
                    "restore": "Certification-only; no project mutation was performed.",
                    "reason": None,
                }
            )
        result_path = bundle / "results.json"
        result_path.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
        return result_path

    def valid_record(self, artifact_root: Path) -> dict[str, object]:
        artifact = self._write_strict_bundle(artifact_root)
        return {
            "id": "promotion-localization-authority-beta",
            "skill_id": "localization-authority-audit",
            "from_maturity": "experimental",
            "target_maturity": "beta",
            "profile": self.PROFILE,
            "case_ids": ["fpc-global-residue-authority", "fpc-localization-doctor"],
            "evidence": [
                {
                    "kind": "dogfood-result",
                    "path": "fpc/results.json",
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                }
            ],
            "owner": "Localization Lead",
            "reviewer": "QA Lead",
            "reviewed_at": "2026-08-17",
            "runtime_targets": ["Codex App/CLI"],
            "restore": "Remove the beta record and return the skill maturity to experimental.",
            "limitations": ["Unity MCP runtime case remains separate."],
            "expires_at": "2027-02-17",
        }

    def test_valid_beta_record_passes_and_hash_is_verified(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={
                    self.PROFILE: {
                        "fpc-global-residue-authority",
                        "fpc-localization-doctor",
                    }
                },
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertEqual([], errors)

    def test_skipping_maturity_level_is_rejected(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["from_maturity"] = "experimental"
            record["target_maturity"] = "release"
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("cannot skip maturity" in error for error in errors))

    def test_malformed_case_ids_returns_validation_errors_instead_of_crashing(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["case_ids"] = None
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("case_ids" in error for error in errors))

    def test_hash_drift_is_rejected(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            artifact = root / "fpc" / "results.json"
            artifact.write_text("tampered\n", encoding="utf-8")
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("hash mismatch" in error for error in errors))

    def test_non_hex_sha256_is_rejected_without_artifact_resolution(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["evidence"][0]["sha256"] = "z" * 64
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("lowercase hex" in error for error in errors))

    def test_expired_record_is_rejected(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["expires_at"] = "2026-08-16"
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("expired" in error for error in errors))

    def test_minimal_fabricated_dogfood_pass_is_rejected_by_strict_schema(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            artifact = root / "fpc" / "results.json"
            artifact.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "id": "fpc-localization-doctor",
                                "verdict": "PASS",
                                "evidence_label": "Verified",
                                "exit_code": 0,
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            record["evidence"][0]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("strict dogfood" in error for error in errors))

    def test_dogfood_result_requires_all_profile_cases_to_be_strict_pass(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            artifact = root / "fpc" / "results.json"
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            payload["results"][0]["verdict"] = "BLOCKED"
            payload["results"][0]["evidence_label"] = "BLOCKED"
            payload["results"][0]["reason"] = "Runner unavailable"
            payload["results"][0]["command"] = None
            payload["results"][0]["exit_code"] = None
            artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            record["evidence"][0]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("strict dogfood verdict is BLOCKED" in error for error in errors))

    def test_dogfood_artifacts_must_be_self_contained_below_bundle_root(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.json"
            outside.write_text('{"outside": true}\n', encoding="utf-8")
            record = self.valid_record(root)
            artifact = root / "fpc" / "results.json"
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            payload["results"][0]["artifacts"][0] = {
                "kind": payload["results"][0]["artifacts"][0]["kind"],
                "path": "../outside.json",
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
            }
            artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            record["evidence"][0]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("unsafe artifact path" in error for error in errors))

    def test_promoted_skill_must_be_selected_by_profile_promotion_scope(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["skill_id"] = "release-candidate-preflight"
            errors = validate_promotion_record(
                record,
                known_skills={"release-candidate-preflight"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("promotion_scope" in error for error in errors))

    def test_promotion_runtime_targets_must_be_observed_by_selected_cases(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["runtime_targets"] = ["Hermes Agent"]
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("runtime_targets" in error and "observed" in error for error in errors))

    def test_promotion_owners_reject_placeholders(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        for field, value in (("owner", "TODO"), ("reviewer", "N/A")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                record = self.valid_record(root)
                record[field] = value
                errors = validate_promotion_record(
                    record,
                    known_skills={"localization-authority-audit"},
                    known_profiles={self.PROFILE},
                    profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                    artifact_root=root,
                    repository_root=self.KIT_ROOT,
                )

                self.assertTrue(any(field in error and "placeholder" in error for error in errors))

    def test_promotion_restore_rejects_placeholders(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["restore"] = "TODO"
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("restore" in error and "placeholder" in error for error in errors))

    def test_promotion_rejects_future_review_and_invalid_date_order(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        cases = {
            "future-review": ("2999-01-01", "3000-01-01", "future"),
            "invalid-order": ("2026-08-17", "2026-08-17", "after reviewed_at"),
        }
        for label, (reviewed_at, expires_at, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                record = self.valid_record(root)
                record["reviewed_at"] = reviewed_at
                record["expires_at"] = expires_at
                errors = validate_promotion_record(
                    record,
                    known_skills={"localization-authority-audit"},
                    known_profiles={self.PROFILE},
                    profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                    artifact_root=root,
                    repository_root=self.KIT_ROOT,
                )

                self.assertTrue(any(expected in error for error in errors))

    def test_valid_stable_record_requires_semantic_lifecycle_evidence(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["from_maturity"] = "beta"
            record["target_maturity"] = "stable"
            record["evidence"].extend(
                self._write_lifecycle_artifact(root, kind)
                for kind in ("tier-b", "behavior", "pressure")
            )
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertEqual([], errors)

    def test_lifecycle_kind_rejects_dogfood_result_bytes_and_duplicate_binding(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["from_maturity"] = "beta"
            record["target_maturity"] = "stable"
            dogfood = record["evidence"][0]
            record["evidence"].extend(
                [
                    {
                        "kind": "tier-b",
                        "path": dogfood["path"],
                        "sha256": dogfood["sha256"],
                    },
                    self._write_lifecycle_artifact(root, "behavior"),
                    self._write_lifecycle_artifact(root, "pressure"),
                ]
            )
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        combined = " ".join(errors)
        self.assertTrue("duplicate promotion evidence path" in combined or "lifecycle" in combined)

    def test_lifecycle_summary_without_runner_provenance_is_rejected(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["from_maturity"] = "beta"
            record["target_maturity"] = "stable"
            summary_path = root / "fpc" / "tier-b-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "tier-b",
                        "skill_id": record["skill_id"],
                        "profile": record["profile"],
                        "runtime_targets": record["runtime_targets"],
                        "verdict": "PASS",
                        "timestamp": "2026-08-17T12:00:00+00:00",
                        "owner": "Localization Lead",
                        "reviewer": "QA Lead",
                        "details": {
                            "cases_total": 2,
                            "cases_passed": 2,
                            "case_ids": ["tb-1", "tb-2"],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            record["evidence"].extend(
                [
                    {
                        "kind": "tier-b",
                        "path": "fpc/tier-b-summary.json",
                        "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                    },
                    self._write_lifecycle_artifact(root, "behavior"),
                    self._write_lifecycle_artifact(root, "pressure"),
                ]
            )
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("artifacts" in error or "provenance" in error for error in errors))

    def test_lifecycle_nested_artifact_hash_and_source_binding_are_required(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        for mutation in ("hash", "source"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                record = self.valid_record(root)
                record["from_maturity"] = "beta"
                record["target_maturity"] = "stable"
                tier_b = self._write_lifecycle_artifact(root, "tier-b")
                envelope_path = root / tier_b["path"]
                envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
                if mutation == "hash":
                    runner_path = envelope_path.parent / envelope["artifacts"][0]["path"]
                    runner_path.write_text("tampered\n", encoding="utf-8")
                else:
                    envelope["source_snapshot"] = "DifferentProject@abcdef0+dirty:000000000000"
                    envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
                    tier_b["sha256"] = hashlib.sha256(envelope_path.read_bytes()).hexdigest()
                record["evidence"].extend(
                    [
                        tier_b,
                        self._write_lifecycle_artifact(root, "behavior"),
                        self._write_lifecycle_artifact(root, "pressure"),
                    ]
                )
                errors = validate_promotion_record(
                    record,
                    known_skills={"localization-authority-audit"},
                    known_profiles={self.PROFILE},
                    profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                    artifact_root=root,
                    repository_root=self.KIT_ROOT,
                )

                expected = "hash mismatch" if mutation == "hash" else "source_snapshot"
                self.assertTrue(any(expected in error for error in errors))

    def test_lifecycle_nested_timestamp_cannot_follow_review_date(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["from_maturity"] = "beta"
            record["target_maturity"] = "stable"
            record["evidence"].extend(
                [
                    self._write_lifecycle_artifact(
                        root,
                        "tier-b",
                        nested_timestamp="2026-08-18T00:00:00+00:00",
                    ),
                    self._write_lifecycle_artifact(root, "behavior"),
                    self._write_lifecycle_artifact(root, "pressure"),
                ]
            )
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("after reviewed_at" in error for error in errors))

    def test_lifecycle_case_ids_validate_element_types_before_deduplication(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            record["from_maturity"] = "beta"
            record["target_maturity"] = "stable"
            tier_b = self._write_lifecycle_artifact(root, "tier-b")
            tier_path = root / tier_b["path"]
            tier_payload = json.loads(tier_path.read_text(encoding="utf-8"))
            tier_payload["details"] = {
                "cases_total": 2,
                "cases_passed": 2,
                "case_ids": ["tb-1", {"bad": "value"}],
            }
            tier_path.write_text(json.dumps(tier_payload) + "\n", encoding="utf-8")
            tier_b["sha256"] = hashlib.sha256(tier_path.read_bytes()).hexdigest()
            record["evidence"].extend(
                [
                    tier_b,
                    self._write_lifecycle_artifact(root, "behavior"),
                    self._write_lifecycle_artifact(root, "pressure"),
                ]
            )
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("case_ids" in error for error in errors))

    def test_lifecycle_numeric_fields_reject_bools_and_impossible_ranges(self) -> None:
        from scripts.promotion_evidence import _validate_lifecycle_details

        record = {"runtime_targets": ["Codex App/CLI"]}
        cases = {
            "tier-b-passed-bool": (
                "tier-b",
                {"cases_total": 1, "cases_passed": True, "case_ids": ["tb-1"]},
            ),
            "behavior-total-bool": (
                "behavior",
                {"cases_total": True, "cases_passed": 1, "pass_rate": 1.0},
            ),
            "behavior-passed-bool": (
                "behavior",
                {"cases_total": 1, "cases_passed": True, "pass_rate": 1.0},
            ),
            "behavior-rate-bool": (
                "behavior",
                {"cases_total": 1, "cases_passed": 1, "pass_rate": True},
            ),
            "behavior-passed-over-total": (
                "behavior",
                {"cases_total": 1, "cases_passed": 2, "pass_rate": 1.0},
            ),
            "pressure-negative-total": (
                "pressure",
                {"scenarios_total": -1, "scenarios_passed": -1, "pass_rate": 1.0},
            ),
            "pressure-rate-over-one": (
                "pressure",
                {"scenarios_total": 1, "scenarios_passed": 1, "pass_rate": 1.1},
            ),
            "session-rate-bool": (
                "session-history",
                {
                    "sessions_total": 1,
                    "pass_with_evidence": True,
                    "unauthorized_writes": 0,
                    "retry_over_three_without_escalation": 0,
                },
            ),
            "session-count-bool": (
                "session-history",
                {
                    "sessions_total": 1,
                    "pass_with_evidence": 1.0,
                    "unauthorized_writes": False,
                    "retry_over_three_without_escalation": 0,
                },
            ),
            "session-negative-count": (
                "session-history",
                {
                    "sessions_total": 1,
                    "pass_with_evidence": 1.0,
                    "unauthorized_writes": 0,
                    "retry_over_three_without_escalation": -1,
                },
            ),
        }

        for name, (kind, details) in cases.items():
            with self.subTest(name=name):
                errors, _ = _validate_lifecycle_details(
                    details,
                    kind=kind,
                    record=record,
                    label=f"lifecycle evidence {kind}",
                )
                self.assertTrue(errors, name)

    def test_malformed_lifecycle_details_are_total_for_list_null_and_scalar(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        for malformed in ([], None, 7):
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                record = self.valid_record(root)
                record["from_maturity"] = "beta"
                record["target_maturity"] = "stable"
                behavior = self._write_lifecycle_artifact(root, "behavior")
                behavior_path = root / behavior["path"]
                payload = json.loads(behavior_path.read_text(encoding="utf-8"))
                payload["details"] = malformed
                behavior_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                behavior["sha256"] = hashlib.sha256(behavior_path.read_bytes()).hexdigest()
                record["evidence"].extend(
                    [
                        self._write_lifecycle_artifact(root, "tier-b"),
                        behavior,
                        self._write_lifecycle_artifact(root, "pressure"),
                    ]
                )

                errors = validate_promotion_record(
                    record,
                    known_skills={"localization-authority-audit"},
                    known_profiles={self.PROFILE},
                    profile_cases={
                        self.PROFILE: {
                            "fpc-global-residue-authority",
                            "fpc-localization-doctor",
                        }
                    },
                    artifact_root=root,
                    repository_root=self.KIT_ROOT,
                )

                self.assertTrue(any("details must be an object" in error for error in errors))

    def test_promotion_review_must_be_close_to_selected_dogfood_timestamp(self) -> None:
        from scripts.promotion_evidence import validate_promotion_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.valid_record(root)
            result_path = root / record["evidence"][0]["path"]
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            old_timestamp = "2026-08-01T12:00:00+00:00"
            for result in payload["results"]:
                result["timestamp"] = old_timestamp
                for artifact in result["artifacts"]:
                    artifact_path = result_path.parent / artifact["path"]
                    if artifact["kind"] == "command-log":
                        content = json.loads(artifact_path.read_text(encoding="utf-8"))
                        content["captured_at"] = old_timestamp
                        artifact_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
                    elif artifact["kind"] == "project-snapshot":
                        content = json.loads(artifact_path.read_text(encoding="utf-8"))
                        content["captured_at"] = old_timestamp
                        artifact_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
                    artifact["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            record["evidence"][0]["sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
            errors = validate_promotion_record(
                record,
                known_skills={"localization-authority-audit"},
                known_profiles={self.PROFILE},
                profile_cases={self.PROFILE: {"fpc-global-residue-authority", "fpc-localization-doctor"}},
                artifact_root=root,
                repository_root=self.KIT_ROOT,
            )

        self.assertTrue(any("reviewed_at" in error and "evidence" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
