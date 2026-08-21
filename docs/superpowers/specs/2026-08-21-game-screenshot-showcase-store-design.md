# Game Screenshot Showcase and Store Packaging — Design Specification

**Status:** Proposed; implementation not started
**Date:** 2026-08-21
**Target maturity:** `experimental` until a real Unity project is dogfooded
**Primary engine:** Unity Editor/PlayMode
**Output scope:** runtime evidence, marketing showcase, and store-ready exports

## 1. Problem and outcome

The kit already has separate workflows for playtest evidence, build/runtime verification, and store submission. It does not yet have a bounded workflow that turns a complete Unity feature surface into an approved, traceable screenshot set. The new capability must let a studio:

1. discover candidate scenes/features;
2. review and select flows through an interactive checklist;
3. run approved Unity Editor/PlayMode scenarios;
4. capture raw screenshots with reproducible metadata and hashes;
5. review the result visually through contact sheets;
6. optionally polish approved captures with templates or a canvas editor; and
7. package showcase and platform-sized store exports without performing external publication.

The result is an evidence-first pipeline. Runtime correctness, visual approval, and store readiness are separate verdicts and may not be collapsed into one PASS.

## 2. Scope

### In scope

- A distributed skill named `game-screenshot-showcase-and-store-packaging`.
- A specialist agent role named `game-showcase-capture-producer`.
- Unity Editor/PlayMode as the first capture source.
- Engine-agnostic output contracts so later adapters can target other engines or capture sources.
- Interactive checklist generation and approval before capture.
- Whole-project feature/scene discovery with suggested flows, while allowing the user to remove, reorder, or add flows.
- Raw screenshot capture, evidence manifests, hashes, contact sheets, and visual review records.
- Optional template-based polish and a future/local canvas-editor adapter inspired by public screenshot-editor patterns.
- On-demand platform presets for Android, iOS, Steam/desktop, WebGL, and other supported storefronts.
- Human-controlled store submission boundary.

### Out of scope for the first implementation

- Device/emulator capture as a required dependency.
- Automatic login, upload, signing, legal attestation, payment, or store submission.
- A mandatory Next.js or web application runtime.
- Copying source code, text, or assets from external repositories.
- Automatic claims about gameplay quality, performance, or product-market fit.
- Replacing existing `playtest-evidence`, `build-and-runtime-verification`, or `store-submission-checklist` workflows.

## 3. Chosen approach

The implementation uses the hybrid approach:

- **Capture/evidence layer:** deterministic and governance-heavy. It discovers candidate flows, obtains interactive approval, runs PlayMode, captures raw images, and records exact evidence.
- **Presentation layer:** optional and replaceable. It consumes immutable approved captures and can render a standard template set or hand off to a canvas editor for manual polish.
- **Packaging layer:** produces showcase decks and platform-sized bundles from a manifest. It never publishes externally.

This keeps the core useful in a headless or minimally equipped repository while leaving room for a richer editor later.

## 4. Components and ownership

### 4.1 Canonical skill

`skills/game-screenshot-showcase-and-store-packaging/SKILL.md` owns the workflow, trigger language, input/output contracts, safety rules, evidence vocabulary, and routing to existing skills. It must remain concise and route build, playtest, and store-specific procedures instead of duplicating them.

The skill has five phases:

1. **Discover:** inspect the Unity project and collect candidate scenes, entry points, UI surfaces, feature labels, and available test hooks.
2. **Propose:** present an interactive checklist with suggested flows and explain missing prerequisites.
3. **Capture:** run only approved flows in PlayMode and emit raw evidence records.
4. **Review:** build contact sheets and collect visual approval/rejection decisions.
5. **Package:** render selected captures through templates or an editor adapter and produce showcase/store manifests.

### 4.2 Specialist agent

`agents/game-showcase-capture-producer.toml` owns coordination. It may write only within an explicitly approved game-project output root or the kit's declared artifact locations. It must not alter gameplay code, scenes, prefabs, source art, credentials, or store accounts as part of screenshot production.

Required routed skills:

- `playtest-evidence` for scenario identity, observations, limitations, and follow-up evidence.
- `build-and-runtime-verification` for exact commands, environment, exit codes, and runtime artifacts.
- `store-submission-checklist` for platform requirement snapshots and the human-controlled publication boundary.
- `unity-batchmode-build-verification` only when a batchmode/build path is explicitly selected.
- `unity-ui-rendering-debugging` only when a capture reveals a rendering defect requiring diagnosis.

### 4.3 Capture adapter

The Unity adapter is an implementation boundary, not part of the public contract. It may use Unity Editor automation, PlayMode test hooks, or Unity MCP when available. If no runner is available, the workflow must produce `BLOCKED` with the missing prerequisite rather than fabricate screenshots.

### 4.4 Presentation adapters

Two adapters are planned:

- **Template renderer:** deterministic device frame, safe area, caption, crop, background, and layout presets. It is the default because it is easy to test and package.
- **Canvas editor adapter:** optional local handoff using a connected-canvas/isolated-screen model, canonical JSON state, hashed source images, and platform export presets. The adapter can be implemented later without changing the capture contracts.

### 4.5 Packaging and review output

Packaging creates immutable derived artifacts under a caller-selected output root. The source evidence set remains intact. A rejection is retained as a record and does not silently disappear from the audit trail.

## 5. Data flow and contracts

```text
Unity project
  -> discovery report
  -> interactive checklist
  -> approved capture plan
  -> PlayMode runner
  -> raw screenshots + capture records
  -> contact sheet + visual review
  -> approved evidence set
  -> template/editor presentation
  -> showcase deck + store export manifest
```

