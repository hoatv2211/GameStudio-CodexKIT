# Skill Authoring

Use `skill-authoring-and-audit` in `author` mode before creating or changing a canonical skill.

## Required sequence

1. Search registries and existing skills for overlap; prefer update-first.
2. Classify Adopt, Adapt, or Write-new and record provenance.
3. Add a failing routing, behavior, pressure, or deterministic regression case before editing behavior.
4. Update the smallest complete skill using the closed frontmatter schema enforced by `scripts/validate.py`.
5. Include required body sections and a completion criterion for every workflow step.
6. Add at least 3 positive, 2 negative with owner, and 1 collision routing case; root skills are exempt and require `Negative scope`.
7. If the skill uses a deterministic helper, update the canonical root script and `registry/skill-resources.yaml`, then run `scripts/sync_skill_resources.py`; never patch `skills/*/scripts/` by hand.
8. Validate repository-root discovery for Codex and per-skill copying for Hermes Agent, then regenerate only the packs or adapter exports being distributed.
9. Run structural validation, routing, secret, policy, cross-agent packaging, and full unittest discovery.

## Trigger quality

Descriptions start with `Use when` and describe triggering conditions rather than summarizing the workflow. Keep triggers concrete, searchable, and distinct from neighboring skills. Put detailed procedures in the body and large reference material in progressively loaded files.

## Provenance

A copied or adapted permissive source needs repo, path, commit, license, and copied-text scope. CC BY-NC-SA sources are pattern-only and must be independently written. High overlap without declared provenance fails the originality gate.

Historical roadmap influence may be named as an archived origin, but active workflow steps must depend only on maintained contracts, registries, and documentation.

## Maturity

New or changed skills stay `draft` or `experimental`. Promotion requires deterministic gates, governed behavior/pressure/Tier-B PASS, complete workflow coverage, and verified dogfood evidence. Missing runners, live builds, or operational KPIs remain `BLOCKED`; targets are not observed metrics.

## Deployment checklist

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" .
python -B scripts/generate_adapters.py . --target hermes --output adapters/hermes
python -B scripts/generate_adapters.py . --target codex --output adapters/codex
```

The Codex plugin manifest exposes canonical `skills/` directly. Hermes Agent copies each canonical skill directory, including its generated helper resources. The adapter commands are optional export maintenance, not primary installation steps. Keep local evaluation output in ignored `evidence/local/`. Optional completed planning history may stay in ignored local `.archive/`; promote durable decisions into maintained docs and never make active skills depend on archived files.
