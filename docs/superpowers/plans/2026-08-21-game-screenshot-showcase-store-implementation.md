# Game Screenshot Showcase and Store Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an experimental Unity-first screenshot capture, evidence review, showcase, and store-packaging capability with an opt-in specialist agent.

**Architecture:** A canonical skill orchestrates discovery, interactive checklist approval, bounded PlayMode capture, immutable evidence records, visual review, and optional presentation/export adapters. A bundled standard-library helper validates four closed JSON contracts, hashes image artifacts, generates an HTML contact sheet, and emits deterministic export manifests; Unity runtime execution remains an adapter boundary and reports `BLOCKED` when unavailable.

**Tech Stack:** Python 3.11, standard library plus the repository's existing `jsonschema`/PyYAML tooling, JSON Schema 2020-12, YAML registries, TOML agent templates, Unity Editor/PlayMode or optional Unity MCP, HTML contact sheets, and platform-specific image tooling when explicitly available.

---

## File map

### New canonical files

- `skills/game-screenshot-showcase-and-store-packaging/SKILL.md`: workflow, triggers, evidence vocabulary, safety, and routing.
- `skills/game-screenshot-showcase-and-store-packaging/agents/openai.yaml`: display metadata and default prompt.
- `agents/game-showcase-capture-producer.toml`: specialist ownership and handoff contract.
- `scripts/screenshot_showcase.py`: report-only discovery, manifest validation, hashing, contact-sheet generation, and export-manifest helper.
- `evals/schema/capture-plan.schema.json`: approved checklist-to-execution contract.
- `evals/schema/capture-record.schema.json`: raw screenshot evidence contract.
- `evals/schema/showcase-deck.schema.json`: reviewed presentation contract.
- `evals/schema/store-export-manifest.schema.json`: platform export and human approval contract.
- `evals/routing/game-screenshot-showcase-and-store-packaging.json`: routing, negative, and collision cases.
- `evals/behavior/game-screenshot-showcase-and-store-packaging.json`: behavior contracts.
- `evals/pressure/game-screenshot-showcase-and-store-guardrails.json`: bypass/refusal contracts.
- `tests/screenshot_showcase/__init__.py`: test package marker.
- `tests/screenshot_showcase/test_screenshot_showcase.py`: schema, path-safety, hashing, contact-sheet, and export-manifest tests.

### Generated files

- `skills/game-screenshot-showcase-and-store-packaging/scripts/screenshot_showcase.py`.
- `skills/game-screenshot-showcase-and-store-packaging/schemas/capture-plan.schema.json`.
- `skills/game-screenshot-showcase-and-store-packaging/schemas/capture-record.schema.json`.
- `skills/game-screenshot-showcase-and-store-packaging/schemas/showcase-deck.schema.json`.
- `skills/game-screenshot-showcase-and-store-packaging/schemas/store-export-manifest.schema.json`.
- `skills/studio-project-scaffold/templates/specialists/game-showcase-capture-producer.toml`.

Generate these only through `python -B scripts/sync_skill_resources.py .`.

### Modified canonical files

- `registry/capabilities.yaml`: add one experimental workflow capability.
- `registry/agent-roles.yaml`: add the specialist role.
- `registry/packs.yaml`: add the skill to `content-production`.
- `registry/skill-resources.yaml`: map the helper, schemas, and specialist template.
- `tests/packaging/test_specialist_agents.py`: add the new specialist ID and exact ownership assertions.
- `tests/packaging/test_skill_resources.py`: add isolated helper/schema loading coverage.
- `evals/schema/dogfood-case.schema.json` and `evals/dogfood/game-studio-scenarios.json`: extend only if the current maintained-case contract requires a new governed scenario.
- `.codex-plugin/plugin.json`, `pyproject.toml`, and maintained catalog/docs counts: increment the distributed version from the current `1.6.2` snapshot to `1.6.3` only after the payload and validation confirm a distributed change.

Do not edit generated adapters, packs, or mirrored skill resources by hand. Preserve the unrelated dirty Unity UI motion changes already present in the worktree.

## Task 1: Establish failing contract tests and closed schemas

**Files:**
- Create: `tests/screenshot_showcase/__init__.py`
- Create: `tests/screenshot_showcase/test_screenshot_showcase.py`
- Create: `evals/schema/capture-plan.schema.json`
- Create: `evals/schema/capture-record.schema.json`
- Create: `evals/schema/showcase-deck.schema.json`
- Create: `evals/schema/store-export-manifest.schema.json`

