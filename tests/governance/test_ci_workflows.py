from __future__ import annotations

import unittest
from pathlib import Path

import yaml


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


if __name__ == "__main__":
    unittest.main()
