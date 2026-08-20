# Golden Paths Expansion and Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all eight Unity/MMORPG Golden Path families, add the missing governed dogfood coverage, and measure whether role-first studio UX reaches useful verdicts safely.

**Architecture:** Extend the pure Role UX planner from one-workflow routes to family-backed workflow candidates while keeping canonical skills as the execution authority. Add deterministic route and behavior fixtures for the remaining families, then evaluate governed adoption runs with a separate strict metrics tool. Reuse the existing dogfood evaluator for workflow evidence and keep absent runners or live projects explicitly `BLOCKED`.

**Tech Stack:** Python 3.11, PyYAML, jsonschema, standard-library `unittest`, JSON Schema 2020-12, existing routing and dogfood evaluators.

---

## Prerequisites

Complete these plans in order before starting this one:

1. `docs/superpowers/plans/2026-08-19-golden-paths-foundations.md`
2. `docs/superpowers/plans/2026-08-19-role-ux-mvp.md`

This plan assumes plugin version `1.6.0`, 280 deterministic routing cases, dependency-closed packs, approval parity, normalized task-packet and evidence-card schemas, and the first four Role UX routes are present and passing.

## File Map

- Modify `scripts/studio_experience.py`: represent all eight Golden Path families and expose workflow candidates without executing them.
- Modify `tests/studio_experience/test_studio_experience.py`: cover the four remaining families, ambiguity, Advanced override, missing capability, and Basic-mode safety.
- Modify `scripts/gamestudio_cli.py`: add the Advanced-only `--workflow` selector.
- Modify `tests/studio_project_scaffold/test_gamestudio_cli.py`: prove Basic mode rejects workflow override and Advanced mode remains report-only.
- Modify `evals/schema/studio-task-packet.schema.json`: add strict `workflow_candidates` output.
- Modify `tests/evals/test_studio_experience_schemas.py`: validate READY, AMBIGUOUS, and BLOCKED packets with workflow candidates.
- Modify ten `evals/routing/*.json` files: add role-and-intent routes for the remaining Golden Path workflows.
- Modify `evals/behavior/role-ux-golden-paths.json`: add normalized behavior cases for Phase 2 families.
- Modify `evals/dogfood/game-studio-scenarios.json`: add GUID/meta, server-authority, and save-migration governed scenarios.
- Modify `evals/schema/dogfood-case.schema.json`: permit the expanded 15-case governed pack.
- Modify `tests/evals/test_dogfood_eval.py`: lock the 15-case count and promotion-summary coverage.
- Modify `docs/authoring/dogfood.md`: document the expanded scenario pack.
- Create `evals/adoption/studio-role-golden-paths.json`: maintained adoption benchmark across all roles, intents, languages, and families.
- Create `evals/schema/studio-adoption-result.schema.json`: strict governed adoption-result wrapper.
- Create `scripts/studio_adoption_eval.py`: report-only adoption metrics evaluator.
- Create `tests/evals/test_studio_adoption_eval.py`: evaluator, schema, threshold, and BLOCKED tests.
- Modify five `personas/*/PERSONA.md` files: align persona lenses with the canonical routes already declared in `registry/personas.yaml`.
- Modify `README.md`, `docs/architecture/overview.md`, `docs/architecture/project-init-and-studio-expansion.md`, and `docs/index.html`: document eight Golden Paths, role/persona boundaries, 15 dogfood cases, and adoption commands.
- Modify `docs/assets/banner.svg`: update the deterministic routing total to 290.
- Modify `.codex-plugin/plugin.json`, `pyproject.toml`, and `tests/packaging/test_codex_plugin.py`: minor-version the completed Golden Path and adoption feature to `1.7.0`.

### Task 1: Expand the Planner to Eight Multi-workflow Golden Paths

**Files:**
- Modify: `scripts/studio_experience.py`
- Modify: `tests/studio_experience/test_studio_experience.py`
- Modify: `evals/schema/studio-task-packet.schema.json`
- Modify: `tests/evals/test_studio_experience_schemas.py`

- [ ] **Step 1: Add failing Phase 2 planner tests**

Append these methods to `StudioExperienceTests` in `tests/studio_experience/test_studio_experience.py`:

```python
    def test_reports_workflow_candidates_for_unity_ui_and_localization(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity", "ui", "localization"),
            role="qa",
            intent="verify",
            requested_golden_path="unity-ui-localization",
            available_skills={
                "unity-ui-rendering-debugging",
                "localization-authority-audit",
            },
        )

        self.assertEqual("AMBIGUOUS", packet["status"])
        self.assertEqual(["unity-ui-localization"], packet["candidates"])
        self.assertEqual(
            ["localization-authority-audit", "unity-ui-rendering-debugging"],
            packet["workflow_candidates"],
        )
        self.assertEqual(1, len(packet["questions"]))

    def test_advanced_override_selects_guid_meta_integrity(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("unity", "assets"),
            role="qa",
            intent="verify",
            mode="advanced",
            requested_golden_path="unity-build-asset-integrity",
            requested_workflow="unity-asset-guid-meta-audit",
            available_skills={
                "unity-asset-guid-meta-audit",
                "unity-batchmode-build-verification",
            },
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("unity-build-asset-integrity", packet["golden_path"])
        self.assertEqual("unity-asset-guid-meta-audit", packet["selected_workflow"])

    def test_basic_mode_rejects_explicit_workflow_override(self) -> None:
        from scripts.studio_experience import plan_experience

        with self.assertRaisesRegex(ValueError, "workflow override requires advanced mode"):
            plan_experience(
                self.profile("unity", "assets"),
                role="qa",
                intent="verify",
                mode="basic",
                requested_golden_path="unity-build-asset-integrity",
                requested_workflow="unity-asset-guid-meta-audit",
            )

    def test_selects_liveops_incident_without_competing_data_routes(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "database", "liveops"),
            role="liveops",
            intent="handle-incident",
            available_skills={"liveops-incident-response"},
        )

        self.assertEqual("READY", packet["status"])
        self.assertEqual("data-live-release-safety", packet["golden_path"])
        self.assertEqual("liveops-incident-response", packet["selected_workflow"])

    def test_blocks_advanced_override_when_capability_is_missing(self) -> None:
        from scripts.studio_experience import plan_experience

        packet = plan_experience(
            self.profile("server", "lua", "network"),
            role="developer",
            intent="verify",
            mode="advanced",
            requested_golden_path="lua-contract-server-authority",
            requested_workflow="network-authority-and-exploit-review",
            available_skills={"lua-client-server-contract-audit"},
        )

        self.assertEqual("BLOCKED", packet["status"])
        self.assertEqual([], packet["workflow_candidates"])
        self.assertIn("network-authority-and-exploit-review", packet["prerequisites"][0])
```

