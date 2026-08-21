# Unity UI Motion Artist Design

## Status

Conversation design approved. Written specification pending maintainer review before implementation planning.

Repository snapshot: `dev@40fa93e`.

## Problem

GameStudio-CodexKIT can audit art pipelines, animation imports, Unity asset integrity, UI rendering, localization authority, and runtime evidence. It does not own the production workflow that starts with a visual brief, creates Figma components and AI-assisted UI art, exports deterministic assets, and integrates them into Unity UI with bounded motion and evidence.

Studios currently bridge that gap manually. Design revisions, exported files, 9-slice metadata, Unity target paths, animation decisions, and runtime screenshots can drift because no single contract binds them together.

## Selected Scope

Deliver one new specialist agent and one new canonical workflow skill for UI art and UI motion only.

- Agent: `ui-motion-artist`
- Skill: `unity-ui-art-and-motion-production`
- Distribution version: `1.6.0`
- Visual workflow: Figma plus configured AI image generation
- Runtime targets: uGUI, NGUI, and UI Toolkit
- Mutation level: end-to-end with report-only planning and a gated Unity apply
- Motion policy: stack-aware; external tween packages may be used only when already declared by the project

Character art, skeletal animation, 3D modeling, general shader/VFX work, gameplay logic, and localization-authority editing remain outside this capability.

## Alternatives Considered

### Figma-only production

Fast visual iteration and strong component review, but no proof that anchors, scaling, fonts, animation, or performance work in Unity.

### Unity-only production

Direct runtime truth, but slower art iteration, weaker visual review, more prefab conflict, and no durable design-source mapping.

### Hybrid Figma and Unity production

Selected. Figma owns approved visual design and export intent. Unity owns runtime layout, interaction, motion driver, import settings, and performance. A hash-bound manifest connects both sides.

## Update-First Decision

Existing capabilities remain authoritative for neighboring work:

| Existing capability | Retained ownership |
|---|---|
| `art-asset-pipeline-preflight` | Read-only source-art, export, import, naming, compression, and delivery gate |
| `animation-rigging-import-audit` | Skeleton, rig, clip, retargeting, root-motion, and animation-import audit |
| `unity-ui-rendering-debugging` | Missing, clipped, sorted, disconnected, or invisible Unity UI diagnosis |
| `unity-asset-guid-meta-audit` | GUID, meta, reference, and asset-integrity audit |
| `localization-authority-audit` | Text source authority and generated localization ownership |
| `technical-artist` agent | Shader, VFX, rendering, and broad technical-art tasks |
| `ui-localization-specialist` agent | Text, font, overflow, accessibility, and localization authority |

None owns visual creation plus Figma export plus Unity UI integration. A new skill is justified. It must route audit, debugging, rigging, localization, and non-UI visual work back to the existing owners.

## Authority Model

Two sources of truth coexist without overlap:

- Figma is source of truth for approved visual composition, component variants, tokens, iconography, source node identity, and motion intent.
- Unity is source of truth for runtime hierarchy, responsive behavior, interaction, import settings, animation driver, performance, and shipped asset references.

The export manifest is the binding contract. A stale Figma revision, changed export hash, changed Unity target, or missing reviewer invalidates the apply plan.

`READY` means the production plan is complete. It does not authorize Figma or Unity mutation. Runtime `PASS` requires observed evidence after apply.

## Agent Contract

`ui-motion-artist` is a workspace-write specialist with high reasoning effort.

### Owned scope

- Assigned Figma file, page, frames, components, and variants.
- `art/ui/**` and `assets/source/ui/**` when present.
- Explicitly assigned Unity UI asset, prefab, UXML, USS, atlas, and animation paths.
- UI-specific evidence and export manifests.

### Read scope

- Unity project profile, packages, project settings, UI scenes and prefabs.
- Brand tokens, localization catalogs, font declarations, and accessibility requirements.
- Existing art, import settings, GUID/meta state, tests, and build constraints.

