# MOStudio Kit Skill and Agent User Guide

> Wiki-ready English guide for Codex App/CLI and Hermes Agent users. This page
> covers all **49 canonical skills**, **24 canonical agent roles**, and the
> operating rules that keep game-project work evidence-based and reversible.

MOStudio Kit is designed for operating real game projects: Unity clients,
C++/Lua MMORPG servers, services, player data, content pipelines, releases, and
live operations. A **skill** is a reusable workflow with an evidence contract.
An **agent role** receives a bounded assignment and uses one or more skills to
complete it. Selecting a specialist never grants additional mutation authority.

## Contents

1. [Quick start](#quick-start)
2. [Golden Paths and role-first routing](#golden-paths-and-role-first-routing)
3. [Prompt templates](#prompt-templates)
4. [Evidence and risk model](#evidence-and-risk-model)
5. [All 49 skills](#all-49-skills)
6. [All 24 agent roles](#all-24-agent-roles)
7. [Multi-agent orchestration](#multi-agent-orchestration)
8. [End-to-end examples](#end-to-end-examples)
9. [Installation and project activation](#installation-and-project-activation)
10. [Result acceptance checklist](#result-acceptance-checklist)
11. [Publishing to GitHub Wiki](#publishing-to-github-wiki)
12. [Canonical sources](#canonical-sources)

## Quick start

You do not need to memorize every skill. Describe the outcome, repository,
allowed scope, do-not-touch scope, and required evidence.

Minimal request:

```text
Audit this Unity project, identify its subsystems, and route the task to the
right MOStudio Kit skill. Stay read-only. Report Verified, Snapshot,
Unverified, and BLOCKED facts separately.
```

More useful request:

```text
Repository: D:/Games/MyMMO
Goal: determine why the client cannot enter offline gameplay.
Readable scope: Assets/, ProjectSettings/, Logs/.
Do not touch: .env, databases, generated localization, production services.
Requirements: reproduce the failure, rank hypotheses, prove the root cause
before editing, run focused tests, and return commands, exit codes, artifacts,
and limitations.
```

The root router normally starts with `using-game-studio-skills` and selects the
narrowest matching workflow. You can also name a skill explicitly:

```text
Use unity-ui-rendering-debugging to diagnose the missing HUD. Stay read-only
until the root cause is supported by evidence.
```

In Codex, use `@game-studio-codex-kit` when you want an explicit plugin route.
If your client exposes a skill picker, you may select the skill directly.
Otherwise, naming the skill in plain text is sufficient.

## Golden Paths and role-first routing

The public router organizes common Unity and MMORPG work into eight Golden
Path families. Each family routes to canonical workflows; it does not create a
second workflow authority.

| Golden Path | Typical canonical workflows |
|---|---|
| Project adoption and routing | `studio-project-intake`, `studio-workspace-routing`, `studio-project-scaffold` |
| Local environment recovery | `multi-service-local-environment-doctor` |
| Unity client entry recovery | `unity-client-offline-debugging` |
| C++ server failure recovery | `cpp-server-crash-triage`, `mmorpg-packet-protocol-review` |
| Unity UI and localization | `unity-ui-rendering-debugging`, `localization-authority-audit` |
| Unity build and asset integrity | `unity-batchmode-build-verification`, `unity-asset-guid-meta-audit` |
| Lua contract and server authority | `lua-client-server-contract-audit`, `network-authority-and-exploit-review` |
| Data and live release safety | `game-database-migration-safety`, `save-data-schema-migration`, `release-candidate-preflight`, `liveops-incident-response` |

State the studio role and required outcome when you want role-first routing.
The router maps requests to the public intents **Diagnose**, **Verify**, **Plan
Change**, **Ship**, and **Handle Incident**.

| Role and outcome | Example request |
|---|---|
| Developer · Diagnose | "As a Developer, diagnose why this Unity client cannot enter offline mode." |
| QA · Verify | "As QA, verify this local multi-service environment, including server, service, and database context." |
| Producer · Plan Change | "As a Producer, plan repository adoption and show the proposed route without writing files." |
| LiveOps · Handle Incident | "As LiveOps, handle this C++ server crash incident and preserve the build-bound diagnostic evidence." |

The report-only router may return `READY`, `AMBIGUOUS`, or `BLOCKED`. These are
planning states, never runtime `PASS` verdicts. `READY` grants no execution or
mutation authority. Basic mode asks one focused question when the best route is
ambiguous; Advanced mode may select a reported candidate with `--workflow`.
Neither mode weakens evidence, review, backup, approval, or restore gates.

## Prompt templates

### General task template

```text
Goal:
Repository/project:
Snapshot, branch, or build:
Readable scope:
Writable scope:
Do-not-touch scope:
Preferred skill, if known:
Preferred agent role, if needed:
Reviewer:
Expected verification commands:
Required artifacts:
Stop/BLOCKED conditions:
```

### Debugging template

```text
Use evidence-first-debugging for <failure>. Reproduce first, rank hypotheses,
isolate the root cause, add a regression test, and then implement the smallest
fix. Do not modify <do-not-touch>. Finish with build-and-runtime-verification,
including commands, exit codes, artifact paths, and limitations.
```

### Review template

```text
Use review-swarm to review <commit/branch/working tree> through independent
correctness, security/mutation, and test/release lanes. Every lane is read-only.
Each finding must include severity, file:line, evidence, and counterevidence.
The main thread owns deduplication and the final verdict.
```

### Safe-change template

```text
Create a report-only plan for <change>. List exact paths, before/after hashes,
collisions, backup data, and restore actions. Do not apply until a named reviewer
approves the exact plan digest. If source or target state changes, stop and
produce a new report.
```

## Evidence and risk model

### Evidence labels

| Label | Meaning | Example |
|---|---|---|
| `Verified` | Directly observed command, test, build, primary source, or artifact | `dotnet test`, exit `0`, retained log |
| `Snapshot` | True for a named commit, build, configuration, or environment | Unity `6000.0.45f1` at commit `abc123` |
| `Unverified` | Hypothesis or forecast without sufficient evidence | “The prefab may have lost a reference.” |
| `BLOCKED` | A required runner, project, permission, dependency, or artifact is unavailable | Unity Editor is unavailable for PlayMode verification |

`BLOCKED` is an honest outcome. It must never be converted to `PASS` because
the code looks correct or compilation succeeded.

### Mutation risk

| Risk | Minimum gate |
|---|---|
| `read-only` | Non-mutating inspection may run automatically |
| `low` | Visible diff and verification command |
| `medium` | Exact scope, named reviewer, backup or manifest, restore path, reviewed plan |
| `high` | Explicit human approval, dry run/report, backup/rollback, stop conditions |

A specialist role does not reduce risk. `game-data-engineer` cannot run
destructive SQL without approval. `build-release-engineer` cannot publish or
sign a release. Read-only agents cannot edit production source.

## All 49 skills

### Studio Core

| Skill | Use it when | Example request |
|---|---|---|
| `using-game-studio-skills` | Starting any task and selecting route, risk, and evidence expectations | “Audit this repository and select the correct workflow. Do not edit yet.” |
| `studio-project-intake` | Adopting an unfamiliar repository and collecting goals, engine, owners, and constraints | “Create an intake task packet for this Unity client and C++ server.” |
| `studio-workspace-routing` | A workspace contains nested Git roots or several related repositories | “Route client, server, and workbench repos through the project profile.” |
| `studio-agent-orchestration` | Two or more independent workstreams justify bounded agents | “Create an agent plan with disjoint writers and an independent verifier.” |
| `safe-project-mutation` | File or generated-state changes require report, digest, backup, and restore | “Dry-run these three config changes. Do not apply before review.” |
| `build-and-runtime-verification` | A build, test, launch, or runtime claim needs fresh proof | “Run the build and return command, exit code, log, artifact, and limitation.” |
| `evidence-first-debugging` | A failure exists but the root cause is not yet known | “Reproduce the login failure, rank hypotheses, fix minimally, add regression.” |
| `studio-handoff` | Work is paused, transferred, or moved to another session | “Update HANDOFF with branch, files, commands, failures, and next action.” |
| `review-swarm` | A known change set needs independent review perspectives | “Review this diff for correctness, architecture, safety, and tests.” |
| `bug-hunt-swarm` | An intermittent or cross-subsystem bug needs parallel investigation | “Investigate client, server, and protocol lanes without editing.” |
| `game-feature-brainstorming` | A feature direction is not chosen and needs 2–3 options with trade-offs | “Propose three party-finder designs for an MMORPG.” |
| `game-feature-to-spec` | A chosen feature direction must become a testable specification | “Turn party-finder option B into states, inputs, edge cases, and acceptance.” |
| `feature-to-work-packets` | An approved specification must be split by owner, path, and dependency | “Create disjoint client, server, telemetry, and QA work packets.” |
| `skill-authoring-and-audit` | Creating/updating a skill or auditing routing, provenance, and maturity | “Audit overlap and update an existing skill before proposing a new one.” |
| `studio-project-scaffold` | Bootstrapping governance, project profile, local skills, and agents | “Run report-only project scaffold and list every collision and proposed file.” |

Typical feature flow:

```text
game-feature-brainstorming
  → game-feature-to-spec
  → feature-to-work-packets
  → studio-agent-orchestration
  → safe-project-mutation
  → build-and-runtime-verification
  → studio-handoff
```

### Unity Client

| Skill | Use it when | Example request |
|---|---|---|
| `unity-client-offline-debugging` | Login, bootstrap, mock data, fallback, or scene startup blocks offline play | “Trace the offline flag from bootstrap to scene startup.” |
| `unity-ui-rendering-debugging` | A HUD/widget is missing, clipped, mis-sorted, misanchored, or disconnected | “Diagnose an NGUI widget that exists but does not render.” |
| `localization-authority-audit` | Localization sources/copies drift, keys are missing, or encoding is corrupted | “Find the authority for `UI_LOGIN` and compare all generated copies.” |
| `unity-asset-guid-meta-audit` | `.meta` files, GUIDs, prefab references, or imports are inconsistent | “Audit GUID/meta integrity under Assets/UI without reimporting.” |
| `unity-batchmode-build-verification` | Unity batchmode, BuildPipeline, Editor.log, or Unity CI is involved | “Run the Windows batch build and extract real failures from Editor.log.” |

Typical missing-HUD flow:

```text
unity-ui-rendering-debugging
  → localization-authority-audit, when text authority is involved
  → unity-asset-guid-meta-audit, when prefab/atlas references are involved
  → unity-batchmode-build-verification
  → build-and-runtime-verification
```

### C++, Lua, and MMORPG Services

| Skill | Use it when | Example request |
|---|---|---|
| `multi-service-local-environment-doctor` | Local ports, listeners, startup dependencies, or isolation are broken | “Map configured ports to listeners without stopping any process.” |
| `game-database-migration-safety` | A MySQL migration needs isolation, dry run, backup, and restore | “Plan this migration on sandbox port 3307 without exposing credentials.” |
| `lua-client-server-contract-audit` | Lua RPC/opcode/field/type/order differs between client and server | “Compare the client table to canonical protocol authority.” |
| `cpp-server-crash-triage` | A dump, access violation, segfault, stack, or symbol identity needs triage | “Normalize this dump into a stable crash signature and ranked causes.” |
| `mmorpg-packet-protocol-review` | Opcode, byte layout, direction, pairing, or version negotiation needs review | “Compare `LOGIN_REQ/RES` between C++ and Unity.” |
| `network-authority-and-exploit-review` | Server authority, replay, abuse, or rate limiting needs static review | “Review reward claiming and identify client-trusted decisions.” |
| `save-data-schema-migration` | Save/profile/checkpoint payloads change versions | “Plan v3-to-v4 conversion with fixtures, compatibility, and rollback.” |

Typical packet flow:

```text
lua-client-server-contract-audit
  → mmorpg-packet-protocol-review
  → network-authority-and-exploit-review
  → focused client/server tests
  → build-and-runtime-verification
```

### Design, Release, and Live Operations

| Skill | Use it when | Example request |
|---|---|---|
| `playtest-evidence` | A playtest needs scenarios, participant context, observations, and reproduction proof | “Design an onboarding playtest for eight new players.” |
| `game-performance-budget` | Frame time, memory, loading, network, allocation, or thermal limits need a budget | “Define mobile tier-B budgets and compare captured measurements.” |
| `economy-source-sink-model` | Currency faucets, sinks, exchange, affordability, or inflation need modeling | “Model the gold economy for three player segments over 90 days.” |
| `balance-data-change-review` | Damage, price, cooldown, drop rate, or progression diffs need bounds checking | “Verify this tuning patch stays inside approved min/max limits.” |
| `release-candidate-preflight` | A release candidate needs a go/no-go recommendation | “Preflight RC 1.8.0 against build hash, tests, issues, and rollback.” |
| `store-submission-checklist` | Steam, console, or mobile submission readiness needs review | “Prepare Steam metadata, privacy, package, and entitlement checks. Do not upload.” |
| `liveops-incident-response` | A production outage needs incident command, containment, timeline, and recovery | “Open an incident for login outage. Observe first; wait for IC approval.” |
| `telemetry-event-contract-review` | Event names, IDs, properties, versions, privacy, and compatibility need review | “Review `purchase_completed` v2 and its backward compatibility.” |

Typical release flow:

```text
build-and-runtime-verification
  → platform-device-compatibility-matrix
  → release-candidate-preflight
  → store-submission-checklist
  → human-controlled publication outside the skill
```

### Content Production

| Skill | Use it when | Example request |
|---|---|---|
| `level-and-content-design-review` | Level flow, pacing, readability, content density, or progression needs review | “Review this 20-minute dungeon and its encounter pacing.” |
| `narrative-quest-content-contract` | Quest, dialogue, objective, reward, localization, and cinematic teams need one contract | “Convert this rescue quest into an implementation-ready content contract.” |
| `art-asset-pipeline-preflight` | Source art, DCC export, scale, pivot, LOD, collision, or import needs preflight | “Audit this environment-art batch before Unity import.” |
| `animation-rigging-import-audit` | Skeleton, skinning, retargeting, clips, root motion, or compression needs review | “Audit the boss humanoid rig and root-motion clips.” |
| `unity-ui-art-and-motion-production` | Producing Figma/Unity UI art and motion or decomposing a flattened UI screenshot | “Split this HUD into raster, native UI, and background candidates.” |
| `game-screenshot-showcase-and-store-packaging` | Approved PlayMode capture, immutable evidence, showcase decks, or store packaging is needed | “Plan six Steam screenshots. Do not upload or submit.” |
| `audio-content-pipeline-review` | Music, VO, SFX, loudness, codec, streaming, loops, or middleware need review | “Audit boss-music looping, loudness, streaming, and memory.” |

`unity-ui-art-and-motion-production` and
`game-screenshot-showcase-and-store-packaging` are currently `experimental`.
They require real Figma, Unity, capture, and reviewer evidence before a runtime
`PASS` can be claimed.

### Production Management

| Skill | Use it when | Example request |
|---|---|---|
| `studio-production-planning` | A milestone needs schedule, staffing, workstreams, dependencies, and forecast | “Plan a 12-week vertical slice with milestone acceptance.” |
| `production-risk-and-dependency-review` | A production plan needs critical-path and ownership-gap review | “Review alpha schedule exposure without changing the baseline plan.” |
| `qa-test-strategy-and-coverage` | A project/feature needs a risk-based test and regression strategy | “Create a cross-platform login coverage matrix.” |
| `platform-device-compatibility-matrix` | OS, GPU, memory, input, network, storefront, and support tiers need definition | “Define Windows and Android support tiers.” |
| `load-soak-capacity-verification` | Load, soak, saturation, leaks, failover, recovery, or scaling need verification | “Plan an eight-hour 5,000-CCU soak test with stop conditions.” |

### Product Analytics

| Skill | Use it when | Example request |
|---|---|---|
| `product-analytics-experiment-review` | An A/B test needs hypothesis, assignment, metrics, guardrails, sample size, and ethics review | “Review the starter-pack discount experiment.” |
| `liveops-content-rollout-and-rollback` | Live content needs canary cohorts, monitoring, triggers, and rollback | “Plan a 5% → 25% → 100% Halloween rollout. Do not publish.” |

## All 24 agent roles

### Foundation roles

| Agent | Responsibility | Use it when | Example assignment |
|---|---|---|---|
| `investigator` | Read-only ownership, dependency, and call-path discovery | Authority must be known before edits begin | “Trace localization-key authority and return file:line evidence. Do not edit.” |
| `implementer` | Bounded writer for one explicit scope | Root cause/specification is stable and one package remains | “Own only `server/auth/**`; do not touch the protocol registry.” |
| `verifier` | Independent validation without production-source mutation | After implementation or before release/handoff | “Run focused and regression tests; verify artifacts and hashes.” |

### Specialist roles

| Agent | Domain | Common skills | Example assignment |
|---|---|---|---|
| `unity-csharp-client` | Unity C#, scenes, prefabs, UI, performance | UI rendering, GUID/meta, batch build, runtime verification | “Fix offline bootstrap under `client/Assets/**`; provide PlayMode evidence.” |
| `csharp-backend` | .NET services, APIs, jobs, tooling | Debugging, build verification, environment doctor | “Investigate auth API timeout; own only `services/Auth/**`.” |
| `cpp-game-server` | Authoritative C++ server, crashes, protocol, memory | Crash triage, packet review, build verification | “Fix crash signature X in `server/Game/**`; do not change opcodes.” |
| `golang-services` | Go services, gateways, concurrency, observability | Debugging, build verification, environment doctor | “Review the goroutine leak and run `go test ./...`.” |
| `lua-gameplay` | Lua gameplay and client/server contracts | Lua contract, packet review, debugging | “Update the Lua consumer from canonical protocol; do not edit generated tables.” |
| `game-data-engineer` | Schemas, migrations, config pipelines, telemetry | DB migration, save migration, telemetry contracts | “Prepare a migration dry run without importing data or exposing credentials.” |
| `technical-artist` | Shaders, VFX, materials, rendering, import pipelines | GUID/meta, performance budgets, runtime verification | “Audit shader variants and render budget; preserve source art.” |
| `ui-motion-artist` | Figma UI, screenshot decomposition, Unity UI, micro-motion | UI art/motion, asset preflight, GUID/meta | “Decompose the HUD and produce a report-only import and reduced-motion plan.” |
| `game-showcase-capture-producer` | PlayMode capture, evidence, showcase/store packages | Screenshot packaging, playtest, store readiness | “Capture approved checkpoints. Do not upload, sign, or submit.” |
| `ui-localization-specialist` | UI prefabs, localization, fonts, overflow, accessibility | Localization audit, UI rendering, playtest | “Audit German overflow and key authority; preserve generated overlays.” |
| `systems-game-designer` | Economy, progression, balance, content systems | Feature spec, economy model, balance review | “Model the progression curve and review tuning deltas.” |
| `qa-automation` | Unit, integration, PlayMode, browser, regression evidence | Playtest evidence, verification, review swarm | “Own `tests/**`; do not edit production source to force green tests.” |
| `build-release-engineer` | Builds, CI, packaging, rollback, release gates | RC preflight, Unity batch build, store checklist | “Fix CI caching and verify the package. Do not publish or sign.” |
| `liveops-sre` | Runtime health, incidents, monitoring, recovery, capacity | Incident response, environment doctor, authority review | “Observe the login outage and build a timeline. Do not restart production.” |
| `game-security-engineer` | Trust boundaries, exploit paths, secrets, authority | Authority review, debugging, review swarm | “Review reward replay protection without sending attack traffic.” |
| `producer` | Milestones, scope, staffing, dependencies, risk | Production planning, risk review, handoff | “Create a beta milestone and owner map; do not self-approve the gate.” |
| `level-content-designer` | Level layout, encounter pacing, mission flow | Level review, feature spec, playtest | “Review dungeon flow and propose acceptance/playtest cases.” |
| `narrative-designer` | Narrative, quests, dialogue, cinematics, localization contracts | Quest contract, localization, telemetry | “Write the quest contract and telemetry requirements; do not edit gameplay.” |
| `asset-pipeline-specialist` | DCC export, engine import, LOD, collision, compression | Asset preflight, rig audit, GUID/meta | “Preflight the character batch and report blockers before import.” |
| `audio-engineer` | Music, VO, SFX, middleware, loudness, streaming, memory | Audio review, performance budget, localization | “Audit localized VO loudness and memory/concurrency limits.” |
| `product-analyst` | Metrics, experiments, segmentation, live-content decisions | Experiment review, telemetry, governed rollout | “Review assignment and guardrails. Do not enable the experiment.” |

## Multi-agent orchestration

Use multiple agents only when workstreams are genuinely independent. The main
thread retains the immediate critical path and integration ownership. Use no
more than three concurrent sidecars.

Example `agent-plan.yaml`:

```yaml
critical_path: confirm canonical packet schema
integration_owner: main-thread
concurrency: 3
lanes:
  - role: investigator
    read_scope: [client/protocol/**, server/protocol/**]
    write_scope: []
    expected_output: authority-map.md
  - role: cpp-game-server
    write_scope: [server/network/**]
    do_not_touch: [client/**, registry/opcodes.yaml]
    validation: [focused C++ tests]
  - role: unity-csharp-client
    write_scope: [client/Assets/Scripts/Network/**]
    do_not_touch: [server/**, generated/**]
    validation: [Unity EditMode tests]
verifier:
  role: verifier
  starts_after: [cpp-game-server, unity-csharp-client]
  source_write: false
```

Do not parallelize when:

- two agents would edit the same file, scene, prefab, or registry;
- the shared interface is still unstable;
- one writer must repeatedly wait for another writer;
- the task is a small one-file fix;
- a verifier would need to edit source when tests fail.

## End-to-end examples

### Adopt a Unity/MMORPG repository

```text
using-game-studio-skills
  → studio-project-intake
  → studio-workspace-routing
  → studio-project-scaffold report-only
  → human review of digest, collisions, and backup
  → approved scaffold apply
  → studio-agent-orchestration, if multiple repos are involved
  → studio-handoff
```

```text
Adopt D:/Games/MyMMO into MOStudio Kit. Begin with intake and a report-only
scaffold. Preserve AGENTS.md, .env, credentials, and all local skills. Do not
apply until I approve the plan digest and backup path.
```

### Unity offline failure

```text
unity-client-offline-debugging
  → evidence-first-debugging
  → unity-csharp-client or lua-gameplay implementer
  → unity-batchmode-build-verification
  → verifier
```

```text
Trace offline flags, login bypass, mock data, and scene bootstrap. Prove the root
cause before editing. If Unity Editor is unavailable, static findings may be
Verified but the PlayMode verdict must remain BLOCKED.
```

### C++ server crash

```text
cpp-server-crash-triage
  → investigator confirms build and symbol identity
  → cpp-game-server implementer
  → verifier runs focused tests and compilation
```

```text
Turn this dump into a stable crash signature. Do not trust stack frames when
symbols do not match. After root-cause confirmation, implement the smallest fix
under server/Game and add a regression test.
```

### MySQL migration

```text
game-database-migration-safety
  → game-data-engineer
  → dry run on isolated port 3307
  → backup and restore verification
  → explicit human approval
```

```text
Plan an index migration for player_items. Use only the 3307 sandbox, never print
credentials, and do not touch production. Return lock estimates, dry-run output,
backup, restore, stop conditions, and the decision requiring DBA approval.
```

### UI from a flattened screenshot

```text
unity-ui-art-and-motion-production
  → ui-motion-artist
  → human bbox and classification review
  → Figma authority and export hashes
  → art-asset-pipeline-preflight
  → safe-project-mutation
  → Unity runtime evidence
```

```text
Decompose combat-hud.png in original pixel coordinates into raster assets,
native UI, and background candidates. Preserve the original, raw-full, and
local-composite restoration variants. Do not import into Unity until the Art
Lead approves bboxes, Figma revision, and the plan digest.
```

### Live incident

```text
liveops-incident-response
  → liveops-sre read-only observation
  → incident commander approves containment
  → authorized operator performs mitigation
  → recovery verification
  → postmortem handoff
```

```text
Login success rate has fallen to 42%. Open an incident record, establish the
timeline and blast radius, and propose containment options. Do not restart
services or change databases/configuration before IC approval.
```

### Release candidate

```text
build-and-runtime-verification
  → qa-automation
  → platform-device-compatibility-matrix
  → build-release-engineer
  → release-candidate-preflight
  → store-submission-checklist
```

```text
Preflight RC 1.8.0 at commit abc123. Bind every test, log, and package to the
exact build hash. List blockers, waivers, monitoring, rollback, and the go/no-go
recommendation. Do not publish.
```

### A/B test and live-content rollout

```text
telemetry-event-contract-review
  → product-analytics-experiment-review
  → product-analyst
  → liveops-content-rollout-and-rollback
  → human approval
```

```text
Review the starter-pack experiment: hypothesis, assignment, primary metric,
guardrails, sample size, and novelty. If gates pass, plan a 5/25/100% rollout
with rollback triggers. Do not enable the experiment.
```

## Installation and project activation

### Codex App/CLI

```bash
codex plugin marketplace add hoatv2211/GameStudio-CodexKIT
codex
```

Open `/plugins`, select the **MOStudio Kit** marketplace, install the plugin,
and start a new session. In Codex App, open Plugins from Codex and follow the
same flow.

Upgrade the marketplace snapshot before reviewing and reinstalling an updated
plugin, or remove it after uninstalling MOStudio Kit from `/plugins`:

```bash
codex plugin marketplace upgrade gamestudio-codex-kit
codex plugin marketplace remove gamestudio-codex-kit
```

The repository root is the plugin package. `.codex-plugin/plugin.json` exposes
the canonical skills directly, while `.claude-plugin/marketplace.json` provides
the GitHub marketplace compatibility path.

### Hermes Agent

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -g -y
```

List available skills before installation:

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -l
```

### Scaffold skills and agents into a game project

These commands require a full repository clone. Generate the report first:

```powershell
$report = python -B scripts/generate_adapters.py . --target per-project --output D:/Games/MyMMO | ConvertFrom-Json
$report | ConvertTo-Json -Depth 10
```

After reviewing the exact plan:

```powershell
python -B scripts/generate_adapters.py . --target per-project --output D:/Games/MyMMO --apply --reviewer "Tech Lead" --backup-root D:/Games/MyMMO/.adapter-backup --plan-digest $report.plan_digest
```

The adapter places project-local skills under `.agents/skills/`, role templates
under `.codex/agents/`, and emits `.codex/agents.generated.toml`. The generated
snippet is **inert**. Review it and manually merge only the desired activation
into `.codex/config.toml`. The adapter must not edit active configuration.

## Result acceptance checklist

- Does the selected skill match the actual trigger rather than a broad keyword?
- Are repository, branch/build, and do-not-touch scope recorded?
- Does every mutation have exact scope, reviewer, backup, and restore data?
- Does each writer own a disjoint file set?
- Does every `PASS` include command, exit code, and artifact path?
- Is compilation being mistaken for regression or runtime proof?
- Are missing Unity/Figma/database/service runners reported as `BLOCKED`?
- Were generated files changed through their canonical source and regenerated?
- Were secrets kept out of commands, logs, fixtures, and prompts?
- Does the handoff record failures, limitations, next owner, and next action?

Avoid requests such as:

```text
Fix everything, decide everything yourself, and deploy if the tests look okay.
```

Prefer:

```text
Diagnose first, bound the scope, and report the plan and risk. Apply only the
authorized low-risk change. Stop for approval before any database, service,
credential, destructive, or publish action. Verify with exact commands and
return BLOCKED when a required runner is unavailable.
```

Do not ask a verifier to “fix it if tests fail”; return the finding to the
writer. Do not assign the same prefab, scene, registry, or file to two agents.
Do not use `review-swarm` instead of debugging when no stable change set exists.

## Publishing to GitHub Wiki

GitHub Wiki is a separate Git repository. Pushing this file to the main
`GameStudio-CodexKIT` repository makes the source available under `docs/`, but
does **not** publish or update a Wiki page.

After the main-repository change has been reviewed, clone the Wiki repository
from a common parent directory and copy this guide into the recommended page
name:

```powershell
git clone https://github.com/hoatv2211/GameStudio-CodexKIT.wiki.git
Copy-Item .\GameStudio-CodexKIT\docs\wiki-skill-agent-user-guide.md .\GameStudio-CodexKIT.wiki\Skill-and-Agent-User-Guide.md
```

Review the Wiki-repository diff before committing or pushing it. Wiki
publication is a separate human-authorized action; this repository does not
auto-publish the page through GitHub Actions.

## Canonical sources

This Wiki page is a user guide, not an authority override. When it differs from
the repository, canonical files win:

- [Skill Catalog](https://github.com/hoatv2211/GameStudio-CodexKIT/blob/main/docs/CATALOG.md)
- [Agent Role Registry](https://github.com/hoatv2211/GameStudio-CodexKIT/blob/main/registry/agent-roles.yaml)
- [Architecture](https://github.com/hoatv2211/GameStudio-CodexKIT/blob/main/docs/architecture/overview.md)
- [Adoption Evidence](https://github.com/hoatv2211/GameStudio-CodexKIT/blob/main/docs/adoption.md)
- [Repository Operating Contract](https://github.com/hoatv2211/GameStudio-CodexKIT/blob/main/AGENTS.md)
- [Canonical Skills](https://github.com/hoatv2211/GameStudio-CodexKIT/tree/main/skills)

This guide grants no additional permission for mutation, publishing, database
access, credential handling, or service control.
