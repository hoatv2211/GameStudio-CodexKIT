# Studio Goal Progress and Context Brief Design

## Status

The hybrid adapter design and its written review corrections were approved by
the maintainer in conversation on 2026-09-04. The specification is the design
authority for implementation planning.

Repository snapshot at specification time:
<code>dev@f5c3576f97d5fd946fa92ba54c4dc3b97c9cc6c9</code>.

The only pre-existing worktree change observed before this specification was
the local Visual Companion session under <code>.superpowers/</code>. That
directory is brainstorming output, is not part of the proposed plugin payload,
and does not authorize changes to unrelated tracked or untracked files.

No implementation, generated-resource synchronization, plugin version change,
commit, push, publish, or release is authorized by this specification.

## Problem

GameStudio-CodexKIT has task packets, workflow-specific artifacts, normalized
evidence cards, and durable handoffs, but it has no common live progress
contract. During a long Codex Goal, the operator cannot reliably answer:

- Which work packet is active?
- How much verified work is complete?
- What is waiting for input, blocked, failed, or stale?
- Which evidence supports a completed packet?
- What completion-time range is currently forecast?
- What compact context should the current agent, GUI, or next session receive?

Codex App Server can emit thread, turn, item, and tool-progress notifications,
but a Codex-only event stream would not serve Hermes Agent and would couple the
kit's evidence model to one runtime. Conversely, a file-only reporter would be
portable but would omit useful Codex-native activity when App Server is
available.

The kit needs one portable source of truth, optional runtime adapters, two
read-only GUI projections, and a separate compact-context capability that does
not duplicate <code>studio-handoff</code>.

## Goals

1. Add a normalized, append-only progress event contract for KIT-managed goals.
2. Calculate progress from verified weighted work packets, never from elapsed
   wall time or unsupported model confidence.
3. Show a completion-time range and confidence separately from evidence-backed
   progress.
4. Provide a compact Codex panel and a full local web dashboard from the same
   reduced state.
5. Open the GUI only when the operator requests <code>Open Progress</code> or
   invokes the progress skill.
6. Enrich the portable KIT stream with Codex App Server notifications when that
   integration is available.
7. Keep the portable path usable in Codex CLI and Hermes Agent without App
   Server.
8. Add a separate compact-context skill inspired by Caveman's precision and
   compression principles while preserving exact technical meaning.
9. Keep <code>studio-handoff</code> authoritative for durable cross-session
   transfer.
10. Report unavailable integrations, stale state, and evidence gaps honestly.

## Non-goals

- Modifying the native Codex application UI.
- Automatically opening a panel or browser when every Goal starts.
- Adding Pause, Resume, Cancel, approval, mutation, or service-control buttons.
- Exposing raw stdout, stderr, credentials, or unrestricted artifact browsing.
- Treating percentage or ETA as verification evidence.
- Replacing workflow artifacts, evidence cards, or <code>HANDOFF.md</code>.
- Requiring Codex App Server for the core progress path.
- Monitoring arbitrary Codex tasks that did not opt into the KIT contract.
- Copying the Caveman skill, its modes, examples, prose, or runtime modules.
- Applying Caveman fragments to persisted specifications, reports, comments,
  handoffs, or other human-facing project documents.
- Adding a new agent role.
- Adding third-party runtime dependencies in the initial implementation.

## Selected Approach

Use hybrid adapters around an artifact-first canonical stream.

KIT workflows emit normalized events into an append-only local JSONL file. A
deterministic reducer derives current goal, packet, progress, ETA, evidence, and
context state. Both GUI projections read that reduced state. A Codex adapter
may add normalized observations from App Server lifecycle notifications. If
that adapter is unavailable or incompatible, the portable KIT stream continues
and the missing enrichment remains visible.

This approach is preferred over App Server-first integration because the kit
also targets Hermes Agent. It is preferred over a file-only design because
Codex-native events improve activity visibility without becoming authoritative
for workflow completion.

