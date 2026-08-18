# Skill Authoring

Use `skill-authoring-and-audit` in `author` mode before creating or changing a canonical skill.

## Required sequence

1. Search capability, agent-role, pack, persona, and resource registries plus existing skills for overlap; prefer update-first.
2. Classify Adopt, Adapt, or Write-new and record provenance.
3. Add a failing routing, behavior, pressure, or deterministic regression case before editing behavior.
4. Update the smallest complete skill using the closed frontmatter schema enforced by `scripts/validate.py`.
5. Include required body sections and a completion criterion for every workflow step.
6. Add at least 3 positive, 2 negative with owner, and 1 collision routing case; root skills are exempt and require `Negative scope`.
7. If the skill uses a deterministic helper, update the canonical root script and `registry/skill-resources.yaml`, then run `scripts/sync_skill_resources.py`; never patch `skills/*/scripts/` by hand.
8. For execution-heavy workflows, add a progressively loaded `references/commands.md` with platform-specific commands, evidence fields, and mutation boundaries.
9. Validate repository-root discovery for Codex, per-skill copying for Hermes Agent, and project-local role materialization from `registry/agent-roles.yaml`, then regenerate only the packs or adapter exports being distributed.
10. Run structural validation, routing, external-catalog collision, secret, policy, cross-agent packaging, and full unittest discovery.

## Project adapter contract

Keep project adapter documentation and tests aligned with its safety boundary: report-only by default; apply requires a named reviewer, disjoint backup root, and approved plan digest. The overlay combines packaged generic agent templates with the profile specialist overlay, emits inert activation for manual review, and leaves `.codex/config.toml` untouched. Record per-file ownership so unmanaged local agents survive regeneration and hash-safe uninstall can return `PARTIAL` recovery with remaining owned paths instead of deleting drifted content.

## Trigger quality

Descriptions start with `Use when` and describe triggering conditions rather than summarizing the workflow. Keep triggers concrete, searchable, and distinct from neighboring skills. Put detailed procedures in the body and large reference material in progressively loaded files.

## Provenance

A copied or adapted permissive source needs repo, path, commit, license, and copied-text scope. CC BY-NC-SA sources are pattern-only and must be independently written. High overlap without declared provenance fails the originality gate.

Historical roadmap influence may be named as an archived origin, but active workflow steps must depend only on maintained contracts, registries, and documentation.

## Maturity

New or changed skills stay `draft` or `experimental` until a matching record in
`registry/promotion-evidence.yaml` binds the adjacent transition to a named dogfood
profile, exact cases, owner/reviewer, restore text, expiry, and SHA-256 artifacts.
`beta` may use fresh verified static dogfood; `stable` additionally requires Tier-B,
behavior, and pressure evidence; `release` additionally requires a runtime matrix
and session history. Missing runners, live builds, Unity MCP, or operational KPIs
remain `BLOCKED`; targets are never treated as observed metrics.

The current FPC rollout promotes only `localization-authority-audit` to `beta` from
the read-only static profile. Runtime/editor verification remains explicitly
`BLOCKED`, so no stable or release promotion is recorded.

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
