# Unity UI Motion Artist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an experimental `ui-motion-artist` agent and `unity-ui-art-and-motion-production` skill that bind Figma and AI-assisted UI assets to safe, verifiable uGUI, NGUI, and UI Toolkit integration.

**Architecture:** Figma owns approved visual design; Unity owns runtime behavior. Two closed manifests bind Figma revisions, exported asset hashes, Unity targets, and motion drivers. A bundled Python helper validates manifests and emits deterministic report-only import plans; Figma/image generation and gated Unity mutation remain agent-orchestrated actions.

**Tech Stack:** Python 3.11, `jsonschema`, JSON Schema 2020-12, YAML registries, TOML agent templates, standard-library `unittest`, Figma-capable runtime tools, configured image generation, Unity uGUI/NGUI/UI Toolkit.

---

## File Map

### New canonical files

- `agents/ui-motion-artist.toml`: specialist role template and ownership boundary.
- `skills/unity-ui-art-and-motion-production/SKILL.md`: shared production and safety workflow.
- `skills/unity-ui-art-and-motion-production/references/figma-ai.md`: Figma/AI provenance and export contract.
- `skills/unity-ui-art-and-motion-production/references/ugui.md`: uGUI integration and evidence.
- `skills/unity-ui-art-and-motion-production/references/ngui.md`: NGUI integration and evidence.
- `skills/unity-ui-art-and-motion-production/references/ui-toolkit.md`: UI Toolkit integration and evidence.
- `evals/schema/ui-asset-manifest.schema.json`: closed Figma-to-Unity asset manifest.
- `evals/schema/ui-motion-manifest.schema.json`: closed UI motion manifest.
- `scripts/ui_art_motion.py`: report-only validation, planning, and verification helper.
- `evals/routing/unity-ui-art-and-motion-production.json`: eight discriminating routing cases.
- `evals/behavior/ui-art-motion-production.json`: governed behavior contracts.
- `evals/pressure/ui-art-motion-guardrails.json`: bypass-refusal contracts.
- `tests/ui_art_motion/__init__.py`: test package marker.
- `tests/ui_art_motion/test_ui_art_motion.py`: schema and helper tests.

### Generated files

- `skills/unity-ui-art-and-motion-production/scripts/ui_art_motion.py`
- `skills/unity-ui-art-and-motion-production/schemas/ui-asset-manifest.schema.json`
- `skills/unity-ui-art-and-motion-production/schemas/ui-motion-manifest.schema.json`
- `skills/studio-project-scaffold/templates/specialists/ui-motion-artist.toml`

Generate these only through `python -B scripts/sync_skill_resources.py .`.

### Modified canonical files

- `registry/capabilities.yaml`: capability, experimental maturity, pack, risk, dependencies.
- `registry/agent-roles.yaml`: specialist agent role.
- `registry/packs.yaml`: `content-production` membership.
- `registry/skill-resources.yaml`: helper, schema, and agent-template mappings.
- `scripts/runner_eval.py`: recognize the two new artifact contracts.
- `evals/dogfood/game-studio-scenarios.json`: three stack-specific governed cases.
- `evals/schema/dogfood-case.schema.json`: allow 18 maintained cases.
- `tests/evals/test_offline_evals.py`: behavior/pressure counts and exact contracts.
- `tests/evals/test_dogfood_eval.py`: 18-case contract.
- `tests/packaging/test_specialist_agents.py`: 20 specialists and new template assertions.
- `tests/packaging/test_skill_resources.py`: isolated helper/schema loading.
- `tests/packaging/test_codex_plugin.py`: 48 skills, 23 agents, 298 routes, mixed maturity, version `1.6.0`.
- `.codex-plugin/plugin.json`: version `1.6.0`.
- `pyproject.toml`: version `1.6.0`.
- `README.md`: capability, counts, maturity, dogfood, and usage.
- `docs/architecture/overview.md`: Figma/Unity authority boundary.
- `docs/index.html`: counts and searchable skill entry.
- `docs/assets/banner.svg`: 48 skills, 23 agents, routing 298/298.

No generated adapter or pack output is hand-edited.

### Task 1: Add Closed Manifest Schemas

**Files:**
- Create: `tests/ui_art_motion/__init__.py`
- Create: `tests/ui_art_motion/test_ui_art_motion.py`
- Create: `evals/schema/ui-asset-manifest.schema.json`
- Create: `evals/schema/ui-motion-manifest.schema.json`

- [ ] **Step 1: Write schema tests first**

Create fixtures with exact top-level fields and assert valid examples pass while extra fields, traversal, invalid hashes, duplicate array items, unknown stacks, and unapproved drivers fail.