## Authority and Ownership

The existing authority order remains unchanged:

1. <code>AGENTS.md</code> owns repository operation, evidence, mutation,
   ownership, archive, and handoff rules.
2. Repository-local maintenance skills own kit-source maintenance behavior.
3. Registries own distributed capability, pack, resource, and provenance
   indexing.
4. Canonical distributed workflows live under <code>skills/</code>.
5. Root helpers under <code>scripts/</code> are canonical executable sources.
6. Bundled helpers and generated catalogs are derived outputs.

<code>studio-goal-progress</code> owns progress-session creation, event
validation, state reduction, GUI serving, and <code>Open Progress</code>.

<code>studio-context-brief</code> owns compact context projections from
structured goal state. It does not own source discovery, verification, mutation
authorization, or durable handoff.

The active workflow owns packet completion and evidence truth. The progress
layer may reject invalid evidence but may not promote a packet to
<code>verified</code> by inference.

One logical writer owns each goal event stream. The writer holds an exclusive
goal-local lock, serializes candidate submissions, validates the expected
prior state, appends one accepted record, flushes it, and updates derived state.
Workflows and runtime adapters submit candidate events through the writer API;
they never open or append the JSONL file directly. Dashboard, panel, context,
and handoff consumers are read-only. The main thread remains integration owner.

A source label is not authority. State-changing submissions must match the
workflow, packet owner, plan version, and any available runtime binding declared
by the active manifest, and must present the goal-local submission capability.
Verification events must also reference an accepted evidence record owned by
the active workflow. The writer prevents accidental or stale same-user
submissions; defending against a process already compromised under the same
operating-system user is outside the initial threat model.

## User Experience

### Starting a goal

A KIT-managed long-running goal declares:

- Goal identifier and title.
- Repository and snapshot.
- Plan version.
- Ordered work packets and positive weights.
- Completion criteria and required evidence.
- Optional low/high duration estimate per packet.
- Scope and do-not-touch boundaries.

Starting the goal does not open a GUI.

### Progress participation

The root <code>using-game-studio-skills</code> contract initializes a progress
session whenever the current task is explicitly running as a KIT-managed Goal.
Initialization records an available Codex thread ID or Hermes session identity
as a runtime binding in the goal manifest. Multiple tasks in one repository use
separate goal directories and never share an event writer.

The active workflow emits events only at meaningful boundaries: start, packet
transition, evidence observation, plan revision, context refresh, and terminal
goal state. An explicit bounded runtime heartbeat is the only liveness
exception for long-running operations. Ordinary commentary and raw tool output
do not become events.

<code>feature-to-work-packets</code> adds a positive
<code>progress_weight</code> for progress-enabled plans and may add low/high
duration estimates. Existing non-Goal plans remain valid without these fields.
When a progress-enabled plan lacks weights, progress initialization is
<code>BLOCKED</code>; it never silently assigns equal weights. When estimates
are absent, percentage remains available and ETA displays
<code>Calculating...</code>.

### Opening progress

The operator says <code>Open Progress</code> or invokes
<code>$studio-goal-progress</code>.

The skill:

1. Resolves the active KIT goal from the current runtime binding. When none or
   more than one goal matches, it lists bounded recent local sessions and
   requires an explicit operator selection instead of guessing.
2. Validates the goal root and last-good reduced state.
3. Starts or reuses a trusted loopback dashboard server.
4. Opens the compact view in a Codex panel when the app tool is available.
5. Returns the clean localhost URL and integration status without exposing a
   reusable session credential.

When the skill cannot open the browser or panel, it may return a short-lived,
single-use bootstrap URL after an explicit operator request. The bootstrap
token expires after first use or 60 seconds, establishes an HttpOnly,
SameSite=Strict session cookie, and redirects immediately to the clean URL. The
reusable session key never appears in agent output, browser URLs, reports, or
logs.

When panel opening is unavailable, the local dashboard remains usable and the
embedded panel is <code>BLOCKED</code>. When App Server is unavailable,
portable progress remains usable and Codex enrichment is
<code>BLOCKED</code>.

