from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "evals" / "schema" / "code-intelligence-evidence.schema.json"
NO_GRAPH_RESULT_LIMITATION = "No graph result is not proof that no dependency exists."

VALID = {
    "schema_version": 1,
    "provider": "graphify",
    "provider_version": "0.9.50",
    "repository": "repo://game",
    "revision": "abc123",
    "worktree_identity": "sha256:worktree",
    "index_revision": "abc123",
    "index_worktree_identity": "sha256:worktree",
    "index_state": "FRESH",
    "capability": "impact",
    "query": {"query_id": "impact:TaskChangeNotify", "subjects": ["TaskChangeNotify"]},
    "resolved_subjects": ["TaskChangeNotify@Assets/Scripts/Task.cs:12"],
    "required_languages": ["csharp"],
    "supported_languages": ["csharp"],
    "missing_languages": [],
    "affected_paths": ["Assets/Scripts/TaskConsumer.cs"],
    "generated_boundaries": [],
    "edges": [
        {
            "relation": "CALLS",
            "source": "TaskConsumer::.ctor",
            "target": "TaskChangeNotify::.ctor",
            "source_locator": "Assets/Scripts/TaskConsumer.cs:20",
            "origin": "ast",
            "confidence": "EXTRACTED",
            "provenance": "SOURCE_EXTRACTED",
        }
    ],
    "query_state": "COMPLETE",
    "evidence_label": "Verified",
    "graph_verdict": "PASS",
    "source_confirmations": ["Exact source call inspected."],
    "test_confirmations": [],
    "side_effects": [],
    "limitations": ["Verified covers extraction at this snapshot, not runtime behavior."],
    "disagreements": [],
    "commands": [{"command": "provider status", "exit_code": 0}],
    "artifacts": ["evidence/local/code-intelligence/graph.json"],
    "next_action": "Confirm runtime behavior with a focused test.",
}


