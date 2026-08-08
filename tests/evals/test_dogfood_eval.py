from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from tests._meta.support import temporary_directory


class DogfoodEvalTests(unittest.TestCase):
    def test_repository_pack_has_ten_unique_game_scenarios(self) -> None:
        from scripts.dogfood_eval import load_cases

        root = Path(__file__).resolve().parents[2]
        cases = load_cases(root)
        self.assertEqual(10, len(cases))
        self.assertEqual(10, len({case["id"] for case in cases}))
        self.assertGreaterEqual(len({case["workflow"] for case in cases}), 8)

    def test_repository_pack_matches_schema(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "evals" / "schema" / "dogfood-case.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((root / "evals" / "dogfood" / "game-studio-scenarios.json").read_text(encoding="utf-8"))
        jsonschema.validate(fixture, schema)

    def test_missing_runner_results_are_blocked(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        report = evaluate_results(root, None)
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertEqual(0, report["observed_cases"])

    def test_malformed_case_pack_is_rejected_before_runner_use(self) -> None:
        from scripts.dogfood_eval import load_cases

        with temporary_directory() as temp:
            root = Path(temp)
            fixture = root / "evals" / "dogfood" / "game-studio-scenarios.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                json.dumps({"schema_version": 1, "cases": [{"id": "broken"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_cases(root)

    def test_bare_pass_without_evidence_fails(self) -> None:
        from scripts.dogfood_eval import evaluate_results, load_cases

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            result_path = Path(temp) / "results.json"
            result_path.write_text(
                json.dumps(
                    [
                        {
                            "id": case["id"],
                            "workflow": case["workflow"],
                            "verdict": "PASS",
                        }
                        for case in load_cases(root)
                    ]
                ),
                encoding="utf-8",
            )

            report = evaluate_results(root, result_path)

            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(report["failures"])

    def test_verified_results_can_generate_catalog_summaries(self) -> None:
        from scripts.dogfood_eval import evaluate_results, load_cases, write_summaries

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            result_path = output_root / "results.json"
            results = []
            for case in load_cases(root):
                results.append(
                    {
                        "id": case["id"],
                        "workflow": case["workflow"],
                        "verdict": "PASS",
                        "evidence_label": "Verified",
                        "command": "hermes run governed-dogfood",
                        "exit_code": 0,
                        "artifacts": [
                            {"kind": kind, "path": f"artifacts/{case['id']}/{kind}.json"}
                            for kind in case["required_artifacts"]
                        ],
                        "project_snapshot": "test-project@abc123",
                        "reviewer": "QA Lead",
                        "timestamp": "2026-08-09T12:00:00+07:00",
                        "unauthorized_write": False,
                        "restore": "No mutation performed",
                    }
                )
            result_path.write_text(json.dumps(results), encoding="utf-8")

            report = evaluate_results(root, result_path)
            written = write_summaries(root, result_path, output_root / "summaries")

            self.assertEqual("PASS", report["verdict"])
            self.assertEqual(10, len(written))
            summary = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual("Verified", summary["label"])
            self.assertEqual(0, summary["exit_code"])
            self.assertTrue(summary["artifacts"])


if __name__ == "__main__":
    unittest.main()