### Compact panel

The compact panel shows:

- Goal title and current state.
- Verified percentage.
- ETA range and confidence.
- Current work packet.
- Waiting input, blockers, and failures.
- Latest evidence summary.
- Next action.
- Last update and stale indicator.

### Full dashboard

The full local dashboard adds:

- Plan version and revision history.
- Packet order, weight, state, attempt, elapsed time, and evidence.
- Append-only event timeline.
- Sanitized command and artifact references.
- ETA basis and recalculation history.
- <code>brief</code>, <code>working</code>, and <code>resume</code> context
  projections.
- Runtime integration status.

The GUI is operationally read-only. Tabs, filters, and safe artifact links do
not count as Goal control.

## Runtime Artifact Layout

Runtime output belongs under ignored local evidence:

~~~text
evidence/local/goals/<goal-id>/
|-- goal.json
|-- progress.jsonl
|-- state.json
|-- integration-status.json
|-- context/
|   |-- brief.json
|   |-- brief.md
|   |-- working.json
|   |-- working.md
|   |-- resume.json
|   +-- resume.md
|-- logs/
|   +-- <packet-id>.log
|-- quarantine/
|   +-- invalid-events.jsonl
+-- runtime/
    +-- server-info.json
~~~

<code>goal.json</code> is the current materialized goal and packet manifest.
<code>progress.jsonl</code> is the sole canonical append-only replay stream.
The accepted <code>goal.started</code> record contains the complete initial
manifest, and every accepted <code>plan.revised</code> record contains the
complete replacement manifest plus the previous and new manifest hashes.
Every other file, including <code>goal.json</code>, is derived or runtime state
and can be rebuilt or replaced atomically.

The server key may exist only in ignored runtime state and process memory. It
must never enter committed evidence, reports, logs, or generated catalogs.

## Goal Manifest Contract

The goal manifest is a closed versioned schema containing:

- <code>schema_version</code>
- <code>goal_id</code>
- <code>title</code>
- <code>repository_root</code>
- <code>repository_snapshot</code>
- <code>created_at</code>
- <code>plan_version</code>
- <code>scope</code>
- <code>do_not_touch</code>
- <code>packets</code>
- <code>final_verification_required</code>
- Optional <code>runtime_bindings</code>
- Timing policy with initial
  <code>max_active_timed_packets: 1</code>

Each packet contains a stable ID, workflow ID, owner, objective, positive
integer weight, dependencies, completion criteria, required evidence, optional
estimate range, and owned/excluded paths when file ownership applies.

Weights are relative units and do not need to total 100. The reducer rejects
zero or negative weights, missing dependencies, duplicate IDs, and dependency
cycles.

## Normalized Event Contract

Each JSONL record is a closed schema containing:

- <code>schema_version</code>
- <code>event_id</code>
- <code>goal_id</code>
- <code>plan_version</code>
- Monotonic <code>sequence</code>
- UTC <code>emitted_at</code>
- Writer epoch and monotonic offset
- <code>source</code>
- <code>event_type</code>
- Optional <code>packet_id</code>
- Event-type-specific closed <code>payload</code>
- Authority binding for state-changing events
- Sanitized <code>summary</code>
- Evidence references
- Optional goal-local raw-log reference
- Record content hash

<code>goal.started</code> carries the complete initial goal manifest.
<code>plan.revised</code> carries the complete replacement manifest,
<code>previous_manifest_hash</code>, <code>new_manifest_hash</code>, revision
reason, and reviewer or approval reference when the revision changes approved
scope. Full manifest payloads are schema-bounded data, not optional metadata.
This makes packet weights, dependencies, revision history, and the current
manifest reconstructible from <code>progress.jsonl</code> alone.

Initial source kinds:

- <code>kit_workflow</code>
- <code>codex_app_server</code>
- <code>operator_note</code>

