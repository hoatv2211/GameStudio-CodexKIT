# Architecture

The full skill list with routing triggers, risk gates, and artifacts is in [`docs/CATALOG.md`](../CATALOG.md). Practical usage is covered by the [Vietnamese skill and agent guide](../huong-dan-su-dung-skill-agent.md) and the [Wiki-ready English guide](../wiki-skill-agent-user-guide.md). Observed adoption evidence and remaining blockers are in [`docs/adoption.md`](../adoption.md).

## Source of truth

Workflow logic lives only in `skills/<name>/SKILL.md` and progressively loaded references, scripts, templates, or assets. Root `scripts/` files are canonical helper implementations; `registry/skill-resources.yaml` deterministically copies the runtime subset into the owning skill directories. Registries index capabilities, agent roles, personas, packs, skill resources, and upstream snapshots. Personas contain perspective and routes only. The repository root serves both the native Codex plugin and Hermes Agent skill discovery; adapters and packs are generated optional exports.

Active authority flows from `AGENTS.md` to registries, canonical skills, and maintained documentation. The ignored local `.archive/` may hold maintainer history but is never distributable authority and must not drive current execution.

The catalog contains 49 canonical skills across seven additive packs: `studio-core`, `unity`, `cpp-lua-mmorpg`, `production-design-liveops`, `production-management`, `content-production`, and `product-analytics`. Shared skills may appear in more than one pack without duplicating canonical source text. The registry also defines 24 canonical agent roles. `.codex-plugin/plugin.json` exposes the canonical skill catalog directly.

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

## Role-first planning boundary

Role UX is a presentation and selection layer over canonical skills, not another workflow authority. Its pure planner combines project-profile defaults with detected subsystems and returns a report-only task packet in the planning state `READY`, `AMBIGUOUS`, or `BLOCKED`; these are never runtime PASS verdicts. `READY` authorizes no execution or mutation. An ambiguous top-two result asks one focused question. Role defaults remain advisory and cannot grant mutation, service-control, or approval authority.

The contract has three stages: the task packet records planning state; only the selected canonical workflow executes or reviews its own actions and emits its native artifact; then a normalized evidence card records the observed runtime `PASS`, `BLOCKED`, or `FAIL` verdict. The router cannot fabricate that final runtime verdict. Basic mode reduces visible routing controls, while Advanced mode may select a reported workflow candidate explicitly with `--workflow`; neither mode weakens evidence, mutation, or approval gates. The optional `gamestudio guide [root] --intent <intent>` command remains report-only, whereas `gamestudio init --apply` is a separately gated project-adoption mutation.

Golden Paths are registry-backed route families, not new workflow authorities. A family may expose multiple canonical workflow candidates. Basic mode asks one clarifying question when repository and intent evidence cannot safely select one; Advanced mode may select a reported candidate explicitly. Adoption metrics are runner-backed and remain BLOCKED without governed result artifacts.

The five public intents Diagnose, Verify, Plan Change, Ship, and Handle Incident route across eight implemented Unity/MMORPG Golden Path families. Unsupported combinations remain `BLOCKED`; family selection never grants workflow execution or mutation authority.

## Evaluation model

Tier-A routing is deterministic and covers 48 routed skills with 306 cases. The external-catalog collision fixture checks that studio-specific routes beat generic neighboring catalogs; `--external-root` can add installed Codex/Hermes catalogs to the same rank-1 check. Behavior, pressure, Tier-B, eighteen-scenario real-project dogfood, and studio adoption are runner-backed: export is deterministic, but PASS requires exact case coverage and evidence fields.

## UI art and motion authority

`unity-ui-art-and-motion-production` is an experimental, medium-risk workflow for Figma- and AI-assisted UI assets plus micro-motion. It also accepts flattened or AI-generated UI screenshots as report-only decomposition inputs. Every candidate bbox stays in original-pixel coordinates and is reviewed as `raster`, `native-ui`, `background`, or `discard`; overlay candidates must intersect their parent background. Background repair retains the original plus hash-bound `raw-full` and `local-composite` variants, and a human reviewer must approve the candidate and restoration choice before it enters the Figma/Unity import path. Figma owns approved visual intent and revision provenance; Unity owns layout, state, input, reduced-motion behavior, and runtime performance. A closed design brief captures the visual system, prompt lineage, variants, copy policy, and negative constraints; static QC checks supported PNG/JPEG/SVG structure, dimensions, alpha where decodable, export hashes, source revision, and text policy. Closed decomposition, asset, and motion manifests bind source dimensions, revisions, hashes, Unity targets, stack selection, native/existing drivers, and restore data. The bundled helpers emit schema-bound review evidence, an art-QC report, and a report-only import plan; `safe-project-mutation` gates any apply. Without the configured visual tools, a real Unity project, reviewer approval, or runtime captures, the result remains `BLOCKED`.

Without a model runner or live project, the correct status is `BLOCKED`. Keyword routing proves catalog separation, not real model behavior.

## Risk model

Read-only work runs automatically. Low-risk changes require a visible diff and verification. Medium risk requires exact scope, manifest or backup, restore path, and reviewer. High-risk, database, service-control, credential, destructive, or publish operations require explicit human approval and dry-run evidence.

## Distribution model

Codex and Hermes Agent are the two primary distributions. `.claude-plugin/marketplace.json` exposes the repository-root Codex plugin from GitHub, `.codex-plugin/plugin.json` points directly at canonical `skills/`, and the Agent Skills CLI discovers those same directories for `hermes-agent`. Hermes copies individual skill directories rather than repository-root maintenance files, so every runtime helper is generated into the skill that owns it. Neither primary path duplicates workflow text.

Seven deterministic packs provide scoped installation. Generated pack artifacts resolve declared pack dependencies transitively and include every skill in that closure; validation fails if a capability dependency is unavailable. Hermes and Codex adapters remain optional exports regenerated from canonical skills. The per-project adapter is report-only by default; apply requires a reviewer, a disjoint backup root, and an approved plan digest. It merges kit-owned skills into `.agents/`, combines packaged generic agent templates with a profile specialist overlay under `.codex/agents/`, and emits an inert activation file for manual merge while it leaves `.codex/config.toml` untouched. Per-file ownership hashes preserve unmanaged local agents and enable hash-safe uninstall; uninstall is also report-only until a named reviewer, disjoint backup root, and matching plan digest are supplied. Drift, unsafe links, or incomplete cleanup produce a `PARTIAL` recovery report instead of destructive removal.

New project profiles may optionally declare `studio_experience` defaults for role, mode, and enabled intents. These fields shape presentation and routing UX only; they do not grant mutation authority or waive any risk or approval gate.

Generated content carries a `Generated by scripts/... Do not edit manually.` marker. `scripts/sync_skill_resources.py --check` detects missing or stale installed-helper sources, and generators refuse to replace unmanaged output.

## Evidence lifecycle

`evidence/example/` documents the portable evidence format. Reproducible local runner output belongs under ignored `evidence/local/`; CI stores equivalent files as workflow artifacts. Durable PASS claims should be attached to the target project or release, not baked into the reusable template.

## Template boundary

The distributable tree contains the root plugin manifest, repository marketplace metadata, canonical workflows, generated per-skill helpers, registries, tests, eval fixtures, policy, canonical root scripts, CI, maintained docs, adapter generators, upstream restore metadata, and a small evidence example. Generated `adapters/` output is ignored and rebuilt on demand.

It excludes research clones, runner exports, caches, local execution state, dated dogfood output, reproducible verification residue, and the ignored local `.archive/` history directory.
