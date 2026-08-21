from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

from scripts.common import parse_frontmatter
from tests._meta.support import temporary_directory


ROOT = Path(__file__).resolve().parents[2]
class TemplateFinalizationTests(unittest.TestCase):
    def test_completed_documents_are_kept_out_of_the_public_template(self) -> None:
        self.assertFalse((ROOT / "PLAN_final.md").exists())
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".archive/", gitignore)

    def test_public_template_excludes_private_machine_and_project_identifiers(self) -> None:
        public_paths = [ROOT / "AGENTS.md", ROOT / "README.md"]
        public_paths.extend((ROOT / "docs").rglob("*.md"))
        public_paths.extend((ROOT / "workflows").rglob("*.md"))
        public_paths.extend((ROOT / "skills").glob("*/SKILL.md"))
        public_paths.extend((ROOT / "tests" / "studio_project_scaffold" / "fixtures").glob("*.json"))
        banned = (
            "C:/Users/",
            "C:\\Users\\",
            "D:/2026/",
            "D:\\2026\\",
        )
        private_project_hashes = {
            "d2838702a8908abd7de428a1bfc3b9f876c2cf774cffde2f451f5b4cfe336981",
            "c22af241b81fcd4db48a55f1f0c0ef86464dc2e0024467f5f0cda2b8b9e6f61c",
        }
        for path in public_paths:
            text = path.read_text(encoding="utf-8")
            for value in banned:
                self.assertNotIn(value, text, path)
            for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text):
                digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                self.assertNotIn(digest, private_project_hashes, path)
        for skill_path in (ROOT / "skills").glob("*/SKILL.md"):
            frontmatter, _body = parse_frontmatter(skill_path)
            self.assertEqual(
                "HoaTV Studio",
                frontmatter["metadata"]["studio"]["owner"],
                skill_path,
            )

    def test_active_entry_docs_and_skill_bodies_do_not_depend_on_roadmap(self) -> None:
        for relative in ("README.md", "AGENTS.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("PLAN_final.md", text, relative)
        for skill_path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            _frontmatter, body = parse_frontmatter(skill_path)
            self.assertNotIn("PLAN_final.md", body, skill_path.as_posix())

    def test_public_docs_expose_template_usage_and_honest_maturity(self) -> None:
        text = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "docs/architecture/overview.md",
                "docs/architecture/project-init-and-studio-expansion.md",
                "docs/adoption.md",
                "docs/authoring/skills.md",
                "docs/wiki-skill-agent-user-guide.md",
            )
        )
        for required in (
            "studio-core",
            "per-project",
            "evidence/local/",
            "BLOCKED",
            "experimental",
            ".archive/",
            "unittest discover",
        ):
            self.assertIn(required, text)
        self.assertNotIn("always-loaded root router", text)
        self.assertIn(
            "python -B scripts/generate_adapters.py . --target per-project --output D:/Games/MyMMO",
            text,
        )
        self.assertIn(
            '$report = python -B scripts/generate_adapters.py . --target per-project --output D:/Games/MyMMO | ConvertFrom-Json',
            text,
        )
        self.assertIn("$report.plan_digest", text)
        self.assertIn("--plan-digest $report.plan_digest", text)
        self.assertIn("leaves `.codex/config.toml` untouched", text)

    def test_project_bootstrap_requires_adapter_report_review_before_apply(self) -> None:
        text = (ROOT / "workflows" / "project-bootstrap.md").read_text(encoding="utf-8")
        self.assertIn("report-only", text)
        self.assertIn("Review the report before apply", text)
        self.assertIn("plan_digest", text)
        self.assertIn("--plan-digest", text)
        self.assertIn("manually reviewed and merged", text)
        self.assertIn("never overwrites `.codex/config.toml`", text)

    def test_canonical_project_scaffold_skill_owns_adapter_lifecycle(self) -> None:
        text = (ROOT / "skills" / "studio-project-scaffold" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "report-only first",
            "`plan_digest`",
            "`proposed`",
            "`mutation_report.operations`",
            "`collisions`",
            "`activated_roles`",
            "named reviewer",
            "backup root",
            "approved plan digest",
            "leaves `.codex/config.toml` untouched",
            "`.codex/agents.generated.toml`",
            "inert",
            "packaged generic agent templates",
            "profile specialists",
            "per-file ownership",
            "hash-safe uninstall",
            "`PARTIAL`",
            "`preserved_drift`",
            "`remaining_owned`",
            "manual recovery",
        ):
            self.assertIn(required, text)
        self.assertRegex(
            text.casefold(),
            r"(?s)report-only first.*apply.*named reviewer.*backup root.*approved plan digest",
        )

    def test_project_adapter_docs_expose_the_safe_lifecycle_contract(self) -> None:
        contracts = {
            "docs/architecture/overview.md": (
                "report-only by default",
                "reviewer",
                "backup root",
                "approved plan digest",
                "packaged generic agent templates",
                "profile specialist overlay",
                "leaves `.codex/config.toml` untouched",
                "inert activation",
                "Per-file ownership",
                "hash-safe uninstall",
                "`PARTIAL` recovery",
            ),
            "docs/authoring/skills.md": (
                "report-only by default",
                "named reviewer",
                "backup root",
                "approved plan digest",
                "packaged generic agent templates",
                "profile specialist overlay",
                "leaves `.codex/config.toml` untouched",
                "inert activation",
                "per-file ownership",
                "hash-safe uninstall",
                "`PARTIAL` recovery",
            ),
            "workflows/project-bootstrap.md": (
                "report-only by default",
                "named reviewer",
                "backup root",
                "approved plan digest",
                "packaged generic agent templates",
                "profile specialist overlay",
                "leaves `.codex/config.toml` untouched",
                "inert activation",
                "per-file ownership",
                "Hash-safe uninstall",
                "`PARTIAL` recovery",
            ),
        }
        forbidden_patterns = {
            "config overwrite": r"(?<!never )overwrit(?:e|es|ten)\s+`\.codex/config\.toml`",
            "immediate activation": r"activat\w*\s+immediately",
            "drift deletion": r"(?:delete|remove)\w*\s+(?:all\s+)?drifted",
            "apply gate bypass": (
                r"apply\s+without\s+(?:a\s+)?"
                r"(?:named reviewer|backup root|approved plan digest)"
            ),
        }
        for relative, required_markers in contracts.items():
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                for required in required_markers:
                    self.assertIn(required, text)
                for claim, pattern in forbidden_patterns.items():
                    self.assertNotRegex(text, pattern, (relative, claim))

    def test_authoring_docs_use_an_executable_plugin_validator_command(self) -> None:
        text = (ROOT / "docs" / "authoring" / "skills.md").read_text(encoding="utf-8")
        self.assertIn(
            'python "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" .',
            text,
        )
        self.assertNotIn("<CODEX_HOME>", text)

    def test_wiki_exposes_native_codex_plugin_install_lifecycle(self) -> None:
        text = (ROOT / "docs" / "wiki-skill-agent-user-guide.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "codex plugin marketplace add hoatv2211/GameStudio-CodexKIT",
            "npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -g -y",
            "/plugins",
            "codex plugin marketplace upgrade gamestudio-codex-kit",
            "codex plugin marketplace remove gamestudio-codex-kit",
            ".codex-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
        ):
            self.assertIn(required, text)

    def test_agents_defines_the_native_plugin_source_boundary(self) -> None:
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for required in (
            "Primary Distribution",
            "Hermes Agent",
            ".codex-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            "optional export artifacts",
        ):
            self.assertIn(required, text)

    def test_reproducible_verification_residue_is_not_distributed(self) -> None:
        self.assertFalse((ROOT / "evidence" / "template-verification").exists())
        self.assertTrue((ROOT / "evidence" / "example" / "verdict.md").is_file())

    def test_generated_adapters_do_not_package_archive_history(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            for target in ("hermes", "codex"):
                adapter = Path(temp) / target
                generate_adapter(ROOT, target, adapter)
                self.assertFalse((adapter / ".archive").exists())
                for path in adapter.rglob("*"):
                    self.assertNotIn(".archive", path.relative_to(adapter).parts)


if __name__ == "__main__":
    unittest.main()