An operator note is informational and cannot directly change state.

Initial event families:

- <code>goal.started</code>
- <code>plan.revised</code>
- <code>packet.started</code>
- <code>packet.waiting_input</code>
- <code>packet.blocked</code>
- <code>packet.failed</code>
- <code>packet.retry_started</code>
- <code>packet.resumed</code>
- <code>evidence.observed</code>
- <code>packet.verified</code>
- <code>context.refreshed</code>
- <code>runtime.heartbeat</code>
- <code>goal.completed</code>
- <code>goal.cancelled</code>

Every state-changing event includes the expected prior state. The writer
rejects mismatched goal, plan, packet, state, or sequence data.

<code>packet.verified</code> requires an evidence reference whose workflow ID,
packet ID, evidence kind, command and exit code where applicable, artifact path
and digest where applicable, and evidence label satisfy the packet's declared
completion criteria. The active workflow remains responsible for the semantic
truth of that evidence; the progress writer validates the closed contract and
binding but does not infer success. <code>evidence.observed</code> alone never
increments progress.

## Writer Submission and Recovery Contract

The progress writer is a goal-local process with one random submission
capability and one writer epoch. Candidate submissions use a private loopback
endpoint or equivalent process-local channel that is not exposed to dashboard
JavaScript. The dashboard origin remains read-only. The submission capability
exists only in ignored runtime state and process memory.

The writer rejects concurrent stale sequences, mismatched authority bindings,
unknown fields, invalid transitions, reused conflicting event IDs, and records
whose content hash does not match their canonical serialization. Accepted
records are flushed before derived state is replaced atomically. A restarted
writer obtains the exclusive lock, replays the last-good stream, creates a new
writer epoch, and never attributes the restart gap to active work.

Only the writer may quarantine a rejected candidate. Quarantine records include
the rejection reason and sanitized candidate identity, but never reusable
credentials or unrestricted raw payloads.

## State Model

Packet states:

- <code>queued</code>
- <code>running</code>
- <code>waiting_input</code>
- <code>blocked</code>
- <code>failed</code>
- <code>verified</code>
- <code>skipped</code>

<code>waiting_input</code> represents a human choice or approval gate and must
not be reported as <code>BLOCKED</code>.

<code>failed</code> represents an observed failure. Retrying creates a new
attempt through <code>packet.retry_started</code>; failure history remains.

<code>skipped</code> requires a plan revision with an explicit scope reason. It
leaves the active denominator only in the new plan version.

Legal packet transitions are closed:

| Event | Expected prior state | Result |
|---|---|---|
| <code>packet.started</code> | <code>queued</code> | <code>running</code> |
| <code>packet.waiting_input</code> | <code>running</code> | <code>waiting_input</code> |
| <code>packet.resumed</code> | <code>waiting_input</code> | <code>running</code> |
| <code>packet.blocked</code> | <code>running</code> or <code>waiting_input</code> | <code>blocked</code> |
| <code>packet.failed</code> | <code>running</code> | <code>failed</code> |
| <code>packet.retry_started</code> | <code>blocked</code> or <code>failed</code> | <code>running</code> and increment attempt |
| <code>packet.verified</code> | <code>running</code> | <code>verified</code> |

Initial packets enter <code>queued</code> through <code>goal.started</code>.
Adding, removing, skipping, or reopening a packet is permitted only through a
new complete manifest in <code>plan.revised</code>. No other packet transition
is accepted.

Goal states:

- <code>planned</code>
- <code>running</code>
- <code>waiting_input</code>
- <code>blocked</code>
- <code>failed</code>
- <code>completed</code>
- <code>cancelled</code>

<code>stale</code> is a derived display condition. It appears when no valid
boundary event or runtime heartbeat arrives inside the configured freshness
window. For a packet with an estimate, the default window is the greater of 15
minutes or twice its high estimate. Without an estimate, the default is 30
minutes. A runtime that cannot emit heartbeat reports liveness as
<code>unknown</code> until that window expires; silence never proves failure or
completion.