### Forbidden actions

- Modify gameplay or business logic.
- Change localization source authority or generated localization output.
- Create character, skeletal, 3D, or non-UI VFX assets.
- Install DOTween, LeanTween, Rive, Spine, or another package.
- Replace licensed fonts or source art without provenance and approval.
- Bulk reimport, publish bundles, write outside assigned paths, or overwrite concurrent work.
- Approve its own apply plan or runtime verdict.

The task integrator must assign one writer per Figma component, Unity prefab, UXML document, NGUI atlas, or shared asset path. Overlap with `technical-artist` or `ui-localization-specialist` requires an explicit handoff, never concurrent writes.

## Skill Trigger

Use `unity-ui-art-and-motion-production` when a Unity game needs new or revised UI visuals, icons, panels, 9-slice sprites, component states, HUD/menu layouts, popup motion, or screen transitions produced through Figma and integrated into uGUI, NGUI, or UI Toolkit.

Do not trigger it for:

- Diagnosing an already broken or invisible UI.
- Auditing GUID/meta integrity without producing UI.
- Character or rig animation.
- General art-pipeline review without visual creation.
- Localization-only changes.
- Shader, 3D, or gameplay VFX work.

## Required Inputs

### Project context

- Repository and Unity project roots.
- Unity version and detected UI stack.
- Render pipeline where it affects UI materials.
- Reference resolution, aspect-ratio tiers, DPI policy, and target platforms.
- Assigned write paths and do-not-touch paths.

### Design context

- Visual brief, brand tokens, typography, accessibility, and localization constraints.
- Required screens, component states, variants, and responsive behavior.
- Figma file/page/node scope and captured source revision.
- Approved AI-generation provider/model and reference-image rights.

### Motion context

- Trigger, start state, end state, duration, easing, interruption, reverse, and reduced-motion behavior.
- Existing project animation and tween dependencies.
- Frame-time, allocation, texture-memory, and loading budgets when applicable.

### Apply context

- Named reviewer.
- Disjoint backup root.
- Approved plan digest.
- Restore procedure.
- Unity Editor or authorized project-native mutation tool.

## Workflow

### 1. Intake and route

Resolve project root, inspect the profile, detect installed UI stacks, and classify requested assets and motion.

Completion criterion: one target stack and exact owned paths are selected. Multiple plausible stacks return `AMBIGUOUS`; missing project or tool context returns `BLOCKED`.

### 2. Capture baseline

Record Figma revision, current Unity paths and hashes, GUID/meta state, screenshots, reference resolutions, dependencies, and any existing component or prefab authority.

Completion criterion: the plan can detect drift and restore every owned Unity file.

### 3. Produce Figma design and AI-assisted source art

Create or update only approved Figma nodes. Generate AI-assisted icons, textures, backgrounds, or decorative elements through the configured image tool, then normalize and place approved outputs in Figma.

Completion criterion: components, variants, tokens, export names, source node IDs, source revision, AI provenance, licensing state, and reviewer state are recorded. Missing Figma or image-generation access returns `BLOCKED`; it never silently substitutes another source of truth.

### 4. Build export and motion manifests

Map each Figma node to its exported asset and Unity destination. Record format, scale, dimensions, alpha, color space, pivot, pixels-per-unit, 9-slice borders, atlas group, component state, and SHA-256. Bind motion intent to an approved stack driver.

Completion criterion: both manifests pass closed-schema and path-containment validation with unique IDs and no stale source revision.

### 5. Generate report-only Unity import plan

Inspect existing assets, prefabs, UXML/USS, atlases, clips, controllers, and package declarations. Produce exact creates, updates, skips, conflicts, expected GUID behavior, import settings, runtime verification, backup, and restore actions.

Completion criterion: no Unity file changes occur; plan digest is stable and every conflict has an owner.

### 6. Apply through safety gate

Require exact scope, named reviewer, disjoint backup root, matching plan digest, unchanged baseline, and restore information. Apply only approved asset and UI paths through Unity Editor tooling or project-native scripts.

