from __future__ import annotations

import unittest


class PackDependencyClosureTests(unittest.TestCase):
    def capabilities(self) -> list[dict[str, object]]:
        return [
            {"id": "root", "depends_on": []},
            {"id": "unity-audit", "depends_on": ["root"]},
            {"id": "art-preflight", "depends_on": ["unity-audit"]},
        ]

    def test_resolves_transitive_pack_skills(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "core", "skills": ["root"], "depends_on": []},
            {"id": "unity", "skills": ["unity-audit"], "depends_on": ["core"]},
            {"id": "content", "skills": ["art-preflight"], "depends_on": ["unity"]},
        ]

        self.assertEqual(
            ["art-preflight", "root", "unity-audit"],
            resolve_pack_skill_closure(packs, self.capabilities(), "content"),
        )

    def test_rejects_capability_missing_from_declared_pack_closure(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "core", "skills": ["root"], "depends_on": []},
            {"id": "unity", "skills": ["unity-audit"], "depends_on": ["core"]},
            {"id": "content", "skills": ["art-preflight"], "depends_on": ["core"]},
        ]

        with self.assertRaisesRegex(
            ValueError,
            r"^pack content is missing capability unity-audit required by art-preflight$",
        ):
            resolve_pack_skill_closure(packs, self.capabilities(), "content")

    def test_rejects_pack_dependency_cycles(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "a", "skills": ["root"], "depends_on": ["b"]},
            {"id": "b", "skills": [], "depends_on": ["a"]},
        ]

        with self.assertRaisesRegex(ValueError, r"^pack dependency cycle: a -> b -> a$"):
            resolve_pack_skill_closure(packs, self.capabilities(), "a")

    def test_rejects_non_string_pack_id(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": None, "skills": [], "depends_on": []}]

        with self.assertRaisesRegex(ValueError, r"^invalid pack id: None$"):
            resolve_pack_skill_closure(packs, self.capabilities(), "content")

    def test_rejects_whitespace_only_capability_id(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": [], "depends_on": []}]
        capabilities = [{"id": "   ", "depends_on": []}]

        with self.assertRaisesRegex(ValueError, r"^invalid capability id: '   '$"):
            resolve_pack_skill_closure(packs, capabilities, "content")

    def test_treats_null_pack_skills_as_empty(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": None, "depends_on": []}]

        self.assertEqual([], resolve_pack_skill_closure(packs, self.capabilities(), "content"))

    def test_treats_null_pack_dependencies_as_empty(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": ["root"], "depends_on": None}]

        self.assertEqual(
            ["root"],
            resolve_pack_skill_closure(packs, self.capabilities(), "content"),
        )

    def test_treats_null_capability_dependencies_as_empty(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": ["root"], "depends_on": []}]
        capabilities = [{"id": "root", "depends_on": None}]

        self.assertEqual(
            ["root"],
            resolve_pack_skill_closure(packs, capabilities, "content"),
        )

    def test_rejects_non_list_relationship_fields(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        cases = [
            (
                [{"id": "content", "skills": [], "depends_on": "core"}],
                self.capabilities(),
                r"^pack content depends_on must be a list$",
            ),
            (
                [{"id": "content", "skills": "root", "depends_on": []}],
                self.capabilities(),
                r"^pack content skills must be a list$",
            ),
            (
                [{"id": "content", "skills": ["root"], "depends_on": []}],
                [{"id": "root", "depends_on": "base"}],
                r"^capability root depends_on must be a list$",
            ),
        ]

        for packs, capabilities, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    resolve_pack_skill_closure(packs, capabilities, "content")

    def test_rejects_invalid_relationship_elements(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        cases = [
            (
                [{"id": "content", "skills": [], "depends_on": [7]}],
                self.capabilities(),
                r"^pack content depends_on\[0\] must be a nonblank string, got 7$",
            ),
            (
                [{"id": "content", "skills": [None], "depends_on": []}],
                self.capabilities(),
                r"^pack content skills\[0\] must be a nonblank string, got None$",
            ),
            (
                [{"id": "content", "skills": ["root"], "depends_on": []}],
                [{"id": "root", "depends_on": ["   "]}],
                r"^capability root depends_on\[0\] must be a nonblank string, got '   '$",
            ),
        ]

        for packs, capabilities, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    resolve_pack_skill_closure(packs, capabilities, "content")

    def test_reports_transitive_dependency_owner(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": ["a", "b"], "depends_on": []}]
        capabilities = [
            {"id": "a", "depends_on": ["b"]},
            {"id": "b", "depends_on": ["missing"]},
        ]

        with self.assertRaisesRegex(
            ValueError,
            r"^capability b references unknown dependency missing$",
        ):
            resolve_pack_skill_closure(packs, capabilities, "content")

    def test_rejects_unknown_pack_dependency(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": [], "depends_on": ["missing"]}]

        with self.assertRaisesRegex(ValueError, r"^unknown pack dependency: missing$"):
            resolve_pack_skill_closure(packs, self.capabilities(), "content")

    def test_rejects_duplicate_pack_ids(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "content", "skills": [], "depends_on": []},
            {"id": "content", "skills": [], "depends_on": []},
        ]

        with self.assertRaisesRegex(
            ValueError,
            r"^invalid or duplicate pack id: content$",
        ):
            resolve_pack_skill_closure(packs, self.capabilities(), "content")

    def test_rejects_duplicate_capability_ids(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [{"id": "content", "skills": [], "depends_on": []}]
        capabilities = [
            {"id": "root", "depends_on": []},
            {"id": "root", "depends_on": []},
        ]

        with self.assertRaisesRegex(
            ValueError,
            r"^invalid or duplicate capability id: root$",
        ):
            resolve_pack_skill_closure(packs, capabilities, "content")

    def test_repository_pack_registry_is_dependency_closed(self) -> None:
        from pathlib import Path

        from scripts.catalog_graph import resolve_pack_skill_closure
        from scripts.common import load_yaml

        root = Path(__file__).resolve().parents[2]
        packs = load_yaml(root / "registry" / "packs.yaml")["packs"]
        capabilities = load_yaml(root / "registry" / "capabilities.yaml")["capabilities"]

        for pack in packs:
            with self.subTest(pack=pack["id"]):
                resolved = resolve_pack_skill_closure(packs, capabilities, pack["id"])
                self.assertTrue(resolved)


class PackDependencyClosureValidationTests(unittest.TestCase):
    def validate_fixture(
        self,
        capability_dependencies: dict[str, object],
        packs: list[dict[str, object]],
    ) -> list[object]:
        from pathlib import Path

        import yaml

        from scripts.validate import validate_repository
        from tests._meta.support import (
            temporary_directory,
            write_plugin_package,
            write_registries,
            write_skill,
        )

        temp_dir = temporary_directory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        skill_ids = list(capability_dependencies)
        for skill_id in skill_ids:
            write_skill(root, skill_id)
        write_registries(root, skill_ids)
        write_plugin_package(root)

        capabilities_path = root / "registry" / "capabilities.yaml"
        capabilities = yaml.safe_load(capabilities_path.read_text(encoding="utf-8"))
        for capability in capabilities["capabilities"]:
            capability["depends_on"] = capability_dependencies[capability["id"]]
        capabilities_path.write_text(
            yaml.safe_dump(capabilities, sort_keys=False),
            encoding="utf-8",
        )

        packs_path = root / "registry" / "packs.yaml"
        packs_path.write_text(
            yaml.safe_dump({"schema_version": 1, "packs": packs}, sort_keys=False),
            encoding="utf-8",
        )
        return validate_repository(root)

    def test_validate_repository_reports_missing_pack_closure_once(self) -> None:
        issues = self.validate_fixture(
            {"root": [], "child": ["root"]},
            [
                {
                    "id": "studio-core",
                    "description": "Fixture pack",
                    "skills": ["child"],
                    "depends_on": [],
                }
            ],
        )

        closure_messages = [
            issue.message
            for issue in issues
            if issue.code == "registry.pack.dependency.missing"
        ]
        self.assertEqual(
            ["pack studio-core is missing capability root required by child"],
            closure_messages,
        )

    def test_validate_repository_reports_cycle_and_unrelated_missing_closure(self) -> None:
        issues = self.validate_fixture(
            {"root": [], "child": ["root"]},
            [
                {
                    "id": "studio-core",
                    "description": "Fixture pack",
                    "skills": ["child"],
                    "depends_on": [],
                },
                {
                    "id": "cycle-a",
                    "description": "Cycle fixture",
                    "skills": [],
                    "depends_on": ["cycle-b"],
                },
                {
                    "id": "cycle-b",
                    "description": "Cycle fixture",
                    "skills": [],
                    "depends_on": ["cycle-a"],
                },
            ],
        )

        cycle_messages = [
            issue.message for issue in issues if issue.code == "registry.dependency.cycle"
        ]
        closure_messages = [
            issue.message
            for issue in issues
            if issue.code == "registry.pack.dependency.missing"
        ]
        self.assertEqual(["cycle-a -> cycle-b -> cycle-a"], cycle_messages)
        self.assertEqual(
            ["pack studio-core is missing capability root required by child"],
            closure_messages,
        )

    def test_validate_repository_deduplicates_malformed_relationships(self) -> None:
        cases = [
            ("base", "capability root depends_on must be a list"),
            ([7], "capability root depends_on[0] must be a nonblank string, got 7"),
        ]
        packs = [
            {
                "id": "studio-core",
                "description": "Fixture pack",
                "skills": ["root"],
                "depends_on": [],
            },
            {
                "id": "extra",
                "description": "Fixture pack",
                "skills": ["root"],
                "depends_on": [],
            },
        ]

        for malformed_dependencies, expected_message in cases:
            with self.subTest(malformed_dependencies=malformed_dependencies):
                issues = self.validate_fixture({"root": malformed_dependencies}, packs)
                schema_issues = [
                    issue
                    for issue in issues
                    if issue.code == "registry.schema" and issue.message == expected_message
                ]
                closure_messages = [
                    issue.message
                    for issue in issues
                    if issue.code == "registry.pack.dependency.missing"
                ]
                self.assertEqual(1, len(schema_issues))
                self.assertEqual(expected_message, schema_issues[0].message)
                self.assertEqual("registry", schema_issues[0].path.parent.name)
                self.assertEqual("capabilities.yaml", schema_issues[0].path.name)
                self.assertEqual([], closure_messages)

    def test_validate_repository_does_not_duplicate_covered_unknown_references(self) -> None:
        issues = self.validate_fixture(
            {"root": []},
            [
                {
                    "id": "studio-core",
                    "description": "Fixture pack",
                    "skills": ["missing"],
                    "depends_on": [],
                }
            ],
        )

        reference_messages = [
            issue.message for issue in issues if issue.code == "registry.reference.missing"
        ]
        self.assertEqual(["unknown capability: missing"], reference_messages)

    def test_validate_repository_classifies_duplicate_ids_as_schema_once(self) -> None:
        duplicate_pack = {
            "id": "studio-core",
            "description": "Fixture pack",
            "skills": ["root"],
            "depends_on": [],
        }
        issues = self.validate_fixture(
            {"root": []},
            [duplicate_pack, duplicate_pack.copy()],
        )

        schema_messages = [
            issue.message
            for issue in issues
            if issue.code == "registry.schema"
            and issue.message == "invalid or duplicate pack id: studio-core"
        ]
        closure_messages = [
            issue.message
            for issue in issues
            if issue.code == "registry.pack.dependency.missing"
        ]
        self.assertEqual(["invalid or duplicate pack id: studio-core"], schema_messages)
        self.assertEqual([], closure_messages)


if __name__ == "__main__":
    unittest.main()