### 5.1 `capture-plan.json`

Required fields:

- schema version;
- project path/profile reference;
- build or source identity;
- selected flows in explicit order;
- scene and entry point;
- prerequisites and setup actions;
- expected state or visual checkpoint;
- viewport/resolution and locale;
- capture trigger and timeout;
- reviewer approval and timestamp.

The plan is generated only after interactive checklist approval. It is not a user-editable authority during execution unless re-approved.

### 5.2 `capture-record.json`

Each capture records:

- capture ID and plan ID;
- scenario/feature/scene identity;
- raw image path, MIME type, dimensions, byte size, and SHA-256;
- project/build identity and Unity/editor version snapshot;
- locale, viewport, timestamp, and execution duration;
- runtime result (`PASS`, `FAIL`, or `BLOCKED`);
- visual review result (`approved`, `rejected`, or `needs-review`);
- limitation or rejection reason;
- derived-artifact links, if any.

### 5.3 `showcase-deck.json`

Defines the approved slide order and presentation intent:

- slide ID and source capture ID;
- one clear outcome/message per slide;
- crop and focal region;
- background, device frame, caption, and safe-area settings;
- locale and directionality;
- alt text and content warnings where applicable;
- approval status.

The deck must not reference a capture that lacks a valid hash and visual-review record.

### 5.4 `store-export-manifest.json`

Defines a reproducible export bundle:

- target platform/store and requirement snapshot date/source;
- device class, dimensions, scale, and file format;
- locale and ordering;
- output paths, sizes, hashes, and source capture IDs;
- rejected/missing slots and reasons;
- reviewer and human approval status;
- explicit `BLOCKED` state for any external submission action.

## 6. Checklist and capture lifecycle

1. **Preflight:** verify repository/project path, Unity availability, output root, write scope, and protected paths.
2. **Discovery:** enumerate candidate scenes and hooks; classify suggestions as observed, inferred, or unavailable.
3. **Interactive checklist:** show grouped flows, prerequisites, estimated risk, and suggested priority. The user selects, reorders, edits, or rejects.
4. **Plan freeze:** generate `capture-plan.json`, compute its hash, and require approval before execution.
5. **Bounded execution:** run one flow at a time with an explicit timeout and cleanup step. Capture only at named checkpoints.
6. **Artifact verification:** confirm image decode, dimensions, hash, and record consistency before continuing.
7. **Visual review:** generate contact sheets with labels. Retain every rejection and its reason.
8. **Presentation selection:** choose template or editor adapter; never edit raw evidence in place.
9. **Export:** generate showcase and requested store sizes, then verify all files against the export manifest.
10. **Handoff:** return paths, hashes, verdicts, limitations, and the next human-controlled store action.

## 7. Error handling and safety

- Missing Unity, PlayMode runner, project scene, test hook, or required package: `BLOCKED` with exact prerequisite and safe next step.
- Flow timeout or uncaught PlayMode exception: capture diagnostic logs if available, mark the flow `FAIL`, continue only if the plan permits, and never convert it to PASS.
- Screenshot missing, corrupt, wrong-size, or hash mismatch: reject the record and retain the failure artifact/log.
- Scene or feature discovered but not executable: keep it in the checklist as `unavailable`; do not infer a successful capture.
- Template overflow, unreadable caption, invalid crop, or unsafe area violation: mark visual review `rejected` and do not include it in a store bundle.
- Stale platform requirements: route to `store-submission-checklist`; mark export readiness `BLOCKED` until a current requirement snapshot exists.
- External publication, account access, signing, upload, or legal action: always remain human-controlled and `BLOCKED` until separately approved.
- Credentials and personal data are excluded from all manifests and screenshots; logs must be redacted before packaging.

## 8. Verification and acceptance criteria

### Focused behavior checks

- Discovery proposes a complete, deduplicated feature/scene checklist and distinguishes observed from inferred items.
- Checklist approval is required before a capture plan is executable.
- A rejected flow cannot create a falsely approved showcase slide.
- Every exported image traces to exactly one hashed source capture.
- Platform presets reject unsupported dimensions and report missing requirements.
- A missing Unity runner yields `BLOCKED`, not a synthetic PASS.
- Protected paths and unrelated work remain unchanged.

### Repository gates

After implementation, run the narrowest tests first, then the local gates from `AGENTS.md`:

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
```

Lifecycle audits and real Unity dogfood remain separate. Until a real project produces fresh capture evidence, maturity stays `experimental` and any runtime claim is `BLOCKED` or `Unverified`.

## 9. Provenance and external reference

The design takes conceptual inspiration from `ParthJadhav/app-store-screenshots` (MIT). Reused patterns are limited to the ideas of a connected/isolated canvas, canonical JSON project state, hashed image inputs, multi-platform export presets, and thumbnail-first slide design. No source code, prose, or assets are copied. The external repository remains read-only.

## 10. Planned implementation surface

The implementation plan will decide exact filenames after routing and test preflight. The expected canonical surface is:

- `skills/game-screenshot-showcase-and-store-packaging/SKILL.md`;
- `skills/game-screenshot-showcase-and-store-packaging/agents/openai.yaml`;
- `agents/game-showcase-capture-producer.toml`;
- registry entry in `registry/capabilities.yaml`;
- registry entry in `registry/agent-roles.yaml`;
- scaffold template and `registry/skill-resources.yaml` mapping;
- routing, behavior, pressure, and schema eval cases;
- focused unit/packaging tests;
- documentation/catalog updates only where required by validation.

No generated adapter or `skills/*/scripts/` file is a canonical edit target.
