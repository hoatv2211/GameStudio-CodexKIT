# Agent Overlay Packaging Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project-profile routing and agent overlays safe, self-contained in packaged skills, deterministic across regenerate/uninstall cycles, and ready for a `1.3.1` patch release.

**Architecture:** Keep `skills/` as the canonical workflow catalog, `agents/*.toml` as canonical generic templates, and root `scripts/` as canonical helpers. Add a pure `agent_overlay.py` planner, bundle it and the canonical templates into `studio-project-scaffold`, and route every per-project write through `safe_mutation.py` with report-only as the default. Preserve ownership per file so local takeover never orphans sibling generated resources.

**Tech Stack:** Python 3.11+, `unittest`, PyYAML, `tomllib`, TOML, JSON ownership manifests, YAML registries.

**Commit Policy:** Do not commit unless the user explicitly approves a checkpoint.

---

---

## File Boundaries

- Modify `scripts/project_profile.py`: profile validation.
- Create `scripts/agent_overlay.py`: pure generic/specialist agent planning.
- Modify `scripts/generate_adapters.py`: report/apply, ownership, uninstall.
- Modify `scripts/sync_skill_resources.py`: arbitrary bundled resources.
- Modify `scripts/validate.py`: resource and packaged-agent validation.
- Modify `registry/skill-resources.yaml`: helper/template mappings.
- Modify tests under `tests/project_profile/`, `tests/packaging/`, and `tests/_meta/`.
- Regenerate skill resources only through `scripts/sync_skill_resources.py`.
- Update plugin metadata and docs for `1.3.1` after behavior is green.

---

---

### Task 1: Harden Project Profile Validation

**Files:**
- Modify: `scripts/project_profile.py:9-216`
- Test: `tests/project_profile/test_project_profile.py`
- Generated: `skills/studio-project-scaffold/scripts/project_profile.py`
- Generated: `skills/studio-workspace-routing/scripts/project_profile.py`

- [ ] **Step 1: Add failing path tests**

Add a table-driven test rejecting `C:/outside`, `C:\outside`, `\\server\share`, `\\?\C:\outside`, and `../client`. Each case must produce `unsafe repository path: <value>`.

- [ ] **Step 2: Verify the path test fails**

Run: `python -B -m unittest tests.project_profile.test_project_profile.ProjectProfileTests.test_rejects_windows_absolute_and_traversal_repository_paths`

Expected: FAIL because drive-based Windows paths currently pass.

- [ ] **Step 3: Add failing identifier tests**

Reject repository ID `client/core` and specialist IDs `bad/role`, `bad role`, `Explorer`, `explorer`, and `implementer`. Use `^[a-z0-9]+(?:-[a-z0-9]+)*$` and reserve `default`, `worker`, `explorer`, `investigator`, `implementer`, and `verifier`.

- [ ] **Step 4: Add failing ownership tests**

Add assertions for duplicate repository path, duplicate validation name, duplicate contract participant, and authority outside the contract.

- [ ] **Step 5: Verify the profile suite fails only on new cases**

Run: `python -B -m unittest tests.project_profile.test_project_profile`

- [ ] **Step 6: Implement safe helpers**

`_safe_relative_path` must use both `PurePosixPath` and `PureWindowsPath`; add a lowercase kebab-case ID regex and the reserved agent set. Track normalized repository paths, per-repository validation names, distinct contract participants, and authority membership.

- [ ] **Step 7: Run tests and regenerate canonical resources**

Run `python -B -m unittest tests.project_profile.test_project_profile`, `python -B scripts/sync_skill_resources.py .`, then `python -B scripts/sync_skill_resources.py . --check`. Expected: exit `0` for all.

- [ ] **Step 8: Optional commit checkpoint**

After explicit approval only: `git commit -m "fix: harden project profile validation"`.

---

---

### Task 2: Generalize Skill Resource Packaging