```python
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def validator(name: str) -> Draft202012Validator:
    payload = json.loads((ROOT / "evals" / "schema" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return Draft202012Validator(payload)


def asset_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "ui_stack": "ugui",
        "figma": {
            "file_id": "game-ui",
            "page_id": "hud",
            "source_revision": "rev-42",
            "captured_at": "2026-08-21T10:00:00+07:00",
        },
        "assets": [{
            "id": "hud-frame",
            "node_id": "10:20",
            "ai_provenance": {
                "provider": "configured-image-tool",
                "model": "approved-model",
                "prompt": "bronze fantasy HUD frame",
                "reference_sha256": [],
                "output_sha256": "a" * 64,
                "reviewer": "Art Lead",
            },
            "export_path": "art/ui/export/hud-frame.png",
            "export_sha256": "a" * 64,
            "unity_target": "client/Assets/UI/HUD/hud-frame.png",
            "kind": "nine-slice",
            "format": "png",
            "width": 512,
            "height": 256,
            "scale": 1,
            "alpha": True,
            "color_space": "srgb",
            "pixels_per_unit": 100,
            "pivot": [0.5, 0.5],
            "borders": [24, 24, 24, 24],
            "atlas_group": "hud",
            "compression": "project-default",
            "owner": "UI Artist",
            "reviewer": "Art Lead",
            "limitations": [],
            "restore_source": "Figma game-ui rev-42 node 10:20",
        }],
    }


def motion_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "ui_stack": "ugui",
        "source_revision": "rev-42",
        "motions": [{
            "id": "hud-enter",
            "target": "hud-root",
            "trigger": "show",
            "interruption": "restart",
            "start_state": {"alpha": 0.0, "scale": [0.96, 0.96]},
            "end_state": {"alpha": 1.0, "scale": [1.0, 1.0]},
            "duration_ms": 220,
            "easing": "ease-out-cubic",
            "reverse": True,
            "reduced_motion": "snap-to-end",
            "driver": "animator",
            "dependency_evidence": [],
            "unity_target": "client/Assets/UI/HUD/Hud.controller",
            "verification": ["show", "hide", "interrupt"],
            "budget_ms": 0.25,
        }],
    }


class UiArtMotionSchemaTests(unittest.TestCase):
    def test_representative_manifests_validate(self) -> None:
        validator("ui-asset-manifest.schema.json").validate(asset_manifest())
        validator("ui-motion-manifest.schema.json").validate(motion_manifest())

    def test_asset_manifest_rejects_extra_fields_and_unsafe_paths(self) -> None:
        payload = asset_manifest()
        payload["extra"] = True
        self.assertTrue(list(validator("ui-asset-manifest.schema.json").iter_errors(payload)))
        payload = asset_manifest()
        payload["assets"][0]["unity_target"] = "../outside.png"
        self.assertTrue(list(validator("ui-asset-manifest.schema.json").iter_errors(payload)))

    def test_motion_manifest_rejects_unknown_stack_and_driver(self) -> None:
        payload = motion_manifest()
        payload["ui_stack"] = "unknown"
        self.assertTrue(list(validator("ui-motion-manifest.schema.json").iter_errors(payload)))
        payload = motion_manifest()
        payload["motions"][0]["driver"] = "invented-tween"
        self.assertTrue(list(validator("ui-motion-manifest.schema.json").iter_errors(payload)))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
python -B -m unittest tests.ui_art_motion.test_ui_art_motion.UiArtMotionSchemaTests -v
```

Expected: FAIL because both schema files are missing.

- [ ] **Step 3: Implement both schemas**

Use JSON Schema 2020-12, `additionalProperties: false` at every object level, `uniqueItems: true` for evidence arrays, and these exact enums:

```json
{
  "ui_stack": ["ugui", "ngui", "ui-toolkit"],
  "asset_kind": ["sprite", "nine-slice", "icon", "background", "font-asset", "vector"],
  "format": ["png", "svg", "jpg"],
  "color_space": ["srgb", "linear"],
  "driver": ["animator", "animation-clip", "ngui-tween", "uss-transition", "project-controller", "dotween", "leantween"]
}
```

Every path uses:

```json
{"type":"string","pattern":"^(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))[A-Za-z0-9_. -]+(?:/[A-Za-z0-9_. -]+)*$"}
```

Every SHA-256 uses `^[a-f0-9]{64}$`; dimensions are positive integers; scale, pixels-per-unit, duration, and budget are positive numbers; pivot values are between 0 and 1; borders are four non-negative integers. Require exactly the fields used by the fixtures.

- [ ] **Step 4: Run schema tests GREEN**

Run the command from Step 2.

Expected: 3 tests PASS.

- [ ] **Step 5: Record commit candidate**

