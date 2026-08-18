# Kit Release Safety Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unsupported PASS paths and unsafe mutation/generator behavior before distributing plugin version `1.3.3`.

**Architecture:** Keep canonical logic in root `scripts/`, enforce evidence and path boundaries before state changes, and regenerate bundled skill helpers from `registry/skill-resources.yaml`. Preserve diagnostic compatibility for legacy BLOCKED dogfood arrays while requiring the new strict wrapper for promotion evidence.

**Tech Stack:** Python 3.11, standard-library `unittest`, PyYAML, jsonschema, JSON Schema Draft 2020-12, GitHub Actions repository gates.

---

### Task 1: Make Atomic Replacement Retry Concurrency-Safe

**Files:**
- Modify: `tests/safe_project_mutation/test_safe_mutation.py`
- Modify: `scripts/safe_mutation.py`
- Generate: `skills/safe-project-mutation/scripts/safe_mutation.py`
- Generate: `skills/studio-project-scaffold/scripts/safe_mutation.py`

- [ ] **Step 1: Write failing update/create race and manifest retry tests**

Add tests that patch target replacement so the first attempt changes the target and raises `PermissionError`. Assert update and create mutations raise, preserve the concurrent content, and do not report `applied`. Add a manifest test that raises once while writing the `applied` state and then succeeds.

- [ ] **Step 2: Run the focused suite and verify RED**

Run: `python -B -m unittest tests.safe_project_mutation.test_safe_mutation`

Expected: the race tests show concurrent content is overwritten and the manifest retry test raises `PermissionError`.

- [ ] **Step 3: Implement pre-attempt validation and reusable bounded replacement**

Change the helper contract to accept a replace callable and optional pre-attempt callback:

```python
def _replace_with_retry(
    replace: Callable[[Path, Path], None],
    source: Path,
    target: Path,
    *,
    before_attempt: Callable[[], None] | None = None,
) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        if before_attempt is not None:
            before_attempt()
        try:
            replace(source, target)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))
```

Use `_ATOMIC_REPLACE` for manifest writes. For target writes, pass `os.replace` and a callback that reruns `_assert_safe_components` and `_assert_target_pre_state` before every attempt.

- [ ] **Step 4: Run the focused suite and verify GREEN**

Run: `python -B -m unittest tests.safe_project_mutation.test_safe_mutation`

Expected: all safe-mutation tests pass.

- [ ] **Step 5: Regenerate bundled copies and verify synchronization**

Run: `python -B scripts/sync_skill_resources.py .`

Run: `python -B scripts/sync_skill_resources.py . --check`

Expected: both bundled copies match the canonical helper and check reports zero generated files needed.

### Task 2: Remove Vacuous Release-Preflight PASS

**Files:**
- Modify: `tests/p2/test_production_tools.py`
- Modify: `scripts/release_preflight.py`
- Generate: `skills/release-candidate-preflight/scripts/release_preflight.py`

- [ ] **Step 1: Write failing release evidence tests**

Cover empty checks, missing mandatory IDs, duplicate IDs, missing evidence root, traversal, missing files, malformed PASS metadata, and a complete valid mandatory set. Valid PASS fixtures create real files below a temporary evidence root.

- [ ] **Step 2: Run the focused suite and verify RED**

Run: `python -B -m unittest tests.p2.test_production_tools`

Expected: empty and placeholder-only input incorrectly PASS, and the complete structured fixture is unsupported.

- [ ] **Step 3: Implement strict default gate and evidence validation**

Keep `evaluate_release_preflight(checks, *, evidence_root=None, required_checks=REQUIRED_RELEASE_CHECKS)`. Require unique IDs, the mandatory gate set, valid statuses, real evidence files under the approved root, PASS command/exit/timestamp/owner fields, and reasons for FAIL/BLOCKED. Use verdict precedence `FAIL` then `BLOCKED` then `PASS`.

- [ ] **Step 4: Run focused tests and regenerate the bundled helper**

Run: `python -B -m unittest tests.p2.test_production_tools`

Run: `python -B scripts/sync_skill_resources.py .`

Expected: focused tests pass and the release skill helper is synchronized.

### Task 3: Enforce Strict, Artifact-Bound Dogfood Evidence

**Files:**
- Modify: `evals/schema/dogfood-result.schema.json`
- Modify: `scripts/dogfood_eval.py`
- Modify: `scripts/catalog_audit.py`
- Modify: `tests/evals/test_dogfood_eval.py`
- Modify: `tests/governance/test_governance.py`
- Modify: `docs/authoring/dogfood.md`
- Modify: `README.md`

- [ ] **Step 1: Write failing strict-schema and artifact tests**

