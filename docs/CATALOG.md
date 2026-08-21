# Skill Catalog

49 canonical skills across seven additive packs. Every row links to the canonical `SKILL.md`.

- **Use when** is the routing trigger. The agent selects by matching this, so scan this column first.
- **Type** is the library layer: `root`, `router`, `workflow`, `diagnostic`, `gate`, `safety`, `governance`, `interactive`.
- **Risk** is the mutation gate: `read-only` runs automatically; `low` needs a visible diff and a verification command; `medium` needs exact scope, backup or manifest, restore information, and a named reviewer; `high` needs explicit human approval and a dry run.
- **Artifact** is the evidence file the skill must produce.
- `*` marks `experimental` maturity. Every other skill is `beta`.

## Where to start

| Situation | Start here |
|---|---|
| First contact with any kit task | [`using-game-studio-skills`](../skills/using-game-studio-skills/SKILL.md) |
| Adopting an unfamiliar game repository | [`studio-project-intake`](../skills/studio-project-intake/SKILL.md) |
| Something is broken and the cause is unknown | [`evidence-first-debugging`](../skills/evidence-first-debugging/SKILL.md) |
| About to change files | [`safe-project-mutation`](../skills/safe-project-mutation/SKILL.md) |
| Need to claim something works | [`build-and-runtime-verification`](../skills/build-and-runtime-verification/SKILL.md) |
| Pausing or transferring work | [`studio-handoff`](../skills/studio-handoff/SKILL.md) |

## Catalog

### Studio core — routing, safety, evidence, handoff (`studio-core`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`bug-hunt-swarm`](../skills/bug-hunt-swarm/SKILL.md) | An unknown crash, intermittent failure, or cross-subsystem bug needs parallel read-only reproduction lanes, ranked hypotheses, suspect paths, and an... | workflow | read-only | `bug-packets.json` |
| [`build-and-runtime-verification`](../skills/build-and-runtime-verification/SKILL.md) | Running build, compile, test, launch, or runtime checks and producing a verdict tied to exact commands, exit codes, artifact paths, limitations, and... | gate | read-only | `verdict.md` |
| [`evidence-first-debugging`](../skills/evidence-first-debugging/SKILL.md) | Debugging a crash, lỗi, failing game, tool, build, service, script, or reproducible local code failure requires repro or reproduction, giả thuyết or... | workflow | low | `debug-verdict.md` |
| [`feature-to-work-packets`](../skills/feature-to-work-packets/SKILL.md) | Decomposing an approved specification into ordered work packets with a file owner, exact paths, single-writer ownership, dependencies, risks, evidence,... | workflow | low | `work-packets.yaml` |
| [`game-feature-brainstorming`](../skills/game-feature-brainstorming/SKILL.md) | Exploring a game feature, mechanic, player experience, or production approach and the team needs two or three options with trade-offs before choosing a... | interactive | read-only | `design-options.md` |
| [`game-feature-to-spec`](../skills/game-feature-to-spec/SKILL.md) | An approved, chosen, or selected game mechanic direction must become a testable specification with acceptance criteria, state transitions, inputs,... | workflow | low | `feature-spec.md` |
| [`review-swarm`](../skills/review-swarm/SKILL.md) | Reviewing a known change set through parallel read-only code, architecture, test, safety, or product lanes with disjoint concerns and one integrator... | workflow | read-only | `review-verdict.md` |
| [`safe-project-mutation`](../skills/safe-project-mutation/SKILL.md) | Changing project files or generated state requires a report-only dry run, exact scope, backup manifest, apply verification, and a tested restore path. | safety | medium | `mutation-manifest.json` |
| [`skill-authoring-and-audit`](../skills/skill-authoring-and-audit/SKILL.md) | Creating or revising a GameStudio-CodexKIT skill, resolving ambiguous skill triggers, auditing provenance or lifecycle maturity, or deriving reusable... | governance | low | `skill-audit.json` |
| [`studio-agent-orchestration`](../skills/studio-agent-orchestration/SKILL.md) | Selecting project investigator, implementer, independent verifier, or profile specialist roles with expected output, do-not-touch scope, critical-path... | workflow | read-only | `agent-plan.yaml` |
| [`studio-handoff`](../skills/studio-handoff/SKILL.md) | Pausing, transferring, or reactivating game-studio work and a durable handoff must capture branch, goal, scope, files, commands, Verified Snapshot... | workflow | low | `HANDOFF.md` |
| [`studio-project-intake`](../skills/studio-project-intake/SKILL.md) | Collecting a game project goal, scope, risk tier, engine and version, subsystem ownership, constraints, and do-not-touch paths into an actionable... | router | read-only | `task-packet.json` |
| [`studio-project-scaffold`](../skills/studio-project-scaffold/SKILL.md) | Running gamestudio init, status, or uninit, or bootstrapping a new or adopted game repository with AGENTS.md, HANDOFF.md, .agents/CONTRACT.md, project... | workflow | medium | `scaffold-report.json` |
| [`studio-workspace-routing`](../skills/studio-workspace-routing/SKILL.md) | `.agents/project-profile.yaml`, nested Git roots, or cross-repository game work requires a profile-defined repository route, validation slice, or... | router | read-only | `workspace-route.json` |
| [`using-game-studio-skills`](../skills/using-game-studio-skills/SKILL.md) | Starting any GameStudio-CodexKIT task or when a model runner is unavailable and someone requests a confidence-based PASS. | root | read-only | `operating-contract.md` |