- [ ] **Step 2: Add the failing schema expectation**

In the READY task-packet fixture in `tests/evals/test_studio_experience_schemas.py`, add:

```python
            "workflow_candidates": ["unity-client-offline-debugging"],
```

Add this test to `StudioExperienceSchemaTests`:

```python
    def test_ambiguous_packet_requires_workflow_candidates(self) -> None:
        payload = {
            "schema_version": 1,
            "status": "AMBIGUOUS",
            "role": "qa",
            "intent": "verify",
            "mode": "basic",
            "golden_path": "unity-ui-localization",
            "selected_workflow": None,
            "candidates": ["unity-ui-localization"],
            "workflow_candidates": [
                "localization-authority-audit",
                "unity-ui-rendering-debugging",
            ],
            "questions": ["Is the failing evidence visual rendering or localization authority?"],
            "risk_level": "read-only",
            "prerequisites": [],
            "next_action": "Choose one canonical workflow; no mutation is authorized.",
        }

        jsonschema.validate(payload, self.schema("studio-task-packet.schema.json"))
```

- [ ] **Step 3: Run the focused tests and verify the new contract fails**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience tests.evals.test_studio_experience_schemas -v
```

Expected: FAIL because `plan_experience` does not accept `requested_workflow`, Phase 2 families are absent, and the schema rejects `workflow_candidates`.

- [ ] **Step 4: Replace the one-workflow route table**

In `scripts/studio_experience.py`, replace `GOLDEN_PATHS` with this complete family-backed route table:

```python
GOLDEN_PATH_ROUTES: tuple[dict[str, object], ...] = (
    {
        "family": "project-adoption-routing",
        "workflow": "studio-project-intake",
        "roles": frozenset(ROLE_IDS),
        "intents": frozenset({"plan-change"}),
        "subsystems": frozenset(),
        "risk_level": "read-only",
        "next_action": "Create the report-only project intake and repository routing packet.",
    },
    {
        "family": "local-environment-recovery",
        "workflow": "multi-service-local-environment-doctor",
        "roles": frozenset({"developer", "qa", "liveops"}),
        "intents": frozenset({"diagnose", "verify"}),
        "subsystems": frozenset({"server", "service", "services", "database"}),
        "risk_level": "read-only",
        "next_action": "Inspect processes, ports, configuration, and prerequisites without service control.",
    },
    {
        "family": "unity-client-entry-recovery",
        "workflow": "unity-client-offline-debugging",
        "roles": frozenset({"developer", "qa"}),
        "intents": frozenset({"diagnose"}),
        "subsystems": frozenset({"unity"}),
        "risk_level": "read-only",
        "next_action": "Trace login, bootstrap, disconnected fallback, local data, and scene entry.",
    },
    {
        "family": "cpp-server-failure-recovery",
        "workflow": "cpp-server-crash-triage",
        "roles": frozenset({"developer", "qa", "liveops"}),
        "intents": frozenset({"diagnose", "handle-incident"}),
        "subsystems": frozenset({"cpp", "server"}),
        "risk_level": "read-only",
        "next_action": "Bind the crash signature to the exact build and rank the next diagnostics.",
    },
    {
        "family": "cpp-server-failure-recovery",
        "workflow": "mmorpg-packet-protocol-review",
        "roles": frozenset({"developer", "qa"}),
        "intents": frozenset({"diagnose", "verify"}),
        "subsystems": frozenset({"cpp", "server", "network"}),
        "risk_level": "read-only",
        "next_action": "Compare packet versions, directions, opcodes, fields, and response contracts.",
    },
    {
        "family": "unity-ui-localization",
        "workflow": "unity-ui-rendering-debugging",
        "roles": frozenset({"developer", "qa"}),
        "intents": frozenset({"diagnose", "verify"}),
        "subsystems": frozenset({"unity", "ui"}),
        "risk_level": "read-only",
        "next_action": "Trace the render chain, canvas or panel ordering, clipping, and runtime evidence.",
    },
    {
        "family": "unity-ui-localization",
        "workflow": "localization-authority-audit",
        "roles": frozenset({"developer", "qa", "producer"}),
        "intents": frozenset({"diagnose", "verify", "plan-change"}),
        "subsystems": frozenset({"unity", "localization"}),
        "risk_level": "read-only",
        "next_action": "Identify the localization source of truth, generated copies, and runtime limitations.",
    },
    {
        "family": "unity-build-asset-integrity",
        "workflow": "unity-batchmode-build-verification",
        "roles": frozenset({"developer", "qa", "producer"}),
        "intents": frozenset({"verify", "ship"}),
        "subsystems": frozenset({"unity", "build"}),
        "risk_level": "read-only",
        "next_action": "Bind the batch command, Editor log, settings, and output artifact to one verdict.",
    },
    {
        "family": "unity-build-asset-integrity",
        "workflow": "unity-asset-guid-meta-audit",
        "roles": frozenset({"developer", "qa"}),
        "intents": frozenset({"diagnose", "verify"}),
        "subsystems": frozenset({"unity", "assets"}),
        "risk_level": "read-only",
        "next_action": "Audit duplicate GUIDs, missing meta files, stale references, and import-state limits.",
    },
    {
        "family": "lua-contract-server-authority",
        "workflow": "lua-client-server-contract-audit",
        "roles": frozenset({"developer", "qa"}),
        "intents": frozenset({"diagnose", "verify"}),
        "subsystems": frozenset({"lua", "server", "network"}),
        "risk_level": "read-only",
        "next_action": "Map normalized Lua fields and handlers across the client and server copies.",
    },
    {
        "family": "lua-contract-server-authority",
        "workflow": "network-authority-and-exploit-review",
        "roles": frozenset({"developer", "qa", "liveops"}),
        "intents": frozenset({"diagnose", "verify", "handle-incident"}),
        "subsystems": frozenset({"server", "network", "security"}),
        "risk_level": "read-only",
        "next_action": "Trace sensitive actions to exact server validation, authority, and rate-limit guards.",
    },
    {
        "family": "data-live-release-safety",
        "workflow": "game-database-migration-safety",
        "roles": frozenset({"developer", "qa", "producer", "liveops"}),
        "intents": frozenset({"plan-change"}),
        "subsystems": frozenset({"database", "server"}),
        "risk_level": "medium",
        "next_action": "Produce the isolated dry-run, backup, restore, reviewer, and approval plan.",
    },
    {
        "family": "data-live-release-safety",
        "workflow": "save-data-schema-migration",
        "roles": frozenset({"developer", "qa", "producer"}),
        "intents": frozenset({"plan-change"}),
        "subsystems": frozenset({"save", "data", "server"}),
        "risk_level": "medium",
        "next_action": "Plan versioned fixture conversion, rollback preservation, and unknown-version blocking.",
    },
    {
        "family": "data-live-release-safety",
        "workflow": "release-candidate-preflight",
        "roles": frozenset({"qa", "producer", "liveops"}),
        "intents": frozenset({"ship"}),
        "subsystems": frozenset(),
        "risk_level": "read-only",
        "next_action": "Bind the candidate identity, required artifacts, blockers, and go or no-go decision.",
    },
    {
        "family": "data-live-release-safety",
        "workflow": "liveops-incident-response",
        "roles": frozenset({"producer", "liveops"}),
        "intents": frozenset({"handle-incident"}),
        "subsystems": frozenset(),
        "risk_level": "high",
        "next_action": "Establish incident state, mitigation boundary, rollback, approval, and monitoring.",
    },
)
```

- [ ] **Step 5: Replace packet selection with family and workflow selection**

Replace `_packet` with this exact signature and return value:

```python
def _packet(
    *,
    status: str,
    role: str,
    intent: str,
    mode: str,
    golden_path: str | None,
    selected_workflow: str | None,
    candidates: list[str],
    workflow_candidates: list[str],
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
        "workflow_candidates": workflow_candidates,
        "questions": questions,
        "risk_level": risk_level,
        "prerequisites": prerequisites,
        "next_action": next_action,
    }
