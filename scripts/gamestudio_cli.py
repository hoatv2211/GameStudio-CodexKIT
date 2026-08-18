from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from scripts.codegraph_adapter import apply_install_plan, create_install_plan
    from scripts.project_scaffold import (
        apply_scaffold,
        scaffold_project,
        scaffold_status,
        uninit_scaffold,
    )
except ModuleNotFoundError:
    from codegraph_adapter import apply_install_plan, create_install_plan
    from project_scaffold import apply_scaffold, scaffold_project, scaffold_status, uninit_scaffold


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
    if args.command == "status":
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
