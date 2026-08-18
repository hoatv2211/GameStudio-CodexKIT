from __future__ import annotations

import copy
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from tests._meta.support import temporary_directory


class ProjectProfileTests(unittest.TestCase):
    def valid_profile(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "workspace": {
                "name": "sample-game",
                "root_git": False,
                "default_concurrency": 2,
            },
            "repositories": [
                {
                    "id": "client",
                    "path": "client",
                    "git_root": True,
                    "subsystems": ["unity", "ui"],
                    "owner_skill": "unity-client-offline-debugging",
                    "validation": [
                        {"name": "compile", "command": "run-client-build", "risk": "low"}
                    ],
                },
                {
                    "id": "server",
                    "path": "server",
                    "git_root": True,
                    "subsystems": ["server", "lua"],
                    "owner_skill": "cpp-server-crash-triage",
                    "validation": [
                        {"name": "tests", "command": "run-server-tests", "risk": "low"}
                    ],
                },
            ],
            "exclusions": ["Generated"],
            "agents": {
                "specialists": [
                    {
                        "id": "server-specialist",
                        "repository": "server",
                        "reasoning_effort": "xhigh",
                        "constraints": ["preserve protocol compatibility"],
                    }
                ]
            },
            "cross_project_contracts": [
                {
                    "id": "reward-flow",
                    "repositories": ["server", "client"],
                    "authority": "server",
                }
            ],
        }

    def test_loads_valid_profile_and_renders_deterministically(self) -> None:
        from scripts.project_profile import (
            load_project_profile,
            render_validation_matrix,
            render_workspace_map,
        )

        with temporary_directory() as temp:
            path = Path(temp) / "project-profile.yaml"
            path.write_text(yaml.safe_dump(self.valid_profile(), sort_keys=False), encoding="utf-8")

            profile = load_project_profile(
                path,
                known_skills={"unity-client-offline-debugging", "cpp-server-crash-triage"},
            )

            workspace_map = render_workspace_map(profile)
            validation_matrix = render_validation_matrix(profile)
            self.assertIn("| client | `client` | unity, ui | `unity-client-offline-debugging` |", workspace_map)
            self.assertIn("| server | tests | `run-server-tests` | low |", validation_matrix)
            self.assertEqual(workspace_map, render_workspace_map(profile))
            self.assertEqual(validation_matrix, render_validation_matrix(profile))

    def test_cli_validates_and_renders_workspace_map(self) -> None:
        from scripts.project_profile import main

        with temporary_directory() as temp:
            path = Path(temp) / "project-profile.yaml"
            path.write_text(yaml.safe_dump(self.valid_profile(), sort_keys=False), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main([str(path), "--workspace-map"])

            self.assertEqual(0, exit_code)
            self.assertIn("# Workspace Map", output.getvalue())
            self.assertIn("unity-client-offline-debugging", output.getvalue())

    def test_rejects_duplicate_repository_ids(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["repositories"] = [profile["repositories"][0], profile["repositories"][0]]

        errors = validate_project_profile(
            profile,
            known_skills={"unity-client-offline-debugging", "cpp-server-crash-triage"},
        )

        self.assertIn("duplicate repository id: client", errors)

    def test_rejects_unsafe_repository_path_and_unknown_owner(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["repositories"][0]["path"] = "../client"
        profile["repositories"][1]["owner_skill"] = "missing-skill"

        errors = validate_project_profile(
            profile,
            known_skills={"unity-client-offline-debugging", "cpp-server-crash-triage"},
        )

        self.assertIn("unsafe repository path: ../client", errors)
        self.assertIn("unknown owner skill for server: missing-skill", errors)

    def test_reports_non_string_unknown_mapping_keys_without_crashing(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile[7] = "top"
        profile["workspace"][8] = "workspace"
        profile["repositories"][0][9] = "repository"
        profile["repositories"][0]["validation"][0][10] = "validation"
        profile["agents"]["specialists"][0][11] = "specialist"
        profile["cross_project_contracts"][0][12] = "contract"

        errors = validate_project_profile(profile)

        self.assertIn("unknown project profile fields: 7", errors)
        self.assertIn("unknown workspace fields: 8", errors)
        self.assertIn("unknown repository fields for 0: 9", errors)
        self.assertIn("unknown validation fields for client: 10", errors)
        self.assertIn("unknown specialist fields: 11", errors)
        self.assertIn("unknown cross-project contract fields: 12", errors)

    def test_rejects_absolute_and_parent_repository_paths_but_accepts_dot(self) -> None:
        from scripts.project_profile import validate_project_profile

        for path_value in (
            "C:/outside",
            "C:\\outside",
            "\\\\server\\share",
            "\\\\?\\C:\\outside",
            "../client",
        ):
            with self.subTest(path_value=path_value):
                profile = self.valid_profile()
                profile["repositories"][0]["path"] = path_value

                errors = validate_project_profile(profile)

                self.assertIn(f"unsafe repository path: {path_value}", errors)

        profile = self.valid_profile()
        profile["repositories"][0]["path"] = "."

        errors = validate_project_profile(profile)

        self.assertNotIn("unsafe repository path: .", errors)

    def test_rejects_windows_invalid_repository_path_segments(self) -> None:
        from scripts.project_profile import validate_project_profile

        for path_value in (
            "CON",
            "con.txt",
            "dir/PRN.log",
            "AUX",
            "NUL.data",
            "COM1",
            "com9.json",
            "CONIN$",
            "conout$",
            "CONIN$.txt",
            "COM¹",
            "com¹.txt",
            "LPT1",
            "lpt9.log",
            "LPT²",
            "client.",
            "client ",
            "dir/name. ",
            "client/control\x01name",
            "client<name",
            "client>name",
            'client"name',
            "client|name",
            "client?name",
            "client*name",
            "client:name",
        ):
            with self.subTest(path_value=path_value):
                profile = self.valid_profile()
                profile["repositories"][0]["path"] = path_value

                errors = validate_project_profile(profile)

                self.assertIn(f"unsafe repository path: {path_value}", errors)

    def test_requires_lowercase_kebab_case_ids(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["repositories"][0]["id"] = "Game_Client"
        profile["agents"]["specialists"][0]["id"] = "Server Specialist"
        profile["cross_project_contracts"][0]["id"] = "Reward_Flow"

        errors = validate_project_profile(profile)

        self.assertIn("invalid repository id: Game_Client", errors)
        self.assertIn("invalid specialist id: Server Specialist", errors)
        self.assertIn("invalid contract id: Reward_Flow", errors)

    def test_rejects_reserved_specialist_ids_case_insensitively(self) -> None:
        from scripts.project_profile import validate_project_profile

        for specialist_id in (
            "default",
            "Worker",
            "explorer",
            "Investigator",
            "implementer",
            "Verifier",
        ):
            with self.subTest(specialist_id=specialist_id):
                profile = self.valid_profile()
                profile["agents"]["specialists"][0]["id"] = specialist_id

                errors = validate_project_profile(profile)

                self.assertIn(f"reserved specialist id: {specialist_id}", errors)

    def test_rejects_duplicate_normalized_repository_paths(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["repositories"][1]["path"] = "client/."

        errors = validate_project_profile(profile)

        self.assertIn("duplicate repository path: client", errors)

    def test_rejects_case_aliased_repository_paths_with_original_display(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["repositories"][1]["path"] = "CLIENT"

        errors = validate_project_profile(profile)

        self.assertIn("duplicate repository path: CLIENT", errors)

    def test_rejects_duplicate_validation_names_within_repository(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        duplicate_validation = copy.deepcopy(profile["repositories"][0]["validation"][0])
        duplicate_validation["name"] = " Compile "
        profile["repositories"][0]["validation"].append(duplicate_validation)

        errors = validate_project_profile(profile)

        self.assertIn("duplicate validation name for client:  Compile ", errors)

    def test_empty_known_skill_catalog_rejects_all_owner_skills(self) -> None:
        from scripts.project_profile import validate_project_profile

        errors_without_catalog = validate_project_profile(self.valid_profile(), known_skills=None)
        errors_with_empty_catalog = validate_project_profile(self.valid_profile(), known_skills=[])

        self.assertNotIn(
            "unknown owner skill for client: unity-client-offline-debugging",
            errors_without_catalog,
        )
        self.assertIn(
            "unknown owner skill for client: unity-client-offline-debugging",
            errors_with_empty_catalog,
        )
        self.assertIn(
            "unknown owner skill for server: cpp-server-crash-triage",
            errors_with_empty_catalog,
        )

    def test_rejects_specialist_for_unknown_repository(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["agents"]["specialists"][0]["repository"] = "database"

        errors = validate_project_profile(
            profile,
            known_skills={"unity-client-offline-debugging", "cpp-server-crash-triage"},
        )

        self.assertIn("unknown specialist repository for server-specialist: database", errors)

    def test_rejects_duplicate_contract_participants_and_requires_distinct_repositories(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["cross_project_contracts"][0]["repositories"] = ["client", "client"]
        profile["cross_project_contracts"][0]["authority"] = "client"

        errors = validate_project_profile(profile)

        self.assertIn("duplicate contract repository for reward-flow: client", errors)
        self.assertIn("cross-project contract repositories are invalid: reward-flow", errors)

    def test_requires_known_contract_authority_to_participate(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["repositories"].append(
            {
                "id": "database",
                "path": "database",
                "git_root": True,
                "subsystems": ["database"],
                "owner_skill": "database-skill",
                "validation": [],
            }
        )
        profile["cross_project_contracts"][0]["authority"] = "database"

        errors = validate_project_profile(profile)

        self.assertIn("contract authority must participate in reward-flow: database", errors)
        self.assertNotIn("unknown contract authority for reward-flow: database", errors)

    def test_unknown_contract_authority_does_not_report_non_participation(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["cross_project_contracts"][0]["authority"] = "database"

        errors = validate_project_profile(profile)

        self.assertIn("unknown contract authority for reward-flow: database", errors)
        self.assertNotIn("contract authority must participate in reward-flow: database", errors)

    def test_accepts_optional_specialist_scope_metadata(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["agents"]["specialists"][0]["owned_scope_patterns"] = ["server/src/**"]
        profile["agents"]["specialists"][0]["read_scope_patterns"] = ["server/tests/**"]

        errors = validate_project_profile(profile)

        self.assertEqual([], errors)

    def test_rejects_overlapping_active_specialist_writer_scopes(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["agents"]["specialists"] = [
            {
                "id": "server-specialist",
                "repository": "server",
                "reasoning_effort": "high",
                "constraints": ["preserve protocol compatibility"],
                "owned_scope_patterns": ["server/src/**"],
                "read_scope_patterns": ["server/tests/**"],
            },
            {
                "id": "server-qa",
                "repository": "server",
                "reasoning_effort": "high",
                "constraints": ["preserve test evidence"],
                "owned_scope_patterns": ["server/src/game/**"],
                "read_scope_patterns": ["server/tests/**"],
            },
        ]

        errors = validate_project_profile(profile)

        self.assertIn(
            "overlapping active specialist writer scopes: server-specialist and server-qa",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
