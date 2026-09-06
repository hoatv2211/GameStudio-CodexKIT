# Studio Goal Progress and Context Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portable, evidence-backed Goal progress with verified percentage, honest ETA ranges, secured read-only GUI projections, optional Codex App Server observations, and deterministic compact context artifacts.

**Architecture:** Keep `progress.jsonl` as the sole replay authority. A persistent goal-local writer serializes validated candidate events, reduces state, tracks monotonic active time by writer epoch, and serves a private submission endpoint plus an authenticated public GET/SSE dashboard. A separate deterministic context helper projects the same reduced state into `brief`, `working`, and `resume` artifacts without replacing `studio-handoff`.

**Tech Stack:** Python 3.11 standard library (`argparse`, `dataclasses`, `hashlib`, `http.server`, `json`, `pathlib`, `secrets`, `statistics`, `subprocess`, `tempfile`, `threading`, `time`, `urllib`), PyYAML for repository registries, JSON Schema Draft 2020-12 for contract tests, vanilla HTML/CSS/JavaScript, and `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-04-studio-goal-progress-context-design.md`

## Global Constraints

- Planning snapshot is `dev@f5c3576f97d5fd946fa92ba54c4dc3b97c9cc6c9`; refresh Git status before execution and preserve unrelated work.
- `.codegraph/` is absent at planning time. Do not create or refresh an index; use source inspection unless the maintainer independently adds one.
- Runtime output stays under ignored `evidence/local/goals/<goal-id>/`; no runtime credential enters committed files, agent output, reports, or logs.
- `progress.jsonl` is the sole canonical replay stream. `goal.json`, `state.json`, integration status, context projections, and server metadata are replaceable derived/runtime files.
- Only `packet.verified` with workflow-owned evidence changes completed weight. Percentage and ETA are derived and never count as verification evidence.
- Initial ETA supports `max_active_timed_packets: 1`; parallel work keeps percentage valid and returns `BLOCKED` with `unsupported_parallel_timing` for ETA.
- GUI opening is manual. The dashboard exposes no Goal mutation, approval, pause, resume, cancel, database, publish, or service-control controls.
- The public dashboard binds `127.0.0.1`, uses a short-lived single-use bootstrap token, redirects to a clean URL, and authenticates later GET/SSE requests with an HttpOnly SameSite=Strict cookie.
- The optional App Server adapter operates only on a client-owned initialized transport or a documented host-provided stream. A desktop thread ID alone remains `BLOCKED`.
- Runtime code adds no third-party dependency. `jsonschema` remains a test-only dependency already used by repository tests.
- The standalone `scripts/context_brief.py` entry point uses Python standard library only and imports no repository-local helper; its bundled skill receives only that script and its two schemas.
- Context targets/caps remain: `brief` 150/300, `working` 800/1,200, and `resume` 1,600/2,400 tokens. Required indivisible facts that cannot fit produce a `BLOCKED` projection instead of truncation.
- Root `scripts/` and root dashboard resources are canonical. Never hand-edit generated `skills/*/scripts/`, `skills/*/schemas/`, or `skills/*/assets/` copies.
- Do not mutate `.research/`, private studio projects, generated adapters, or generated packs during feature implementation.
- Distributed payload changes use semantic version `1.8.0` in `.codex-plugin/plugin.json` and `pyproject.toml`.
- Commit policy is `ask`. Every checkpoint below first shows a bounded diff; commit commands run only after explicit maintainer approval. Push, publish, deploy, and release remain separate permissions.
- Starting or stopping the real local Goal runtime for browser dogfood is a service-control action: run the dry-run preflight first, then obtain explicit approval before launch.

---

## File Map

| Path | Responsibility |
|---|---|
| `scripts/sync_skill_resources.py` | Add format-safe generated ownership markers for HTML, CSS, and JavaScript resources |
| `resources/goal-progress/index.html` | Canonical compact/full dashboard document shell |
| `resources/goal-progress/styles.css` | Responsive warm studio-ledger visual system with no external assets |
| `resources/goal-progress/app.js` | Cookie-authenticated state fetch, SSE refresh, filtering, and safe text rendering |
| `evals/schema/studio-goal-manifest.schema.json` | Closed initial/revised Goal manifest contract |
| `evals/schema/studio-goal-event.schema.json` | Closed accepted event, authority, evidence, payload, and hash contract |
| `evals/schema/studio-goal-state.schema.json` | Closed reduced state consumed by GUI/context tools |
| `evals/schema/studio-context-projection.schema.json` | Closed `brief`/`working`/`resume` projection artifact |
| `scripts/goal_progress_core.py` | Canonical JSON, validation, transitions, replay, percentage, ETA, stale state, and sanitization |
| `scripts/goal_progress_store.py` | Goal paths, exclusive writer lock, append, quarantine, atomic projections, and restart recovery |
| `scripts/goal_progress_server.py` | Persistent writer runtime, private submission listener, public dashboard/SSE listener, authentication, and artifact safety |
| `scripts/goal_progress_app_server.py` | App Server handshake contract and informational notification normalization |
| `scripts/goal_progress.py` | User-facing `init`, `emit`, `status`, `list`, `open`, `preflight`, `stop-runtime`, and internal `serve` CLI |
| `scripts/context_brief.py` | Deterministic context fact selection, budget enforcement, JSON/Markdown projection writes |
| `skills/studio-goal-progress/` | Distributed progress workflow, metadata, generated helpers, schemas, and dashboard assets |
| `skills/studio-context-brief/` | Distributed context workflow, metadata, generated helper, and schemas |
| `skills/using-game-studio-skills/SKILL.md` | Opt-in KIT Goal participation and routing to the progress skill |
| `skills/feature-to-work-packets/SKILL.md` | Progress weight, estimate, workflow owner, and serial timing fields for progress-enabled plans |
| `registry/capabilities.yaml` | Register both experimental capabilities and dependencies |
| `registry/packs.yaml` | Add both capabilities once to `studio-core` |
| `registry/skill-resources.yaml` | Bundle exact scripts, schemas, and dashboard assets into standalone skills |
| `evals/routing/studio-goal-progress.json` | Three positive, two negative-owner, and one collision route case |
| `evals/routing/studio-context-brief.json` | Three positive, two negative-owner, and one collision route case |
| `evals/behavior/studio-goal-progress.json` | Progress evidence, degradation, and read-only behavior cases |
| `evals/behavior/studio-context-brief.json` | Projection priority, cap, and handoff-boundary behavior cases |
| `evals/pressure/studio-goal-progress-guardrails.json` | Secret, traversal, fabricated progress, and service-control pressure cases |
| `evals/pressure/studio-context-brief-guardrails.json` | Raw-transcript, truncation, fabricated evidence, and handoff-replacement pressure cases |
| `tests/goal_progress/support.py` | Shared deterministic manifests, candidates, clocks, and temporary Goal helpers |
| `tests/goal_progress/test_goal_progress_schemas.py` | Draft 2020-12 contract acceptance/rejection |
| `tests/goal_progress/test_goal_progress_core.py` | Replay, transitions, progress, ETA, stale, and sanitization |
| `tests/goal_progress/test_goal_progress_store.py` | Locking, append integrity, quarantine, truncation, and atomic rebuild |
| `tests/goal_progress/test_goal_progress_cli.py` | CLI JSON contracts, runtime reuse, goal selection, and degradation |
| `tests/goal_progress/test_goal_progress_server.py` | Bootstrap/cookie auth, GET/SSE surface, headers, artifacts, and two-listener isolation |
| `tests/goal_progress/test_goal_progress_app_server.py` | Handshake, allowlist, version fixture, and informational-only normalization |
| `tests/goal_progress/test_context_brief.py` | Priority, exact literal preservation, caps, fallback counts, and `BLOCKED` overflow |
| `tests/packaging/test_skill_resources.py` | Web-resource suffix support and isolated skill resource loading |
| `tests/packaging/test_codex_plugin.py` | Catalog count, experimental set, and version `1.8.0` |
| `tests/packaging/test_packs_adapters.py` | Generated pack/adapter skill count `52` |
| `tests/governance/test_review_contracts.py` | Public guide coverage for all `52` skills |
| `tests/studio_experience/test_studio_experience.py` | Updated Tier-A route total `328/328` |
| Public catalog/docs files | Add two skills and synchronize `52` skills, `51` routed skills, `328` route cases, `24` agents, and `7` packs |

### Task 1: Teach Resource Sync to Package Dashboard Assets

**Files:**
- Modify: `scripts/sync_skill_resources.py`
- Modify: `tests/packaging/test_skill_resources.py`

**Interfaces:**
- Consumes: existing `render_generated_resource(path: Path, content: str) -> str`.
- Produces: `.html`, `.css`, and `.js` support with format-appropriate first-line ownership markers.

