# Lean SEO README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the technical 3,963-word README with a focused, search-friendly product entry point while preserving detailed routing and operating guidance in maintained docs.

**Architecture:** `README.md` becomes the concise discovery and quick-start surface. `docs/wiki-skill-agent-user-guide.md` retains the detailed Golden Path and role-first routing contract, while governance tests enforce the new ownership boundary and prevent README growth from drifting back.

**Tech Stack:** GitHub Flavored Markdown, Python 3.11 `unittest`, repository-local validation scripts.

---

### Task 1: Move the public routing contract out of README

**Files:**
- Modify: `docs/wiki-skill-agent-user-guide.md`
- Modify: `tests/studio_experience/test_studio_experience.py`
- Modify: `tests/packaging/test_skill_resources.py`
- Modify: `tests/governance/test_template_finalization.py`

- [ ] **Step 1: Add a Wiki section for Golden Paths and role-first routing**

Add a section after Quick start that lists all eight route families:

```text
Project adoption and routing
Local environment recovery
Unity client entry recovery
C++ server failure recovery
Unity UI and localization
Unity build and asset integrity
Lua contract and server authority
Data and live release safety
```

Retain the four canonical role/request examples for Developer Diagnose, QA Verify, Producer Plan Change, and LiveOps Handle Incident. State that `READY` is a planning state and never mutation authority or runtime PASS.

- [ ] **Step 2: Point the route documentation test at the Wiki guide**

Change `test_readme_examples_and_eight_family_catalog_match_current_routes` so its detailed family and role assertions read `docs/wiki-skill-agent-user-guide.md`. Rename the test to describe the Wiki contract. Keep README covered separately by the lean-entry-point test in Task 2.

- [ ] **Step 3: Run the focused route documentation test**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience.StudioExperienceDocumentationContractTests
```

Expected: exit `0`; all documentation contract tests pass.

### Task 2: Establish a lean README regression contract

**Files:**
- Modify: `tests/governance/test_review_contracts.py`
- Modify: `README.md`

- [ ] **Step 1: Add assertions for the new README boundary**

Extend the existing public-doc contract to require:

```python
self.assertLessEqual(len(readme.split()), 1600)
self.assertIn("AI agent skills", readme)
self.assertIn("Unity", readme)
self.assertIn("MMORPG", readme)
self.assertIn("Codex", readme)
self.assertIn("Hermes Agent", readme)
self.assertIn("docs/wiki-skill-agent-user-guide.md", readme)
self.assertIn("docs/huong-dan-su-dung-skill-agent.md", readme)
for removed_heading in (
    "## Unity/MMORPG Golden Paths",
    "## Role-first workflow",
    "## Advanced maintenance: packs and adapters",
    "## Governed evaluation",
    "## Repository layout",
    "## Local archive boundary",
):
    self.assertNotIn(removed_heading, readme)
```

- [ ] **Step 2: Run the contract and observe the current README fail**

Run:

```text
python -B -m unittest tests.governance.test_review_contracts
```

Expected before the rewrite: FAIL because the current README has 3,963 words and contains the removed technical headings.

- [ ] **Step 3: Rewrite README as a product landing page**

Keep these sections, in this order:

```text
# MOStudio Kit — AI Agent Skills for Unity and MMORPG Operations
## Why MOStudio Kit
## What you can do
## Install
## Quick start
## Evidence, not confidence
## Documentation
## Project status
## License
```

Keep one banner, the four catalog badges, a natural opening summary, six representative requests, the Codex and Hermes install commands, one bounded prompt example, a compact evidence summary, descriptive documentation links, contribution/help links, and the MIT license. Link detailed operations instead of repeating adapter, scaffold, mutation, evaluation, archive, and authoring procedures.

- [ ] **Step 4: Run the README contract again**

Run:

```text
python -B -m unittest tests.governance.test_review_contracts tests.packaging.test_codex_plugin tests.studio_experience.test_studio_experience.StudioExperienceDocumentationContractTests
```

Expected: exit `0`; README packaging, counts, links, and public routing docs remain consistent.

### Task 3: Verify repository documentation integrity

**Files:**
- Verify: `README.md`
- Verify: `docs/wiki-skill-agent-user-guide.md`
- Verify: `tests/governance/test_review_contracts.py`
- Verify: `tests/studio_experience/test_studio_experience.py`

- [ ] **Step 1: Check word count, headings, and links**

Run:

```powershell
(Get-Content -Raw README.md | Measure-Object -Word -Line)
rg -n "^#{1,3} |docs/.*\.md|codex plugin|npx skills add" README.md
```

Expected: at most 1,600 words, one H1, concise H2 sections, and descriptive links to maintained docs.

- [ ] **Step 2: Run the required local gates**

Run:

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
git diff --check
```

Expected: every command exits `0`. Remote CI remains unverified until the branch is pushed.

- [ ] **Step 3: Inspect the final diff and preserve unrelated work**

Run:

```text
git diff -- README.md docs/wiki-skill-agent-user-guide.md tests/governance/test_review_contracts.py tests/studio_experience/test_studio_experience.py
git status --short --untracked-files=all
```

Expected: only the owned README/docs/test changes from this plan are attributable to this task; all pre-existing work remains present. Commit and push are intentionally omitted because repository `commit_policy` is `ask`.

### Task 4: Add the approved visual overview

**Files:**
- Modify: `README.md`
- Modify: `tests/governance/test_review_contracts.py`
- Reference: `docs/assets/showcase-handcrafted/slide-01.webp` through `slide-07.webp`

- [ ] **Step 1: Lock the image set in the README contract**

Require the `Visual overview` heading, all seven approved relative image paths,
unique descriptive alt text, and the absence of `slide-08.webp`.

- [ ] **Step 2: Verify the contract fails before the README edit**

Run `python -B -m unittest tests.governance.test_review_contracts` and expect a
failure because the lean README does not yet contain the showcase images.

- [ ] **Step 3: Add the approved layout**

Insert one full-width hero followed by three two-column image rows after
`Why MOStudio Kit`. Reuse existing WebP assets and keep captions concise.

- [ ] **Step 4: Verify docs and repository gates**

Run the focused README/packaging contracts, full unittest discovery, all local
gates from `AGENTS.md`, originality audit, and `git diff --check`. Commit and
push remain outside this task.
