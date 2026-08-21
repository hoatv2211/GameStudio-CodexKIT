from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReviewContractTests(unittest.TestCase):
    def test_public_docs_do_not_advertise_unimplemented_or_unobserved_contracts(self) -> None:
        catalog = (ROOT / "docs" / "CATALOG.md").read_text(encoding="utf-8")
        adoption = (ROOT / "docs" / "adoption.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        landing = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        vietnamese_guide = (
            ROOT / "docs" / "huong-dan-su-dung-skill-agent.md"
        ).read_text(encoding="utf-8")
        wiki_guide = (
            ROOT / "docs" / "wiki-skill-agent-user-guide.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("skip intake and handoff", catalog)
        self.assertNotIn("plus lite mode for small read-only tasks", readme)
        self.assertNotIn(
            "Yes, all eight, on Windows and in CI on ubuntu + windows | `Verified`",
            adoption,
        )
        self.assertIn("local Windows", adoption)
        self.assertIn("docs/huong-dan-su-dung-skill-agent.md", readme)
        self.assertIn("docs/wiki-skill-agent-user-guide.md", readme)
        self.assertLessEqual(len(readme.split()), 1600)
        for phrase in (
            "AI agent skills",
            "Unity",
            "MMORPG",
            "Codex",
            "Hermes Agent",
            "49 canonical skills",
            "24 canonical agent roles",
            "306 deterministic eval cases",
        ):
            with self.subTest(readme_phrase=phrase):
                self.assertIn(phrase, readme)
        for removed_heading in (
            "## Unity/MMORPG Golden Paths",
            "## Role-first workflow",
            "## Advanced maintenance: packs and adapters",
            "## Governed evaluation",
            "## Repository layout",
            "## Local archive boundary",
        ):
            with self.subTest(removed_heading=removed_heading):
                self.assertNotIn(removed_heading, readme)
        self.assertIn("## Visual overview", readme)
        showcase_paths = tuple(
            f"docs/assets/showcase-handcrafted/slide-{index:02d}.webp"
            for index in range(1, 8)
        )
        for showcase_path in showcase_paths:
            with self.subTest(showcase_path=showcase_path):
                self.assertEqual(1, readme.count(showcase_path))
        self.assertNotIn(
            "docs/assets/showcase-handcrafted/slide-08.webp",
            readme,
        )
        self.assertGreaterEqual(readme.count('alt="MOStudio Kit'), 7)
        self.assertIn("flattened UI screenshot decomposition", catalog)
        self.assertIn("flattened UI screenshot decomposition", landing)
        self.assertIn("GitHub Wiki is a separate Git repository", wiki_guide)
        self.assertIn("blob/main/docs/CATALOG.md", wiki_guide)

        skill_ids = sorted(
            path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
        )
        role_ids = sorted(path.stem for path in (ROOT / "agents").glob("*.toml"))
        self.assertEqual(49, len(skill_ids))
        self.assertEqual(24, len(role_ids))
        for identifier in (*skill_ids, *role_ids):
            with self.subTest(identifier=identifier):
                self.assertIn(f"`{identifier}`", vietnamese_guide)
                self.assertIn(f"`{identifier}`", wiki_guide)

    def test_liveops_reference_uses_safe_config_and_prometheus_queries(self) -> None:
        reference = (
            ROOT / "skills" / "liveops-incident-response" / "references" / "commands.md"
        ).read_text(encoding="utf-8")

        self.assertIn("data_keys", reference)
        self.assertIn("--data-urlencode", reference)
        self.assertNotIn("get configmap game-config -o yaml | rg -v", reference)
        self.assertNotIn("http://prometheus:9090/api/v1/query?query=", reference)

    def test_unity_references_state_actual_runtime_and_serialization_boundaries(self) -> None:
        offline = (
            ROOT / "skills" / "unity-client-offline-debugging" / "references" / "commands.md"
        ).read_text(encoding="utf-8")
        ui = (
            ROOT / "skills" / "unity-ui-rendering-debugging" / "references" / "commands.md"
        ).read_text(encoding="utf-8")

        self.assertIn("BeforeSceneLoad", offline)
        self.assertIn("AfterSceneLoad", offline)
        self.assertIn("project-specific", offline)
        self.assertNotIn("runs before any scene `Awake`", offline)
        self.assertNotIn("m_Script:.*UIPanel", ui)
        self.assertIn("mDepth:", ui)
        self.assertIn("Resources.FindObjectsOfTypeAll", ui)
        self.assertIn("if (go == null)", ui)


if __name__ == "__main__":
    unittest.main()
