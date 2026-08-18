# Evidence-Backed Maturity Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Replace implicit maturity labels with a validated, per-skill promotion record that can advance skills only from fresh, hashed evidence.

**Architecture:** Add a repository-level promotion evidence registry referencing dogfood profiles, deterministic gates, behavior/pressure/Tier-B status, owner/reviewer, runtime targets, and rollback. Validation checks records and frontmatter/registry maturity agreement; catalog audit rechecks every referenced artifact and prevents stale or unsupported beta/stable/release labels.

**Tech Stack:** Python, YAML/JSON, SHA-256, existing `validate.py` and `catalog_audit.py` gates, `unittest`.

---

### Task 1: Define promotion evidence schema and loader

**Files:**
- Create: `registry/promotion-evidence.yaml`
- Create: `evals/schema/promotion-evidence.schema.json`
- Create: `scripts/promotion_evidence.py`
- Test: `tests/governance/test_promotion_evidence.py`

- [ ] **Step 1: Write failing tests for target transitions, required fields, profile/case references, digest validation, rollback text, and expiry.**

```python
def test_experimental_to_beta_requires_profile_and_artifacts(self):
    record = valid_record(target="beta")
    self.assertEqual([], validate_promotion_record(record, known_skills={"localization-authority-audit"}, known_profiles={"fpc-global-localization-static"}))

def test_release_requires_runtime_matrix_and_rollback(self):
    record = valid_record(target="release", runtime_targets=[])
    self.assertIn("runtime_targets", validate_promotion_record(record, ...)[0])
```

- [ ] **Step 2: Run the focused tests and verify the loader is missing.**

- [ ] **Step 3: Implement exact allowed transitions `experimental -> beta -> stable -> release`; reject skipped levels, unknown skills/profiles/cases, missing reviewer/owner/review date/restore, empty artifacts, and SHA-256 drift.**

- [ ] **Step 4: Add a seed registry containing no fabricated promotion records and a documented example schema comment-free record only in tests.**

- [ ] **Step 5: Run focused governance tests and expect PASS for valid records and FAIL for every invalid mutation.**

### Task 2: Enforce maturity in repository validation

**Files:**
- Modify: `scripts/validate.py`
- Modify: `registry/capabilities.yaml`
- Test: `tests/_meta/test_validate.py`

- [ ] **Step 1: Add failing tests that mark a skill `beta`, `stable`, or `release` without a matching promotion record and expect a dedicated validation issue.**
- [ ] **Step 2: Run the tests and confirm current validator accepts the unsupported maturity.**
- [ ] **Step 3: Load promotion evidence during `_validate_registries`; require a matching record at or above the capability maturity, matching skill frontmatter, and exact artifact bindings. Add `release` to `MATURITY_LEVELS` while retaining `deprecated` and `archived` as terminal states.**
- [ ] **Step 4: Keep all current capabilities experimental until fresh evidence exists; do not bulk-promote the catalog.**
- [ ] **Step 5: Run `python -B -m unittest tests._meta.test_validate -v` and `python -B scripts/validate.py .`; expect no maturity issue for existing records.**

### Task 3: Make catalog audit promotion-aware

**Files:**
- Modify: `scripts/catalog_audit.py`
- Modify: `docs/authoring/skills.md`
- Test: `tests/governance/test_governance.py`

- [ ] **Step 1: Add failing tests for stale promotion artifacts, wrong profile case coverage, and a valid beta record supported by the FPC static profile.**
- [ ] **Step 2: Run the tests to observe missing promotion checks.**
- [ ] **Step 3: Add `promotion_evidence` audit output with `verified`, `stale`, `invalid`, and `unsupported` lists; require fresh strict profile results and preserve `BLOCKED` as `BLOCKED`.**
- [ ] **Step 4: Make promotion readiness per skill and target, never a catalog-wide switch; document the evidence ladder and why FPC cannot promote runtime/build/release skills.**
- [ ] **Step 5: Run existing governance tests plus `python -B scripts/catalog_audit.py .`; report actual status without relabeling missing Tier-B/behavior/pressure evidence.**

### Task 4: Produce an evidence report for the current rollout

**Files:**
- Create: `evidence/local/promotion-rollout.json` (generated, ignored)
- Modify: `docs/authoring/skills.md`

- [ ] **Step 1: Run the deterministic local gates and the FPC static profile.**
- [ ] **Step 2: Generate a report listing skills eligible for beta, skills still experimental, and the exact blockers for stable/release.**
- [ ] **Step 3: Verify hashes and status with `python -B scripts/catalog_audit.py .`; keep the report under ignored local evidence and do not claim any unsupported release promotion.**

