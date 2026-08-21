# Unity/MMORPG Golden Paths and Role UX Design

## Status

Draft approved in conversation for specification. Pending maintainer review before implementation planning.

Repository snapshot refreshed before implementation: `dev@e5dcaa2`.

## Problem

GameStudio-CodexKIT has broad studio coverage, deterministic routing, and strong safety contracts, but its practical depth and operator experience are uneven. Unity/MMORPG workflows are the strongest part of the catalog, yet users still need to understand skill names, prerequisites, evidence expectations, and multi-argument approval flows. Several newer studio workflows are useful as governance checklists but do not yet have the runnable helpers, focused tests, and governed dogfood evidence expected from the kit's strongest workflows.

The design must improve both workflow depth and studio usability without weakening evidence, ownership, mutation, or approval gates.

## Goals

1. Establish eight Unity/MMORPG Golden Path families that are easy to invoke and have complete execution and evidence contracts.
2. Add role-aware UX for Developer, QA, Producer, and LiveOps users without creating a second workflow source of truth.
3. Let users ask for outcomes through five stable entry intents rather than memorizing skill names.
4. Reduce the number of questions needed to produce a useful read-only task packet while preserving explicit approval for mutation.
5. Make scoped packs dependency-closed so a routed Golden Path cannot reference a missing capability.
6. Produce measurable adoption and reliability evidence suitable for later maturity decisions.

## Non-goals

- Adding Unreal, console SDK, native mobile signing, DCC, or audio-middleware verticals in this initiative.
- Building a graphical dashboard or separate web application.
- Replacing canonical `skills/`, registries, or `.agents/project-profile.yaml` with another configuration system.
- Making all 47 skills executable in the first rollout.
- Relaxing reviewer, backup, digest, dry-run, service-control, database, credential, publish, or destructive-action gates.
- Changing Codex App/CLI and Hermes Agent as the primary distributions.

## Selected Approach

Use a balanced Golden Paths plus Role UX approach.

The Golden Paths deepen existing workflows with helpers, schemas, tests, and dogfood evidence. The Role UX remains a thin routing and presentation layer over the canonical catalog. UX work ships alongside each Golden Path instead of preceding the underlying capability.

This approach is preferred over UX-first work, which would improve presentation without increasing operational confidence, and certification-first work, which would improve evidence while leaving adoption friction largely unchanged.

## Design Principles

- Keep `AGENTS.md`, registries, and canonical skills as the active authority chain.
- Reuse existing skills before proposing a new skill.
- Keep role presets advisory; risk and repository evidence override a preset.
- Default to report-only and progressive disclosure.
- Collect medium-risk approval inputs in one interaction while preserving every required field.
- Return `BLOCKED` with a concrete recovery action when prerequisites are unavailable.
- Never silently fall back from a specialist workflow to a generic workflow.
- Treat UX success as measurable task completion, not shorter output alone.

## Golden Path Families

Each family routes to existing canonical skills and may use supporting skills when evidence requires them.

| Golden Path | Primary workflows | Required depth outcome |
|---|---|---|
| Project adoption and routing | `studio-project-intake`, `studio-workspace-routing`, `studio-project-scaffold` | Report-only adoption packet, detected repositories, safe apply plan, status, and recovery |
| Local environment recovery | `multi-service-local-environment-doctor` | Process, port, dependency, configuration, and safe next-action evidence |
| Unity client entry recovery | `unity-client-offline-debugging` | Bootstrap/login/offline state trace with a reproducible verdict |
| Unity UI and localization | `unity-ui-rendering-debugging`, `localization-authority-audit` | Render-chain and content-authority evidence, including runtime limitations |
| Unity build and asset integrity | `unity-batchmode-build-verification`, `unity-asset-guid-meta-audit` | Batch log, artifact identity, GUID/meta findings, and build-bound verdict |
| C++ server failure recovery | `cpp-server-crash-triage`, `mmorpg-packet-protocol-review` | Crash signature, likely fault boundary, protocol compatibility, and next diagnostic |
| Lua contract and server authority | `lua-client-server-contract-audit`, `network-authority-and-exploit-review` | Client/server field mapping and authority findings tied to exact handlers |
| Data and live release safety | `game-database-migration-safety`, `save-data-schema-migration`, `release-candidate-preflight`, `liveops-incident-response` | Dry-run, restore, candidate identity, incident control, and no-go criteria |

### Golden Path Completion Contract

