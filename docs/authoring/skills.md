# Skill Authoring

Use `skill-authoring-and-audit` in `author` mode before creating or changing a canonical skill. For user-facing routing and prompt examples, keep the [Vietnamese skill and agent guide](../huong-dan-su-dung-skill-agent.md) and the [Wiki-ready English guide](../wiki-skill-agent-user-guide.md) synchronized with the canonical catalog.

## Required sequence

1. Search capability, agent-role, pack, persona, and resource registries plus existing skills for overlap; prefer update-first.
2. Classify Adopt, Adapt, or Write-new and record provenance.
3. Add a failing routing, behavior, pressure, or deterministic regression case before editing behavior.
4. Update the smallest complete skill using the closed frontmatter schema enforced by `scripts/validate.py`.
5. Add `agents/openai.yaml` with `display_name: "MOStudio Kit: <skill heading>"`, a 25-64 character `short_description`, and a `default_prompt` that explicitly mentions `$<skill-id>`.
6. Include required body sections and a completion criterion for every workflow step.
7. Add at least 3 positive, 2 negative with owner, and 1 collision routing case; root skills are exempt and require `Negative scope`.
8. If the skill uses a deterministic helper, update the canonical root script and `registry/skill-resources.yaml`, then run `scripts/sync_skill_resources.py`; never patch `skills/*/scripts/` by hand.
9. For execution-heavy workflows, add a progressively loaded `references/commands.md` with platform-specific commands, evidence fields, and mutation boundaries.
10. Validate repository-root discovery for Codex, per-skill copying for Hermes Agent, and project-local role materialization from `registry/agent-roles.yaml`, then regenerate only the packs or adapter exports being distributed.
11. Run structural validation, routing, external-catalog collision, secret, policy, cross-agent packaging, and full unittest discovery.

## Project adapter contract

Keep project adapter documentation and tests aligned with its safety boundary: report-only by default; apply requires a named reviewer, disjoint backup root, and approved plan digest. The overlay combines packaged generic agent templates with the profile specialist overlay, emits inert activation for manual review, and leaves `.codex/config.toml` untouched. Record per-file ownership so unmanaged local agents survive regeneration and hash-safe uninstall can return `PARTIAL` recovery with remaining owned paths instead of deleting drifted content.

## Trigger quality

Descriptions start with `Use when` and describe triggering conditions rather than summarizing the workflow. Keep triggers concrete, searchable, and distinct from neighboring skills. Put detailed procedures in the body and large reference material in progressively loaded files.

## Body depth: procedure versus knowledge

A skill body carries two different things, and both are required.

**Procedure** is the order of operations, the completion criterion, the evidence contract, and the risk gate. The shared section skeleton covers this, and it is what stops an agent from claiming success it did not earn.

**Knowledge** is what the agent cannot derive: the exact command, the field that actually decides the behavior, the value that signals a fault, and the misdiagnosis that looks correct. Without it the agent improvises exactly where improvisation is most expensive.

A body step written only as procedure fails this test:

```text
Inspect canvas/camera/layer/sorting or NGUI panel and widget depth.
Completion criterion: render-order conflicts are supported by values.
```

The step is correct and unactionable. It does not say which field wins, how to read it without an editor, or which check must come first to avoid a false root cause. Add the knowledge to a progressively loaded reference and link it from `## References and scripts`.

When authoring or reviewing a skill, require at least one of these to be concrete:

- a named command, API, config key, serialized field, or log signal;
- a decision table or precedence order that resolves a real ambiguity;
- a diagnostic ordering that prevents a specific known misdiagnosis;
- a threshold, unit, or value range that distinguishes healthy from faulty.

If none apply, the skill is a checklist. That is acceptable for pure governance and planning skills; it is not acceptable for diagnostic, gate, or execution workflows.

## Writing `references/commands.md`

Any `diagnostic`, `gate`, or execution workflow whose hard part is "which command do I run" needs one. Keep `SKILL.md` at contract level and put the operational depth here so it loads only when needed.

Structure that has worked in this repository:

1. **A boundary sentence first.** State what the commands do and do not authorize. A reference for a read-only skill must say that it does not authorize service control, saving assets, or database writes.
2. **Detection before action.** When a skill spans variants (uGUI vs NGUI vs UI Toolkit, Windows vs Linux, MySQL vs SQLite), open with the commands that identify which variant is present, plus a table mapping each marker to the fields that matter. Guessing the variant is the most common failure.
3. **Fenced, runnable blocks with the right shell tag.** Use ` ```bash `, ` ```powershell `, ` ```sql `, ` ```csharp `. Placeholders must be obviously placeholders (`<pod>`, `D:\Projects\MyGame`), never plausible-looking fabrications.
4. **Explain what the output means.** A command without an interpretation rule just relocates the guesswork. State which value proves what, and which value looks conclusive but is not.
5. **A diagnostic order section.** List the checks in the order that avoids false root causes, and name the misdiagnosis being avoided.
6. **A blocked-actions table for risky domains.** For `medium` and `high` risk skills, enumerate the actions that stay `BLOCKED` and what approval each needs.
7. **An `## Evidence` section last.** List the exact fields to record and restate the `BLOCKED`-never-`PASS` rule for this domain.

Constraints enforced by the gates:

- `scripts/validate.py` reports `skill.link.missing` for a reference that is not linked from its `SKILL.md`. Always add the link in `## References and scripts` in the same change.
- `scripts/secret_scan.py` fails on credential-shaped literals. Pass credentials through defaults files or environment variables in examples, never inline.
- `scripts/check_originality.py` flags high overlap without declared provenance. Write reference content from primary sources or first-hand project experience.
- Reference files are progressively loaded, so length is cheap; `SKILL.md` bloat is not. Prefer moving depth into `references/` over growing the body.

## Provenance

A copied or adapted permissive source needs repo, path, commit, license, and copied-text scope. CC BY-NC-SA sources are pattern-only and must be independently written. High overlap without declared provenance fails the originality gate.

Historical roadmap influence may be named as an archived origin, but active workflow steps must depend only on maintained contracts, registries, and documentation.

## Maturity

New or changed skills stay `draft` or `experimental` until the maintainer confirms
real studio adoption or a governed dogfood result demonstrates use. `beta` marks a
workflow that has been applied in a real studio project; it does not claim that every
skill has an individual verified dogfood case.

`stable` requires a matching record in `registry/promotion-evidence.yaml` with fresh
verified dogfood plus Tier-B, behavior, and pressure evidence. `release` additionally
requires a runtime matrix and session history. Missing runners, live builds, Unity MCP,
or operational KPIs remain `BLOCKED`; targets are never treated as observed metrics.

The current catalog is `beta` based on maintainer-confirmed application in FPC
(`Snapshot`). `localization-authority-audit` additionally has verified static FPC
dogfood artifacts. This catalog-wide beta status does not promote missing runtime or
model evidence to `Verified` and does not satisfy the `stable` gate.

Current observed adoption evidence, with labels, is tracked in [`docs/adoption.md`](../adoption.md).

## Deployment checklist

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/external_collision_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" .
python -B scripts/generate_adapters.py . --target hermes --output adapters/hermes
python -B scripts/generate_adapters.py . --target codex --output adapters/codex
```

The Codex plugin manifest exposes canonical `skills/` directly. Hermes Agent copies each canonical skill directory, including its generated helper resources. The adapter commands are optional export maintenance, not primary installation steps. Keep local evaluation output in ignored `evidence/local/`. Optional completed planning history may stay in ignored local `.archive/`; promote durable decisions into maintained docs and never make active skills depend on archived files.
