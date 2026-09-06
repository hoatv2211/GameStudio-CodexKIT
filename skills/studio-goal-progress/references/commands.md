# Studio Goal Progress Commands

These commands validate and operate one opted-in local Goal. They do not authorize project mutation, raw-log exposure, arbitrary task monitoring, browser launch, or service control. `init` may launch a detached private writer runtime and therefore needs explicit service-start approval immediately before execution. Browser or panel opening separately needs an explicit `Open Progress` request.

## Detect install shape

From a full kit clone, run modules from repository root so package imports resolve:

```powershell
python -B -m scripts.goal_progress --help
```

From a standalone installed skill, run its bundled entry point from the skill directory:

```powershell
python -B scripts/goal_progress.py --help
```

A missing helper or schema is `BLOCKED: incomplete skill installation`; do not switch to manually edited JSONL.

## Preflight before initialization

```powershell
python -B -m scripts.goal_progress preflight --manifest <manifest.json> --goal-root <goal-root> --json
```

Preflight success validates inputs; it does not prove work complete and does not approve service control. Runtime bindings may be absent or empty; declared bindings must be `codex_thread` or `hermes_session`. Packet `estimate_seconds` may be absent or null, in which case percentage remains available and ETA is `Calculating...`.

Immediately before the following command, obtain explicit operator approval to start or reuse the private writer runtime. Without that approval, return `BLOCKED` and do not run `init`:

```powershell
python -B -m scripts.goal_progress init --manifest <manifest.json> --goal-root <goal-root> --json
```

Run `init` only after the same manifest and root pass `preflight` and the immediate service-control approval is recorded. A valid manifest includes positive `progress_weight`, required evidence, and `timing_policy.max_active_timed_packets: 1`.

## Submit and read state

```powershell
python -B -m scripts.goal_progress emit --goal-root <goal-root> --candidate <candidate-event.json> --json
python -B -m scripts.goal_progress status --goal-root <goal-root> --json
python -B -m scripts.goal_progress list --repository-root <repository-root> --json
```

The candidate event must match Goal, plan, workflow, packet owner, any declared runtime binding, prior state, and required evidence. Never append `progress.jsonl` directly. `status` reduces the append-only stream; its verified weight drives percentage. `list` provides bounded path selection when an explicit Goal root is unavailable.

## Open read-only progress

After an explicit `Open Progress` request, resolve an explicit Goal root or one unique nonterminal Goal from the caller's declared manifest runtime binding before repository-level ambiguity fallback:

```powershell
python -B -m scripts.goal_progress open --goal-root <goal-root> --view compact --json
python -B -m scripts.goal_progress open --goal-root <goal-root> --view full --json
python -B -m scripts.goal_progress open --goal-root <repository-root> --runtime-binding-kind codex_thread --runtime-binding-id <thread-id> --view compact --json
python -B -m scripts.goal_progress open --goal-root <repository-root> --runtime-binding-kind hermes_session --runtime-binding-id <session-id> --view full --json
```

When binding-first resolution finds zero or multiple active Goals, use `list`, show the bounded candidates, and require an exact Goal-root selection. Reuse a healthy authenticated dashboard runtime without new service-control approval. Starting a stopped or missing runtime requires immediate explicit service-control approval; only then add `--approve-service-control` to the `open` command. Without that approval, return `BLOCKED` and do not start the runtime.

Python returns one one-time localhost URL with separate server, panel, and browser statuses; it never invokes a panel or browser API. After URL generation, the host agent opens the Codex panel when available or instructs manual browser use. The one-time URL is not permission to reveal reusable runtime credentials. An ambiguous Goal, missing start approval, failed runtime start, unavailable panel/browser, or unavailable App Server remains `BLOCKED` for that integration; core status may still work.

Stopping the viewer is service control and requires explicit approval:

```powershell
python -B -m scripts.goal_progress stop-runtime --goal-root <goal-root> --json
```

## Diagnostic order

1. Confirm explicit Goal opt-in and exact goal root.
2. Run `preflight`; do not diagnose event replay before manifest validity.
3. Run `status` to prove append-only replay and last-good reduced state.
4. Inspect percentage evidence bindings separately from ETA.
5. Resolve an explicit Goal path or one unique runtime-binding match before repository lookup; list and require selection when the result is not unique.
6. Reuse a healthy local viewer without new approval; require immediate explicit service-control approval before `open` starts a stopped or missing runtime.
7. Let Python return the one-time URL and integration statuses, then have the host open a panel or instruct manual browser use.

This order prevents optional GUI or App Server failure from being misdiagnosed as loss of portable progress authority.

## Evidence

Record command, exit code, goal root, manifest hash, plan version, last sequence, event and state paths, verified/planned weights, percentage, ETA status/range/confidence, stale flag, integration status, and redacted warnings. An unavailable runner, unsupported integration, missing approval, invalid evidence binding, or unresolved Goal is `BLOCKED`, never `PASS`.