```

Replace `plan_experience` with this implementation:

```python
def plan_experience(
    profile: dict[str, Any],
    *,
    intent: str,
    role: str | None = None,
    mode: str | None = None,
    requested_golden_path: str | None = None,
    requested_workflow: str | None = None,
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
    if requested_workflow is not None and selected_mode != "advanced":
        raise ValueError("workflow override requires advanced mode")

    subsystems = _profile_subsystems(profile)
    routes = [
        route
        for route in GOLDEN_PATH_ROUTES
        if selected_role in route["roles"]
        and intent in route["intents"]
        and (
            not route["subsystems"]
            or bool(subsystems.intersection(route["subsystems"]))
        )
    ]
    family_ids = sorted({str(route["family"]) for route in routes})
    if requested_golden_path is not None:
        routes = [route for route in routes if route["family"] == requested_golden_path]
        if not routes:
            return _packet(
                status="BLOCKED",
                role=selected_role,
                intent=intent,
                mode=selected_mode,
                golden_path=requested_golden_path,
                selected_workflow=None,
                candidates=family_ids,
                workflow_candidates=[],
                questions=[],
                risk_level="read-only",
                prerequisites=[f"Golden Path is unavailable for this role, intent, or project: {requested_golden_path}"],
                next_action="Select one of the reported candidate Golden Paths.",
            )

    if requested_workflow is not None:
        matching = [route for route in routes if route["workflow"] == requested_workflow]
        if not matching:
            return _packet(
                status="BLOCKED",
                role=selected_role,
                intent=intent,
                mode=selected_mode,
                golden_path=requested_golden_path,
                selected_workflow=None,
                candidates=sorted({str(route["family"]) for route in routes}),
                workflow_candidates=sorted(str(route["workflow"]) for route in routes),
                questions=[],
                risk_level="read-only",
                prerequisites=[f"Workflow is unavailable for the selected Golden Path: {requested_workflow}"],
                next_action="Choose one of the reported workflow candidates.",
            )
        routes = matching

    if not routes:
        return _packet(
            status="BLOCKED",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=None,
            selected_workflow=None,
            candidates=family_ids,
            workflow_candidates=[],
            questions=[],
            risk_level="read-only",
            prerequisites=["No Golden Path matches the detected project evidence."],
            next_action="Run studio-project-intake or choose Advanced mode with an explicit workflow.",
        )

    selected_families = sorted({str(route["family"]) for route in routes})
    workflows = sorted({str(route["workflow"]) for route in routes})
    if len(selected_families) > 1:
        return _packet(
            status="AMBIGUOUS",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=None,
            selected_workflow=None,
            candidates=selected_families,
            workflow_candidates=workflows,
            questions=["Which reported Golden Path matches the first failing or requested outcome?"],
            risk_level="read-only",
            prerequisites=[],
            next_action="Choose one candidate Golden Path; no mutation is authorized.",
        )
    if len(workflows) > 1:
        return _packet(
            status="AMBIGUOUS",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=selected_families[0],
            selected_workflow=None,
            candidates=selected_families,
            workflow_candidates=workflows,
            questions=["Which workflow candidate matches the evidence boundary you need to inspect?"],
            risk_level="read-only",
            prerequisites=[],
            next_action="Choose one canonical workflow; no mutation is authorized.",
        )

    selected = routes[0]
    workflow = str(selected["workflow"])
    installed = set(available_skills) if available_skills is not None else None
    if installed is not None and workflow not in installed:
        return _packet(
            status="BLOCKED",
            role=selected_role,
            intent=intent,
            mode=selected_mode,
            golden_path=str(selected["family"]),
            selected_workflow=None,
            candidates=[str(selected["family"])],
            workflow_candidates=[],
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
        golden_path=str(selected["family"]),
        selected_workflow=workflow,
        candidates=[str(selected["family"])],
        workflow_candidates=[workflow],
        questions=[],
        risk_level=str(selected["risk_level"]),
        prerequisites=[],
        next_action=str(selected["next_action"]),
    )
```

- [ ] **Step 6: Extend the strict task-packet schema**

In `evals/schema/studio-task-packet.schema.json`, add `workflow_candidates` to `required` immediately after `candidates`, then add:

```json
    "workflow_candidates": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "type": "string",
        "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"
      }
    },