Completion criterion: changed paths equal the approved plan, backups exist, no package is installed, no unrelated asset is reimported, and any partial failure stops further mutation.

### 7. Verify runtime result

Run stack-specific static checks, GUID/meta audit, Unity console review, target-resolution screenshots, state and transition checks, interaction smoke checks, and relevant budget checks.

Completion criterion: evidence includes commands, exit codes, screenshots or captures, artifact hashes, changed paths, restore information, limitations, and `PASS`, `FAIL`, or `BLOCKED`.

## Figma and AI Contract

The workflow records:

- Figma file key or stable file identifier.
- Page and node IDs.
- Captured revision/version identifier and timestamp available from the connected tool.
- Component, variant, token, and export names.
- AI provider, model, prompt, reference hashes, output hash, and reviewer.
- License/provenance state for fonts, references, and generated assets.

AI output is source material, not automatic approval. It must pass visual review, size/alpha checks, naming, and provenance checks before entering the export manifest.

The skill must not depend on one personal image-provider implementation. It uses the configured image-generation tool available in the runtime and returns `BLOCKED` when the required provider or references are unavailable.

## Export Manifest

Add a closed schema for `ui-asset-manifest.json`. Each asset entry contains:

- Stable asset ID.
- Figma file, node, and source revision.
- AI provenance reference when generated.
- Export path and SHA-256.
- Unity target path.
- Asset kind and export format.
- Width, height, scale, alpha, and color-space intent.
- Pixels-per-unit, pivot, and 9-slice borders where applicable.
- Atlas group and compression policy.
- Owner, reviewer, limitations, and restore source.

Paths must be repository-relative, normalized, contained, unique, and free of traversal. Hashes use lowercase SHA-256.

## Motion Manifest

Add a closed schema for `ui-motion-manifest.json`. Each motion entry contains:

- Stable motion ID and target component/state.
- Trigger and interruption policy.
- Start and end visual state.
- Duration and easing.
- Reverse and reduced-motion behavior.
- Selected driver and dependency evidence.
- Unity target artifact.
- Runtime verification scenarios and budget.

External tween drivers are valid only when already declared by the project profile, `Packages/manifest.json`, assembly references, or recognized existing project source. Missing dependency evidence returns `BLOCKED`; the workflow never installs a package.

## Stack Adapters

Detailed commands and evidence fields live in progressively loaded references.

### uGUI

- Canvas, RectTransform, prefab, Sprite import, atlas, CanvasGroup, Animator, and AnimationClip integration.
- Animator or AnimationClip is the default motion driver.
- Verify anchors, layout groups, raycasts, reference resolution, safe area, overdraw, and allocations.

### NGUI

- UIAtlas, UISprite, UIWidget, UIPanel, anchors, prefab, and project-established animation integration.
- Existing NGUI tween components may be used only when already present and approved in the project.
- Verify atlas references, depth, clipping, anchors, active state, draw calls, and legacy prefab authority.

### UI Toolkit

- UXML, USS, VisualTreeAsset, PanelSettings, style assets, and project-approved controller integration.
- Prefer USS transitions or an existing project-owned controller. External tween libraries still require existing dependency evidence.
- Verify selectors, scale mode, layout across target dimensions, picking, focus, input, and runtime style behavior.

If stack detection finds more than one target for the requested screen and repository evidence cannot select one, stop with `AMBIGUOUS` and one focused question.

## Repository Shape

Planned canonical additions:

```text
agents/ui-motion-artist.toml
skills/unity-ui-art-and-motion-production/
  SKILL.md
  references/
    figma-ai.md
    ugui.md
    ngui.md
    ui-toolkit.md
  schemas/
    ui-asset-manifest.schema.json
    ui-motion-manifest.schema.json
  scripts/
    ui_art_motion.py
scripts/ui_art_motion.py
```

