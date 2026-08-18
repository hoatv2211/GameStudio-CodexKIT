# KIT Release 90+ Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the current P1/P2 release blockers and collect real FPC Unity evidence so GameStudio-CodexKIT can earn a defensible 90+ production-readiness score.

**Architecture:** Keep root scripts canonical, use transactional journals/staging for filesystem changes, use one strict artifact contract for dogfood and promotion, and pin Unity MCP to the FPC project through the configured relay. Each task follows red-green TDD and preserves the existing dirty worktrees.

**Tech Stack:** Python 3.11+, `unittest`, PyYAML, jsonschema, SHA-256 evidence manifests, Windows atomic rename semantics, Unity 6000.3.10f1, MCP streamable HTTP/stdio relay.

---

### Task 1: Make Restore Transactional And Resumable

**Files:**
- Modify: `tests/safe_project_mutation/test_safe_mutation.py`
- Modify: `scripts/safe_mutation.py`
- Generate: `skills/safe-project-mutation/scripts/safe_mutation.py`
- Generate: `skills/studio-project-scaffold/scripts/safe_mutation.py`

- [ ] **Step 1: Add failing concurrent and partial-restore tests**

Add tests that call `restore_mutation()` with two operations and inject each of these conditions:

```python
def test_restore_preserves_create_target_changed_after_preflight(self) -> None:
    # Change the created target after validation but before its destructive step.
    # Expected: restore raises and the concurrent bytes remain at the target.

def test_restore_failure_rolls_back_completed_operations(self) -> None:
    # Fail the second restore write after the first completed.
    # Expected: both targets return to their applied bytes and manifest remains retryable.

def test_restore_can_resume_owned_interrupted_progress(self) -> None:
    # Seed a valid progress journal with one quarantined operation.
    # Expected: restore completes, marks the manifest restored, and removes progress files.
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -B -m unittest tests.safe_project_mutation.test_safe_mutation -v`

Expected: the new race test shows concurrent data deletion and the failure test shows a mixed state with an unretryable `applied` manifest.

- [ ] **Step 3: Implement owned restore progress and quarantine**

Add a strict progress payload:

```python
RESTORE_PROGRESS_FIELDS = {
    "schema_version", "operation_id", "manifest_digest", "mode", "completed"
}

def _restore_progress_path(backup_root: Path) -> Path:
    return backup_root / "restore-progress.json"

def _restore_quarantine_path(backup_root: Path, index: int) -> Path:
    return backup_root / "restore-quarantine" / f"{index:04d}.applied"
```

For each reversed operation, atomically move the target to its owned quarantine path, verify the moved hash equals `after_sha256`, then install the verified before-state or keep the target absent. Persist completion after each step. On error, roll completed steps back from quarantine; if rollback itself fails, write `restore-incomplete-manual-recovery` with exact paths and reasons. Allow a subsequent call to resume only when the progress digest matches the trusted manifest.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -B -m unittest tests.safe_project_mutation.test_safe_mutation -v`

Expected: all safe-mutation tests pass, including the new race, rollback, resume, and recovery cases.

- [ ] **Step 5: Synchronize canonical copies**

Run: `python -B scripts/sync_skill_resources.py .`

Run: `python -B scripts/sync_skill_resources.py . --check`

Expected: generated safe-mutation helpers match the root script and the check exits zero.

### Task 2: Make Adapter And Pack Generation Contained And Transactional

**Files:**
- Modify: `tests/packaging/test_packs_adapters.py`
- Modify: `scripts/generate_adapters.py`
- Modify: `scripts/build_packs.py`

- [ ] **Step 1: Add failing path and preservation tests**

Add tests for unsafe `pack["id"]`, unsafe `pack["skills"]`, unsafe capability `id`, capability path outside `skills/`, unsupported resources after a valid old output, injected swap failure, and unmanaged empty directories. Representative assertions:

```python
with self.assertRaisesRegex(ValueError, "safe path component"):
    build_pack(root, {**pack, "id": "../../escaped"}, output_root)
self.assertEqual(old_digest, tree_digest(old_output))
self.assertFalse((output_root.parent / "escaped").exists())
```

- [ ] **Step 2: Run packaging tests and verify RED**

Run: `python -B -m unittest tests.packaging.test_packs_adapters -v`

Expected: traversal escapes the intended output and failed rendering removes or partially replaces the previous output.

- [ ] **Step 3: Implement safe components, containment, staging, and swap rollback**

Use one safe-component contract in each script:

```python
SAFE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")

