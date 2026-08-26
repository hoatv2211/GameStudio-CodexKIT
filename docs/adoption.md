# Adoption Evidence

This page applies the kit's own evidence rules to the kit itself. Every claim below is labeled `Verified`, `Snapshot`, `Unverified`, or `BLOCKED`. Nothing here is upgraded to `PASS` because it would be convenient.

Local deterministic-gate observations were refreshed against the current pre-release working tree on 2026-08-22. The latest commit-bound remote CI evidence recorded here remains commit `1ea9903`.

## Summary

| Question | Answer | Label |
|---|---|---|
| Do the deterministic gates pass locally? | Yes, all eight in the current Windows checkout | `Verified` |
| Is the commit-bound CI matrix green? | No — the run for `1ea9903` failed on `windows-latest`; the matrix remains configured for Ubuntu and Windows | `Verified` |
| Has the catalog been used on a real game project? | Yes, one — a live Unity 6 WebGL MMORPG client | `Snapshot` |
| Is there a skill with verified per-skill dogfood artifacts? | Yes, one — `localization-authority-audit` | `Verified` |
| Have model-driven evals been run? | Yes, on one runner only | `Verified` for that runner, `BLOCKED` as a matrix |
| Is there a runtime matrix across Codex and Hermes? | No | `BLOCKED` |
| Are operational KPIs from real sessions observed? | No sanitized session history supplied | `BLOCKED` |
| Are there external adopters outside the maintaining studio? | No | `Unverified` |

## Deterministic gates

`Verified`. Reproduce with:

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

The observations below are local Windows results from the refreshed checkout. CI configuration is not treated as a passing run; the commit-bound result is recorded separately in the summary above.

| Gate | Observation |
|---|---|
| Structural and provenance validation | 0 errors, 0 warnings |
| Tier-A routing | 316/316 cases, rank-1 accuracy 1.0 across 49 routed skills |
| External-catalog collision | 10/10 — studio routes beat six generic neighboring skills |
| Secret scan | 0 findings |
| Network and package policy | PASS |
| Originality and provenance overlap | PASS, 1199 upstream sources scanned, 0 undeclared overlaps |
| Unit tests | 659 tests, 6 skipped, 0 failures |
| Repository doctor | PASS, managed pre-commit hook installed |

These prove **catalog separation and structural integrity**. They do not prove that a model behaves correctly when handed a skill. Keyword routing is not model behavior.

## Model-driven evaluation

`Verified` for a single runner. `BLOCKED` as a runtime matrix.

| Suite | Cases | Passed | Runner | Observed |
|---|---|---|---|---|
| Tier-B | 204 | 204 | Codex CLI `cx/gpt-5.6-sol` (xhigh) | 2026-08-18 |
| Behavior | 18 | 18 | Codex CLI `cx/gpt-5.6-sol` (xhigh) | 2026-08-18 |
| Pressure | 12 | 12 | Codex CLI `cx/gpt-5.6-sol` (xhigh) | 2026-08-18 |

Limitations, stated plainly:

- One runner, one model, one reasoning effort. A second runner may disagree, and until one is executed the generalization is `Unverified`.
- The snapshot predates the two `experimental` skills added on 2026-08-21, so `unity-ui-art-and-motion-production` and `game-screenshot-showcase-and-store-packaging` are **not** covered by it.
- Pressure cases prove the agent refused to skip gates in twelve scripted scenarios, not that no bypass exists.

## Real-project dogfood

`Snapshot` at catalog level, `Verified` for one skill.

The catalog is marked `beta` on the basis of maintainer-confirmed application in one commercial-style Unity 6 (6000.3.10f1) WebGL MMORPG client with a Lua gameplay layer and multiple concurrent agent sessions sharing one worktree. Per `AGENTS.md`, `beta` records adoption; it does not assert individual verified dogfood evidence for each of the 50 skills.

One skill exceeds that bar. `localization-authority-audit` has a promotion record in `registry/promotion-evidence.yaml` with hash-bound artifacts under `registry/promotion-artifacts/localization-authority-audit-fpc/`, covering two cases with real command logs, exit codes, and a project snapshot. Validation reports it as `verified: 1, stale: 0, invalid: 0`. The record expires 2027-02-17 and is bound to a static profile.

The full narrative, including the honest `BLOCKED` verdicts inside that run, is in [the case study](case-studies/unity-mmorpg-global-localization.md).

## What remains BLOCKED

`scripts/catalog_audit.py` currently returns `BLOCKED` — not `FAIL`, since no deterministic gate is failing — for these reasons:

1. **Session history is BLOCKED.** No sanitized real-session transcripts have been supplied, so the operational KPIs `pass_with_evidence`, `unauthorized_writes`, and `retry_over_three_without_escalation` are all `null`. Targets exist (1.0, 0, 0) but a target is not an observation.
2. **Hermes dogfood is BLOCKED.** `scripts/dogfood_eval.py --status` reports `verdict: BLOCKED, observed_cases: 0` because no governed Hermes runner plus real game-project snapshot has been supplied. Fifteen dogfood scenarios are exported and waiting.
3. **No runtime matrix.** `release` maturity requires evidence across runtimes; only Codex CLI has been exercised.

These are honest gaps, not defects. Per `AGENTS.md`, a lifecycle audit may remain `BLOCKED` for missing runner, history, or KPI evidence while catalog `beta` maturity stays valid.

## What would move the needle

Ordered by evidentiary value:

1. Run the fifteen exported dogfood scenarios against a governed Hermes runner on a real project. Removes gap 2, adds a second runtime.
2. Supply sanitized session history so the three operational KPIs become observed rather than `null`. Removes gap 1.
3. Re-run Tier-B, behavior, and pressure so the two `experimental` skills are covered, then consider promoting them.
4. Add promotion records with hash-bound artifacts for the most-used skills, the way `localization-authority-audit` already has.
5. External adoption outside the maintaining studio. Currently `Unverified`, and no amount of internal work changes that label.

## How to read maturity here

| Level | Meaning in this repository |
|---|---|
| `experimental` | New or changed; no confirmed studio adoption yet. Two skills. |
| `beta` | Catalog applied in a real studio project (`Snapshot`). Forty-seven skills. |
| `stable` | Requires a promotion record with fresh verified dogfood plus Tier-B, behavior, and pressure evidence. **No skill currently qualifies.** |
| `release` | Additionally requires a runtime matrix and sanitized session history. **`BLOCKED`.** |

Maturity is separate from task evidence. A `beta` skill must still report each individual claim as `Verified`, `Snapshot`, `Unverified`, or `BLOCKED` according to what was actually observed in that task.