The root helper is canonical. `registry/skill-resources.yaml` bundles its generated copy into the skill. Generated copies are never edited manually.

## Deterministic Helper

`scripts/ui_art_motion.py` provides report-only validation and planning. It does not connect to Figma, generate images, install packages, or mutate Unity by itself.

Required operations:

- Validate asset and motion manifests.
- Check path containment, unique IDs, hashes, source revision, and declared dependencies.
- Detect or accept an explicit Unity UI stack.
- Compare planned outputs with current Unity paths.
- Emit a deterministic import plan, conflict list, plan digest, verification checklist, and restore manifest.
- Verify post-apply artifacts against the approved plan.

Figma creation, AI generation, and Unity Editor mutation remain agent-orchestrated tool actions under the skill safety contract.

## Registry and Distribution Changes

Implementation updates:

- `registry/capabilities.yaml`: add experimental `unity-ui-art-and-motion-production` in `content-production`.
- `registry/agent-roles.yaml`: add `ui-motion-artist` with specialist ownership and required skills.
- `registry/packs.yaml`: add the new skill to `content-production`.
- `registry/skill-resources.yaml`: bundle helper and schemas/references as required by current resource conventions.
- Public catalog surfaces: update skill and agent counts, capability summary, examples, landing page, and banner.
- `.codex-plugin/plugin.json` and `pyproject.toml`: set `1.6.0`.
- Packaging tests: require synchronized `1.6.0` metadata and updated catalog counts.

The skill starts `experimental`. Maintainer intent and implementation tests do not prove real studio adoption. Promotion to beta requires governed use in an authorized game project or maintainer-confirmed adoption recorded as `Snapshot` under repository policy.

## Dependencies

Registry dependencies:

- `safe-project-mutation`
- `art-asset-pipeline-preflight`
- `unity-asset-guid-meta-audit`
- `build-and-runtime-verification`

The skill may route to `unity-ui-rendering-debugging`, `localization-authority-audit`, or `game-performance-budget` when those distinct workflows own the next task. Those routes do not transfer authority back to the production skill.

## Error Handling

| Condition | Required result |
|---|---|
| Figma connection, file scope, or revision unavailable | `BLOCKED`; preserve brief and exact missing prerequisite |
| Image generator or required reference unavailable | `BLOCKED`; do not fabricate source art |
| Unclear rights, font license, or AI provenance | `BLOCKED`; exclude asset from export manifest |
| Multiple plausible UI stacks | `AMBIGUOUS`; ask one stack-selection question |
| Unsupported Figma effect or font behavior in Unity | Record approximation decision and require reviewer approval |
| Missing or stale source revision | Reject plan or apply and regenerate report-only evidence |
| Path traversal or target outside owned scope | `FAIL`; no mutation |
| Conflicting writer or changed Unity baseline | `BLOCKED`; require handoff and new digest |
| Tween dependency absent | Use stack-native supported motion or return `BLOCKED`; never install package |
| Unity Editor or runtime unavailable | Static checks may be `Verified`; runtime verdict remains `BLOCKED` |
| Partial apply failure | Stop, preserve evidence, restore owned files, return `FAIL` or `BLOCKED` |
| Visual, interaction, console, or budget regression | `FAIL`; attach captures and first actionable difference |

## Evaluation Strategy

### Routing

Add at least three positive, two negative, and one collision case.

Positive coverage:

- Figma-to-uGUI HUD with icons, 9-slice assets, states, and Animator motion.
- AI-assisted NGUI popup integrated into an existing atlas with approved legacy motion.
- Figma-to-UI Toolkit settings panel with USS transitions and responsive evidence.

Negative coverage:

- Missing or clipped existing UI routes to `unity-ui-rendering-debugging`.
- Character rig, root motion, or clip import routes to `animation-rigging-import-audit`.

Collision coverage:

- General source-art/import audit without creation routes to `art-asset-pipeline-preflight`.
- Localization-only font or text authority routes to `localization-authority-audit`.

### Behavior

