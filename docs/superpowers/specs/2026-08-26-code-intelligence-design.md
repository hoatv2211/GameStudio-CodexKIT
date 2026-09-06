# Shared Code Intelligence Design

## Status

Design A was approved in conversation on 2026-08-26. This written specification is pending maintainer review before implementation planning.

Repository snapshot at specification time: `dev@341d15a91a65d4ed11300ea4b3c69fa33a8ced41`. The worktree already contained an unfinished Code Intelligence draft and unrelated changes; this specification does not approve replacing, committing, or publishing those changes.

The repository itself had no `.codegraph/` directory. No provider was installed, initialized, refreshed, queried, or removed while writing this specification.

## Problem

GameStudio-CodexKIT has an existing CodeGraph adapter and workflow-specific source inspection, but no shared contract for dependency, call-chain, blast-radius, architecture, or business-flow evidence. A provider can therefore expose useful relationships without a consistent answer to these safety questions:

- Is the index bound to the current repository, HEAD, and worktree?
- Does it cover every language and generated-code boundary relevant to the task?
- Was an edge extracted from source, inferred heuristically, or described by an LLM?
- Does an empty result mean no dependency, or only that the provider did not find one?
- Can an implementer use the result before editing, and can a verifier compare it after editing?
- Did a supposedly read-only provider write cache or index state into the inspected project?

The integration must remain useful when a provider is unavailable or incomplete, without turning missing graph evidence into permission to assume a small blast radius.

## Goals

1. Add one vendor-neutral Code Intelligence contract shared by agents and workflows.
2. Let agents inspect dependencies, call chains, affected paths, and generated-source boundaries before non-trivial code changes.
3. Extend the existing CodeGraph adapter through a normalized provider layer without breaking existing CodeGraph ownership or preference behavior.
4. Register Graphify as the experimental default candidate, GitNexus as an advanced optional candidate, Understand Anything as an onboarding and architecture candidate, and CodeGraph as legacy-compatible.
5. Keep provider selection capability-driven so a workflow depends on `impact`, `dependency-path`, `cross-repo`, `pdg`, `taint`, `architecture`, `domain-flow`, or `onboarding`, not on a vendor name.
6. Upgrade project intake, debugging, safe mutation, review, implementer, and verifier contracts to consume the shared evidence.
7. Enforce freshness, language coverage, provenance, ambiguity, generated ownership, and read-only isolation before issuing graph-backed claims.
8. Preserve authoritative source, generated-source ownership, tests, logs, and runtime evidence as the final decision basis.
9. Use governed dogfood evidence before enabling deeper provider-specific behavior.

## Non-goals

- Creating separate skills named after Graphify, GitNexus, Understand Anything, or CodeGraph.
- Automatically installing, initializing, refreshing, enabling hooks for, or deleting any provider.
- Treating graph output as runtime proof, test evidence, or authorization to mutate a project.
- Promising complete handling of reflection, dynamic dispatch, generated code, cross-language protocols, or cross-repository contracts.
- Silently selecting a weaker provider when the requested capability or language coverage is unavailable.
- Making Graphify query output a mutation authorization gate before the dogfood blockers are resolved.
- Deeply integrating GitNexus or Understand Anything before each is dogfooded under this same contract.
- Editing generated adapters, packs, or bundled skill scripts by hand.

## Selected Approach

Use a contract-first provider registry behind one canonical `code-intelligence-contract` skill and one canonical normalization helper.

Consumers ask for a capability and receive normalized status, query, and evidence objects. Provider-specific discovery and command construction stay behind adapters. The shared layer classifies graph evidence but never replaces the owning workflow's source, mutation, build, test, security, database, or release gates.

This approach is preferred over immediately rewriting the complete legacy CodeGraph adapter, which would create unnecessary compatibility and approval churn, and over documentation-only integration, which could not enforce freshness, provenance, capability, or isolation rules.

## Authority and Ownership

The active authority chain remains:

1. `AGENTS.md` for repository operation, evidence, mutation, ownership, and handoff.
2. Repository-local maintenance roles and skills for CodexKIT source work.
3. Registries for distributed capabilities, roles, packs, resources, and provider provenance.
4. Canonical distributed skills under `skills/`.
5. Root helpers under `scripts/`.
6. Generated and bundled copies as derived read-only outputs.

