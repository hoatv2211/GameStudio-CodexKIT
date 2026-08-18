# Profile-Aware Dogfood And FPC Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Add named dogfood profiles and produce a fresh, read-only FPC localization certification without weakening the universal fixture.

**Architecture:** Keep `evals/dogfood/game-studio-scenarios.json` as the default catalog. Add profile manifests that select exact case records, make the evaluator resolve a selected case pack, and add a KIT-side certification runner that invokes FPC audit commands without writing to FPC. Strict results remain `{\"results\": [...]}` with artifact hashes and current snapshot binding.

**Tech Stack:** Python 3.11+, JSON/YAML, `jsonschema`, `unittest`, PowerShell subprocesses, SHA-256 manifests.

---

### Task 1: Define profile manifests and schema

**Files:**
- Create: `evals/dogfood/profiles/fpc-global-localization-static.json`
- Create: `evals/dogfood/profiles/fpc-global-localization-runtime.json`
- Create: `evals/schema/dogfood-profile.schema.json`
- Test: `tests/evals/test_dogfood_profiles.py`

- [ ] **Step 1: Write the failing schema/profile tests**

```python
def test_fpc_static_selects_only_two_cases(self):
    profile = load_profile(root, "fpc-global-localization-static")
    self.assertEqual(
        ["fpc-global-residue-authority", "fpc-localization-doctor"],
        profile["case_ids"],
    )
    self.assertEqual(["file-audit"], profile["runner_capabilities"])

def test_runtime_profile_requires_unity_mcp(self):
    profile = load_profile(root, "fpc-global-localization-runtime")
    self.assertEqual(3, len(profile["case_ids"]))
    self.assertIn("unity-mcp", profile["runner_capabilities"])
```

- [ ] **Step 2: Run `python -B -m unittest tests.evals.test_dogfood_profiles -v` and observe import/fixture failure.**

- [ ] **Step 3: Add manifests with exact cases, project matcher, artifact policy, and promotion scope.** The static profile contains cases 1 and 2, `allow_mutation: false`, and `promotion_scope: [localization-authority-audit, studio-project-intake, studio-workspace-routing, studio-agent-orchestration]`; runtime adds case 3 and `unity-mcp`, `play-mode`.

- [ ] **Step 4: Implement `load_profile` and JSON-schema validation in `scripts/dogfood_eval.py`; reject unknown profile IDs, duplicate case IDs, case IDs outside the universal catalog, and capability/profile mismatches.**

- [ ] **Step 5: Run the focused tests and `python -B scripts/dogfood_eval.py . --profile fpc-global-localization-static --export evidence/local/fpc-profile-cases.jsonl`; expect two exported rows.**

### Task 2: Make evaluation profile-aware without changing default behavior

**Files:**
- Modify: `scripts/dogfood_eval.py`
- Modify: `evals/schema/dogfood-result.schema.json`
- Test: `tests/evals/test_dogfood_eval.py`

- [ ] **Step 1: Add failing tests for profile-scoped exact coverage and runtime BLOCKED semantics.**

```python
def test_profile_results_ignore_unrelated_universal_cases(self):
    payload = strict_results_for_profile(root, "fpc-global-localization-static")
    report = evaluate_results(root, result_path, profile="fpc-global-localization-static", artifact_root=evidence)
    self.assertEqual("PASS", report["verdict"])
    self.assertEqual(2, report["total_cases"])

def test_runtime_profile_does_not_downgrade_missing_mcp(self):
    report = evaluate_results(root, result_path, profile="fpc-global-localization-runtime")
    self.assertEqual("BLOCKED", report["verdict"])
    self.assertIn("fpc-unity-localization-runtime", report["blocked"])
```

- [ ] **Step 2: Run the focused tests and confirm they fail because evaluator always loads the twelve-case catalog.**

- [ ] **Step 3: Thread an optional `profile` through `load_cases`, `_load_results`, `evaluate_results`, `write_summaries`, and CLI `--profile`; preserve twelve-case behavior when omitted.**

- [ ] **Step 4: Add profile metadata to the report (`profile`, `project_matcher`, `runner_capabilities`) while keeping the strict result object unchanged and rejecting extra result properties.**

- [ ] **Step 5: Run all dogfood tests; expected existing twelve-case tests remain green and new profile tests pass.**

### Task 3: Add read-only FPC certification runner

**Files:**
- Create: `scripts/fpc_localization_certify.py`
- Test: `tests/evals/test_fpc_localization_certify.py`
- Modify: `docs/authoring/dogfood.md`

- [ ] **Step 1: Write tests for snapshot digest, command capture, artifact hash generation, no-write enforcement, and unavailable runtime dependency.**

```python
def test_snapshot_digest_changes_when_fpc_dirty_scope_changes(self):
    first = snapshot_project(fpc_root, owned_scope=["client/LineRWebGL/Assets/Game/RunTimeRes"])
    second = snapshot_project(fpc_root, owned_scope=["client/LineRWebGL/Assets/Game/RunTimeRes"])
    self.assertEqual(first["dirty_digest"], second["dirty_digest"])

def test_runtime_case_is_blocked_when_unity_mcp_is_unavailable(self):
    result = run_certification(..., profile="fpc-global-localization-runtime", mcp_available=False)
    self.assertEqual("BLOCKED", result["results"][-1]["verdict"])
```

- [ ] **Step 2: Run the focused tests and confirm they fail because the runner module does not exist.**

- [ ] **Step 3: Implement read-only snapshot collection using `git -C <fpc> rev-parse --abbrev-ref HEAD`, `git rev-parse HEAD`, `git status --porcelain=v1`, and SHA-256 of the selected scope manifest.** Never write under FPC; evidence goes below KIT `evidence/local/fpc-global-localization/<run-id>/`.

- [ ] **Step 4: Execute `audit_global_prefab_text.py --profile global-webgl-beta --strict` and `global_residue_factory.py` only when the command is provably read-only; capture stdout/stderr/exit code as artifacts. If the documented localization doctor is absent, emit a `BLOCKED` case with the exact missing command rather than relabeling stale `tmp/loc-demo` files.**

- [ ] **Step 5: Emit strict wrapper results with `project_snapshot`, `reviewer`, `restore: Certification-only; no FPC mutation`, and lowercase artifact hashes.** Runtime case is BLOCKED when MCP/editor evidence is unavailable.

- [ ] **Step 6: Run `python -B scripts/fpc_localization_certify.py --project D:/path/to/fpc-project --profile fpc-global-localization-static --output evidence/local/fpc-global-localization`, read the emitted `results.json` and `artifact-root.txt`, then run `python -B scripts/dogfood_eval.py . --profile fpc-global-localization-static --results evidence/local/fpc-global-localization/results.json --artifact-root evidence/local/fpc-global-localization`. Record the actual PASS/BLOCKED result and leave FPC untouched.**

### Task 4: Verify the workstream

**Files:**
- Modify: `docs/authoring/dogfood.md`
- Test: `tests/evals/test_dogfood_eval.py`, `tests/evals/test_dogfood_profiles.py`, `tests/evals/test_fpc_localization_certify.py`

- [ ] **Step 1: Run `python -B -m unittest discover -s tests/evals -p "test_*.py"` and inspect all failures.**
- [ ] **Step 2: Run `python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl` and verify the default export still contains twelve rows.**
- [ ] **Step 3: Run the FPC static and runtime certification commands; preserve any honest `BLOCKED` status and never claim runtime PASS without MCP evidence.**