A verified packet can reopen only through a new plan version. Old verification
remains in revision history.

## Progress Calculation

Progress is evidence-backed:

~~~text
verified_weight / active_planned_weight * 100
~~~

Rules:

- Only <code>verified</code> packets contribute completed weight.
- Running, waiting, blocked, and failed packets contribute zero.
- Revised-out packets leave the new denominator but remain in history.
- A plan revision may reduce progress. The GUI shows the new version and
  <code>Progress recalculated</code>; it never hides the decrease.
- Display is capped at 99 percent until required final verification passes and
  <code>goal.completed</code> is accepted.
- Percentage is derived state, never model- or operator-supplied.

## ETA Calculation

ETA is a forecast and remains separate from Verified evidence.

Each packet may declare a low/high estimate. Before observations exist, the
reducer sums remaining ranges and reports low confidence only while the plan
uses the initial serial timing policy. If more than one packet is actively
timed, the parallel-timing rule below takes precedence.

After verified packets exist:

1. The persistent writer measures active elapsed time with a monotonic clock
   inside its current writer epoch and stores the accepted duration delta and
   cumulative active duration at each state boundary.
2. Exclude <code>waiting_input</code>, <code>blocked</code>, and stale periods.
3. Calculate actual-to-estimated-midpoint ratios for completed packets.
4. Apply the median ratio as a bounded calibration factor to remaining ranges.
5. Recalculate after verification and plan revision.

On writer restart, previously recorded cumulative active duration remains
usable, but the gap between writer epochs is excluded and recorded as an ETA
basis warning. Confidence cannot increase from an interval that crosses writer
epochs. A runtime heartbeat proves only liveness; it never changes percentage
or counts as packet verification.

The initial ETA contract supports one actively timed packet at a time. Progress
percentage remains valid when independent packets run in parallel, but ETA is
<code>BLOCKED</code> with reason <code>unsupported_parallel_timing</code> unless
a future version defines and tests dependency- and lane-aware critical-path
forecasting. The writer never sums parallel packet estimates as though they
were serial work.

The calibration factor is clipped to <code>0.5-3.0</code>. Confidence is:

- <code>low</code> with zero or one calibrated packet.
- <code>medium</code> with two to four calibrated packets.
- <code>medium</code> with five or more packets when relative median absolute
  deviation exceeds <code>0.35</code>.
- <code>high</code> with five or more packets when relative median absolute
  deviation is at most <code>0.35</code>.

A plan revision recalculates ETA and cannot raise confidence until at least one
packet in the new plan version is verified.

The GUI displays ranges such as <code>18-28 min</code>, never a falsely precise
countdown. Insufficient data shows <code>Calculating...</code>. Waiting,
blocked, or stale state shows <code>ETA paused</code> with the reason. Plan
revision shows <code>ETA recalculated</code>.

## Codex App Server Adapter

The optional adapter consumes supported thread, turn, item, and tool lifecycle
notifications only when it owns an initialized App Server transport or the host
explicitly supplies an authorized notification stream.

It:

- Treats runtime payloads as untrusted input.
- Allowlists recognized methods and fields.
- Maps recognized notifications into informational normalized events.
- Never marks a packet verified from tool activity alone.
- Records runtime version and supported methods.
- Disables only enrichment on unknown required schema changes.

Private or undocumented Goal metadata is not required. If the adapter cannot
bind a runtime thread to a declared KIT goal, enrichment is
<code>BLOCKED</code>.

A thread ID alone does not authorize or create a passive subscription to an
already-running Codex Desktop task. The initial implementation verifies a
client-owned App Server connection and version-specific generated schema
fixtures. Live enrichment of an existing desktop task remains
<code>BLOCKED</code> unless the host exposes a documented transport to that
task. Portable KIT events remain the only required path.

Official reference: <https://learn.chatgpt.com/docs/app-server>.

## Dashboard Server

The initial server uses the Python standard library and bundled static assets.