**Files:**
- Modify: `scripts/sync_skill_resources.py`
- Modify: `registry/skill-resources.yaml`
- Modify: `scripts/validate.py`
- Test: `tests/_meta/test_validate.py`
- Test: `tests/packaging/test_packs_adapters.py`

- [ ] **Step 1: Add failing explicit resource tests**

Use a schema-version-2 fixture containing the existing `project_scaffold.py` shorthand plus:

`source: agents/investigator.toml` → `destination: templates/agents/investigator.toml`.

Assert sync creates both files, `--check` detects stale template content, and unmanaged undeclared files remain untouched.

- [ ] **Step 2: Verify the resource tests fail**

Run: `python -B -m unittest tests._meta.test_validate tests.packaging.test_packs_adapters`.

Expected: FAIL because the current registry accepts Python filenames only.

- [ ] **Step 3: Normalize resource entries**

Add:

`@dataclass(frozen=True) class SkillResource: skill_id: str; source: Path; destination: Path`.

Keep string entries as shorthand for `scripts/<name>`. Mapping entries use repository-relative `source` and skill-relative `destination`. Reject absolute paths, `..`, missing sources, duplicate destinations, reparse-point escapes, and destinations outside `skills/<skill-id>/`.

- [ ] **Step 4: Render format-appropriate markers**

Use `# Generated by scripts/sync_skill_resources.py. Do not edit manually.` for Python, TOML, YAML, PowerShell, and shell resources; use an HTML comment for Markdown/text. Preserve existing Python bytes where possible to avoid churn.

- [ ] **Step 5: Upgrade the registry**

Set `registry/skill-resources.yaml` to schema version 2 and map the three canonical root `agents/*.toml` files into `skills/studio-project-scaffold/templates/agents/`. Do not reference `agent_overlay.py` until Task 3 creates the canonical helper, and do not duplicate template contents in YAML or Python.

- [ ] **Step 6: Extend validation**

Reject missing sources, unsafe destinations, duplicate destinations, generated drift, invalid packaged TOML, and a template `name` that does not match its filename.

- [ ] **Step 7: Synchronize and verify**

Run:

`python -B scripts/sync_skill_resources.py .`

`python -B scripts/sync_skill_resources.py . --check`

`python -B -m unittest tests._meta.test_validate tests.packaging.test_packs_adapters`

`python -B scripts/validate.py .`

Expected: exit `0` for all.

- [ ] **Step 8: Optional commit checkpoint**

After explicit approval only: `git commit -m "feat: bundle agent overlay resources"`.

---

---

### Task 3: Extract a Self-Contained Agent Overlay Planner

**Files:**
- Create: `scripts/agent_overlay.py`
- Modify: `scripts/generate_adapters.py:96-145`
- Modify: `registry/skill-resources.yaml`
- Test: `tests/packaging/test_packs_adapters.py`
- Generated: `skills/studio-project-scaffold/scripts/agent_overlay.py`

- [ ] **Step 1: Add a failing pure-planner test**

Create a temporary project with a valid specialist profile. Call:

`plan_agent_overlay(project, template_root=source_root / "agents", profile_path=profile_path, known_skills={"studio-project-intake"})`.

Assert no file is written and operations contain the three generic TOMLs, one specialist TOML, and `.codex/agents.generated.toml`.

- [ ] **Step 2: Add a failing unmanaged-collision test**

Pre-create unmanaged `.codex/agents/server-specialist.toml`. Assert the planner preserves it, excludes it from operations, and excludes that role from activation.

- [ ] **Step 3: Verify planner tests fail**

Run the two new tests. Expected: FAIL because `scripts.agent_overlay` does not exist.

- [ ] **Step 4: Implement the planner interface**

`plan_agent_overlay(...)` returns `operations`, `preserved`, `collisions`, `owned_files`, and `activated_roles` without calling `mkdir`, `write_text`, or `unlink`.