### Unity client (`unity`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`localization-authority-audit`](../skills/localization-authority-audit/SKILL.md) | Auditing localization source authority, generated copies, translation keys, missing or extra entries, mismatched text, encoding, mojibake, or client... | diagnostic | read-only | `localization-audit.json` |
| [`unity-asset-guid-meta-audit`](../skills/unity-asset-guid-meta-audit/SKILL.md) | Auditing Unity asset GUID and meta consistency, duplicate GUIDs, missing meta files, stale references, or import and prefab reference failures without... | diagnostic | read-only | `unity-guid-meta-audit.json` |
| [`unity-batchmode-build-verification`](../skills/unity-batchmode-build-verification/SKILL.md) | A Unity batch or batchmode, BuildPipeline, Editor.log, PlayerSettings, or Unity CI job is involved. | gate | low | `unity-build-verdict.json` |
| [`unity-client-offline-debugging`](../skills/unity-client-offline-debugging/SKILL.md) | A Unity client cannot enter offline gameplay because login, bootstrap, disconnected server handling, local mock data, network fallback, or scene... | diagnostic | read-only | `unity-offline-debug-report.md` |
| [`unity-ui-rendering-debugging`](../skills/unity-ui-rendering-debugging/SKILL.md) | A Unity UI, HUD, screen item, or NGUI widget is missing, clipped, behind another canvas, wrongly sorted, disconnected from a prefab or atlas,... | diagnostic | read-only | `unity-ui-debug-report.md` |

### C++ / Lua MMORPG server (`cpp-lua-mmorpg`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`cpp-server-crash-triage`](../skills/cpp-server-crash-triage/SKILL.md) | Triaging a C++ game server crash, dump, access violation, segmentation fault, stack trace, symbols, or build identity into a stable signature and... | diagnostic | read-only | `cpp-crash-triage.json` |
| [`game-database-migration-safety`](../skills/game-database-migration-safety/SKILL.md) | Planning a game MySQL schema or data migration that requires 3306 or 3307 isolation, recognized schema gates, dry-run review, backup, restore, human... | safety | high | `migration-safety-plan.json` |
| [`lua-client-server-contract-audit`](../skills/lua-client-server-contract-audit/SKILL.md) | Normalized Lua client/server RPC contract copies or generated protocol tables disagree on opcode, request-response fields, types, ordering, or source... | diagnostic | read-only | `lua-contract-audit.json` |
| [`mmorpg-packet-protocol-review`](../skills/mmorpg-packet-protocol-review/SKILL.md) | A C++ server and Unity client protocol manifest or wire compatibility review covers packet version negotiation, numeric opcode registry, byte layout... | diagnostic | read-only | `packet-protocol-review.json` |
| [`multi-service-local-environment-doctor`](../skills/multi-service-local-environment-doctor/SKILL.md) | Diagnosing a multi-service local game environment with port conflicts, process listeners, configured ports, service names, startup dependencies, and... | diagnostic | read-only | `environment-report.json` |
| [`network-authority-and-exploit-review`](../skills/network-authority-and-exploit-review/SKILL.md) | Sensitive multiplayer or MMORPG client actions require static server-authority validation, trust-boundary, replay, abuse, or rate-limit analysis with... | diagnostic | read-only | `network-authority-review.json` |
| [`save-data-schema-migration`](../skills/save-data-schema-migration/SKILL.md) | Versioning or converting serialized player save files, profiles, checkpoints, or persistence payloads across recognized save-format versions with... | safety | high | `save-migration-plan.json` |

