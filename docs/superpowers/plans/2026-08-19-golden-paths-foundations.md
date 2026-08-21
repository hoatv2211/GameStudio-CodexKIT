# Golden Paths Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scoped packs dependency-closed, enforce identical scaffold approval gates across every entry point, and add the backward-compatible profile and artifact contracts required by Role UX.

**Architecture:** Add a pure catalog-graph module shared by registry validation and pack generation. Tighten the canonical scaffold API so all callers must supply the reviewed digest and a non-overlapping backup root. Extend the project profile with UX defaults and introduce strict JSON schemas for normalized task packets and evidence cards without changing canonical workflow ownership.

**Tech Stack:** Python 3.11, PyYAML, jsonschema, standard-library `unittest`, JSON Schema 2020-12.

---

## File Map

- Create `scripts/catalog_graph.py`: pure pack and capability dependency resolution.
- Create `tests/governance/test_pack_dependency_closure.py`: registry and synthetic closure tests.
- Modify `scripts/validate.py`: report missing pack dependency closure.
- Modify `scripts/build_packs.py`: package the resolved transitive skill set.
- Modify `registry/packs.yaml`: declare the missing Unity and production/liveops pack dependencies.
- Modify `tests/packaging/test_packs_adapters.py`: assert generated packs contain their dependency closure.
- Modify `scripts/project_scaffold.py`: require the approved digest and reject overlapping backup paths.
- Modify `scripts/gamestudio_cli.py`: preserve CLI/API approval parity.
- Modify `tests/studio_project_scaffold/test_project_scaffold.py`: direct API negative and success cases.
- Modify `tests/studio_project_scaffold/test_gamestudio_cli.py`: standalone and primary CLI parity cases.
- Modify `scripts/project_profile.py`: validate optional `studio_experience` defaults.
- Modify `tests/project_profile/test_project_profile.py`: backward compatibility and strict UX-field validation.
- Create `evals/schema/studio-task-packet.schema.json`: normalized pre-execution contract.
- Create `evals/schema/studio-evidence-card.schema.json`: normalized result contract.
- Create `tests/evals/test_studio_experience_schemas.py`: strict schema tests.
- Modify `scripts/project_scaffold.py`: include safe UX defaults in newly drafted profiles.
- Modify `registry/skill-resources.yaml`: bundle the two schemas with the root and scaffold skills.
- Modify `.codex-plugin/plugin.json` and `pyproject.toml`: patch-version the distributed foundation change from the refreshed `1.5.3` baseline.
- Modify `tests/packaging/test_codex_plugin.py`: keep the exact manifest-version assertion synchronized.

### Task 1: Add Pure Pack Dependency Resolution

**Files:**
- Create: `scripts/catalog_graph.py`
- Create: `tests/governance/test_pack_dependency_closure.py`

- [ ] **Step 1: Write the failing synthetic closure tests**

Create `tests/governance/test_pack_dependency_closure.py`:

```python
from __future__ import annotations

import unittest


class PackDependencyClosureTests(unittest.TestCase):
    def capabilities(self) -> list[dict[str, object]]:
        return [
            {"id": "root", "depends_on": []},
            {"id": "unity-audit", "depends_on": ["root"]},
            {"id": "art-preflight", "depends_on": ["unity-audit"]},
        ]

    def test_resolves_transitive_pack_skills(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "core", "skills": ["root"], "depends_on": []},
            {"id": "unity", "skills": ["unity-audit"], "depends_on": ["core"]},
            {"id": "content", "skills": ["art-preflight"], "depends_on": ["unity"]},
        ]

        self.assertEqual(
            ["art-preflight", "root", "unity-audit"],
            resolve_pack_skill_closure(packs, self.capabilities(), "content"),
        )

    def test_rejects_capability_missing_from_declared_pack_closure(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "core", "skills": ["root"], "depends_on": []},
            {"id": "unity", "skills": ["unity-audit"], "depends_on": ["core"]},
            {"id": "content", "skills": ["art-preflight"], "depends_on": ["core"]},
        ]

        with self.assertRaisesRegex(
            ValueError,
            "pack content is missing capability unity-audit required by art-preflight",
        ):
            resolve_pack_skill_closure(packs, self.capabilities(), "content")

    def test_rejects_pack_dependency_cycles(self) -> None:
        from scripts.catalog_graph import resolve_pack_skill_closure

        packs = [
            {"id": "a", "skills": ["root"], "depends_on": ["b"]},
            {"id": "b", "skills": [], "depends_on": ["a"]},
        ]

        with self.assertRaisesRegex(ValueError, "pack dependency cycle: a -> b -> a"):
            resolve_pack_skill_closure(packs, self.capabilities(), "a")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run:

```text
python -B -m unittest tests.governance.test_pack_dependency_closure -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.catalog_graph'`.