Requirements:

- Bind <code>127.0.0.1</code> by default.
- Generate a cryptographically random session key.
- Authenticate HTTP and SSE with an HttpOnly, SameSite=Strict session cookie.
- Use only a short-lived, single-use bootstrap token to establish that cookie.
- Expose only read-only GET and SSE endpoints on the dashboard origin; writer
  submission uses a separate private capability and endpoint.
- Restrict artifact paths to the resolved active goal root.
- Refuse traversal, symlink, junction, mount-point, and Windows reparse-point
  escapes.
- Reuse only trusted matching PID, root, port, and session metadata.
- Select another loopback port when an unrelated listener owns the old port.
- Shut down after a configurable idle timeout.
- Never inject raw log content into HTML.
- Send <code>Cache-Control: no-store</code>,
  <code>Referrer-Policy: no-referrer</code>, a restrictive Content Security
  Policy, and <code>X-Content-Type-Options: nosniff</code>.
- Serve allowlisted text and JSON artifacts as escaped text. Force unknown,
  HTML, SVG, and other active content to download instead of executing under
  the authenticated dashboard origin.

SSE carries reduced-state changes and bounded sanitized summaries. After a
dropped connection, the dashboard fetches current state before resuming.

The Codex skill may call the app's panel-opening capability when available. The
server itself does not depend on that capability.

## Context Brief Contract

<code>studio-context-brief</code> is separate because active Goal context
reduction differs from durable handoff.

The skill reads structured trusted inputs:

- Goal manifest and last-good state.
- Evidence references.
- Scope and do-not-touch boundaries.
- Decisions, blockers, failures, changed files, and next action.

It does not summarize arbitrary raw transcripts by default. Missing facts stay
missing or receive <code>Unverified</code>/<code>BLOCKED</code>.

Preservation priority:

1. Safety, owned scope, do-not-touch paths, negations, and blockers.
2. Active packet and exact next action.
3. Paths, commands, decisive errors, artifacts, and evidence labels.
4. Decisions, dependencies, and deduplicated completed history.

Projections:

| Projection | Purpose | Target | Hard cap |
|---|---|---:|---:|
| <code>brief</code> | Compact GUI state | 150 tokens | 300 tokens |
| <code>working</code> | Active-agent context | 800 tokens | 1,200 tokens |
| <code>resume</code> | Cross-session projection | 1,600 tokens | 2,400 tokens |

Exact token counting is used when an available supported tokenizer matches the
target runtime. Without one, the fallback also requires UTF-8 byte length to be
at most the numeric hard cap, records an approximate count kind, and labels the
exact target-runtime token count <code>Unverified</code>. This conservative
fallback keeps the initial runtime useful without a tokenizer dependency while
never claiming an exact count it did not perform.

The reducer removes filler, repeated commentary, duplicate output, and
superseded history. It never shortens exact paths, commands, symbols, numbers,
units, negations, or decisive error strings. Projection text never exceeds its
hard cap. If required safety text or one indivisible exact literal cannot fit,
the projection is <code>BLOCKED</code> rather than truncated; the artifact
contains references to the complete required facts, and the GUI shows that the
projection must not be used as standalone context.

This design adapts general precision and compression patterns from
<code>JuliusBrussee/caveman</code> at upstream commit
<code>b4335705d436f5110386a1c39c6d8aed5002aeeb</code>, which matches the
installed <code>skills/caveman/SKILL.md</code> content after newline
normalization. The relevant skill area is covered by the repository's MIT
license; Engine-linked BSL modules are outside scope. No upstream text,
examples, modes, runtime modules, or code are copied.

## Studio Handoff Integration

<code>studio-handoff</code> remains authoritative.

It may consume the <code>resume</code> projection, but it must still refresh
Git state, record exact files and commands, separate evidence labels, preserve
normal prose, and add restore information plus a reactivation prompt.

A compact context artifact is not proof that a handoff is current.

## Error Handling and Recovery