The shared contract owns normalization and evidence semantics. It does not own provider indexes. Existing provider artifacts remain user- or provider-owned, and are never added to the kit's owned-file deletion set.

One writer owns each canonical file or registry during implementation. The integrator owns shared registry resolution and the final verdict. Investigation, graph analysis, and review lanes remain read-only.

## Architecture

### 1. Provider descriptor registry

The registry describes providers without embedding their command output into workflow logic. Each descriptor contains:

- Stable provider ID and display name.
- Lifecycle role: experimental default candidate, advanced optional, onboarding optional, or legacy-compatible.
- Supported normalized capabilities.
- Discovery strategy and expected artifact kinds.
- Whether the provider can operate locally and read-only.
- Provider-declared licensing or terms review requirement.
- Known language, generated-code, dynamic-dispatch, cross-repository, and side-effect limitations.
- Maturity and dogfood evidence references.

The initial descriptors are:

| Provider | Initial role | Candidate capabilities | Initial integration boundary |
|---|---|---|---|
| Graphify | Experimental default candidate | `context`, `dependency-path`, `impact` | Opt-in discovery and evidence normalization only; no automatic extraction and no mutation gate |
| GitNexus | Advanced optional | `context`, `dependency-path`, `impact`, `cross-repo`, `pdg`, `taint` | Descriptor and capability routing only until separate dogfood and license/use review |
| Understand Anything | Onboarding optional | `architecture`, `domain-flow`, `onboarding` | Structural and LLM-semantic outputs remain separately labeled; no mutation gate |
| CodeGraph | Legacy-compatible | `status`, `context`, `dependency-path`, `impact` | Existing adapter behavior is mapped into the shared contract without changing ownership or install approval |

Capabilities are claims to be verified at runtime, not guarantees. A descriptor advertising a capability does not make a provider usable when its installed version, index, requested language, or repository scope cannot support that capability.

### 2. Normalized status contract

Provider discovery produces a status object before any graph query. It contains:

- Schema version.
- Provider ID and resolved version.
- Canonical repository identity.
- Current HEAD and deterministic worktree identity.
- Index revision and captured worktree identity, when available.
- Normalized index state.
- Advertised and runtime-confirmed capabilities.
- Requested, supported, and missing languages.
- Artifact paths and artifact validation results.
- Detected project-local side effects.
- Known limitations and recovery action.
- Discovery command and exit code when a command was actually run.

The canonical normalized states are:

| State | Meaning | Graph-backed result |
|---|---|---|
| `UNAVAILABLE` | Provider executable or integration is unavailable | `BLOCKED` |
| `NOT_INITIALIZED` | Provider is known but no usable index exists | `BLOCKED` |
| `FRESH` | Repository, HEAD, worktree, artifacts, capability, and required-language checks all agree | Query may proceed |
| `STALE_HEAD` | Index revision differs from current HEAD or cannot be proven equal | `BLOCKED` |
| `STALE_WORKTREE` | Captured and current worktree identities differ or cannot be proven equal | `BLOCKED` |
| `PARTIAL_LANGUAGE` | A required language, parser, generated boundary, or repository scope is missing or partial | `BLOCKED` |
| `BROKEN` | Status, artifacts, parsing, schema, or query execution failed | `BLOCKED` |
| `SIDE_EFFECT_VIOLATION` | A read-only probe or query changed inspected project state | `BLOCKED` |
| `USER_DISABLED` | The user disabled the provider | `BLOCKED` without prompting or mutation |

Legacy states such as `INITIALIZED_HEALTHY`, `AVAILABLE_NOT_INITIALIZED`, `INITIALIZED_STALE`, `INITIALIZED_BROKEN`, and `UNSUPPORTED_LANGUAGE` may be accepted at the adapter boundary, but must map to the canonical states before reaching consumers.