- [ ] **Step 3: Implement the pure resolver**

Create `scripts/catalog_graph.py`:

```python
from __future__ import annotations

from typing import Any, Iterable


def _index(items: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get("id", ""))
        if not item_id or item_id in indexed:
            raise ValueError(f"invalid or duplicate {label} id: {item_id}")
        indexed[item_id] = item
    return indexed


def resolve_pack_skill_closure(
    packs: Iterable[dict[str, Any]],
    capabilities: Iterable[dict[str, Any]],
    pack_id: str,
) -> list[str]:
    pack_by_id = _index(packs, "pack")
    capability_by_id = _index(capabilities, "capability")
    if pack_id not in pack_by_id:
        raise ValueError(f"unknown pack: {pack_id}")

    selected_packs: set[str] = set()

    def visit_pack(current: str, trail: tuple[str, ...]) -> None:
        if current in trail:
            cycle = " -> ".join((*trail[trail.index(current):], current))
            raise ValueError(f"pack dependency cycle: {cycle}")
        pack = pack_by_id.get(current)
        if pack is None:
            raise ValueError(f"unknown pack dependency: {current}")
        if current in selected_packs:
            return
        for dependency in pack.get("depends_on", []) or []:
            visit_pack(str(dependency), (*trail, current))
        selected_packs.add(current)

    visit_pack(pack_id, ())
    available = {
        str(skill_id)
        for selected_pack in selected_packs
        for skill_id in pack_by_id[selected_pack].get("skills", []) or []
    }

    for skill_id in sorted(available):
        capability = capability_by_id.get(skill_id)
        if capability is None:
            raise ValueError(f"pack {pack_id} references unknown capability {skill_id}")
        pending = [str(value) for value in capability.get("depends_on", []) or []]
        seen: set[str] = set()
        while pending:
            dependency = pending.pop()
            if dependency in seen:
                continue
            seen.add(dependency)
            dependency_capability = capability_by_id.get(dependency)
            if dependency_capability is None:
                raise ValueError(f"capability {skill_id} references unknown dependency {dependency}")
            if dependency not in available:
                raise ValueError(
                    f"pack {pack_id} is missing capability {dependency} required by {skill_id}"
                )
            pending.extend(
                str(value) for value in dependency_capability.get("depends_on", []) or []
            )
    return sorted(available)
```

- [ ] **Step 4: Run the focused tests**

Run:

```text
python -B -m unittest tests.governance.test_pack_dependency_closure -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit only after explicit maintainer authorization**

```text
git add scripts/catalog_graph.py tests/governance/test_pack_dependency_closure.py
git commit -m "feat: resolve pack dependency closure"
```

### Task 2: Enforce Closure in Registry Validation

**Files:**
- Modify: `scripts/validate.py:13-26`
- Modify: `scripts/validate.py:457-562`
- Modify: `registry/packs.yaml:64-71`
- Modify: `tests/governance/test_pack_dependency_closure.py`

- [ ] **Step 1: Add a failing repository-registry test**

Append to `PackDependencyClosureTests`:

```python
    def test_repository_pack_registry_is_dependency_closed(self) -> None:
        from pathlib import Path

        from scripts.catalog_graph import resolve_pack_skill_closure
        from scripts.common import load_yaml

        root = Path(__file__).resolve().parents[2]
        packs = load_yaml(root / "registry" / "packs.yaml")["packs"]
        capabilities = load_yaml(root / "registry" / "capabilities.yaml")["capabilities"]

        for pack in packs:
            with self.subTest(pack=pack["id"]):
                resolved = resolve_pack_skill_closure(packs, capabilities, pack["id"])
                self.assertTrue(resolved)
