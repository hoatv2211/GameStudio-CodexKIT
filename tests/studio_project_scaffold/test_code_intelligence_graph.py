from __future__ import annotations

import unittest


class CodeIntelligenceGraphDiagnosticsTests(unittest.TestCase):
    @staticmethod
    def graph() -> dict[str, object]:
        return {
            "directed": False,
            "built_at_commit": "abc123",
            "nodes": [
                {
                    "id": "caller",
                    "label": "emit()",
                    "norm_label": "emit()",
                    "_callable": True,
                    "community": 1,
                    "file_type": "code",
                    "source_file": "scripts/goal_progress.py",
                    "source_location": "L20",
                },
                {
                    "id": "goal-root",
                    "label": "GoalProgressError",
                    "norm_label": "goalprogresserror",
                    "_callable_class": True,
                    "community": 2,
                    "file_type": "code",
                    "source_file": "scripts/goal_progress_core.py",
                    "source_location": "L10",
                },
                {
                    "id": "goal-bundled",
                    "label": "GoalProgressError",
                    "norm_label": "goalprogresserror",
                    "_callable_class": True,
                    "community": 3,
                    "file_type": "code",
                    "source_file": "skills/studio-goal-progress/scripts/goal_progress_core.py",
                    "source_location": "L12",
                },
                {
                    "id": "schema-json",
                    "label": "properties",
                    "norm_label": "properties",
                    "community": 4,
                    "file_type": "code",
                    "source_file": "evals/schema/example.schema.json",
                    "source_location": "$.properties",
                },
                {
                    "id": "schema-yaml",
                    "label": "schema_version",
                    "norm_label": "schema_version",
                    "community": 5,
                    "file_type": "concept",
                    "source_file": "registry/example.yaml",
                    "source_location": "schema_version",
                },
                {
                    "id": "isolated-doc",
                    "label": "Unlinked note",
                    "norm_label": "unlinked note",
                    "community": 6,
                    "file_type": "document",
                    "source_file": "docs/note.md",
                    "source_location": "L1",
                },
            ],
            "links": [
                {
                    "source": "caller",
                    "target": "goal-root",
                    "relation": "calls",
                    "_origin": "ast",
                    "confidence": "EXTRACTED",
                    "source_file": "scripts/goal_progress.py",
                    "source_location": "L20",
                },
                {
                    "source": "caller",
                    "target": "goal-bundled",
                    "relation": "calls",
                    "_origin": "ast",
                    "confidence": "INFERRED",
                    "source_file": "scripts/goal_progress.py",
                    "source_location": "L20",
                },
                {
                    "source": "caller",
                    "target": "schema-json",
                    "relation": "contains",
                    "_origin": "ast",
                    "confidence": "EXTRACTED",
                    "source_file": "evals/schema/example.schema.json",
                    "source_location": "$.properties",
                },
                {
                    "source": "caller",
                    "target": "schema-yaml",
                    "relation": "contains",
                    "_origin": "ast",
                    "confidence": "EXTRACTED",
                    "source_file": "registry/example.yaml",
                    "source_location": "schema_version",
                },
                {
                    "source": "caller",
                    "target": "missing-node",
                    "relation": "calls",
                    "_origin": "ast",
                    "confidence": "INFERRED",
                    "source_file": "scripts/goal_progress.py",
                    "source_location": "L30",
                },
            ],
        }

    def test_recomputes_low_connectivity_with_explicit_definition(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        result = diagnose_graph_export(self.graph(), top_limit=10)

        self.assertEqual(
            "at most one distinct valid neighbor in the undirected projection",
            result["definitions"]["low_connectivity_node"],
        )
        self.assertEqual(5, result["connectivity"]["low_connectivity_node_count"])
        self.assertEqual(1, result["connectivity"]["isolated_node_count"])
        self.assertEqual(2, result["connectivity"]["component_count"])
        self.assertEqual(
            2,
            result["connectivity"]["schema_low_connectivity_node_count"],
        )
        self.assertEqual(
            {".json": 1, ".md": 1, ".py": 2, ".yaml": 1},
            result["connectivity"]["low_connectivity_by_source_suffix"],
        )

    def test_flags_ambiguous_targets_without_upgrading_inference(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        result = diagnose_graph_export(self.graph(), top_limit=10)

        identity = result["identity"]
        inference = result["inference"]
        self.assertEqual(1, identity["duplicate_callable_label_count"])
        self.assertEqual(1, identity["ambiguous_callsite_target_group_count"])
        self.assertEqual(
            ["goal-bundled", "goal-root"],
            identity["ambiguous_callsite_targets"][0]["target_ids"],
        )
        self.assertEqual(2, inference["inferred_edge_count"])
        self.assertEqual(1, inference["inferred_edges_to_duplicate_callable_labels"])
        self.assertEqual("UNVERIFIED", inference["evidence_label"])

    def test_reports_endpoint_health_and_cross_community_bridges(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        result = diagnose_graph_export(self.graph(), top_limit=10)

        self.assertEqual(1, result["integrity"]["missing_endpoint_edge_count"])
        bridge = result["bridges"]["top_cross_community_bridges"][0]
        self.assertEqual("caller", bridge["id"])
        self.assertEqual(4, bridge["external_community_count"])
        self.assertEqual(4, bridge["degree"])

    def test_subject_query_blocks_duplicate_symbol_identity(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        result = diagnose_graph_export(
            self.graph(),
            subject="GoalProgressError",
            top_limit=10,
        )

        subject = result["subject"]
        self.assertEqual("AMBIGUOUS", subject["resolution_state"])
        self.assertEqual("BLOCKED", subject["evidence_label"])
        self.assertEqual(2, subject["matched_node_count"])
        self.assertEqual(2, subject["incident_edge_count"])
        self.assertEqual(
            {"EXTRACTED": 1, "INFERRED": 1},
            subject["incident_edges_by_confidence"],
        )
        self.assertEqual(1, subject["ambiguous_callsite_target_group_count"])

    def test_subject_query_keeps_missing_symbol_uncertain(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        subject = diagnose_graph_export(
            self.graph(),
            subject="MissingSymbol",
        )["subject"]

        self.assertEqual("EMPTY_UNCERTAIN", subject["resolution_state"])
        self.assertEqual("Unverified", subject["evidence_label"])
        self.assertEqual(0, subject["matched_node_count"])

    def test_revision_binding_blocks_stale_graph_snapshot(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        result = diagnose_graph_export(
            self.graph(),
            expected_revision="def456",
        )

        self.assertEqual("abc123", result["snapshot"]["graph_revision"])
        self.assertEqual("def456", result["snapshot"]["expected_revision"])
        self.assertEqual("STALE_HEAD", result["snapshot"]["revision_state"])
        self.assertEqual("BLOCKED", result["snapshot"]["evidence_label"])
        self.assertTrue(
            any("stale" in warning.casefold() for warning in result["warnings"])
        )

    def test_rejects_duplicate_node_ids_and_ambiguous_edge_collections(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        duplicate = self.graph()
        duplicate["nodes"] = [*duplicate["nodes"], duplicate["nodes"][0]]
        with self.assertRaisesRegex(ValueError, "duplicate graph node id"):
            diagnose_graph_export(duplicate)

        ambiguous = self.graph()
        ambiguous["edges"] = []
        with self.assertRaisesRegex(ValueError, "exactly one edge collection"):
            diagnose_graph_export(ambiguous)

    def test_self_loop_does_not_inflate_connectivity(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        graph = self.graph()
        graph["nodes"] = [graph["nodes"][0]]
        graph["links"] = [
            {
                "source": "caller",
                "target": "caller",
                "relation": "calls",
                "confidence": "EXTRACTED",
            }
        ]

        result = diagnose_graph_export(graph)

        self.assertEqual(1, result["integrity"]["self_loop_edge_count"])
        self.assertEqual(1, result["connectivity"]["isolated_node_count"])
        self.assertEqual(1, result["connectivity"]["low_connectivity_node_count"])

    def test_redacts_absolute_source_paths_from_report(self) -> None:
        from scripts.code_intelligence_graph import diagnose_graph_export

        graph = self.graph()
        graph["nodes"][0]["source_file"] = "C:/private/studio/scripts/goal_progress.py"
        graph["links"][0]["source_file"] = "C:/private/studio/scripts/goal_progress.py"

        result = diagnose_graph_export(
            graph,
            subject="GoalProgressError",
            top_limit=10,
        )
        rendered = str(result)

        self.assertNotIn("C:/private/studio", rendered)
        self.assertIn("goal_progress.py", rendered)


if __name__ == "__main__":
    unittest.main()