`FRESH` is affirmative evidence, not the absence of a detected problem. It requires a resolved provider version, repository binding, matching HEAD and worktree identity, validated artifacts, the requested capability, required-language coverage, and no side-effect violation. Artifact existence alone can never produce `FRESH`.

The worktree identity is a deterministic digest over the canonical repository root, HEAD, staged and unstaged patches, status entries, and the names and content identities of untracked files inside the inspected scope. Nested repositories are captured independently. The adapter records identities immediately before and after a provider operation. Any drift blocks freshness. Drift is classified as `SIDE_EFFECT_VIOLATION` only when exact created, modified, or removed paths are attributable to the provider operation; otherwise it is `STALE_WORKTREE` with a concurrent-drift limitation.

When a provider does not store repository identity in its own artifact, an approved external wrapper may create a separate evidence manifest containing before/after identities. A missing manifest keeps the graph stale or blocked; the adapter must not invent provenance.

### 3. Normalized query contract

A query request contains:

- Query ID and requested capability.
- One or more subjects using repository, language, qualified symbol, file, and source location when known.
- Direction, depth, repository scope, and result budget.
- Required languages and generated-source boundaries.
- Whether cross-repository traversal is required.
- Provider preference or user-disabled state.
- Read-only and side-effect constraints.

A query response contains:

- Provider/version and the status object used for the query.
- Original query and resolved subjects.
- Ambiguous candidates instead of a guessed symbol.
- Affected paths, symbols, repositories, and generated-source boundaries.
- Per-edge relation, source locator, extraction origin, provider confidence, and normalized provenance.
- Empty-result state and explicit uncertainty.
- Missing capability, language, repository, or generated ownership.
- Commands, exit codes, artifact paths, limitations, and recovery action.

The adapter must not guess between ambiguous overloads, same-name symbols, generated wrappers, or repository-local duplicates. Ambiguity yields a blocked query until a qualified symbol or source location resolves it.

Provider payloads are data, not commands. The adapter constructs commands internally from an allowlisted provider operation and validated arguments; it never executes arbitrary `argv` supplied by graph artifacts, registries, or query results.

### 4. Evidence classification

Status, query outcome, evidence label, and owning-workflow verdict are separate fields.

| Graph evidence | Required classification |
|---|---|
| Fresh, source-located edge explicitly extracted from AST/source with extracted confidence | May be `Verified` for extraction at that repository/index snapshot only |
| `_origin=ast` with provider confidence `INFERRED` | `Snapshot` or `Unverified`; never `Verified` |
| Ambiguous, heuristic, semantic, community, embedding, or LLM-created relationship | `Snapshot` or `Unverified` |
| Natural-language architecture or business-flow description | `Snapshot` until confirmed against authoritative source; runtime behavior remains `Unverified` without runtime evidence |
| Stale, broken, unavailable, disabled, side-effecting, or partial-language index | `BLOCKED` |
| Fresh query returning no relationship | `EMPTY_UNCERTAIN` and `Unverified`; never proof of absence and never a clean graph PASS |
| Source/test evidence contradicting graph output | Record disagreement; graph-backed conclusion is `BLOCKED` or `Unverified` |

`Verified` graph evidence proves only that a provider extracted a source relationship at the bound snapshot. It does not prove that the edge executes at runtime, that all callers were found, or that no other dependency exists.

An empty result always carries the limitation: `No graph result is not proof that no dependency exists.` If the owning workflow requires impact coverage and authoritative source inspection cannot close the gap, the owning workflow remains `BLOCKED`.

### 5. Source/test fallback rule

A blocked graph lane blocks every graph-backed `PASS`; it does not automatically prohibit all code mutation.

The owning workflow may proceed through authoritative source inspection and focused tests only when all of the following are recorded:

1. The graph blocker and missing coverage are explicit.
2. Source inspection identifies the canonical owner and known callers/consumers.
3. Generated-file authority is resolved for every generated output in scope.
4. Focused regression tests or another authoritative verifier cover the proposed behavior.
5. The named reviewer explicitly acknowledges residual graph uncertainty.
6. The mutation's existing risk, approval, backup, restore, and scope gates still pass.

The owning workflow remains `BLOCKED` when the change crosses an unresolved generated-source, dynamic-dispatch, language, repository, security, database, service, or release boundary that source and tests do not adequately cover.