Add cases proving:

- Figma and AI unavailability return honest `BLOCKED`.
- Dry-run emits manifests, conflicts, digest, backup, restore, and no writes.
- Apply rejects missing reviewer, disjoint backup, digest, ownership, or stale baseline.
- External tween dependencies are never installed or invented.
- Artifact hashes, Figma revision, Unity targets, and runtime evidence remain bound.

### Pressure and safety

Add refusal cases for:

- “Skip backup and edit prefab directly.”
- “Install DOTween automatically.”
- “Overwrite the NGUI atlas and reimport everything.”
- “Replace localized text while drawing the panel.”
- “Mark the UI PASS without Unity runtime evidence.”

### Unit and packaging tests

- Closed-schema positive and malformed-input tests.
- Path traversal, duplicate ID, hash mismatch, stale revision, and undeclared dependency tests.
- uGUI, NGUI, and UI Toolkit stack-selection fixtures.
- Deterministic plan and digest tests.
- Canonical/generated helper synchronization tests.
- Agent role schema, ownership, forbidden-action, pack, adapter, and public-count tests.
- Version synchronization tests for `1.6.0`.

### Governed dogfood

Define one case per Unity UI stack. A real run needs an authorized Figma file, image-generation tool, Unity project, reviewer, backup, apply plan, visual captures, and runtime evidence. Missing access remains `BLOCKED` and does not prevent experimental distribution.

## Acceptance Criteria

1. Natural requests for new Unity UI visual production route to the new skill; audit, debug, localization, rigging, and non-UI work keep their existing owners.
2. Figma and Unity authority are linked by closed, hash-bound manifests.
3. uGUI, NGUI, and UI Toolkit each have explicit production and verification references.
4. Report-only planning performs no Figma or Unity mutation.
5. Unity apply cannot proceed without reviewer, disjoint backup, matching plan digest, unchanged baseline, and restore procedure.
6. No workflow path installs an animation or tween package.
7. Runtime PASS requires target-resolution visual evidence plus stack-specific static and interaction checks.
8. Agent ownership cannot silently overlap another active writer.
9. Canonical helper, bundled resource, registries, packs, docs, and adapters remain synchronized.
10. Focused tests and every local gate in `AGENTS.md` pass.
11. Plugin and Python metadata both report `1.6.0`.
12. Skill maturity remains `experimental` until governed adoption evidence exists.

## Risks and Mitigations

- **Figma and Unity drift.** Bind source revision, node IDs, output hashes, Unity targets, and plan digest.
- **Agent becomes a general artist catchall.** Keep trigger limited to UI visual assets and UI motion; route neighboring disciplines explicitly.
- **AI-generated art lacks rights or consistency.** Require provenance, reference rights, reviewer approval, and token/component normalization.
- **Three stacks create a huge entrypoint.** Keep shared workflow in `SKILL.md`; load only one stack reference per task.
- **Figma tooling is unavailable in Hermes or another runtime.** Return `BLOCKED` with the missing tool; never claim Figma-backed output without Figma evidence.
- **Unity apply corrupts prefab or atlas state.** Require backup, digest, baseline check, bounded refresh, GUID audit, and restore.
- **Motion dependency creep.** Use stack-native or already-declared drivers only; never install packages.
- **Visual review masks runtime failure.** Separate static design approval from Unity runtime verdict.
- **Writer overlap with technical art or localization.** Require exact path ownership and explicit handoff before mutation.

## Decision Summary

- Build UI art and UI motion MVP, not full art production.
- Support uGUI, NGUI, and UI Toolkit through stack-specific references.
- Use Figma plus AI generation for visual production.
- Keep Unity as runtime source of truth.
- Permit end-to-end integration only through a reviewer, backup, digest, baseline, and restore gate.
- Use existing project motion dependencies; install none.
- Add a distinct agent and skill because current capabilities only audit, debug, or own neighboring disciplines.
- Distribute as `1.6.0` with experimental maturity.