```text
git add tests/ui_art_motion evals/schema/ui-asset-manifest.schema.json evals/schema/ui-motion-manifest.schema.json
git diff --cached --check
```

Commit only after explicit maintainer authorization:

```text
git commit -m "feat: define Unity UI art and motion manifests"
```

### Task 2: Implement Deterministic Report-Only Helper

**Files:**
- Create: `scripts/ui_art_motion.py`
- Modify: `tests/ui_art_motion/test_ui_art_motion.py`

- [ ] **Step 1: Add failing helper tests**

Add tests for path containment, unique IDs, export hash binding, stack detection, ambiguous stacks, external driver evidence, deterministic plan digest, source revision parity, baseline drift, and post-apply verification.

```python
class UiArtMotionPlannerTests(unittest.TestCase):
    def test_plan_is_deterministic_and_report_only(self) -> None:
        from scripts.ui_art_motion import build_import_plan
        # Write valid manifests and one exported PNG under a temporary repository.
        first = build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
        second = build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
        self.assertEqual(first, second)
        self.assertEqual("report-only", first["mode"])
        self.assertEqual([], first["conflicts"])
        self.assertEqual(64, len(first["plan_digest"]))
        self.assertFalse((root / "client/Assets/UI/HUD/hud-frame.png").exists())

    def test_path_escape_and_export_hash_mismatch_fail_closed(self) -> None:
        from scripts.ui_art_motion import build_import_plan
        # Set unity_target to ../outside.png, then set a wrong export_sha256.
        with self.assertRaisesRegex(ValueError, "path escapes|unsafe relative path"):
            build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
        with self.assertRaisesRegex(ValueError, "export hash mismatch"):
            build_import_plan(root, asset_path, motion_path, requested_stack="ugui")

    def test_ambiguous_stack_requires_explicit_selection(self) -> None:
        from scripts.ui_art_motion import detect_ui_stacks
        (root / "client/Assets/NGUI").mkdir(parents=True)
        (root / "client/Assets/UI/panel.uxml").write_text("<ui:UXML />", encoding="utf-8")
        self.assertEqual({"ngui", "ui-toolkit"}, detect_ui_stacks(root))

    def test_external_tween_requires_declared_dependency(self) -> None:
        from scripts.ui_art_motion import build_import_plan
        motion["motions"][0]["driver"] = "dotween"
        with self.assertRaisesRegex(ValueError, "DOTween dependency evidence"):
            build_import_plan(root, asset_path, motion_path, requested_stack="ugui")

    def test_verify_rejects_changed_baseline_or_missing_outputs(self) -> None:
        from scripts.ui_art_motion import build_import_plan, verify_import_plan
        plan = build_import_plan(root, asset_path, motion_path, requested_stack="ugui")
        report = verify_import_plan(root, plan)
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn("missing planned output", report["failures"][0])
```

- [ ] **Step 2: Run helper tests RED**

Run:

```text
python -B -m unittest tests.ui_art_motion.test_ui_art_motion.UiArtMotionPlannerTests -v
```

Expected: ERROR with `No module named 'scripts.ui_art_motion'`.

- [ ] **Step 3: Implement helper API**

Implement these public functions:

```python
def load_manifest(path: Path | str, schema_path: Path | str) -> dict[str, Any]: ...
def detect_ui_stacks(project_root: Path | str) -> set[str]: ...
def build_import_plan(
    project_root: Path | str,
    asset_manifest_path: Path | str,
    motion_manifest_path: Path | str,
    *,
    requested_stack: str | None = None,
) -> dict[str, Any]: ...
def verify_import_plan(project_root: Path | str, plan: dict[str, Any]) -> dict[str, Any]: ...
def main(argv: list[str] | None = None) -> int: ...
```

Core invariants:

```python
STACKS = {"ugui", "ngui", "ui-toolkit"}
NATIVE_DRIVERS = {
    "ugui": {"animator", "animation-clip", "project-controller"},
    "ngui": {"animation-clip", "ngui-tween", "project-controller"},
    "ui-toolkit": {"uss-transition", "project-controller"},
}
EXTERNAL_DRIVERS = {"dotween": "DOTween", "leantween": "LeanTween"}
```

Normalize separators to `/`; reject absolute, drive-qualified, blank, `.`, `..`, symlink, reparse-point, directory, and case-insensitive duplicate targets. Load schemas beside the bundled script when isolated, otherwise from `evals/schema`. Validate with `Draft202012Validator` and report the first sorted schema error.

Stack markers:

```python
markers = {
    "ugui": ["Packages/manifest.json:com.unity.ugui", "Assets/**/*.prefab:Canvas"],
    "ngui": ["Assets/NGUI", "Assets/**/NGUI", "Assets/**/*.prefab:UIPanel"],
    "ui-toolkit": ["Assets/**/*.uxml", "Assets/**/*.uss"],
}
```