Malformed, out-of-order, duplicate-conflicting, wrong-goal, wrong-plan, or
invalid-transition events are quarantined. Last-good state remains available.

Exact duplicate event IDs are ignored idempotently. Reusing an ID with
different content is corruption.

The append-only stream is authoritative. Derived files use atomic replacement
and rebuild after interruption. A truncated final line is quarantined without
discarding earlier valid events.

Unknown App Server schema, unsupported methods, or failed thread binding
disables enrichment and reports <code>BLOCKED</code>. Portable events continue.

Stale goals show last update, suppress active ETA, and never turn silence into
completion or failure.

Summaries are filtered before display. Suspicious content is redacted and
recorded as a filtering warning. Raw logs remain references. Artifact requests
outside the goal root are rejected.

## Distribution Design

### studio-goal-progress

- Type: <code>interactive</code>
- Risk: <code>low</code>
- Maturity: <code>experimental</code>
- Pack: <code>studio-core</code>
- Depends on: <code>using-game-studio-skills</code>
- Artifact: <code>progress.jsonl</code>

### studio-context-brief

- Type: <code>workflow</code>
- Risk: <code>low</code>
- Maturity: <code>experimental</code>
- Pack: <code>studio-core</code>
- Depends on: <code>studio-goal-progress</code>
- Artifact: <code>context/working.json</code>

No new agent role is required.

Root helpers remain canonical and are bundled through
<code>registry/skill-resources.yaml</code>. Hermes installation must receive
every needed helper and dashboard asset. Generated copies are never edited.

The plugin semantic version must increase because distributed payload changes.
The exact version is selected during implementation review. Local PASS does not
authorize push, publish, release, or release readiness.

## Proposed Canonical Write Scope

Expected new paths:

- <code>skills/studio-goal-progress/</code>
- <code>skills/studio-context-brief/</code>
- <code>scripts/goal_progress.py</code>
- <code>scripts/context_brief.py</code>
- Focused tests and routing, behavior, pressure, originality, and safety cases.

Expected modified paths:

- <code>registry/capabilities.yaml</code>
- <code>registry/packs.yaml</code>
- <code>registry/skill-resources.yaml</code>
- <code>skills/using-game-studio-skills/SKILL.md</code> for active Goal
  participation and meaningful-boundary emission.
- <code>skills/feature-to-work-packets/SKILL.md</code> for progress weight and
  optional estimate fields on progress-enabled plans.
- Maintained architecture and authoring documentation where required.
- <code>.codex-plugin/plugin.json</code> only for the approved version change.

Generated changes are determined by existing generators and inspected after
synchronization. Generated outputs are never patched manually.

No change to <code>studio-handoff</code> is required unless focused tests prove
an explicit optional-input sentence is needed. Update-first review runs before
that edit.

## Testing Strategy

### Schema and reducer

- Closed-schema acceptance and rejection.
- Full replay of initial and revised manifests from <code>progress.jsonl</code>
  with <code>goal.json</code> deleted.
- Manifest and record hash mismatch rejection.
- Monotonic sequence enforcement.
- Duplicate and conflicting IDs.
- Legal and illegal transitions.
- Authority-binding and evidence-contract rejection.
- Concurrent writer lock and stale-submission rejection.
- Plan revision and skipped history.
- Rebuild after interrupted derived writes.
- Truncated final line and quarantine behavior.

### Progress and ETA

- Arbitrary positive weights.
- Verified-only percentage.
- 99 percent cap before goal completion.
- Visible decrease after plan revision.
- Deterministic fake-clock duration fixtures.
- Waiting, blocked, and stale time exclusion.
- Writer restart, epoch-gap exclusion, and confidence non-increase.
- Heartbeat liveness without progress changes.
- Parallel timing returns <code>unsupported_parallel_timing</code> instead of a
  serial sum.
- Calibration, clipping, confidence, and recalculation.
- Insufficient-data output.

### Context