```

- [ ] **Step 2: Run the test and observe the current catalog failure**

Run:

```text
python -B -m unittest tests.governance.test_pack_dependency_closure.PackDependencyClosureTests.test_repository_pack_registry_is_dependency_closed -v
```

Expected: FAIL for `production-management` or `content-production` with a missing capability message.

- [ ] **Step 3: Add the missing pack dependencies**

Change the three compact pack records in `registry/packs.yaml` to:

```yaml
- id: production-management
  description: Production planning, dependency risk, QA strategy, compatibility, and capacity verification workflows.
  skills: [studio-production-planning, production-risk-and-dependency-review, qa-test-strategy-and-coverage, platform-device-compatibility-matrix, load-soak-capacity-verification]
  depends_on: [studio-core, production-design-liveops]
- id: content-production
  description: Level, narrative, art, animation, and audio content production review workflows.
  skills: [level-and-content-design-review, narrative-quest-content-contract, art-asset-pipeline-preflight, animation-rigging-import-audit, audio-content-pipeline-review]
  depends_on: [studio-core, unity, production-design-liveops]
- id: product-analytics
  description: Product experimentation and governed live content rollout workflows.
  skills: [product-analytics-experiment-review, liveops-content-rollout-and-rollback]
  depends_on: [production-design-liveops]
```

- [ ] **Step 4: Integrate closure validation into `validate.py`**

Add the import beside the existing local/fallback imports:

```python
try:
    from scripts.catalog_graph import resolve_pack_skill_closure
except ModuleNotFoundError:
    from catalog_graph import resolve_pack_skill_closure
```

After pack cycles are checked, add:

```python
    if not _find_cycles(pack_graph):
        for pack_id in pack_ids:
            try:
                resolve_pack_skill_closure(packs, capabilities, pack_id)
            except ValueError as error:
                _issue(
                    issues,
                    "registry.pack.dependency.missing",
                    packs_path,
                    str(error),
                )
```

- [ ] **Step 5: Run focused validation tests**

Run:

```text
python -B -m unittest tests.governance.test_pack_dependency_closure tests._meta.test_validate -v
```

Expected: all tests PASS. If the long-lived Windows checkout still reports the known promotion-artifact CRLF hash mismatch, run the same command in a fresh temporary clone and record the local checkout limitation separately.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add scripts/validate.py registry/packs.yaml tests/governance/test_pack_dependency_closure.py
git commit -m "fix: require dependency-closed packs"
```

### Task 3: Package the Resolved Skill Closure

**Files:**
- Modify: `scripts/build_packs.py:1043-1137`
- Modify: `tests/packaging/test_packs_adapters.py:629-691`

- [ ] **Step 1: Add failing artifact-closure assertions**

In `test_pack_build_is_deterministic_and_generated`, after the existing pack-set assertion, add:

```python
            content_manifest = json.loads(
                (output / "content-production" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [
                    "art-asset-pipeline-preflight",
                    "audio-content-pipeline-review",
                    "game-performance-budget",
                    "unity-asset-guid-meta-audit",
                ],
                [
                    skill
                    for skill in (
                        "art-asset-pipeline-preflight",
                        "audio-content-pipeline-review",
                        "game-performance-budget",
                        "unity-asset-guid-meta-audit",
                    )
                    if skill in content_manifest["skills"]
                ],
            )
            self.assertEqual(
                [
                    "level-and-content-design-review",
                    "narrative-quest-content-contract",
                    "art-asset-pipeline-preflight",
                    "animation-rigging-import-audit",
                    "audio-content-pipeline-review",
                ],
                content_manifest["declared_skills"],
            )
```

- [ ] **Step 2: Run the focused test and confirm the missing closure**

Run:

```text
python -B -m unittest tests.packaging.test_packs_adapters.PackagingTests.test_pack_build_is_deterministic_and_generated -v
```

Expected: FAIL because `manifest.json` has no `declared_skills` and dependency skills are absent.

- [ ] **Step 3: Load both registries once and pass resolved skills into `_pack_plan`**

Import the resolver:

```python
try:
    from scripts.catalog_graph import resolve_pack_skill_closure
except ModuleNotFoundError:
    from catalog_graph import resolve_pack_skill_closure
```

