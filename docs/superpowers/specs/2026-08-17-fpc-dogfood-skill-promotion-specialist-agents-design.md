# FPC Dogfood, Skill Promotion, And Specialist Agents

## Context

The FPC sample project is separate from the unrelated comparison project. The current
dogfood fixture mixes scenarios for unrelated projects, including a comparison-project intake
case, crash-dump triage, database migration, live incident response, and multi-repository
routing. FPC therefore cannot honestly pass the universal twelve-case set.

The current FPC result file is a legacy array with twelve `BLOCKED` diagnostic records. It
does not contain the strict `results` wrapper, current project snapshot, reviewer, command
exit codes, restore information, or hashed artifacts required for promotion evidence. FPC
already has useful localization evidence, but the evidence predates the current dirty
snapshot and must not be relabeled as fresh `Verified` evidence without rerunning the static
audits.

FPC currently has project-local client, localization, residue, server, data, workbench, and
WebGL workflows. Its project profile nevertheless has `default_concurrency: 0` and an empty
`specialists` list. The KIT has 35 canonical skills and three generic agent roles, all skills
currently marked `experimental`.

## Goals

1. Add project/capability-specific dogfood profiles without weakening the strict result
   contract or deleting the universal diagnostic catalog.
2. Produce the first honest FPC dogfood result from fresh, read-only localization evidence.
3. Promote only skills whose maturity is supported by explicit, artifact-bound evidence.
4. Add a governed specialist-agent catalog that is materialized from canonical KIT templates
   and opt-in per project profile.
5. Keep source ownership, path locks, generated-output ownership, rollback, and evidence
   labels enforceable by scripts and tests rather than prompt text alone.

## Non-goals

- Do not translate or edit FPC in the certification-only pilot.
- Do not edit serialized prefab text as a substitute for an English source authority.
- Do not force every project to execute every universal dogfood scenario.
- Do not mark all 35 skills `release` after one project run.
- Do not activate every specialist in every project.
- Do not reclaim FPC locks, start/stop services, build Unity, import databases, publish, or
  commit without a later explicit task authorization.

## Workstream Decomposition

The program is intentionally split into three independently testable workstreams:

### A. Profile-aware dogfood

Keep the universal catalog for cross-project diagnostics, but add named profiles that select
only cases applicable to a project and its available runners. The first profile family is
`fpc-global-localization-static` plus a runtime extension named
`fpc-global-localization-runtime`.

### B. Evidence-based promotion

Add a promotion evidence contract and maturity ladder. A skill can advance only when the
required profile cases, artifact integrity, owner, review date, rollback information, and
runtime compatibility checks are present.

### C. Specialist-agent catalog

Extend the canonical agent-role registry and templates with discipline specialists. Project
profiles explicitly activate specialists; generated adapters materialize the same canonical
templates without creating a second skill tree.

## Dogfood Architecture

```text
FPC snapshot + dirty-state manifest
        |
        v
fpc-global-localization-static profile
        |
        +--> global residue inventory/report
        +--> strict localization doctor
        |
        v
artifact bundle (command log, snapshot, reports, verdict, SHA-256)
        |
        v
strict results wrapper -> PASS, FAIL, or BLOCKED
```

### Profile contract

Add a profile directory under `evals/dogfood/profiles/`. Each profile contains:

- `id` and human-readable description;
- project identity and allowed project-kind matchers;
- selected case IDs and expected workflow IDs;
- required runner capabilities (`file-audit`, `unity-mcp`, `play-mode`, or similar);
- approved artifact root policy;
- promotion scope, if the profile is allowed to support maturity changes.

The CLI gains `--profile`. Without it, the existing universal fixture remains the default
diagnostic behavior. With it, exact case coverage is calculated against the selected profile,
not against unrelated scenarios.

### FPC profile cases

The initial profile family contains:

