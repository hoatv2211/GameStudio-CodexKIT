# Project Profile and Agent Overlay Design

**Status:** Approved on 2026-08-14

## Context

GameStudio-CodexKIT has a strong canonical skill catalog, packaging model, safety contract, and deterministic evaluation suite. Its current project scaffold detects broad subsystem categories, but it does not capture real multi-repository ownership, project-local validation commands, runtime topology, or executable agent roles. A read-only inspection of the `_Sabo` workspace demonstrated that those project-local facts materially improve routing and delegation without belonging in a reusable core catalog.

## Goals

- Add a project-profile seam for multi-repository game workspaces.
- Route work by repository, subsystem, owner skill, and validation slice.
- Ship reusable investigator, implementer, and verifier role templates.
- Generate project-local specialist agents from profile data without copying domain facts into the core kit.
- Make project discovery prune Unity, build, dependency, archive, and generated trees.
- Turn a sanitized `_Sabo`-shaped workspace into deterministic regression coverage.
- Preserve the canonical `skills/` source, generated-resource workflow, and safe uninstall guarantees.

## Non-Goals

- Do not distribute JX names, topology, encoding rules, paths, or proprietary workflow text.
- Do not overwrite an existing `.codex/config.toml`, project-local skill, agent, governance file, or unmanaged adapter output.
- Do not make Claude or GitHub compatibility trees a primary source of truth.
- Do not activate specialist agents without a project profile and an explicit safe apply step.

## Architecture

The upgrade uses four layers:

1. **Canonical catalog:** reusable skills, agent role templates, registries, validators, and generators live in GameStudio-CodexKIT.
2. **Project profile:** `.agents/project-profile.yaml` records project-local repositories, subsystems, validation, exclusions, topology notes, and agent specialization inputs.
3. **Generated overlay:** scaffold renders project-profile references and validation views; the per-project adapter materializes generic agent definitions, specialist definitions, and the inert activation snippet.
4. **Runtime activation:** generated agent files are inert until project configuration references them. Existing configuration is preserved; safe apply requires reviewer, backup manifest, and restore instructions.

## Project Profile Interface

The versioned profile records workspace metadata, repositories, subsystem ownership, validation commands, exclusions, specialist roles, and cross-project contracts. Callers learn one profile interface; discovery, routing, role generation, and validation-matrix rendering remain hidden behind helpers.

## Skill Changes

### New Skills

- `studio-workspace-routing`: selects the owning repository, subsystem, skill, phase, and narrow validation from a project profile.
- `studio-agent-orchestration`: selects investigator, implementer, verifier, or specialist roles while enforcing critical-path ownership, disjoint writers, concurrency limits, and no nested delegation.

### Updated Skills

- `using-game-studio-skills`: prefer project-profile routing when a profile exists.
- `studio-project-intake`: collect enough verified information to produce a profile draft.
- `studio-project-scaffold`: report and safely generate profiles, overlays, and role definitions.
- `feature-to-work-packets`: emit repository-phased work packets for cross-project contracts.
- `skill-authoring-and-audit`: audit project-local skill and role collisions while preserving update-first behavior.

## Agent Role Model

`registry/agent-roles.yaml` indexes `investigator`, `implementer`, and `verifier`. Canonical templates live under `agents/`. The per-project adapter copies owned templates to `.codex/agents/`, records hashes, and emits `.codex/agents.generated.toml`. Specialist roles are rendered only from profile data. Existing agent files and active config remain untouched.

Because the Codex plugin manifest does not activate custom agents directly, templates are distributed as repository resources and materialized project-locally. Skills remain the primary plugin interface.

## Scanner Design

Replace unprunable `Path.rglob` discovery with `os.walk` directory pruning. Default exclusions are `.git`, `.archive`, `archive`, `Library`, `Temp`, `Logs`, `obj`, `bin`, `node_modules`, and `.cache`. Profile exclusions extend these defaults. Discovery detects nested Git roots, Unity markers, project files, Lua, SQL, and existing governance without descending into excluded or reparse-point directories.

## Generated Outputs

Report-only scaffold proposes a project profile, registry, ownership contract, workspace map, validation matrix, adapter activation references, `AGENTS.md`, and `HANDOFF.md` when missing. The per-project adapter separately proposes and materializes generic agent TOMLs, specialist TOMLs, and the inert activation snippet. Existing files are preserved and reported as merge candidates. Generated files carry ownership markers and are removed only when recorded hashes still match.

## Evaluation and Dogfood

A sanitized multi-repository fixture models a non-Git workspace root, nested Unity client, MMO server, and Java service repositories, one cross-project workflow, generic and specialist roles, a large ignored cache tree, and a neighboring trigger boundary. The live `_Sabo` workspace remains read-only dogfood; unavailable runtime evidence is `BLOCKED`.

## Compatibility and Distribution

- Existing skill IDs and project adapters remain compatible.
- The canonical catalog grows from 33 to 35 skills.
- The plugin version advances from `1.2.0` to `1.3.0`.
- Root helpers remain canonical and are bundled through `registry/skill-resources.yaml`.
- Codex and Hermes Agent remain the primary distribution targets.

## Safety

- Inspection and profile drafting are read-only.
- Scaffold and agent materialization remain medium-risk safe mutations.
- Report-only precedes apply; apply requires reviewer and backup root.
- Existing `.codex/config.toml` is never overwritten.
- External repositories are not mutated during kit tests or dogfood.

## Acceptance Criteria

- Existing deterministic routing remains green.
- New profile-aware routing and agent orchestration cases pass.
- Large ignored cache trees do not cause full traversal or timeout.
- Existing local governance, skills, agents, and configuration are preserved.
- Generated files have hashes, safe uninstall behavior, backup manifests, and restore commands.
- Validators cover agent roles, profiles, new skills, resources, adapters, and version synchronization.
- All local gates in `AGENTS.md` complete with honest evidence labels.