### Design, release, and liveops (`production-design-liveops`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`balance-data-change-review`](../skills/balance-data-change-review/SKILL.md) | Numeric game tuning data such as damage, price, cooldown, drop rate, or progression has a before/after diff that must stay within approved min/max bounds. | workflow | read-only | `balance-change-review.json` |
| [`economy-source-sink-model`](../skills/economy-source-sink-model/SKILL.md) | Modeling a game economy's currencies, item faucets, sinks, exchange rates, player segments, inflation risk, progression affordability, or... | workflow | read-only | `economy-source-sink-model.json` |
| [`game-performance-budget`](../skills/game-performance-budget/SKILL.md) | Defining or reviewing game frame-time, memory, loading, network, CPU, GPU, allocation, or thermal budgets against captured measurements and target... | gate | read-only | `performance-budget-report.json` |
| [`liveops-incident-response`](../skills/liveops-incident-response/SKILL.md) | A live production service outage needs incident-controlled service or database mitigation, an incident commander, containment, timeline, player... | workflow | high | `liveops-incident-record.json` |
| [`playtest-evidence`](../skills/playtest-evidence/SKILL.md) | Planning or reviewing game playtests that need structured scenarios, participant context, observations, reproduction evidence, severity, and honest... | workflow | read-only | `playtest-evidence.json` |
| [`release-candidate-preflight`](../skills/release-candidate-preflight/SKILL.md) | A release candidate or RC needs a go/no-go readiness decision across required artifacts, test summaries, known issues, approvals, compatibility,... | gate | read-only | `release-preflight.json` |
| [`store-submission-checklist`](../skills/store-submission-checklist/SKILL.md) | Preparing a game for Steam, console, mobile, or other storefront submission with platform metadata, compliance, ratings, privacy, package, entitlement,... | gate | high | `store-submission-checklist.json` |
| [`telemetry-event-contract-review`](../skills/telemetry-event-contract-review/SKILL.md) | Reviewing game analytics or telemetry event names, IDs, required properties, types, versions, privacy classes, producers, consumers, and backward... | diagnostic | read-only | `telemetry-contract-review.json` |

### Content production (`content-production`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`animation-rigging-import-audit`](../skills/animation-rigging-import-audit/SKILL.md) | Character animation needs an audit across skeleton, rig, skin weights, avatar, retargeting, clips, events, root motion, compression, import settings,... | diagnostic | read-only | `animation-rigging-audit.json` |
| [`art-asset-pipeline-preflight`](../skills/art-asset-pipeline-preflight/SKILL.md) | Source art or game assets need preflight across naming, ownership, DCC export, scale, pivots, materials, textures, LOD, collision, compression, import... | gate | read-only | `art-asset-preflight.json` |
| [`audio-content-pipeline-review`](../skills/audio-content-pipeline-review/SKILL.md) | Music, voice, SFX, ambience, or middleware content needs review across source ownership, loudness, codec, streaming, looping, localization, routing,... | diagnostic | read-only | `audio-pipeline-review.json` |
| [`game-screenshot-showcase-and-store-packaging`](../skills/game-screenshot-showcase-and-store-packaging/SKILL.md) * | A Unity team needs approved PlayMode screenshots, immutable capture evidence, reviewed showcase slides, or report-only store screenshot packaging... | workflow | medium | `screenshot-showcase-report.json` |
| [`level-and-content-design-review`](../skills/level-and-content-design-review/SKILL.md) | A level, encounter, mission space, or content slice needs review for player flow, pacing, readability, content density, progression gates, challenge,... | workflow | read-only | `level-content-review.json` |
| [`narrative-quest-content-contract`](../skills/narrative-quest-content-contract/SKILL.md) | Narrative, quest, dialogue, objective, state, reward, localization, cinematic, and implementation teams need one explicit content contract | workflow | low | `narrative-quest-contract.json` |
| [`unity-ui-art-and-motion-production`](../skills/unity-ui-art-and-motion-production/SKILL.md) * | New or revised Unity UI visuals, icons, panels, 9-slice sprites, component states, HUD or menu layouts, popup motion, screen transitions, or flattened UI screenshot decomposition must be produced through Figma and integrated into uGUI, NGUI, or UI Toolkit; not for UI debugging, localization-only work, character animation, or general art-pipeline audits. | workflow | medium | `ui-art-motion-production.json` |

