from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from scripts.adapter_sources import MARKER, _generated_resource
    from scripts.project_adapters import (
        apply_project_adapter,
        report_project_adapter,
        report_uninstall_project_adapter,
        uninstall_project_adapter,
        _uninstall_plan_digest,
        _validate_uninstall_backup_root,
    )
    from scripts.standard_adapters import (
        _is_standard_generated_artifact,
        generate_adapter as _generate_standard_adapter,
    )
except ModuleNotFoundError:
    from adapter_sources import MARKER, _generated_resource
    from project_adapters import (
        apply_project_adapter,
        report_project_adapter,
        report_uninstall_project_adapter,
        uninstall_project_adapter,
        _uninstall_plan_digest,
        _validate_uninstall_backup_root,
    )
    from standard_adapters import (
        _is_standard_generated_artifact,
        generate_adapter as _generate_standard_adapter,
    )


def generate_adapter(
    root: Path | str,
    target: str,
    output: Path | str,
) -> dict[str, object]:
    root_path = Path(root).resolve()
    output_path = Path(os.path.abspath(str(output)))
    if target in {"hermes", "codex"}:
        return _generate_standard_adapter(root_path, target, output_path)
    if target == "per-project":
        return report_project_adapter(root_path, output_path)
    raise ValueError(f"unsupported adapter target: {target}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Hermes, Codex, or project-local adapters."
    )
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument(
        "--target", required=True, choices=["hermes", "codex", "per-project"]
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--backup-root")
    parser.add_argument("--plan-digest")
    args = parser.parse_args(argv)
    if args.uninstall:
        if args.target != "per-project":
            parser.error("--uninstall is only supported for per-project adapters")
        if not args.apply:
            if args.reviewer or args.backup_root or args.plan_digest:
                parser.error("--reviewer, --backup-root, and --plan-digest require --apply")
            print(json.dumps(report_uninstall_project_adapter(Path(args.output)), indent=2))
            return 0
        if not args.reviewer or not args.reviewer.strip():
            parser.error("--reviewer is required with --uninstall --apply")
        if not args.backup_root:
            parser.error("--backup-root is required with --uninstall --apply")
        if not args.plan_digest or not args.plan_digest.strip():
            parser.error("--plan-digest is required with --uninstall --apply")
        _validate_uninstall_backup_root(Path(args.output), Path(args.backup_root))
        current_digest = _uninstall_plan_digest(Path(args.output))
        if args.plan_digest.strip() != current_digest:
            parser.error("adapter uninstall plan changed since report")
        print(json.dumps(uninstall_project_adapter(Path(args.output)), indent=2))
        return 0
    if args.apply:
        if args.target != "per-project":
            parser.error("--apply is only supported for per-project adapters")
        if not args.reviewer or not args.reviewer.strip():
            parser.error("--reviewer is required with --apply")
        if not args.backup_root:
            parser.error("--backup-root is required with --apply")
        if not args.plan_digest or not args.plan_digest.strip():
            parser.error("--plan-digest is required with --apply")
        result = apply_project_adapter(
            Path(args.root),
            Path(args.output),
            reviewer=args.reviewer,
            backup_root=Path(args.backup_root),
            approved_plan_digest=args.plan_digest,
        )
    else:
        if args.reviewer or args.backup_root or args.plan_digest:
            parser.error("--reviewer, --backup-root, and --plan-digest require --apply")
        result = generate_adapter(Path(args.root), args.target, Path(args.output))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