def _safe_component(value: object, label: str) -> str:
    if not isinstance(value, str) or SAFE_COMPONENT.fullmatch(value) is None:
        raise ValueError(f"{label} must be a safe path component")
    return value
```

Resolve every source under `root/skills`, every destination under the staging output, and reject containment failures before any write. Render to a sibling `.<name>.<uuid>.stage`, validate the complete generated tree, rename the old managed output to an owned rollback path, rename the stage into place, then remove the rollback path. Restore the old output if either rename fails.

- [ ] **Step 4: Run packaging tests and verify GREEN**

Run: `python -B -m unittest tests.packaging.test_packs_adapters -v`

Expected: all packaging tests pass and every failure preserves the previous output and surrounding filesystem.

### Task 3: Bind Release And Promotion PASS To Real Evidence

**Files:**
- Create: `evals/schema/release-preflight.schema.json`
- Modify: `tests/p2/test_production_tools.py`
- Modify: `tests/governance/test_promotion_evidence.py`
- Modify: `scripts/release_preflight.py`
- Modify: `scripts/promotion_evidence.py`
- Modify: `scripts/validate.py`
- Modify: `scripts/catalog_audit.py`
- Modify: `registry/promotion-evidence.yaml`
- Replace: `registry/promotion-artifacts/localization-authority-audit-fpc-results.json`
- Create: `registry/promotion-artifacts/localization-authority-audit-fpc/**`
- Generate: `skills/release-candidate-preflight/scripts/release_preflight.py`

- [ ] **Step 1: Add failing semantic release tests**

Define a strict payload with `candidate`, `checks`, `defects`, and `waivers`. Add tests proving the current placeholder fixture cannot PASS and that cross-candidate evidence, hash drift, stale timestamps, incomplete monitoring, incomplete rollback, ownerless approvals, and unexpired blocking defects fail.

```python
payload = {
    "candidate": {
        "id": "fpc-1.0.0+abc123",
        "version": "1.0.0",
        "source_snapshot": "abc123",
        "build_id": "windows-server-42",
        "primary_artifact": {"path": "build.zip", "sha256": digest},
    },
    "checks": checks,
    "defects": [],
    "waivers": [],
}
self.assertNotEqual("PASS", evaluate_release_preflight(payload, evidence_root=root)["verdict"])
```

- [ ] **Step 2: Add failing strict promotion tests**

Run the committed FPC promotion result through `evaluate_results(..., profile="fpc-global-localization-static")`. Assert all selected promotion cases must produce strict PASS and every artifact must exist below the promotion bundle root with matching SHA-256.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `python -B -m unittest tests.p2.test_production_tools tests.governance.test_promotion_evidence -v`

Expected: semantic placeholders and the current incomplete promotion bundle are rejected by the new tests.

- [ ] **Step 4: Implement the candidate-bound release schema and evaluator**

Make `evaluate_release_preflight(payload, *, evidence_root)` validate `evals/schema/release-preflight.schema.json`, resolve and hash every evidence entry, require all mandatory checks to reference `candidate.id`, require actionable monitoring and rollback records, and apply verdict precedence `FAIL`, then `BLOCKED`, then `PASS`.

- [ ] **Step 5: Reuse strict dogfood evaluation for promotion**

For each `dogfood-result` promotion artifact, resolve its bundle root, call the strict dogfood evaluator with the declared profile, and require the selected cases to be strict PASS. Package the FPC static evidence directory with sanitized machine paths and recomputed hashes, then update `registry/promotion-evidence.yaml` to the new result path and digest. If sanitization cannot preserve a self-contained valid bundle, revert `localization-authority-audit` to `experimental` instead of keeping unsupported beta.

- [ ] **Step 6: Run focused tests, sync resources, and verify GREEN**

Run: `python -B -m unittest tests.p2.test_production_tools tests.governance.test_promotion_evidence -v`

Run: `python -B scripts/sync_skill_resources.py .`

Expected: strict release and promotion suites pass and bundled release helper is synchronized.

### Task 4: Collect Real Unity MCP Runtime Evidence From FPC

**Files:**
- Modify: `scripts/fpc_localization_certify.py`
- Modify: `tests/evals/test_fpc_localization_certify.py`
- Modify: `evals/dogfood/profiles/fpc-global-localization-runtime.json`
- Modify: `<FPC_ROOT>/.agents/project-profile.yaml`
- Create under ignored evidence: `evidence/local/fpc-unity-runtime-20260817/**`

- [ ] **Step 1: Add failing runtime evidence validation tests**

Require the runtime case to supply hashed artifacts for MCP transcript, editor state, Unity test result, PlayMode result, console report, and runtime assertion. A boolean availability flag or a transcript without actual test/PlayMode calls remains BLOCKED.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -B -m unittest tests.evals.test_fpc_localization_certify -v`

Expected: the existing runtime implementation cannot produce PASS because it never consumes a real MCP evidence bundle.

- [ ] **Step 3: Connect through the pinned Unity relay**

Start the configured `relay_win.exe --mcp --project-path <FPC_ROOT>/client/LineRWebGL` as an MCP stdio session. Initialize it, list resources/tools, read the exact URIs for instances, editor state, project info, custom tools, and tests, and pin the `LineRWebGL` instance before any tool call.

- [ ] **Step 4: Run read-first Unity certification**

Require editor readiness, zero compilation errors, an EditMode localization test run, controlled PlayMode entry/exit on the existing startup scene, a runtime localization assertion covering `Assets/Game/RunTimeRes/preload/update.prefab`, console capture, and a screenshot when available. Do not edit scenes, prefabs, scripts, packages, or project settings during certification.

- [ ] **Step 5: Persist and validate the evidence bundle**

Write the raw MCP transcript and normalized artifacts under ignored `evidence/local/fpc-unity-runtime-20260817/`. Run the updated certification script and dogfood evaluator against the bundle.

Run: `python -B scripts/dogfood_eval.py . --results evidence/local/fpc-unity-runtime-20260817/results.json --artifact-root evidence/local/fpc-unity-runtime-20260817 --profile fpc-global-localization-runtime`

Expected: `PASS 3/3`; otherwise preserve the exact FAIL or BLOCKED reason.

- [ ] **Step 6: Add executable FPC validation matrix entries**

Populate the FPC project profile with existing safe read-only validation commands for Unity/localization, Lua contracts, C++ static/build checks when locally available, data/catalog validation, and QA. Commands unavailable in the current environment are explicitly marked with their evidence requirement rather than omitted.

### Task 5: Make Lifecycle Readiness A Release Signal And Re-score

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/nightly.yml`
- Modify: `tests/governance/test_ci_workflows.py`
- Modify: `.codex-plugin/plugin.json`
- Modify: `tests/packaging/test_codex_plugin.py`
- Create under ignored evidence: `evidence/local/release-90-audit/**`

- [ ] **Step 1: Add failing workflow contract tests**

Require nightly to run and upload `catalog_audit.py` and `check_originality.py` reports. Require an explicit release-readiness job or workflow-dispatch input that does not convert BLOCKED lifecycle status into PASS for a release decision.

- [ ] **Step 2: Run governance tests and verify RED**

Run: `python -B -m unittest tests.governance.test_ci_workflows -v`

Expected: current workflows lack the required lifecycle release verdict.

- [ ] **Step 3: Implement lifecycle artifact publication and release gating**

Keep ordinary deterministic CI green when optional upstream snapshots are absent, but add a separate release-readiness job that uploads originality, catalog, Tier-B, behavior, pressure, session-history, and dogfood reports and fails or remains BLOCKED for release when any required input is unavailable.

- [ ] **Step 4: Bump the distributed plugin minor version**

Change plugin version from `1.3.3` to `1.4.0` because release-preflight input semantics and runtime certification behavior change. Update the packaging assertion and run its focused test.

- [ ] **Step 5: Run all deterministic gates**

Run every command under `AGENTS.md` Local Gates, followed by `git diff --check` in KIT and the FPC localization suite.

Expected: deterministic gates exit zero; FPC tests pass with only documented skips.

- [ ] **Step 6: Run lifecycle audits and produce the final score**

Run originality, catalog, Tier-B, behavior, pressure, strict FPC dogfood, and release preflight. Save reports under `evidence/local/release-90-audit/`. Score capability completeness and production readiness separately. A remaining P1/P2 or required BLOCKED lifecycle gate prevents a 90+ release claim.

- [ ] **Step 7: Final review without commit or push**

Review the exact diff, verify generated resources are synchronized, confirm no unrelated work was reverted, and report files, commands, exit codes, evidence paths, restore information, residual blockers, and the achieved score. Do not commit or push.
