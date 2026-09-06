# GameStudio-CodexKIT Operating Contract

## Active Sources Of Truth

Use this precedence order:

1. `AGENTS.md` for operating, evidence, mutation, ownership, archive, and handoff rules.
2. `.agents/skills/*/SKILL.md` and `.codex/agents/*.toml` for repository-local maintenance behavior while working in this repository.
3. `registry/*.yaml` for distributed capabilities, agent roles, packs, personas, skill resources, and upstream snapshot provenance.
4. `skills/*/SKILL.md` for canonical distributed workflows.
5. `docs/architecture/overview.md` and `docs/authoring/skills.md` for maintained design guidance.
6. Generated adapters as read-only optional export artifacts.

Files under the ignored local `.archive/` are optional historical context only and never active policy or distributable template content.

## Primary Distribution

- Codex App/CLI and Hermes Agent are the only primary runtime targets. Treat every other export as optional maintenance output.
- The repository root is the installable plugin; `skills/` remains the only canonical distributed workflow source.
- `.codex-plugin/plugin.json` defines the plugin identity and exposes `./skills/` directly.
- `.claude-plugin/marketplace.json` is the Codex-supported repository marketplace compatibility path used by the GitHub install flow.
- Hermes Agent installs the same canonical catalog through `npx skills add <repo> -a hermes-agent`; the CLI copies individual skill directories, so runtime helpers must be bundled inside each skill.
- Generated Hermes, Codex, pack, and per-project outputs are optional export artifacts. Canonical agent-role templates live in `agents/` and are materialized project-locally; never create a second hand-maintained plugin skill tree.
- Keep Codex plugin metadata, the Hermes Agent-discoverable root catalog, repository URL, and registry synchronized through `scripts/validate.py` and packaging tests.
- Increment the plugin semantic version when a distributed plugin change must invalidate an installed cache.

## Repository-Local Maintenance

- `.agents/skills/` is the only allowed repository-local maintenance skill tree. It is tracked for maintainers, excluded from plugin skill exports, and never added to capability or pack registries.
- `.codex/agents/` and `.codex/config.toml` may activate repository-local maintenance roles. These roles are never added to `registry/agent-roles.yaml` or project scaffold templates.
- `workflows/repository-maintenance.md` is the maintained human-readable workflow for improving this kit.
- Repository-local maintenance skills may route to distributed skills but must not duplicate their specialist procedures.
- Keep internal IDs out of generated adapters, packs, project overlays, and installed game projects. Validate this boundary through `scripts/validate.py` and governance tests.

## Evidence

- Use `Verified` only for commands, tests, builds, primary-source inspection, or artifacts that were actually observed.
- Use `Snapshot` for commit-, configuration-, environment-, or version-specific facts.
- Use `Unverified` for hypotheses and forecasts.
- Use `BLOCKED` when a tool, dependency, permission, live project, or model runner is unavailable. Never convert `BLOCKED` into `PASS`.
- A PASS claim requires a command, exit code, and artifact path where applicable.
- Compile success is not regression proof; performance claims require a baseline, scenario, hardware, sample count, and measured delta.
## Maturity

- Use `draft` or `experimental` before real studio adoption is confirmed.
- Use `beta` for a catalog or workflow adopted in a real studio project. Maintainer confirmation may be recorded as `Snapshot`; beta does not claim that every skill has individual verified dogfood evidence.
- `beta` does not require a per-skill promotion record. `stable` requires verified dogfood plus Tier-B, behavior, and pressure evidence; `release` additionally requires a runtime matrix and sanitized session history.
- Keep maturity separate from task evidence: a beta skill must still report individual claims as `Verified`, `Snapshot`, `Unverified`, or `BLOCKED` according to what was observed.
- A lifecycle audit may honestly remain `BLOCKED` for missing model, runtime, history, upstream, or KPI evidence while catalog beta maturity remains valid. Never treat that absence as `premature_maturity`; that gate applies to `stable` and `release`.

## Mutation

- Read-only inspection is the default.
- Low-risk reversible changes require a visible diff and verification command.
- Medium-risk changes require exact scope, backup or manifest, restore information, and a named reviewer.
- High-risk, destructive, database, service-control, credential, or publish actions require explicit human approval and a dry run.
- Never mutate `.research/` repositories, private studio projects, or external repositories during kit development.
- Never patch generated adapters or packs by hand.

## Repeated Work And Tooling

- Before repeating the same action across records, files, or assets, assess an existing tool, workflow, or batch pipeline before manual processing.
- Three or more similar targets, or any high-volume set, requires an explicit choice among manual, reuse, extend, or create-tool. The threshold requires assessment, not automatic tool creation.
- Reuse or extend an existing tool before creating a new one. Do not over-engineer a small one-off task when direct handling is clearer and lower risk.
- A mutating tool requires report-only or dry-run mode, bounded scope and output, a manifest or structured log, validation, and a safe rerun contract. Long-running pipelines must be resumable; repeated operations must be idempotent or detect completed state.
- Quarantine recoverable per-item failures when the remaining set can continue safely; fail fast when a failure invalidates shared integrity.
- Group failures by cause and repair the owning rule, converter, or pipeline before rerunning the affected cluster. Do not default to one-off edits for every failed item.
- Automation does not expand authority. Commit, service control, database actions, Unity mutation, publishing, credentials, and destructive actions retain their existing approval gates.

## Ownership

- One writer owns a file, scene, prefab, generated output, or shared registry at a time.
- Review and investigation lanes are read-only. The integrator owns registry resolution and the final verdict.
- Preserve unrelated tracked and untracked work. Do not reset, checkout, clean, branch, commit, or push unless explicitly requested.
- Default `commit_policy` is `ask`.

## Generated Files

- Generated files start with `# Generated by scripts/<tool>. Do not edit manually.` or the format-appropriate equivalent.
- Root `scripts/` files are the canonical helper sources. `registry/skill-resources.yaml` maps them into self-contained skill directories through `scripts/sync_skill_resources.py`.
- Change the canonical skill, root helper, or registry, then regenerate. Never patch `skills/*/scripts/` by hand.
- Generators must preserve unmanaged project-local files and refuse unsafe replacement.

## Archive

- `.archive/` is ignored local-only storage; never require or package it.
- Archive only completed plans or cleanup notes that remain useful to the local maintainer.
- Active workflows must not require archived files.
- Reproducible runner output belongs under ignored `evidence/local/` or CI artifacts.
- Promote durable decisions into maintained docs before relying on them across clones.

## Handoff

A durable handoff records repository/path, branch, goal, owned scope, do-not-touch scope, files changed, commands and exit codes, Verified results, Snapshot assumptions, Unverified hypotheses, BLOCKED items, failures, decisions, restore information, next actions, and a reactivation prompt.

Do not use a handoff as a substitute for verification that is locally available.

## Local Gates

Run before handoff:

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

Run `scripts/check_originality.py` and `scripts/catalog_audit.py` as lifecycle audits. Run `scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl` and `scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json` when preparing a governed dogfood session. Their honest result may be `BLOCKED` when upstream content, governed runners, session history, live projects, or verified dogfood evidence is unavailable.