- [ ] **Step 1: Write representative fixtures and failing tests first.**

Create fixtures with exact top-level fields for an approved plan, a raw capture, an approved showcase slide, and a store export. Assert valid examples pass and the following fail: extra top-level fields, absolute paths, `..` traversal, empty IDs, invalid SHA-256 values, dimension mismatches, capture records without visual review, showcase slides pointing to rejected captures, and store exports with unsupported dimensions or missing human approval.

Use `jsonschema.Draft202012Validator`, load schemas from `evals/schema`, and keep the test independent of Unity. The tests must import `scripts.screenshot_showcase`; before implementation this import or the expected functions must fail.

Required helper API names used by the tests:

```python
validate_payload(schema_name: str, payload: object) -> list[str]
sha256_file(path: Path) -> str
image_dimensions(path: Path) -> tuple[int, int]
build_contact_sheet(records: list[dict[str, object]], output: Path) -> dict[str, object]
build_store_export_manifest(
    deck: dict[str, object], platform: str, locale: str, output_root: Path,
) -> dict[str, object]
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing implementation.**

Run:

```text
python -B -m unittest tests.screenshot_showcase.test_screenshot_showcase -v
```

Expected: `FAIL` or import errors naming the missing helper/module, with no schema test falsely passing.

- [ ] **Step 3: Add closed JSON Schemas.**

Each schema must use `additionalProperties: false`, `schema_version: 1`, explicit enums, minimum lengths, SHA-256 patterns, and safe relative path patterns. Required semantics:

`capture-plan.schema.json` must require project/source identity, ordered flows, scene/entry point, checkpoint, viewport, locale, timeout, and reviewer approval.

`capture-record.schema.json` must require raw image path, MIME type, dimensions, byte size, hash, build/editor snapshot, runtime result, visual review result, and limitation/rejection fields.

`showcase-deck.schema.json` must require source capture ID, one outcome/message, crop/focal data, layout settings, locale/direction, alt text, and approval status.

`store-export-manifest.schema.json` must require platform, requirement snapshot, device/dimensions/format, ordered outputs, hashes, source capture IDs, missing/rejected slots, reviewer, and a human approval status.

- [ ] **Step 4: Run the focused schema tests and verify they pass.**

Run the same unittest command. Expected: all contract tests pass and invalid payload tests report the intended validation failures.

## Task 2: Implement the report-only screenshot helper

**Files:**
- Modify: `scripts/screenshot_showcase.py`
- Test: `tests/screenshot_showcase/test_screenshot_showcase.py`

- [ ] **Step 1: Implement safe path and hash primitives.**

Implement `safe_relative_path(root, value, label, must_exist=False)` with Windows drive, absolute path, empty segment, `.`/`..`, NUL, symlink, reparse-point, containment, regular-file, and optional existence checks. Implement `sha256_file` in 1 MiB chunks. Reuse the repository's existing safety conventions; do not shell out to delete, copy, or mutate project files.

- [ ] **Step 2: Implement image header inspection without a new runtime dependency.**

Implement `image_dimensions` for PNG and JPEG headers only. Reject truncated, unsupported, or malformed files with a deterministic `ValueError`. The helper may accept WebP/other formats only by recording `dimensions: null` and returning `BLOCKED` from the caller; it must never invent dimensions.

- [ ] **Step 3: Implement payload validation and capture-record verification.**

Implement `validate_payload` to load a canonical schema, return sorted `path: message` failures, and reject missing schemas as a clear error. Add `verify_capture_record(project_root, record)` that validates safe paths, confirms the image exists and decodes, checks recorded byte size/dimensions/hash, and returns a JSON-safe result with `PASS`, `FAIL`, or `BLOCKED` plus failure strings.

- [ ] **Step 4: Implement deterministic contact-sheet generation.**

Implement `build_contact_sheet(records, output)` as an HTML artifact, not a binary image compositor. It must sort records by explicit order then capture ID, include escaped labels, image paths, runtime/visual verdicts, hashes, and rejection reasons, and write only below the caller-provided output path. It must retain rejected/blocked records visibly.

- [ ] **Step 5: Implement export-manifest construction.**

Implement `build_store_export_manifest(deck, platform, locale, output_root)` to validate the deck first, reject unapproved/rejected source captures, normalize output paths below `output_root`, preserve requested order, hash existing outputs, and return `BLOCKED` when a platform requirement snapshot or human approval is missing. The function must not resize, overwrite, upload, or delete images.

- [ ] **Step 6: Add a report-only CLI.**

Provide subcommands:

```text
python -B scripts/screenshot_showcase.py verify-capture <project-root> --record <capture-record.json>
python -B scripts/screenshot_showcase.py contact-sheet --records <records.json> --output <review.html>
python -B scripts/screenshot_showcase.py export-manifest --deck <showcase-deck.json> --platform <platform> --locale <locale> --output-root <dir>
```

Exit codes must be `0` for PASS, `1` for FAIL, and `2` for BLOCKED. Print deterministic JSON with `verdict`, `failures`, and artifact paths. No command may invoke Unity or mutate source project files.

- [ ] **Step 7: Run helper tests and CLI smoke tests.**

Run:

```text
python -B -m unittest tests.screenshot_showcase.test_screenshot_showcase -v
python -B scripts/screenshot_showcase.py --help
```

Expected: focused tests pass; help exits `0`; malformed/missing runtime inputs return the documented FAIL/BLOCKED code and JSON.

## Task 3: Author the canonical skill and its routing contract

**Files:**
- Create: `skills/game-screenshot-showcase-and-store-packaging/SKILL.md`
- Create: `skills/game-screenshot-showcase-and-store-packaging/agents/openai.yaml`
- Create: `evals/routing/game-screenshot-showcase-and-store-packaging.json`
- Create: `evals/behavior/game-screenshot-showcase-and-store-packaging.json`
- Create: `evals/pressure/game-screenshot-showcase-and-store-guardrails.json`

- [ ] **Step 1: Write the skill with closed workflow phases.**

Document the five phases exactly: discover, propose interactive checklist, capture only after approval, review, and package. State Unity Editor/PlayMode as the first adapter, report-only fallback behavior, artifact contracts, separate runtime/visual/store verdicts, protected paths, privacy redaction, and human-controlled publication. Route to existing skills for playtest, runtime, batchmode, UI debugging, and store requirements.

- [ ] **Step 2: Add agent metadata.**

Set the OpenAI display name, short description, and default prompt to invoke `$game-screenshot-showcase-and-store-packaging` for Unity feature capture and showcase/store packaging.

- [ ] **Step 3: Add discriminating routing cases.**

Include at least four positive prompts covering Unity PlayMode feature capture, interactive checklist-to-manifest generation, showcase deck production, and platform export packaging; at least two negative cases owned by `playtest-evidence` or `store-submission-checklist`; and at least one collision case requiring refusal of auto-upload or fabricated runtime PASS.

- [ ] **Step 4: Add behavior and pressure contracts.**

Behavior cases must assert checklist approval before execution, raw evidence preservation, traceable hashes, rejected-slide exclusion, and `BLOCKED` when Unity is unavailable. Pressure cases must assert refusal of credential use, store submission, source overwrite, path traversal, and runtime PASS claims without evidence.

- [ ] **Step 5: Run route and offline evals before registry edits.**

Run:

```text
python -B scripts/route_eval.py .
python -B scripts/behavior_eval.py . --export evidence/local/screenshot-showcase-behavior.jsonl
python -B scripts/pressure_eval.py . --export evidence/local/screenshot-showcase-pressure.jsonl
```

Expected: new routing cases rank the new skill first, and the new behavior/pressure cases are structurally accepted. Any failure is fixed in the canonical skill/eval files, not by weakening the evaluator.

## Task 4: Register and package the skill and specialist role

**Files:**
- Create: `agents/game-showcase-capture-producer.toml`
- Modify: `registry/capabilities.yaml`
- Modify: `registry/agent-roles.yaml`
- Modify: `registry/packs.yaml`
- Modify: `registry/skill-resources.yaml`
- Create through sync: `skills/studio-project-scaffold/templates/specialists/game-showcase-capture-producer.toml`
- Test: `tests/packaging/test_specialist_agents.py`
- Test: `tests/packaging/test_skill_resources.py`

- [ ] **Step 1: Add the canonical specialist template.**

Use `name = 'game-showcase-capture-producer'`, `kind = 'specialist'`, high reasoning, workspace-write, discipline `Game screenshot showcase production`, required skills `[game-screenshot-showcase-and-store-packaging, playtest-evidence, build-and-runtime-verification, store-submission-checklist]`, output ownership limited to approved evidence/showcase roots, and forbidden actions covering gameplay edits, credential access, publication, source overwrite, evidence deletion, and self-approval.

- [ ] **Step 2: Add the capability entry.**

Register ID `game-screenshot-showcase-and-store-packaging` with path `skills/game-screenshot-showcase-and-store-packaging/SKILL.md`, type `workflow`, pack `content-production`, risk `medium`, maturity `experimental`, and dependencies `[playtest-evidence, build-and-runtime-verification, store-submission-checklist]`. Keep provenance explicitly conceptual/MIT from `ParthJadhav/app-store-screenshots` with copied text/assets set to none.

- [ ] **Step 3: Add the role and pack membership.**

Mirror the TOML role fields in `registry/agent-roles.yaml`; add the skill to `content-production` in `registry/packs.yaml`; map the helper, four schemas, and role template in `registry/skill-resources.yaml`.

- [ ] **Step 4: Extend packaging tests before synchronization.**

Add `game-showcase-capture-producer` to the specialist ID set and assert exact required skills, ownership patterns, forbidden actions, and canonical template parity. Assert the bundled skill contains all four schemas and the helper can load in an isolated copied skill directory.

- [ ] **Step 5: Synchronize generated resources and run packaging tests.**

Run:

```text
python -B scripts/sync_skill_resources.py .
python -B -m unittest tests.packaging.test_specialist_agents tests.packaging.test_skill_resources -v
python -B scripts/sync_skill_resources.py . --check
```

Expected: generated files have the required header, packaging tests pass, and the check reports no drift.

## Task 5: Update maintained catalog metadata and version only after payload validation

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/index.html`
- Modify: `docs/assets/banner.svg` only if maintained counts are encoded there
- Modify: related catalog/eval count assertions discovered by focused test failures