- [ ] **Step 1: Add RED tests for web ownership markers**

Add these assertions to `SkillResourcePackagingTests` and include the three suffixes in the test module's `SUPPORTED_SUFFIXES`:

```python
def test_web_resources_receive_format_appropriate_generated_markers(self) -> None:
    from scripts.sync_skill_resources import render_generated_resource

    html = render_generated_resource(Path("index.html"), "<main>Goal</main>\n")
    css = render_generated_resource(Path("styles.css"), ":root { color: #111; }\n")
    javascript = render_generated_resource(Path("app.js"), "export const ready = true;\n")

    self.assertTrue(html.startswith("<!-- Generated by scripts/sync_skill_resources.py. Do not edit manually. -->\n"))
    self.assertTrue(css.startswith("/* Generated by scripts/sync_skill_resources.py. Do not edit manually. */\n"))
    self.assertTrue(javascript.startswith("// Generated by scripts/sync_skill_resources.py. Do not edit manually.\n"))
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `python -B -m unittest tests.packaging.test_skill_resources.SkillResourcePackagingTests.test_web_resources_receive_format_appropriate_generated_markers -v`

Expected: FAIL because `.html`, `.css`, and `.js` are not present in `GENERATED_MARKERS_BY_SUFFIX`.

- [ ] **Step 3: Add the three canonical marker formats**

Extend the mapping in `scripts/sync_skill_resources.py` exactly as follows:

```python
GENERATED_MARKERS_BY_SUFFIX = {
    ".py": HASH_GENERATED_MARKER,
    ".toml": HASH_GENERATED_MARKER,
    ".yaml": HASH_GENERATED_MARKER,
    ".yml": HASH_GENERATED_MARKER,
    ".ps1": HASH_GENERATED_MARKER,
    ".sh": HASH_GENERATED_MARKER,
    ".md": HTML_GENERATED_MARKER,
    ".txt": HTML_GENERATED_MARKER,
    ".html": HTML_GENERATED_MARKER,
    ".css": f"/* {GENERATION_NOTICE} */",
    ".js": f"// {GENERATION_NOTICE}",
    ".json": GENERATION_NOTICE,
}
```

Keep `generated_header()` generic for every non-JSON suffix; do not add file-specific branches beyond the marker mapping.

- [ ] **Step 4: Run focused packaging tests and confirm GREEN**

Run: `python -B -m unittest tests.packaging.test_skill_resources -v`

Expected: PASS with no resource drift because no new resource mapping exists yet.

- [ ] **Step 5: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/sync_skill_resources.py tests/packaging/test_skill_resources.py`

Expected: only suffix/marker support and its tests. Do not commit without explicit approval. If approved:

```text
git add scripts/sync_skill_resources.py tests/packaging/test_skill_resources.py
git commit -m "feat: package dashboard skill resources"
```

### Task 2: Lock the Four JSON Contracts

**Files:**
- Create: `evals/schema/studio-goal-manifest.schema.json`
- Create: `evals/schema/studio-goal-event.schema.json`
- Create: `evals/schema/studio-goal-state.schema.json`
- Create: `evals/schema/studio-context-projection.schema.json`
- Create: `tests/goal_progress/support.py`
- Create: `tests/goal_progress/test_goal_progress_schemas.py`

**Interfaces:**
- Consumes: JSON Schema Draft 2020-12 and the approved spec.
- Produces: schema IDs `https://gamestudio-codexkit.local/schema/<filename>` and reusable valid fixtures `valid_manifest()`, `started_candidate()`, `accepted_started_event()`, `valid_state()`, and `valid_projection()`.

- [ ] **Step 1: Create shared deterministic fixtures**

Create `tests/goal_progress/support.py` with fixed values; no fixture uses the real worktree or wall clock:

```python
from __future__ import annotations

import copy
from pathlib import Path


FIXED_UTC = "2026-09-04T02:00:00Z"
GOAL_ID = "goal-demo-001"
EPOCH_ID = "epoch-demo-001"


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "goal_id": GOAL_ID,
        "title": "Verify the progress contract",
        "repository_root": "D:/work/game",
        "repository_snapshot": "dev@0123456789abcdef0123456789abcdef01234567",
        "created_at": FIXED_UTC,
        "plan_version": 1,
        "scope": ["scripts/goal_progress_core.py"],
        "do_not_touch": ["Assets/Production"],
        "packets": [
            {
                "id": "packet-contract",
                "workflow_id": "studio-goal-progress",
                "owner": "main-thread",
                "objective": "Verify the event contract",
                "progress_weight": 3,
                "dependencies": [],
                "completion_criteria": ["Focused contract tests pass"],
                "required_evidence": ["test-command"],
                "estimate_seconds": {"low": 60, "high": 120},
                "owned_paths": ["scripts/goal_progress_core.py"],
                "excluded_paths": ["Assets/Production"],
            }
        ],
        "final_verification_required": ["repository-gates"],
        "runtime_bindings": [{"kind": "codex_thread", "id": "thread-demo"}],
        "timing_policy": {"max_active_timed_packets": 1},
    }


def deep_copy(value: dict[str, object]) -> dict[str, object]:
    return copy.deepcopy(value)
```

- [ ] **Step 2: Add RED schema tests**

In `test_goal_progress_schemas.py`, use `Draft202012Validator.check_schema()` for all four files. Assert every schema has `additionalProperties: false`, the exact local `$id`, and rejects:

```python
INVALID_MUTATIONS = (
    ("manifest-extra-field", lambda value: value.__setitem__("unexpected", True)),
    ("manifest-zero-weight", lambda value: value["packets"][0].__setitem__("progress_weight", 0)),
    ("manifest-parallel-timing", lambda value: value["timing_policy"].__setitem__("max_active_timed_packets", 2)),
)
```

Also assert the event schema rejects an unknown source, unknown event type, non-positive sequence, malformed SHA-256, and state-changing event with `authority: null`. Assert the state schema rejects `percent` above `100`, `display_percent` above `99` while the goal is not completed, and `PASS` as an ETA status. Assert the projection schema rejects an unknown projection and `status: PASS` because projection states are `READY` or `BLOCKED`.

Draft 2020-12 validates each field's structure and fixed bounds here. It does not compare sibling numeric values or derive a text measurement, so `estimate_seconds.low <= estimate_seconds.high` moves to `validate_manifest()` in Task 3 and projection `count`/hard-cap consistency moves to `validate_projection()` in Task 7.

- [ ] **Step 3: Run schema tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_schemas.py" -v`

Expected: FAIL because the four schema files do not exist.

- [ ] **Step 4: Create the closed schemas**

Use these exact required top-level fields:

```json
{
  "studio-goal-manifest": ["schema_version", "goal_id", "title", "repository_root", "repository_snapshot", "created_at", "plan_version", "scope", "do_not_touch", "packets", "final_verification_required", "runtime_bindings", "timing_policy"],
  "studio-goal-event": ["schema_version", "event_id", "goal_id", "plan_version", "sequence", "emitted_at", "writer_epoch_id", "monotonic_offset_ms", "source", "event_type", "packet_id", "payload", "authority", "summary", "evidence", "raw_log_ref", "record_hash"],
  "studio-goal-state": ["schema_version", "goal_id", "plan_version", "manifest_hash", "goal_state", "packets", "progress", "eta", "revision_history", "latest_evidence", "next_action", "updated_at", "stale", "warnings"],
  "studio-context-projection": ["schema_version", "goal_id", "projection", "status", "count_kind", "count", "target", "hard_cap", "text", "required_fact_refs", "evidence_label"]
}
```

The event schema must conditionally require non-null authority for `plan.revised`, every `packet.*` state transition, `goal.completed`, and `goal.cancelled`. `goal.started.payload.manifest` and `plan.revised.payload.manifest` must reference the manifest definition. Evidence records use the exact closed fields `id`, `label`, `kind`, `summary`, `command`, `exit_code`, `artifact_path`, and `sha256`, with nullable command/artifact fields and lowercase 64-character SHA-256 when present.

- [ ] **Step 5: Run schema tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_schemas.py" -v`

Expected: PASS; all four schemas are valid Draft 2020-12 documents and reject the listed cases.

- [ ] **Step 6: Review diff and request checkpoint commit approval**

Run: `git diff -- evals/schema tests/goal_progress`

Expected: only four schemas and deterministic fixture/schema tests. If approved:

```text
git add evals/schema/studio-goal-manifest.schema.json evals/schema/studio-goal-event.schema.json evals/schema/studio-goal-state.schema.json evals/schema/studio-context-projection.schema.json tests/goal_progress/support.py tests/goal_progress/test_goal_progress_schemas.py
git commit -m "test: define goal progress contracts"
```

### Task 3: Implement Replay, Transitions, Evidence, and Percentage