A family is complete only when it has:

1. A stable natural-language route and negative routing cases.
2. A runnable helper or an explicit repository-only execution boundary.
3. A strict task-packet and verdict artifact contract.
4. Focused unit or contract tests for success, failure, and `BLOCKED` behavior.
5. Recovery guidance for missing tools, stale evidence, partial results, and unsafe mutation.
6. At least one governed dogfood case; runtime-dependent families must also state which runtime evidence remains `BLOCKED`.
7. A documented owner and reviewer expectation.

## Role UX

### Role Presets

Role presets influence prompt wording, default intent ordering, and result presentation. They do not grant authority or bypass project evidence.

| Role | Default emphasis | Primary outputs |
|---|---|---|
| Developer | Diagnose, reproduce, implement safely, verify | Root-cause packet, affected paths, focused verification |
| QA | Verify, reproduce, cover risks, collect artifacts | Test matrix, evidence gaps, regression verdict |
| Producer | Plan change, expose dependencies, prepare release decision | Work packets, risk register, readiness summary |
| LiveOps | Stabilize service, control incident, verify recovery | Incident state, mitigation boundary, rollback and monitoring |

### Stable Entry Intents

Users may ask naturally, while adapters and documentation consistently present five entry intents:

- `Diagnose`
- `Verify`
- `Plan Change`
- `Ship`
- `Handle Incident`

The root router combines intent, role, project profile, repository evidence, and risk level to select the narrowest workflow. Skill names remain available for expert use but are not required.

### Basic and Advanced Modes

Basic mode:

- Asks no more than three required questions before producing a read-only task packet.
- Uses safe defaults derived from `.agents/project-profile.yaml` and repository inspection.
- Shows the selected workflow, why it was selected, prerequisites, risk, and next action.
- Does not expose registry or adapter internals unless they block progress.

Advanced mode:

- Exposes workflow override, repository route, evidence freshness, owner boundaries, reviewer, backup, plan digest, and runtime options.
- Remains subject to the same validators and safety contracts as Basic mode.

### Project Profile Extension

Extend `.agents/project-profile.yaml` with an optional backward-compatible `studio_experience` section:

```yaml
studio_experience:
  default_role: developer
  preferred_mode: basic
  enabled_intents:
    - diagnose
    - verify
    - plan-change
    - ship
    - handle-incident
```

Unknown or absent values retain current behavior. The section affects UX defaults only and never changes mutation authority.

## Task Packet and Evidence Card

The UX layer renders existing workflow evidence into two normalized views.

### Task Packet

Produced before execution:

- Repository and project snapshot.
- Detected role and requested intent.
- Selected Golden Path and canonical workflow.
- Selection reason and rejected neighboring routes.
- Risk level and exact write ownership.
- Required tools, artifacts, and unavailable prerequisites.
- Report-only next action or approval requirements.

### Evidence Card

Produced after execution or when blocked:

- Verdict: `PASS`, `FAIL`, or `BLOCKED` where the selected workflow permits it.
- Evidence labels: `Verified`, `Snapshot`, `Unverified`, and `BLOCKED`.
- Commands, exit codes, artifact paths, and freshness.
- First actionable failure or blocker.
- Restore or rollback information.
- One recommended next action and optional advanced details.

The normalized views do not replace workflow-specific artifacts. They reference them.

## Approval Bundle UX

Medium-risk actions continue to require exact scope, reviewer, disjoint backup root, approved plan digest, and restore information. The UX collects these inputs in one explicit approval interaction:

1. Generate and display the report-only plan.
2. Offer a repository-safe default backup location outside owned output paths.
3. Require the human reviewer name.
4. Display the plan digest and restore procedure.
5. Require explicit confirmation before passing the same fields to the canonical mutation API.

The standalone APIs and CLI entry points must enforce identical requirements. No direct apply path may accept a missing digest or weaker backup validation.

## Routing and Dependency Closure

Before Role UX can claim a Golden Path is available, every scoped installation must contain the complete capability dependency closure.

The pack validator and pack builder must:

- Resolve transitive skill dependencies within declared pack dependencies.
- Fail generation when a skill references a capability unavailable in the resulting pack.
- Report the missing capability, owning skill, and required pack.
- Preserve full-plugin behavior where all canonical skills are present.

The Role UX must return `BLOCKED` with an installation recommendation if an external or manually assembled catalog is incomplete.

## Error Handling