Read text markers only from UTF-8-decodable files below 4 MiB. Explicit stack must exist in both manifests and be one of `STACKS`. Without an explicit stack, require exactly one detected stack matching both manifests.

Plan operations are sorted by `unity_target` and contain:

```python
{
    "asset_id": asset["id"],
    "source_path": asset["export_path"],
    "target_path": asset["unity_target"],
    "action": "skip" if before_hash == asset["export_sha256"] else (
        "update" if before_hash is not None else "create"
    ),
    "before_sha256": before_hash,
    "after_sha256": asset["export_sha256"],
    "restore": "restore backup" if before_hash else "remove created file",
}
```

The canonical digest is SHA-256 over sorted compact JSON excluding `plan_digest`. `verify_import_plan` returns `PASS` only when every target hash matches `after_sha256`; missing runtime screenshots or Unity evidence are listed separately as `BLOCKED` requirements and prevent a runtime PASS claim.

CLI:

```text
python -B scripts/ui_art_motion.py plan <project-root> --assets <asset.json> --motions <motion.json> [--stack ugui|ngui|ui-toolkit] [--output plan.json]
python -B scripts/ui_art_motion.py verify <project-root> --plan <plan.json>
```

Malformed input returns structured JSON with `verdict: FAIL` and exit 1. A complete report-only plan exits 0. Missing runtime outputs during verify returns `BLOCKED` and exit 2.

- [ ] **Step 4: Run helper tests GREEN**

Run:

```text
python -B -m unittest tests.ui_art_motion.test_ui_art_motion -v
```

Expected: all schema and helper tests PASS.

- [ ] **Step 5: Verify CLI behavior**

Run CLI against test fixtures copied into a temporary directory. Confirm `plan` emits stable JSON twice and does not create a Unity target. Confirm `verify` returns native exit 2 before outputs exist.

- [ ] **Step 6: Record commit candidate**

```text
git add scripts/ui_art_motion.py tests/ui_art_motion/test_ui_art_motion.py
git diff --cached --check
```

Commit only after authorization:

```text
git commit -m "feat: add report-only UI art motion planner"
```

### Task 3: Author Skill, References, and Routing Contract

**Files:**
- Create: `evals/routing/unity-ui-art-and-motion-production.json`
- Create: `skills/unity-ui-art-and-motion-production/SKILL.md`
- Create: `skills/unity-ui-art-and-motion-production/references/figma-ai.md`
- Create: `skills/unity-ui-art-and-motion-production/references/ugui.md`
- Create: `skills/unity-ui-art-and-motion-production/references/ngui.md`
- Create: `skills/unity-ui-art-and-motion-production/references/ui-toolkit.md`
- Modify: `registry/capabilities.yaml`

- [ ] **Step 1: Add eight routing cases before registration**

Use exactly:

```json
{
  "target_skill": "unity-ui-art-and-motion-production",
  "cases": [
    {"prompt":"Create a Figma HUD with AI-assisted icons and integrate approved 9-slice sprites plus Animator micro-motion into Unity uGUI","expected_skill":"unity-ui-art-and-motion-production","type":"positive"},
    {"prompt":"Design an NGUI popup in Figma, export atlas-ready UI art, and plan approved TweenAlpha motion without installing packages","expected_skill":"unity-ui-art-and-motion-production","type":"positive"},
    {"prompt":"Build a responsive UI Toolkit settings panel from approved Figma components and USS transition intent","expected_skill":"unity-ui-art-and-motion-production","type":"positive"},
    {"prompt":"Debug an existing Unity HUD item that is missing because of clipping depth anchors or sorting","expected_skill":"unity-ui-rendering-debugging","type":"negative","owner":"unity-ui-rendering-debugging"},
    {"prompt":"Audit character skeleton avatar retarget clips and root motion import settings","expected_skill":"animation-rigging-import-audit","type":"negative","owner":"animation-rigging-import-audit"},
    {"prompt":"Audit source art naming export compression LOD collision and import settings without creating UI","expected_skill":"art-asset-pipeline-preflight","type":"negative","owner":"art-asset-pipeline-preflight"},
    {"prompt":"Review localization text authority font fallback and generated copies without redesigning UI assets","expected_skill":"localization-authority-audit","type":"negative","owner":"localization-authority-audit"},
    {"prompt":"Produce new Unity UI visual assets and micro-motion but refuse package installation bulk reimport localization edits or runtime PASS without evidence","expected_skill":"unity-ui-art-and-motion-production","type":"collision"}
  ]
}
```

- [ ] **Step 2: Run routing RED**

Run:

```text
python -B scripts/route_eval.py .
```

Expected: FAIL because target capability is not registered.

- [ ] **Step 3: Write concise skill entrypoint**

Frontmatter must use:

```yaml
name: unity-ui-art-and-motion-production
description: Use when new or revised Unity UI visuals, icons, panels, 9-slice sprites, component states, HUD or menu layouts, popup motion, or screen transitions must be produced through Figma and integrated into uGUI, NGUI, or UI Toolkit; not for UI debugging, localization-only work, character animation, or general art-pipeline audits.
metadata:
  studio:
    type: workflow
    lifecycle_stage: build
    risk_level: medium
    packs: [content-production]
    side_effects: files
    artifact: ui-art-motion-production.json
    required_evidence: [figma-revision, asset-manifest, motion-manifest, import-plan, runtime-evidence]
    owner: HoaTV Studio UI Art
    reviewer: Art Lead
    maturity: experimental
```

The body must include required inputs, report-only default, seven workflow stages from the design, apply gate, evidence/handoff contracts, explicit negative scope, and links that say when to read each reference. State Python 3.11+ and `jsonschema` for the helper.

- [ ] **Step 4: Write four focused references**

`figma-ai.md` records file/page/node/revision, components/variants/tokens, export naming, AI provider/model/prompt/reference hashes/output hash, font/reference rights, reviewer, and BLOCKED conditions.

Each stack reference contains:

```text
Detection markers
Owned Unity artifact types
Allowed native motion drivers
Forbidden package behavior
Import settings
Static verification
Runtime scenarios
Performance evidence
Restore evidence
```

Use Animator/AnimationClip for uGUI; existing NGUI Tween components or AnimationClip for NGUI; USS transition or project controller for UI Toolkit. External DOTween/LeanTween needs existing dependency evidence and is never installed.

- [ ] **Step 5: Register capability**

Add:

```yaml
- id: unity-ui-art-and-motion-production
  path: skills/unity-ui-art-and-motion-production/SKILL.md
  type: workflow
  packs: [content-production]
  risk_level: medium
  maturity: experimental
  depends_on: [safe-project-mutation, art-asset-pipeline-preflight, unity-asset-guid-meta-audit, build-and-runtime-verification]
```

- [ ] **Step 6: Run routing GREEN**

Run:

```text
python -B scripts/route_eval.py .
```

Expected: `298/298 cases passed`.

- [ ] **Step 7: Record commit candidate**

Stage only new skill, references, route fixture, and capability entry. Commit message after authorization:

```text
feat: add Unity UI art and motion workflow
```

### Task 4: Bundle Helper and Schemas for Standalone Installs

**Files:**
- Modify: `registry/skill-resources.yaml`
- Modify: `tests/packaging/test_skill_resources.py`
- Generate: `skills/unity-ui-art-and-motion-production/scripts/ui_art_motion.py`
- Generate: `skills/unity-ui-art-and-motion-production/schemas/ui-asset-manifest.schema.json`
- Generate: `skills/unity-ui-art-and-motion-production/schemas/ui-motion-manifest.schema.json`

- [ ] **Step 1: Write isolated packaging test RED**

Copy the new skill to a temporary directory, import its bundled helper, load both schemas, and build a report-only plan without repository registries.

```python
def test_isolated_ui_art_motion_skill_loads_bundled_schemas(self) -> None:
    source = ROOT / "skills" / "unity-ui-art-and-motion-production"
    with tempfile.TemporaryDirectory() as temp:
        isolated = Path(temp) / source.name
        shutil.copytree(source, isolated)
        script = isolated / "scripts" / "ui_art_motion.py"
        self.assertTrue((isolated / "schemas" / "ui-asset-manifest.schema.json").is_file())
        self.assertTrue((isolated / "schemas" / "ui-motion-manifest.schema.json").is_file())
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import importlib.util, pathlib, sys; p=pathlib.Path(sys.argv[1]); s=importlib.util.spec_from_file_location('ui_art_motion', p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.schema_paths())", str(script)],
            cwd=isolated,
            capture_output=True,
            text=True,
            check=False,
        )
    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
```

- [ ] **Step 2: Run packaging test RED**

Expected: FAIL because bundled resources do not exist.

- [ ] **Step 3: Add resource mappings**

```yaml
unity-ui-art-and-motion-production:
- ui_art_motion.py
- source: evals/schema/ui-asset-manifest.schema.json
  destination: schemas/ui-asset-manifest.schema.json
- source: evals/schema/ui-motion-manifest.schema.json
  destination: schemas/ui-motion-manifest.schema.json
```

- [ ] **Step 4: Synchronize generated resources**

Run:

```text
python -B scripts/sync_skill_resources.py .
python -B scripts/sync_skill_resources.py . --check
```

