from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.common import load_yaml
except ModuleNotFoundError:
    from common import load_yaml


NETWORK_MODULES = {"requests", "socket"}
NETWORK_IMPORT_PREFIXES = ("urllib.request", "http.client", "http.server")
URL_PATTERN = re.compile(r"https?://[^'\"\s)]+")
DYNAMIC_NETWORK_DECLARATION = "dynamic://declared-at-runtime"


def _is_network_import(name: str) -> bool:
    return name.split(".", 1)[0] in NETWORK_MODULES or name.startswith(
        NETWORK_IMPORT_PREFIXES
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports


def _uses_network(path: Path) -> bool:
    """Detect executable network imports without matching comments or string literals."""
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_network_import(alias.name) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _is_network_import(node.module) or (
                node.module in {"urllib", "http"}
                and any(
                    alias.name == "*"
                    or _is_network_import(f"{node.module}.{alias.name}")
                    for alias in node.names
                )
            ):
                return True
    return False


def check_policy(root: Path | str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    policy_path = root_path / "policy" / "network-package-policy.yaml"
    if not policy_path.exists():
        return {
            "status": "BLOCKED",
            "reason": "missing policy/network-package-policy.yaml",
            "dependency_violations": [],
            "network_violations": [],
        }
    policy = load_yaml(policy_path)
    allowed_third_party = set(policy.get("allowed_third_party_modules", []))
    network_access = policy.get("network_access", {}) or {}
    scripts_dir = root_path / "scripts"
    local_modules = {path.stem for path in scripts_dir.glob("*.py")}
    dependency_violations: list[dict[str, str]] = []
    network_violations: list[dict[str, object]] = []
    for path in sorted((root_path / "scripts").glob("*.py")):
        relative = path.relative_to(root_path).as_posix()
        tree = _tree(path)
        for module in sorted(_imports(tree)):
            if (
                module in sys.stdlib_module_names
                or module == "scripts"
                or module in local_modules
                or module in allowed_third_party
            ):
                continue
            dependency_violations.append({"path": relative, "module": module})
        text = path.read_text(encoding="utf-8")
        if not _uses_network(path):
            continue
        declared_urls = set(network_access.get(relative, []))
        observed_urls = set(URL_PATTERN.findall(text))
        dynamic_network = not observed_urls
        if (
            relative not in network_access
            or (observed_urls and observed_urls != declared_urls)
            or (dynamic_network and DYNAMIC_NETWORK_DECLARATION not in declared_urls)
        ):
            network_violations.append(
                {"path": relative, "observed_urls": sorted(observed_urls), "declared_urls": sorted(declared_urls)}
            )
    return {
        "status": "FAIL" if dependency_violations or network_violations else "PASS",
        "dependency_violations": dependency_violations,
        "network_violations": network_violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check declared Python dependencies and network access.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    report = check_policy(Path(args.root))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