Move specialist rendering, activation rendering, safe `.codex` path checks, template loading, and collision handling from `generate_adapters.py`. Use `json.dumps` for TOML strings and validate the profile before constructing filenames.

- [ ] **Step 5: Reuse the planner from the full-clone adapter**

Call the planner with `template_root=root / "agents"` and merge its operations and ownership records into the project-adapter plan.

- [ ] **Step 6: Verify packaged independence**

Generate a Hermes adapter, start a subprocess with `cwd` outside the repository and `PYTHONPATH` containing only the packaged scaffold `scripts/` directory, then import packaged `agent_overlay` and use sibling `templates/agents/`. Repository-root imports must be impossible.

- [ ] **Step 7: Register, synchronize, and test**

Add `agent_overlay.py` to the scaffold skill's bundled resources only after the canonical helper exists. Then run `python -B scripts/sync_skill_resources.py .`, `python -B -m unittest tests.packaging.test_packs_adapters`, and `python -B scripts/validate.py .`. Expected: all PASS.

- [ ] **Step 8: Optional commit checkpoint**

After explicit approval only: `git commit -m "refactor: extract agent overlay planner"`.

---

---

### Task 4: Make Per-Project Adapter Report-Only by Default

**Files:**
- Modify: `scripts/generate_adapters.py:179-365`
- Test: `tests/packaging/test_packs_adapters.py`
- Modify: `README.md:245-258`
- Modify: `workflows/project-bootstrap.md`

- [ ] **Step 1: Add a failing report-only test**

Call `report_project_adapter(source_root, project)`. Assert status `REPORT_ONLY`, proposed paths include `.codex/agents/investigator.toml`, mutation mode is `report-only`, and neither `.agents` nor `.codex` is created.

- [ ] **Step 2: Add a failing safe-apply test**

Call `apply_project_adapter` with an empty reviewer and expect `ValueError`. Then call with reviewer `QA Lead` and a backup root; assert status `PASS`, reviewer, manifest path, and a restore argv beginning with `sys.executable`.

- [ ] **Step 3: Verify both tests fail**

Run: `python -B -m unittest tests.packaging.test_packs_adapters`.

Expected: FAIL because report/apply APIs do not exist.

- [ ] **Step 4: Refactor writing into a pure plan**

Replace `_write_project_adapter` with `_project_adapter_plan(root, project)`. It may read current state but must not create directories, write files, remove files, or call `shutil.rmtree`. Return operations, created, updated, preserved, collisions, and owned files. Include `.agents/registry.json` as the final planned operation.

- [ ] **Step 5: Add report and apply APIs**

`report_project_adapter` wraps `report_mutation(project, operations)`.

`apply_project_adapter` requires a non-empty reviewer, calls `apply_mutation(project, operations, backup_root)`, and returns manifest plus the exact restore command using sibling `safe_mutation.py`.

- [ ] **Step 6: Change CLI semantics**

For `--target per-project`, default to report-only. Require `--apply`, `--reviewer`, and `--backup-root` to write. Make `--uninstall` mutually exclusive with `--apply`. Leave generator-owned Hermes/Codex output behavior unchanged.

- [ ] **Step 7: Update documentation**

Show report-only first, then the explicit apply command. State that `.codex/config.toml` is never written and `.codex/agents.generated.toml` remains inert until reviewed and merged.

- [ ] **Step 8: Run focused gates**

Run `python -B -m unittest tests.packaging.test_packs_adapters tests.governance.test_template_finalization`, `python -B scripts/secret_scan.py .`, and `python -B scripts/policy_check.py .`. Expected: all exit `0`.

- [ ] **Step 9: Optional commit checkpoint**

After explicit approval only: `git commit -m "fix: gate per-project adapter mutations"`.

---

---

### Task 5: Preserve Ownership Across Regenerate and Uninstall

**Files:**
- Modify: `scripts/generate_adapters.py:203-483`
- Test: `tests/packaging/test_packs_adapters.py`

- [ ] **Step 1: Add the reproduced orphan regression test**

