from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import yaml

from tests._meta.support import (
    temporary_directory,
    write_plugin_package,
    write_registries,
    write_routing_file,
    write_skill,
)


class GovernanceTests(unittest.TestCase):
    def write_runner_status(
        self,
        evidence: Path,
        kind: str,
        skills: list[str],
        *,
        verdict: str = "PASS",
    ) -> None:
        observed_cases = max(1, len(skills) * 6)
        (evidence / f"{kind}-status.json").write_text(
            json.dumps(
                {
                    "verdict": verdict,
                    "runner": "Hermes",
                    "validation_command": f"hermes run {kind}",
                    "exit_code": 0 if verdict == "PASS" else 2,
                    "observed_cases": observed_cases if verdict == "PASS" else 0,
                    "passed": observed_cases if verdict == "PASS" else 0,
                    "pass_rate": 1.0 if verdict == "PASS" else None,
                    "unique_ids": observed_cases if verdict == "PASS" else 0,
                    "covered_skills": skills if verdict == "PASS" else [],
                    "timestamp": "2026-08-08T12:00:00+07:00",
                }
            ),
            encoding="utf-8",
        )

    def write_history(self, root: Path, entries: list[dict[str, object]]) -> Path:
        path = root / "session-history.json"
        path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        return path

    def write_dogfood_summary(self, path: Path, workflow: str, *, complete: bool = True) -> None:
        payload = {"label": "Verified", "exit_code": 0, "workflow": workflow}
        if complete:
            artifact_root = path.parent / "artifacts"
            artifact_root.mkdir(parents=True, exist_ok=True)
            artifact = artifact_root / "verdict.json"
            artifact.write_text(f"{workflow}:verified\n", encoding="utf-8")
            payload.update(
                {
                    "case_id": f"{workflow}-case",
                    "command": "hermes run governed-dogfood",
                    "artifact_root": str(artifact_root.resolve()),
                    "artifacts": [
                        {
                            "kind": "verdict",
                            "path": artifact.name,
                            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        }
                    ],
                    "project_snapshot": "game@abc123",
                    "reviewer": "QA Lead",
                    "timestamp": "2026-08-08T12:00:00+07:00",
                    "unauthorized_write": False,
                    "restore": "No mutation performed",
                }
            )
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_originality_requires_declared_provenance_for_high_overlap(self) -> None:
        from scripts.check_originality import scan_originality

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            source = Path(temp) / "source"
            skill_path = write_skill(root, "example-skill")
            source.mkdir()
            (source / "SKILL.md").write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
            report = scan_originality(root, [source], threshold=0.8)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("example-skill", report["undeclared_overlaps"][0]["skill"])

            declared_path = write_skill(
                root,
                "example-skill",
                derived_from={
                    "repo": "example/source",
                    "path": "SKILL.md",
                    "commit": "abc123",
                    "license": "MIT",
                },
            )
            source.joinpath("SKILL.md").write_text(declared_path.read_text(encoding="utf-8"), encoding="utf-8")
            report = scan_originality(root, [source], threshold=0.8)
            self.assertEqual("PASS", report["status"])

    def test_originality_is_blocked_when_no_source_content_is_available(self) -> None:
        from scripts.check_originality import scan_originality

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            write_skill(root, "example-skill")
            report = scan_originality(root, [], threshold=0.8)
            self.assertEqual("BLOCKED", report["status"])
            self.assertEqual(0, report["sources_scanned"])
            self.assertIn("source content", report["reason"])

    def test_network_and_package_policy_blocks_undeclared_dependencies(self) -> None:
        from scripts.policy_check import check_policy

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "networked.py").write_text("import requests\nrequests.get('https://example.invalid')\n", encoding="utf-8")
            (root / "policy").mkdir()
            policy = {
                "allowed_third_party_modules": ["yaml"],
                "network_access": {},
            }
            (root / "policy" / "network-package-policy.yaml").write_text(
                yaml.safe_dump(policy, sort_keys=False), encoding="utf-8"
            )
            report = check_policy(root)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(report["dependency_violations"])
            self.assertTrue(report["network_violations"])

            policy["allowed_third_party_modules"].append("requests")
            policy["network_access"] = {"scripts/networked.py": ["https://example.invalid"]}
            (root / "policy" / "network-package-policy.yaml").write_text(
                yaml.safe_dump(policy, sort_keys=False), encoding="utf-8"
            )
            self.assertEqual("PASS", check_policy(root)["status"])

    def test_policy_allows_local_script_imports_and_ignores_marker_strings(self) -> None:
        from scripts.policy_check import check_policy

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "common.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "scripts" / "tool.py").write_text(
                "try:\n    from scripts.common import VALUE\nexcept ModuleNotFoundError:\n    from common import VALUE\n",
                encoding="utf-8",
            )
            (root / "scripts" / "markers.py").write_text(
                "NETWORK_MARKERS = ('requests.', 'socket.')\n",
                encoding="utf-8",
            )
            (root / "policy").mkdir()
            (root / "policy" / "network-package-policy.yaml").write_text(
                yaml.safe_dump(
                    {"allowed_third_party_modules": ["yaml"], "network_access": {}},
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual("PASS", check_policy(root)["status"])

    def test_network_policy_rejects_dynamic_destination_without_explicit_dynamic_declaration(self) -> None:
        from scripts.policy_check import check_policy

        with temporary_directory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "dynamic_socket.py").write_text(
                "import socket\n"
                "def connect(host, port):\n"
                "    return socket.create_connection((host, port))\n",
                encoding="utf-8",
            )
            (root / "policy").mkdir()
            policy_path = root / "policy" / "network-package-policy.yaml"
            policy_path.write_text(
                yaml.safe_dump(
                    {
                        "allowed_third_party_modules": ["yaml"],
                        "network_access": {"scripts/dynamic_socket.py": []},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual("FAIL", check_policy(root)["status"])

            policy_path.write_text(
                yaml.safe_dump(
                    {
                        "allowed_third_party_modules": ["yaml"],
                        "network_access": {"scripts/dynamic_socket.py": ["dynamic://declared-at-runtime"]},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual("PASS", check_policy(root)["status"])

    def test_catalog_audit_separates_targets_from_observed_metrics(self) -> None:
        from scripts.catalog_audit import audit_catalog

        with temporary_directory() as temp:
            root = Path(temp)
            write_skill(root, "alpha-skill", description="Use when alpha unique routing behavior is required.")
            write_registries(root, ["alpha-skill"])
            write_plugin_package(root)
            write_routing_file(
                root,
                "alpha-skill",
                [
                    {"prompt": "alpha unique one", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha unique two", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha unique three", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha owner one", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha owner two", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha unique collision", "expected_skill": "alpha-skill", "type": "collision"},
                ],
            )
            (root / "evidence").mkdir()
            (root / "evidence" / "tier-b-status.json").write_text(
                json.dumps({"verdict": "BLOCKED", "reason": "runner unavailable"}), encoding="utf-8"
            )
            report = audit_catalog(root)
            self.assertIn("Do not edit manually", report["_generated"])
            self.assertEqual(1.0, report["kpis"]["routing_rank_1"]["observed"])
            self.assertEqual(0.85, report["kpis"]["routing_rank_1"]["target_mvp"])
            self.assertIsNone(report["kpis"]["unauthorized_writes"]["observed"])
            self.assertEqual("BLOCKED", report["tier_b"]["verdict"])
            self.assertEqual("BLOCKED", report["status"])
            self.assertEqual([], report["promotion_ready"])

    def test_catalog_rejects_bare_tier_b_pass_artifact(self) -> None:
        from scripts.catalog_audit import audit_catalog

        with temporary_directory() as temp:
            root = Path(temp)
            write_skill(root, "alpha-skill", description="Use when alpha unique routing behavior is required.")
            write_registries(root, ["alpha-skill"])
            write_plugin_package(root)
            write_routing_file(
                root,
                "alpha-skill",
                [
                    {"prompt": "alpha one", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha two", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha three", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha owner one", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha owner two", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha collision", "expected_skill": "alpha-skill", "type": "collision"},
                ],
            )
            evidence = root / "evidence" / "run"
            evidence.mkdir(parents=True)
            (evidence / "tier-b-status.json").write_text(
                json.dumps({"verdict": "PASS"}), encoding="utf-8"
            )
            report = audit_catalog(root)
            self.assertEqual("BLOCKED", report["tier_b"]["verdict"])
            self.assertIn("missing", " ".join(report["tier_b"].get("reasons", [])).lower())

    def test_catalog_audit_does_not_promote_from_blocked_dogfood(self) -> None:
        from scripts.catalog_audit import audit_catalog

        with temporary_directory() as temp:
            root = Path(temp)
            write_skill(root, "alpha-skill", description="Use when alpha unique routing behavior is required.")
            write_registries(root, ["alpha-skill"])
            write_plugin_package(root)
            write_routing_file(
                root,
                "alpha-skill",
                [
                    {"prompt": "alpha one", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha two", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha three", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha owner one", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha owner two", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha collision", "expected_skill": "alpha-skill", "type": "collision"},
                ],
            )
            evidence = root / "evidence" / "run"
            evidence.mkdir(parents=True)
            self.write_runner_status(evidence, "tier-b", ["alpha-skill"])
            self.write_runner_status(evidence, "behavior", ["alpha-skill"])
            self.write_runner_status(evidence, "pressure", ["alpha-skill"])
            (evidence / "dogfood-summary.json").write_text(json.dumps({"label": "BLOCKED"}), encoding="utf-8")

            report = audit_catalog(root)

            self.assertEqual([], report["promotion_ready"])
            self.assertEqual([], report["verified_dogfood_summaries"])

    def test_catalog_promotes_only_verified_workflow_with_intact_artifact(self) -> None:
        from scripts.catalog_audit import audit_catalog

        with temporary_directory() as temp:
            root = Path(temp)
            for skill in ("alpha-skill", "beta-skill"):
                write_skill(root, skill, description=f"Use when {skill} unique routing behavior is required.")
            write_registries(root, ["alpha-skill", "beta-skill"])
            write_plugin_package(root)
            for skill in ("alpha-skill", "beta-skill"):
                write_routing_file(
                    root,
                    skill,
                    [
                        {"prompt": f"{skill} one", "expected_skill": skill, "type": "positive"},
                        {"prompt": f"{skill} two", "expected_skill": skill, "type": "positive"},
                        {"prompt": f"{skill} three", "expected_skill": skill, "type": "positive"},
                        {"prompt": f"{skill} owner one", "expected_skill": skill, "type": "negative", "owner": skill},
                        {"prompt": f"{skill} owner two", "expected_skill": skill, "type": "negative", "owner": skill},
                        {"prompt": f"{skill} collision", "expected_skill": skill, "type": "collision"},
                    ],
                )
            evidence = root / "evidence" / "run"
            evidence.mkdir(parents=True)
            self.write_runner_status(evidence, "tier-b", ["alpha-skill", "beta-skill"])
            self.write_runner_status(evidence, "behavior", ["alpha-skill", "beta-skill"])
            self.write_runner_status(evidence, "pressure", ["alpha-skill", "beta-skill"])
            self.write_dogfood_summary(evidence / "dogfood-summary.json", "alpha-skill")
            history = self.write_history(
                root,
                [
                    {
                        "timestamp": "2026-08-08T12:00:00+07:00",
                        "workflow": "alpha-skill",
                        "outcome": "PASS",
                        "evidence_label": "Verified",
                        "retry_count": 0,
                        "unauthorized_write": False,
                        "manual_pattern": "",
                    }
                ],
            )

            report = audit_catalog(root, history_path=history)

            self.assertEqual(["alpha-skill"], report["promotion_ready"])

            (evidence / "artifacts" / "verdict.json").write_text(
                "changed-after-summary\n",
                encoding="utf-8",
            )
            drifted = audit_catalog(root, history_path=history)
            self.assertEqual([], drifted["verified_dogfood_summaries"])
            self.assertTrue(drifted["invalid_dogfood_summaries"])

    def test_catalog_rejects_bare_verified_dogfood_summary(self) -> None:
        from scripts.catalog_audit import audit_catalog

        with temporary_directory() as temp:
            root = Path(temp)
            write_skill(root, "alpha-skill", description="Use when alpha unique routing behavior is required.")
            write_registries(root, ["alpha-skill"])
            write_plugin_package(root)
            write_routing_file(
                root,
                "alpha-skill",
                [
                    {"prompt": "alpha one", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha two", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha three", "expected_skill": "alpha-skill", "type": "positive"},
                    {"prompt": "alpha owner one", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha owner two", "expected_skill": "alpha-skill", "type": "negative", "owner": "alpha-skill"},
                    {"prompt": "alpha collision", "expected_skill": "alpha-skill", "type": "collision"},
                ],
            )
            evidence = root / "evidence" / "run"
            evidence.mkdir(parents=True)
            for kind in ("tier-b", "behavior", "pressure"):
                self.write_runner_status(evidence, kind, ["alpha-skill"])
            (evidence / "dogfood-summary.json").write_text(
                json.dumps({"label": "Verified", "exit_code": 0, "workflow": "alpha-skill"}),
                encoding="utf-8",
            )

            report = audit_catalog(root)

            self.assertEqual([], report["promotion_ready"])
            self.assertEqual([], report["verified_dogfood_summaries"])

    def test_catalog_history_detects_repeated_manual_work_and_retry_violations(self) -> None:
        from scripts.catalog_audit import audit_session_history

        history = {
            "entries": [
                {
                    "timestamp": "2026-08-08T10:00:00+07:00",
                    "workflow": "studio-project-intake",
                    "outcome": "PASS",
                    "evidence_label": "Verified",
                    "retry_count": 4,
                    "unauthorized_write": False,
                    "manual_pattern": "rebuild-localization-copy-map",
                },
                {
                    "timestamp": "2026-08-08T11:00:00+07:00",
                    "workflow": "localization-authority-audit",
                    "outcome": "FAIL",
                    "evidence_label": "Unverified",
                    "retry_count": 0,
                    "unauthorized_write": True,
                    "manual_pattern": "rebuild-localization-copy-map",
                },
            ]
        }
        report = audit_session_history(history)
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertIn("repeated-manual-workflow", kinds)
        self.assertIn("retry-over-three", kinds)
        self.assertIn("unauthorized-write", kinds)
        self.assertEqual(0.5, report["kpis"]["pass_with_evidence"])
        self.assertEqual(1, report["kpis"]["unauthorized_writes"])
        self.assertEqual(1, report["kpis"]["retry_over_three_without_escalation"])


if __name__ == "__main__":
    unittest.main()