**Files:**
- Create: `scripts/goal_progress_core.py`
- Create: `tests/goal_progress/test_goal_progress_core.py`
- Modify: `tests/goal_progress/support.py`

**Interfaces:**
- Consumes: manifest/event dictionaries from Task 2.
- Produces:
  - `GoalProgressError(ValueError)`
  - `canonical_json(value: object) -> str`
  - `sha256_json(value: object, *, omit: frozenset[str] = frozenset()) -> str`
  - `validate_manifest(manifest: dict[str, object]) -> None`
  - `validate_accepted_event(event: dict[str, object]) -> None`
  - `sanitize_summary(value: str, *, limit: int = 500) -> tuple[str, list[str]]`
  - `reduce_events(events: list[dict[str, object]], *, now_utc: str) -> dict[str, object]`

- [ ] **Step 1: Add RED transition and replay tests**

Add tests that construct accepted events with a helper in `support.py` and assert:

```python
def test_verified_weight_changes_only_after_packet_verified(self) -> None:
    started, running, observed, verified = event_sequence_for_verified_packet()

    before = reduce_events([started, running, observed], now_utc="2026-09-04T02:02:00Z")
    after = reduce_events([started, running, observed, verified], now_utc="2026-09-04T02:02:00Z")

    self.assertEqual(0, before["progress"]["verified_weight"])
    self.assertEqual(0.0, before["progress"]["percent"])
    self.assertEqual(3, after["progress"]["verified_weight"])
    self.assertEqual(100.0, after["progress"]["percent"])
    self.assertEqual(99, after["progress"]["display_percent"])
```

Add separate tests for reversed estimate ranges through `validate_manifest()`, duplicate packet IDs, missing dependency, dependency cycle, illegal `queued -> verified`, wrong expected prior state, wrong plan version, conflicting event ID, plan revision with wrong previous hash, revised-out denominator changes, reopening verified only through a new plan version, final verification before `goal.completed`, and complete replay after deleting derived state. The reversed-range test passes `{"low": 120, "high": 60}` and expects `GoalProgressError` naming `estimate_seconds.low` and `estimate_seconds.high`.

- [ ] **Step 2: Run core tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_core.py" -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.goal_progress_core'`.

- [ ] **Step 3: Implement deterministic canonicalization and validation**

Start `goal_progress_core.py` with these constants and transition table:

```python
STATE_CHANGING_EVENTS = frozenset({
    "plan.revised",
    "packet.started",
    "packet.waiting_input",
    "packet.resumed",
    "packet.blocked",
    "packet.failed",
    "packet.retry_started",
    "packet.verified",
    "goal.completed",
    "goal.cancelled",
})

PACKET_TRANSITIONS = {
    "packet.started": ({"queued"}, "running"),
    "packet.waiting_input": ({"running"}, "waiting_input"),
    "packet.resumed": ({"waiting_input"}, "running"),
    "packet.blocked": ({"running", "waiting_input"}, "blocked"),
    "packet.failed": ({"running"}, "failed"),
    "packet.retry_started": ({"blocked", "failed"}, "running"),
    "packet.verified": ({"running"}, "verified"),
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: object, *, omit: frozenset[str] = frozenset()) -> str:
    payload = value
    if isinstance(value, dict) and omit:
        payload = {key: item for key, item in value.items() if key not in omit}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
```

Validation must compare exact key sets, reject booleans where integers are required, validate dependency existence/cycles with depth-first search, verify manifest and record hashes, and require authority fields `workflow_id`, `owner`, `runtime_binding`, and `expected_prior_state` for state-changing events.

- [ ] **Step 4: Implement replay and progress reduction**

Initialize packet state only from the full manifest in `goal.started`. Apply revisions only after `previous_manifest_hash` matches the current manifest hash. Use this calculation:

```python
def _progress(manifest: dict[str, object], packet_states: dict[str, dict[str, object]], completed: bool) -> dict[str, object]:
    active = {packet["id"]: packet for packet in manifest["packets"]}
    total = sum(int(packet["progress_weight"]) for packet in active.values())
    verified = sum(
        int(active[packet_id]["progress_weight"])
        for packet_id, state in packet_states.items()
        if packet_id in active and state["state"] == "verified"
    )
    percent = round(verified / total * 100, 2)
    return {
        "verified_weight": verified,
        "active_planned_weight": total,
        "percent": percent,
        "display_percent": 100 if completed else min(99, int(percent)),
    }
```

`evidence.observed`, `context.refreshed`, `runtime.heartbeat`, and `codex_app_server` events remain informational. `packet.verified` must reference evidence whose workflow/packet binding and required evidence kinds match the manifest.

- [ ] **Step 5: Run core and schema tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_core.py" -v`

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_schemas.py" -v`

Expected: both commands PASS.

- [ ] **Step 6: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/goal_progress_core.py tests/goal_progress`

Expected: replay, transition, evidence, and percentage behavior only; ETA timing is still `Calculating...`. If approved:

```text
git add scripts/goal_progress_core.py tests/goal_progress/support.py tests/goal_progress/test_goal_progress_core.py
git commit -m "feat: reduce verified goal progress"
```

### Task 4: Add Replay-Safe ETA, Staleness, and Sanitization

**Files:**
- Modify: `scripts/goal_progress_core.py`
- Modify: `tests/goal_progress/test_goal_progress_core.py`

**Interfaces:**
- Consumes: accepted event durations stamped by the writer.
- Produces:
  - `calculate_eta(manifest, packet_states, completed_timings, *, active_packet_count) -> dict[str, object]`
  - `derive_stale(manifest, events, *, now_utc: str) -> tuple[bool, str | None]`
  - deterministic `low|medium|high` confidence and factor clipped to `0.5-3.0`.

- [ ] **Step 1: Add RED ETA and stale tests**

Use fixed duration fixtures and assert:

```python
def test_eta_uses_median_calibration_and_clips_factor(self) -> None:
    eta = calculate_eta(
        manifest_with_estimates((60, 120), (120, 240)),
        packet_states={"p1": {"state": "verified"}, "p2": {"state": "queued"}},
        completed_timings=[{"packet_id": "p1", "actual_seconds": 450, "estimated_midpoint_seconds": 90}],
        active_packet_count=0,
    )

    self.assertEqual(3.0, eta["calibration_factor"])
    self.assertEqual(360, eta["low_seconds"])
    self.assertEqual(720, eta["high_seconds"])
    self.assertEqual("low", eta["confidence"])
```

Add tests for zero observations, two to four samples, five stable samples, five high-dispersion samples, waiting/blocked/stale pause reasons, writer epoch gap warnings, confidence non-increase across an epoch, plan-revision confidence reset, no estimate showing `Calculating...`, and two running packets returning `status: BLOCKED`, `reason: unsupported_parallel_timing`.

- [ ] **Step 2: Run the ETA subset and confirm RED**

Run: `python -B -m unittest tests.goal_progress.test_goal_progress_core.GoalProgressEtaTests -v`

Expected: FAIL because ETA calculation and stale derivation are not implemented.

- [ ] **Step 3: Implement calibration and confidence**

Use `statistics.median` and this relative median absolute deviation:

```python
def _relative_mad(values: list[float]) -> float:
    center = statistics.median(values)
    if center == 0:
        return 0.0
    return statistics.median(abs(value - center) for value in values) / abs(center)


def _confidence(ratios: list[float]) -> str:
    if len(ratios) <= 1:
        return "low"
    if len(ratios) <= 4:
        return "medium"
    return "high" if _relative_mad(ratios) <= 0.35 else "medium"
```

Clip the median ratio with `min(3.0, max(0.5, median_ratio))`. Sum only remaining serial packet ranges. Exclude waiting, blocked, stale, and cross-epoch gaps from actual active time.

- [ ] **Step 4: Implement the freshness rule and summary sanitizer**

Freshness seconds are `max(900, high_estimate * 2)` when the active packet has an estimate and `1800` otherwise. Parse only UTC `Z` timestamps. `sanitize_summary()` must normalize CR/LF/control characters, redact case-insensitive key/token/password/authorization assignments, HTML-escape only at rendering time, cap stored summaries at 500 characters, and return warning codes separately.

- [ ] **Step 5: Run core tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_core.py" -v`

Expected: PASS, including deterministic fake-clock cases.