Apply the adapter, replace the generated marker only in `studio-project-scaffold/SKILL.md`, apply again, and assert its generated `scripts/project_scaffold.py` remains in `kit_adapter.files`. After uninstall, the local `SKILL.md` must remain and the matching generated helper must be removed.

- [ ] **Step 2: Add stale-owned resource coverage**

Generate from a temporary source catalog, remove one resource from that source, regenerate, and verify the old matching file stays tracked until uninstall. Repeat with a drifted old file and verify uninstall preserves it and reports the drift.

- [ ] **Step 3: Verify ownership tests fail**

Run the packaging suite. Expected: FAIL because preserving `SKILL.md` currently drops sibling helper ownership.

- [ ] **Step 4: Remove directory-level takeover**

Delete the early capability-wide `continue`. Evaluate each destination independently: unmanaged files are preserved; marker-owned files are planned and tracked. This permits a local-owned `SKILL.md` alongside kit-owned helpers.

- [ ] **Step 5: Merge previous ownership records**

Load previous `kit_adapter.files` before planning. Key records by safe normalized path. Replace records for newly planned files, retain records for existing files not produced in the new run, and remove records only when the target no longer exists. Never claim an unmanaged path absent from the previous manifest.

- [ ] **Step 6: Return a structured uninstall report**

Return `status`, `removed`, `preserved_drift`, and `remaining_owned` instead of a bare list. Resolve every manifest path through `_safe_project_path` and preserve hash-mismatched files.

- [ ] **Step 7: Run regenerate/uninstall tests**

Run: `python -B -m unittest tests.packaging.test_packs_adapters`.

Expected: all PASS and no generated helper remains without a manifest record.

- [ ] **Step 8: Optional commit checkpoint**

After explicit approval only: `git commit -m "fix: preserve adapter ownership across updates"`.

---

---

### Task 6: Validate Generated TOML and Packaged Runtime

**Files:**
- Modify: `tests/packaging/test_packs_adapters.py`
- Modify: `tests/_meta/test_validate.py`
- Modify: `scripts/validate.py`

- [ ] **Step 1: Add generated TOML parse tests**

After applying an adapter with one specialist, parse every `.codex/agents/*.toml` with `tomllib`. Assert filename stem equals `name`, required strings are non-empty, and each activation `config_file` resolves to an existing file under `.codex`.

- [ ] **Step 2: Add unmanaged collision activation coverage**

Pre-create an unmanaged agent using the specialist filename. Assert it is unchanged, reported as preserved/collision, and omitted from `.codex/agents.generated.toml`.

- [ ] **Step 3: Add packaged execution coverage**

Build a Hermes adapter into a temporary directory. Start a subprocess outside the repository with `PYTHONPATH` limited to the packaged scaffold `scripts/` directory. Import packaged `agent_overlay`, read packaged templates, validate a profile, and emit an overlay plan. Repository-root imports must fail if attempted.

- [ ] **Step 4: Run packaging tests**

Run: `python -B -m unittest tests.packaging.test_packs_adapters tests._meta.test_validate`.

Expected: all TOML parses, all activation paths resolve, and the packaged helper runs independently.

- [ ] **Step 5: Verify determinism**

Generate Hermes, Codex, and per-project reports twice against unchanged inputs. Compare tree digests or normalized JSON and require identical output.

- [ ] **Step 6: Optional commit checkpoint**

After explicit approval only: `git commit -m "test: verify packaged agent runtime"`.

---

---

### Task 7: Release Metadata, Documentation, and Evals

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json` only if versioned
- Modify: `README.md`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/authoring/skills.md`
- Modify: `workflows/project-bootstrap.md`
- Modify: `evals/behavior/catalog-contracts.json`
- Modify: `evals/pressure/high-risk-gates.json`
- Test: `tests/packaging/test_codex_plugin.py`

- [ ] **Step 1: Add a failing version assertion**

