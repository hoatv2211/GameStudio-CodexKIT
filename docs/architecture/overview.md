# Architecture

## Source of truth

Workflow logic lives only in `skills/<name>/SKILL.md` and progressively loaded references, scripts, templates, or assets. Root `scripts/` files are canonical helper implementations; `registry/skill-resources.yaml` deterministically copies the runtime subset into the owning skill directories. Registries index capabilities, agent roles, personas, packs, skill resources, and upstream snapshots. Personas contain perspective and routes only. The repository root serves both the native Codex plugin and Hermes Agent skill discovery; adapters and packs are generated optional exports.

Active authority flows from `AGENTS.md` to registries, canonical skills, and maintained documentation. The ignored local `.archive/` may hold maintainer history but is never distributable authority and must not drive current execution.

The catalog contains 47 canonical skills across seven additive packs: `studio-core`, `unity`, `cpp-lua-mmorpg`, `production-design-liveops`, `production-management`, `content-production`, and `product-analytics`. Shared skills may appear in more than one pack without duplicating canonical source text. The registry also defines 22 canonical agent roles. `.codex-plugin/plugin.json` exposes the canonical skill catalog directly.

## Naming contract

`MOStudio Kit` is the public display name used in plugin interfaces, landing pages, banners, screenshots, and user-facing installation guidance. `GameStudio-CodexKIT` remains the source repository name and therefore stays unchanged in repository URLs, GitHub Pages paths, install commands, source-repository maintenance instructions, stable adapter identifiers, and historical or provenance records. The plugin ID `game-studio-codex-kit` is also stable and is not derived from the display name.

Every canonical skill owns `agents/openai.yaml` for Codex-facing UI metadata. Its `display_name` follows `MOStudio Kit: <skill heading>`; otherwise Codex falls back to humanizing the stable namespaced skill ID and exposes the repository-derived `Game Studio Codex Kit: ...` label in the picker.

## Layers

1. Policy: evidence, mutation, ownership, archive, and handoff contracts in `AGENTS.md`.
2. Router/context: root skill, project intake, project profiles, multi-repository routing, agent orchestration, and persona lenses.
3. Workflow orchestration: design, planning, debugging, review, mutation, and handoff skills.
4. Domain execution: Unity, C++, Lua, MMORPG, database, production, release, and liveops skills plus pure helpers.
5. Evidence adapters: reports, verdicts, summaries, manifests, and handoffs.
6. Quality: validator, routing, external-catalog collision, behavior, pressure, safety, secret, policy, and originality gates.
7. Governance: provenance, maturity, lifecycle promotion, session history, and observed KPIs.

## Skill and persona boundary

Skills own reusable procedures and output contracts. Personas are thin lenses that route to skills; they do not duplicate workflows. Commands and workflow documents are entry points rather than alternate sources of truth.

## Evaluation model

Tier-A routing is deterministic and covers 46 routed skills with 276 cases. The external-catalog collision fixture checks that studio-specific routes beat generic neighboring catalogs; `--external-root` can add installed Codex/Hermes catalogs to the same rank-1 check. Behavior, pressure, Tier-B, and real-project dogfood are runner-backed: export is deterministic, but PASS requires exact case coverage and evidence fields.

Without a model runner or live project, the correct status is `BLOCKED`. Keyword routing proves catalog separation, not real model behavior.

## Risk model

Read-only work runs automatically. Low-risk changes require a visible diff and verification. Medium risk requires exact scope, manifest or backup, restore path, and reviewer. High-risk, database, service-control, credential, destructive, or publish operations require explicit human approval and dry-run evidence.

## Distribution model

Codex and Hermes Agent are the two primary distributions. `.claude-plugin/marketplace.json` exposes the repository-root Codex plugin from GitHub, `.codex-plugin/plugin.json` points directly at canonical `skills/`, and the Agent Skills CLI discovers those same directories for `hermes-agent`. Hermes copies individual skill directories rather than repository-root maintenance files, so every runtime helper is generated into the skill that owns it. Neither primary path duplicates workflow text.

Seven deterministic packs provide scoped installation. Hermes and Codex adapters remain optional exports regenerated from canonical skills. The per-project adapter is report-only by default; apply requires a reviewer, a disjoint backup root, and an approved plan digest. It merges kit-owned skills into `.agents/`, combines packaged generic agent templates with a profile specialist overlay under `.codex/agents/`, and emits an inert activation file for manual merge while it leaves `.codex/config.toml` untouched. Per-file ownership hashes preserve unmanaged local agents and enable hash-safe uninstall; drift, unsafe links, or incomplete cleanup produce a `PARTIAL` recovery report instead of destructive removal.

Generated content carries a `Generated by scripts/... Do not edit manually.` marker. `scripts/sync_skill_resources.py --check` detects missing or stale installed-helper sources, and generators refuse to replace unmanaged output.

## Evidence lifecycle

`evidence/example/` documents the portable evidence format. Reproducible local runner output belongs under ignored `evidence/local/`; CI stores equivalent files as workflow artifacts. Durable PASS claims should be attached to the target project or release, not baked into the reusable template.

## Template boundary

The distributable tree contains the root plugin manifest, repository marketplace metadata, canonical workflows, generated per-skill helpers, registries, tests, eval fixtures, policy, canonical root scripts, CI, maintained docs, adapter generators, upstream restore metadata, and a small evidence example. Generated `adapters/` output is ignored and rebuilt on demand.

It excludes research clones, runner exports, caches, local execution state, dated dogfood output, reproducible verification residue, and the ignored local `.archive/` history directory.
