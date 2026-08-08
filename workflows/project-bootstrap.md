# Project bootstrap

1. Run `studio-project-intake` read-only against the target project.
2. Run `studio-project-scaffold` in report mode; review detected subsystems and proposed paths.
3. Apply only after scope approval; preserve existing `.agents/` content.
4. Generate per-project adapter using `scripts/generate_adapters.py`.
5. Verify and hand off with `studio-handoff`.

Never bootstrap private studio projects or external repositories automatically during kit development.