- [ ] **Step 6: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/goal_progress_core.py tests/goal_progress/test_goal_progress_core.py`

Expected: ETA/stale/sanitization only. If approved:

```text
git add scripts/goal_progress_core.py tests/goal_progress/test_goal_progress_core.py
git commit -m "feat: forecast replay-safe goal eta"
```

### Task 5: Build the Append-Only Store and Exclusive Writer

**Files:**
- Create: `scripts/goal_progress_store.py`
- Create: `tests/goal_progress/test_goal_progress_store.py`
- Modify: `tests/goal_progress/support.py`

**Interfaces:**
- Consumes: `goal_progress_core` validation/reduction.
- Produces:
  - `GoalPaths.from_root(goal_root: Path) -> GoalPaths`
  - `GoalLock(path: Path, *, timeout_seconds: float = 5.0)`
  - `ProgressWriter(goal_root: Path, submission_capability: str, clock: Clock)`
  - `ProgressWriter.accept(candidate: dict[str, object], presented_capability: str) -> dict[str, object]`
  - `replay_goal(goal_root: Path, *, now_utc: str) -> dict[str, object]`
  - `atomic_write_json(path: Path, value: object) -> None`

- [ ] **Step 1: Add RED storage tests**

Cover: exclusive lock refusal, sequential stamping, wrong capability, stale expected sequence, exact duplicate ID idempotence, conflicting duplicate quarantine, truncated final line quarantine, invalid transition quarantine, wrong hash rejection during replay, atomic `goal.json`/`state.json` replacement, and rebuild with both derived files deleted.

The idempotence test must assert only one physical JSONL record:

```python
first = writer.accept(candidate, presented_capability="submit-secret")
second = writer.accept(candidate, presented_capability="submit-secret")
self.assertEqual(first, second)
self.assertEqual(1, len(paths.progress.read_text(encoding="utf-8").splitlines()))
```

- [ ] **Step 2: Run storage tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_store.py" -v`

Expected: FAIL with missing `scripts.goal_progress_store`.

- [ ] **Step 3: Implement safe Goal paths and atomic writes**

`GoalPaths` must expose `progress`, `goal`, `state`, `integration_status`, `context`, `logs`, `quarantine`, `runtime`, `writer_info`, and `server_info`. Reject missing roots, traversal, symlinks, junctions, mount points, and Windows reparse points before every sensitive read/write. Write derived JSON through a same-directory temporary file, flush, `os.fsync`, then `os.replace`.

- [ ] **Step 4: Implement the persistent writer contract**

Use an injectable clock:

```python
class Clock(Protocol):
    def utc_now(self) -> str: ...
    def monotonic(self) -> float: ...


class ProgressWriter:
    def __init__(self, goal_root: Path, submission_capability: str, clock: Clock) -> None:
        self.paths = GoalPaths.from_root(goal_root)
        self.submission_capability = submission_capability
        self.clock = clock
        self.epoch_id = str(uuid.uuid4())
        self.epoch_started = clock.monotonic()
```

The writer stamps `sequence`, UTC time, epoch ID, monotonic offset, record hash, and accumulated active-duration payload fields. It flushes the accepted JSONL record before replacing derived files. On restart it replays prior records, creates a new epoch, and adds an ETA epoch-gap warning without counting downtime.

- [ ] **Step 5: Run storage and core tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_store.py" -v`

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_core.py" -v`

Expected: both commands PASS.

- [ ] **Step 6: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/goal_progress_store.py tests/goal_progress`

Expected: append/replay/recovery only; no network listener. If approved:

```text
git add scripts/goal_progress_store.py tests/goal_progress/support.py tests/goal_progress/test_goal_progress_store.py
git commit -m "feat: persist append-only goal events"
```

### Task 6: Add the Goal Runtime and CLI

**Files:**
- Create: `scripts/goal_progress_server.py`
- Create: `scripts/goal_progress.py`
- Create: `tests/goal_progress/test_goal_progress_cli.py`
- Modify: `tests/goal_progress/support.py`

**Interfaces:**
- Consumes: `ProgressWriter`, goal schemas, and explicit filesystem paths.
- Produces CLI commands:
  - `preflight --manifest <file> --goal-root <dir> --json`
  - `init --manifest <file> --goal-root <dir> [--idle-timeout-seconds <positive-int>] --json`
  - `emit --goal-root <dir> --candidate <file> --json`
  - `status --goal-root <dir> --json`
  - `list --repository-root <dir> --json`
  - `open --goal-root <dir> --view compact|full --json`
  - `stop-runtime --goal-root <dir> --json`
  - internal `serve --goal-root <dir> --runtime-token-file <file> --idle-timeout-seconds <positive-int>`

- [ ] **Step 1: Add RED CLI and runtime identity tests**

Use `main(argv)` with captured stdout. Assert `preflight` performs validation without creating the Goal directory; `init` defaults idle timeout to `1800`, rejects zero/negative timeout values, returns `goal_id`, `goal_root`, `writer_status`, and no reusable credential; `emit` rejects wrong goal/plan/authority; `list` returns bounded sessions; `open` refuses ambiguous active goals; runtime reuse requires a successful private health response matching PID, resolved root, port, epoch, and instance nonce; and `stop-runtime` authenticates, preserves `progress.jsonl`/derived evidence, closes the listener, releases the lock, and returns an idempotent already-stopped result on a second call.

- [ ] **Step 2: Run CLI tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_cli.py" -v`

Expected: FAIL because the CLI and runtime do not exist.

- [ ] **Step 3: Implement the private writer listener**

In `goal_progress_server.py`, create a private `ThreadingHTTPServer` on `127.0.0.1` with:

```text
GET  /health   Authorization: Bearer <submission capability>
POST /events   Authorization: Bearer <submission capability>
POST /shutdown Authorization: Bearer <submission capability>
```

`/health` returns only `goal_root`, `pid`, `writer_epoch_id`, and `instance_nonce`. `/events` accepts at most 256 KiB, rejects non-JSON and unknown fields, and calls `ProgressWriter.accept()` under a process-local mutex. `/shutdown` is private, requires the same ignored runtime capability, accepts no body, stops both listeners, flushes derived state, and releases the Goal lock. No private route echoes a capability.

- [ ] **Step 4: Implement deterministic CLI JSON output and detached startup**

Use `subprocess.Popen` without `shell=True`. On Windows combine `CREATE_NO_WINDOW | DETACHED_PROCESS`; on POSIX use `start_new_session=True`. Redirect process stdout/stderr to `subprocess.DEVNULL`. Poll `writer-info.json` and authenticated `/health` for at most five seconds. If readiness fails, return exit `2` with `status: BLOCKED` and the sanitized reason.

Default idle timeout is `1800` seconds and resets only on an accepted private event or authenticated dashboard request. A terminal Goal does not force immediate shutdown, so the operator can inspect final evidence; `stop-runtime` is the explicit restore command, and idle shutdown is the fallback. `stop-runtime` reads the ignored capability locally, verifies `/health` identity before `POST /shutdown`, waits at most five seconds, then removes only runtime token/server metadata after confirmed exit. It never deletes Goal evidence.

Root execution imports `scripts.goal_progress_*`; bundled execution falls back to sibling imports:

```python
try:
    from scripts.goal_progress_core import GoalProgressError
    from scripts.goal_progress_server import ensure_runtime
except ModuleNotFoundError:
    from goal_progress_core import GoalProgressError
    from goal_progress_server import ensure_runtime
```

- [ ] **Step 5: Run CLI tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_cli.py" -v`

Expected: PASS using in-process ephemeral loopback servers; tests leave no background process.

- [ ] **Step 6: Run report-only preflight against a fixed local fixture**

Write the valid manifest fixture into a temporary test directory, then run through the test harness:

Run: `python -B -m unittest tests.goal_progress.test_goal_progress_cli.GoalProgressCliTests.test_preflight_is_report_only -v`

Expected: PASS and no `evidence/local/goals/goal-demo-001` directory.

- [ ] **Step 7: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/goal_progress.py scripts/goal_progress_server.py tests/goal_progress`

Expected: private runtime and CLI only; public dashboard routes are not enabled yet. If approved:

```text
git add scripts/goal_progress.py scripts/goal_progress_server.py tests/goal_progress/support.py tests/goal_progress/test_goal_progress_cli.py
git commit -m "feat: run goal progress writer"
```

### Task 7: Implement Deterministic Context Projections

**Files:**
- Create: `scripts/context_brief.py`
- Create: `tests/goal_progress/test_context_brief.py`

**Interfaces:**
- Consumes: `state.json`, `goal.json`, evidence references, decisions, failures, blockers, changed files, and next action.
- Produces:
  - `ContextProjectionError(ValueError)`
  - `ProjectionKind = Literal["brief", "working", "resume"]`
  - `build_projection(state: dict[str, object], manifest: dict[str, object], kind: ProjectionKind, *, tokenizer: Callable[[str], int] | None = None) -> dict[str, object]`
  - `validate_projection(projection: dict[str, object], *, tokenizer: Callable[[str], int] | None = None) -> None`
  - `write_projections(goal_root: Path, *, tokenizer: Callable[[str], int] | None = None) -> list[Path]`
  - CLI `context_brief.py --goal-root <dir> --projection all|brief|working|resume --json`.

- [ ] **Step 1: Add RED priority and budget tests**

Assert the exact priority order: safety/scope/negations/blockers; active packet/next action; paths/commands/errors/artifacts/evidence labels; decisions/dependencies/deduplicated history. Include these literals and require byte-for-byte preservation:

```python
EXACT_LITERALS = (
    "D:/work/game/Assets/UI/HUD.prefab",
    'python -B scripts/validate.py .',
    "Shader.Find returned null",
    "do NOT edit Assets/Production",
    "150 ms",
    "BLOCKED",
)
```

Add a single 350-byte indivisible path to the `brief` input and assert `status == "BLOCKED"`, empty standalone `text`, and a non-empty `required_fact_refs`. Add fallback tests whose UTF-8 byte count never exceeds `300`, `1200`, or `2400`. Tamper a valid projection's numeric `count` and separately its `hard_cap`, then assert `validate_projection()` rejects both instead of trusting schema-only validation.

- [ ] **Step 2: Run context tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_context_brief.py" -v`

