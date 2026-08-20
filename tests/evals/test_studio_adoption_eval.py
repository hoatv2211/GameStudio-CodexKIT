from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


class StudioAdoptionEvalTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def isolated_root(self, temp: str | Path) -> Path:
        root = Path(temp) / "repo"
        for relative in (
            Path("evals/adoption/studio-role-golden-paths.json"),
            Path("evals/schema/studio-adoption-result.schema.json"),
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                (self.ROOT / relative).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        return root

    def results(self, root: Path) -> dict[str, object]:
        benchmark = json.loads(
            (root / "evals" / "adoption" / "studio-role-golden-paths.json").read_text(
                encoding="utf-8"
            )
        )
        runs = []
        for index, case in enumerate(benchmark["cases"]):
            started = f"2026-08-19T10:{index:02d}:00+07:00"
            finished = f"2026-08-19T10:{index:02d}:30+07:00"
            artifact = Path("evidence/local/adoption") / f"{case['id']}.json"
            artifact_path = root / artifact
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(
                json.dumps({"case_id": case["id"], "verdict": "PASS"}),
                encoding="utf-8",
            )
            runs.append(
                {
                    "id": case["id"],
                    "selected_golden_path": case["expected_golden_path"],
                    "question_count": 1,
                    "started_at": started,
                    "verdict_at": finished,
                    "task_verdict": "PASS",
                    "dependency_failure": False,
                    "unauthorized_writes": 0,
                    "evidence_label": "Verified",
                    "reviewer": "QA Lead",
                    "artifact": artifact.as_posix(),
                    "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                }
            )
        return {"schema_version": 1, "runs": runs}

    @staticmethod
    def write_results(root: Path, payload: dict[str, object]) -> Path:
        path = root / "evidence" / "local" / "studio-adoption-results.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_without_governed_results_is_blocked(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        report = evaluate_adoption(self.ROOT)

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIsNone(report["metrics"]["routing_success_rate"])

    def test_malformed_result_files_return_governed_failures(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        with temporary_directory() as temp:
            invalid_json = Path(temp) / "invalid.json"
            invalid_json.write_text("{", encoding="utf-8")
            missing = Path(temp) / "missing.json"

            for label, path, phrase in (
                ("invalid-json", invalid_json, "invalid JSON"),
                ("missing", missing, "could not be read"),
            ):
                with self.subTest(label=label):
                    report = evaluate_adoption(self.ROOT, path)
                    self.assertEqual("FAIL", report["verdict"], report)
                    self.assertTrue(
                        any(phrase in failure for failure in report["failures"]),
                        report,
                    )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(self.ROOT / "scripts" / "studio_adoption_eval.py"),
                    str(self.ROOT),
                    "--results",
                    str(invalid_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual("", completed.stderr)
            self.assertEqual("FAIL", json.loads(completed.stdout)["verdict"])

    def test_verified_results_meet_all_targets(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        with temporary_directory() as temp:
            root = self.isolated_root(temp)
            path = self.write_results(root, self.results(root))
            report = evaluate_adoption(root, path)

        self.assertEqual("PASS", report["verdict"])
        self.assertEqual(1.0, report["metrics"]["routing_success_rate"])
        self.assertEqual(1, report["metrics"]["max_question_count"])
        self.assertEqual(0, report["metrics"]["dependency_failures"])
        self.assertEqual(0, report["metrics"]["unauthorized_writes"])
        self.assertLessEqual(report["metrics"]["onboarding_time_to_verdict_seconds"], 300)

    def test_threshold_failures_are_reported_together(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        with temporary_directory() as temp:
            root = self.isolated_root(temp)
            payload = self.results(root)
            payload["runs"][0]["selected_golden_path"] = "wrong-route"
            payload["runs"][1]["selected_golden_path"] = "wrong-route"
            payload["runs"][2]["selected_golden_path"] = "wrong-route"
            payload["runs"][0]["question_count"] = 4
            payload["runs"][0]["dependency_failure"] = True
            payload["runs"][0]["unauthorized_writes"] = 1
            onboarding = next(
                run for run in payload["runs"] if run["id"] == "install-to-first-use"
            )
            onboarding["verdict_at"] = "2026-08-19T10:10:01+07:00"
            path = self.write_results(root, payload)
            report = evaluate_adoption(root, path)

        self.assertEqual("FAIL", report["verdict"])
        joined = " ".join(report["failures"])
        self.assertIn("routing success", joined)
        self.assertIn("question count", joined)
        self.assertIn("dependency failures", joined)
        self.assertIn("unauthorized writes", joined)
        self.assertIn("install-to-first-use", joined)

    def test_result_schema_requires_substantive_hash_bound_evidence(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        for field in ("reviewer", "artifact"):
            with self.subTest(field=field), temporary_directory() as temp:
                root = self.isolated_root(temp)
                payload = self.results(root)
                payload["runs"][0][field] = " "
                path = self.write_results(root, payload)
                report = evaluate_adoption(root, path)

                self.assertEqual("FAIL", report["verdict"], report)
                self.assertIn("result schema", " ".join(report["failures"]))

    def test_benchmark_targets_drive_thresholds(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        with temporary_directory() as temp:
            root = self.isolated_root(temp)
            benchmark_path = root / "evals" / "adoption" / "studio-role-golden-paths.json"
            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
            benchmark["targets"]["max_question_count"] = 0
            benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")
            path = self.write_results(root, self.results(root))
            report = evaluate_adoption(root, path)

        self.assertEqual("FAIL", report["verdict"], report)
        self.assertIn("question count 1 exceeds 0", report["failures"])

    def test_non_pass_task_verdicts_fail_adoption(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        with temporary_directory() as temp:
            root = self.isolated_root(temp)
            payload = self.results(root)
            payload["runs"][0]["task_verdict"] = "FAIL"
            payload["runs"][1]["task_verdict"] = "BLOCKED"
            path = self.write_results(root, payload)
            report = evaluate_adoption(root, path)

        self.assertEqual("FAIL", report["verdict"], report)
        joined = " ".join(report["failures"])
        self.assertIn("task verdicts not PASS", joined)
        self.assertIn("install-to-first-use=FAIL", joined)
        self.assertIn("liveops-local-environment=BLOCKED", joined)

    def test_verified_artifacts_must_be_contained_present_and_hash_bound(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        for failure_kind, expected in (
            ("missing", "artifact file does not exist"),
            ("hash-drift", "artifact sha256 mismatch"),
            ("escape", "artifact escapes repository root"),
        ):
            with self.subTest(failure_kind=failure_kind), temporary_directory() as temp:
                root = self.isolated_root(temp)
                payload = self.results(root)
                run = payload["runs"][0]
                artifact_path = root / run["artifact"]
                if failure_kind == "missing":
                    artifact_path.unlink()
                elif failure_kind == "hash-drift":
                    artifact_path.write_text("drift", encoding="utf-8")
                else:
                    outside = root.parent / "outside.json"
                    outside.write_text("outside", encoding="utf-8")
                    run["artifact"] = "../outside.json"
                    run["artifact_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
                path = self.write_results(root, payload)
                report = evaluate_adoption(root, path)

                self.assertEqual("FAIL", report["verdict"], report)
                self.assertTrue(
                    any(expected in failure for failure in report["failures"]),
                    report,
                )

    def test_benchmark_covers_all_roles_intents_and_golden_paths(self) -> None:
        from scripts.studio_adoption_eval import load_benchmark

        benchmark = load_benchmark(self.ROOT)

        self.assertEqual({"developer", "qa", "producer", "liveops"}, {case["role"] for case in benchmark})
        self.assertEqual(
            {"diagnose", "verify", "plan-change", "ship", "handle-incident"},
            {case["intent"] for case in benchmark},
        )
        self.assertEqual(8, len({case["expected_golden_path"] for case in benchmark}))
        self.assertTrue(any("hãy" in case["prompt"].casefold() for case in benchmark))


if __name__ == "__main__":
    unittest.main()