Change `_pack_plan` to accept the full catalog:

```python
def _pack_plan(
    root_path: Path,
    pack: dict[str, Any],
    output_root: Path | str,
    *,
    packs: list[dict[str, Any]],
    capabilities: list[dict[str, Any]],
) -> tuple[Path, list[tuple[str, str]], dict[str, Any], _TreeSnapshot | None]:
    pack_id = _safe_component(pack.get("id"), "pack id")
    declared = pack.get("skills")
    if not isinstance(declared, list) or not declared:
        raise ValueError(f"pack {pack_id} must declare skills")
    declared_skills = [_safe_component(value, "pack skill") for value in declared]
    resolved_skills = resolve_pack_skill_closure(packs, capabilities, pack_id)
    source_roots = [_safe_skill_source(root_path, skill_name) for skill_name in resolved_skills]
```

Keep the existing generation loop but zip `resolved_skills` with `source_roots`. Replace the manifest skill fields with:

```python
        "declared_skills": declared_skills,
        "skills": resolved_skills,
```

Update `build_pack` and `build_all_packs`:

```python
def _catalog(root_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packs = load_yaml(root_path / "registry" / "packs.yaml").get("packs", [])
    capabilities = load_yaml(root_path / "registry" / "capabilities.yaml").get("capabilities", [])
    if not isinstance(packs, list) or not isinstance(capabilities, list):
        raise ValueError("pack and capability registries must contain lists")
    return packs, capabilities


def build_pack(root: Path | str, pack: dict[str, Any], output_root: Path | str) -> list[str]:
    root_path = Path(root).resolve()
    packs, capabilities = _catalog(root_path)
    return _publish_pack_plan(
        *_pack_plan(root_path, pack, output_root, packs=packs, capabilities=capabilities)
    )


def build_all_packs(root: Path | str, output_root: Path | str) -> dict[str, list[str]]:
    root_path = Path(root).resolve()
    packs, capabilities = _catalog(root_path)
    plans = [
        _pack_plan(root_path, pack, output_root, packs=packs, capabilities=capabilities)
        for pack in packs
    ]
    pack_ids = [str(plan[2]["pack"]) for plan in plans]
    if len(set(pack_ids)) != len(pack_ids):
        raise ValueError("pack registry contains duplicate pack ids")
    return {
        pack_id: _publish_pack_plan(*plan)
        for pack_id, plan in zip(pack_ids, plans)
    }
```

- [ ] **Step 4: Run packaging tests**

Run:

```text
python -B -m unittest tests.packaging.test_packs_adapters -v
```

Expected: all packaging tests PASS.

- [ ] **Step 5: Commit only after explicit maintainer authorization**

```text
git add scripts/build_packs.py tests/packaging/test_packs_adapters.py
git commit -m "feat: package transitive pack dependencies"
```

### Task 4: Enforce Scaffold Approval Parity

**Files:**
- Modify: `scripts/project_scaffold.py:297-312`
- Modify: `scripts/project_scaffold.py:441-463`
- Modify: `scripts/project_scaffold.py:609-627`
- Modify: `scripts/gamestudio_cli.py:29-105`
- Modify: `tests/studio_project_scaffold/test_project_scaffold.py:139-175`
- Modify: `tests/studio_project_scaffold/test_gamestudio_cli.py:33-59`

- [ ] **Step 1: Replace the direct-API success test with required-digest coverage**

Change the direct API test body to:

```python
    def test_apply_requires_reviewer_digest_and_nonoverlapping_backup(self) -> None:
        from scripts.project_scaffold import apply_scaffold, scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            report = scaffold_project(root)
            with self.assertRaisesRegex(ValueError, "reviewer"):
                apply_scaffold(
                    root,
                    reviewer="",
                    backup_root=root / ".scaffold-backup",
                    approved_plan_digest=report["plan_digest"],
                )
            with self.assertRaisesRegex(ValueError, "approved plan digest"):
                apply_scaffold(
                    root,
                    reviewer="Producer",
                    backup_root=root / ".scaffold-backup",
                    approved_plan_digest="",
                )
            with self.assertRaisesRegex(ValueError, "overlaps scaffold output"):
                apply_scaffold(
                    root,
                    reviewer="Producer",
                    backup_root=root / ".agents" / "backup",
                    approved_plan_digest=report["plan_digest"],
                )

            result = apply_scaffold(
                root,
                reviewer="Producer",
                backup_root=root / ".scaffold-backup",
                approved_plan_digest=report["plan_digest"],
            )

            self.assertEqual("PASS", result["status"])
            self.assertEqual("Producer", result["reviewer"])
```