| Condition | Required behavior |
|---|---|
| Ambiguous intent | Present the two highest-ranked routes and ask one clarifying question |
| Missing local tool or runtime | Return `BLOCKED` with the exact prerequisite and a non-mutating fallback if available |
| Missing pack dependency | Return `BLOCKED`; name the missing capability and owning pack |
| Dirty or mismatched repository | Preserve unrelated work and narrow ownership; block unsafe replacement |
| Stale plan or digest mismatch | Reject apply and regenerate a report-only plan |
| Medium/high-risk action | Require the canonical approval or human-approval contract |
| Partial runtime evidence | Separate static `Verified` evidence from runtime `BLOCKED` evidence |
| Workflow failure | Preserve raw command output and identify the first actionable error |

## Testing Strategy

### Deterministic Tests

- Add role-and-intent routing cases for every Golden Path, including Vietnamese and English prompts.
- Add negative cases proving role presets do not override repository or risk evidence.
- Add pack dependency-closure tests and failure fixtures.
- Add project-profile schema and backward-compatibility tests.
- Add Basic and Advanced task-packet snapshot tests.
- Add parity tests proving CLI, API, and bundled skill mutation entry points enforce the same approval inputs.

### Golden Path Verification

- Add focused helper tests for each family.
- Test `PASS`, `FAIL`, and `BLOCKED` artifact completeness.
- Test stale evidence, missing tools, unsafe paths, and restore information.
- Preserve the full local gate suite from `AGENTS.md`.

### Governed Dogfood

- Use authorized, named game-project snapshots.
- Cover all eight families with at least one governed case over the rollout.
- Require runtime evidence for Unity build/play-mode claims and service evidence for live operations claims.
- Keep missing runners, credentials, projects, or permissions as `BLOCKED`.

## Rollout

### Phase 0: Contract Repair

- Make packs dependency-closed.
- Enforce approval parity across every scaffold entry point.
- Normalize task-packet and evidence-card schemas.
- Add the optional project-profile UX section.

### Phase 1: UX MVP and Four Golden Paths

- Project adoption and routing.
- Local environment recovery.
- Unity client entry recovery.
- C++ server failure recovery.
- Ship Developer and QA presets with Basic and Advanced modes.

### Phase 2: Remaining Golden Paths

- Unity UI/localization.
- Unity build/asset integrity.
- Lua contract/server authority.
- Data/live release safety.
- Ship Producer and LiveOps presets.

### Phase 3: Adoption Evidence

- Run governed dogfood across the eight families.
- Measure task completion, question count, routing failures, missing dependencies, and unauthorized writes.
- Update maturity only when the required promotion evidence exists.

## Success Criteria

- At least 80% of the maintained benchmark prompts reach the intended Golden Path without naming a skill.
- Basic mode needs no more than three required questions before producing a read-only task packet.
- Every generated pack passes dependency-closure validation.
- Every Golden Path has focused tests, a strict artifact contract, and governed dogfood coverage or an explicit runtime `BLOCKED` record.
- CLI, API, and bundled skill entry points enforce identical mutation approvals.
- No governed run records an unauthorized write.
- Missing-dependency routing failures are zero in maintained fixtures.
- Install-to-first-use evaluation records a useful verdict within five minutes in the governed onboarding scenario.

## Risks and Mitigations

- **Golden Paths become another source of truth.** Keep them as registry-backed groupings that route to canonical skills.
- **Role presets hide important details.** Preserve Advanced mode and always expose risk, ownership, and evidence labels.
- **Basic mode weakens safety.** Basic mode reduces presentation complexity only; canonical mutation APIs remain unchanged or become stricter.
- **Catalog growth resumes.** Add a new skill only when an existing skill cannot own the workflow without losing a distinct validation contract.
- **Dogfood evidence remains concentrated in one project.** Require coverage reporting by Golden Path and clearly label project-specific snapshots.
- **UX becomes runtime-specific.** Keep task-packet and evidence-card schemas engine-agnostic while Golden Path helpers remain domain-specific.

## Decision Summary

- Deepen Unity/MMORPG operations before expanding to another engine vertical.
- Deliver UX incrementally with the workflow depth it represents.
- Use roles and intents as routing hints, not new authority.
- Reuse `.agents/project-profile.yaml` for UX defaults.
- Treat pack closure and approval parity as prerequisites, not later polish.
- Measure adoption with governed scenarios and retain honest `BLOCKED` outcomes.
