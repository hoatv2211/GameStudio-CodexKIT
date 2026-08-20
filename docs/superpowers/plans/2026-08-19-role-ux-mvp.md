# Role UX MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver role-aware Basic and Advanced task packets for Developer, QA, Producer, and LiveOps users across the first four Unity/MMORPG Golden Paths.

**Architecture:** Add a pure `studio_experience` planner that combines profile defaults, explicit role/intent inputs, project subsystems, and available skills. Expose it through the root skill and a report-only `gamestudio guide` command. Keep canonical skills as the execution authority; the UX module only selects and normalizes routes and evidence.

**Tech Stack:** Python 3.11, PyYAML, standard-library `unittest`, existing JSON schemas from the Golden Paths Foundations plan.

---

## Prerequisite

Complete `docs/superpowers/plans/2026-08-19-golden-paths-foundations.md` first. This plan assumes pack closure, scaffold approval parity, `studio_experience` profile fields, and both normalized schemas are present and passing.

## File Map

- Create `scripts/studio_experience.py`: pure Golden Path selection and evidence-card normalization.
- Create `tests/studio_experience/__init__.py`: test package marker.
- Create `tests/studio_experience/test_studio_experience.py`: role, intent, ambiguity, and evidence tests.
- Modify `scripts/gamestudio_cli.py`: add report-only `guide` command.
- Modify `tests/studio_project_scaffold/test_gamestudio_cli.py`: CLI guide coverage.
- Modify `skills/using-game-studio-skills/SKILL.md`: role/intent/mode routing contract.
- Modify `skills/studio-project-scaffold/SKILL.md`: generated profile and guide documentation.
- Modify `registry/skill-resources.yaml`: bundle the planner with root and scaffold skills.
- Modify `evals/routing/studio-project-intake.json`: Producer plan-change prompts.
- Modify `evals/routing/multi-service-local-environment-doctor.json`: LiveOps and Developer prompts.
- Modify `evals/routing/unity-client-offline-debugging.json`: Developer and QA prompts.
- Modify `evals/routing/cpp-server-crash-triage.json`: Developer and LiveOps prompts.
- Create `evals/behavior/role-ux-golden-paths.json`: normalized artifact behavior cases.
- Modify `README.md`: role-first quick-start documentation.
- Modify `docs/index.html` and `docs/assets/banner.svg`: keep public routing totals synchronized at 280.
- Modify `.codex-plugin/plugin.json` and `pyproject.toml`: minor-version the new distributed UX.
- Modify `tests/packaging/test_codex_plugin.py`: update the exact manifest-version assertion.

### Task 1: Build the Pure Golden Path Planner

**Files:**
- Create: `scripts/studio_experience.py`
- Create: `tests/studio_experience/__init__.py`
- Create: `tests/studio_experience/test_studio_experience.py`

- [ ] **Step 1: Create the test package marker**

Create an empty `tests/studio_experience/__init__.py`.

- [ ] **Step 2: Write failing planner tests**

Create `tests/studio_experience/test_studio_experience.py`:

```python
from __future__ import annotations

import unittest


class StudioExperienceTests(unittest.TestCase):
    def profile(self, *subsystems: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "workspace": {"name": "sample", "root_git": True, "default_concurrency": 1},
            "repositories": [
                {
                    "id": "workspace",
                    "path": ".",
                    "git_root": True,
                    "subsystems": list(subsystems),
                    "owner_skill": "studio-project-intake",
                    "validation": [],
                }
            ],
            "exclusions": [],
            "agents": {"specialists": []},
            "cross_project_contracts": [],
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
        }

    def test_selects_project_adoption_for_producer_plan_change(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity"),
            role="producer",
            intent="plan-change",
            available_skills={"studio-project-intake"},
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("project-adoption-routing", packet["golden_path"])
        self.assertEqual("studio-project-intake", packet["selected_workflow"])

    def test_returns_one_question_for_ambiguous_server_diagnosis(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "cpp"),
            role="developer",
            intent="diagnose",
            available_skills={
                "multi-service-local-environment-doctor",
                "cpp-server-crash-triage",
            },
        )

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(
            ["cpp-server-failure-recovery", "local-environment-recovery"],
            packet["candidates"],
        )
        self.assertEqual(1, len(packet["questions"]))

    def test_explicit_golden_path_resolves_ambiguity(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "cpp"),
            role="developer",
            intent="diagnose",
            requested_golden_path="cpp-server-failure-recovery",
            available_skills={
                "multi-service-local-environment-doctor",
                "cpp-server-crash-triage",
            },
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("cpp-server-crash-triage", packet["selected_workflow"])

    def test_blocks_when_the_selected_workflow_is_not_installed(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity"),
            role="qa",
            intent="diagnose",
            requested_golden_path="unity-client-entry-recovery",
            available_skills={"studio-project-intake"},
        )

        self.assertEqual("BLOCKED", packet["status"])
        self.assertIn("unity-client-offline-debugging", packet["prerequisites"][0])

    def test_profile_defaults_are_used_when_role_and_mode_are_omitted(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity"),
            intent="diagnose",
            requested_golden_path="unity-client-entry-recovery",
            available_skills={"unity-client-offline-debugging"},
        )

        self.assertEqual("developer", packet["role"])
        self.assertEqual("basic", packet["mode"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm the planner module is missing**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.studio_experience'`.

- [ ] **Step 4: Implement the first four Golden Paths**

Create `scripts/studio_experience.py`:

```python
from __future__ import annotations

from typing import Any, Iterable


ROLE_IDS = {"developer", "qa", "producer", "liveops"}
INTENT_IDS = {"diagnose", "verify", "plan-change", "ship", "handle-incident"}
MODE_IDS = {"basic", "advanced"}

GOLDEN_PATHS: tuple[dict[str, object], ...] = (
    {
        "id": "project-adoption-routing",
        "workflow": "studio-project-intake",
        "roles": frozenset(ROLE_IDS),
        "intents": frozenset({"plan-change"}),
        "subsystems": frozenset(),
        "risk_level": "read-only",
        "next_action": "Create the report-only project intake and repository routing packet.",
    },
    {
        "id": "local-environment-recovery",
        "workflow": "multi-service-local-environment-doctor",
        "roles": frozenset({"developer", "qa", "liveops"}),
        "intents": frozenset({"diagnose", "verify"}),
        "subsystems": frozenset({"server", "service", "services", "database"}),
        "risk_level": "read-only",
        "next_action": "Inspect processes, ports, configuration, and prerequisites without service control.",
    },
    {
        "id": "unity-client-entry-recovery",
        "workflow": "unity-client-offline-debugging",
        "roles": frozenset({"developer", "qa"}),
        "intents": frozenset({"diagnose"}),
        "subsystems": frozenset({"unity"}),
        "risk_level": "read-only",
        "next_action": "Trace login, bootstrap, disconnected fallback, local data, and scene entry.",
    },
    {
        "id": "cpp-server-failure-recovery",
        "workflow": "cpp-server-crash-triage",
        "roles": frozenset({"developer", "qa", "liveops"}),
        "intents": frozenset({"diagnose", "handle-incident"}),
        "subsystems": frozenset({"cpp", "server"}),
        "risk_level": "read-only",
        "next_action": "Bind the crash signature to the exact build and rank the next diagnostics.",
    },
)


def _profile_subsystems(profile: dict[str, Any]) -> set[str]:
    return {
        str(subsystem).casefold()
        for repository in profile.get("repositories", [])
        for subsystem in repository.get("subsystems", [])
    }


def _defaults(profile: dict[str, Any]) -> tuple[str, str, set[str]]:
    experience = profile.get("studio_experience", {})
    role = str(experience.get("default_role", "developer"))
    mode = str(experience.get("preferred_mode", "basic"))
    enabled = {
        str(value) for value in experience.get("enabled_intents", sorted(INTENT_IDS))
    }
    return role, mode, enabled


def _packet(
    *,
    status: str,
    role: str,
    intent: str,
    mode: str,
    golden_path: str | None,
    selected_workflow: str | None,
    candidates: list[str],
    questions: list[str],
    risk_level: str,
    prerequisites: list[str],
    next_action: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "role": role,
        "intent": intent,
        "mode": mode,
        "golden_path": golden_path,
        "selected_workflow": selected_workflow,
        "candidates": candidates,
        "questions": questions,
        "risk_level": risk_level,
        "prerequisites": prerequisites,
        "next_action": next_action,
    }


def plan_experience(
    profile: dict[str, Any],
    *,
    intent: str,
    role: str | None = None,
    mode: str | None = None,
    requested_golden_path: str | None = None,
    available_skills: Iterable[str] | None = None,
) -> dict[str, object]:
    default_role, default_mode, enabled_intents = _defaults(profile)
    selected_role = role or default_role
    selected_mode = mode or default_mode
    if selected_role not in ROLE_IDS:
        raise ValueError(f"unknown studio role: {selected_role}")
    if selected_mode not in MODE_IDS:
        raise ValueError(f"unknown studio mode: {selected_mode}")
    if intent not in INTENT_IDS or intent not in enabled_intents:
        raise ValueError(f"studio intent is not enabled: {intent}")

    subsystems = _profile_subsystems(profile)
    candidates = [
        path
        for path in GOLDEN_PATHS
        if selected_role in path["roles"]
        and intent in path["intents"]
        and (
            not path["subsystems"]
            or bool(subsystems.intersection(path["subsystems"]))
        )
    ]
    candidates.sort(key=lambda path: str(path["id"]))
    candidate_ids = [str(path["id"]) for path in candidates]

    if requested_golden_path is not None:
        candidates = [path for path in candidates if path["id"] == requested_golden_path]
        if not candidates:
            return _packet(
                status="BLOCKED",
                role=selected_role,
                intent=intent,
                mode=selected_mode,
                golden_path=requested_golden_path,
                selected_workflow=None,
                candidates=candidate_ids,
                questions=[],
                risk_level="read-only",
                prerequisites=[f"Golden Path is unavailable for this role, intent, or project: {requested_golden_path}"],
                next_action="Select one of the reported candidate Golden Paths.",
            )

    if not candidates:
        return _packet(
            status="BLOCKED",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=None,
            selected_workflow=None,
            candidates=candidate_ids,
            questions=[],
            risk_level="read-only",
            prerequisites=["No Golden Path matches the detected project evidence."],
            next_action="Run studio-project-intake or choose Advanced mode with an explicit workflow.",
        )
    if len(candidates) > 1:
        return _packet(
            status="AMBIGUOUS",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=None,
            selected_workflow=None,
            candidates=[str(path["id"]) for path in candidates],
            questions=["Is this a local environment problem or a build-bound server crash?"],
            risk_level="read-only",
            prerequisites=[],
            next_action="Choose one candidate Golden Path; no mutation is authorized.",
        )

    selected = candidates[0]
    workflow = str(selected["workflow"])
    installed = set(available_skills) if available_skills is not None else None
    if installed is not None and workflow not in installed:
        return _packet(
            status="BLOCKED",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=str(selected["id"]),
            selected_workflow=None,
            candidates=[str(selected["id"])],
            questions=[],
            risk_level=str(selected["risk_level"]),
            prerequisites=[f"Install the missing workflow capability: {workflow}"],
            next_action="Install the owning pack or the full GameStudio Codex Kit catalog.",
        )
    return _packet(
        status="READY",
        role=selected_role,
        intent=intent,
        mode=selected_mode,
        golden_path=str(selected["id"]),
        selected_workflow=workflow,
        candidates=[str(selected["id"])],
        questions=[],
        risk_level=str(selected["risk_level"]),
        prerequisites=[],
        next_action=str(selected["next_action"]),
    )
```

