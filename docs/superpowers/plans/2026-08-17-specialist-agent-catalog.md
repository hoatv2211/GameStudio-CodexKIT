# Specialist Agent Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Add governed, opt-in studio specialist roles for Unity/C#, C++, Go, Lua, data, art, QA, release, liveops, and security while preserving the three generic coordination roles.

**Architecture:** Canonical role metadata lives in `registry/agent-roles.yaml`; canonical TOML templates live in `agents/`. The overlay generator reads active specialists from a project profile and materializes generated `.codex/agents` files. Required skills and scope patterns are validated before activation, and overlapping active writer scopes are rejected. Private FPC files are read-only during this rollout; activation is tested against a sanitized temporary profile fixture and only reported for FPC.

**Tech Stack:** YAML, TOML, Python `tomllib`, generated overlays, project-profile validation, `unittest`.

---

### Task 1: Extend canonical role schema and validation

**Files:**
- Modify: `registry/agent-roles.yaml`
- Modify: `scripts/validate.py`
- Test: `tests/_meta/test_validate.py`

- [ ] **Step 1: Write failing tests for specialist metadata, unknown required skills, invalid scope patterns, and duplicate concurrency groups.**

```python
def test_specialist_requires_discipline_and_scopes(self):
    registry = valid_registry_with_specialist()
    registry["agent_roles"][3].pop("owned_scope_patterns")
    self.assertIn("owned_scope_patterns", " ".join(issue.message for issue in validate_registry_fixture(registry)))
```

- [ ] **Step 2: Run focused validator tests and observe the current five-field schema reject/ignore the new metadata.**
- [ ] **Step 3: Define optional metadata for generic roles and required metadata for specialist roles: `kind`, `discipline`, `required_skills`, `owned_scope_patterns`, `read_scope_patterns`, `forbidden_actions`, `validation_commands`, `concurrency_group`. Validate IDs, paths, scopes, commands, skill references, and generic/specialist uniqueness.**
- [ ] **Step 4: Add all 13 approved specialist entries to the registry and keep investigator/implementer/verifier unchanged as generic coordination roles.**
- [ ] **Step 5: Run validator tests and the full registry validation command.**

### Task 2: Add canonical specialist templates

**Files:**
- Create: `agents/unity-csharp-client.toml`
- Create: `agents/csharp-backend.toml`
- Create: `agents/cpp-game-server.toml`
- Create: `agents/golang-services.toml`
- Create: `agents/lua-gameplay.toml`
- Create: `agents/game-data-engineer.toml`
- Create: `agents/technical-artist.toml`
- Create: `agents/ui-localization-specialist.toml`
- Create: `agents/systems-game-designer.toml`
- Create: `agents/qa-automation.toml`
- Create: `agents/build-release-engineer.toml`
- Create: `agents/liveops-sre.toml`
- Create: `agents/game-security-engineer.toml`
- Test: `tests/packaging/test_specialist_agents.py`

- [ ] **Step 1: Write a failing test that loads every registry template and checks declared discipline, exact role name, sandbox, reasoning effort, forbidden actions, and validation commands.**
- [ ] **Step 2: Run it and confirm templates are missing.**
- [ ] **Step 3: Add concise TOML templates. Each specialist must state that it is not alone in the workspace, owns only its profile repository/scope, never reverts concurrent edits, never delegates, and returns paths/commands/exit codes/artifacts/risk.**
- [ ] **Step 4: Add canonical template sources to `registry/skill-resources.yaml` only through root registry changes, then run `python -B scripts/sync_skill_resources.py .`.**
- [ ] **Step 5: Run packaging tests and inspect generated helper copies; do not edit `skills/*/scripts/` manually.**

### Task 3: Activate FPC specialists safely

**Files:**
- Create: `tests/fixtures/fpc-project-profile.yaml`
- Modify: `scripts/project_profile.py`
- Modify: `scripts/agent_overlay.py`
- Test: `tests/project_profile/test_project_profile.py`, `tests/packaging/test_packs_adapters.py`

- [ ] **Step 1: Add failing tests for active specialist known-skill validation and writer-scope overlap rejection.**
- [ ] **Step 2: Run focused tests and confirm current profile accepts an empty specialist list but has no overlap/skill enforcement.**
- [ ] **Step 3: Add `scope_patterns`/`write` metadata validation and deterministic overlap detection; allow FPC to activate Unity/C#, Lua, C++ server, data, technical-art, UI/localization, QA, and build/release only. Keep Go and C# backend distributed but inactive.**
- [ ] **Step 4: Add a sanitized fixture mirroring FPC subsystems with `default_concurrency: 1` and the eight approved active specialists; keep Go and C# backend roles inactive. Do not edit or materialize anything under `D:/path/to/fpc-project`.**
- [ ] **Step 5: Run `python -B scripts/project_profile.py tests/fixtures/fpc-project-profile.yaml` and the pure overlay planner against a temporary project; verify exactly the active roles are reported and unmanaged files are preserved.**

### Task 4: Verify packaging and generated adapters

**Files:**
- Modify: `docs/authoring/skills.md`
- Test: `tests/packaging/test_packs_adapters.py`, `tests/governance/test_governance.py`

- [ ] **Step 1: Run `python -B scripts/sync_skill_resources.py . --check`.**
- [ ] **Step 2: Run packaging and project-profile tests, then `python -B scripts/validate.py .`.**
- [ ] **Step 3: Inspect the generated-role manifest and confirm unmanaged project-local files are preserved; do not claim an FPC overlay write occurred during certification.**