- [ ] **Step 2: Run the test and confirm direct apply still accepts a missing digest**

Run:

```text
python -B -m unittest tests.studio_project_scaffold.test_project_scaffold.StudioProjectScaffoldTests.test_apply_requires_reviewer_digest_and_nonoverlapping_backup -v
```

Expected: FAIL because `approved_plan_digest` is optional and `.agents/backup` is not rejected before mutation.

- [ ] **Step 3: Add shared backup validation and require an exact digest**

Add before `apply_scaffold`:

```python
def _validate_scaffold_backup(
    root: Path,
    backup_root: Path | str,
    operations: list[dict[str, str]],
) -> Path:
    backup = Path(backup_root).resolve()
    try:
        backup.relative_to(root)
    except ValueError as error:
        raise ValueError("scaffold backup root must remain inside the project root") from error
    if backup == root:
        raise ValueError("scaffold backup root must be below the project root")
    for operation in operations:
        target = (root / operation["path"]).resolve()
        if target == backup or target in backup.parents or backup in target.parents:
            raise ValueError(
                f"scaffold backup root overlaps scaffold output: {operation['path']}"
            )
    return backup
```

Change the signature and guard:

```python
def apply_scaffold(
    root: Path | str,
    *,
    reviewer: str,
    backup_root: Path | str,
    approved_plan_digest: str,
    codegraph_runner: CommandRunner | None = None,
    codegraph_preference: str | None = None,
) -> dict[str, object]:
    if not reviewer.strip():
        raise ValueError("reviewer is required for scaffold apply")
    if not approved_plan_digest.strip():
        raise ValueError("approved plan digest is required for scaffold apply")
    root_path = Path(root).resolve()
    operations, preserved, profile, skill_plan, agent_plan = _scaffold_operations(root_path)
    mutation_report = report_mutation(root_path, operations)
    plan_digest = _plan_digest(mutation_report)
    if approved_plan_digest.strip() != plan_digest:
        raise ValueError("scaffold plan changed since report; review the new plan digest")
    backup_path = _validate_scaffold_backup(root_path, backup_root, operations)
    manifest_path = apply_mutation(
        root_path,
        operations,
        backup_path,
        expected_operations=mutation_report["operations"],
    )
```

- [ ] **Step 4: Require `--plan-digest` in the standalone scaffold CLI**

Add:

```python
    parser.add_argument("--plan-digest")
```

Replace the apply guard and call:

```python
    if args.apply:
        if not args.reviewer or not args.backup_root or not args.plan_digest:
            parser.error("--apply requires --reviewer, --backup-root, and --plan-digest")
        report = apply_scaffold(
            Path(args.root),
            reviewer=args.reviewer,
            backup_root=Path(args.backup_root),
            approved_plan_digest=args.plan_digest,
        )
```

The primary `gamestudio` CLI already requires all three values. Keep its call signature unchanged and add a regression assertion that it passes `approved_plan_digest` to the shared API.

- [ ] **Step 5: Run scaffold and CLI tests**

Run:

```text
python -B -m unittest tests.studio_project_scaffold.test_project_scaffold tests.studio_project_scaffold.test_gamestudio_cli -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add scripts/project_scaffold.py scripts/gamestudio_cli.py tests/studio_project_scaffold/test_project_scaffold.py tests/studio_project_scaffold/test_gamestudio_cli.py
git commit -m "fix: enforce scaffold approval parity"
```

### Task 5: Extend the Project Profile with UX Defaults

**Files:**
- Modify: `scripts/project_profile.py:14-42`
- Modify: `scripts/project_profile.py:143-220`
- Modify: `scripts/project_scaffold.py:140-174`
- Modify: `tests/project_profile/test_project_profile.py`

- [ ] **Step 1: Add backward-compatibility and strict-field tests**

Append to `ProjectProfileTests`:

```python
    def test_accepts_optional_studio_experience_defaults(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["studio_experience"] = {
            "default_role": "developer",
            "preferred_mode": "basic",
            "enabled_intents": [
                "diagnose",
                "verify",
                "plan-change",
                "ship",
                "handle-incident",
            ],
        }

        self.assertEqual([], validate_project_profile(profile))

    def test_rejects_invalid_studio_experience_values(self) -> None:
        from scripts.project_profile import validate_project_profile

        profile = self.valid_profile()
        profile["studio_experience"] = {
            "default_role": "administrator",
            "preferred_mode": "hidden",
            "enabled_intents": ["diagnose", "deploy-now"],
        }

        errors = validate_project_profile(profile)
        self.assertIn("studio experience default_role must be developer, liveops, producer, or qa", errors)
        self.assertIn("studio experience preferred_mode must be advanced or basic", errors)
        self.assertIn("unknown studio experience intent: deploy-now", errors)

    def test_profile_without_studio_experience_remains_valid(self) -> None:
        from scripts.project_profile import validate_project_profile

        self.assertEqual([], validate_project_profile(self.valid_profile()))
```

- [ ] **Step 2: Run the tests and confirm the top-level field is rejected**

Run:

```text
python -B -m unittest tests.project_profile.test_project_profile.ProjectProfileTests.test_accepts_optional_studio_experience_defaults tests.project_profile.test_project_profile.ProjectProfileTests.test_rejects_invalid_studio_experience_values -v
```

Expected: FAIL with `unknown project profile fields: studio_experience`.

- [ ] **Step 3: Add strict profile constants and validation**

Update the constants:

```python
PROFILE_TOP_LEVEL_FIELDS = {
    "schema_version",
    "workspace",
    "repositories",
    "exclusions",
    "agents",
    "cross_project_contracts",
    "studio_experience",
}
STUDIO_EXPERIENCE_FIELDS = {"default_role", "preferred_mode", "enabled_intents"}
STUDIO_ROLES = {"developer", "qa", "producer", "liveops"}
STUDIO_MODES = {"basic", "advanced"}
STUDIO_INTENTS = {"diagnose", "verify", "plan-change", "ship", "handle-incident"}
```

After workspace validation, add:

```python
    experience = profile.get("studio_experience")
    if experience is not None:
        if not isinstance(experience, dict):
            errors.append("studio_experience must be a mapping")
        else:
            unknown_experience = _unknown_fields(experience, STUDIO_EXPERIENCE_FIELDS)
            if unknown_experience:
                errors.append(
                    f"unknown studio experience fields: {', '.join(unknown_experience)}"
                )
            if experience.get("default_role") not in STUDIO_ROLES:
                errors.append(
                    "studio experience default_role must be developer, liveops, producer, or qa"
                )
            if experience.get("preferred_mode") not in STUDIO_MODES:
                errors.append("studio experience preferred_mode must be advanced or basic")
            intents = experience.get("enabled_intents")
            if not isinstance(intents, list) or not intents:
                errors.append("studio experience enabled_intents must be a non-empty list")
            else:
                if len(set(str(value) for value in intents)) != len(intents):
                    errors.append("studio experience enabled_intents must be unique")
                for intent in intents:
                    if intent not in STUDIO_INTENTS:
                        errors.append(f"unknown studio experience intent: {intent}")
```

- [ ] **Step 4: Include defaults in newly drafted profiles**

Add to the return value of `draft_project_profile`:

```python
        "studio_experience": {
            "default_role": "developer",
            "preferred_mode": "basic",
            "enabled_intents": [
                "diagnose",
                "verify",
                "plan-change",
                "ship",
                "handle-incident",
            ],
        },
```

- [ ] **Step 5: Run profile and scaffold tests**

Run:

```text
python -B -m unittest tests.project_profile.test_project_profile tests.studio_project_scaffold.test_project_scaffold -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add scripts/project_profile.py scripts/project_scaffold.py tests/project_profile/test_project_profile.py
git commit -m "feat: add studio experience profile defaults"
```

### Task 6: Add Strict Task Packet and Evidence Card Schemas