- [ ] **Step 5: Run planner and profile tests**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience tests.project_profile.test_project_profile -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add scripts/studio_experience.py tests/studio_experience
git commit -m "feat: add role-aware golden path planner"
```

### Task 2: Add Evidence Card Normalization

**Files:**
- Modify: `scripts/studio_experience.py`
- Modify: `tests/studio_experience/test_studio_experience.py`

- [ ] **Step 1: Add failing evidence-card tests**

Append:

```python
    def test_builds_blocked_evidence_card_without_fabricating_commands(self) -> None:
        from scripts.studio_experience import build_evidence_card

        card = build_evidence_card(
            workflow="unity-client-offline-debugging",
            verdict="BLOCKED",
            verified=[],
            snapshot=["Unity project profile selected"],
            unverified=[],
            blocked=["Unity Editor is unavailable"],
            commands=[],
            artifacts=[],
            restore=None,
            next_action="Open the project in the supported Unity Editor version.",
        )

        self.assertEqual("BLOCKED", card["verdict"])
        self.assertEqual([], card["commands"])

    def test_rejects_pass_without_verified_evidence(self) -> None:
        from scripts.studio_experience import build_evidence_card

        with self.assertRaisesRegex(ValueError, "PASS requires verified evidence"):
            build_evidence_card(
                workflow="cpp-server-crash-triage",
                verdict="PASS",
                verified=[],
                snapshot=[],
                unverified=[],
                blocked=[],
                commands=[{"command": "analyze-dump", "exit_code": 0}],
                artifacts=["crash-signature.json"],
                restore=None,
                next_action="Review the ranked hypotheses.",
            )
```

- [ ] **Step 2: Run the two tests and confirm the function is missing**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience.StudioExperienceTests.test_builds_blocked_evidence_card_without_fabricating_commands tests.studio_experience.test_studio_experience.StudioExperienceTests.test_rejects_pass_without_verified_evidence -v
```

Expected: FAIL with `ImportError: cannot import name 'build_evidence_card'`.

- [ ] **Step 3: Implement strict normalization**

Append to `scripts/studio_experience.py`:

```python
def build_evidence_card(
    *,
    workflow: str,
    verdict: str,
    verified: list[str],
    snapshot: list[str],
    unverified: list[str],
    blocked: list[str],
    commands: list[dict[str, object]],
    artifacts: list[str],
    restore: str | None,
    next_action: str,
) -> dict[str, object]:
    if verdict not in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError(f"unknown evidence verdict: {verdict}")
    if verdict == "PASS" and not verified:
        raise ValueError("PASS requires verified evidence")
    if verdict == "BLOCKED" and not blocked:
        raise ValueError("BLOCKED requires at least one blocker")
    for command in commands:
        if set(command) != {"command", "exit_code"}:
            raise ValueError("command evidence requires command and exit_code")
    return {
        "schema_version": 1,
        "verdict": verdict,
        "workflow": workflow,
        "verified": list(verified),
        "snapshot": list(snapshot),
        "unverified": list(unverified),
        "blocked": list(blocked),
        "commands": list(commands),
        "artifacts": list(artifacts),
        "restore": restore,
        "next_action": next_action,
    }
```

- [ ] **Step 4: Run the full module tests**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience tests.evals.test_studio_experience_schemas -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit only after explicit maintainer authorization**

```text
git add scripts/studio_experience.py tests/studio_experience/test_studio_experience.py
git commit -m "feat: normalize studio evidence cards"
```

### Task 3: Expose a Report-only `gamestudio guide` Command

**Files:**
- Modify: `scripts/gamestudio_cli.py`
- Modify: `tests/studio_project_scaffold/test_gamestudio_cli.py`

- [ ] **Step 1: Add failing CLI guide tests**

Append to `GameStudioCliTests`:

```python
    def test_guide_uses_profile_defaults_and_never_writes(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            profile = draft_project_profile(root)
            profile["repositories"][0]["subsystems"] = ["unity"]
            profile_path = root / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            import yaml
            profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "guide",
                    str(root),
                    "--intent",
                    "diagnose",
                    "--golden-path",
                    "unity-client-entry-recovery",
                ])

            packet = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("READY", packet["status"])
            self.assertEqual("developer", packet["role"])
            self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())

    def test_guide_reports_ambiguity_without_prompting(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            profile = draft_project_profile(root)
            profile["repositories"][0]["subsystems"] = ["server", "cpp"]
            profile_path = root / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            import yaml
            profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "guide", str(root), "--role", "developer", "--intent", "diagnose"
                ])

            packet = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("AMBIGUOUS", packet["status"])
            self.assertEqual(1, len(packet["questions"]))
```

- [ ] **Step 2: Run the tests and confirm `guide` is unknown**

Run:

```text
python -B -m unittest tests.studio_project_scaffold.test_gamestudio_cli.GameStudioCliTests.test_guide_uses_profile_defaults_and_never_writes tests.studio_project_scaffold.test_gamestudio_cli.GameStudioCliTests.test_guide_reports_ambiguity_without_prompting -v
```

Expected: FAIL with argparse reporting an invalid command choice.

- [ ] **Step 3: Add the guide parser**

Import the new dependencies in both package and standalone import branches:

```python
from scripts.project_profile import load_project_profile
from scripts.project_scaffold import draft_project_profile
from scripts.studio_experience import INTENT_IDS, MODE_IDS, ROLE_IDS, plan_experience
```

Add the parser before `status`:

```python
    guide = commands.add_parser("guide")
    guide.add_argument("root", nargs="?", default=".")
    guide.add_argument("--role", choices=sorted(ROLE_IDS))
    guide.add_argument("--intent", choices=sorted(INTENT_IDS), required=True)
    guide.add_argument("--mode", choices=sorted(MODE_IDS))
    guide.add_argument("--golden-path")
```

- [ ] **Step 4: Add report-only command handling**

Before the status branch, add:

```python
    if args.command == "guide":
        profile_path = root / ".agents" / "project-profile.yaml"
        profile = (
            load_project_profile(profile_path)
            if profile_path.is_file()
            else draft_project_profile(root)
        )
        report = plan_experience(
            profile,
            role=args.role,
            intent=args.intent,
            mode=args.mode,
            requested_golden_path=args.golden_path,
        )
        print(json.dumps(report, indent=2))
        return 0
```

This command must not call scaffold apply, create directories, or install missing capabilities.

- [ ] **Step 5: Run all CLI tests**

Run:

```text
python -B -m unittest tests.studio_project_scaffold.test_gamestudio_cli -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add scripts/gamestudio_cli.py tests/studio_project_scaffold/test_gamestudio_cli.py
git commit -m "feat: add report-only studio guide"
```

### Task 4: Route the Root Skill Through Role UX

**Files:**
- Modify: `skills/using-game-studio-skills/SKILL.md`
- Modify: `skills/studio-project-scaffold/SKILL.md`
- Modify: `registry/skill-resources.yaml`

- [ ] **Step 1: Update the root skill contract**

Replace the root skill workflow with the following numbered behavior while retaining its evidence and safety sections:

```markdown
1. Collect repository path, project profile, goal, constraints, available tools, do-not-touch paths, and any explicit role, intent, or mode.
   Completion criterion: a bounded request context exists and unknowns are labeled.
2. Use the project-profile `studio_experience` defaults when role or mode is absent. Infer one of `Diagnose`, `Verify`, `Plan Change`, `Ship`, or `Handle Incident` from the request; ask one question when the top Golden Paths remain ambiguous.
   Completion criterion: role, intent, mode, and candidate Golden Paths are explicit.
3. Select the narrowest canonical workflow. A role preset is advisory and cannot override repository evidence, missing capabilities, or risk gates.
   Completion criterion: the normalized task packet names the selected workflow or returns `BLOCKED` with the missing prerequisite.
4. Apply evidence and mutation contracts from the selected workflow without weakening them in Basic mode.
   Completion criterion: Basic and Advanced modes differ only in presentation and explicit controls.
5. Return the workflow-specific artifact plus the normalized evidence card and one recommended next action.
   Completion criterion: commands, exit codes, artifacts, limitations, restore information, and blockers remain available.
```