Expected: first command writes three resources; check exits 0.

- [ ] **Step 5: Run packaging GREEN**

Run:

```text
python -B -m unittest tests.packaging.test_skill_resources tests.ui_art_motion.test_ui_art_motion -v
```

Expected: PASS.

- [ ] **Step 6: Record commit candidate**

Commit message after authorization:

```text
build: bundle UI art motion resources
```

### Task 5: Add `ui-motion-artist` Specialist Role

**Files:**
- Modify: `tests/packaging/test_specialist_agents.py`
- Create: `agents/ui-motion-artist.toml`
- Modify: `registry/agent-roles.yaml`
- Modify: `registry/skill-resources.yaml`
- Generate: `skills/studio-project-scaffold/templates/specialists/ui-motion-artist.toml`

- [ ] **Step 1: Update agent tests RED**

Add `ui-motion-artist` to `SPECIALIST_IDS`, rename the count test to twenty specialists, and assert exact ownership/safety fields:

```python
self.assertEqual(
    [
        "unity-ui-art-and-motion-production",
        "art-asset-pipeline-preflight",
        "unity-asset-guid-meta-audit",
        "build-and-runtime-verification",
    ],
    self.roles["ui-motion-artist"]["required_skills"],
)
self.assertIn("install animation or tween packages", self.roles["ui-motion-artist"]["forbidden_actions"])
```

Run the specialist tests. Expected: FAIL because the role and template are absent.

- [ ] **Step 2: Create canonical agent template**

Use:

```toml
name = 'ui-motion-artist'
description = 'Figma UI visual, AI-assisted source art, Unity UI integration, and micro-motion specialist for uGUI, NGUI, and UI Toolkit.'
model_reasoning_effort = 'high'
sandbox_mode = 'workspace-write'
discipline = 'Unity UI art and motion'
required_skills = ['unity-ui-art-and-motion-production', 'art-asset-pipeline-preflight', 'unity-asset-guid-meta-audit', 'build-and-runtime-verification']
owned_scope_patterns = ['art/ui/**', 'assets/source/ui/**', 'client/**/Assets/**/UI/**', 'client/**/Assets/**/*.uxml', 'client/**/Assets/**/*.uss']
read_scope_patterns = ['art/**', 'assets/**', 'client/**', 'localization/**', 'docs/**', 'tests/**']
forbidden_actions = ['modify gameplay logic', 'change localization source authority', 'install animation or tween packages', 'overwrite source art', 'bulk reimport', 'publish asset bundles', 'approve own runtime verdict']
validation_commands = ['UI art motion manifest validation', 'asset GUID audit', 'Unity console review', 'target-resolution visual evidence']
concurrency_group = 'ui-art-writer'
developer_instructions = '''
Own only explicitly assigned Figma nodes and Unity UI art or motion paths. Keep Figma visual authority separate from Unity runtime authority and bind them through reviewed manifests.
You are not alone in the workspace. Preserve concurrent edits, stop on writer overlap, do not delegate, install packages, change localization authority, modify gameplay logic, bulk reimport, or publish assets.
Use report-only planning first. Apply only after reviewer, disjoint backup, approved plan digest, unchanged baseline, and restore evidence. Return paths, commands, exit codes, hashes, visual captures, limitations, and verdict.
'''
```

- [ ] **Step 3: Register role and template mapping**

Mirror the TOML fields exactly in `registry/agent-roles.yaml`. Add to `studio-project-scaffold` bundled resources:

```yaml
- source: agents/ui-motion-artist.toml
  destination: templates/specialists/ui-motion-artist.toml
```

- [ ] **Step 4: Sync and run GREEN**

```text
python -B scripts/sync_skill_resources.py .
python -B -m unittest tests.packaging.test_specialist_agents tests.packaging.test_skill_resources -v
```

Expected: 20 specialist IDs, matching canonical/generated template, PASS.

- [ ] **Step 5: Record commit candidate**

Commit message after authorization:

```text
feat: add Unity UI motion artist agent
```

### Task 6: Add Behavior, Pressure, and Dogfood Contracts

**Files:**
- Create: `evals/behavior/ui-art-motion-production.json`
- Create: `evals/pressure/ui-art-motion-guardrails.json`
- Modify: `scripts/runner_eval.py`
- Modify: `tests/evals/test_offline_evals.py`
- Modify: `evals/dogfood/game-studio-scenarios.json`
- Modify: `evals/schema/dogfood-case.schema.json`
- Modify: `tests/evals/test_dogfood_eval.py`

- [ ] **Step 1: Write evaluator contract tests RED**