- Projection field priority and budget behavior.
- Exact preservation of paths, commands, symbols, numbers, units, errors,
  negations, and evidence labels.
- Deduplication and superseded history.
- Security-warning clarity override.
- Tokenizer and approximate-fallback labeling.
- Hard-cap enforcement and <code>BLOCKED</code> indivisible literal behavior.
- Missing evidence remains Unverified or BLOCKED.

### Server and GUI

- Loopback binding and random-key authentication.
- Unauthorized request rejection.
- Single-use bootstrap expiry, clean redirect, and reusable-key non-disclosure.
- GET/SSE-only dashboard surface and isolated writer submission surface.
- Path traversal, symlink, junction, mount-point, reparse-point, and invalid
  artifact requests.
- Trusted server reuse and unrelated port conflict.
- SSE reconnect and state recovery.
- Sanitized rendering.
- Security headers, inert artifact rendering, and active-content download.
- Responsive compact and full layouts.
- No mutation or approval controls.

### Runtime compatibility

- KIT-only portable stream.
- Supported Codex App Server fixture.
- Client-owned App Server transport handshake and version-specific schema.
- Missing or incompatible App Server.
- Failed thread-to-goal binding.
- Existing desktop thread ID without an exposed transport remains
  <code>BLOCKED</code>.
- Missing panel-opening capability.
- Hermes standalone installation with bundled resources.

### Repository gates

Run focused tests, then:

~~~text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
~~~

Run <code>scripts/check_originality.py</code> and
<code>scripts/catalog_audit.py</code> as lifecycle audits. Governed dogfood is
required for adoption evidence. Missing runtime, session, or live-project
evidence remains <code>BLOCKED</code>.

Browser interaction evidence is required before claiming GUI behavior
Verified. Structural HTML checks do not replace browser evidence.

## Maturity and Rollout

Both capabilities start <code>experimental</code>.

Delivery sequence:

1. Contracts, reducer, and deterministic context projections.
2. Read-only dashboard and SSE.
3. Manual <code>Open Progress</code>.
4. Optional Codex App Server enrichment.
5. Hermes standalone-resource verification.
6. Governed dogfood on one bounded KIT-managed Goal.
7. Maturity audit after real project evidence.

Beta requires real studio adoption evidence. Stable requires verified dogfood
plus Tier-B, behavior, and pressure evidence. Release additionally requires a
runtime matrix and sanitized session history.

## Acceptance Criteria

1. A KIT-managed Goal declares weighted packets and appends validated events.
2. Reduced state rebuilds from the event stream.
3. Percentage changes only from verified weight and approved revisions.
4. ETA is a range with basis and confidence, pauses for inactive time, and is
   never evidence.
5. <code>Open Progress</code> opens a panel when supported, never exposes a
   reusable session key, and provides a single-use bootstrap URL only when the
   operator explicitly needs manual opening.
6. The dashboard updates live and exposes no Goal mutation controls.
7. Missing App Server or panel support degrades honestly.
8. Context projections preserve required technical facts within declared
   budget behavior.
9. <code>studio-handoff</code> remains authoritative.
10. Security, routing, behavior, pressure, originality, focused tests, and all
    local gates pass with recorded exit codes.
11. Browser interaction verifies both GUI projections, or GUI verification
    remains <code>BLOCKED</code>.
12. Generated resources match canonical owners.
13. Deleting every derived file and replaying <code>progress.jsonl</code>
    reconstructs the current manifest, revision history, progress, and recorded
    ETA basis.

## Approved Decisions

- Hybrid artifact-first plus optional App Server adapter.
- Compact Codex panel and full local dashboard.
- Manual GUI opening only.
- Read-only GUI.
- Weighted verified progress.
- ETA range with confidence and recalibration.
- Sanitized summaries with raw-log references.
- Separate <code>studio-context-brief</code> capability.
- Three context projections.
- Initial experimental maturity.

Implementation may choose internal function names and file decomposition without
reopening design when these contracts and ownership boundaries remain intact.
