from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.studio_experience import build_evidence_card


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_CARD_SCHEMA = ROOT / "evals" / "schema" / "studio-evidence-card.schema.json"

EXPECTED_EVIDENCE_CARD_FIELDS = [
    "schema_version",
    "verdict",
    "workflow",
    "verified",
    "snapshot",
    "unverified",
    "blocked",
    "commands",
    "artifacts",
    "restore",
    "next_action",
]


EXPECTED_PACKET_FIELDS = {
    "schema_version",
    "status",
    "role",
    "intent",
    "mode",
    "golden_path",
    "selected_workflow",
    "candidates",
    "workflow_candidates",
    "questions",
    "risk_level",
    "prerequisites",
    "next_action",
}


class StudioExperienceTests(unittest.TestCase):
    def profile(
        self,
        *subsystems: str,
        default_role: str = "developer",
        preferred_mode: str = "basic",
        enabled_intents: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "repositories": [
                {"id": "game", "subsystems": list(subsystems)},
            ],
            "studio_experience": {
                "default_role": default_role,
                "preferred_mode": preferred_mode,
                "enabled_intents": enabled_intents
                or [
                    "diagnose",
                    "verify",
                    "plan-change",
                    "ship",
                    "handle-incident",
                ],
            },
        }

    def assert_packet_shape(self, packet: dict[str, object]) -> None:
        self.assertEqual(EXPECTED_PACKET_FIELDS, set(packet))
        self.assertEqual(1, packet["schema_version"])
        self.assertEqual("read-only", packet["risk_level"])
        self.assertIsInstance(packet["candidates"], list)
        self.assertIsInstance(packet["workflow_candidates"], list)
        self.assertIsInstance(packet["questions"], list)
        self.assertIsInstance(packet["prerequisites"], list)
        self.assertIsInstance(packet["next_action"], str)
        self.assertTrue(packet["next_action"].strip())

    def test_producer_plan_change_selects_project_adoption(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity"),
            intent="plan-change",
            role="producer",
        )

        self.assert_packet_shape(packet)
        self.assertEqual("READY", packet["status"])
        self.assertEqual("producer", packet["role"])
        self.assertEqual("project-adoption-routing", packet["golden_path"])
        self.assertEqual("studio-project-intake", packet["selected_workflow"])
        self.assertEqual(["project-adoption-routing"], packet["candidates"])
        self.assertEqual([], packet["questions"])
        self.assertEqual([], packet["prerequisites"])
        self.assertEqual(
            "Create the report-only project intake and repository routing packet.",
            packet["next_action"],
        )

    def test_developer_server_cpp_diagnosis_is_ambiguous_and_sorted(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("SERVER", "Cpp"),
            intent="diagnose",
            role="developer",
            available_skills={
                "cpp-server-crash-triage",
                "multi-service-local-environment-doctor",
            },
        )

        self.assert_packet_shape(packet)
        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertIsNone(packet["golden_path"])
        self.assertIsNone(packet["selected_workflow"])
        self.assertEqual(
            ["cpp-server-failure-recovery", "local-environment-recovery"],
            packet["candidates"],
        )
        self.assertEqual(
            ["Is this a local environment problem or a build-bound server crash?"],
            packet["questions"],
        )
        self.assertIn("does not authorize mutation", packet["next_action"])

    def test_cpp_local_pair_keeps_exact_question_when_ranking_reverses(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("cpp", "server", "service", "services", "database"),
            intent="diagnose",
            role="developer",
        )

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(
            ["local-environment-recovery", "cpp-server-failure-recovery"],
            packet["candidates"],
        )
        self.assertEqual(
            ["Is this a local environment problem or a build-bound server crash?"],
            packet["questions"],
        )

    def test_mixed_project_ambiguity_exposes_only_top_two_ranked_routes(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity")
        profile["repositories"].append(
            {"id": "server", "subsystems": ["server", "cpp"]}
        )

        packet = plan_experience(profile, intent="diagnose", role="developer")

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(
            ["cpp-server-failure-recovery", "local-environment-recovery"],
            packet["candidates"],
        )
        self.assertEqual(
            ["Is this a local environment problem or a build-bound server crash?"],
            packet["questions"],
        )

    def test_other_ambiguous_pair_gets_candidate_specific_question(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity")
        profile["repositories"].append(
            {"id": "database", "subsystems": ["database"]}
        )

        packet = plan_experience(profile, intent="diagnose", role="developer")

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(
            ["local-environment-recovery", "unity-client-entry-recovery"],
            packet["candidates"],
        )
        self.assertEqual(
            [
                "Which Golden Path matches the current symptom: "
                "local-environment-recovery or unity-client-entry-recovery?"
            ],
            packet["questions"],
        )

    def test_explicit_cpp_path_resolves_ambiguity(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "cpp"),
            intent="diagnose",
            role="developer",
            requested_golden_path="cpp-server-failure-recovery",
            available_skills={
                "cpp-server-crash-triage",
                "multi-service-local-environment-doctor",
            },
        )

        self.assert_packet_shape(packet)
        self.assertEqual("READY", packet["status"])
        self.assertEqual("cpp-server-failure-recovery", packet["golden_path"])
        self.assertEqual("cpp-server-crash-triage", packet["selected_workflow"])
        self.assertEqual(["cpp-server-failure-recovery"], packet["candidates"])

    def test_explicit_path_can_select_match_omitted_from_ambiguous_top_two(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity")
        profile["repositories"].append(
            {"id": "server", "subsystems": ["server", "cpp"]}
        )

        packet = plan_experience(
            profile,
            intent="diagnose",
            role="developer",
            requested_golden_path="unity-client-entry-recovery",
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("unity-client-entry-recovery", packet["golden_path"])
        self.assertEqual(
            "unity-client-offline-debugging", packet["selected_workflow"]
        )
        self.assertEqual(["unity-client-entry-recovery"], packet["candidates"])

    def test_missing_selected_workflow_blocks_without_losing_path(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity"),
            intent="diagnose",
            role="qa",
            requested_golden_path="unity-client-entry-recovery",
            available_skills={"studio-project-intake"},
        )

        self.assert_packet_shape(packet)
        self.assertEqual("BLOCKED", packet["status"])
        self.assertEqual("unity-client-entry-recovery", packet["golden_path"])
        self.assertIsNone(packet["selected_workflow"])
        self.assertEqual(["unity-client-entry-recovery"], packet["candidates"])
        self.assertEqual([], packet["questions"])
        self.assertEqual(1, len(packet["prerequisites"]))
        self.assertIn("unity-client-offline-debugging", packet["prerequisites"][0])
        self.assertIn("owning pack or full catalog", packet["next_action"])

    def test_omitted_role_and_mode_use_fallback_defaults(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            {"repositories": [{"subsystems": ["unity"]}]},
            intent="diagnose",
        )

        self.assertEqual("developer", packet["role"])
        self.assertEqual("basic", packet["mode"])

    def test_absent_enabled_intents_defaults_to_all_intents(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            {
                "repositories": [{"subsystems": ["unity"]}],
                "studio_experience": {
                    "default_role": "developer",
                    "preferred_mode": "basic",
                },
            },
            intent="diagnose",
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual(
            "unity-client-offline-debugging", packet["selected_workflow"]
        )

    def test_explicit_empty_enabled_intents_fails_closed(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity")
        profile["studio_experience"]["enabled_intents"] = []

        with self.assertRaisesRegex(
            ValueError,
            "^studio experience enabled_intents must be a non-empty list$",
        ):
            plan_experience(profile, intent="diagnose")

    def test_explicit_wrong_type_enabled_intents_fails_closed(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity")
        profile["studio_experience"]["enabled_intents"] = "diagnose"

        with self.assertRaisesRegex(
            ValueError,
            "^studio experience enabled_intents must be a non-empty list$",
        ):
            plan_experience(profile, intent="diagnose")

    def test_invalid_enabled_intent_data_fails_closed(self) -> None:
        from scripts.studio_experience import plan_experience

        cases = (
            (["diagnose", "deploy-now"], "unknown studio experience intent: deploy-now"),
            (["diagnose", "diagnose"], "studio experience enabled_intents must be unique"),
            (["diagnose", 1], "studio experience intent must be a string"),
        )
        for enabled_intents, message in cases:
            with self.subTest(enabled_intents=enabled_intents):
                profile = self.profile("unity")
                profile["studio_experience"]["enabled_intents"] = enabled_intents
                with self.assertRaisesRegex(ValueError, f"^{message}$"):
                    plan_experience(profile, intent="diagnose")

    def test_explicit_malformed_studio_experience_fails_closed(self) -> None:
        from scripts.studio_experience import plan_experience

        with self.assertRaisesRegex(
            ValueError,
            "^studio_experience must be a mapping$",
        ):
            plan_experience(
                {
                    "repositories": [{"subsystems": ["unity"]}],
                    "studio_experience": "developer",
                },
                intent="diagnose",
            )

    def test_non_mapping_profile_fails_closed_before_route_selection(self) -> None:
        from scripts.studio_experience import plan_experience

        with self.assertRaisesRegex(
            ValueError,
            "^project profile must be a mapping$",
        ):
            plan_experience(None, intent="plan-change")

    def test_omitted_role_and_mode_use_profile_provided_defaults(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile(
                "unity",
                default_role="producer",
                preferred_mode="advanced",
                enabled_intents=["plan-change"],
            ),
            intent="plan-change",
        )

        self.assertEqual("producer", packet["role"])
        self.assertEqual("advanced", packet["mode"])
        self.assertEqual("READY", packet["status"])
        self.assertEqual("project-adoption-routing", packet["golden_path"])
        self.assertEqual("studio-project-intake", packet["selected_workflow"])

    def test_profile_defaults_can_be_overridden_explicitly(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity", default_role="producer", preferred_mode="advanced"),
            intent="diagnose",
            role="qa",
            mode="basic",
        )

        self.assertEqual("qa", packet["role"])
        self.assertEqual("basic", packet["mode"])

    def test_rejects_unknown_role_mode_and_unknown_or_disabled_intent(self) -> None:
        from scripts.studio_experience import plan_experience

        cases = (
            ({"intent": "diagnose", "role": "wizard"}, "unknown studio role: wizard"),
            ({"intent": "diagnose", "mode": "expert"}, "unknown studio mode: expert"),
            ({"intent": "deploy"}, "studio intent is not enabled: deploy"),
            (
                {
                    "intent": "verify",
                    "profile": self.profile("server", enabled_intents=["diagnose"]),
                },
                "studio intent is not enabled: verify",
            ),
        )
        for arguments, message in cases:
            with self.subTest(message=message):
                selected_profile = arguments.pop("profile", self.profile("unity"))
                with self.assertRaisesRegex(ValueError, f"^{message}$"):
                    plan_experience(selected_profile, **arguments)

    def test_requested_unavailable_path_preserves_prefilter_candidates(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity")
        profile["repositories"].append(
            {"id": "server", "subsystems": ["server", "cpp"]}
        )
        packet = plan_experience(
            profile,
            intent="diagnose",
            role="developer",
            requested_golden_path="project-adoption-routing",
        )

        self.assertEqual("BLOCKED", packet["status"])
        self.assertIsNone(packet["golden_path"])
        self.assertIsNone(packet["selected_workflow"])
        self.assertEqual(
            [
                "cpp-server-failure-recovery",
                "local-environment-recovery",
                "unity-client-entry-recovery",
            ],
            packet["candidates"],
        )
        self.assertEqual(1, len(packet["prerequisites"]))
        self.assertIn("project-adoption-routing", packet["prerequisites"][0])
        self.assertIn("reported candidate", packet["next_action"])

    def test_requested_golden_path_must_be_a_string(self) -> None:
        from scripts.studio_experience import plan_experience

        for requested in (["unity-client-entry-recovery"], {"unity", "cpp"}):
            with self.subTest(requested_type=type(requested).__name__):
                with self.assertRaises(ValueError) as context:
                    plan_experience(
                        self.profile("unity"),
                        intent="diagnose",
                        requested_golden_path=requested,
                    )
                self.assertEqual(
                    "requested_golden_path must be a string", str(context.exception)
                )

    def test_no_candidate_is_blocked_with_exact_guidance(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity"),
            intent="ship",
            role="developer",
        )

        self.assertEqual("BLOCKED", packet["status"])
        self.assertEqual([], packet["candidates"])
        self.assertEqual(
            ["No Golden Path matches the detected project evidence."],
            packet["prerequisites"],
        )
        self.assertEqual(
            "Run studio-project-intake, or use Advanced presentation and select a "
            "canonical skill directly outside gamestudio guide.",
            packet["next_action"],
        )

    def test_no_candidate_with_capability_catalogs_keeps_route_evidence_blocker(self) -> None:
        from scripts.studio_experience import plan_experience

        for available_skills in (
            set(),
            {
                "studio-project-intake",
                "multi-service-local-environment-doctor",
                "unity-client-offline-debugging",
                "cpp-server-crash-triage",
            },
        ):
            with self.subTest(available_skills=available_skills):
                packet = plan_experience(
                    self.profile("unity"),
                    intent="ship",
                    role="developer",
                    available_skills=available_skills,
                )
                self.assertEqual("BLOCKED", packet["status"])
                self.assertEqual([], packet["candidates"])
                self.assertEqual([], packet["workflow_candidates"])
                self.assertEqual(
                    ["No Golden Path matches the detected project evidence."],
                    packet["prerequisites"],
                )

    def test_malformed_profile_collections_do_not_crash_or_add_subsystems(self) -> None:
        from scripts.studio_experience import plan_experience

        malformed_profiles = (
            {"repositories": "unity"},
            {"repositories": [None, "server", {"subsystems": "cpp"}]},
        )
        for profile in malformed_profiles:
            with self.subTest(profile=profile):
                packet = plan_experience(profile, intent="diagnose")
                self.assertEqual("BLOCKED", packet["status"])
                self.assertEqual([], packet["candidates"])

    def test_reports_workflow_candidates_for_unity_ui_and_localization(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity", "ui", "localization"),
            intent="verify",
            role="qa",
        )

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(["unity-ui-localization"], packet["candidates"])
        self.assertEqual(
            [
                "localization-authority-audit",
                "unity-ui-rendering-debugging",
            ],
            packet["workflow_candidates"],
        )
        self.assertEqual("unity-ui-localization", packet["golden_path"])
        self.assertIsNone(packet["selected_workflow"])
        self.assertEqual(1, len(packet["questions"]))

    def test_available_workflows_filter_before_workflow_ambiguity(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity", "ui", "localization")
        one_installed = plan_experience(
            profile,
            intent="verify",
            role="qa",
            available_skills={"localization-authority-audit"},
        )
        self.assertEqual("READY", one_installed["status"])
        self.assertEqual("unity-ui-localization", one_installed["golden_path"])
        self.assertEqual(
            ["localization-authority-audit"], one_installed["workflow_candidates"]
        )

        none_installed = plan_experience(
            profile,
            intent="verify",
            role="qa",
            available_skills=set(),
        )
        self.assertEqual("BLOCKED", none_installed["status"])
        self.assertEqual("unity-ui-localization", none_installed["golden_path"])
        self.assertIsNone(none_installed["selected_workflow"])
        self.assertEqual([], none_installed["workflow_candidates"])
        self.assertIn("localization-authority-audit", none_installed["prerequisites"][0])
        self.assertIn("unity-ui-rendering-debugging", none_installed["prerequisites"][0])

        both_installed = plan_experience(
            profile,
            intent="verify",
            role="qa",
            available_skills={
                "localization-authority-audit",
                "unity-ui-rendering-debugging",
            },
        )
        self.assertEqual("AMBIGUOUS", both_installed["status"])
        self.assertEqual(
            [
                "localization-authority-audit",
                "unity-ui-rendering-debugging",
            ],
            both_installed["workflow_candidates"],
        )

    def test_partial_installs_filter_multi_family_ambiguity_closure(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity", "server", "cpp")
        packet = plan_experience(
            profile,
            intent="diagnose",
            role="developer",
            available_skills={
                "cpp-server-crash-triage",
                "unity-client-offline-debugging",
            },
        )

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(
            ["cpp-server-failure-recovery", "unity-client-entry-recovery"],
            packet["candidates"],
        )
        self.assertEqual(
            ["cpp-server-crash-triage", "unity-client-offline-debugging"],
            packet["workflow_candidates"],
        )
        self.assertNotIn(
            "multi-service-local-environment-doctor", packet["workflow_candidates"]
        )

    def test_advanced_workflow_override_selects_unity_asset_audit(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity", "assets"),
            intent="verify",
            role="qa",
            mode="advanced",
            requested_workflow="unity-asset-guid-meta-audit",
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("unity-build-asset-integrity", packet["golden_path"])
        self.assertEqual(
            "unity-asset-guid-meta-audit", packet["selected_workflow"]
        )
        self.assertEqual(
            ["unity-asset-guid-meta-audit"], packet["workflow_candidates"]
        )

    def test_basic_workflow_override_rejects_with_exact_error(self) -> None:
        from scripts.studio_experience import plan_experience

        with self.assertRaisesRegex(
            ValueError, "^workflow override requires advanced mode$"
        ):
            plan_experience(
                self.profile("unity", "assets"),
                intent="verify",
                role="qa",
                mode="basic",
                requested_workflow="unity-asset-guid-meta-audit",
            )

    def test_liveops_handle_incident_selects_liveops_recovery(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile(),
            intent="handle-incident",
            role="liveops",
            mode="advanced",
            requested_workflow="liveops-incident-response",
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("data-live-release-safety", packet["golden_path"])
        self.assertEqual("liveops-incident-response", packet["selected_workflow"])
        self.assertEqual(["liveops-incident-response"], packet["workflow_candidates"])

    def test_missing_requested_workflow_capability_blocks_without_candidates(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "network", "security"),
            intent="verify",
            role="qa",
            mode="advanced",
            requested_workflow="network-authority-and-exploit-review",
            available_skills={"mmorpg-packet-protocol-review"},
        )

        self.assertEqual("BLOCKED", packet["status"])
        self.assertEqual("lua-contract-server-authority", packet["golden_path"])
        self.assertIsNone(packet["selected_workflow"])
        self.assertEqual([], packet["workflow_candidates"])
        self.assertIn(
            "network-authority-and-exploit-review", packet["prerequisites"][0]
        )

    def test_requested_workflow_malformed_values_fail_closed(self) -> None:
        from scripts.studio_experience import plan_experience

        for requested, message in (
            (None, None),
            ([], "requested_workflow must be a string"),
            ({"workflow"}, "requested_workflow must be a string"),
            ("   ", "requested_workflow must be a non-empty string"),
        ):
            if requested is None:
                continue
            with self.subTest(requested=requested):
                with self.assertRaisesRegex(ValueError, f"^{message}$"):
                    plan_experience(
                        self.profile("unity"),
                        intent="diagnose",
                        mode="advanced",
                        requested_workflow=requested,
                    )

    def test_all_eight_families_are_represented_and_deterministic(self) -> None:
        from scripts.studio_experience import plan_experience

        cases = (
            ("project-adoption-routing", "plan-change", "producer", "unity"),
            ("local-environment-recovery", "diagnose", "qa", "server"),
            ("unity-client-entry-recovery", "diagnose", "qa", "unity"),
            ("cpp-server-failure-recovery", "diagnose", "qa", "cpp"),
            ("unity-ui-localization", "verify", "qa", "unity"),
            ("unity-build-asset-integrity", "verify", "qa", "unity"),
            ("lua-contract-server-authority", "verify", "qa", "lua"),
            ("data-live-release-safety", "ship", "qa", ""),
        )
        for family, intent, role, subsystem in cases:
            if family == "unity-ui-localization":
                profile = self.profile("unity", "ui")
            elif family == "unity-build-asset-integrity":
                profile = self.profile("unity", "assets")
            elif family == "lua-contract-server-authority":
                profile = self.profile("lua", "server", "network")
            else:
                profile = self.profile(
                    *(
                        [subsystem, "server"]
                        if subsystem == "cpp"
                        else [subsystem]
                        if subsystem
                        else []
                    )
                )
            first = plan_experience(profile, intent=intent, role=role)
            second = plan_experience(profile, intent=intent, role=role)
            self.assertEqual(first, second)
            self.assertIn(family, first["candidates"])

    def test_family_ambiguity_bounds_top_two_and_workflows_match_reported_families(self) -> None:
        from scripts.studio_experience import plan_experience

        profile = self.profile("unity", "server", "cpp", "ui", "localization")
        packet = plan_experience(profile, intent="diagnose", role="developer")

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(2, len(packet["candidates"]))
        self.assertGreaterEqual(len(packet["workflow_candidates"]), 2)
        family_workflows = {
            "cpp-server-failure-recovery": {
                "cpp-server-crash-triage",
                "mmorpg-packet-protocol-review",
            },
            "local-environment-recovery": {"multi-service-local-environment-doctor"},
            "unity-client-entry-recovery": {"unity-client-offline-debugging"},
            "unity-ui-localization": {
                "localization-authority-audit",
                "unity-ui-rendering-debugging",
            },
        }
        allowed = set().union(*(family_workflows[family] for family in packet["candidates"]))
        self.assertTrue(set(packet["workflow_candidates"]).issubset(allowed))

    def test_server_database_liveops_incident_uses_incident_route(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "database"),
            intent="handle-incident",
            role="liveops",
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("data-live-release-safety", packet["golden_path"])
        self.assertEqual("liveops-incident-response", packet["selected_workflow"])

    def test_lua_server_network_stays_in_lua_contract_family(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("lua", "server", "network"),
            intent="verify",
            role="qa",
        )

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual("lua-contract-server-authority", packet["golden_path"])
        self.assertIsNone(packet["selected_workflow"])
        self.assertEqual(
            [
                "lua-client-server-contract-audit",
                "network-authority-and-exploit-review",
            ],
            packet["workflow_candidates"],
        )

    def test_generic_server_verification_does_not_surface_unrelated_families(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server"),
            intent="verify",
            role="qa",
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual(["local-environment-recovery"], packet["candidates"])
        self.assertEqual(
            ["multi-service-local-environment-doctor"],
            packet["workflow_candidates"],
        )

    def test_lua_without_authority_route_keeps_local_environment_recovery(self) -> None:
        from scripts.studio_experience import plan_experience

        for subsystems in (("lua", "server"), ("lua", "service")):
            with self.subTest(subsystems=subsystems):
                packet = plan_experience(
                    self.profile(*subsystems),
                    intent="verify",
                    role="qa",
                )
                self.assertEqual("READY", packet["status"])
                self.assertEqual("local-environment-recovery", packet["golden_path"])

    def test_task_packet_semantics_reject_structural_contradictions_defensively(self) -> None:
        from scripts.studio_experience import (
            plan_experience,
            task_packet_semantic_errors,
        )

        coherent = plan_experience(
            self.profile("unity"),
            intent="diagnose",
            role="qa",
        )
        self.assertEqual([], task_packet_semantic_errors(coherent))

        contradiction = dict(coherent)
        contradiction["golden_path"] = "project-adoption-routing"
        self.assertEqual(
            ["READY golden_path must equal candidates[0]"],
            task_packet_semantic_errors(contradiction),
        )

        malformed_values = (None, [], "packet", {"status": "READY"})
        for malformed in malformed_values:
            with self.subTest(malformed=malformed):
                errors = task_packet_semantic_errors(malformed)
                self.assertIsInstance(errors, list)
                self.assertTrue(errors)
                self.assertNotIn("Traceback", " ".join(errors))


class StudioExperienceDocumentationContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_root_skill_separates_planning_execution_and_runtime_evidence(self) -> None:
        text = self.read("skills/using-game-studio-skills/SKILL.md")

        for phrase in (
            "Stage 1 - task packet",
            "READY`, `AMBIGUOUS`, or `BLOCKED",
            "never a runtime `PASS`",
            "Stage 2 - canonical workflow",
            "only the selected canonical workflow executes or reviews its own actions",
            "Stage 3 - normalized evidence card",
            "runtime verdict of `PASS`, `BLOCKED`, or `FAIL`",
            "`READY` authorizes no execution or mutation",
            "cannot fabricate the final runtime verdict",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn("eight Golden Path families", text)
        self.assertNotIn("Phase 1 implements four Golden Paths", text)
        self.assertNotIn("Ship has no Phase-1 Golden Path", text)

    def test_wiki_examples_and_eight_family_catalog_match_current_routes(self) -> None:
        text = self.read("docs/wiki-skill-agent-user-guide.md")
        route_section = text.split("## Golden Paths and role-first routing", 1)[1].split(
            "## Prompt templates", 1
        )[0]

        expected_families = (
            "Project adoption and routing",
            "Local environment recovery",
            "Unity client entry recovery",
            "C++ server failure recovery",
            "Unity UI and localization",
            "Unity build and asset integrity",
            "Lua contract and server authority",
            "Data and live release safety",
        )
        for family in expected_families:
            with self.subTest(family=family):
                self.assertIn(family, route_section)

        expected_rows = (
            (
                "Developer · Diagnose",
                "diagnose why this Unity client cannot enter offline mode",
            ),
            (
                "QA · Verify",
                "verify this local multi-service environment, including server, "
                "service, and database context",
            ),
            (
                "Producer · Plan Change",
                "plan repository adoption and show the proposed route without "
                "writing files",
            ),
            (
                "LiveOps · Handle Incident",
                "handle this C++ server crash incident and preserve the build-bound "
                "diagnostic evidence",
            ),
        )
        for role, request in expected_rows:
            with self.subTest(role=role):
                self.assertIn(role, route_section)
                self.assertIn(request, route_section)
        self.assertNotIn("verify this Unity build", route_section)

    def test_public_docs_state_current_eight_family_scope(self) -> None:
        expected_intents = (
            "Diagnose",
            "Verify",
            "Plan Change",
            "Ship",
            "Handle Incident",
        )
        for relative_path in (
            "docs/wiki-skill-agent-user-guide.md",
            "docs/architecture/overview.md",
            "docs/architecture/project-init-and-studio-expansion.md",
        ):
            text = self.read(relative_path)
            with self.subTest(path=relative_path):
                self.assertNotIn("Phase 1", text)
                self.assertNotIn("four Golden Paths", text)
                self.assertNotIn("Ship has no Phase-1 Golden Path", text)
                self.assertIn("eight", text.casefold())
                self.assertIn("Golden Path", text)
                self.assertIn("`BLOCKED`", text)
                self.assertIn("report-only", text)
                self.assertIn("`--workflow`", text)
                for intent in expected_intents:
                    self.assertIn(intent, text)

        expansion = self.read(
            "docs/architecture/project-init-and-studio-expansion.md"
        )
        self.assertIn("eight implemented Unity/MMORPG Golden Path families", expansion)
        self.assertIn("studio_adoption_eval.py", expansion)

    def test_landing_page_publishes_current_studio_ux_evidence(self) -> None:
        landing = self.read("docs/index.html")

        for phrase in (
            "316/316",
            "18 governed dogfood",
            "Eight Golden Path families",
            "--workflow",
            "80% intended routing",
            "three questions",
            "five minutes",
            "SHA-256-bound artifacts",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, landing)


class StudioEvidenceCardTests(unittest.TestCase):
    def build(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "workflow": "build-and-runtime-verification",
            "verdict": "FAIL",
            "verified": [],
            "snapshot": [],
            "unverified": ["A regression remains reproducible."],
            "blocked": [],
            "commands": [],
            "artifacts": [],
            "restore": None,
            "next_action": "Inspect the first failing assertion.",
        }
        arguments.update(overrides)
        return build_evidence_card(**arguments)

    def validator(self) -> Draft202012Validator:
        schema = json.loads(EVIDENCE_CARD_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_blocked_card_preserves_empty_command_and_artifact_evidence(self) -> None:
        card = self.build(
            workflow="unity-client-offline-debugging",
            verdict="BLOCKED",
            snapshot=["Unity project profile selected."],
            unverified=[],
            blocked=["Unity Editor is unavailable."],
            commands=[],
            artifacts=[],
            next_action="Open the project in a supported Unity Editor.",
        )

        self.assertEqual("BLOCKED", card["verdict"])
        self.assertEqual([], card["commands"])
        self.assertEqual([], card["artifacts"])
        self.assertIsNone(card["restore"])
        self.assertEqual(EXPECTED_EVIDENCE_CARD_FIELDS, list(card))

    def test_pass_requires_verified_evidence(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.build(verdict="PASS", verified=[], unverified=[])

        self.assertEqual("PASS requires verified evidence", str(context.exception))

    def test_pass_rejects_blockers_and_unverified_command_exit_codes(self) -> None:
        cases = (
            (
                {"blocked": ["A required dependency is unavailable."]},
                "PASS cannot include blockers",
            ),
            (
                {
                    "commands": [
                        {"command": "python -B scripts/validate.py .", "exit_code": None}
                    ]
                },
                "PASS requires every command to have exit_code 0",
            ),
            (
                {
                    "commands": [
                        {"command": "python -B scripts/validate.py .", "exit_code": 1}
                    ]
                },
                "PASS requires every command to have exit_code 0",
            ),
        )
        for overrides, expected in cases:
            with self.subTest(expected=expected, overrides=overrides):
                with self.assertRaises(ValueError) as context:
                    self.build(
                        verdict="PASS",
                        verified=["A governed check completed."],
                        unverified=[],
                        **overrides,
                    )
                self.assertEqual(expected, str(context.exception))

    def test_rejects_invalid_verdict_semantics_and_command_shape(self) -> None:
        cases = (
            ({"verdict": "READY"}, "unknown evidence verdict: READY"),
            (
                {"verdict": "BLOCKED", "unverified": [], "blocked": []},
                "BLOCKED requires at least one blocker",
            ),
            (
                {"commands": [{"command": "python -B scripts/validate.py ."}]},
                "command evidence requires command and exit_code",
            ),
            (
                {
                    "commands": [
                        {
                            "command": "python -B scripts/validate.py .",
                            "exit_code": 0,
                            "output": "PASS",
                        }
                    ]
                },
                "command evidence requires command and exit_code",
            ),
        )
        for overrides, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError) as context:
                    self.build(**overrides)
                self.assertEqual(expected, str(context.exception))

    def test_representative_verdicts_validate_against_evidence_schema(self) -> None:
        cards = (
            self.build(
                verdict="PASS",
                verified=["Validation completed with exit code 0."],
                unverified=[],
                commands=[
                    {"command": "python -B scripts/validate.py .", "exit_code": 0}
                ],
                artifacts=["evidence/local/validation.txt"],
                restore="Delete the local evidence artifact.",
                next_action="Hand off the verified result.",
            ),
            self.build(),
            self.build(
                verdict="BLOCKED",
                unverified=[],
                blocked=["Required model runner is unavailable."],
                next_action="Provide the required model runner.",
            ),
        )

        validator = self.validator()
        for card in cards:
            with self.subTest(verdict=card["verdict"]):
                validator.validate(card)

    def test_rejects_schema_invalid_types_and_whitespace(self) -> None:
        cases = (
            ({"workflow": "Unity_Client"}, "workflow"),
            ({"workflow": "   "}, "workflow whitespace"),
            ({"verified": ("evidence",)}, "verified type"),
            ({"snapshot": [" \t"]}, "snapshot whitespace"),
            ({"unverified": [1]}, "unverified item type"),
            ({"blocked": "blocker"}, "blocked type"),
            ({"artifacts": [""]}, "artifact whitespace"),
            ({"commands": ()}, "commands type"),
            ({"commands": ["python -B test.py"]}, "command mapping type"),
            (
                {"commands": [{"command": " \t", "exit_code": 0}]},
                "command whitespace",
            ),
            (
                {"commands": [{"command": "python -B test.py", "exit_code": True}]},
                "bool exit code",
            ),
            (
                {"commands": [{"command": "python -B test.py", "exit_code": "0"}]},
                "exit code type",
            ),
            ({"restore": 1}, "restore type"),
            ({"next_action": " \t"}, "next action whitespace"),
            ({"next_action": None}, "next action type"),
        )
        for overrides, label in cases:
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    self.build(**overrides)

    def test_copies_inputs_without_deduplicating_or_reordering(self) -> None:
        verified = ["first", "first", "second"]
        snapshot = ["snapshot"]
        unverified = ["unverified"]
        blocked: list[str] = []
        commands = [
            {"command": "command-one", "exit_code": 0},
            {"command": "command-two", "exit_code": None},
        ]
        artifacts = ["artifact-b", "artifact-a", "artifact-b"]

        card = build_evidence_card(
            workflow="build-and-runtime-verification",
            verdict="FAIL",
            verified=verified,
            snapshot=snapshot,
            unverified=unverified,
            blocked=blocked,
            commands=commands,
            artifacts=artifacts,
            restore=None,
            next_action="Preserve the caller-owned values.",
        )

        self.assertEqual(["first", "first", "second"], card["verified"])
        self.assertEqual(["artifact-b", "artifact-a", "artifact-b"], card["artifacts"])
        self.assertIsNot(verified, card["verified"])
        self.assertIsNot(commands, card["commands"])
        self.assertIsNot(commands[0], card["commands"][0])

        verified.append("caller-only")
        commands[0]["command"] = "caller-mutated"
        artifacts.clear()
        self.assertEqual(["first", "first", "second"], card["verified"])
        self.assertEqual("command-one", card["commands"][0]["command"])
        self.assertEqual(["artifact-b", "artifact-a", "artifact-b"], card["artifacts"])

        card["verified"].append("card-only")
        card["commands"][0]["command"] = "card-mutated"
        self.assertEqual(["first", "first", "second", "caller-only"], verified)
        self.assertEqual("caller-mutated", commands[0]["command"])

    def test_evidence_list_subclass_is_snapshotted_once_before_validation(self) -> None:
        class ChangingList(list[object]):
            def __init__(self) -> None:
                super().__init__()
                self.iterations = 0

            def __iter__(self):
                self.iterations += 1
                if self.iterations == 1:
                    return iter(["first snapshot"])
                return iter([object()])

        changing_snapshot = ChangingList()

        card = self.build(snapshot=changing_snapshot)

        self.assertEqual([], list(self.validator().iter_errors(card)))
        self.assertEqual(["first snapshot"], card["snapshot"])
        self.assertEqual(1, changing_snapshot.iterations)


if __name__ == "__main__":
    unittest.main()
