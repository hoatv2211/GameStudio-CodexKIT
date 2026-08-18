---
name: using-game-studio-skills
description: Use when starting any GameStudio-CodexKIT task or when a model runner is unavailable and someone requests a confidence-based PASS.
version: 0.1.0
author: GameStudio-CodexKIT
license: MIT
compatibility:
  engines: [engine-agnostic]
  versions: [any]
  platforms: [windows, linux, macos]
metadata:
  studio:
    type: root
    lifecycle_stage: discover
    risk_level: read-only
    packs: [studio-core]
    side_effects: none
    artifact: operating-contract.md
    required_evidence: [task-packet, verdict]
    owner: HoaTV Studio
    reviewer: null
    maturity: beta
    last_reviewed: 2026-08-07
    provenance:
      derived_from: none
      patterns_from: [AGENTS.md evidence labels, sanitized studio operating contract]
      copied_text: none
---
# Using Game Studio Skills

## Overview
Apply the kit as a workflow router: inspect context, select the narrowest skill, preserve safety gates, and label every claim honestly.

## When to use
Use at the start of every kit-guided task and whenever a task changes scope, risk, owner, or verification strategy.

## When NOT to use
Do not use this root contract as a substitute for intake, debugging, mutation, review, build verification, or handoff workflows.

## Required inputs and context discovery
Collect the workspace and repository paths, current branch or snapshot, user goal, explicit constraints, available tools, project-profile path when present, and any do-not-touch paths.

## Safety and risk level
This skill is read-only. It classifies work and routes it; it never authorizes mutation, service control, database changes, publishing, credentials, or destructive cleanup.

## Workflow
1. Restate the goal, repository scope, constraints, and unavailable capabilities.
   Completion criterion: a bounded task packet exists and unknowns are labeled.
2. If `.agents/project-profile.yaml` exists or nested Git roots are present, route through `studio-workspace-routing`; otherwise select the narrowest matching workflow skill from the installed catalog.
   Completion criterion: one repository route, primary skill, and any explicit dependencies are named.
3. Assign `Verified`, `Snapshot`, `Unverified`, or `BLOCKED` to each material claim.
   Completion criterion: no PASS claim depends on confidence or memory alone.
4. Apply the risk gate before any side effect and preserve exact write ownership.
   Completion criterion: mutations are either authorized with rollback or remain blocked.
5. End with fresh verification and a handoff when work spans sessions.
   Completion criterion: commands, exit codes, artifacts, limitations, and next actions are recorded.

## Evidence and output contract
Return a task packet, selected skill route, risk tier, evidence labels, and final verdict. `BLOCKED` is a valid outcome; fabricated PASS is not.

## Handoff contract
Record repository/path, branch, goal, owned scope, do-not-touch paths, files touched, commands, verified results, snapshots, hypotheses, failures, decisions, next actions, and a reactivation prompt.

## Pitfalls and anti-rationalization
- “The change is small” does not waive intake or verification.
- “It compiled” does not prove runtime or regression safety.
- “The runner is unavailable” means `BLOCKED`, never PASS.
- “Another project uses this pattern” is a snapshot until this repository is inspected.

## Verification checklist
- [ ] The primary workflow skill is explicit.
- [ ] Every material claim has an evidence label.
- [ ] Side effects match the declared risk gate.
- [ ] Unavailable live operations are `BLOCKED`.
- [ ] Final verification is fresh.

## References and scripts
Use the active project's `AGENTS.md` when present and route through the installed skill catalog. Architecture, registry, and `scripts/doctor.py` maintenance checks are available only in a full repository clone.

## Negative scope
This root skill does not debug failures, mutate files, run database migrations, start or stop services, replace project intake, perform review lanes, generate adapters, or claim verification for commands it did not run.