### Production management (`production-management`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`load-soak-capacity-verification`](../skills/load-soak-capacity-verification/SKILL.md) | Servers or online game services need controlled load, soak, concurrency, capacity, saturation, leak, queue, failover, recovery, and scaling... | gate | medium | `load-soak-report.json` |
| [`platform-device-compatibility-matrix`](../skills/platform-device-compatibility-matrix/SKILL.md) | A game needs a platform and device compatibility matrix across OS, hardware, GPU, memory, resolution, input, network, storefront, certification, test... | gate | read-only | `compatibility-matrix.json` |
| [`production-risk-and-dependency-review`](../skills/production-risk-and-dependency-review/SKILL.md) | A production plan needs a read-only dependency risk review covering critical path, ownership gaps, blocked handoffs, mitigation, escalation, and... | gate | read-only | `production-risk-review.json` |
| [`qa-test-strategy-and-coverage`](../skills/qa-test-strategy-and-coverage/SKILL.md) | A game project, milestone, or feature needs a QA test strategy and coverage matrix across risk, test levels, platforms, environments, ownership,... | workflow | read-only | `qa-strategy.json` |
| [`studio-production-planning`](../skills/studio-production-planning/SKILL.md) | A game milestone needs production planning across schedule, staffing, workstreams, dependencies, delivery forecast, scope, and milestone acceptance | workflow | low | `production-plan.json` |

### Product analytics (`product-analytics`)

| Skill | Use when | Type | Risk | Artifact |
|---|---|---|---|---|
| [`liveops-content-rollout-and-rollback`](../skills/liveops-content-rollout-and-rollback/SKILL.md) | A live game content update needs a governed rollout and rollback plan across cohort, canary, configuration, dependencies, monitoring, approvals,... | gate | high | `liveops-rollout-plan.json` |
| [`product-analytics-experiment-review`](../skills/product-analytics-experiment-review/SKILL.md) | A game product experiment or A/B test needs review across hypothesis, population, assignment, metrics, guardrails, instrumentation, segmentation,... | workflow | read-only | `experiment-review.json` |

## Deeper reference material

Some skills ship progressively loaded references with concrete, platform-specific commands. Load these when the skill body's procedure is not enough:

| Skill | Reference |
|---|---|
| `build-and-runtime-verification` | [exit-code capture, freshness proof, verdict mapping](../skills/build-and-runtime-verification/references/commands.md) |
| `cpp-server-crash-triage` | [symbolization on Windows and Linux](../skills/cpp-server-crash-triage/references/commands.md) |
| `game-database-migration-safety` | [credential-safe inspection, backup, restore](../skills/game-database-migration-safety/references/commands.md) |
| `game-screenshot-showcase-and-store-packaging` | [capture and packaging commands](../skills/game-screenshot-showcase-and-store-packaging/references/commands.md) |
| `liveops-incident-response` | [read-only incident observation and blocked-action table](../skills/liveops-incident-response/references/commands.md) |
| `multi-service-local-environment-doctor` | [port, process, and configuration snapshots](../skills/multi-service-local-environment-doctor/references/commands.md) |
| `unity-batchmode-build-verification` | [batchmode invocation and log parsing](../skills/unity-batchmode-build-verification/references/commands.md) |
| `unity-client-offline-debugging` | [offline flag precedence, bootstrap order, player logs](../skills/unity-client-offline-debugging/references/commands.md) |
| `unity-ui-art-and-motion-production` | [Figma provenance, design brief, flattened UI decomposition, background restoration, uGUI, NGUI, UI Toolkit, and visual iteration](../skills/unity-ui-art-and-motion-production/references/) |
| `unity-ui-rendering-debugging` | [stack detection, serialized inspection, diagnostic order](../skills/unity-ui-rendering-debugging/references/commands.md) |

## Packs

Install a scoped subset instead of the whole catalog. Packs are additive and resolve their dependencies transitively.

| Pack | Focus |
|---|---|
| `studio-core` | Always required. Routing, safety, verification, evidence, handoff. |
| `unity` | Unity client diagnosis, builds, assets, localization. |
| `cpp-lua-mmorpg` | Authoritative server, protocol, database, save data, local environment. |
| `production-design-liveops` | Balance, economy, performance, release, incidents, telemetry. |
| `content-production` | Art, audio, animation, level, narrative, UI production. |
| `production-management` | QA strategy, capacity, compatibility, planning, risk. |
| `product-analytics` | Experiments and governed content rollout. |

## Related documents

- [Architecture](architecture/overview.md) — layers, authority flow, evaluation model.
- [Skill authoring](authoring/skills.md) — required sequence for creating or changing a skill.
- [Adoption evidence](adoption.md) — what has actually been dogfooded, and what remains `BLOCKED`.
- [Case study](case-studies/unity-mmorpg-global-localization.md) — a real routed localization run with artifacts.
