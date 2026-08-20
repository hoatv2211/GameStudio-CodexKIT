from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

try:
    from scripts.codegraph_adapter import apply_install_plan, create_install_plan
    from scripts.project_profile import load_project_profile
    from scripts.project_scaffold import (
        apply_scaffold,
        draft_project_profile,
        scaffold_project,
        scaffold_status,
        uninit_scaffold,
    )
    from scripts.studio_experience import (
        INTENT_IDS,
        MODE_IDS,
        ROLE_IDS,
        plan_experience,
    )
except ModuleNotFoundError:
    from codegraph_adapter import apply_install_plan, create_install_plan
    from project_profile import load_project_profile
    from project_scaffold import (
        apply_scaffold,
        draft_project_profile,
        scaffold_project,
        scaffold_status,
        uninit_scaffold,
    )
    from studio_experience import INTENT_IDS, MODE_IDS, ROLE_IDS, plan_experience


def _discover_available_skills(
    *, module_path: Path | str | None = None
) -> tuple[str, ...]:
    source_path = (
        Path(module_path) if module_path is not None else Path(__file__)
    ).absolute()

    def unredirected(path: Path) -> Path | None:
        absolute_path = path.absolute()
        try:
            resolved_path = path.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        return resolved_path if resolved_path == absolute_path else None

    resolved_source = unredirected(source_path)
    if resolved_source is None or not resolved_source.is_file():
        return ()
    scripts_root = source_path.parent
    repository_root = scripts_root.parent
    plugin_manifest = repository_root / ".codex-plugin" / "plugin.json"
    resolved_manifest = unredirected(plugin_manifest)
    if resolved_manifest is not None and resolved_manifest.is_file():
        catalog_root = repository_root / "skills"
    else:
        installed_skill_root = repository_root
        installed_skill_file = installed_skill_root / "SKILL.md"
        resolved_installed_skill = unredirected(installed_skill_file)
        if (
            resolved_installed_skill is None
            or not resolved_installed_skill.is_file()
        ):
            return ()
        catalog_root = installed_skill_root.parent

    resolved_catalog = unredirected(catalog_root)
    if resolved_catalog is None or not resolved_catalog.is_dir():
        return ()
    try:
        candidates = tuple(catalog_root.iterdir())
    except OSError:
        return ()

    available: list[str] = []
    for candidate in candidates:
        resolved_candidate = unredirected(candidate)
        if (
            resolved_candidate is None
            or not resolved_candidate.is_dir()
            or resolved_candidate.parent != resolved_catalog
        ):
            continue
        skill_file = candidate / "SKILL.md"
        resolved_skill_file = unredirected(skill_file)
        if (
            resolved_skill_file is None
            or not resolved_skill_file.is_file()
            or resolved_skill_file.parent != resolved_candidate
        ):
            continue
        available.append(candidate.name)
    return tuple(sorted(available))


def _codegraph_preference(mode: str) -> str | None:
    return "never_suggest" if mode in {"disabled", "plan-install"} else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gamestudio")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("root", nargs="?", default=".")
    init.add_argument("--apply", action="store_true")
    init.add_argument("--reviewer")
    init.add_argument("--backup-root")
    init.add_argument("--plan-digest")
    init.add_argument(
        "--codegraph",
        choices=("auto", "disabled", "plan-install"),
        default="auto",
    )

    guide = commands.add_parser("guide")
    guide.add_argument("root", nargs="?", default=".")
    guide.add_argument("--role", choices=sorted(ROLE_IDS))
    guide.add_argument("--intent", choices=sorted(INTENT_IDS), required=True)
    guide.add_argument("--mode", choices=sorted(MODE_IDS))
    guide.add_argument("--golden-path")
    guide.add_argument(
        "--workflow",
        help="Select a canonical workflow (requires explicit --mode advanced).",
    )

    status = commands.add_parser("status")
    status.add_argument("root", nargs="?", default=".")

    codegraph = commands.add_parser("codegraph")
    codegraph.add_argument("plan")
    codegraph.add_argument("--apply", action="store_true")
    codegraph.add_argument("--reviewer")
    codegraph.add_argument("--plan-digest")

    uninit = commands.add_parser("uninit")
    uninit.add_argument("root", nargs="?", default=".")
    uninit.add_argument("--apply", action="store_true")
    uninit.add_argument("--reviewer")
    uninit.add_argument("--backup-root")

    args = parser.parse_args(argv)
    if (
        args.command == "guide"
        and args.workflow is not None
        and args.mode != "advanced"
    ):
        parser.error("--workflow requires --mode advanced")
    if args.command == "codegraph":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        if args.apply:
            if not args.reviewer or not args.plan_digest:
                parser.error("codegraph --apply requires --reviewer and --plan-digest")
            report = apply_install_plan(
                plan,
                reviewer=args.reviewer,
                digest=args.plan_digest,
            )
        else:
            report = {"status": "REPORT_ONLY", "codegraph_install_plan": plan}
        print(json.dumps(report, indent=2))
        return 0
    root = Path(args.root)
    if args.command == "guide":
        try:
            profile_path = root / ".agents" / "project-profile.yaml"
            profile = (
                load_project_profile(profile_path)
                if profile_path.is_file()
                else draft_project_profile(root)
            )
            report = plan_experience(
                profile,
                role=args.role,
                intent=args.intent,
                mode=args.mode,
                requested_golden_path=args.golden_path,
                requested_workflow=args.workflow,
                available_skills=_discover_available_skills(),
            )
        except (OSError, ValueError, yaml.YAMLError) as error:
            parser.error(f"guide failed: {error}")
    elif args.command == "status":
        report = scaffold_status(root)
    elif args.command == "uninit":
        if args.apply and (not args.reviewer or not args.backup_root):
            parser.error("uninit --apply requires --reviewer and --backup-root")
        report = uninit_scaffold(
            root,
            apply=args.apply,
            reviewer=args.reviewer,
            backup_root=Path(args.backup_root) if args.backup_root else None,
        )
    else:
        preference = _codegraph_preference(args.codegraph)
        if args.apply:
            if not args.reviewer or not args.backup_root or not args.plan_digest:
                parser.error("init --apply requires --reviewer, --backup-root, and --plan-digest")
            report = apply_scaffold(
                root,
                reviewer=args.reviewer,
                backup_root=Path(args.backup_root),
                approved_plan_digest=args.plan_digest,
                codegraph_preference=preference,
            )
        else:
            report = scaffold_project(root, codegraph_preference=preference)
            if args.codegraph == "plan-install":
                if not args.reviewer:
                    parser.error("--codegraph plan-install requires --reviewer")
                report["codegraph_install_plan"] = create_install_plan(
                    root,
                    reviewer=args.reviewer,
                )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