Expected: FAIL because `scripts.context_brief` does not exist.

- [ ] **Step 3: Implement fact selection and fitting**

Represent facts with stable priority/order and never paraphrase protected literals:

```python
@dataclass(frozen=True)
class ContextFact:
    ref: str
    priority: int
    order: int
    text: str
    indivisible: bool = False


PROJECTION_LIMITS = {
    "brief": (150, 300),
    "working": (800, 1200),
    "resume": (1600, 2400),
}
```

Implement this file with Python standard library only; do not import `goal_progress_core.py` or another repository-local helper because the distributed context skill bundles only `context_brief.py`. When `tokenizer` is supplied, record `count_kind: exact_tokenizer` and enforce the exact hard cap. Otherwise record `count_kind: utf8_byte_fallback`, enforce UTF-8 bytes at most the numeric cap, and set `evidence_label: Unverified` for target-runtime token count. `validate_projection()` recomputes the measurement from `text`, requires exact equality with `count`, and enforces `count <= hard_cap`. Never summarize raw transcripts by default.

- [ ] **Step 4: Write atomic JSON and Markdown projections**

Write `context/<kind>.json` using the projection schema and `context/<kind>.md` with normal readable prose. `resume` includes a visible sentence that `studio-handoff` must refresh Git state, commands, restore information, and the reactivation prompt before durable transfer.

- [ ] **Step 5: Run context tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_context_brief.py" -v`

Expected: PASS for all three projection sizes and the `BLOCKED` overflow case.

- [ ] **Step 6: Run the Caveman originality comparison**

Run: `python -B scripts/check_originality.py . "C:\Users\MAD\.agents\skills\caveman"`

Expected: exit `0` and no undeclared overlap. If the installed source is unavailable, record lifecycle audit `BLOCKED`; do not weaken the provenance test or copy source text.

- [ ] **Step 7: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/context_brief.py tests/goal_progress/test_context_brief.py`

Expected: deterministic projection logic only. If approved:

```text
git add scripts/context_brief.py tests/goal_progress/test_context_brief.py
git commit -m "feat: project compact goal context"
```

### Task 8: Add the Secured Read-Only Dashboard and SSE

**Files:**
- Create: `resources/goal-progress/index.html`
- Create: `resources/goal-progress/styles.css`
- Create: `resources/goal-progress/app.js`
- Create: `tests/goal_progress/test_goal_progress_server.py`
- Modify: `scripts/goal_progress_server.py`
- Modify: `scripts/goal_progress.py`

**Interfaces:**
- Consumes: reduced state, context JSON, event summaries, and public session metadata.
- Produces public routes:
  - `GET /open?token=<single-use>&view=compact|full`
  - `GET /compact`
  - `GET /full`
  - `GET /assets/styles.css`
  - `GET /assets/app.js`
  - `GET /api/state`
  - `GET /api/events` with `text/event-stream`
  - `GET /artifact?path=<goal-relative>`

- [ ] **Step 1: Add RED authentication and artifact tests**

Start the public server in a test thread on port `0`. Use `urllib.request.HTTPCookieProcessor` and assert: unauthorized state is `401`; bootstrap sets `HttpOnly`, `SameSite=Strict`, `Path=/`; token reuse is `401`; redirect target contains no token; all authenticated responses contain `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, CSP, and `X-Content-Type-Options: nosniff`; POST/PUT/DELETE return `405`; traversal and reparse paths return `403`; HTML/SVG artifacts use attachment disposition; JSON/log text is escaped or returned as inert text.

- [ ] **Step 2: Run server tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_server.py" -v`

Expected: FAIL because public routes and assets are absent.

- [ ] **Step 3: Create the dashboard shell and intentional visual system**

`index.html` contains one semantic application shell with `data-view` switching, an accessible live status region, packet table, timeline, ETA basis, context tabs, and integration status. It imports only `/assets/styles.css` and `/assets/app.js`; no inline script, remote font, image, analytics, or CDN.

Use these canonical CSS tokens:

```css
:root {
  --paper: #f3ead8;
  --paper-deep: #dfcfb2;
  --ink: #1f2825;
  --muted: #6f756c;
  --brand: #c4552d;
  --brand-dark: #7d2d18;
  --signal: #24746b;
  --danger: #a1342f;
  --line: rgba(31, 40, 37, 0.18);
  --display: Georgia, "Times New Roman", serif;
  --body: "Trebuchet MS", Verdana, sans-serif;
  --mono: Consolas, "Courier New", monospace;
}
```

Use a ledger/grid background, a large numeric progress dial, one page-load reveal, and staggered packet rows. At `max-width: 720px`, collapse the two-column dashboard to one column, keep the active packet first, and preserve a minimum 44px control target. Respect `prefers-reduced-motion`.

- [ ] **Step 4: Implement safe browser rendering and SSE recovery**

`app.js` uses `textContent`, never `innerHTML`, for runtime values. It fetches `/api/state` on load and after every SSE reconnect. `EventSource('/api/events')` triggers a state refresh for `state` events. Tabs and filters modify only local view state. No code issues POST/PUT/DELETE requests.

- [ ] **Step 5: Implement bootstrap, cookies, headers, assets, and artifacts**

Generate a 32-byte session key and 24-byte one-time token with `secrets.token_urlsafe`. Token lifetime is 60 seconds. The bootstrap route consumes the token, sets the cookie, and returns `303` to `/compact` or `/full`. Asset discovery checks root execution at `resources/goal-progress/` and bundled execution at the owning skill's `assets/` directory.

The CSP is:

```text
default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'
```

- [ ] **Step 6: Run server, CLI, and static checks and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_server.py" -v`

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_cli.py" -v`

Run: `rg -n "innerHTML|https?://|<form|method=|fetch\([^)]*," resources/goal-progress`

Expected: both unit-test commands PASS. The search returns no runtime `innerHTML`, remote dependency, form, or mutating fetch usage.

- [ ] **Step 7: Review diff and request checkpoint commit approval**

Run: `git diff -- resources/goal-progress scripts/goal_progress_server.py scripts/goal_progress.py tests/goal_progress/test_goal_progress_server.py`

Expected: secured public read surface only. If approved:

```text
git add resources/goal-progress scripts/goal_progress_server.py scripts/goal_progress.py tests/goal_progress/test_goal_progress_server.py
git commit -m "feat: show secured goal progress dashboard"
```

### Task 9: Normalize Optional Codex App Server Observations

**Files:**
- Create: `scripts/goal_progress_app_server.py`
- Create: `tests/goal_progress/fixtures/app-server-supported.jsonl`
- Create: `tests/goal_progress/fixtures/app-server-unknown.jsonl`
- Create: `tests/goal_progress/test_goal_progress_app_server.py`

**Interfaces:**
- Consumes: newline-delimited JSON-RPC messages from a client-owned initialized transport.
- Produces:
  - `build_initialize_request(request_id: int, client_version: str) -> dict[str, object]`
  - `build_initialized_notification() -> dict[str, object]`
  - `normalize_notification(message, binding) -> list[dict[str, object]]`
  - `consume_notifications(lines, binding, *, runtime_version) -> tuple[list[dict[str, object]], dict[str, object]]`

- [ ] **Step 1: Add RED App Server contract tests**

The supported fixture includes `thread/started`, `thread/status/changed`, `turn/started`, `turn/plan/updated`, `item/started` and `item/completed` for `commandExecution`, `turn/completed`, and `thread/tokenUsage/updated`. Assert every normalized candidate uses `source: codex_app_server`, is informational, contains no authority, never emits `packet.verified`, and redacts command output.

The unknown fixture includes one recognized event with an added unknown required shape and one unknown method. Assert integration status becomes `BLOCKED`, portable candidates before the incompatibility remain readable, and no workflow state changes.

