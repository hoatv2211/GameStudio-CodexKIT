from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
TASK_PACKET_SCHEMA = ROOT / "evals" / "schema" / "studio-task-packet.schema.json"
EVIDENCE_CARD_SCHEMA = ROOT / "evals" / "schema" / "studio-evidence-card.schema.json"

VALID_TASK_PACKET = {
    "schema_version": 1,
    "status": "READY",
    "role": "developer",
    "intent": "diagnose",
    "mode": "basic",
    "golden_path": "unity-client-entry-recovery",
    "selected_workflow": "unity-client-offline-debugging",
    "candidates": ["unity-client-entry-recovery"],
    "workflow_candidates": ["unity-client-offline-debugging"],
    "questions": [],
    "risk_level": "read-only",
    "prerequisites": [],
    "next_action": "Run the selected workflow read-only.",
}

VALID_EVIDENCE_CARD = {
    "schema_version": 1,
    "verdict": "BLOCKED",
    "workflow": "unity-client-offline-debugging",
    "verified": [],
    "snapshot": ["Unity project profile selected"],
    "unverified": [],
    "blocked": ["Unity Editor is unavailable"],
    "commands": [],
    "artifacts": [],
    "restore": None,
    "next_action": "Open the project in the supported Unity Editor version.",
}


def load_validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class StudioTaskPacketSchemaTests(unittest.TestCase):
    def assert_invalid(self, payload: dict[str, object]) -> None:
        with self.assertRaises(ValidationError):
            load_validator(TASK_PACKET_SCHEMA).validate(payload)

    def test_valid_task_packet(self) -> None:
        load_validator(TASK_PACKET_SCHEMA).validate(VALID_TASK_PACKET)

    def test_metadata_and_required_fields_are_exact(self) -> None:
        schema = json.loads(TASK_PACKET_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/studio-task-packet.schema.json",
            schema["$id"],
        )
        self.assertEqual("GameStudio role-aware task packet", schema["title"])
        self.assertEqual(list(VALID_TASK_PACKET), schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_required_fields_additional_properties_and_enums_are_strict(self) -> None:
        cases = []
        missing = copy.deepcopy(VALID_TASK_PACKET)
        del missing["next_action"]
        cases.append(missing)
        additional = copy.deepcopy(VALID_TASK_PACKET)
        additional["unexpected"] = True
        cases.append(additional)
        for field, invalid_value in (
            ("status", "PASS"),
            ("role", "designer"),
            ("intent", "implement"),
            ("mode", "expert"),
            ("risk_level", "critical"),
        ):
            payload = copy.deepcopy(VALID_TASK_PACKET)
            payload[field] = invalid_value
            cases.append(payload)

        for payload in cases:
            with self.subTest(payload=payload):
                self.assert_invalid(payload)

    def test_ready_requires_selected_kebab_case_identifiers_candidates_and_no_question(self) -> None:
        for field in ("golden_path", "selected_workflow"):
            nullable = copy.deepcopy(VALID_TASK_PACKET)
            nullable[field] = None
            with self.subTest(field=field, value=None):
                self.assert_invalid(nullable)

            invalid = copy.deepcopy(VALID_TASK_PACKET)
            invalid[field] = "Unity_Client"
            with self.subTest(field=field, value="Unity_Client"):
                self.assert_invalid(invalid)

        for field, value in (
            ("candidates", []),
            ("candidates", ["unity-client-entry-recovery", "project-adoption-routing"]),
            (
                "workflow_candidates",
                ["unity-client-offline-debugging", "review-swarm"],
            ),
            ("questions", ["Which workflow should run?"]),
            ("prerequisites", ["A required dependency is unavailable."]),
        ):
            payload = copy.deepcopy(VALID_TASK_PACKET)
            payload[field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)

    def test_ambiguous_requires_exactly_two_candidates_one_question_and_null_selection(self) -> None:
        ambiguous = copy.deepcopy(VALID_TASK_PACKET)
        ambiguous.update(
            status="AMBIGUOUS",
            golden_path=None,
            selected_workflow=None,
            candidates=["cpp-server-failure-recovery", "local-environment-recovery"],
            workflow_candidates=[
                "cpp-server-crash-triage",
                "multi-service-local-environment-doctor",
            ],
            questions=["Is this an environment failure or a server crash?"],
        )
        load_validator(TASK_PACKET_SCHEMA).validate(ambiguous)

        for field, value in (
            ("golden_path", "cpp-server-failure-recovery"),
            ("selected_workflow", "cpp-server-crash-triage"),
            ("candidates", ["cpp-server-failure-recovery"]),
            (
                "candidates",
                [
                    "cpp-server-failure-recovery",
                    "local-environment-recovery",
                    "unity-client-entry-recovery",
                ],
            ),
            ("questions", []),
            ("questions", ["First?", "Second?"]),
            ("prerequisites", ["A required dependency is unavailable."]),
        ):
            payload = copy.deepcopy(ambiguous)
            payload[field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)

    def test_ambiguous_workflow_form_allows_one_family_and_two_workflows(self) -> None:
        ambiguous = copy.deepcopy(VALID_TASK_PACKET)
        ambiguous.update(
            status="AMBIGUOUS",
            golden_path="unity-ui-localization",
            selected_workflow=None,
            candidates=["unity-ui-localization"],
            workflow_candidates=[
                "localization-authority-audit",
                "unity-ui-rendering-debugging",
            ],
            questions=["Which workflow should run?"],
            prerequisites=[],
        )
        load_validator(TASK_PACKET_SCHEMA).validate(ambiguous)

        for field, value in (
            ("golden_path", None),
            ("candidates", ["unity-ui-localization", "project-adoption-routing"]),
            ("workflow_candidates", ["unity-ui-rendering-debugging"]),
            ("questions", []),
        ):
            payload = copy.deepcopy(ambiguous)
            payload[field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)

    def test_blocked_requires_prerequisite_null_workflow_and_no_question(self) -> None:
        blocked = copy.deepcopy(VALID_TASK_PACKET)
        blocked.update(
            status="BLOCKED",
            golden_path="unity-client-entry-recovery",
            selected_workflow=None,
            candidates=["unity-client-entry-recovery"],
            questions=[],
            prerequisites=["Required workflow is not installed."],
        )
        validator = load_validator(TASK_PACKET_SCHEMA)
        validator.validate(blocked)

        without_path = copy.deepcopy(blocked)
        without_path["golden_path"] = None
        validator.validate(without_path)

        for field, value in (
            ("selected_workflow", "unity-client-offline-debugging"),
            ("questions", ["Should this continue?"]),
            ("prerequisites", []),
        ):
            payload = copy.deepcopy(blocked)
            payload[field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)

    def test_candidate_question_and_prerequisite_constraints_are_strict(self) -> None:
        invalid_values = (
            ("candidates", ["duplicate", "duplicate"]),
            ("candidates", ["Not-Kebab"]),
            ("workflow_candidates", ["duplicate", "duplicate"]),
            ("workflow_candidates", ["Not-Kebab"]),
            ("workflow_candidates", [""]),
            ("questions", ["one", "two"]),
            ("questions", [""]),
            ("prerequisites", ["duplicate", "duplicate"]),
            ("prerequisites", [""]),
        )
        for field, value in invalid_values:
            payload = copy.deepcopy(VALID_TASK_PACKET)
            payload[field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)

    def test_meaningful_text_fields_reject_whitespace_only_strings(self) -> None:
        for field in ("questions", "prerequisites"):
            payload = copy.deepcopy(VALID_TASK_PACKET)
            payload[field] = [" \t"]
            with self.subTest(field=field):
                self.assert_invalid(payload)

        payload = copy.deepcopy(VALID_TASK_PACKET)
        payload["next_action"] = " \t"
        with self.subTest(field="next_action"):
            self.assert_invalid(payload)


class StudioEvidenceCardSchemaTests(unittest.TestCase):
    def assert_invalid(self, payload: dict[str, object]) -> None:
        with self.assertRaises(ValidationError):
            load_validator(EVIDENCE_CARD_SCHEMA).validate(payload)

    def test_valid_evidence_card(self) -> None:
        load_validator(EVIDENCE_CARD_SCHEMA).validate(VALID_EVIDENCE_CARD)

    def test_metadata_and_required_fields_are_exact(self) -> None:
        schema = json.loads(EVIDENCE_CARD_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(
            "https://gamestudio-codexkit.local/schema/studio-evidence-card.schema.json",
            schema["$id"],
        )
        self.assertEqual("GameStudio normalized evidence card", schema["title"])
        self.assertEqual(list(VALID_EVIDENCE_CARD), schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_required_fields_additional_properties_and_verdict_are_strict(self) -> None:
        missing = copy.deepcopy(VALID_EVIDENCE_CARD)
        del missing["workflow"]
        self.assert_invalid(missing)

        additional = copy.deepcopy(VALID_EVIDENCE_CARD)
        additional["unexpected"] = True
        self.assert_invalid(additional)

        invalid_verdict = copy.deepcopy(VALID_EVIDENCE_CARD)
        invalid_verdict["verdict"] = "READY"
        self.assert_invalid(invalid_verdict)

    def test_workflow_and_evidence_array_items_are_strict(self) -> None:
        invalid_workflow = copy.deepcopy(VALID_EVIDENCE_CARD)
        invalid_workflow["workflow"] = "Unity_Client"
        self.assert_invalid(invalid_workflow)

        for field in ("verified", "snapshot", "unverified", "blocked", "artifacts"):
            payload = copy.deepcopy(VALID_EVIDENCE_CARD)
            payload[field] = [""]
            with self.subTest(field=field):
                self.assert_invalid(payload)

    def test_command_objects_are_strict(self) -> None:
        valid = copy.deepcopy(VALID_EVIDENCE_CARD)
        valid["commands"] = [
            {"command": "python -B scripts/validate.py .", "exit_code": 0},
            {"command": "Unity batchmode", "exit_code": None},
        ]
        load_validator(EVIDENCE_CARD_SCHEMA).validate(valid)

        invalid_commands = (
            {"command": "missing exit code"},
            {"command": "extra property", "exit_code": 0, "output": "PASS"},
            {"command": "wrong exit code", "exit_code": "0"},
            {"command": "", "exit_code": 0},
        )
        for command in invalid_commands:
            payload = copy.deepcopy(VALID_EVIDENCE_CARD)
            payload["commands"] = [command]
            with self.subTest(command=command):
                self.assert_invalid(payload)

    def test_pass_requires_verified_evidence_no_blockers_and_zero_exit_codes(self) -> None:
        valid_pass = copy.deepcopy(VALID_EVIDENCE_CARD)
        valid_pass.update(
            verdict="PASS",
            verified=["Validation completed with exit code 0."],
            blocked=[],
            commands=[
                {"command": "python -B scripts/validate.py .", "exit_code": 0}
            ],
        )
        load_validator(EVIDENCE_CARD_SCHEMA).validate(valid_pass)

        invalid_values = (
            ("verified", []),
            ("blocked", ["A prerequisite is still missing."]),
            (
                "commands",
                [{"command": "python -B scripts/validate.py .", "exit_code": None}],
            ),
            (
                "commands",
                [{"command": "python -B scripts/validate.py .", "exit_code": 1}],
            ),
        )
        for field, value in invalid_values:
            payload = copy.deepcopy(valid_pass)
            payload[field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)

    def test_blocked_requires_at_least_one_blocker(self) -> None:
        blocked = copy.deepcopy(VALID_EVIDENCE_CARD)
        load_validator(EVIDENCE_CARD_SCHEMA).validate(blocked)

        blocked["blocked"] = []
        self.assert_invalid(blocked)

    def test_restore_accepts_string_or_null_and_next_action_is_non_empty(self) -> None:
        with_restore = copy.deepcopy(VALID_EVIDENCE_CARD)
        with_restore["restore"] = "Delete the generated local evidence file."
        load_validator(EVIDENCE_CARD_SCHEMA).validate(with_restore)

        empty_next_action = copy.deepcopy(VALID_EVIDENCE_CARD)
        empty_next_action["next_action"] = ""
        self.assert_invalid(empty_next_action)

    def test_meaningful_text_fields_reject_whitespace_only_strings(self) -> None:
        for field in (
            "verified",
            "snapshot",
            "unverified",
            "blocked",
            "artifacts",
        ):
            payload = copy.deepcopy(VALID_EVIDENCE_CARD)
            payload[field] = [" \t"]
            with self.subTest(field=field):
                self.assert_invalid(payload)

        command_payload = copy.deepcopy(VALID_EVIDENCE_CARD)
        command_payload["commands"] = [{"command": " \t", "exit_code": 0}]
        with self.subTest(field="commands.command"):
            self.assert_invalid(command_payload)

        next_action_payload = copy.deepcopy(VALID_EVIDENCE_CARD)
        next_action_payload["next_action"] = " \t"
        with self.subTest(field="next_action"):
            self.assert_invalid(next_action_payload)


if __name__ == "__main__":
    unittest.main()
