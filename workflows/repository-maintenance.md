# Repository maintenance

Use this workflow only inside the `GameStudio-CodexKIT` source repository. Invoke `codexkit-repository-maintenance` for the operating contract and select `codexkit-maintainer` when a bounded repository writer is needed.

## Intake

1. Verify repository identity and read `AGENTS.md`.
2. Record branch, working-tree state, requested outcome, owned write scope, and do-not-touch scope.
3. Preserve unrelated tracked and untracked work.
4. Classify the request before selecting tools or edits.

## Maintenance branches

| Request | Required route |
|---|---|
| GitHub Actions, test, build, or cross-platform failure | Reproduce from the exact command or authenticated log, then use evidence-first debugging. |
| Skill, agent, workflow, trigger, provenance, or maturity change | Run update-first authoring and audit with failing routing or behavior evidence before changing canonical content. |
| Registry, pack, persona, or catalog drift | Change the canonical entry and verify every dependent index or count. |
| Generator, adapter, or bundled resource change | Edit the root owner, regenerate only affected outputs, and inspect preservation behavior. |
| Plugin metadata, semantic version, or release readiness | Compare the distributed payload and run release preflight; internal-only changes do not bump the plugin version. |
| Documentation-only maintenance | Verify links, counts, commands, and source-of-truth alignment without broad formatting churn. |
| Architecture improvement or cleanup | Require evidence of the maintenance problem, exact scope, restore path, and regression coverage. |

## Root cause

1. Reproduce the failure or record concrete evidence for the improvement.
2. Separate canonical-source defects from generated drift, fixture defects, environmental failures, and CI-only behavior.
3. Select the smallest canonical owner that explains the evidence.
4. Record unavailable dependencies or runners as `BLOCKED` rather than weakening the gate.

## Canonical edit

1. Assign one writer per file, registry, generator, or output.
2. Add a failing test before changing executable behavior.
3. Edit canonical files only.
4. Regenerate affected resources through their root helper.
5. Review the diff for unrelated edits, generated-file hand patches, catalog leakage, and version impact.

## Local gates

Run focused checks first, followed by:

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

A PASS requires the command, exit code, and artifact path where applicable. Lifecycle audits and dogfood evidence may remain `BLOCKED` when their governed inputs are unavailable.

## Handoff

Record repository and branch, goal, owned scope, do-not-touch scope, files changed, commands and exit codes, artifacts, Verified results, Snapshot assumptions, Unverified hypotheses, BLOCKED items, failures, decisions, restore information, next actions, and a reactivation prompt. Treat commit, push, publish, deploy, and release as separately authorized actions.