- [ ] **Step 2: Run App Server tests and confirm RED**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_app_server.py" -v`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement handshake and strict allowlist**

Allow these stable notification families only:

```python
SUPPORTED_METHODS = frozenset({
    "thread/started",
    "thread/status/changed",
    "turn/started",
    "turn/completed",
    "turn/plan/updated",
    "item/started",
    "item/completed",
    "thread/tokenUsage/updated",
    "warning",
    "configWarning",
})
```

Initialization uses `clientInfo.name: gamestudio_codexkit`, title `GameStudio-CodexKIT Goal Progress`, and supplied version. Do not set `experimentalApi`. Record runtime version and recognized methods in `integration-status.json`.

- [ ] **Step 4: Enforce the desktop attachment boundary**

If the caller supplies only a thread ID and no initialized transport, return:

```json
{
  "status": "BLOCKED",
  "reason": "desktop_transport_unavailable",
  "portable_progress_available": true
}
```

Do not spawn, interrupt, resume, fork, or start a Codex thread automatically. A later host integration may feed the same normalizer through a documented transport.

- [ ] **Step 5: Run adapter tests and confirm GREEN**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_goal_progress_app_server.py" -v`

Expected: PASS with informational-only candidates and honest incompatible-schema degradation.

- [ ] **Step 6: Optionally compare current generated App Server schemas**

Run only when `codex app-server generate-json-schema --help` exits `0`:

```text
codex app-server generate-json-schema --out evidence/local/app-server-schema-2026-09-04
```

Expected: generated files remain ignored local evidence. If the command or runtime is unavailable, record this optional check as `BLOCKED`; fixture tests remain the deterministic gate.

- [ ] **Step 7: Review diff and request checkpoint commit approval**

Run: `git diff -- scripts/goal_progress_app_server.py tests/goal_progress`

Expected: optional adapter and sanitized fixtures only. If approved:

```text
git add scripts/goal_progress_app_server.py tests/goal_progress/fixtures tests/goal_progress/test_goal_progress_app_server.py
git commit -m "feat: normalize codex runtime observations"
```

### Task 10: Author the Two Skills and Evaluation Contracts

**Files:**
- Create: `skills/studio-goal-progress/SKILL.md`
- Create: `skills/studio-goal-progress/agents/openai.yaml`
- Create: `skills/studio-context-brief/SKILL.md`
- Create: `skills/studio-context-brief/agents/openai.yaml`
- Create: `evals/routing/studio-goal-progress.json`
- Create: `evals/routing/studio-context-brief.json`
- Create: `evals/behavior/studio-goal-progress.json`
- Create: `evals/behavior/studio-context-brief.json`
- Create: `evals/pressure/studio-goal-progress-guardrails.json`
- Create: `evals/pressure/studio-context-brief-guardrails.json`
- Modify: `skills/using-game-studio-skills/SKILL.md`
- Modify: `skills/feature-to-work-packets/SKILL.md`
- Modify: `registry/capabilities.yaml`
- Modify: `registry/packs.yaml`
- Modify: `tests/packaging/test_skill_resources.py`

**Interfaces:**
- Consumes: implemented helpers and approved design authority.
- Produces: two experimental `studio-core` skills with distinct triggers and no new agent role.

- [ ] **Step 1: Add routing files and a focused registration contract before skill descriptions**

Use exactly six cases per skill. Progress prompts must cover `Open Progress`, verified weighted percentage/ETA, and append-only KIT Goal recovery. Negative owners are `feature-to-work-packets` and `studio-handoff`. The collision prompt is: `Open the active KIT Goal progress GUI, but never infer completion percentage from commentary or elapsed wall time`.

Context prompts must cover compact active Goal context, exact technical literal preservation, and the three projections. Negative owners are `studio-project-intake` and `studio-handoff`. The collision prompt is: `Create compact working context for the active Goal while keeping durable handoff authority in studio-handoff`.

Add `SkillResourcePackagingTests.test_goal_progress_capabilities_and_pack_membership_are_registered` to `tests/packaging/test_skill_resources.py`. It loads capabilities and packs by ID and asserts both exact capability dictionaries from Step 8, each ID appears exactly once in `studio-core`, and both canonical `SKILL.md` paths exist.

- [ ] **Step 2: Run the focused governance contract and confirm RED**

Run: `python -B -m unittest tests.packaging.test_skill_resources.SkillResourcePackagingTests.test_goal_progress_capabilities_and_pack_membership_are_registered -v`

Expected: FAIL because the new capability IDs, pack membership, and canonical skill paths do not exist. Do not use `route_eval.py` as this RED gate: it intentionally ignores routing files for unregistered capabilities.

- [ ] **Step 3: Write `studio-goal-progress` with closed workflow boundaries**

Use this frontmatter contract:

```yaml
name: studio-goal-progress
description: Use when a KIT-managed Codex or Hermes Goal needs evidence-backed percentage, ETA range, live read-only progress views, or portable append-only progress recovery.
version: 0.1.0
author: GameStudio-CodexKIT
license: MIT
compatibility:
  engines: [engine-agnostic]
  versions: [any]
  platforms: [windows, linux, macos]
metadata:
  studio:
    type: interactive
    lifecycle_stage: operate
    risk_level: low
    packs: [studio-core]
    side_effects: files
    artifact: progress.jsonl
    required_evidence: [goal-manifest, progress-events, reduced-state]
    owner: HoaTV Studio
    reviewer: null
    maturity: experimental
    last_reviewed: 2026-09-04
    provenance:
      derived_from: none
      patterns_from: [Codex App Server documented lifecycle events, AGENTS.md evidence labels]
      copied_text: none
```

The workflow must require `preflight` before initialization, weighted packets, explicit Goal opt-in, meaningful-boundary events, manual GUI opening, `BLOCKED` degradation, and final evidence card. Its references section names all bundled helpers: `scripts/goal_progress.py`, `scripts/goal_progress_core.py`, `scripts/goal_progress_store.py`, `scripts/goal_progress_server.py`, and `scripts/goal_progress_app_server.py`.

- [ ] **Step 4: Write `studio-context-brief` with declared Caveman provenance**

Use the same common metadata, with type `workflow`, lifecycle `operate`, artifact `context/working.json`, required evidence `[goal-manifest, reduced-state, projection-report]`, and:

```yaml
provenance:
  derived_from:
    repo: JuliusBrussee/caveman
    path: skills/caveman/SKILL.md
    commit: b4335705d436f5110386a1c39c6d8aed5002aeeb
    license: MIT
  patterns_from: [precision and compression principles only]
  copied_text: none
```

The workflow must preserve exact literals, refuse arbitrary transcript compression by default, emit `BLOCKED` on indivisible overflow, and state that `studio-handoff` remains durable-transfer authority. Reference `scripts/context_brief.py` and both bundled schemas.

- [ ] **Step 5: Add branded OpenAI metadata**

Use:

```yaml
interface:
  display_name: "MOStudio Kit: Studio Goal Progress"
  short_description: "Evidence-backed Goal progress and read-only live dashboard"
  default_prompt: "Use $studio-goal-progress to initialize or open progress for this explicit KIT-managed Goal using verified weighted packets and honest ETA ranges."
```

```yaml
interface:
  display_name: "MOStudio Kit: Studio Context Brief"
  short_description: "Exact compact context projections for active studio Goals"
  default_prompt: "Use $studio-context-brief to generate brief, working, and resume context projections from trusted structured Goal state without replacing studio-handoff."
```

- [ ] **Step 6: Add behavior and pressure cases**

Progress behavior IDs: `goal-progress-weighted-verification`, `goal-progress-plan-recalculation`, `goal-progress-eta-paused`, `goal-progress-app-server-blocked`, and `goal-progress-gui-read-only`. Pressure IDs: `goal-progress-fabricated-percent-blocked`, `goal-progress-secret-output-blocked`, `goal-progress-traversal-blocked`, `goal-progress-mutating-control-blocked`, `goal-progress-arbitrary-task-blocked`, and `goal-progress-service-start-approval`.

Context behavior IDs: `context-priority-preserved`, `context-three-projections`, `context-fallback-labeled`, `context-overflow-blocked`, and `context-handoff-authority`. Pressure IDs: `context-raw-transcript-blocked`, `context-path-shortening-blocked`, `context-negation-loss-blocked`, `context-fabricated-evidence-blocked`, `context-cap-bypass-blocked`, and `context-handoff-replacement-blocked`.

Every behavior/pressure case sets `allow_mutation: false`; expected verdicts are `PASS` only for deterministic artifact generation with all inputs present and `BLOCKED` for missing authority, unsupported integration, or requested boundary violation.

- [ ] **Step 7: Update root participation and work-packet fields**

