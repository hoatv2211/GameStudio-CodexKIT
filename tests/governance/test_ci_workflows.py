from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


def _python_heredoc(step: dict[str, object]) -> str:
    run = str(step.get("run", ""))
    marker = "python - <<'PY'\n"
    start = run.index(marker) + len(marker)
    end = run.index("\nPY", start)
    return run[start:end]


class ContinuousIntegrationTests(unittest.TestCase):
    def test_remote_ci_mirrors_local_deterministic_gates(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = root / ".github" / "workflows" / "ci.yml"
        payload = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        self.assertIn("on", payload)
        verify = payload["jobs"]["verify"]
        self.assertEqual("${{ matrix.os }}", verify["runs-on"])
        self.assertEqual(
            ["ubuntu-latest", "windows-latest"],
            verify["strategy"]["matrix"]["os"],
        )
        setup_python = next(
            step
            for step in verify["steps"]
            if step.get("uses") == "actions/setup-python@v5"
        )
        self.assertNotIn("cache", setup_python.get("with", {}))
        run_commands = "\n".join(
            step.get("run", "")
            for job in payload["jobs"].values()
            for step in job["steps"]
        )
        for command in (
            'python -B -m unittest discover -s tests -p "test_*.py"',
            "python -B scripts/validate.py .",
            "python -B scripts/route_eval.py .",
            "python -B scripts/secret_scan.py .",
            "python -B scripts/policy_check.py .",
            "python -B scripts/external_collision_eval.py .",
            "python -B scripts/sync_skill_resources.py . --check",
            "python -B scripts/doctor.py --check --root .",
            "python -B scripts/check_originality.py .",
        ):
            self.assertIn(command, run_commands)
        originality = next(
            step
            for step in verify["steps"]
            if step.get("name") == "Originality and provenance overlap"
        )
        self.assertEqual("bash", originality.get("shell"))
        self.assertIn('if [ "$status" -eq 2 ]', run_commands)
        self.assertNotIn("check_originality.py . || true", run_commands)

    def test_nightly_exports_runner_cases_and_never_claims_model_pass(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = root / ".github" / "workflows" / "nightly.yml"
        text = workflow.read_text(encoding="utf-8")
        payload = yaml.safe_load(text)
        self.assertIn("schedule", payload["on"])
        self.assertIn("behavior_eval.py . --export behavior-cases.jsonl", text)
        self.assertIn("behavior_eval.py . --status behavior-status.json", text)
        self.assertIn("pressure_eval.py . --export pressure-cases.jsonl", text)
        self.assertIn("pressure_eval.py . --status pressure-status.json", text)
        self.assertIn("--export tier-b-cases.jsonl", text)
        self.assertIn("--status tier-b-status.json", text)
        for artifact in (
            "behavior-cases.jsonl",
            "behavior-status.json",
            "pressure-cases.jsonl",
            "pressure-status.json",
            "tier-b-cases.jsonl",
            "tier-b-status.json",
            "dogfood-cases.jsonl",
            "dogfood-status.json",
        ):
            self.assertIn(artifact, text)
        self.assertIn("dogfood_eval.py . --export dogfood-cases.jsonl", text)
        self.assertIn("dogfood_eval.py . --status dogfood-status.json", text)
        self.assertIn("if: ${{ false }}", text)
        self.assertNotIn('"verdict": "PASS"', text)

    def test_nightly_publishes_lifecycle_audits_and_has_strict_release_gate(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = root / ".github" / "workflows" / "nightly.yml"
        text = workflow.read_text(encoding="utf-8")
        payload = yaml.safe_load(text)

        dispatch = payload["on"]["workflow_dispatch"]
        self.assertIsInstance(dispatch, dict)
        release_input = dispatch["inputs"]["enforce_release_readiness"]
        self.assertEqual("boolean", release_input["type"])
        self.assertIs(False, release_input["default"])

        for command in (
            "python -B scripts/check_originality.py .",
            "python -B scripts/catalog_audit.py . --output catalog-audit.json",
        ):
            self.assertIn(command, text)
        for artifact in (
            "originality-report.json",
            "catalog-audit.json",
            "session-history-status.json",
        ):
            self.assertIn(artifact, text)

        release_job = payload["jobs"]["release-readiness"]
        self.assertEqual("offline-evals", release_job["needs"])
        self.assertIn("inputs.enforce_release_readiness", release_job["if"])
        self.assertIn("always()", release_job["if"])
        release_commands = "\n".join(
            step.get("run", "") for step in release_job["steps"]
        )
        for artifact in (
            "behavior-status.json",
            "pressure-status.json",
            "tier-b-status.json",
            "dogfood-status.json",
            "originality-report.json",
            "catalog-audit.json",
            "session-history-status.json",
        ):
            self.assertIn(artifact, release_commands)
        self.assertIn('status != "PASS"', release_commands)
        self.assertIn('status == "BLOCKED"', release_commands)
        self.assertNotIn("|| true", release_commands)

        upload = next(
            step
            for step in payload["jobs"]["offline-evals"]["steps"]
            if step.get("uses") == "actions/upload-artifact@v4"
        )
        self.assertEqual("always()", upload.get("if"))
        uploaded = {
            line.strip()
            for line in upload["with"]["path"].splitlines()
            if line.strip()
        }
        self.assertEqual(
            {
                "behavior-cases.jsonl",
                "behavior-status.json",
                "pressure-cases.jsonl",
                "pressure-status.json",
                "tier-b-cases.jsonl",
                "tier-b-status.json",
                "dogfood-cases.jsonl",
                "dogfood-status.json",
                "originality-report.json",
                "catalog-audit.json",
                "catalog-audit.stdout.json",
                "session-history-status.json",
                "lifecycle-verdict.json",
            },
            uploaded,
        )

    def test_release_gate_preserves_pass_blocked_fail_and_missing_semantics(self) -> None:
        root = Path(__file__).resolve().parents[2]
        payload = yaml.safe_load(
            (root / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8")
        )
        release_job = payload["jobs"]["release-readiness"]
        gate = next(
            step for step in release_job["steps"] if step.get("name") == "Enforce governed release readiness"
        )
        script = _python_heredoc(gate)
        report_names = (
            "behavior-status.json",
            "pressure-status.json",
            "tier-b-status.json",
            "dogfood-status.json",
            "originality-report.json",
            "catalog-audit.json",
            "session-history-status.json",
        )

        for changed_name, changed_status, expected_exit in (
            (None, None, 0),
            ("behavior-status.json", "BLOCKED", 2),
            ("pressure-status.json", "FAIL", 1),
            ("tier-b-status.json", None, 1),
        ):
            with self.subTest(status=changed_status, name=changed_name), tempfile.TemporaryDirectory() as temp:
                readiness = Path(temp) / "readiness"
                readiness.mkdir()
                for name in report_names:
                    if name == changed_name and changed_status is None:
                        continue
                    status = changed_status if name == changed_name else "PASS"
                    (readiness / name).write_text(
                        json.dumps({"status": status, "verdict": status}), encoding="utf-8"
                    )
                completed = subprocess.run(
                    [sys.executable, "-c", script], cwd=temp, check=False, capture_output=True, text=True
                )
                self.assertEqual(expected_exit, completed.returncode, completed.stdout + completed.stderr)

    def test_nightly_verdict_uploads_diagnostics_and_fails_only_real_failures(self) -> None:
        root = Path(__file__).resolve().parents[2]
        payload = yaml.safe_load(
            (root / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8")
        )
        steps = payload["jobs"]["offline-evals"]["steps"]
        matching = [
            step
            for step in steps
            if step.get("name") == "Validate lifecycle artifact completeness and scheduled verdict"
        ]
        self.assertEqual(1, len(matching))
        verdict_step = matching[0]
        self.assertEqual("always()", verdict_step.get("if"))
        script = _python_heredoc(verdict_step)
        status_names = (
            "behavior-status.json",
            "pressure-status.json",
            "tier-b-status.json",
            "dogfood-status.json",
            "originality-report.json",
            "catalog-audit.json",
            "session-history-status.json",
        )
        support_names = (
            "behavior-cases.jsonl",
            "pressure-cases.jsonl",
            "tier-b-cases.jsonl",
            "dogfood-cases.jsonl",
            "catalog-audit.stdout.json",
        )

        for changed_name, changed_status, expected_exit, expected_verdict in (
            (None, None, 0, "PASS"),
            ("behavior-status.json", "BLOCKED", 0, "BLOCKED"),
            ("pressure-status.json", "FAIL", 1, "FAIL"),
            ("tier-b-cases.jsonl", None, 1, "FAIL"),
        ):
            with self.subTest(status=changed_status, name=changed_name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                for name in support_names:
                    if name != changed_name:
                        (directory / name).write_text("{}\n", encoding="utf-8")
                for name in status_names:
                    status = changed_status if name == changed_name else "PASS"
                    (directory / name).write_text(
                        json.dumps({"status": status, "verdict": status}), encoding="utf-8"
                    )
                completed = subprocess.run(
                    [sys.executable, "-c", script], cwd=temp, check=False, capture_output=True, text=True
                )
                self.assertEqual(expected_exit, completed.returncode, completed.stdout + completed.stderr)
                verdict = json.loads((directory / "lifecycle-verdict.json").read_text(encoding="utf-8"))
                self.assertEqual(expected_verdict, verdict["status"])


if __name__ == "__main__":
    unittest.main()