Update references:

```markdown
Use the bundled `scripts/studio_experience.py` planner and normalized schemas for role-aware task packets and evidence cards. The planner selects routes but never executes or authorizes the selected workflow.
```

- [ ] **Step 2: Update the scaffold skill contract**

Add to project-local output documentation:

```markdown
Newly generated profiles include optional `studio_experience` defaults for role, mode, and enabled intents. These defaults affect routing presentation only. Use `gamestudio guide` for a report-only Golden Path packet; `gamestudio init --apply` remains a separate reviewed mutation.
```

- [ ] **Step 3: Bundle the planner with both owning skills**

Add `studio_experience.py` to `using-game-studio-skills` and `studio-project-scaffold` under `registry/skill-resources.yaml`:

```yaml
  studio-project-scaffold:
  - studio_experience.py
```

```yaml
  using-game-studio-skills:
  - studio_experience.py
```

Retain both schema mappings introduced by the Foundations plan.

- [ ] **Step 4: Synchronize and verify resources**

Run:

```text
python -B scripts/sync_skill_resources.py .
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest tests.packaging.test_skill_resources -v
```

Expected: generated copies are updated from `scripts/studio_experience.py`; the final sync check and packaging tests PASS.

- [ ] **Step 5: Commit only after explicit maintainer authorization**

```text
git add skills/using-game-studio-skills skills/studio-project-scaffold registry/skill-resources.yaml
git commit -m "feat: route studio tasks through role UX"
```

### Task 5: Add Role-aware Routing and Behavior Evals

**Files:**
- Modify: `evals/routing/studio-project-intake.json`
- Modify: `evals/routing/multi-service-local-environment-doctor.json`
- Modify: `evals/routing/unity-client-offline-debugging.json`
- Modify: `evals/routing/cpp-server-crash-triage.json`
- Create: `evals/behavior/role-ux-golden-paths.json`

- [ ] **Step 1: Add role-first route cases**

Add these cases to their owning routing files, preserving valid JSON:

```json
{"prompt":"As producer, plan adoption of this Unity MMORPG repository before anyone writes files","expected_skill":"studio-project-intake","type":"positive"}
```

```json
{"prompt":"LiveOps diagnose local service ports and dependencies without restarting anything","expected_skill":"multi-service-local-environment-doctor","type":"positive"}
```

```json
{"prompt":"QA cần chẩn đoán Unity client không vào được offline mode trước khi chạy PlayMode","expected_skill":"unity-client-offline-debugging","type":"positive"}
```

```json
{"prompt":"Developer hãy phân tích crash signature của C++ game server đúng build, không restart service","expected_skill":"cpp-server-crash-triage","type":"positive"}
```

- [ ] **Step 2: Create behavior cases for normalized outputs**

Create `evals/behavior/role-ux-golden-paths.json`:

```json
{
  "cases": [
    {
      "id": "role-ux-project-adoption-packet",
      "prompt": "As producer, create a report-only project adoption packet with role, Plan Change intent, risk, selected workflow, prerequisites, and next action.",
      "target_skill": "studio-project-intake",
      "expected_verdict": "PASS",
      "allow_mutation": false,
      "required_artifact_fields": ["role", "intent", "risk_level", "selected_workflow", "next_action"]
    },
    {
      "id": "role-ux-local-environment-blocked",
      "prompt": "As LiveOps, diagnose the local environment but return BLOCKED with the missing prerequisite when process inspection is unavailable.",
      "target_skill": "multi-service-local-environment-doctor",
      "expected_verdict": "BLOCKED",
      "allow_mutation": false,
      "required_artifact_fields": ["role", "intent", "blocked", "next_action"]
    },
    {
      "id": "role-ux-unity-client-entry",
      "prompt": "As QA, diagnose Unity offline entry and return the workflow artifact plus a normalized evidence card.",
      "target_skill": "unity-client-offline-debugging",
      "expected_verdict": "PASS",
      "allow_mutation": false,
      "required_artifact_fields": ["selected_workflow", "verified", "snapshot", "unverified", "blocked"]
    },
    {
      "id": "role-ux-cpp-crash",
      "prompt": "As developer, diagnose a C++ server crash and preserve build identity, command evidence, artifacts, and one next action.",
      "target_skill": "cpp-server-crash-triage",
      "expected_verdict": "PASS",
      "allow_mutation": false,
      "required_artifact_fields": ["workflow", "commands", "artifacts", "next_action"]
    }
  ]
}
```