In `using-game-studio-skills`, add an explicit KIT Goal branch that routes initialization/event/open actions to `studio-goal-progress`; ordinary tasks remain unchanged and missing progress capability is `BLOCKED`, never silently simulated. In `feature-to-work-packets`, add progress-enabled fields `workflow_id`, `owner`, positive integer `progress_weight`, optional `{low, high}` seconds, required evidence kinds, and timing policy `max_active_timed_packets: 1`. Existing plans without Goal opt-in remain valid.

- [ ] **Step 8: Register capabilities and pack membership**

Add exactly:

```yaml
- id: studio-goal-progress
  path: skills/studio-goal-progress/SKILL.md
  type: interactive
  packs: [studio-core]
  risk_level: low
  maturity: experimental
  depends_on: [using-game-studio-skills]
- id: studio-context-brief
  path: skills/studio-context-brief/SKILL.md
  type: workflow
  packs: [studio-core]
  risk_level: low
  maturity: experimental
  depends_on: [studio-goal-progress]
```

Add each ID once to `studio-core`; do not add a role, persona, or project-local maintenance ID.

- [ ] **Step 9: Run structural, routing, behavior, and pressure checks**

Run: `python -B scripts/validate.py .`

Run: `python -B scripts/route_eval.py .`

Run: `python -B scripts/runner_eval.py --help`

Run: `python -B -m unittest tests.packaging.test_skill_resources.SkillResourcePackagingTests.test_goal_progress_capabilities_and_pack_membership_are_registered -v`

Expected: focused governance and validation PASS. Routing reaches `328/328`; if rank-1 collisions occur, strengthen unique trigger wording without changing negative owners or deleting cases. Runner help exits `0`; governed behavior/pressure execution remains a later runner-backed gate.

- [ ] **Step 10: Review diff and request checkpoint commit approval**

Run: `git diff -- skills/studio-goal-progress skills/studio-context-brief skills/using-game-studio-skills/SKILL.md skills/feature-to-work-packets/SKILL.md registry/capabilities.yaml registry/packs.yaml evals/routing evals/behavior evals/pressure tests/packaging/test_skill_resources.py`

Expected: two new skills, two bounded existing-skill updates, twelve routing cases, behavior/pressure contracts, and no agent role. If approved:

```text
git add skills/studio-goal-progress/SKILL.md skills/studio-goal-progress/agents/openai.yaml skills/studio-context-brief/SKILL.md skills/studio-context-brief/agents/openai.yaml skills/using-game-studio-skills/SKILL.md skills/feature-to-work-packets/SKILL.md registry/capabilities.yaml registry/packs.yaml evals/routing/studio-goal-progress.json evals/routing/studio-context-brief.json evals/behavior/studio-goal-progress.json evals/behavior/studio-context-brief.json evals/pressure/studio-goal-progress-guardrails.json evals/pressure/studio-context-brief-guardrails.json tests/packaging/test_skill_resources.py
git commit -m "feat: add goal progress and context skills"
```

### Task 11: Bundle Standalone Resources, Version the Plugin, and Synchronize Public Catalogs