1. `fpc-global-residue-authority`: inventory and trace prefab/component/binder/source
   authority using the FPC global-residue workflow.
2. `fpc-localization-doctor`: run the strict localization doctor and verify source, catalog,
   generated overlay, encoding, signature, and blocking-count invariants.
3. `fpc-unity-localization-runtime`: a runtime case requiring fresh Unity MCP/editor
   evidence, active text audit, console result, and target-resolution overflow evidence.

`fpc-global-localization-static` selects cases 1 and 2 and can produce an overall PASS from
fresh read-only evidence. `fpc-global-localization-runtime` selects cases 1, 2, and 3; it
remains BLOCKED until Unity MCP/editor evidence is available. The runtime profile must not
silently downgrade case 3 to optional.

### Snapshot and artifacts

The certification runner writes a new evidence directory outside source ownership, for
example `evidence/local/fpc-global-localization-static/<run-id>/`. It records:

- `command-log`: exact command, exit code, environment/runtime version, and timestamp;
- `project-snapshot`: repository path, branch, HEAD, dirty-state digest, and exact owned-scope
  file manifest; untracked/private values are represented by hashes where possible;
- `localization-report`: fresh inventory/report or doctor JSON;
- `verdict`: the case-specific interpretation and limitations;
- optional Unity artifacts: MCP state, edit-mode audit, play-mode audit, console output, and
  screenshot metadata.

Every result uses the strict object root `{ "results": [...] }`. Every artifact has `kind`, a
relative `path`, and a lowercase SHA-256 digest. Absolute paths, traversal, missing files,
hash drift, and stale snapshot bindings fail evaluation. Old `tmp/loc-demo` files remain
`Snapshot` evidence unless a fresh run proves they match the current scope.

### Runtime and mutation boundary

The certification-only pilot is read-only. It never edits a prefab, localization source,
generated overlay, Lua file, or Unity scene. A later translation/fix task must be a separate
work packet with exact source-owned paths, path locks, backup/manifest, reviewer, regeneration,
and Unity verification. If a finding is a dynamic source gap, the action is to add or repair
English source authority and regenerate; direct prefab replacement is forbidden.

## Promotion Architecture

Maturity becomes an evidence-backed state machine:

```text
experimental
  -> beta       deterministic gates + one real project profile PASS
  -> stable     repeated profiles + behavior/pressure/Tier-B + rollback proof
  -> release    compatibility matrix + versioned contract + owner + session KPI
```

The registry accepts `experimental`, `beta`, `stable`, and `release`. A promotion record
contains:

- skill ID and target maturity;
- profile and case IDs that produced the evidence;
- artifact manifest and verified hashes;
- owner, reviewer, review date, and supported runtime targets;
- rollback/restore procedure;
- known limitations and expiry/review policy.

`scripts/validate.py` rejects a non-experimental maturity with missing or invalid promotion
evidence. `scripts/catalog_audit.py` rechecks artifact existence and hashes before accepting
the promotion. Promotion is per skill, not an all-catalog flag.

### Initial promotion policy

The FPC localization profile can support beta evidence for project intake, routing,
orchestration, handoff, and localization-authority workflows when their exact cases pass. It
cannot promote safe mutation, build verification, release preflight, liveops, database, or
security workflows without their domain-specific evidence. The proposed twelve-skill cohort
is a target backlog, not an automatic status change.

## Specialist-Agent Architecture

The three existing generic roles remain the coordination foundation:

- `investigator`: read-only ownership and dependency discovery;
- `implementer`: bounded write work for one explicit scope;
- `verifier`: independent validation without source edits.

Add these opt-in discipline roles:

| Role ID | Primary ownership |
| --- | --- |
| `unity-csharp-client` | Unity C#, scenes, prefabs, client runtime, performance |
| `csharp-backend` | .NET services, APIs, jobs, and tooling |
| `cpp-game-server` | C++ server, protocol, memory, crash, and build paths |
| `golang-services` | Go services, gateways, concurrency, and observability |
| `lua-gameplay` | Lua gameplay, contracts, and generated-config consumers |
| `game-data-engineer` | MySQL, migrations, config pipeline, and telemetry data |
| `technical-artist` | Shaders, VFX, asset import, rendering, and content pipeline |
| `ui-localization-specialist` | UI prefabs, localization authority, fonts, overflow, accessibility |
| `systems-game-designer` | Economy, progression, balance, and content data |
| `qa-automation` | Unit, integration, Play Mode, browser, and regression evidence |
| `build-release-engineer` | Unity builds, CI, packaging, rollback, and release gates |
| `liveops-sre` | Runtime health, incidents, monitoring, and recovery |
| `game-security-engineer` | Network authority, exploit paths, secrets, and boundaries |

Each role entry in `registry/agent-roles.yaml` and its canonical `agents/*.toml` template
declares:

- `discipline`, `required_skills`, and `validation_commands`;
- exact `owned_scope_patterns` and `read_scope_patterns`;
- forbidden actions and generated-output boundaries;
- sandbox mode, reasoning effort, and concurrency group.

Project profiles opt in to specialists. FPC initially activates Unity/C#, Lua, C++ server,
data, technical-art, UI/localization, QA, and build/release roles. Go and C# backend roles are
distributed by KIT but remain inactive until a project profile declares those subsystems.
The validator rejects missing skills, duplicate IDs, invalid templates, and overlapping active
writer scopes.

## Failure Handling

- Missing Unity MCP or Play Mode evidence produces `BLOCKED` for runtime cases, never PASS.
- Artifact hash drift or a dirty-snapshot mismatch produces `FAIL`.
- Missing source authority or an untraceable prefab produces `BLOCKED`; it is not translated
  from serialized text.
- Path-lock or ownership conflict produces `BLOCKED`; stale-lock recovery remains governed by
  the FPC contract.
- Project capabilities not selected by a profile are out of scope, not failures.
- Promotion never occurs from legacy arrays, string-only artifact claims, or unrelated
  project fixtures.

## Verification Plan

### KIT

- profile schema and CLI tests;
- strict wrapper/profile coverage tests;
- artifact path/hash and dirty-snapshot tests;
- promotion evidence validation and catalog recheck tests;
- agent registry/template/materialization and scope-overlap tests;
- existing sync, unit, validation, routing, secret, policy, collision, and doctor gates.

### FPC certification

- fresh global residue inventory/report;
- strict localization doctor;
- source/catalog/generated consistency and signature checks;
- exact snapshot manifest and artifact hash verification;
- separate edit-mode and play-mode Unity evidence when MCP is available.

### Later mutation pilot

A separate plan may select one reviewed static or source-backed localization finding, reserve
exact locks, create a backup/manifest, change the owning English source, regenerate outputs,
run focused tests, and verify Unity UI at target resolutions. This is not part of the
certification-only design.

## Rollout

1. Implement and test profile-aware dogfood without changing the universal catalog semantics.
2. Run a fresh FPC certification-only localization profile and preserve honest per-case
   `PASS`/`BLOCKED` results.
3. Add promotion evidence schema and promote only the exact workflows supported by those
   artifacts to `beta`.
4. Add specialist templates, registry validation, project-profile activation, and overlay
   tests; activate only FPC-relevant roles.
5. Run repeated project profiles and domain evidence before `stable` or `release`.
6. Handle actual prefab/source translation as a separately approved mutation workstream.

## Decisions

- FPC and the comparison project use separate dogfood profiles.
- The universal 12-case catalog remains available for diagnostics but is not a universal
  project promotion gate.
- Certification-only comes before mutation.
- Evidence freshness and artifact integrity are mandatory.
- Maturity promotion is per skill and per evidence record.
- Specialist agents are opt-in discipline roles, not an automatically activated swarm.
