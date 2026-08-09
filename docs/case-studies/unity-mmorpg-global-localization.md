# Case Study: Skill-Routed Global English Localization Of A Live Unity MMORPG Client

Date: 2026-08-09. Status: dogfood evidence, two runs (initial + approved continuation). Runner: Codex CLI non-interactive (`codex exec`), skill-routed. Project: a commercial-style Unity 6 (6000.3.10f1) WebGL MMORPG client with a Lua gameplay layer, a localization workbench pipeline, and multiple parallel agent sessions sharing one worktree.

Names below are lightly sanitized; every number, command shape, exit code, and verdict is taken from the real run artifacts.

## Why this case matters

This is the exact scenario GameStudio-CodexKIT is built for: an agent asked to "review and fix all mixed-Chinese text and UI to English" on a **live game project** where the naive approach — grep for Han characters and bulk-replace — would corrupt generated files, break placeholder contracts, fight other agent sessions for file ownership, and produce a confident "done!" with no proof.

Instead, the task was forced through skill routing, evidence labels, risk gates, and lock ownership. The result: real fixes with verifiable artifacts, honest `BLOCKED` verdicts where verification was impossible, and zero collateral damage across ~10 concurrent session lock namespaces.

## Operating rules applied

- Skill routing was mandatory and announced per step (localization workflow skill, prefab-residue skill, config-gap skill, client/runtime skill).
- Every material claim carried an evidence label: `Verified` (command + exit code + artifact), `Snapshot`, `Unverified`, or `BLOCKED`.
- `BLOCKED` was never converted into PASS. Lock reclaim required explicit human approval with per-PID proof of death, re-verified immediately before reclaim.
- Generated outputs (runtime Lua bundles, quarantine overlays) were only regenerated through their owning generator, never hand-edited.
- No commit, no push, no service control, no bulk prefab edits. All session locks released at exit; one live lock (PID alive) was never touched.

## Run 1 — audit and first remediation

Baseline gates: localization doctor (strict) exit `0`; missing-translation inventory `243` missing / `243` quarantined / `0` anomalies; raw prefab audit `1,067` unclassified Han findings.

What was fixed with evidence:

- A Unity `LocalizationText` component raced localization readiness and flashed raw keys; it now defers lookup until the catalog is ready. `Verified` by focused tests.
- Preload/error labels were rewritten to compact game-native English while preserving the exact placeholder, newline, and rich-text signatures the catalog contract requires. `Verified`.
- The generated Lua byte mirror was stale; regenerated through the owner menu (`Build Bundle`), never hand-edited. `Verified` — the stale mirror was the root cause of "old text still showing".
- Focused localization suites: `205` passed, `2` skipped, exit `0`. `git diff --check` exit `0`.
- Play-mode proof via Unity MCP (read-only): preload and login scenes audited live — `Han=0`, `placeholder=0`, `overflow=0` across the active `UnityEngine.UI.Text` set; `0` exceptions, `0` localization lookup errors in the captured console.

What was honestly refused:

- `BLOCKED`: a staged 32-row config-gap batch could not be applied because the generator outputs were locked by another (dead) agent session. The dry-run passed; apply was not faked.
- `BLOCKED`: one Lua sanitizer fix was locked by a second dead session; its RED test was written and left failing on purpose.
- `BLOCKED`: a compact progress string still overflowed a `160 px` widget for representative values; flagged for a human decision instead of silently editing prefab layout.
- Intentional-keep: Chinese artwork assets listed in the image-localization manifest were preserved, not "fixed".

## Human decision gate

The user reviewed the three blockers and issued two decisions: (1) approve reclaiming exactly the two proven-dead sessions' locks — nothing else; (2) choose Option A for the overflow string: shorten the English, do not touch prefab layout.

## Run 2 — approved continuation

- Config-gap batch: apply/export/generate/package pipeline exit `0`; verify artifact reports `PASS`, `32/32` IDs, `31` distinct English values, `0` warnings, `0` Han, matching packaged/generated hashes. Catalog grew `25,609 → 25,641`; bridge stable at `1,969`; pipeline test groups `58/58` and `42/42`.
- Sanitizer fix: the RED test went GREEN (`10/10` focused, `34/34` combined). Guild-name display paths now route through a validator that rejects malformed UTF-8, C0/C1 controls, and Han through `U+323AF` — Global builds only; CN behavior unchanged.
- Overflow string: solved with a signature-preserving format trick — `"%d%% %s/%s%.0s"` keeps the 4-argument contract (`d,s,s,s`) while `%.0s` consumes and hides the speed argument, so no Lua caller changed. Representative render: `100% 1.0/2.0MB`. Edit-mode audit: `preferred_width=150` inside `rect_width=160`, `overflow=false`, exit `0`.
- Still honestly blocked at the end: play-mode re-audit (the editor instance dropped off MCP mid-run and was deliberately not force-restarted) and strict doctor (`stale_authoritative_artifact` on a report owned by a session outside the approved reclaim scope). Non-strict doctor exit `0`.
- Exit hygiene: `git diff --check` exit `0`, all continuation locks released, the one live lock untouched, no commit or push.

## Runner failures worth recording

Real dogfood includes tool failures, and this run had three:

1. The Codex CLI had been upgraded (0.125 → 0.147) and dropped the old `--full-auto` flag; the first launch died at argument parsing. Fix: `codex exec -s workspace-write` with the prompt on stdin.
2. `--approve-for-me` on 0.147 routes risk approvals through the OpenAI Responses API; behind an OpenAI-compatible proxy without `/v1/responses`, every high-risk action was auto-declined with a 404 — the agent correctly stopped instead of working around its own safety reviewer. Fix: drop the flag and split the risky step behind an explicit human approval.
3. Long PowerShell one-liners hit quoting/parser failures and script-execution policy; the agent fell back to smaller commands rather than disabling the policy.

## Outcome

| Gate | Result |
|---|---|
| Config-gap batch (32 IDs) | PASS with hash-verified artifacts |
| Sanitizer RED test | GREEN (10/10, 34/34) |
| Overflow string | Fixed, edit-mode verified, signature preserved |
| Strict doctor | BLOCKED (stale artifact outside approved scope) — not faked |
| Play-mode re-audit | BLOCKED (editor instance lost) — not faked |
| Collateral damage | None: 0 foreign locks touched, 0 commits, unrelated work preserved |

Two runs, three real fixes shipped through owning pipelines, two blockers left standing because the evidence to close them did not exist. That is the intended behavior of this kit: **the agent's report is trustworthy precisely because it is allowed to say BLOCKED.**