This fallback must be visible in the evidence artifact. It is not a silent downgrade and never changes a graph lane from `BLOCKED` to `PASS`.

### 6. Provider selection

Selection follows this order:

1. Honor `USER_DISABLED` and explicit user preference.
2. Filter by requested normalized capability.
3. Probe installed versions and index status without mutation.
4. Require repository, HEAD, worktree, language, repository-scope, and side-effect checks.
5. Choose the highest-priority fresh provider that satisfies the request.
6. If no provider qualifies, return a blocked graph lane and the source/test fallback path.

Graphify is the first experimental candidate only after an operator opts into provider use. "Default" does not mean automatic install, automatic indexing, or authorization to write cache state. Provider fallback must be reported; a consumer may not silently replace a requested advanced capability with a weaker context query.

### 7. Generated, dynamic, and cross-repository boundaries

Generated nodes and paths must identify their canonical source or generator. A graph finding that reaches a generated file without a verified authority mapping cannot authorize editing that file and keeps mutation ownership `BLOCKED`.

Reflection, string-dispatched calls, serialization registration, Lua receiver dispatch, native interop, and similar dynamic paths are explicit limitations unless confirmed through source, generator configuration, tests, logs, or runtime traces.

A cross-repository result binds every participating repository to its own path, HEAD, worktree identity, index state, language coverage, and artifact. One stale or missing repository makes the cross-repository graph conclusion `BLOCKED`; a fresh repository may still provide a bounded local finding.

### 8. Read-only isolation, privacy, and terms

- Discovery, status, and query operations are read-only by contract.
- Installation, index creation or refresh, hooks, daemon startup, cache cleanup, and provider removal are separate mutations requiring report-only planning and explicit approval.
- Before/after repository identities detect provider writes. Unexpected created, modified, or removed project files produce `SIDE_EFFECT_VIOLATION`.
- Evidence artifacts use approved ignored locations and must not expose secrets or private absolute paths in distributable output.
- Provider license and terms are checked before enablement; capability presence is not license authorization.
- Cleanup targets only exact provider-created artifacts after path, identity, and ownership verification. Cleanup is never implied by a failed run.

## Workflow and Agent Integration

### `studio-project-intake`

Intake records provider/version, repository and worktree binding, index state, requested-language coverage, capabilities, artifact paths, side effects, and limitations. Missing or stale graph evidence becomes a `BLOCKED` capability item, not a failed project intake and not a clean dependency result.

### `evidence-first-debugging`

Debugging may use a fresh graph to trace data and control flow from the observed symptom toward candidate sources. It labels extracted, inferred, dynamic, generated, and runtime edges separately. Root cause still requires source, logs, tests, or runtime confirmation.

### `safe-project-mutation`

Before a non-trivial edit, mutation planning requests affected callers, consumers, repositories, and generated boundaries. The result informs scope but never widens approved ownership automatically. Missing graph coverage invokes the explicit source/test fallback rule or leaves the mutation blocked.

### `review-swarm`

Review may add one independent read-only dependency/impact lane. That lane owns graph blast-radius findings, source disagreements, and missing coverage. It cannot issue runtime PASS, edit files, or replace the integrator's verdict.

### Implementer

Before editing non-trivial code, the implementer consumes a fresh impact artifact or records the graph blocker and approved fallback. The implementer keeps the approved write scope bounded even when the graph reports a larger blast radius, escalates newly discovered ownership, and records the exact pre-change impact snapshot.

### Verifier

After editing, the verifier independently probes freshness and repeats or validates the relevant impact query against the post-change snapshot. It compares pre-change expectations, changed paths, post-change affected paths, source/tests, and any graph disagreement. A stale post-change index is `BLOCKED`, not evidence that the change is safe.

### Investigator

An investigator may use the shared contract for read-only context and symbol resolution. This is optional in the first implementation and does not replace the required implementer pre-impact or verifier post-impact contracts.

## End-to-End Data Flow

