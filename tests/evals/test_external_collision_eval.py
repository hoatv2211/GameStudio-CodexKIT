from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from tests._meta.support import temporary_directory, write_registries, write_skill


class ExternalCollisionEvalTests(unittest.TestCase):
    def test_external_catalog_competitors_must_not_outrank_internal_skill(self) -> None:
        from scripts.external_collision_eval import evaluate_external_collisions

        with temporary_directory() as temp:
            root = Path(temp)
            write_skill(
                root,
                "unity-build-proof",
                description="Use when Unity batchmode BuildPipeline Editor.log and player artifact verification are required.",
            )
            write_registries(root, ["unity-build-proof"])
            fixture = root / "evals" / "external-catalog" / "cases.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                json.dumps(
                    {
                        "external_skills": [
                            {
                                "id": "generic-build-helper",
                                "description": "Use when a software build command or CI job needs general assistance.",
                            }
                        ],
                        "cases": [
                            {
                                "id": "unity-batchmode-vs-generic-build",
                                "prompt": "Verify Unity batchmode BuildPipeline Editor.log and the generated player artifact.",
                                "expected_skill": "unity-build-proof",
                                "must_beat": ["generic-build-helper"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = evaluate_external_collisions(root, fixture)

            self.assertEqual("PASS", report["verdict"])
            self.assertEqual(1, report["passed"])
            self.assertEqual([], report["failures"])

    def test_external_catalog_discovery_excludes_archive_and_generated_trees(self) -> None:
        from scripts.external_collision_eval import _external_root_descriptions

        with temporary_directory() as temp:
            external_root = Path(temp) / "external"
            active = external_root / "skills" / "active-skill" / "SKILL.md"
            archived = external_root / "archive" / "old-skill" / "SKILL.md"
            generated = external_root / "adapters" / "generated-skill" / "SKILL.md"
            for path, name in (
                (active, "active-skill"),
                (archived, "old-skill"),
                (generated, "generated-skill"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"---\nname: {name}\ndescription: Use when exercising {name}.\n---\n",
                    encoding="utf-8",
                )

            descriptions, errors = _external_root_descriptions([external_root])

            self.assertEqual([], errors)
            self.assertEqual(1, len(descriptions))
            self.assertIn("external-1-skills-active-skill", descriptions)

    def test_repository_external_catalog_fixture_passes(self) -> None:
        from scripts.external_collision_eval import evaluate_external_collisions

        root = Path(__file__).resolve().parents[2]
        report = evaluate_external_collisions(root)
        self.assertEqual("PASS", report["verdict"], report["failures"])
        self.assertGreaterEqual(report["total"], 10)

    def test_repository_external_catalog_fixture_matches_schema(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "evals" / "schema" / "external-catalog.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((root / "evals" / "external-catalog" / "cases.json").read_text(encoding="utf-8"))
        jsonschema.validate(fixture, schema)

    def test_live_external_root_can_expose_a_real_rank_one_collision(self) -> None:
        from scripts.external_collision_eval import evaluate_external_collisions

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            external_root = Path(temp) / "installed-skills"
            write_skill(
                root,
                "unity-build-proof",
                description="Use when Unity batchmode BuildPipeline Editor.log and player artifact verification are required.",
            )
            write_registries(root, ["unity-build-proof"])
            fixture = root / "evals" / "external-catalog" / "cases.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                json.dumps(
                    {
                        "external_skills": [
                            {"id": "generic-helper", "description": "Use when general software help is needed."}
                        ],
                        "cases": [
                            {
                                "id": "live-collision",
                                "prompt": "Unity batchmode BuildPipeline Editor.log generated player artifact verification",
                                "expected_skill": "unity-build-proof",
                                "must_beat": ["generic-helper"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            competitor = external_root / "unity-build-competitor" / "SKILL.md"
            competitor.parent.mkdir(parents=True)
            competitor.write_text(
                "---\nname: unity-build-competitor\ndescription: Use when Unity batchmode BuildPipeline Editor.log generated player artifact verification is required.\n---\n",
                encoding="utf-8",
            )

            report = evaluate_external_collisions(root, fixture, [external_root])

            self.assertEqual("FAIL", report["verdict"])
            self.assertEqual("external-1-unity-build-competitor", report["failures"][0]["actual"])


if __name__ == "__main__":
    unittest.main()
