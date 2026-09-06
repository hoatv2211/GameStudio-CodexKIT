import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class CodeIntelligenceContractTests(unittest.TestCase):
    def test_one_provider_neutral_skill_owns_the_contract(self) -> None:
        self.assertTrue((SKILLS / "code-intelligence-contract" / "SKILL.md").is_file())
        for vendor_id in ("graphify", "gitnexus", "understand-anything", "codegraph"):
            self.assertFalse((SKILLS / vendor_id).exists(), vendor_id)

    def test_shared_skill_has_exact_canonical_sections(self) -> None:
        body = read("skills/code-intelligence-contract/SKILL.md")
        headings = re.findall(r"^## .+$", body, flags=re.MULTILINE)
        self.assertEqual(
            [
                "## Overview",
                "## When to use",
                "## When NOT to use",
                "## Required inputs and context discovery",
                "## Safety and risk level",
                "## Workflow",
                "## Provider roles",
                "## Evidence and output contract",
                "## Handoff contract",
                "## Pitfalls and anti-rationalization",
                "## Verification checklist",
                "## References and scripts",
                "## Negative scope",
            ],
            headings,
        )
        self.assertEqual(1, body.count("## Evidence and output contract"))

    def test_shared_skill_closes_freshness_and_empty_result_states(self) -> None:
        body = read("skills/code-intelligence-contract/SKILL.md")
        for phrase in (
            "STALE_HEAD",
            "STALE_WORKTREE",
            "PARTIAL_LANGUAGE",
            "SIDE_EFFECT_VIOLATION",
            "EMPTY_UNCERTAIN",
            "confidence=INFERRED",
            "No graph result is not proof",
            "source/test fallback",
            "reviewer",
            "repository, revision, worktree identity, capability, required languages, and artifacts",
            "exactly one resolved subject",
            "privacy-safe untracked content identity",
        ):
            self.assertIn(phrase, body)

    def test_shared_skill_separates_provider_roles_and_evidence_classes(self) -> None:
        body = read("skills/code-intelligence-contract/SKILL.md")
        for phrase in (
            "Graphify",
            "experimental opt-in default candidate",
            "never an automatic dependency or mutation gate",
            "GitNexus",
            "advanced optional",
            "cross-repository impact",
            "PDG",
            "taint",
            "terms review",
            "Understand Anything",
            "onboarding, architecture, and domain-flow",
            "semantic/LLM evidence",
            "CodeGraph",
            "legacy-compatible",
            "legacy caller-declared `FRESH`/`EXTRACTED`",
            "EXTRACTED",
            "REVIEWER_ACKNOWLEDGED_FALLBACK",
            "generated authorities",
            "NOT_APPLICABLE",
        ):
            self.assertIn(phrase, body)
        self.assertIn("Graph verdict remains BLOCKED", body)
        self.assertNotRegex(body, r"(?i)BLOCKED.{0,50}(?:becomes|counts as|return(?:s|ed)?)\s+PASS")

    def test_provider_selection_honors_opt_in_and_exact_eligibility(self) -> None:
        body = read("skills/code-intelligence-contract/SKILL.md")
        for phrase in (
            "USER_DISABLED",
            "recorded preference/opt-in",
            "probe installed provider version and index status without mutation",
            "repository scope",
            "repository/HEAD/worktree/language/side-effect binding",
            "exact required capability and language",
            "highest-priority `FRESH` eligible provider",
            "never silently substitute a weaker capability",
            "selection remains BLOCKED",
        ):
            self.assertIn(phrase, body)

    def test_reviewer_fallback_records_complete_safety_boundary(self) -> None:
        body = read("skills/code-intelligence-contract/SKILL.md")
        for phrase in (
            "Decision: `REVIEWER_ACKNOWLEDGED_FALLBACK`",
            "explicit missing graph coverage/blocker",
            "authoritative source owners",
            "known callers/consumers",
            "generated authorities or exact `NOT_APPLICABLE`",
            "focused test commands",
            "named reviewer",
            "residual risk",
            "existing risk, approval, backup, and restore gates",
            "unresolved generated, cross-repository, or dynamic boundary remains BLOCKED",
            "generated-source, dynamic-dispatch, language, repository, security, database, service, or release boundary",
            "if source/tests cannot cover any unresolved boundary, the owning workflow remains BLOCKED",
            "graph verdict stays BLOCKED",
            "all required source owners, known callers, known consumers",
        ):
            self.assertIn(phrase, body)

    def test_no_result_warning_is_exact_where_used(self) -> None:
        warning = "No graph result is not proof that no dependency exists."
        for path in (
            "skills/code-intelligence-contract/SKILL.md",
            "skills/evidence-first-debugging/SKILL.md",
            "agents/investigator.toml",
        ):
            self.assertIn(warning, read(path), path)

    def test_consumers_use_provider_neutral_phrase_contracts(self) -> None:
        intake = read("skills/studio-project-intake/SKILL.md")
        debugging = read("skills/evidence-first-debugging/SKILL.md")
        mutation = read("skills/safe-project-mutation/SKILL.md")
        review = read("skills/review-swarm/SKILL.md")

        self.assertIn("provider/version, repository/revision/worktree binding, index state, capability, required languages, artifacts, side effects, and blocker", intake)
        self.assertIn("The graph lane is optional", intake)
        self.assertIn("intake may still succeed when the graph lane is BLOCKED", intake)
        self.assertIn("only when graph context or capability is requested or materially useful", intake)
        self.assertIn("provider existence alone never triggers", intake)
        self.assertIn("Pure intake remains intake", intake)
        self.assertIn("optional graph lane may stay absent or BLOCKED without failing intake", intake)
        self.assertIn("data and control path", debugging)
        self.assertIn("Source, logs, tests, and runtime evidence own the root-cause verdict", debugging)
        self.assertIn("pre-change impact query", mutation)
        self.assertIn("REVIEWER_ACKNOWLEDGED_FALLBACK", mutation)
        self.assertIn("reviewer", mutation)
        self.assertIn("source owners", mutation)
        self.assertIn("optional independent dependency/impact lane", review)
        self.assertIn("read-only", review)
        self.assertIn("cannot issue runtime PASS", review)
        self.assertIn("owns source disagreements and missing coverage", review)

    def test_consumers_do_not_embed_vendor_commands(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "skills/studio-project-intake/SKILL.md",
                "skills/evidence-first-debugging/SKILL.md",
                "skills/safe-project-mutation/SKILL.md",
                "skills/review-swarm/SKILL.md",
                "skills/studio-project-scaffold/SKILL.md",
                "agents/implementer.toml",
                "agents/verifier.toml",
                "agents/investigator.toml",
            )
        )
        self.assertNotRegex(
            combined,
            r"(?i)\b(?:graphify|gitnexus|understand anything|codegraph)\s+(?:explore|query|index|install|init|scan|analyze)\b",
        )

    def test_canonical_agents_enforce_pre_and_post_change_contracts(self) -> None:
        implementer = read("agents/implementer.toml")
        verifier = read("agents/verifier.toml")
        investigator = read("agents/investigator.toml")

        for phrase in ("fresh impact artifact", "recorded graph blocker", "approved fallback", "query ID", "graph status", "affected paths", "generated authorities", "approved write scope", "escalate newly discovered owners before editing"):
            self.assertIn(phrase, implementer)
        for phrase in ("fresh post-change identity", "same query ID", "changed paths", "pre-change expectations", "added, removed, and unexpected", "compare_impact", "graph disagreement", "source and tests", "stale post-change graph remains BLOCKED"):
            self.assertIn(phrase, verifier)
        for phrase in ("Graph path:", "Approved fallback path:", "REVIEWER_ACKNOWLEDGED_FALLBACK", "post graph lane BLOCKED", "original blocker, missing coverage, and residual risk", "authoritative source, tests, and generated ownership", "never fabricate a query or PASS"):
            self.assertIn(phrase, verifier)
        for phrase in ("provider/version/index identity", "ambiguity", "limitations", "source-confirmed owner paths"):
            self.assertIn(phrase, investigator)

    def test_routing_fixture_has_required_pressure_and_collision_cases(self) -> None:
        payload = json.loads(read("evals/routing/code-intelligence-contract.json"))
        self.assertEqual("code-intelligence-contract", payload["target_skill"])
        by_type = {kind: [case for case in payload["cases"] if case["type"] == kind] for kind in ("positive", "negative", "collision")}
        self.assertGreaterEqual(len(by_type["positive"]), 3)
        self.assertGreaterEqual(len(by_type["negative"]), 4)
        self.assertGreaterEqual(len(by_type["collision"]), 1)
        positives = "\n".join(case["prompt"] for case in by_type["positive"])
        negatives = "\n".join(case["prompt"] for case in by_type["negative"])
        collisions = "\n".join(case["prompt"] for case in by_type["collision"])
        self.assertIn("inferred AST", positives)
        self.assertIn("Snapshot", positives)
        self.assertIn("empty", positives)
        self.assertIn("not proof", positives)
        self.assertIn("pure intake", negatives)
        self.assertIn("pure debugging", negatives)
        self.assertIn("shared contract first", collisions)
        self.assertIn("explicit handoff", collisions)
        self.assertIn("safe-project-mutation", collisions)

    def test_graphify_dogfood_case_study_preserves_snapshot_blockers(self) -> None:
        text = read("docs/case-studies/graphify-code-intelligence-dogfood.md")
        for phrase in (
            "Graphify 0.9.50",
            "AST-only",
            "authorized private Unity project",
            "88,955",
            "244,284",
            "84.85%",
            "sample precision 100%",
            "confidence=INFERRED",
            "generated",
            "Lua",
            "C++",
            "cross-repository",
            "BLOCKED",
            "experimental",
            "opt-in",
            "The owner-constrained second private project is excluded; no data was accessed or reported.",
            "Verified",
            "Snapshot",
            "Unverified",
            "2026-08-26",
            "33 known C# TaskChangeNotify constructor sites",
            "28 matched",
            "0 extras",
            "28/28=100%",
            "28/33=84.85%",
            "does not independently prove current freshness",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

        self.assertRegex(
            text,
            r"(?m)^- Snapshot: observed snapshot size was 88,955 nodes and 244,284 edges\.$",
        )
        self.assertRegex(
            text,
            r"(?m)^- Snapshot of a locally Verified comparison:.*33 known C# TaskChangeNotify constructor sites.*28 matched.*0 extras.*sample precision 100% \(28/28=100%\).*recall 28/33=84\.85%\.$",
        )
        self.assertRegex(
            text,
            r"(?m)^- Snapshot: sampled misses included generated wrappers.*generated-Lua.*Lua-handler path\.",
        )
        for blocked_pattern in (
            r"(?m)^- BLOCKED:.*Generated, Lua, and cross-language coverage",
            r"(?m)^- BLOCKED: C\+\+ coverage",
            r"(?m)^Cross-repository accuracy is BLOCKED",
            r"(?m)^Graphify remains experimental and opt-in\. Deep integration is BLOCKED\.",
        ):
            self.assertRegex(text, blocked_pattern)
        self.assertNotRegex(text, r"(?im)^\s*(?:-\s*Verified:|\|\s*Verified\s*\|)")

    def test_graphify_dogfood_case_study_is_sanitized(self) -> None:
        text = read("docs/case-studies/graphify-code-intelligence-dogfood.md")
        self.assertNotRegex(text, r"(?i)(?:D:|C:)[\\/]")
        self.assertNotRegex(
            text,
            r"(?im)^\s*(?:graphify\s+(?:init|index|scan|analyze)|git\s+(?:clean|reset)|rm\s|rmdir\s|del\s|Remove-Item\b)",
        )
        self.assertNotRegex(text, r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]")
        self.assertNotRegex(text, r"(?i)untracked\s+(?:file|filename|path)")
        self.assertNotIn("```", text)

    def test_public_dogfood_materials_use_only_generic_private_project_wording(self) -> None:
        public_paths = (
            "docs/case-studies/graphify-code-intelligence-dogfood.md",
            "tests/governance/test_code_intelligence_contracts.py",
            "skills/code-intelligence-contract/SKILL.md",
            "docs/superpowers/plans/2026-08-26-shared-code-intelligence.md",
            "docs/superpowers/specs/2026-08-26-code-intelligence-design.md",
        )
        allowed_statement = "The owner-constrained second private project is excluded; no data was accessed or reported."
        private_marker = allowed_statement.split(" is excluded", 1)[0].removeprefix("The ")
        for path in public_paths:
            text = read(path)
            with self.subTest(path=path):
                self.assertNotRegex(text, r"(?i)(?:D:|C:)[\\/]")
                private_project_lines = [
                    line for line in text.splitlines()
                    if private_marker in line
                ]
                for line in private_project_lines:
                    self.assertIn(allowed_statement, line)
                    self.assertNotRegex(line, r"\d")
                    self.assertNotRegex(line, r"(?i)(?:D:|C:)[\\/]")
                    self.assertNotRegex(
                        line,
                        r"(?i)\b(?:BLOCKED|PASS|FAIL|failure|restructuring|metric|node|edge|revision|version|identity)\b",
                    )

    def test_public_dogfood_summaries_keep_observations_at_snapshot(self) -> None:
        specification = read("docs/superpowers/specs/2026-08-26-code-intelligence-design.md")
        plan = read("docs/superpowers/plans/2026-08-26-shared-code-intelligence.md")
        self.assertRegex(
            specification,
            r"(?m)^- Snapshot: the authorized private Unity project produced.*missed generated wrapper calls.*generated-Lua.*Lua-handler path\.$",
        )
        self.assertRegex(
            plan,
            r"(?m)^- Record the authorized private Unity project node/edge counts, C# sample precision/recall, generated wrapper misses, cross-language miss, parser gaps, and generated-authority gap as `Snapshot`\.$",
        )


if __name__ == "__main__":
    unittest.main()