- [ ] **Step 3: Run deterministic routing and offline eval tests**

Run:

```text
python -B scripts/route_eval.py .
python -B -m unittest tests.evals.test_offline_evals tests._meta.test_route_eval -v
```

Expected: routing remains rank-1 PASS for every case and offline eval tests PASS.

- [ ] **Step 4: Commit only after explicit maintainer authorization**

```text
git add evals/routing evals/behavior/role-ux-golden-paths.json
git commit -m "test: add role-aware golden path evals"
```

### Task 6: Document and Release the Role UX MVP

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/architecture/project-init-and-studio-expansion.md`
- Modify: `docs/index.html`
- Modify: `docs/assets/banner.svg`
- Modify: `.codex-plugin/plugin.json`
- Modify: `pyproject.toml`
- Modify: `tests/packaging/test_codex_plugin.py`

- [ ] **Step 1: Add the role-first quick start**

Add a compact README section:

```markdown
## Role-first workflow

You do not need to remember skill names. State your role and outcome:

- Developer: "Diagnose why this Unity client cannot enter offline mode."
- QA: "Verify this Unity build and return artifact-bound evidence."
- Producer: "Plan this repository adoption without writing files."
- LiveOps: "Handle this incident without restarting services until approval."

The root router maps the request to `Diagnose`, `Verify`, `Plan Change`, `Ship`, or `Handle Incident`, then returns a report-only task packet. In a full repository clone, `gamestudio guide --intent <intent>` produces the same normalized planning view without executing the workflow.
```

- [ ] **Step 2: Document the architecture boundary**

Add to architecture documentation:

```markdown
Role UX is a presentation and selection layer over canonical skills. The pure planner reads project-profile defaults and detected subsystems, returns READY, AMBIGUOUS, or BLOCKED, and never performs the selected workflow. Basic mode reduces exposed controls; it does not reduce evidence or mutation requirements.
```

- [ ] **Step 3: Minor-version the distributed plugin**

Change both version declarations from `1.5.4` to `1.6.0`:

```json
"version": "1.6.0"
```

```toml
version = "1.6.0"
```

In `CodexPluginPackagingTests.test_root_manifest_packages_the_canonical_skill_catalog`, change:

```python
        self.assertEqual("1.6.0", manifest["version"])
```

Update maintained public routing totals from `276` to `280` in:

- `README.md`
- `docs/index.html`
- `docs/assets/banner.svg`

- [ ] **Step 4: Run focused verification**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience tests.studio_project_scaffold.test_gamestudio_cli tests.project_profile.test_project_profile tests.evals.test_studio_experience_schemas tests.evals.test_offline_evals tests.packaging.test_codex_plugin -v
python -B scripts/route_eval.py .
python -B scripts/sync_skill_resources.py . --check
```

Expected: all focused tests PASS, deterministic routing reports `280/280`, and public catalog surfaces match that total.

- [ ] **Step 5: Run every repository gate**

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

Expected: every command exits `0` with the same fresh-clone caveat documented in the Foundations plan for a stale Windows worktree.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add README.md docs/architecture docs/index.html docs/assets/banner.svg .codex-plugin/plugin.json pyproject.toml tests/packaging/test_codex_plugin.py
git commit -m "release: add role-aware studio UX"
```
