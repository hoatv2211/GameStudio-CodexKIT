---
name: studio-project-scaffold
description: Use when bootstrapping a new or newly adopted game repository with AGENTS.md, HANDOFF.md, .agents/CONTRACT.md, a subsystem registry, ownership rules, and preserved project-local skills.
version: 0.1.0
author: GameStudio-CodexKIT
license: MIT
compatibility:
  engines: [engine-agnostic, unity]
  versions: [any]
  platforms: [windows, linux, macos]
metadata:
  studio:
    type: workflow
    lifecycle_stage: build
    risk_level: medium
    packs: [studio-core, unity, cpp-lua-mmorpg]
    side_effects: files
    artifact: scaffold-report.json
    required_evidence: [detected-subsystems, created-file-list, preserved-file-list]
    owner: HoaTV Studio
    reviewer: Producer
    maturity: experimental
    last_reviewed: 2026-08-07
    provenance:
      derived_from: none
      patterns_from: [sanitized multi-project governance fixtures]
      copied_text: none
---
# Studio Project Scaffold

## Overview
Create the minimum project-local governance needed for safe multi-session work while preserving existing instructions and local skills.

## When to use
Use for a new game repository, an inherited legacy project without agent governance, or a project that needs standardized ownership, evidence labels, and handoff state.

## When NOT to use
Do not overwrite a mature project-local `.agents/` system, existing `AGENTS.md`, `HANDOFF.md`, or skills. Generate a report and merge plan instead.

## Required inputs and context discovery
Collect repository root, Git state, existing governance files, Unity markers, server projects, Lua/data trees, database inputs, generated paths, vendor paths, and project-local skill IDs.

## Safety and risk level
Scaffolding is medium-risk because it writes governance files. Run report-only first, preserve every existing file by default, require a reviewer, and never mutate external projects during kit tests.

## Workflow
1. Scan structure read-only and detect Unity, server, Lua, database, tooling, and generated subsystems.
   Completion criterion: detected subsystems and unknown areas are reported.
2. Inventory existing `AGENTS.md`, `HANDOFF.md`, `.agents/`, local skills, and ignore rules.
   Completion criterion: every existing governance artifact is marked preserve, merge, or BLOCKED.
3. Render the minimum scaffold with evidence, ownership, mutation, generated-file, and no-touch rules.
   Completion criterion: report-only output lists exact proposed files without writes.
4. Apply only missing files and merge registries without replacing project-local skill IDs.
   Completion criterion: created and preserved paths are both recorded.
5. Run project-local validation and inspect the generated handoff snapshot.
   Completion criterion: scaffold output is parseable and unresolved runtime facts remain Unverified or BLOCKED.

## Evidence and output contract
Produce `scaffold-report.json` with subsystem detection, source snapshots, proposed files, created files, preserved files, collisions, reviewer, and verification results.

## Handoff contract
Record project path, detected subsystems, existing local skills, created governance files, preserved conflicts, unverified owners, and the project-intake reactivation prompt.

## Pitfalls and anti-rationalization
- Similarity to golden fixtures does not authorize copying project-specific text.
- Never overwrite `project-*` or other project-local skills.
- Do not infer service ports or DB schemas from directory names.
- Generated scaffold state is only a starting Snapshot.

## Verification checklist
- [ ] Report-only ran before apply.
- [ ] Existing governance and local skills were preserved.
- [ ] Detected subsystems are evidence-backed.
- [ ] Created files carry generated markers where appropriate.
- [ ] Runtime facts remain Unverified or BLOCKED until checked.

## References and scripts
Use the bundled [scripts/project_scaffold.py](scripts/project_scaffold.py) with its [scripts/safe_mutation.py](scripts/safe_mutation.py) dependency. Sanitized golden fixtures are kit-maintenance resources available only in a full repository clone.
