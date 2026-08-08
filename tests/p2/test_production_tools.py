from __future__ import annotations

import unittest


class ProductionToolTests(unittest.TestCase):
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

    def test_release_preflight_requires_pass_and_evidence_for_every_check(self) -> None:
        from scripts.release_preflight import evaluate_release_preflight

        report = evaluate_release_preflight(
            [
                {"id": "tests", "status": "PASS", "evidence": ["test-summary.json"]},
                {"id": "build", "status": "PASS", "evidence": []},
                {"id": "store", "status": "BLOCKED", "evidence": ["store-review.md"]},
            ]
        )
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn("build", report["missing_evidence"])
        self.assertIn("store", report["blocked"])

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