```

Do not hand-edit bundled schema copies under `skills/*/schemas/`.

- [ ] **Step 7: Synchronize and run focused tests**

Run:

```text
python -B scripts/sync_skill_resources.py .
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest tests.studio_experience.test_studio_experience tests.evals.test_studio_experience_schemas tests.packaging.test_skill_resources -v
```

Expected: generated schema copies update from the canonical schema; every focused test PASS.

- [ ] **Step 8: Commit only after explicit maintainer authorization**

```text
git add scripts/studio_experience.py tests/studio_experience/test_studio_experience.py evals/schema/studio-task-packet.schema.json tests/evals/test_studio_experience_schemas.py skills/using-game-studio-skills/schemas skills/studio-project-scaffold/schemas
git commit -m "feat: complete eight golden path routes"
```

### Task 2: Add Advanced Workflow Selection to the Report-only CLI

**Files:**
- Modify: `scripts/gamestudio_cli.py`
- Modify: `tests/studio_project_scaffold/test_gamestudio_cli.py`

- [ ] **Step 1: Add failing CLI safety tests**

Append these methods to `GameStudioCliTests`:

```python
    def test_guide_rejects_workflow_override_in_basic_mode(self) -> None:
        from scripts.gamestudio_cli import main

        with temporary_directory() as temp:
            output = io.StringIO()
            errors = io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors), self.assertRaises(SystemExit):
                main([
                    "guide",
                    temp,
                    "--role",
                    "qa",
                    "--intent",
                    "verify",
                    "--mode",
                    "basic",
                    "--workflow",
                    "unity-asset-guid-meta-audit",
                ])

    def test_advanced_guide_selects_workflow_without_writing(self) -> None:
        from scripts.gamestudio_cli import main
        from scripts.project_scaffold import draft_project_profile

        with temporary_directory() as temp:
            root = Path(temp)
            profile = draft_project_profile(root)
            profile["repositories"][0]["subsystems"] = ["unity", "assets"]
            profile_path = root / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            import yaml
            profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main([
                    "guide",
                    str(root),
                    "--role",
                    "qa",
                    "--intent",
                    "verify",
                    "--mode",
                    "advanced",
                    "--golden-path",
                    "unity-build-asset-integrity",
                    "--workflow",
                    "unity-asset-guid-meta-audit",
                ])

            packet = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("READY", packet["status"])
            self.assertEqual("unity-asset-guid-meta-audit", packet["selected_workflow"])
            self.assertFalse((root / ".agents" / "gamestudio-install.json").exists())
```

- [ ] **Step 2: Run the tests and verify `--workflow` is unknown**

Run:

```text
python -B -m unittest tests.studio_project_scaffold.test_gamestudio_cli.GameStudioCliTests.test_guide_rejects_workflow_override_in_basic_mode tests.studio_project_scaffold.test_gamestudio_cli.GameStudioCliTests.test_advanced_guide_selects_workflow_without_writing -v
```

Expected: FAIL because the guide parser has no `--workflow` argument.

- [ ] **Step 3: Add the Advanced-only parser contract**

Add this guide argument:

```python
    guide.add_argument("--workflow")
```

After `args = parser.parse_args(argv)`, add:

```python
    if args.command == "guide" and args.workflow and args.mode != "advanced":
        parser.error("--workflow requires --mode advanced")
```

Pass the value to the planner:

```python
            requested_workflow=args.workflow,
```

- [ ] **Step 4: Run the full CLI suite**

Run:

```text
python -B -m unittest tests.studio_project_scaffold.test_gamestudio_cli -v
```

Expected: all tests PASS and no guide test creates scaffold-owned files.

- [ ] **Step 5: Commit only after explicit maintainer authorization**

```text
git add scripts/gamestudio_cli.py tests/studio_project_scaffold/test_gamestudio_cli.py
git commit -m "feat: add advanced golden path selection"
```

### Task 3: Add Phase 2 Routing and Behavior Coverage

**Files:**
- Modify: `evals/routing/unity-ui-rendering-debugging.json`
- Modify: `evals/routing/localization-authority-audit.json`
- Modify: `evals/routing/unity-batchmode-build-verification.json`
- Modify: `evals/routing/unity-asset-guid-meta-audit.json`
- Modify: `evals/routing/lua-client-server-contract-audit.json`
- Modify: `evals/routing/network-authority-and-exploit-review.json`
- Modify: `evals/routing/game-database-migration-safety.json`
- Modify: `evals/routing/save-data-schema-migration.json`
- Modify: `evals/routing/release-candidate-preflight.json`
- Modify: `evals/routing/liveops-incident-response.json`
- Modify: `evals/behavior/role-ux-golden-paths.json`

- [ ] **Step 1: Add one role-and-intent route per remaining canonical workflow**

Add the following case to its named routing file:

```json
{"prompt":"QA verify the Unity HUD render chain and clipping before changing a prefab","expected_skill":"unity-ui-rendering-debugging","type":"positive"}
```

```json
{"prompt":"Producer hãy lập kế hoạch kiểm tra nguồn authority localization và generated copies, chưa sửa file","expected_skill":"localization-authority-audit","type":"positive"}
```

```json
{"prompt":"QA verify the Unity batchmode build log and exact player artifact for Ship intent","expected_skill":"unity-batchmode-build-verification","type":"positive"}
```

```json
{"prompt":"Developer chẩn đoán duplicate GUID, missing meta và stale prefab reference trong Unity project","expected_skill":"unity-asset-guid-meta-audit","type":"positive"}
```

```json
{"prompt":"QA verify Lua client and server field mappings for the same RPC handler","expected_skill":"lua-client-server-contract-audit","type":"positive"}
```

```json
{"prompt":"LiveOps xử lý nghi vấn exploit nhưng chỉ review server authority, validation và rate limit","expected_skill":"network-authority-and-exploit-review","type":"positive"}
```

```json
{"prompt":"Producer plan the MySQL schema change with isolated dry-run, reviewer, backup and restore","expected_skill":"game-database-migration-safety","type":"positive"}
```

```json
{"prompt":"Developer lập kế hoạch migrate player save schema có rollback và block unknown version","expected_skill":"save-data-schema-migration","type":"positive"}
```

```json
{"prompt":"Producer run Ship readiness for this exact release candidate and return go or no-go evidence","expected_skill":"release-candidate-preflight","type":"positive"}
```

```json
{"prompt":"LiveOps handle the production incident with mitigation boundary, rollback and monitoring, no restart yet","expected_skill":"liveops-incident-response","type":"positive"}
```

- [ ] **Step 2: Add four Phase 2 behavior cases**

Append these objects to `evals/behavior/role-ux-golden-paths.json`:

```json
    {
      "id": "role-ux-unity-ui-localization",
      "prompt": "As QA, distinguish Unity UI rendering evidence from localization authority and ask one question when the family is ambiguous.",
      "target_skill": "using-game-studio-skills",
      "expected_verdict": "PASS",
      "allow_mutation": false,
      "required_artifact_fields": ["golden_path", "workflow_candidates", "questions", "risk_level"]
    },
    {
      "id": "role-ux-unity-build-assets",
      "prompt": "As QA in Advanced mode, select Unity GUID/meta integrity within the build and asset Golden Path and return a report-only packet.",
      "target_skill": "unity-asset-guid-meta-audit",
      "expected_verdict": "PASS",
      "allow_mutation": false,
      "required_artifact_fields": ["golden_path", "selected_workflow", "prerequisites", "next_action"]
    },
    {
      "id": "role-ux-lua-authority-blocked",
      "prompt": "As LiveOps, select server-authority review but return BLOCKED with the owning pack when that capability is missing.",
      "target_skill": "network-authority-and-exploit-review",
      "expected_verdict": "BLOCKED",
      "allow_mutation": false,
      "required_artifact_fields": ["golden_path", "blocked", "prerequisites", "next_action"]
    },
    {
      "id": "role-ux-data-live-safety",
      "prompt": "As Producer, route Ship to release preflight and keep database, save migration, and incident mutation gates separate.",
      "target_skill": "release-candidate-preflight",
      "expected_verdict": "PASS",
      "allow_mutation": false,
      "required_artifact_fields": ["golden_path", "selected_workflow", "risk_level", "next_action"]
    }
```

- [ ] **Step 3: Run deterministic and offline evaluator tests**

Run:

```text
python -B scripts/route_eval.py .
python -B -m unittest tests._meta.test_route_eval tests.evals.test_offline_evals -v
```

Expected: `route-eval: PASS 290/290`; all offline evaluator tests PASS.

- [ ] **Step 4: Commit only after explicit maintainer authorization**

```text
git add evals/routing evals/behavior/role-ux-golden-paths.json
git commit -m "test: cover phase two golden path routing"
```

### Task 4: Fill the Missing Governed Dogfood Scenarios

**Files:**
- Modify: `evals/dogfood/game-studio-scenarios.json`
- Modify: `evals/schema/dogfood-case.schema.json`
- Modify: `tests/evals/test_dogfood_eval.py`
- Modify: `docs/authoring/dogfood.md`

- [ ] **Step 1: Update the failing repository-pack assertions**

Rename `test_repository_pack_has_twelve_unique_game_scenarios` to `test_repository_pack_has_fifteen_unique_game_scenarios`, then change both assertions from `12` to `15`.

In `test_verified_results_can_generate_catalog_summaries`, change:

```python
            self.assertEqual(15, len(written))
```

- [ ] **Step 2: Run the focused assertions and confirm the fixture is still 12 cases**

Run:

```text
python -B -m unittest tests.evals.test_dogfood_eval.DogfoodEvalTests.test_repository_pack_has_fifteen_unique_game_scenarios tests.evals.test_dogfood_eval.DogfoodEvalTests.test_verified_results_can_generate_catalog_summaries -v
```

Expected: FAIL with observed count `12`.

- [ ] **Step 3: Add the three missing report-only scenarios**

Append these cases to `evals/dogfood/game-studio-scenarios.json`:

```json
    {
      "id": "unity-guid-meta-integrity",
      "workflow": "unity-asset-guid-meta-audit",
      "project_kind": "authorized Unity project snapshot",
      "prompt": "Audit duplicate GUIDs, missing meta files, and stale serialized references without reimporting or saving assets.",
      "required_artifacts": ["command-log", "project-snapshot", "guid-meta-report", "verdict"],
      "allow_mutation": false
    },
    {
      "id": "server-authority-boundary",
      "workflow": "network-authority-and-exploit-review",
      "project_kind": "authorized MMORPG client and server snapshot",
      "prompt": "Review sensitive client actions against exact server validation and rate-limit handlers without sending exploit traffic.",
      "required_artifacts": ["command-log", "project-snapshot", "authority-report", "verdict"],
      "allow_mutation": false
    },
    {
      "id": "save-schema-rollback-plan",
      "workflow": "save-data-schema-migration",
      "project_kind": "sanitized player-save fixtures",
      "prompt": "Plan a versioned save migration with unknown-version blocking and byte-preserving rollback evidence; do not modify live player data.",
      "required_artifacts": ["command-log", "project-snapshot", "save-migration-plan", "verdict"],
      "allow_mutation": false
    }
```

- [ ] **Step 4: Raise the strict case limit**

In `evals/schema/dogfood-case.schema.json`, change:

```json
      "maxItems": 15,
```

Do not weaken `additionalProperties`, required fields, or mutation constraints.

- [ ] **Step 5: Update the dogfood authoring guide**

Replace the twelve-scenario sentence with:

```markdown
Export the fifteen scenarios and an explicit local BLOCKED status. The universal pack now includes report-only GUID/meta integrity, server-authority boundary, and save-schema rollback cases in addition to the original twelve workflows.
```

- [ ] **Step 6: Run the full dogfood evaluator suite**

Run:

```text
python -B -m unittest tests.evals.test_dogfood_eval -v
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
```

Expected: all unit tests PASS; export reports `15 cases`; status writes an honest `BLOCKED` artifact because no governed runner result was supplied.

- [ ] **Step 7: Commit only after explicit maintainer authorization**

```text
git add evals/dogfood/game-studio-scenarios.json evals/schema/dogfood-case.schema.json tests/evals/test_dogfood_eval.py docs/authoring/dogfood.md
git commit -m "test: complete golden path dogfood coverage"
```

### Task 5: Add Governed Studio Adoption Metrics

**Files:**
- Create: `evals/adoption/studio-role-golden-paths.json`
- Create: `evals/schema/studio-adoption-result.schema.json`
- Create: `scripts/studio_adoption_eval.py`
- Create: `tests/evals/test_studio_adoption_eval.py`

- [ ] **Step 1: Write the failing evaluator tests**

Create `tests/evals/test_studio_adoption_eval.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


class StudioAdoptionEvalTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def results(self) -> dict[str, object]:
        benchmark = json.loads(
            (self.ROOT / "evals" / "adoption" / "studio-role-golden-paths.json").read_text(
                encoding="utf-8"
            )
        )
        runs = []
        for index, case in enumerate(benchmark["cases"]):
            started = f"2026-08-19T10:{index:02d}:00+07:00"
            finished = f"2026-08-19T10:{index:02d}:30+07:00"
            runs.append(
                {
                    "id": case["id"],
                    "selected_golden_path": case["expected_golden_path"],
                    "question_count": 1,
                    "started_at": started,
                    "verdict_at": finished,
                    "task_verdict": "PASS",
                    "dependency_failure": False,
                    "unauthorized_writes": 0,
                    "evidence_label": "Verified",
                    "reviewer": "QA Lead",
                    "artifact": f"evidence/local/adoption/{case['id']}.json",
                }
            )
        return {"schema_version": 1, "runs": runs}

    def test_without_governed_results_is_blocked(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        report = evaluate_adoption(self.ROOT)

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIsNone(report["metrics"]["routing_success_rate"])

    def test_verified_results_meet_all_targets(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        with temporary_directory() as temp:
            path = Path(temp) / "results.json"
            path.write_text(json.dumps(self.results()), encoding="utf-8")
            report = evaluate_adoption(self.ROOT, path)

        self.assertEqual("PASS", report["verdict"])
        self.assertEqual(1.0, report["metrics"]["routing_success_rate"])
        self.assertEqual(1, report["metrics"]["max_question_count"])
        self.assertEqual(0, report["metrics"]["dependency_failures"])
        self.assertEqual(0, report["metrics"]["unauthorized_writes"])
        self.assertLessEqual(report["metrics"]["onboarding_time_to_verdict_seconds"], 300)

    def test_threshold_failures_are_reported_together(self) -> None:
        from scripts.studio_adoption_eval import evaluate_adoption

        payload = self.results()
        payload["runs"][0]["selected_golden_path"] = "wrong-route"
        payload["runs"][1]["selected_golden_path"] = "wrong-route"
        payload["runs"][2]["selected_golden_path"] = "wrong-route"
        payload["runs"][0]["question_count"] = 4
        payload["runs"][0]["dependency_failure"] = True
        payload["runs"][0]["unauthorized_writes"] = 1
        onboarding = next(run for run in payload["runs"] if run["id"] == "install-to-first-use")
        onboarding["verdict_at"] = "2026-08-19T10:10:01+07:00"

        with temporary_directory() as temp:
            path = Path(temp) / "results.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            report = evaluate_adoption(self.ROOT, path)

        self.assertEqual("FAIL", report["verdict"])
        joined = " ".join(report["failures"])
        self.assertIn("routing success", joined)
        self.assertIn("question count", joined)
        self.assertIn("dependency failures", joined)
        self.assertIn("unauthorized writes", joined)
        self.assertIn("install-to-first-use", joined)

    def test_benchmark_covers_all_roles_intents_and_golden_paths(self) -> None:
        from scripts.studio_adoption_eval import load_benchmark

        benchmark = load_benchmark(self.ROOT)

        self.assertEqual({"developer", "qa", "producer", "liveops"}, {case["role"] for case in benchmark})
        self.assertEqual(
            {"diagnose", "verify", "plan-change", "ship", "handle-incident"},
            {case["intent"] for case in benchmark},
        )
        self.assertEqual(8, len({case["expected_golden_path"] for case in benchmark}))
        self.assertTrue(any("hãy" in case["prompt"].casefold() for case in benchmark))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and confirm the evaluator and fixtures are missing**

Run:

```text
python -B -m unittest tests.evals.test_studio_adoption_eval -v
```

Expected: FAIL with `FileNotFoundError` or `ModuleNotFoundError` for the new adoption files.

- [ ] **Step 3: Create the maintained adoption benchmark**

Create `evals/adoption/studio-role-golden-paths.json`:

```json
{
  "schema_version": 1,
  "targets": {
    "routing_success_rate": 0.8,
    "max_question_count": 3,
    "onboarding_time_to_verdict_seconds": 300,
    "dependency_failures": 0,
    "unauthorized_writes": 0
  },
  "cases": [
    {"id":"install-to-first-use","role":"developer","intent":"plan-change","prompt":"Adopt this Unity MMORPG repository and produce the first useful report-only verdict.","expected_golden_path":"project-adoption-routing","onboarding":true},
    {"id":"liveops-local-environment","role":"liveops","intent":"diagnose","prompt":"Diagnose local service ports and prerequisites without restarting anything.","expected_golden_path":"local-environment-recovery","onboarding":false},
    {"id":"qa-unity-entry","role":"qa","intent":"diagnose","prompt":"QA hãy chẩn đoán Unity client không vào được offline mode.","expected_golden_path":"unity-client-entry-recovery","onboarding":false},
    {"id":"developer-cpp-crash","role":"developer","intent":"diagnose","prompt":"Bind this C++ server crash to the exact build and next diagnostic.","expected_golden_path":"cpp-server-failure-recovery","onboarding":false},
    {"id":"qa-ui-localization","role":"qa","intent":"verify","prompt":"Verify whether this Unity screen failure is render-chain or localization-authority evidence.","expected_golden_path":"unity-ui-localization","onboarding":false},
    {"id":"qa-build-assets","role":"qa","intent":"verify","prompt":"QA hãy verify Unity build artifact và GUID/meta integrity.","expected_golden_path":"unity-build-asset-integrity","onboarding":false},
    {"id":"developer-lua-authority","role":"developer","intent":"verify","prompt":"Verify Lua contract fields and server authority for this sensitive action.","expected_golden_path":"lua-contract-server-authority","onboarding":false},
    {"id":"producer-data-change","role":"producer","intent":"plan-change","prompt":"Plan a save or database migration with reviewer, backup, restore, and no live mutation.","expected_golden_path":"data-live-release-safety","onboarding":false},
    {"id":"producer-ship","role":"producer","intent":"ship","prompt":"Ship intent: prepare the exact release candidate go or no-go packet.","expected_golden_path":"data-live-release-safety","onboarding":false},
    {"id":"liveops-incident","role":"liveops","intent":"handle-incident","prompt":"LiveOps hãy kiểm soát incident, rollback và monitoring; chưa restart service.","expected_golden_path":"data-live-release-safety","onboarding":false}
  ]
}
```

- [ ] **Step 4: Create the strict governed result schema**

Create `evals/schema/studio-adoption-result.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://gamestudio-codexkit.local/schema/studio-adoption-result.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "runs"],
  "properties": {
    "schema_version": {"const": 1},
    "runs": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "selected_golden_path", "question_count", "started_at", "verdict_at", "task_verdict", "dependency_failure", "unauthorized_writes", "evidence_label", "reviewer", "artifact"],
        "properties": {
          "id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
          "selected_golden_path": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
          "question_count": {"type": "integer", "minimum": 0},
          "started_at": {"type": "string", "format": "date-time"},
          "verdict_at": {"type": "string", "format": "date-time"},
          "task_verdict": {"enum": ["PASS", "FAIL", "BLOCKED"]},
          "dependency_failure": {"type": "boolean"},
          "unauthorized_writes": {"type": "integer", "minimum": 0},
          "evidence_label": {"const": "Verified"},
          "reviewer": {"type": "string", "minLength": 1},
          "artifact": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

- [ ] **Step 5: Implement the report-only evaluator**

Create `scripts/studio_adoption_eval.py`:

```python
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import jsonschema


BENCHMARK_PATH = Path("evals/adoption/studio-role-golden-paths.json")
RESULT_SCHEMA_PATH = Path("evals/schema/studio-adoption-result.schema.json")


def load_benchmark(root: Path | str) -> list[dict[str, Any]]:
    payload = json.loads((Path(root).resolve() / BENCHMARK_PATH).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("adoption benchmark requires schema_version 1 and cases")
    ids = [str(case.get("id", "")) for case in payload["cases"]]
    if any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("adoption benchmark requires unique non-empty ids")
    if sum(bool(case.get("onboarding")) for case in payload["cases"]) != 1:
        raise ValueError("adoption benchmark requires exactly one onboarding case")
    return [dict(case) for case in payload["cases"]]


def _timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("adoption timestamps require timezone offsets")
    return parsed


def _blocked(total: int, reason: str) -> dict[str, Any]:
    return {
        "verdict": "BLOCKED",
        "total": total,
        "failures": [reason],
        "metrics": {
            "routing_success_rate": None,
            "max_question_count": None,
            "median_time_to_verdict_seconds": None,
            "onboarding_time_to_verdict_seconds": None,
            "dependency_failures": None,
            "unauthorized_writes": None,
        },
    }


def evaluate_adoption(
    root: Path | str, results_path: Path | str | None = None
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    cases = load_benchmark(root_path)
    if results_path is None:
        return _blocked(len(cases), "No governed studio adoption results were supplied")

    schema = json.loads((root_path / RESULT_SCHEMA_PATH).read_text(encoding="utf-8"))
    payload = json.loads(Path(results_path).read_text(encoding="utf-8"))
    try:
        jsonschema.validate(payload, schema, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as error:
        return {
            **_blocked(len(cases), "Invalid adoption result schema"),
            "verdict": "FAIL",
            "failures": [f"result schema: {error.message}"],
        }

    case_by_id = {case["id"]: case for case in cases}
    run_by_id = {run["id"]: run for run in payload["runs"]}
    failures: list[str] = []
    if len(run_by_id) != len(payload["runs"]):
        failures.append("duplicate adoption result ids")
    missing = sorted(set(case_by_id) - set(run_by_id))
    unknown = sorted(set(run_by_id) - set(case_by_id))
    if missing:
        failures.append(f"missing adoption result ids: {missing}")
    if unknown:
        failures.append(f"unknown adoption result ids: {unknown}")
    if failures:
        return {
            **_blocked(len(cases), failures[0]),
            "verdict": "FAIL",
            "failures": failures,
        }

    durations: list[float] = []
    route_successes = 0
    max_questions = 0
    dependency_failures = 0
    unauthorized_writes = 0
    onboarding_seconds: float | None = None
    for case_id, case in case_by_id.items():
        run = run_by_id[case_id]
        started = _timestamp(run["started_at"])
        finished = _timestamp(run["verdict_at"])
        duration = (finished - started).total_seconds()
        if duration < 0:
            failures.append(f"{case_id}: verdict_at precedes started_at")
            continue
        durations.append(duration)
        if run["selected_golden_path"] == case["expected_golden_path"]:
            route_successes += 1
        max_questions = max(max_questions, int(run["question_count"]))
        dependency_failures += int(bool(run["dependency_failure"]))
        unauthorized_writes += int(run["unauthorized_writes"])
        if case["onboarding"]:
            onboarding_seconds = duration

    routing_success = route_successes / len(cases)
    metrics = {
        "routing_success_rate": routing_success,
        "max_question_count": max_questions,
        "median_time_to_verdict_seconds": statistics.median(durations) if durations else None,
        "onboarding_time_to_verdict_seconds": onboarding_seconds,
        "dependency_failures": dependency_failures,
        "unauthorized_writes": unauthorized_writes,
    }
    if routing_success < 0.8:
        failures.append(f"routing success {routing_success:.3f} is below 0.800")
    if max_questions > 3:
        failures.append(f"question count {max_questions} exceeds 3")
    if onboarding_seconds is None or onboarding_seconds > 300:
        failures.append(f"install-to-first-use time {onboarding_seconds} exceeds 300 seconds")
    if dependency_failures:
        failures.append(f"dependency failures observed: {dependency_failures}")
    if unauthorized_writes:
        failures.append(f"unauthorized writes observed: {unauthorized_writes}")
    return {
        "verdict": "FAIL" if failures else "PASS",
        "total": len(cases),
        "failures": failures,
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate governed Role UX adoption metrics.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--status", type=Path)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.export:
        cases = load_benchmark(root)
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text(
            "".join(json.dumps(case, sort_keys=True, ensure_ascii=False) + "\n" for case in cases),
            encoding="utf-8",
        )
        print(f"studio-adoption-export: {len(cases)} cases")
    if args.status:
        args.status.parent.mkdir(parents=True, exist_ok=True)
        args.status.write_text(
            json.dumps(_blocked(len(load_benchmark(root)), "No governed studio adoption results were supplied"), indent=2) + "\n",
            encoding="utf-8",
        )
        print(args.status)
    if args.results:
        report = evaluate_adoption(root, args.results)
    elif args.export or args.status:
        return 0
    else:
        report = evaluate_adoption(root)
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "PASS" else 2 if report["verdict"] == "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run evaluator tests and export an honest local status**

Run:

```text
python -B -m unittest tests.evals.test_studio_adoption_eval -v
python -B scripts/studio_adoption_eval.py . --export evidence/local/studio-adoption-cases.jsonl
python -B scripts/studio_adoption_eval.py . --status evidence/local/studio-adoption-status.json
```

Expected: all tests PASS; export reports `10 cases`; local status is `BLOCKED` and does not claim observed adoption metrics.

- [ ] **Step 7: Commit only after explicit maintainer authorization**

```text
git add evals/adoption/studio-role-golden-paths.json evals/schema/studio-adoption-result.schema.json scripts/studio_adoption_eval.py tests/evals/test_studio_adoption_eval.py
git commit -m "feat: measure governed studio adoption"
```

### Task 6: Align Persona Lenses and Public Studio UX

**Files:**
- Modify: `personas/gameplay-engineer/PERSONA.md`
- Modify: `personas/technical-artist/PERSONA.md`
- Modify: `personas/network-backend/PERSONA.md`
- Modify: `personas/qa-lead/PERSONA.md`
- Modify: `personas/producer/PERSONA.md`
- Modify: `README.md`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/architecture/project-init-and-studio-expansion.md`
- Modify: `docs/index.html`
- Modify: `docs/assets/banner.svg`

- [ ] **Step 1: Align persona bodies with their existing registry routes**

Replace each persona's `## Routes` paragraph with the following lens-only text. Do not add a `## Workflow` heading or completion criteria.

`personas/gameplay-engineer/PERSONA.md`:

```markdown
## Routes
Use `studio-project-intake`, `evidence-first-debugging`, `build-and-runtime-verification`, `lua-client-server-contract-audit`, `unity-client-offline-debugging`, `unity-batchmode-build-verification`, `game-performance-budget`, `telemetry-event-contract-review`, `studio-workspace-routing`, or `studio-agent-orchestration`.

## Role UX
This lens most often supports the Developer role. The requested intent and repository evidence still choose the canonical workflow.
```

`personas/technical-artist/PERSONA.md`:

```markdown
## Routes
Use `unity-ui-rendering-debugging`, `localization-authority-audit`, `unity-asset-guid-meta-audit`, `unity-batchmode-build-verification`, or `game-performance-budget`.

## Role UX
This lens supports Developer or QA presentation for Unity UI, localization, asset, and build evidence; it grants no asset-save or reimport authority.
```

`personas/network-backend/PERSONA.md`:

```markdown
## Routes
Use `multi-service-local-environment-doctor`, `game-database-migration-safety`, `lua-client-server-contract-audit`, `cpp-server-crash-triage`, `mmorpg-packet-protocol-review`, `network-authority-and-exploit-review`, `save-data-schema-migration`, `telemetry-event-contract-review`, or `review-swarm`.

## Role UX
This lens supports Developer and LiveOps presentation. Service control, exploit traffic, database apply, and save mutation remain separately gated.
```

`personas/qa-lead/PERSONA.md`:

```markdown
## Routes
Use `build-and-runtime-verification`, `review-swarm`, `bug-hunt-swarm`, `playtest-evidence`, `game-performance-budget`, `release-candidate-preflight`, `store-submission-checklist`, `studio-handoff`, `studio-workspace-routing`, or `studio-agent-orchestration`.

## Role UX
This lens maps naturally to the QA role and emphasizes evidence completeness, negative cases, and regression boundaries without changing the selected workflow's authority.
```

`personas/producer/PERSONA.md`:

```markdown
## Routes
Use `studio-project-intake`, `feature-to-work-packets`, `studio-handoff`, `game-feature-brainstorming`, `release-candidate-preflight`, `store-submission-checklist`, `liveops-incident-response`, `studio-workspace-routing`, or `studio-agent-orchestration`.

## Role UX
This lens maps naturally to the Producer role. It exposes dependency and readiness evidence but cannot lower technical, release, or incident gates.
```

- [ ] **Step 2: Add the eight-family catalog to README**

After `## What you can ask`, add:

```markdown
## Unity/MMORPG Golden Paths

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

Roles (`Developer`, `QA`, `Producer`, `LiveOps`) influence default intent and presentation. Personas remain optional discipline lenses; neither roles nor personas bypass canonical skill safety or evidence contracts.
```

- [ ] **Step 3: Document governed adoption commands**

Add to `README.md` and `docs/architecture/project-init-and-studio-expansion.md`:

```markdown
python -B scripts/studio_adoption_eval.py . --export evidence/local/studio-adoption-cases.jsonl
python -B scripts/studio_adoption_eval.py . --status evidence/local/studio-adoption-status.json
python -B scripts/studio_adoption_eval.py . --results evidence/local/studio-adoption-results.json
```

Document that PASS requires at least 80% intended Golden Path routing, no Basic packet above three questions, install-to-first-use at or below five minutes, zero missing-dependency failures, and zero unauthorized writes. Without governed results the evaluator returns `BLOCKED`.

- [ ] **Step 4: Update public counts and architecture statements**

Update all maintained public surfaces from 280 to 290 deterministic routing cases and from 12 to 15 governed dogfood scenarios:

- `README.md`
- `docs/index.html`
- `docs/assets/banner.svg`

Add to `docs/architecture/overview.md`:

```markdown
Golden Paths are registry-backed route families, not new workflow authorities. A family may expose multiple canonical workflow candidates. Basic mode asks one clarifying question when repository and intent evidence cannot safely select one; Advanced mode may select a reported candidate explicitly. Adoption metrics are runner-backed and remain BLOCKED without governed result artifacts.
```

- [ ] **Step 5: Run persona, routing, and public-surface tests**

Run:

```text
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B -m unittest tests.packaging.test_codex_plugin tests._meta.test_validate tests.evals.test_studio_adoption_eval -v
```

Expected: validation accepts lens-only personas; routing reports `290/290`; public catalog counts match registry and routing evidence. If the known long-lived Windows checkout hits only the promotion-artifact raw-byte hash issue, record that command as failed for this checkout and verify the same commit in a fresh clone before any PASS claim.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add personas README.md docs/architecture docs/index.html docs/assets/banner.svg
git commit -m "docs: publish role-aware golden paths"
```

### Task 7: Version and Verify the Completed Rollout

**Files:**
- Modify: `.codex-plugin/plugin.json:3`
- Modify: `pyproject.toml:7`
- Modify: `tests/packaging/test_codex_plugin.py`

- [ ] **Step 1: Minor-version the distributed feature**

Change both version declarations from `1.6.0` to `1.7.0`:

```json
"version": "1.7.0"
```

```toml
version = "1.7.0"
```

In `CodexPluginPackagingTests.test_root_manifest_packages_the_canonical_skill_catalog`, change:

```python
        self.assertEqual("1.7.0", manifest["version"])
```

- [ ] **Step 2: Run focused rollout verification**

Run:

```text
python -B -m unittest tests.studio_experience.test_studio_experience tests.studio_project_scaffold.test_gamestudio_cli tests.evals.test_studio_experience_schemas tests.evals.test_studio_adoption_eval tests.evals.test_dogfood_eval tests.evals.test_offline_evals tests.packaging.test_codex_plugin tests.packaging.test_skill_resources -v
python -B scripts/route_eval.py .
python -B scripts/sync_skill_resources.py . --check
```

Expected: all focused tests PASS, routing reports `290/290`, and generated resources are in sync.

- [ ] **Step 3: Run every required repository gate**

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

Expected: every command exits `0`. If the current long-lived Windows checkout alone fails the known promotion-artifact hash because of CRLF normalization while a fresh clone of the same commit passes, label the local command `BLOCKED` or failed and preserve the fresh-clone command, exit code, and commit as separate Verified evidence.

- [ ] **Step 4: Run lifecycle and governed-evidence commands honestly**

Run:

```text
python -B scripts/check_originality.py .
python -B scripts/catalog_audit.py .
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
python -B scripts/studio_adoption_eval.py . --export evidence/local/studio-adoption-cases.jsonl
python -B scripts/studio_adoption_eval.py . --status evidence/local/studio-adoption-status.json
```

Expected: deterministic exports succeed. Originality, lifecycle, dogfood, or adoption results may remain `BLOCKED` when upstream snapshots, governed runners, live projects, or session evidence are unavailable; do not convert them to PASS.

- [ ] **Step 5: Inspect canonical and generated boundaries**

Run:

```text
git diff -- .codex-plugin/plugin.json pyproject.toml registry skills scripts tests evals personas README.md docs
```

Expected: root helpers and canonical schemas own generated resources; no `skills/*/scripts/` or bundled schema was hand-edited; repository-local maintenance IDs remain outside distributed registries and project outputs.

- [ ] **Step 6: Commit only after explicit maintainer authorization**

```text
git add .codex-plugin/plugin.json pyproject.toml tests/packaging/test_codex_plugin.py
git commit -m "release: complete golden paths and role ux adoption"
```
