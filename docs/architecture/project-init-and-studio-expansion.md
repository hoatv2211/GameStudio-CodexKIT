# Project Init and Full-Studio Expansion

## Status

Approved for implementation on 2026-08-18.

## Goal

Add a safe, reversible project-adoption interface for MOStudio Kit, optionally enhanced by CodeGraph, while expanding the canonical catalog with the highest-value production, content, QA, analytics, and live-operations capabilities missing from a full game studio.

## Decisions

- CodeGraph is optional and never blocks core project initialization.
- A CodeGraph recommendation may prepare an installation plan, but installation requires a second explicit apply action, reviewer, and plan digest.
- The canonical user interface is the bundled skill command. An optional terminal command named `gamestudio` uses the same implementation.
- Existing project governance, skills, agents, configuration, dirty worktrees, generated outputs, and private studio repositories are preserved.
- The live `_Sabo` workspace informed topology patterns only. No private source, path-specific rule, or project-specific text is copied into distributed content.

## Public Interface

`gamestudio init [root]` produces a report-only adoption plan by default. It detects repositories, subsystems, existing governance, project complexity, proposed skills and agents, collisions, ownership operations, backup requirements, and optional CodeGraph advice.

New profiles may include an optional `studio_experience` block with `default_role`, `preferred_mode`, and `enabled_intents` defaults. The block affects presentation and routing UX only; it never grants mutation authority or waives risk or approval gates.

`gamestudio guide [root] --intent <intent>` runs the role-first planner without executing a workflow or writing project state. The optional root defaults to the current directory; explicit planner controls include role, mode, and `--golden-path`. `--workflow` requires explicit Advanced mode and must name a reported candidate for the selected family.

`gamestudio status [root]` reports owned files, drift, project profile validity, generated adapter state, and CodeGraph availability without mutation.

`gamestudio uninit [root]` removes only files whose ownership hashes still match the registry and preserves drift as a partial uninstall.

`gamestudio codegraph plan-install [root]` creates a reviewed external-install plan. `gamestudio codegraph apply-plan [root]` executes only an approved, unexpired plan with explicit apply and reviewer inputs.

## Internal Modules

- `scripts/gamestudio_cli.py`: terminal and bundled-skill command adapter.
- `scripts/project_complexity.py`: bounded project metrics and recommendation logic.
- `scripts/codegraph_adapter.py`: command detection, status parsing, and install-plan generation.
- `scripts/project_skill_overlay.py`: pure project-router and domain-skill planner.
- `scripts/project_scaffold.py`: project adoption orchestrator and backward-compatible scaffold interface.
- `scripts/agent_overlay.py`: generic, canonical specialist, and project-specific agent planning.
- `scripts/safe_mutation.py`: report, apply, backup, ownership, and restore mechanics.

The public interface remains small. Complexity is hidden behind pure planners that return serializable reports and can be tested without touching private projects or installing external tools.

## Role UX Boundary

Role UX presents and selects canonical skills. The pure planner reads profile defaults and detected subsystems, then returns a report-only task packet with the planning status `READY`, `AMBIGUOUS`, or `BLOCKED`; these are never runtime PASS verdicts, and `READY` provides no execution or mutation authority. If the top two candidates remain ambiguous, it asks one focused question. Role defaults are advisory and provide no execution or mutation authority.

The task packet records planning state. Only the selected canonical workflow executes or reviews its own actions and owns its native artifact. A normalized evidence card then summarizes the observed runtime `PASS`, `BLOCKED`, or `FAIL` result or blocker; the router cannot fabricate the final runtime verdict. Basic mode reduces exposed controls and Advanced mode may select a reported workflow candidate explicitly, but neither mode waives evidence, mutation, or approval requirements. `guide` remains report-only; `init --apply` remains the separately approved adoption path described below.

The five public intents Diagnose, Verify, Plan Change, Ship, and Handle Incident route across eight implemented Unity/MMORPG Golden Path families: project adoption and routing, local environment recovery, Unity client entry recovery, C++ server failure recovery, Unity UI and localization, Unity build and asset integrity, Lua contract and server authority, and data and live release safety. Unsupported current combinations return a task-packet `BLOCKED` with no selected workflow, execution, or mutation.

Governed adoption commands:

```text
python -B scripts/studio_adoption_eval.py . --export evidence/local/studio-adoption-cases.jsonl
python -B scripts/studio_adoption_eval.py . --status evidence/local/studio-adoption-status.json
python -B scripts/studio_adoption_eval.py . --results evidence/local/studio-adoption-results.json
```

PASS requires at least 80% intended Golden Path routing, no run above three questions, install-to-first-use at or below five minutes, zero missing-dependency failures, zero unauthorized writes, PASS task verdicts, and repository-contained SHA-256-bound artifacts. Without governed results the evaluator returns `BLOCKED` and leaves unobserved metrics `null`.

## Complexity Advisor

Complexity scoring uses evidence available before CodeGraph exists:

- Two nested Git roots: +2; three or more: +3.
- More than 3,000 source files: +2; more than 10,000: +3.
- Four or more languages: +1; seven or more: +2.
- Four or more detected subsystems: +2.
- Cross-project DTO, protocol, schema, or API signals: +2.
- Two or more generated-output pipelines: +1.
- No root Git repository with nested repositories: +1.
- Multiple build systems or dense project-reference signals: +1.

Scores 0-3 are LOW, 4-6 are MEDIUM, and 7 or higher are HIGH. The report calls this a complexity likelihood and never claims a circular dependency without graph evidence.

When complexity is HIGH and CodeGraph is unavailable, an interactive run offers to prepare an install plan, skip once, or persist a never-suggest preference. Non-interactive runs return the same recommendation without prompting.

## CodeGraph Ownership

An existing `.codegraph/` directory is user-owned. A CodeGraph index created after an approved external plan remains CodeGraph-owned; MOStudio Kit records provenance but does not include the database in its owned-file deletion set. Core init succeeds when CodeGraph is missing, stale, broken, or disabled.

The adapter consumes structured `codegraph status --json` output. Tests use a fake runner and never download, install, initialize, or remove CodeGraph.

## Project-Local Outputs

Cross-runtime state lives under `.agents/`:

- `.agents/CONTRACT.md`
- `.agents/project-profile.yaml`
- `.agents/registry.json`
- `.agents/plans/`
- `.agents/skills/`

Codex adapters live under `.codex/`:

- `.codex/AGENTS.md`
- `.codex/agents/`
- `.codex/skills/`
- `.codex/agents.generated.toml`
- `.codex/validation.generated.json`

Project-local skills are planned once and rendered into cross-runtime and Codex surfaces from the same model. Existing unmanaged files are preserved. Active `.codex/config.toml` is never edited automatically.

## Generated Project Skills

Every adopted project can receive `project-workspace` and `project-customization`. Evidence-backed domains can additionally receive Unity client, .NET server, C++ server, Java services, Go services, Lua gameplay, data pipeline, and build-release skills.

Hotspot skills are suggestions, not automatic output. They require an independent scope, at least two recurring workflows, a distinct validation contract, and complexity that would otherwise leak into a broad router.

## Generated Project Agents

The generic investigator, implementer, and verifier remain the baseline. Canonical specialists activate only when project-profile evidence matches their scope. Project-specific specialists require independent write ownership, at least two related project-local skills, distinct validation, and a non-overlapping concurrency group.

## Canonical Catalog Expansion

New agents:

- `producer`
- `level-content-designer`
- `narrative-designer`
- `asset-pipeline-specialist`
- `audio-engineer`
- `product-analyst`

New skills:

- `studio-production-planning`
- `production-risk-and-dependency-review`
- `level-and-content-design-review`
- `narrative-quest-content-contract`
- `art-asset-pipeline-preflight`
- `animation-rigging-import-audit`
- `audio-content-pipeline-review`
- `qa-test-strategy-and-coverage`
- `platform-device-compatibility-matrix`
- `load-soak-capacity-verification`
- `product-analytics-experiment-review`
- `liveops-content-rollout-and-rollback`

New packs:

- `production-management`
- `content-production`
- `product-analytics`

Existing packs remain compatible.

## Optional Terminal CLI

The repository gains an optional Python console entry point named `gamestudio`. Plugin and Hermes workflows do not depend on installation of this entry point. The console adapter imports the same implementation used by the bundled skill and does not introduce a second maintained skill tree.

## Safety and Recovery

Report-only is the default. The operator selects one scaffold apply entry point and supplies that entry point with a named reviewer, the approved digest from its reviewed report, and a project-local backup root disjoint from every proposed scaffold output. The direct API, standalone `project_scaffold.py` script, and primary `gamestudio init --apply` command independently enforce the equivalent canonical approval gates; the standalone and CLI adapters forward the selected values to the API. Parity tests cover all three without requiring an operator to execute all three. Reparse points, outside-workspace paths, protected active configuration, drifted owned files, stale plans, unmanaged collisions, and dirty replacement targets block mutation. Uninstall is hash-safe and may return PARTIAL when drift is preserved.

## Validation

Implementation must prove:

- Report-only creates no files.
- Apply gates are mandatory.
- Repeated init is idempotent.
- Nested dirty repositories are preserved.
- Existing CodeGraph indexes remain user-owned.
- CodeGraph absence is non-blocking.
- Never-suggest preference persists.
- Skill and terminal interfaces produce equivalent reports.
- Synthetic multi-repository fixtures route Unity, .NET/Lua, and Java domains without private content.
- Canonical registries contain 50 skills, 24 agents, and 7 packs.
- Generated resources remain synchronized and all repository gates pass.

## Delivery Phases

1. Project-init foundation: complexity advisor, project skill planner, orchestration, status, and uninit.
2. Optional integration: CodeGraph plan lifecycle and terminal CLI adapter.
3. Full-studio catalog: six agents, twelve skills, three packs, routing cases, docs, metadata, and version bump.