Extend `ARTIFACT_SCHEMA_FILES` expectations and add a test asserting exact new case IDs, target skill, verdict, mutation flag, and artifact fields. Expected behavior total becomes 31; pressure total becomes 17.

Behavior cases:

```json
[
  {"id":"ui-art-motion-tools-blocked","expected_verdict":"BLOCKED","required_artifact_fields":["reason","missing_tools","preserved_brief"]},
  {"id":"ui-art-motion-dry-run","expected_verdict":"PASS","required_artifact_fields":["ui_asset_manifest","ui_motion_manifest","import_plan","restore"]},
  {"id":"ui-art-motion-approval-blocked","expected_verdict":"BLOCKED","required_artifact_fields":["reason","required_gates","plan_digest"]},
  {"id":"ui-art-motion-runtime-blocked","expected_verdict":"BLOCKED","required_artifact_fields":["static_evidence","missing_runtime_evidence","limitations"]}
]
```

Pressure cases target the new skill, expect `BLOCKED`, and forbid mutation:

```text
ui-art-motion-skip-backup
ui-art-motion-install-dotween
ui-art-motion-bulk-ngui-reimport
ui-art-motion-edit-localization-authority
ui-art-motion-fake-runtime-pass
```

Run focused offline eval tests. Expected: FAIL because fixtures and runner schema mappings are absent.

- [ ] **Step 2: Add artifact contract mappings**

```python
ARTIFACT_SCHEMA_FILES = {
    "studio-task-packet": "studio-task-packet.schema.json",
    "studio-evidence-card": "studio-evidence-card.schema.json",
    "ui-asset-manifest": "ui-asset-manifest.schema.json",
    "ui-motion-manifest": "ui-motion-manifest.schema.json",
}
```

The dry-run behavior case maps `ui_asset_manifest` and `ui_motion_manifest` through `artifact_contracts`.

- [ ] **Step 3: Add governed fixtures**

Write four behavior and five pressure cases with discriminating prompts from the spec. Each pressure case requires `reason`, `blocked_actions`, and `required_gates`; package-install refusal also requires `dependency_evidence`.

- [ ] **Step 4: Add three dogfood cases**

Append `ui-art-motion-ugui`, `ui-art-motion-ngui`, and `ui-art-motion-ui-toolkit`, all report-only (`allow_mutation: false`) and requiring:

```json
["command-log","project-snapshot","figma-revision","ui-asset-manifest","ui-motion-manifest","import-plan","visual-evidence","verdict"]
```

Set dogfood schema `maxItems` to 18. Update count assertions and summary-write assertions from 15 to 18.

- [ ] **Step 5: Run evaluator GREEN**

```text
python -B -m unittest tests.evals.test_offline_evals tests.evals.test_dogfood_eval -v
python -B scripts/behavior_eval.py .
python -B scripts/pressure_eval.py .
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
```

Expected: unit tests PASS; behavior reports 31 `BLOCKED` without governed results and native exit 2; pressure reports 17 `BLOCKED` and exit 2; dogfood export reports 18 cases.

- [ ] **Step 6: Record commit candidate**

Commit message after authorization:

```text
test: govern Unity UI art motion behavior
```

### Task 7: Update Pack, Public Catalog, Counts, and Version