def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class CodeIntelligenceEvidenceSchemaTests(unittest.TestCase):
    def assert_invalid(self, payload: dict[str, object]) -> None:
        with self.assertRaises(ValidationError):
            validator().validate(payload)

    def test_valid_evidence(self) -> None:
        validator().validate(VALID)

    def test_schema_is_strict_and_requires_every_contract_field(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(VALID), schema["required"])

        additional = copy.deepcopy(VALID)
        additional["unexpected"] = True
        self.assert_invalid(additional)

        for field in VALID:
            payload = copy.deepcopy(VALID)
            del payload[field]
            with self.subTest(field=field):
                self.assert_invalid(payload)

    def test_blocked_states_require_blocked_evidence(self) -> None:
        for state in (
            "UNAVAILABLE",
            "NOT_INITIALIZED",
            "STALE_HEAD",
            "STALE_WORKTREE",
            "PARTIAL_LANGUAGE",
            "BROKEN",
            "SIDE_EFFECT_VIOLATION",
            "USER_DISABLED",
        ):
            payload = copy.deepcopy(VALID)
            payload.update(
                index_state=state,
                query_state="STATUS_BLOCKED",
                evidence_label="BLOCKED",
                graph_verdict="BLOCKED",
            )
            with self.subTest(state=state, case="valid"):
                validator().validate(payload)

            invalid_values = (
                ("query_state", "COMPLETE"),
                ("evidence_label", "Verified"),
                ("graph_verdict", "PASS"),
            )
            for field, value in invalid_values:
                invalid = copy.deepcopy(payload)
                invalid[field] = value
                with self.subTest(state=state, field=field):
                    self.assert_invalid(invalid)

    def test_empty_result_is_unverified_and_never_pass(self) -> None:
        payload = copy.deepcopy(VALID)
        payload.update(
            resolved_subjects=[],
            affected_paths=[],
            edges=[],
            query_state="EMPTY_UNCERTAIN",
            evidence_label="Unverified",
            graph_verdict="UNVERIFIED",
            limitations=[NO_GRAPH_RESULT_LIMITATION],
        )
        validator().validate(payload)

        invalid_label = copy.deepcopy(payload)
        invalid_label["evidence_label"] = "Verified"
        self.assert_invalid(invalid_label)

        invalid_verdict = copy.deepcopy(payload)
        invalid_verdict["graph_verdict"] = "PASS"
        self.assert_invalid(invalid_verdict)

    def test_inferred_edge_cannot_be_verified(self) -> None:
        payload = copy.deepcopy(VALID)
        payload["edges"][0].update(confidence="INFERRED", provenance="INFERRED")
        payload.update(evidence_label="Snapshot", graph_verdict="UNVERIFIED")
        validator().validate(payload)

        payload["evidence_label"] = "Verified"
        self.assert_invalid(payload)

    def test_non_source_provenance_cannot_be_verified_or_pass(self) -> None:
        for provenance in ("INFERRED", "SEMANTIC", "LLM", "UNKNOWN"):
            payload = copy.deepcopy(VALID)
            payload["edges"][0]["provenance"] = provenance
            payload.update(evidence_label="Snapshot", graph_verdict="UNVERIFIED")
            with self.subTest(provenance=provenance, case="snapshot"):
                validator().validate(payload)

            verified = copy.deepcopy(payload)
            verified["evidence_label"] = "Verified"
            with self.subTest(provenance=provenance, case="verified"):
                self.assert_invalid(verified)

            passing = copy.deepcopy(payload)
            passing.update(evidence_label="Verified", graph_verdict="PASS")
            with self.subTest(provenance=provenance, case="pass"):
                self.assert_invalid(passing)

    def test_partial_language_blocks_and_pass_requires_no_missing_languages(self) -> None:
        blocked = copy.deepcopy(VALID)
        blocked.update(
            required_languages=["csharp", "lua"],
            supported_languages=["csharp"],
            missing_languages=["lua"],
            index_state="PARTIAL_LANGUAGE",
            query_state="STATUS_BLOCKED",
            evidence_label="BLOCKED",
            graph_verdict="BLOCKED",
        )
        validator().validate(blocked)

        for field, value in (
            ("index_state", "FRESH"),
            ("query_state", "COMPLETE"),
            ("evidence_label", "Verified"),
            ("graph_verdict", "PASS"),
        ):
            invalid = copy.deepcopy(blocked)
            invalid[field] = value
            with self.subTest(field=field):
                self.assert_invalid(invalid)

        passing = copy.deepcopy(VALID)
        passing.update(
            required_languages=["csharp", "lua"],
            supported_languages=["csharp"],
            missing_languages=["lua"],
        )
        self.assert_invalid(passing)

    def test_pass_requires_non_null_revision_and_index_identities(self) -> None:
        for field in (
            "revision",
            "worktree_identity",
            "index_revision",
            "index_worktree_identity",
        ):
            payload = copy.deepcopy(VALID)
            payload[field] = None
            with self.subTest(field=field):
                self.assert_invalid(payload)

    def test_pass_requires_provider_version_and_artifacts(self) -> None:
        for field, value in (
            ("provider_version", None),
            ("artifacts", []),
        ):
            payload = copy.deepcopy(VALID)
            payload[field] = value
            with self.subTest(field=field):
                self.assert_invalid(payload)

    def test_semantic_validator_rejects_forged_pass_binding_and_language_coverage(self) -> None:
        from scripts.code_intelligence import validate_evidence_semantics

        invalid_payloads = (
            {**copy.deepcopy(VALID), "index_revision": "old"},
            {**copy.deepcopy(VALID), "index_worktree_identity": "sha256:old"},
            {
                **copy.deepcopy(VALID),
                "required_languages": ["csharp", "lua"],
                "supported_languages": ["csharp"],
                "missing_languages": [],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_evidence_semantics(payload)

    def test_pass_requires_exactly_one_resolved_subject(self) -> None:
        for resolved_subjects in ([], ["Foo@a.cpp:1", "Foo@b.cpp:2"]):
            payload = copy.deepcopy(VALID)
            payload["resolved_subjects"] = resolved_subjects
            with self.subTest(resolved_subjects=resolved_subjects):
                self.assert_invalid(payload)

            blocked = copy.deepcopy(payload)
            blocked.update(
                query_state="AMBIGUOUS",
                evidence_label="BLOCKED",
                graph_verdict="BLOCKED",
            )
            validator().validate(blocked)

    def test_source_test_fallback_record_is_strict_and_never_graph_pass(self) -> None:
        payload = copy.deepcopy(VALID)
        payload.update(
            index_state="PARTIAL_LANGUAGE",
            required_languages=["csharp", "lua"],
            supported_languages=["csharp"],
            missing_languages=["lua"],
            query_state="STATUS_BLOCKED",
            evidence_label="BLOCKED",
            graph_verdict="BLOCKED",
        )
        payload["source_test_fallback"] = {
            "decision": "REVIEWER_ACKNOWLEDGED_FALLBACK",
            "graph_verdict": "BLOCKED",
            "graph_blocker": "PARTIAL_LANGUAGE: lua",
            "source_owners": ["server/packet.cpp"],
            "known_callers": ["PacketRouter::dispatch"],
            "known_consumers": ["LuaPacketBridge"],
            "generated_authorities": ["tools/generate_packet.py"],
            "test_commands": ["python -B -m unittest tests.packet"],
            "reviewer": "QA Lead",
            "residual_risk": "Lua reflection remains outside graph coverage.",
            "missing_requirements": [],
        }
        try:
            validator().validate(payload)
        except ValidationError as error:
            self.fail(f"canonical evidence schema must represent fallback records: {error}")

        for field in ("known_callers", "known_consumers"):
            missing = copy.deepcopy(payload)
            missing["source_test_fallback"][field] = []
            with self.subTest(field=field, case="acknowledged"):
                self.assert_invalid(missing)

            blocked = copy.deepcopy(missing)
            blocked["source_test_fallback"].update(
                decision="BLOCKED",
                missing_requirements=[field.replace("_", " ")],
            )
            with self.subTest(field=field, case="blocked"):
                validator().validate(blocked)

        passing = copy.deepcopy(payload)
        passing["source_test_fallback"]["graph_verdict"] = "PASS"
        self.assert_invalid(passing)

        top_level_passing = copy.deepcopy(payload)
        top_level_passing.update(
            index_state="FRESH",
            missing_languages=[],
            query_state="COMPLETE",
            evidence_label="Verified",
            graph_verdict="PASS",
        )
        self.assert_invalid(top_level_passing)

        unexpected = copy.deepcopy(payload)
        unexpected["source_test_fallback"]["runtime_verdict"] = "PASS"
        self.assert_invalid(unexpected)

    def test_acknowledged_fallback_rejects_mixed_generated_authority_sentinel(self) -> None:
        payload = copy.deepcopy(VALID)
        payload.update(
            index_state="PARTIAL_LANGUAGE",
            missing_languages=["lua"],
            query_state="STATUS_BLOCKED",
            evidence_label="BLOCKED",
            graph_verdict="BLOCKED",
        )
        payload["source_test_fallback"] = {
            "decision": "REVIEWER_ACKNOWLEDGED_FALLBACK",
            "graph_verdict": "BLOCKED",
            "graph_blocker": "PARTIAL_LANGUAGE: lua",
            "source_owners": ["server/packet.cpp"],
            "known_callers": ["PacketRouter::dispatch"],
            "known_consumers": ["LuaPacketBridge"],
            "generated_authorities": ["NOT_APPLICABLE", "tools/generate_packet.py"],
            "test_commands": ["python -B -m unittest tests.packet"],
            "reviewer": "QA Lead",
            "residual_risk": "Lua reflection remains outside graph coverage.",
            "missing_requirements": [],
        }

        self.assert_invalid(payload)

    def test_runtime_blocked_fallback_with_empty_authorities_is_schema_valid(self) -> None:
        from scripts.code_intelligence import (
            evaluate_source_test_fallback,
            validate_evidence_semantics,
        )

        payload = copy.deepcopy(VALID)
        payload.update(
            index_state="PARTIAL_LANGUAGE",
            required_languages=["csharp", "lua"],
            supported_languages=["csharp"],
            missing_languages=["lua"],
            query_state="STATUS_BLOCKED",
            evidence_label="BLOCKED",
            graph_verdict="BLOCKED",
        )
        for generated_authorities in (
            (),
            ("NOT_APPLICABLE", "tools/generate_packet.py"),
        ):
            fallback = evaluate_source_test_fallback(
                graph_blocker="PARTIAL_LANGUAGE: lua",
                source_owners=("server/packet.cpp",),
                known_callers=("PacketRouter::dispatch",),
                known_consumers=("LuaPacketBridge",),
                generated_authorities=generated_authorities,
                test_commands=("python -B -m unittest tests.packet",),
                reviewer="QA Lead",
                residual_risk="Lua reflection remains outside graph coverage.",
            )
            blocked = copy.deepcopy(payload)
            blocked["source_test_fallback"] = fallback
            with self.subTest(generated_authorities=generated_authorities):
                validator().validate(blocked)
                validate_evidence_semantics(blocked)

    def test_acknowledged_fallback_rejects_reserved_sentinel_case_variants(self) -> None:
        payload = copy.deepcopy(VALID)
        payload.update(
            index_state="PARTIAL_LANGUAGE",
            missing_languages=["lua"],
            query_state="STATUS_BLOCKED",
            evidence_label="BLOCKED",
            graph_verdict="BLOCKED",
        )
        fallback = {
            "decision": "REVIEWER_ACKNOWLEDGED_FALLBACK",
            "graph_verdict": "BLOCKED",
            "graph_blocker": "PARTIAL_LANGUAGE: lua",
            "source_owners": ["server/packet.cpp"],
            "known_callers": ["PacketRouter::dispatch"],
            "known_consumers": ["LuaPacketBridge"],
            "generated_authorities": [],
            "test_commands": ["python -B -m unittest tests.packet"],
            "reviewer": "QA Lead",
            "residual_risk": "Lua reflection remains outside graph coverage.",
            "missing_requirements": [],
        }
        for generated_authorities in (
            ["not_applicable"],
            ["Not_Applicable"],
            ["not_applicable", "tools/generate_packet.py"],
            [" NOT_APPLICABLE "],
            ["\tNot_Applicable\n"],
            [" NOT_APPLICABLE ", "tools/generate_packet.py"],
        ):
            invalid = copy.deepcopy(payload)
            invalid["source_test_fallback"] = {
                **fallback,
                "generated_authorities": generated_authorities,
            }
            with self.subTest(generated_authorities=generated_authorities):
                self.assert_invalid(invalid)

    def test_legacy_declared_fresh_extracted_output_is_schema_valid_blocked(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        result = normalize_evidence(
            provider="graphify",
            provider_version="0.9.50",
            repository="repo://game",
            revision="abc123",
            index_state="FRESH",
            edge_kind="EXTRACTED",
            result={
                "resolved_subjects": ["Foo@server/foo.cpp:10"],
                "affected_paths": ["server/a.cpp"],
                "edges": [{"source": "A", "target": "B"}],
            },
        )
        errors = list(validator().iter_errors(result))
        self.assertEqual([], errors, errors[0].message if errors else "")
        self.assertEqual("BROKEN", result["index_state"])
        self.assertEqual("STATUS_BLOCKED", result["query_state"])
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_empty_arrays_force_empty_uncertain_contract(self) -> None:
        payload = copy.deepcopy(VALID)
        payload.update(
            resolved_subjects=[],
            affected_paths=[],
            edges=[],
            query_state="EMPTY_UNCERTAIN",
            evidence_label="Unverified",
            graph_verdict="UNVERIFIED",
            limitations=[NO_GRAPH_RESULT_LIMITATION],
        )
        validator().validate(payload)

        for field, value in (
            ("query_state", "COMPLETE"),
            ("evidence_label", "Verified"),
            ("graph_verdict", "PASS"),
        ):
            invalid = copy.deepcopy(payload)
            invalid[field] = value
            with self.subTest(field=field):
                self.assert_invalid(invalid)

    def test_disagreements_cannot_claim_verified_pass(self) -> None:
        for evidence_label, graph_verdict in (
            ("Snapshot", "UNVERIFIED"),
            ("Unverified", "UNVERIFIED"),
            ("BLOCKED", "BLOCKED"),
        ):
            payload = copy.deepcopy(VALID)
            payload.update(
                disagreements=["Provider output disagrees with source."],
                evidence_label=evidence_label,
                graph_verdict=graph_verdict,
            )
            with self.subTest(evidence_label=evidence_label, graph_verdict=graph_verdict):
                validator().validate(payload)

        verified = copy.deepcopy(VALID)
        verified.update(
            disagreements=["Provider output disagrees with source."],
            evidence_label="Verified",
            graph_verdict="UNVERIFIED",
        )
        self.assert_invalid(verified)

        passing = copy.deepcopy(VALID)
        passing["disagreements"] = ["Provider output disagrees with source."]
        self.assert_invalid(passing)

    def test_empty_uncertain_requires_canonical_no_result_limitation(self) -> None:
        for limitations in ([], ["A different limitation."]):
            payload = copy.deepcopy(VALID)
            payload.update(
                resolved_subjects=[],
                affected_paths=[],
                edges=[],
                query_state="EMPTY_UNCERTAIN",
                evidence_label="Unverified",
                graph_verdict="UNVERIFIED",
                limitations=limitations,
            )
            with self.subTest(limitations=limitations):
                self.assert_invalid(payload)

        valid = copy.deepcopy(VALID)
        valid.update(
            resolved_subjects=[],
            affected_paths=[],
            edges=[],
            query_state="EMPTY_UNCERTAIN",
            evidence_label="Unverified",
            graph_verdict="UNVERIFIED",
            limitations=[NO_GRAPH_RESULT_LIMITATION, "A different limitation."],
        )
        validator().validate(valid)


if __name__ == "__main__":
    unittest.main()