- [ ] **Step 1: Inspect current counts and version references.**

Use `rg -n "1\.6\.2|skills|specialists|routing" .codex-plugin/plugin.json pyproject.toml README.md docs tests` and record the current dirty-worktree baseline. Do not rewrite unrelated UI motion documentation.

- [ ] **Step 2: Update only the distributed metadata.**

Set the plugin/package version to `1.6.3` if and only if the new skill/agent is registered and packaged. Update skill/agent/routing counts and add one concise usage example. Keep maturity `experimental`; do not claim real Unity dogfood.

- [ ] **Step 3: Run focused catalog tests.**

Run:

```text
python -B -m unittest tests.packaging.test_codex_plugin tests.packaging.test_packs_adapters tests.evals.test_offline_evals -v
```

Expected: version, count, resource, and evaluation contracts pass with no changes to unrelated existing specialist behavior.

## Task 6: Run the complete local gates and evidence review

**Files:**
- Modify only failing canonical sources or tests identified by the commands below.
- Produce ignored local evidence under `evidence/local/` when required by the scripts.

- [ ] **Step 1: Run all repository gates.**

Run exactly:

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

Record command, exit code, duration, and first actionable failure in the handoff. A missing live Unity runner remains `BLOCKED`; it is not a reason to weaken repository gates.