**Files:**
- Create: `evals/schema/studio-task-packet.schema.json`
- Create: `evals/schema/studio-evidence-card.schema.json`
- Create: `tests/evals/test_studio_experience_schemas.py`
- Modify: `registry/skill-resources.yaml`

- [ ] **Step 1: Write schema contract tests first**

Create `tests/evals/test_studio_experience_schemas.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema


class StudioExperienceSchemaTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def schema(self, name: str) -> dict[str, object]:
        return json.loads((self.ROOT / "evals" / "schema" / name).read_text(encoding="utf-8"))

    def test_task_packet_requires_route_risk_and_next_action(self) -> None:
        payload = {
            "schema_version": 1,
            "status": "READY",
            "role": "developer",
            "intent": "diagnose",
            "mode": "basic",
            "golden_path": "unity-client-entry-recovery",
            "selected_workflow": "unity-client-offline-debugging",
            "candidates": ["unity-client-entry-recovery"],
            "questions": [],
            "risk_level": "read-only",
            "prerequisites": [],
            "next_action": "Run the selected workflow read-only.",
        }
        jsonschema.validate(payload, self.schema("studio-task-packet.schema.json"))

    def test_evidence_card_separates_labels_and_command_evidence(self) -> None:
        payload = {
            "schema_version": 1,
            "verdict": "BLOCKED",
            "workflow": "unity-client-offline-debugging",
            "verified": [],
            "snapshot": ["Unity project profile selected"],
            "unverified": [],
            "blocked": ["Unity Editor is unavailable"],
            "commands": [],
            "artifacts": [],
            "restore": None,
            "next_action": "Open the project in the supported Unity Editor version.",
        }
        jsonschema.validate(payload, self.schema("studio-evidence-card.schema.json"))
```

- [ ] **Step 2: Run the tests and confirm both schemas are missing**

Run:

```text
python -B -m unittest tests.evals.test_studio_experience_schemas -v
```

Expected: FAIL with `FileNotFoundError` for `studio-task-packet.schema.json`.

- [ ] **Step 3: Create the strict task packet schema**

Create `evals/schema/studio-task-packet.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://gamestudio-codexkit.local/schema/studio-task-packet.schema.json",
  "title": "GameStudio role-aware task packet",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "status", "role", "intent", "mode", "golden_path", "selected_workflow", "candidates", "questions", "risk_level", "prerequisites", "next_action"],
  "properties": {
    "schema_version": {"const": 1},
    "status": {"enum": ["READY", "AMBIGUOUS", "BLOCKED"]},
    "role": {"enum": ["developer", "qa", "producer", "liveops"]},
    "intent": {"enum": ["diagnose", "verify", "plan-change", "ship", "handle-incident"]},
    "mode": {"enum": ["basic", "advanced"]},
    "golden_path": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
    "selected_workflow": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
    "candidates": {"type": "array", "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"}},
    "questions": {"type": "array", "maxItems": 3, "items": {"type": "string", "minLength": 1}},
    "risk_level": {"enum": ["read-only", "low", "medium", "high"]},
    "prerequisites": {"type": "array", "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
    "next_action": {"type": "string", "minLength": 1}
  }
}
```

- [ ] **Step 4: Create the strict evidence card schema**

Create `evals/schema/studio-evidence-card.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://gamestudio-codexkit.local/schema/studio-evidence-card.schema.json",
  "title": "GameStudio normalized evidence card",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "verdict", "workflow", "verified", "snapshot", "unverified", "blocked", "commands", "artifacts", "restore", "next_action"],
  "properties": {
    "schema_version": {"const": 1},
    "verdict": {"enum": ["PASS", "FAIL", "BLOCKED"]},
    "workflow": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
    "verified": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "snapshot": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "unverified": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "blocked": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "commands": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["command", "exit_code"],
        "properties": {
          "command": {"type": "string", "minLength": 1},
          "exit_code": {"type": ["integer", "null"]}
        }
      }
    },
    "artifacts": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "restore": {"type": ["string", "null"]},
    "next_action": {"type": "string", "minLength": 1}
  }
}
```

- [ ] **Step 5: Bundle schemas with the root and scaffold skills**

Add to `registry/skill-resources.yaml` under `studio-project-scaffold`:

```yaml
  - source: evals/schema/studio-task-packet.schema.json
    destination: schemas/studio-task-packet.schema.json
  - source: evals/schema/studio-evidence-card.schema.json
    destination: schemas/studio-evidence-card.schema.json
```

Replace the `using-game-studio-skills` repository-only entry with bundled schema resources while leaving `doctor.py` repository-only:

```yaml
  using-game-studio-skills:
  - source: evals/schema/studio-task-packet.schema.json
    destination: schemas/studio-task-packet.schema.json
  - source: evals/schema/studio-evidence-card.schema.json
    destination: schemas/studio-evidence-card.schema.json
repository_only:
  using-game-studio-skills:
  - doctor.py
```

- [ ] **Step 6: Synchronize resources and run schema tests**

Run:

```text
python -B scripts/sync_skill_resources.py .
python -B -m unittest tests.evals.test_studio_experience_schemas tests.packaging.test_skill_resources -v
python -B scripts/sync_skill_resources.py . --check
```

Expected: synchronization writes only the declared generated schema copies; all tests PASS; the final check reports `0 generated file(s) already in sync`.

- [ ] **Step 7: Commit only after explicit maintainer authorization**

```text
git add evals/schema/studio-task-packet.schema.json evals/schema/studio-evidence-card.schema.json tests/evals/test_studio_experience_schemas.py registry/skill-resources.yaml skills/using-game-studio-skills/schemas skills/studio-project-scaffold/schemas
git commit -m "feat: add studio experience evidence schemas"
```

### Task 7: Version, Documentation, and Full Verification

**Files:**
- Modify: `.codex-plugin/plugin.json:3`
- Modify: `pyproject.toml:7`
- Modify: `tests/packaging/test_codex_plugin.py`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/architecture/project-init-and-studio-expansion.md`
- Modify: `skills/studio-project-scaffold/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update distributed behavior documentation**

Add these maintained statements:

```markdown
- Generated pack artifacts include the transitive skills from declared pack dependencies and fail validation when a capability dependency is unavailable.
- Every scaffold apply entry point requires the same reviewer, project-local non-overlapping backup root, and approved plan digest.
- New project profiles may include optional `studio_experience` role, mode, and intent defaults; these fields affect presentation only and never grant mutation authority.
```

Update the scaffold skill verification checklist with:

```markdown
- [ ] Direct API, standalone script, and `gamestudio init --apply` all received the same approved plan digest.
- [ ] The backup root is project-local and does not overlap any proposed scaffold output.
```

- [ ] **Step 2: Patch-version the distributed plugin**

Change both version declarations from `1.5.3` to `1.5.4`:

```json
"version": "1.5.4"
```

```toml
version = "1.5.4"
```

In `CodexPluginPackagingTests.test_root_manifest_packages_the_canonical_skill_catalog`, change:

```python
        self.assertEqual("1.5.4", manifest["version"])
```

- [ ] **Step 3: Run focused verification**

Run:

```text
python -B -m unittest tests.governance.test_pack_dependency_closure tests.packaging.test_packs_adapters tests.packaging.test_codex_plugin tests.project_profile.test_project_profile tests.studio_project_scaffold.test_project_scaffold tests.studio_project_scaffold.test_gamestudio_cli tests.evals.test_studio_experience_schemas -v
python -B scripts/sync_skill_resources.py . --check
```

Expected: all focused tests PASS and generated resources are in sync.

- [ ] **Step 4: Run every repository gate**

Run:

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

Expected: every command exits `0`. If the current long-lived Windows checkout alone fails the promotion artifact raw-byte hash while a fresh clone passes, record the worktree normalization issue as a separate blocker; do not report the repository gate as PASS for that checkout.

- [ ] **Step 5: Inspect distribution impact**

Run:

```text
git diff -- .codex-plugin/plugin.json pyproject.toml registry/skill-resources.yaml registry/packs.yaml skills/ docs/ tests/ scripts/ evals/schema/
```

Expected: no generated file was hand-edited, internal maintenance IDs did not enter the distributed catalog, and only the intended schemas/helpers were synchronized.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add .codex-plugin/plugin.json pyproject.toml tests/packaging/test_codex_plugin.py README.md docs/architecture skills/studio-project-scaffold/SKILL.md
git commit -m "release: prepare dependency-safe scaffold foundation"
```