Change the expected plugin version to `1.3.1` and run `python -B -m unittest tests.packaging.test_codex_plugin`. Expected: FAIL until metadata changes.

- [ ] **Step 2: Update distributed metadata**

Set the plugin version to `1.3.1`. Update marketplace metadata only if it already owns a version field; do not invent one.

- [ ] **Step 3: Update user-facing invariants**

Document report-only default, reviewer/backup requirements, packaged agent templates, untouched `.codex/config.toml`, inert activation, per-file ownership, and hash-safe uninstall.

- [ ] **Step 4: Add deterministic safety cases**

Cover report-before-apply, rejection of config overwrite, unsafe specialist IDs, unrelated contract authority, and unmanaged local-agent preservation. Update routing expectations only where wording changes.

- [ ] **Step 5: Run docs and eval tests**

Run `python -B -m unittest tests.packaging.test_codex_plugin tests.governance.test_template_finalization tests.evals.test_dogfood_eval`, `python -B scripts/route_eval.py .`, and `python -B scripts/policy_check.py .`. Expected: all PASS.

- [ ] **Step 6: Optional commit checkpoint**

After explicit approval only: `git commit -m "docs: release hardened agent overlay"`.

---

---

### Task 8: Full Verification and Governed Dogfood

**Files:**
- Write ignored evidence only under `evidence/local/`.
- Do not mutate external or private studio projects.

- [ ] **Step 1: Check generated resources**

Run: `python -B scripts/sync_skill_resources.py . --check`.

Expected: exit `0`, zero drift.

- [ ] **Step 2: Run the complete unit suite**

Run: `python -B -m unittest discover -s tests -p "test_*.py"`.

Expected: exit `0`, all tests PASS.

- [ ] **Step 3: Run mandatory local gates**

Run independently and record exit codes:

`python -B scripts/validate.py .`

`python -B scripts/route_eval.py .`

`python -B scripts/secret_scan.py .`

`python -B scripts/policy_check.py .`

`python -B scripts/external_collision_eval.py .`

`python -B scripts/doctor.py --check --root .`

Expected: exit `0` for every deterministic gate.

- [ ] **Step 4: Run lifecycle audits honestly**

Run `python -B scripts/check_originality.py .` and `python -B scripts/catalog_audit.py .`. Record exact `BLOCKED` reasons when upstream, session, or dogfood evidence is unavailable.

- [ ] **Step 5: Prepare governed dogfood artifacts**

Run:

`python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl`

`python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json`

Exercise sanitized cases for single-repository Unity, multi-repository routing, specialist generation, unmanaged collision, regenerate after local takeover, safe restore, and uninstall with drift.

- [ ] **Step 6: Verify diff boundaries**

Run `git diff --check HEAD` and `git status --short`. Expected: no whitespace errors and no unrelated files changed.

- [ ] **Step 7: Produce the evidence summary**

Report commands, exit codes, artifact paths, Verified results, Snapshot assumptions, Unverified hypotheses, BLOCKED evidence, restore commands, and remaining release risks. Do not claim production readiness without governed dogfood evidence.

- [ ] **Step 8: Optional final commit checkpoint**

After explicit approval and full diff review only: `git commit -m "fix: harden packaged project agents"`.

---

---

## Completion Criteria

- Profiles reject unsafe Windows paths, unsafe/reserved IDs, ambiguous ownership, duplicate contract participants, and unrelated authority.
- Packaged `studio-project-scaffold` contains a self-contained generated overlay helper and canonical generic templates.
- Per-project operations are report-only by default and require reviewer plus backup root to apply.
- `.codex/config.toml` is never written; activation remains inert.
- Every generated TOML parses and every activation path resolves.
- Regeneration preserves per-file ownership and uninstall leaves no generated orphan.
- Mandatory local gates pass with command and exit-code evidence.
- Lifecycle gaps remain `BLOCKED` until real evidence exists.
- Distributed plugin metadata is synchronized at `1.3.1`.
