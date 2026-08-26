<p align="center">
  <img src="docs/assets/banner.svg" alt="MOStudio Kit — AI agent skills for Unity and MMORPG live game operations" width="100%">
</p>

# MOStudio Kit — AI Agent Skills for Unity and MMORPG Operations

**Evidence-first workflows for operating live games with Codex and Hermes Agent.**

MOStudio Kit is a catalog of AI agent skills for Unity clients, C++ and Lua
MMORPG servers, game databases, content pipelines, releases, and live
operations. It helps an agent diagnose failures, plan bounded changes, protect
player data, and prove what was actually verified. It is built for maintaining
shipped games—not generating a new game from scratch.

MOStudio Kit is distributed from the `GameStudio-CodexKIT` repository. The
public product name is MOStudio Kit; repository URLs and the stable plugin ID
`game-studio-codex-kit` keep the technical project name.

[![Skills](<https://img.shields.io/badge/skills-50%20canonical-brightgreen>)](skills/) [![Routing](<https://img.shields.io/badge/routing%20eval-316%2F316-blue>)](evals/routing/) [![Tests](<https://img.shields.io/badge/unittest-test%20suite-informational>)](tests/) [![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

## Why MOStudio Kit

- **Built for live game operations.** Workflows cover fragile clients,
  authoritative servers, generated assets, player data, builds, incidents, and
  releases.
- **Evidence instead of confidence.** Results distinguish `Verified`,
  `Snapshot`, `Unverified`, and `BLOCKED`. An unavailable runner never becomes
  a fake PASS.
- **Safe changes by default.** Read-only diagnosis comes first. Higher-risk
  work requires visible scope, review, backup or restore evidence, and human
  approval where appropriate.
- **One canonical catalog.** Codex and Hermes Agent use the same workflows,
  evidence contracts, and risk boundaries.

## Visual overview

These seven panels summarize the product before the detailed guides: what the
kit operates, how requests are routed, and why evidence and mutation gates
matter in a live game project.

<p align="center">
  <img src="docs/assets/showcase-handcrafted/slide-01.webp" alt="MOStudio Kit operates live games with evidence instead of faking success" width="100%">
</p>

<table>
  <tr>
    <td width="50%"><img src="docs/assets/showcase-handcrafted/slide-02.webp" alt="MOStudio Kit contrasts greenfield game development with maintaining a shipped live game" width="100%"></td>
    <td width="50%"><img src="docs/assets/showcase-handcrafted/slide-03.webp" alt="MOStudio Kit routes a natural-language game problem to a specialist evidence-backed workflow" width="100%"></td>
  </tr>
  <tr>
    <td align="center"><strong>Built for shipped games</strong><br><sub>Clients, servers, assets, and player data remain inside the risk model.</sub></td>
    <td align="center"><strong>Ask for the outcome</strong><br><sub>The router selects the smallest matching canonical workflow.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/showcase-handcrafted/slide-04.webp" alt="MOStudio Kit organizes canonical game studio skills packs personas and agent roles" width="100%"></td>
    <td width="50%"><img src="docs/assets/showcase-handcrafted/slide-05.webp" alt="MOStudio Kit separates Verified Snapshot Unverified and BLOCKED evidence states" width="100%"></td>
  </tr>
  <tr>
    <td align="center"><strong>One studio catalog</strong><br><sub>Skills, packs, and agent roles share one source of truth.</sub></td>
    <td align="center"><strong>Trust is explicit state</strong><br><sub>An unavailable runner remains <code>BLOCKED</code>, never PASS.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/showcase-handcrafted/slide-06.webp" alt="MOStudio Kit applies escalating safety gates to game project mutations" width="100%"></td>
    <td width="50%"><img src="docs/assets/showcase-handcrafted/slide-07.webp" alt="MOStudio Kit records evidence from a real Unity WebGL MMORPG dogfood run" width="100%"></td>
  </tr>
  <tr>
    <td align="center"><strong>Risk controls scale up</strong><br><sub>Diffs, restore paths, reviewers, and approvals stay visible.</sub></td>
    <td align="center"><strong>Observed on a real project</strong><br><sub>Verified results and honest blockers are reported separately.</sub></td>
  </tr>
</table>

## What you can do

Describe the outcome in normal language. The router selects the smallest
matching workflow; you do not need to memorize skill names.

| Request                                                              | Typical workflow                     |
| -------------------------------------------------------------------- | ------------------------------------ |
| “Audit this Unity/MMORPG project and identify the right workflow.” | Project intake and workspace routing |
| “The Unity client cannot enter offline mode.”                      | Offline bootstrap debugging          |
| “The C++ game server crashed; here is the stack trace.”            | Build-bound crash triage             |
| “Check whether this Lua client action is validated server-side.”   | Protocol and server-authority review |
| “Plan this MySQL schema change without risking player data.”       | Dry-run migration safety             |
| “Prepare a release go/no-go decision with rollback evidence.”      | Release candidate preflight          |

The catalog also covers Unity UI and asset integrity, localization authority,
performance budgets, telemetry contracts, game economy review, playtests,
LiveOps incidents, store submission, production planning, and governed
multi-agent work.

## Install

Choose one primary runtime. A repository clone is not required for normal use.

### Codex App and CLI

```bash
codex plugin marketplace add hoatv2211/GameStudio-CodexKIT
codex
```

Open `/plugins`, select the **MOStudio Kit** marketplace, install the plugin,
and start a new task or CLI session.

### Hermes Agent

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -g -y
```

Start a new Hermes Agent session after installation. See the
[English installation and project activation guide](docs/wiki-skill-agent-user-guide.md#installation-and-project-activation)
for upgrades, removal, project-local installation, and governed scaffolding.

## Quick start

Give the agent a goal, readable and writable scope, protected paths, and the
evidence you expect:

```text
Repository: D:/Games/MyMMO
Goal: determine why the Unity client cannot enter offline gameplay.
Readable scope: Assets/, ProjectSettings/, Logs/.
Writable scope: none until the root cause is verified.
Do not touch: .env, databases, generated localization, production services.
Return: selected workflow, ranked evidence, commands, exit codes, artifacts,
limitations, and explicit Verified/Snapshot/Unverified/BLOCKED results.
```

For more examples, use the
[Vietnamese skill and agent guide](docs/huong-dan-su-dung-skill-agent.md) or the
[complete English skill and agent guide](docs/wiki-skill-agent-user-guide.md).

## Evidence, not confidence

The current catalog contains **50 canonical skills**, **24 canonical agent roles**,
seven installable packs, and **316 deterministic eval cases** for Tier-A routing.
Local deterministic tests, model-runner evidence, real-project dogfood, and
lifecycle maturity are deliberately reported as separate things.

Some workflows remain `experimental`, and missing runtime, project, approval,
or session-history evidence remains `BLOCKED`. Read the
[current adoption evidence](docs/adoption.md) for observed results and known
limitations; do not infer release readiness from badges alone.

## Documentation

| Guide                                                                                   | Purpose                                                                                     |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [Hướng dẫn Skill và Agent bằng tiếng Việt](docs/huong-dan-su-dung-skill-agent.md) | Cách chọn và sử dụng toàn bộ skill/agent với ví dụ thực tế                      |
| [English Skill and Agent User Guide](docs/wiki-skill-agent-user-guide.md)                | Wiki-ready user guide, Golden Paths, prompts, agents, installation, and end-to-end examples |
| [Skill Catalog](docs/CATALOG.md)                                                         | All skills, routing triggers, risk levels, and output artifacts                             |
| [Architecture](docs/architecture/overview.md)                                            | Source authority, routing, distribution, evidence, and safety model                         |
| [Project Adoption Workflow](docs/architecture/project-init-and-studio-expansion.md)      | Report-only intake, role-first routing, and governed project scaffolding                    |
| [Adoption Evidence](docs/adoption.md)                                                    | Verified results, snapshots, limitations, and lifecycle blockers                            |
| [Skill Authoring Guide](docs/authoring/skills.md)                                        | Rules for contributors changing canonical workflows                                         |

The [GitHub Pages landing page](https://hoatv2211.github.io/GameStudio-CodexKIT/)
provides the visual overview. Detailed adapter, evaluation, mutation, archive,
and maintenance procedures live in the linked documentation rather than this
README.

## Project status

The catalog is beta based on maintainer-confirmed studio adoption. Individual
skills may be beta or experimental, and each task must still earn its own
evidence. Codex App/CLI and Hermes Agent are the primary distribution targets.

Repository maintenance uses Python 3.11 and the deterministic gates documented
in [Adoption Evidence](docs/adoption.md). Issues and proposals can be opened in
[GitHub Issues](https://github.com/hoatv2211/GameStudio-CodexKIT/issues).

## License

[MIT](LICENSE) © MAD Studio. Contributions to skills, agents, documentation,
or evaluation fixtures should follow the
[Skill Authoring Guide](docs/authoring/skills.md) and repository
[Operating Contract](AGENTS.md).
