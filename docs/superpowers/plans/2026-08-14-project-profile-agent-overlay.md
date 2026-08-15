# Project Profile and Agent Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade GameStudio-CodexKIT with profile-driven multi-repository routing, generated agent roles, pruned discovery, and sanitized `_Sabo`-shaped dogfood coverage.

**Architecture:** A versioned project profile is the seam between reusable kit behavior and project-local facts. Canonical Python helpers validate and render profiles; canonical skills teach routing and orchestration; adapters materialize owned project-local files without replacing unmanaged configuration.

**Tech Stack:** Python 3.11+, PyYAML through the existing YAML loader, unittest, Markdown skills, YAML registries, JSON ownership manifests.

**Commit Policy:** Do not commit unless the user explicitly requests it.

## Task 1: Pruned Project Discovery

- [x] Add failing tests for ignored Unity and dependency trees.
- [x] Replace `rglob` discovery with pruned `os.walk` traversal.
- [x] Detect nested Git roots and expose them in scaffold reports.
- [x] Run `python -B -m unittest tests.studio_project_scaffold.test_project_scaffold`.

## Task 2: Project Profile

- [x] Add failing tests for valid, invalid, duplicate, and unsafe profiles.
- [x] Create `scripts/project_profile.py` with validation and deterministic renderers.
- [x] Make scaffold propose a conservative profile and project references.
- [x] Bundle the helper through `registry/skill-resources.yaml`.

## Task 3: Agent Roles

- [x] Add failing adapter and validator tests for role materialization.
- [x] Add `registry/agent-roles.yaml` and three canonical TOML templates.
- [x] Generate owned `.codex/agents` files and an inert activation snippet.
- [x] Preserve unmanaged agents and uninstall only matching generated hashes.

## Task 4: Skills and Routing

- [x] Add failing routing cases for workspace ownership and role selection.
- [x] Add `studio-workspace-routing` and `studio-agent-orchestration`.
- [x] Update intake, scaffold, root routing, work packets, and authoring audit skills.
- [x] Register capabilities, packs, personas, resources, and eval coverage.

## Task 5: Sanitized Dogfood

- [x] Add a sanitized `_Sabo`-shaped fixture.
- [x] Add archive/generated exclusions to external collision discovery.
- [x] Verify multi-repository routing, cache pruning, and specialist boundaries.

## Task 6: Distribution

- [x] Add failing assertions for version `1.3.0` and 35 skills.
- [x] Update plugin and marketplace metadata, docs, and catalog counts.
- [x] Regenerate only generator-owned resources.

## Task 7: Verification

- [x] Run resource sync check.
- [x] Run the full unittest suite.
- [x] Run validator, route eval, secret scan, policy check, collision eval, and doctor.
- [x] Run originality and catalog lifecycle audits.
- [x] Report Verified, Snapshot, Unverified, BLOCKED, commands, exit codes, and artifacts.
