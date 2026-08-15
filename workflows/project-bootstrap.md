# Project bootstrap

1. Run `studio-project-intake` read-only against the target project.
2. Run `studio-project-scaffold` in report mode; review nested Git roots, detected subsystems, profile draft, exclusions, and proposed paths.
3. Apply the scaffold only after scope approval; preserve existing `.agents/` content.
4. Run the per-project adapter, which is report-only by default, and capture its JSON output. Review the report before apply, including proposed skills, packaged generic agent templates, the profile specialist overlay, preserved files, collisions, and `plan_digest`.
5. Apply only the reviewed plan by passing the approved plan digest with `--plan-digest $report.plan_digest`, a named reviewer, and a disjoint project-local backup root such as `.adapter-backup`. If the digest is stale, generate and review a new report. The generated `.codex/agents.generated.toml` file provides inert activation until manually reviewed and merged. The adapter leaves `.codex/config.toml` untouched and never overwrites `.codex/config.toml`.
6. Treat `.agents/registry.json` as per-file ownership metadata. Hash-safe uninstall removes only unchanged owned files, preserves unmanaged local agents and drifted content, and returns `PARTIAL` recovery with remaining owned paths when cleanup cannot complete safely.
7. Route through `studio-workspace-routing`, plan any sidecars with `studio-agent-orchestration`, then verify and hand off with `studio-handoff`.

Never bootstrap private studio projects or external repositories automatically during kit development.