**Files:**
- Modify: `registry/skill-resources.yaml`
- Generate: `skills/studio-goal-progress/scripts/*`
- Generate: `skills/studio-goal-progress/schemas/*`
- Generate: `skills/studio-goal-progress/assets/*`
- Generate: `skills/studio-context-brief/scripts/*`
- Generate: `skills/studio-context-brief/schemas/*`
- Modify: `tests/packaging/test_skill_resources.py`
- Modify: `.codex-plugin/plugin.json`
- Modify: `pyproject.toml`
- Modify: `tests/packaging/test_codex_plugin.py`
- Modify: `tests/packaging/test_packs_adapters.py`
- Modify: `tests/governance/test_review_contracts.py`
- Modify: `tests/studio_experience/test_studio_experience.py`
- Modify: `README.md`
- Modify: `docs/CATALOG.md`
- Modify: `docs/index.html`
- Modify: `docs/assets/banner.svg`
- Modify: `docs/huong-dan-su-dung-skill-agent.md`
- Modify: `docs/wiki-skill-agent-user-guide.md`
- Modify: `docs/adoption.md`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/architecture/project-init-and-studio-expansion.md`

**Interfaces:**
- Consumes: canonical helpers/assets/schemas and registry entries.
- Produces: self-contained Codex/Hermes skills, plugin `1.8.0`, `52` skills, `51` routed skills, and `328` routing cases.

- [ ] **Step 1: Add RED packaging expectations**

Add exact resource lists. `studio-goal-progress` receives five Python helpers, three Goal schemas, and three dashboard assets. `studio-context-brief` receives `context_brief.py`, `studio-goal-state.schema.json`, and `studio-context-projection.schema.json`. Add an isolated-copy test that imports both entry scripts and finds every schema/asset without the repository root.

Update expected counts/version:

```python
self.assertEqual(52, skill_count)
self.assertEqual(51, len([item for item in capabilities if item["type"] != "root"]))
self.assertEqual(328, routing.total)
self.assertEqual(328, routing.passed)
self.assertEqual("1.8.0", manifest_version)
self.assertEqual("1.8.0", pyproject_version)
```

The experimental set becomes `code-intelligence-contract`, `unity-ui-art-and-motion-production`, `game-screenshot-showcase-and-store-packaging`, `studio-goal-progress`, and `studio-context-brief`.

- [ ] **Step 2: Run packaging tests and confirm RED**

Run: `python -B -m unittest tests.packaging.test_skill_resources tests.packaging.test_codex_plugin -v`

Expected: FAIL because resource mappings, generated copies, counts, docs, and version are not synchronized.

- [ ] **Step 3: Add exact resource mappings and synchronize**

Map canonical files to:

```text
studio-goal-progress/scripts/goal_progress.py
studio-goal-progress/scripts/goal_progress_core.py
studio-goal-progress/scripts/goal_progress_store.py
studio-goal-progress/scripts/goal_progress_server.py
studio-goal-progress/scripts/goal_progress_app_server.py
studio-goal-progress/schemas/studio-goal-manifest.schema.json
studio-goal-progress/schemas/studio-goal-event.schema.json
studio-goal-progress/schemas/studio-goal-state.schema.json
studio-goal-progress/assets/index.html
studio-goal-progress/assets/styles.css
studio-goal-progress/assets/app.js
studio-context-brief/scripts/context_brief.py
studio-context-brief/schemas/studio-goal-state.schema.json
studio-context-brief/schemas/studio-context-projection.schema.json
```

Run: `python -B scripts/sync_skill_resources.py .`

Expected: generated copies contain format-appropriate ownership markers. Inspect them but never patch them manually.

- [ ] **Step 4: Update plugin version to `1.8.0`**

Change only `.codex-plugin/plugin.json` and `[project].version` in `pyproject.toml`. `.claude-plugin/marketplace.json` has no version field and remains unchanged.

- [ ] **Step 5: Synchronize public counts and skill documentation**

Change catalog facts to `52 canonical skills`, `24 canonical agent roles`, `7 packs`, and `328 deterministic eval cases`; architecture/adoption use `51 routed skills with 328 cases`. Add both skills to the English/Vietnamese guides, `docs/CATALOG.md`, and the `docs/index.html` skill data. Add concise usage examples:

```text
$studio-goal-progress Open Progress for the active KIT-managed Goal.
$studio-context-brief Build the working projection without replacing studio-handoff.
```

Keep both skills labeled `experimental`; catalog-wide beta adoption does not promote them. Update the banner text to `52 SKILLS` and `ROUTING 328/328`.

- [ ] **Step 6: Update every hard-coded test count discovered by the bounded search**

Run: `rg -n "50|316|49 routed" README.md docs tests -g "*.md" -g "*.html" -g "*.svg" -g "*.py"`

Update only catalog-count assertions/text. Do not alter unrelated values such as CSS percentages, image bytes, `0.9.50`, or numeric game fixtures. Required test files include `tests/packaging/test_packs_adapters.py`, `tests/governance/test_review_contracts.py`, and `tests/studio_experience/test_studio_experience.py`.

- [ ] **Step 7: Run packaging and routing checks and confirm GREEN**

Run: `python -B scripts/sync_skill_resources.py . --check`

Run: `python -B -m unittest tests.packaging.test_skill_resources tests.packaging.test_codex_plugin tests.governance.test_review_contracts -v`

Run: `python -B scripts/route_eval.py .`

Expected: sync check exit `0`; packaging/governance PASS; routing `328/328`.

- [ ] **Step 8: Review generated and public diff and request checkpoint commit approval**

Run: `git diff -- registry/skill-resources.yaml skills/studio-goal-progress skills/studio-context-brief .codex-plugin/plugin.json pyproject.toml README.md docs tests/packaging tests/governance/test_review_contracts.py tests/studio_experience/test_studio_experience.py`

Expected: generated resources match canonical owners, counts are exactly `52/24/7/328`, and version is exactly `1.8.0`. If approved:

```text
git add registry/skill-resources.yaml skills/studio-goal-progress skills/studio-context-brief .codex-plugin/plugin.json pyproject.toml README.md docs/CATALOG.md docs/index.html docs/assets/banner.svg docs/huong-dan-su-dung-skill-agent.md docs/wiki-skill-agent-user-guide.md docs/adoption.md docs/architecture/overview.md docs/architecture/project-init-and-studio-expansion.md tests/packaging/test_skill_resources.py tests/packaging/test_codex_plugin.py tests/packaging/test_packs_adapters.py tests/governance/test_review_contracts.py tests/studio_experience/test_studio_experience.py
git commit -m "chore: package goal progress plugin update"
```

### Task 12: Verify Runtime UX, Repository Gates, and Handoff

**Files:**
- Create ignored evidence: `evidence/local/goals/goal-progress-dogfood/`
- Create ignored evidence: `evidence/local/goal-progress-browser-review.json`
- Modify only if a verified failure identifies an owning source/test file from Tasks 1-11.

**Interfaces:**
- Consumes: completed canonical implementation and generated resources.
- Produces: exact command/exit-code evidence, browser interaction verdicts, optional App Server status, and final handoff without commit/push authorization.

- [ ] **Step 1: Run focused deterministic suites**

Run: `python -B -m unittest discover -s tests/goal_progress -p "test_*.py" -v`

Expected: PASS with no persistent listener after tests.

- [ ] **Step 2: Run all required local gates**

Run each command separately and record exit code:

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

Expected: every command exits `0`. A failure is `FAIL`, not a partial PASS; repair the owning source and rerun the affected cluster, then rerun all eight gates.

- [ ] **Step 3: Run lifecycle audits honestly**

Run:

```text
python -B scripts/check_originality.py . "C:\Users\MAD\.agents\skills\caveman"
python -B scripts/catalog_audit.py .
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
```

Expected: originality and catalog audit PASS when their sources/evidence are available. Governed dogfood status may remain `BLOCKED`; never promote either new skill beyond `experimental` from deterministic tests alone.

- [ ] **Step 4: Run service-control preflight without starting the runtime**

Create a fixed dogfood manifest for `goal-progress-dogfood`, then run:

```text
python -B scripts/goal_progress.py preflight --manifest evidence/local/goal-progress-dogfood-manifest.json --goal-root evidence/local/goals/goal-progress-dogfood --json
```

Expected: exit `0`, `status: READY`, resolved loopback plan, no created Goal directory, and no listener.

- [ ] **Step 5: Obtain explicit approval for the bounded launch-and-stop dogfood sequence**

Show the preflight result, exact Goal root, selected ephemeral ports policy, default `1800`-second idle timeout, terminal behavior, and exact restore command:

```text
python -B scripts/goal_progress.py stop-runtime --goal-root evidence/local/goals/goal-progress-dogfood --json
```

Explain that terminal completion keeps the runtime available for final GUI inspection, while explicit stop closes both listeners and preserves Goal evidence. Do not run `init` until the maintainer explicitly approves this bounded launch-and-stop service-control sequence.

- [ ] **Step 6: Initialize one bounded Goal and emit deterministic progress**

After approval, run:

```text
python -B scripts/goal_progress.py init --manifest evidence/local/goal-progress-dogfood-manifest.json --goal-root evidence/local/goals/goal-progress-dogfood --json
python -B scripts/goal_progress.py emit --goal-root evidence/local/goals/goal-progress-dogfood --candidate evidence/local/goal-progress-packet-started.json --json
python -B scripts/goal_progress.py emit --goal-root evidence/local/goals/goal-progress-dogfood --candidate evidence/local/goal-progress-evidence-observed.json --json
```

Expected: writer health is trusted, percentage remains `0`, and no reusable key appears in output.

- [ ] **Step 7: Open and inspect compact and full GUI projections**

Run:

```text
python -B scripts/goal_progress.py open --goal-root evidence/local/goals/goal-progress-dogfood --view compact --json
python -B scripts/goal_progress.py open --goal-root evidence/local/goals/goal-progress-dogfood --view full --json
```

Immediately pass each one-time URL to the Codex app panel-opening capability. Verify compact view has a clean redirected URL, visible percentage, ETA range/confidence or honest calculating state, active packet, last update, stale label behavior, and no Goal controls. Verify full view has packet table, revision/event timeline, ETA basis, context tabs, and integration status.

Resize below `720px`, verify one-column ordering and 44px targets, enable reduced motion, reconnect SSE after stopping only the browser connection, and verify state refresh. Record browser evidence in `evidence/local/goal-progress-browser-review.json`. If browser interaction is unavailable, GUI behavior remains `BLOCKED`; structural tests do not replace it.

- [ ] **Step 8: Verify terminal progress and context**

Emit the accepted `packet.verified` and `goal.completed` candidates, then run:

```text
python -B scripts/goal_progress.py emit --goal-root evidence/local/goals/goal-progress-dogfood --candidate evidence/local/goal-progress-packet-verified.json --json
python -B scripts/goal_progress.py emit --goal-root evidence/local/goals/goal-progress-dogfood --candidate evidence/local/goal-progress-goal-completed.json --json
python -B scripts/goal_progress.py status --goal-root evidence/local/goals/goal-progress-dogfood --json
python -B scripts/context_brief.py --goal-root evidence/local/goals/goal-progress-dogfood --projection all --json
```

Expected: completed percentage `100`, ETA terminal state, all six context files present, and `resume.md` still directs durable transfer through `studio-handoff`.

- [ ] **Step 9: Verify isolated Hermes-style copies**

Run the isolated-copy packaging tests that copy each new skill directory without repository root access.

Run: `python -B -m unittest tests.packaging.test_skill_resources.SkillResourcePackagingTests -v`

Expected: both skills import their bundled helpers and resolve all schemas/assets.

- [ ] **Step 10: Stop the bounded dogfood runtime**

Run the pre-approved restore command:

```text
python -B scripts/goal_progress.py stop-runtime --goal-root evidence/local/goals/goal-progress-dogfood --json
python -B scripts/goal_progress.py status --goal-root evidence/local/goals/goal-progress-dogfood --json
```

Expected: both commands exit `0`; stop returns `status: STOPPED`, private/public listeners close, Goal lock releases, runtime credential metadata is removed, and `progress.jsonl`, `goal.json`, `state.json`, context files, and browser-review evidence remain. Status then replays the preserved terminal state without starting a listener.

- [ ] **Step 11: Inspect final scope and produce the handoff**

Run:

```text
git status --short --branch
git diff --check
git diff --stat
git diff -- . ':!skills/*/scripts/*' ':!skills/*/schemas/*' ':!skills/*/assets/*'
python -B scripts/sync_skill_resources.py . --check
```

Report repository/path, branch, goal, owned scope, do-not-touch scope, files changed, commands and exit codes, generated artifacts, browser evidence, `Verified`, `Snapshot`, `Unverified`, `BLOCKED`, failures, restore information, next actions, and a reactivation prompt. Preserve `.superpowers/` and unrelated user work.

- [ ] **Step 12: Request final commit approval separately**

Do not commit automatically. If the maintainer authorizes one final integration commit, stage only the reviewed implementation/spec/plan paths and run:

```text
git commit -m "feat: add studio goal progress gui"
```

Push, publish, deployment, and release remain unauthorized until separately requested. Local PASS does not establish release readiness for the pushed commit or plugin version.

---

## Plan Self-Review

- Spec coverage: every authority, schema, replay, state, progress, ETA, security, GUI, context, App Server, distribution, maturity, and acceptance requirement maps to Tasks 1-12.
- Scope: progress and context remain one plan because context consumes the progress reduced-state contract; App Server remains an optional adapter rather than a separate required subsystem.
- Type consistency: helper names, event/state fields, projection kinds, CLI commands, paths, counts, and version values are identical across tasks.
- Runtime-only relations that JSON Schema cannot express are assigned to `validate_manifest()` and `validate_projection()` with explicit RED tests.
- Runtime lifecycle is closed: `init` has a fixed idle default, terminal state remains inspectable, and authenticated `stop-runtime` is the evidence-preserving restore path.
- Standalone packaging is closed: `context_brief.py` uses only Python standard library and needs no unbundled repository helper.
- RED gates are observable: Task 10 uses a focused registration/pack/path test because `route_eval.py` ignores unregistered capabilities by design.
- Ownership: root helpers/assets/schemas are canonical; generated skill copies are synchronized only by `scripts/sync_skill_resources.py`.
- Approval: implementation execution, every commit, real service launch, push, publish, and release retain explicit human gates.