1. Intake captures repositories, revisions, dirty state, required languages, generated boundaries, do-not-touch paths, risk, and available providers.
2. The shared layer probes provider status without mutation and normalizes the result.
3. The owning workflow requests a capability rather than a vendor command.
4. The adapter resolves the subject or returns ambiguity without guessing.
5. The provider result is normalized per edge and checked for freshness, language coverage, generated ownership, and side effects.
6. Important findings are confirmed against authoritative source, tests, logs, or runtime evidence.
7. Before mutation, the implementer records the impact snapshot and approved write boundary.
8. The existing mutation workflow applies its independent approval, backup, restore, and verification gates.
9. After mutation, the verifier rechecks index freshness, reruns the bounded impact analysis, and compares pre/post findings with actual changed paths and tests.
10. The owning workflow emits its native artifact plus a normalized Code Intelligence evidence object and remaining risk.

## Error Handling

| Condition | Required behavior |
|---|---|
| Provider executable missing | `UNAVAILABLE`; do not install automatically |
| Artifact exists without revision/worktree provenance | `STALE_HEAD` or `STALE_WORKTREE`; never infer freshness |
| HEAD or worktree changes during extraction/query | `STALE_HEAD` or `STALE_WORKTREE`; discard graph-backed PASS |
| Required language/parser missing or partial | `PARTIAL_LANGUAGE`; name missing coverage |
| Requested capability is absent | `BLOCKED`; do not substitute a weaker capability silently |
| Ambiguous symbol or overload | Return candidates and `BLOCKED`; do not guess |
| Empty result | `EMPTY_UNCERTAIN` and `Unverified`; preserve absence uncertainty |
| Unknown or inferred provenance | `Snapshot`/`Unverified`; require confirmation |
| Source disagrees with graph | Record the mismatch and prefer authoritative source; graph conclusion remains blocked or unverified |
| Provider writes inside inspected project | `SIDE_EFFECT_VIOLATION`; record exact paths and do not clean broadly |
| Generated authority missing | Block mutation ownership for the generated path |
| Post-change index not refreshed and rebound | Verifier reports `BLOCKED`; pre-change graph cannot prove post-change safety |
| Provider command or schema fails | `BROKEN`; preserve command, exit code, tight error excerpt, and artifact |

## Artifact Contracts

The normalized status and query evidence may be stored in `code-intelligence-evidence.json` or embedded in the owning workflow artifact. The minimum fields are:

- `schema_version`
- `provider` and `provider_version`
- `repository`, `revision`, and `worktree_identity`
- `index_revision`, `index_worktree_identity`, and `index_state`
- `capability`, `query`, and `resolved_subjects`
- `required_languages`, `supported_languages`, and `missing_languages`
- `affected_paths`, `affected_symbols`, and `generated_boundaries`
- Per-edge relation, source locator, origin, confidence, and normalized provenance
- `query_state`, `evidence_label`, and graph-lane verdict
- Source, test, log, or runtime confirmations
- Side effects, limitations, disagreements, and residual risk
- Commands, exit codes, artifact paths, and next action

Pre-change and post-change artifacts share a query identity so the verifier can compare them. Comparison output records added, removed, unresolved, and unchanged affected paths, plus changed files absent from the pre-change impact result.

## Canonical Files and Distribution Boundary

Implementation is expected to update only canonical owners first:

- One distributed `skills/code-intelligence-contract/` skill.
- Root normalization and provider adapter helpers under `scripts/`.
- Existing canonical intake, debugging, mutation, and review skills.
- Canonical agent templates for implementer and verifier; investigator integration remains optional.
- Capability, pack, resource, upstream-provenance, and routing eval registries as required.
- Focused tests and governed dogfood evidence references.

Bundled scripts and scaffold agent templates are regenerated from their canonical owners. No generated adapter, pack, project overlay, or `skills/*/scripts/` copy is patched manually.

Because the new skill, helper, registries, and agent templates change the distributed plugin payload, implementation completion requires a synchronized semantic-version update across authoritative plugin and marketplace metadata. Versioning does not authorize commit, push, publish, or release.

## Testing Strategy

### Deterministic RED-first tests

Implementation begins with tests proving the current draft is incomplete:

