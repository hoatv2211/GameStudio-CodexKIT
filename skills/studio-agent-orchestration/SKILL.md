---
name: studio-agent-orchestration
description: Use when selecting project investigator, implementer, independent verifier, or profile specialist roles with expected output, do-not-touch scope, critical-path ownership, disjoint writers, concurrency limits, or no child agents.
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
    lifecycle_stage: plan
    risk_level: read-only
    packs: [studio-core]
    side_effects: none
    artifact: agent-plan.yaml
    required_evidence: [critical-path, ownership-map, role-contracts]
    owner: HoaTV Studio
    reviewer: null
    maturity: experimental
    last_reviewed: 2026-08-14
    provenance:
      derived_from: none
      patterns_from: [sanitized bounded investigator implementer verifier roles]
      copied_text: none
---
# Studio Agent Orchestration

## Overview
Choose agent roles only where parallelism creates leverage. Keep the immediate critical path on the main thread and make every sidecar contract independently verifiable.

## When to use
Use when two or more independent workstreams exist, repeated discovery can be partitioned, a stable slice needs independent verification, or a project profile declares a specialist role.

## When NOT to use
Do not delegate small one-file work, immediate blockers, overlapping writes, shared unstable contracts, or tightly coupled edit-test iteration. Do not use a specialist outside its declared repository.

## Required inputs and context discovery
Collect the workspace route, immediate critical-path action, candidate workstreams, exact write sets, read-only scopes, expected outputs, concurrency limit, available role definitions, and validation requirements.

## Safety and risk level
Planning is read-only. Agent role selection never expands mutation permissions. Investigator and review lanes remain read-only; implementers own exact disjoint paths; verifiers may write only normal test/build artifacts.

## Workflow
1. Identify the immediate critical-path action and keep it on the main thread.
   Completion criterion: no sidecar blocks the next local action.
2. Reject workstreams with overlapping files, generated targets, or unstable shared interfaces.
   Completion criterion: every concurrent writer has a disjoint write set.
3. Select the narrowest role: investigator for ownership discovery, implementer for bounded writes, verifier for independent checks, or a profile-declared specialist for difficult domain work.
   Completion criterion: role choice is justified by scope rather than prestige.
4. Bound concurrency by project profile and available independent work.
   Completion criterion: concurrency never exceeds three and may be zero.
5. Give each sidecar ownership, do-not-touch scope, expected output, and verification contract.
   Completion criterion: sidecars cannot create child agents and the main thread owns integration.

## Evidence and output contract
Produce `agent-plan.yaml` with critical path, role, owner, paths, do-not-touch, expected output, validation, concurrency, delegation reason, integration owner, and rejected parallelism.

## Handoff contract
Record active roles, ownership transfers, completed outputs, conflicts, commands, remaining verification, integration decisions, and the next main-thread action.

## Pitfalls and anti-rationalization
- More agents do not make coupled work independent.
- A verifier does not become a source writer because a test fails.
- Specialist knowledge does not grant sibling-repository ownership.
- Waiting for a sidecar while local work is available wastes the critical path.

## Verification checklist
- [ ] The main thread retains the critical path.
- [ ] Concurrent write scopes are disjoint.
- [ ] Role selection matches the task contract.
- [ ] Concurrency respects the profile and never exceeds three.
- [ ] Sidecars have expected outputs and cannot delegate.

## References and scripts
Use `registry/agent-roles.yaml` in a full repository clone and project-local `.codex/agents.generated.toml` only as an activation snippet. Use `studio-workspace-routing` before selecting project specialists.