- [ ] **Step 2: Run lifecycle audits.**

Run `python -B scripts/check_originality.py .` and `python -B scripts/catalog_audit.py .`. Confirm the external repository is named only as conceptual MIT provenance and that maturity remains `experimental` without dogfood evidence.

- [ ] **Step 3: Inspect the final diff and protected paths.**

Run `git diff --check`, `git status --short`, and a targeted diff review for all new/modified files. Confirm no `.env`, `.research`, external checkout, private project, generated adapter, or unrelated UI motion file was overwritten.

- [ ] **Step 4: Prepare the handoff.**

Report changed paths, exact commands/exit codes, artifacts, `Verified` results, `Snapshot` assumptions, `Unverified` claims, `BLOCKED` Unity/runtime items, restore information, and the next action. Do not commit or push until the user explicitly authorizes it under the repository contract.

## Self-review checklist

- [ ] The plan covers discovery, interactive checklist approval, PlayMode capture boundary, evidence contracts, contact sheet, optional presentation, store export, and human publication gate.
- [ ] Every new executable helper has a failing test before implementation.
- [ ] All output paths are bounded and hashed; raw evidence is never overwritten.
- [ ] Existing skills remain the authority for playtest, runtime, and store requirements.
- [ ] External repository provenance is conceptual only; no source/text/assets are copied.
- [ ] Missing Unity/runtime support remains `BLOCKED`.
- [ ] Version/count updates occur only after canonical registration and packaging pass.
- [ ] No plan step contains a placeholder or an unspecified file owner.