Require an object root with `results`, `additionalProperties: false`, and equality between every object schema's property names and required names. Add evaluation failures for unknown fields, non-string paths, traversal, missing files, and SHA-256 mismatch. Update the positive fixture to create real hashed artifacts. Add legacy BLOCKED diagnostic and legacy summary-refusal coverage.

- [ ] **Step 2: Write failing catalog artifact integrity tests**

Create a dogfood summary with an approved artifact root and digest, assert it is accepted, then delete or modify the artifact and assert catalog audit marks the summary invalid.

- [ ] **Step 3: Run focused suites and verify RED**

Run: `python -B -m unittest tests.evals.test_dogfood_eval tests.governance.test_governance`

Expected: current array schema, nonexistent artifacts, and catalog string-only checks fail the new assertions.

- [ ] **Step 4: Implement strict schema, normalization, and integrity checks**

Use this root contract:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["results"],
  "properties": {
    "results": {"type": "array", "items": {"$ref": "#/$defs/result"}}
  }
}
```

Make every result property required and nullable where BLOCKED/FAIL may omit a value. Artifact entries require `kind`, relative `path`, and `sha256`. Validate wrapper input with `jsonschema`, normalize legacy arrays only for diagnostic evaluation, and prohibit legacy summary generation. Resolve artifacts under `artifact_root`, reject escapes, require files, and verify hashes. Persist `artifact_root` in summaries and repeat existence/hash verification in catalog audit.

- [ ] **Step 5: Update authoring documentation**

Document 12 scenarios, the `results` wrapper, artifact hashes, `--artifact-root`, legacy diagnostic behavior, and the `jsonschema` full-clone dependency.

- [ ] **Step 6: Run focused suites and verify GREEN**

Run: `python -B -m unittest tests.evals.test_dogfood_eval tests.governance.test_governance`

Expected: all dogfood and governance tests pass.

### Task 4: Refuse Unsafe Generator Outputs and Unmanaged Deletion

**Files:**
- Modify: `tests/packaging/test_packs_adapters.py`
- Modify: `scripts/generate_adapters.py`
- Modify: `scripts/build_packs.py`

- [ ] **Step 1: Write failing generator safety tests**

Use synthetic temporary roots to prove standard adapter and pack output inside a canonical skill source is rejected before the tree digest changes. Add a pack rerun fixture with an unmanaged note containing the marker in its body and assert the note survives refusal. Add parser-valid frontmatter variants and assert normalized generated frontmatter.

- [ ] **Step 2: Run packaging tests and verify RED**

Run: `python -B -m unittest tests.packaging.test_packs_adapters`

Expected: overlap mutates the temporary source tree, marker-in-body is deleted, and delimiter variants are rejected or malformed.

- [ ] **Step 3: Implement disjoint-output and exact-ownership preflights**

Add a shared local helper in each generator that rejects output equal to, below, or above any source root before clearing or creating directories. Replace substring marker checks with format-aware exact header checks and parsed manifest ownership. Normalize parser-valid opening delimiters to `---` plus the generated marker.

- [ ] **Step 4: Run packaging tests and verify GREEN**

Run: `python -B -m unittest tests.packaging.test_packs_adapters`

Expected: packaging tests pass without source-tree residue.

### Task 5: Version, Synchronize, and Verify the Repository

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `tests/packaging/test_codex_plugin.py`
- Verify all changed paths from Tasks 1-4

- [ ] **Step 1: Change the version assertion to `1.3.3` and verify RED**

Run: `python -B -m unittest tests.packaging.test_codex_plugin`

Expected: FAIL while plugin metadata remains `1.3.2`.

- [ ] **Step 2: Bump plugin metadata and verify GREEN**

Set `.codex-plugin/plugin.json` to `1.3.3`.

Run: `python -B -m unittest tests.packaging.test_codex_plugin`

Expected: PASS.

- [ ] **Step 3: Run resource synchronization and the full test suite**

Run: `python -B scripts/sync_skill_resources.py . --check`

Run: `python -B -m unittest discover -s tests -p "test_*.py"`

Expected: zero synchronization drift and all tests pass, with only documented skips.

- [ ] **Step 4: Run all local gates**

Run the eight commands listed under `AGENTS.md` Local Gates, then `git diff --check`.

Expected: every deterministic gate exits zero.

- [ ] **Step 5: Run lifecycle and dogfood audits honestly**

Run `scripts/check_originality.py`, `scripts/catalog_audit.py`, and dogfood evaluation against the existing FPC result artifact.

Expected: deterministic validation remains green; unavailable external evidence remains BLOCKED rather than PASS. Legacy FPC BLOCKED results remain diagnostic and cannot create promotion summaries.

- [ ] **Step 6: Review exact diff and hand off without committing**

Confirm only task-owned canonical files, regenerated copies, tests, docs, spec, and plan changed. Report commands, exit codes, remaining BLOCKED evidence, and no-commit status.