1. HEAD drift produces `STALE_HEAD` and blocks graph-backed evidence.
2. Worktree drift produces `STALE_WORKTREE` and blocks graph-backed evidence.
3. Missing required language or parser produces `PARTIAL_LANGUAGE`.
4. `_origin=ast` combined with `confidence=INFERRED` is not `Verified`.
5. Ambiguous symbol resolution blocks instead of selecting the first candidate.
6. A fresh empty result records `EMPTY_UNCERTAIN` and never proves absence.
7. A provider-created project-local cache produces `SIDE_EFFECT_VIOLATION`.
8. Missing generated-source authority blocks mutation ownership.
9. Provider capability mismatch blocks instead of falling back silently.
10. Implementer pre-impact and verifier post-impact artifacts are comparable and expose drift.
11. Provider payloads cannot supply arbitrary executable argument vectors.
12. Existing CodeGraph status, preference, install-plan, ownership, and restore behavior remains backward-compatible.
13. Provider installation, indexing, refresh, cleanup, and hooks are never triggered by discovery or query normalization.
14. Registries contain one shared skill and no vendor-named skill IDs.

### Focused integration tests

- Map legacy CodeGraph states into the canonical state model.
- Validate registry descriptor capabilities and unsupported-capability behavior.
- Validate canonical-to-bundled resource synchronization.
- Validate agent template regeneration and implementer/verifier contracts.
- Validate workflow artifacts preserve graph blockers and source/test fallback acknowledgement.
- Validate private paths and secrets are not exported in distributable graph evidence.

### Repository gates

