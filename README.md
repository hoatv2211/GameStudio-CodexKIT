# GameStudio-CodexKIT

Native Codex plugin and Hermes Agent skill kit for game studios working across Unity, C++, Lua, MMORPG services, databases, production, release, and live operations.

The kit is workflow-first, evidence-first, and safety-first. Canonical skills contain executable procedures; personas provide thin review lenses; registries drive routing, packs, and generated adapters.

## Quick install

Choose one primary runtime. A repository clone is not required for normal use.

| Runtime | Install |
|---|---|
| Codex App/CLI | `codex plugin marketplace add hoatv2211/GameStudio-CodexKIT`, then install **GameStudio Codex Kit** from `/plugins` or the App Plugins UI |
| Hermes Agent | `npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -g -y` |

Start a new Codex or Hermes session after installation, then ask for the outcome directly. The root router selects the smallest matching studio workflow.

## Install in Codex

Add the GitHub marketplace from a terminal:

```bash
codex plugin marketplace add hoatv2211/GameStudio-CodexKIT
codex
```

In the Codex CLI session, enter `/plugins`, select the **GameStudio Codex Kit** marketplace, open **GameStudio Codex Kit**, and install it. Start a new CLI session before using the bundled skills.

In the ChatGPT desktop app, open **Plugins** from Codex, select the **GameStudio Codex Kit** marketplace, install the plugin, and start a new task. Ask for the outcome directly or invoke the plugin with `@game-studio-codex-kit` when you want an explicit route.

Example first request:

```text
Audit this game project and route the work to the right studio skills.
```

Update the marketplace snapshot, then review the plugin in `/plugins` and start a new session:

```bash
codex plugin marketplace upgrade gamestudio-codex-kit
```

To remove it, uninstall the plugin from `/plugins` first, then remove the marketplace:

```bash
codex plugin marketplace remove gamestudio-codex-kit
```

The repository root is the plugin package. `.codex-plugin/plugin.json` exposes the canonical `skills/` directory, while `.claude-plugin/marketplace.json` is the Codex-supported compatibility marketplace discovered from the GitHub repository. Each domain skill carries its own generated helper scripts, so the installed plugin does not depend on the user's current working directory.

## Install in Hermes Agent

Install all 33 skills globally with the Agent Skills CLI:

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -g -y
```

Start a new Hermes Agent session after installation. The installer discovers the repository-root `skills/` catalog and copies each skill directory into the Hermes global skills directory. Bundled helpers therefore live inside the skill that uses them. Omit `-g` when you intentionally want a project-local `.hermes/skills/` installation.

To inspect the catalog before installing:

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -l
```

Repository governance tools such as the catalog validator, originality audit, and adapter generators are intentionally not copied by Hermes. Clone the repository only when maintaining the kit itself.

## Current state

- 33 canonical skills, including one root entry router and 32 routed domain skills.
- 192/192 deterministic Tier-A routing cases.
- 10 external-catalog collision cases against six generic neighboring skills.
- 10 governed real-project dogfood scenarios with strict PASS/BLOCKED evidence validation.
- Four installable packs and six thin personas.
- Two primary distributions: native Codex plugin installation and Agent Skills CLI installation for Hermes Agent.
- Seventeen standalone domain skills with 19 generated helper copies and explicit full-clone boundaries for repository-only governance tools.
- Optional generated exports for manual Hermes, Codex, pack, and project-local `.agents/` workflows.
- Structural, provenance, secret, network/package, safety, external-catalog collision, behavior, pressure, and lifecycle gates.
- All skills remain `experimental` until governed model evaluation and verified studio dogfood evidence exist.

The template does not claim that a Unity build, C++ server, database migration, store submission, or liveops action has run unless a real project artifact proves it.

## Catalog

| Pack | Focus |
|---|---|
| `studio-core` | Intake, design, planning, debugging, evidence, safe mutation, review, handoff, and skill governance |
| `unity` | Offline client debugging, UI rendering, localization, GUID/meta integrity, and batch builds |
| `cpp-lua-mmorpg` | Local services, MySQL safety, Lua contracts, C++ crashes, packet protocols, authority, and save migration |
| `production-design-liveops` | Playtests, performance, economy, balance, release, stores, incidents, and telemetry |

The authoritative capability list is `registry/capabilities.yaml`. Pack composition and persona routes live in `registry/packs.yaml` and `registry/personas.yaml`.

## Contributor requirements

- Python 3.11+
- PyYAML
- Git

Codex users need a supported Codex surface with plugin marketplace support and Git. Hermes Agent users need Node.js/npm for the `npx skills` installer. Bundled deterministic helpers use Python 3.11+ standard library only. A full clone additionally needs PyYAML for repository validation, routing, policy, and generation tools. The project uses standard-library `unittest`; pytest is not required.

## Verify the kit

Run the deterministic local gates before distributing or handing off changes:

```bash
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
```

To compare against an installed Codex/Hermes catalog as well as the checked-in generic snapshot, repeat `--external-root` for each catalog root:

```bash
python -B scripts/external_collision_eval.py . --external-root /path/to/installed/skills
```

Install the managed pre-commit hook:

```bash
python -B scripts/doctor.py --install-hook --root .
```

The hook runs structural validation, Tier-A routing, and secret scanning. It never commits or pushes.
On Linux and macOS, hook installation also marks `.git/hooks/pre-commit` executable; Windows does not expose POSIX execute bits.

## Use in a game project

The commands in this section are maintainer workflows and require a full repository clone. Normal Codex and Hermes installations are prompt-driven and use their installed skill catalogs directly.

Inspect a new project without writing files:

```bash
python -B scripts/project_scaffold.py D:/path/to/game-project
```

Applying the scaffold is a medium-risk mutation and requires a reviewer plus backup root:

```bash
python -B scripts/project_scaffold.py D:/path/to/game-project --apply --reviewer "QA Lead" --backup-root D:/path/to/game-project/.scaffold-backup
```

Install the canonical skills into an existing project while preserving unmanaged local skills:

```bash
python -B scripts/generate_adapters.py . --target per-project --output D:/path/to/game-project
```

The per-project adapter writes kit-owned skills under `.agents/skills/`, records hashes in `.agents/registry.json`, and does not overwrite local skills without the generated ownership marker.

## Advanced maintenance: packs and adapters

Build all packs:

```bash
python -B scripts/build_packs.py . --output dist/packs
```

Generate standard adapter exports locally from canonical skills when maintaining a manual distribution:

```bash
python -B scripts/generate_adapters.py . --target hermes --output adapters/hermes
python -B scripts/generate_adapters.py . --target codex --output adapters/codex
```

Native Codex and Hermes Agent installation both consume canonical `skills/` and do not require adapter trees. `adapters/` is ignored generated output; its files and generated packs carry a `Do not edit manually` marker. Change `skills/` or `registry/`, then regenerate any export artifacts you intentionally distribute outside this repository.

Bundled skill helpers are also generated. Change the canonical source under root `scripts/`, update `registry/skill-resources.yaml`, and run:

```bash
python -B scripts/sync_skill_resources.py .
```

## Governed evaluation

Tier-A routing is deterministic. Behavior, pressure, and Tier-B routing require result artifacts from a governed runner; skill wording alone is never evidence of correct model behavior.

Export cases and local `BLOCKED` status into the ignored `evidence/local/` workspace:

```bash
python -B scripts/behavior_eval.py . --export evidence/local/behavior-cases.jsonl
python -B scripts/behavior_eval.py . --status evidence/local/behavior-status.json
python -B scripts/pressure_eval.py . --export evidence/local/pressure-cases.jsonl
python -B scripts/pressure_eval.py . --status evidence/local/pressure-status.json
python -B scripts/tier_b_eval.py . --export evidence/local/tier-b-cases.jsonl
python -B scripts/tier_b_eval.py . --status evidence/local/tier-b-status.json
python -B scripts/dogfood_eval.py . --export evidence/local/dogfood-cases.jsonl
python -B scripts/dogfood_eval.py . --status evidence/local/dogfood-status.json
```

The dogfood pack contains ten real-project scenarios covering Unity offline/bootstrap and NGUI rendering, batchmode builds, MySQL safety, local service ports, C++ crashes, Lua contracts, liveops incidents, release preflight, and project intake. Supply governed results with `--results`; missing Hermes/live-project execution remains `BLOCKED`.

After a governed runner produces the complete result array, validate it and generate promotion-eligible summaries:

```bash
python -B scripts/dogfood_eval.py . --results evidence/local/dogfood-results.json --summary-dir evidence/local/dogfood
```

The evaluator rejects bare PASS labels, missing artifact paths, non-zero exits, missing reviewers or project snapshots, unauthorized writes, and incomplete case coverage. See `docs/authoring/dogfood.md` for the runner contract.

When a runner, live project, engine, service, or permission is unavailable, the correct verdict is `BLOCKED`, never a fabricated PASS.

`scripts/check_originality.py` is also `BLOCKED` until the upstream snapshots in `registry/upstream-sources.yaml` are restored or supplied explicitly.

## Evidence labels

- `Verified`: observed command, test, build, primary source, or artifact.
- `Snapshot`: true for a named commit, version, configuration, or environment.
- `Unverified`: hypothesis or forecast without sufficient evidence.
- `BLOCKED`: required runner, project, dependency, permission, or tool is unavailable.

A PASS claim includes the command, exit code, and artifact path when applicable.

## Repository layout

```text
 .codex-plugin/ native Codex plugin manifest
 .claude-plugin/ GitHub marketplace metadata read by Codex
skills/       canonical workflows plus generated self-contained helper copies
registry/     capability, pack, persona, skill-resource, and upstream indexes
personas/     thin role lenses and routes
workflows/    human-facing entry workflows
scripts/      deterministic helpers, generators, and gates
tests/        unittest regression and governance coverage
evals/        routing, external-catalog, dogfood, behavior, pressure, and schema fixtures
adapters/     ignored local Hermes and Codex export output
evidence/     reusable example; local runner output is ignored
.archive/     ignored local planning history, never distributed or active policy
```

Architecture details live in `docs/architecture/overview.md`; skill authoring rules live in `docs/authoring/skills.md`; operating rules live in `AGENTS.md`.

## Local archive boundary

`.archive/` is ignored local history for completed plans or cleanup notes that an individual maintainer wants to retain. It is not part of the public template, plugin, adapters, or packs, and agents must never treat it as current instructions. Durable project decisions belong in maintained docs; reproducible runtime evidence belongs in `evidence/local/` or CI artifacts.

## Contributing skills

Use update-first authoring:

1. Search the registry for overlap.
2. Add a failing routing, behavior, pressure, or deterministic regression case.
3. Update the smallest canonical skill and provenance record.
4. Update `registry/skill-resources.yaml` and regenerate bundled helpers when a skill uses a root helper.
5. Run all local gates.
6. Validate the native plugin and regenerate any packs or adapters being distributed.
7. Keep maturity `draft` or `experimental` until governed evidence supports promotion.

## License

MIT. Third-party influence is recorded through per-skill provenance. CC BY-NC-SA sources are pattern-only and must not be copied into the kit.