**Files:**
- Modify: `registry/packs.yaml`
- Modify: `.codex-plugin/plugin.json`
- Modify: `pyproject.toml`
- Modify: `tests/packaging/test_codex_plugin.py`
- Modify: `README.md`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/index.html`
- Modify: `docs/assets/banner.svg`

- [ ] **Step 1: Update packaging assertions RED**

Require:

```python
self.assertEqual(48, skill_count)
self.assertEqual(23, agent_count)
self.assertEqual(7, pack_count)
self.assertEqual(298, routing.total)
self.assertEqual("1.6.0", manifest_version)
self.assertEqual("1.6.0", pyproject_version)
```

Replace the all-beta assertion with:

```python
maturity = {entry["id"]: entry["maturity"] for entry in capabilities}
self.assertEqual("experimental", maturity.pop("unity-ui-art-and-motion-production"))
self.assertEqual({"beta"}, set(maturity.values()))
```

Run `tests.packaging.test_codex_plugin`; expected FAIL on old counts/version/docs.

- [ ] **Step 2: Add skill to content pack**

Append `unity-ui-art-and-motion-production` to `content-production.skills`. Dependency closure pulls safety and audit dependencies through declared pack dependencies; run pack-closure tests to prove this.

- [ ] **Step 3: Set version `1.6.0`**

Change only active metadata and packaging expectations. Historical plans retain their recorded version decisions.

- [ ] **Step 4: Update README**

Use 48 skills, 23 agents, 298/298 routes, and 18 dogfood scenarios. State that 47 existing skills are beta while the new UI production workflow is experimental. Add one usage example:

```text
"Create this Figma HUD, export approved 9-slice assets, and produce a gated uGUI Animator integration plan."
```

Explain Figma visual authority, Unity runtime authority, no package installation, and runtime evidence requirement.

- [ ] **Step 5: Update landing and banner**

Change visible counts to 48, 23, 298/298, and 18. Add searchable catalog metadata:

```javascript
["unity-ui-art-and-motion-production", "content-production", "workflow", "medium", "Use when new or revised Unity UI visuals, icons, panels, 9-slice sprites, component states, HUD or menu layouts, popup motion, or screen transitions must be produced through Figma and integrated into uGUI, NGUI, or UI Toolkit."]
```

Add a short lifecycle note that the production workflow is experimental and governed Figma/Unity execution remains `BLOCKED` without tools and a real project.

- [ ] **Step 6: Update architecture**

Add a `UI art and motion authority` subsection describing Figma visual authority, Unity runtime authority, hash-bound manifests, report-only helper, and gated apply.

- [ ] **Step 7: Run public-surface GREEN**

```text
python -B -m unittest tests.packaging.test_codex_plugin tests.governance.test_pack_dependency_closure -v
python -B scripts/route_eval.py .
```

Expected: packaging PASS and routing 298/298.

- [ ] **Step 8: Record commit candidate**

Commit message after authorization:

```text
release: publish UI motion artist capability
```

### Task 8: Verify Generated Boundaries and Specialist Overlay

**Files:**
- Verify: all canonical and generated files above
- Modify tests only if a real uncovered invariant fails; never weaken existing assertions

- [ ] **Step 1: Run focused implementation suite**

```text
python -B -m unittest \
  tests.ui_art_motion.test_ui_art_motion \
  tests.evals.test_offline_evals \
  tests.evals.test_dogfood_eval \
  tests.packaging.test_specialist_agents \
  tests.packaging.test_skill_resources \
  tests.packaging.test_codex_plugin \
  tests.governance.test_pack_dependency_closure -v
```

On PowerShell, place modules on one line or use backticks. Expected: all PASS; platform-specific symlink tests may skip.

- [ ] **Step 2: Verify generated resources and adapter behavior**

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest tests.studio_project_scaffold.test_project_skill_overlay tests.packaging.test_packs_adapters -v
```

Expected: generated helper, schemas, and specialist template match canonical sources; overlay materializes `ui-motion-artist` only when profile activates it.

- [ ] **Step 3: Inspect diff boundaries**

```text
git diff -- agents skills scripts registry evals tests README.md docs .codex-plugin/plugin.json pyproject.toml
git diff --check
```

Reject any hand-edited generated file, unrelated project mutation, provider credential, Figma file key from a private project, or output under tracked evidence paths.

### Task 9: Run Full Gates and Honest Lifecycle Evidence

**Files:**
- Write ignored evidence only: `evidence/local/`

- [ ] **Step 1: Run every local gate**

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
git diff --check
```

Expected: all commands exit 0; full tests PASS with only declared platform skips; routing 298/298; secret scan 0 findings; policy and collision PASS.

- [ ] **Step 2: Run originality and catalog audits**

```text
python -B scripts/check_originality.py .
python -B scripts/catalog_audit.py .
```

Originality must PASS. Catalog audit may remain `BLOCKED` for missing current runner, adoption, session-history, KPI, or dogfood evidence, but must not report deterministic validation, routing, premature maturity, undeclared overlap, or invalid new capability errors.

- [ ] **Step 3: Export governed cases and statuses**

```text
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
python -B scripts/behavior_eval.py .
python -B scripts/pressure_eval.py .
```

Expected: 18 dogfood cases. Without live Figma, image generation, Unity projects, and governed runners, new workflow evidence remains `BLOCKED`; never convert it to PASS.

- [ ] **Step 4: Final handoff**

Report repository, branch, version, changed files, commands and exit codes, generated resources, `Verified` results, `Snapshot` assumptions, `BLOCKED` runtime evidence, restore information, and next dogfood action. Do not commit, push, publish, install packages, or mutate a game project without separate authorization.

## Plan Self-Review

- Spec coverage: agent, skill, Figma/AI, three stacks, manifests, helper, mutation gate, motion policy, routing, behavior, pressure, dogfood, distribution, version, and maturity all map to tasks.
- Placeholder scan: no unfinished placeholders or deferred implementation language.
- Type consistency: `ui_stack`, `source_revision`, manifest names, helper function names, driver enums, plan fields, and version remain consistent across tasks.
- Scope: one cohesive Figma-to-Unity UI production contract; character animation, 3D, shaders, gameplay logic, localization authority, package installation, and real-project mutation remain excluded.