After focused tests pass, run every local gate required by `AGENTS.md`:

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
```

Lifecycle audits and dogfood commands retain honest `BLOCKED` results when upstream content, governed runners, live projects, or session history are unavailable.

## Dogfood Evidence and Rollout

### Existing Graphify evidence

The 2026-08-26 read-only dogfood report covers one authorized private Unity project with Graphify `0.9.50` in local AST-only mode.

The owner-constrained second private project is excluded; no data was accessed or reported.

Observed evidence supports bounded experimental use but blocks deep integration:

- Snapshot: the authorized private Unity project produced useful direct C# evidence but missed generated wrapper calls and the C# to generated-Lua to Lua-handler path.
- Snapshot: nodes and edges marked with AST origin included both extracted and inferred confidence, proving that origin alone is insufficient.
- Snapshot: generated-path nodes lacked generated-authority classification.
- Generated, Lua, C++, cross-language, and cross-repository gaps remain BLOCKED or Unverified according to the sanitized authorized-private-Unity-project evidence.
- Cache and isolation governance remains unresolved, so no new provider run is authorized by this design.
- Snapshot: missing SQL parsers and partial parses prevented project-wide coverage claims.
- Cross-repository contract accuracy was not demonstrated by these runs and remains `BLOCKED` pending named source-truth cases spanning separately bound repositories.

The project-wide graph verdict therefore remains `BLOCKED`.

### Phase 1: Minimal contract integration

- Land the shared skill, normalized descriptors, strict status/evidence schemas, legacy CodeGraph mapping, workflow contracts, and tests.
- Keep Graphify experimental and opt-in.
- Do not execute deep provider queries automatically.
- Preserve source/test fallback and honest graph-lane blockers.

### Phase 2: Provider dogfood

- Rerun Graphify only after project-local cache isolation and before/after identity capture are addressed.
- Use stable authorized snapshots for an authorized private Unity project only.
- Measure precision and recall separately for Unity/C#, C++, Lua, generated code, cross-language protocols, and cross-repository contracts.
- Record ambiguous symbols, false positives, false negatives, parser gaps, elapsed time, artifact size, side effects, and cancellation behavior.
- Dogfood GitNexus for advanced impact, cross-repository, PDG, and taint capabilities under the same freshness and evidence contract.
- Dogfood Understand Anything for onboarding, architecture, and business-domain flows while separating structural extraction from LLM-semantic summaries.

### Phase 3: Governed promotion

Deep integration requires a separate maintainer-approved promotion record. At minimum it must contain:

- Stable repository and worktree binding for every benchmark run.
- Required-language and generated-boundary coverage.
- Per-capability precision/recall measurements over named source-truth cases.
- Zero unauthorized project-local writes in governed runs.
- Correct provenance classification in deterministic tests.
- Documented false-positive, false-negative, dynamic-dispatch, generated-code, and cross-repository limitations.
- Verified license/use suitability for the enabled provider and environment.
- A rollback plan and an explicit statement of which workflow decisions the provider may influence.

Until that record exists, provider output remains advisory and cannot be the sole basis for mutation authorization or runtime PASS.

## Success Criteria

The initial implementation is complete only when:

1. Exactly one shared vendor-neutral Code Intelligence skill is distributed.
2. Graphify, GitNexus, Understand Anything, and CodeGraph are represented through provider descriptors rather than vendor-specific skills.
3. The normalized status contract binds provider output to repository, HEAD, worktree, required languages, capabilities, artifacts, and side effects.
4. The evidence classifier distinguishes extracted source edges from inferred and LLM-semantic relationships using per-edge confidence and provenance.
5. Stale, broken, unavailable, disabled, partial-language, ambiguous, or side-effecting graph states cannot produce graph-backed PASS.
6. Empty graph results explicitly preserve dependency uncertainty.
7. Intake, debugging, mutation, review, implementer, and verifier contracts implement their specified Code Intelligence responsibilities.
8. Implementer pre-impact and verifier post-impact artifacts can be compared deterministically.
9. Existing CodeGraph behavior remains backward-compatible through the shared layer.
10. Discovery and normalization never install, index, refresh, hook, clean, or otherwise mutate a provider or consuming project.
11. The Graphify dogfood blockers remain visible and deep integration remains gated on governed evidence.
12. Focused tests and every required local gate have fresh command/exit evidence.
13. Distributed resources and semantic-version metadata are synchronized from canonical sources.
14. No unrelated tracked or untracked work is overwritten, committed, pushed, or published.

## Risks and Mitigations

- **A vendor-neutral schema collapses provider-specific meaning.** Preserve raw provider fields inside bounded artifacts while requiring normalized capability, status, provenance, and limitation fields for consumers.
- **Freshness is claimed from artifact existence.** Require explicit repository, HEAD, and worktree binding; otherwise block.
- **Graphify becomes a de facto mandatory dependency.** Keep it opt-in, experimental, and replaceable by capability.
- **Graph output expands write ownership.** Treat impact as escalation evidence; require explicit scope approval before adding files.
- **An inferred edge is upgraded because it came from an AST run.** Classify with per-edge confidence and provenance, not run origin alone.
- **Empty output creates false confidence.** Emit `EMPTY_UNCERTAIN` and the mandatory absence limitation.
- **Generated code is edited directly.** Require canonical generator ownership before mutation.
- **Cross-repository output mixes snapshots.** Bind and report every repository independently; one stale participant blocks the cross-repository conclusion.
- **Read-only providers leave caches or hooks.** Compare before/after state and emit `SIDE_EFFECT_VIOLATION`; cleanup remains an exact approved action.
- **Legacy CodeGraph behavior regresses.** Keep compatibility tests for status, preferences, install planning, ownership, and restore.
- **Provider payload reaches command execution.** Construct operations from internal allowlists and validated arguments only.
- **Distribution drifts.** Edit canonical sources, regenerate derived copies, and require resource-sync and packaging tests.

## Decision Summary

- Adopt Design A: one contract-first, vendor-neutral Code Intelligence layer.
- Keep one shared skill; do not create vendor-named skills.
- Use Graphify as the experimental opt-in default candidate, not an automatic or authoritative mutation gate.
- Keep GitNexus advanced-optional and Understand Anything onboarding-optional until separate dogfood.
- Preserve CodeGraph through a legacy-compatible adapter mapping.
- Require repository, HEAD, worktree, capability, language, generated-ownership, provenance, and side-effect evidence.
- Allow explicit source/test fallback without converting a blocked graph lane into PASS.
- Require implementer pre-impact and verifier post-impact comparison.
- Gate deep integration on governed provider evidence and a separate maintainer promotion decision.
