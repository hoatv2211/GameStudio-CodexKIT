from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.common import normalized_tokens, parse_frontmatter
except ModuleNotFoundError:
    from common import normalized_tokens, parse_frontmatter


def _token_set(path: Path) -> set[str]:
    try:
        _, body = parse_frontmatter(path)
    except ValueError:
        body = path.read_text(encoding="utf-8", errors="replace")
    return {token for token in normalized_tokens(body) if len(token) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _source_skills(source_roots: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    for root in source_roots:
        if root.is_file() and root.name == "SKILL.md":
            paths.append(root)
        elif root.exists():
            paths.extend(root.rglob("SKILL.md"))
    return sorted(set(path.resolve() for path in paths))


def scan_originality(
    root: Path | str, source_roots: Iterable[Path | str], threshold: float = 0.82
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    sources = _source_skills(Path(source).resolve() for source in source_roots)
    if not sources:
        return {
            "status": "BLOCKED",
            "reason": "upstream source content is unavailable; restore snapshots from registry/upstream-sources.yaml",
            "threshold": threshold,
            "sources_scanned": 0,
            "undeclared_overlaps": [],
            "declared_overlaps": [],
        }
    undeclared: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    for skill_path in sorted((root_path / "skills").glob("*/SKILL.md")):
        frontmatter, _ = parse_frontmatter(skill_path)
        provenance = frontmatter["metadata"]["studio"]["provenance"]
        best_path: Path | None = None
        best_score = 0.0
        skill_tokens = _token_set(skill_path)
        for source_path in sources:
            score = _jaccard(skill_tokens, _token_set(source_path))
            if score > best_score:
                best_score = score
                best_path = source_path
        if best_path is None or best_score < threshold:
            continue
        finding = {
            "skill": skill_path.parent.name,
            "source": str(best_path),
            "jaccard": round(best_score, 4),
        }
        if provenance.get("derived_from") == "none":
            undeclared.append(finding)
        else:
            declared.append(finding)
    return {
        "status": "FAIL" if undeclared else "PASS",
        "threshold": threshold,
        "sources_scanned": len(sources),
        "undeclared_overlaps": undeclared,
        "declared_overlaps": declared,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect high-overlap skills without declared provenance.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("sources", nargs="*")
    parser.add_argument("--threshold", type=float, default=0.82)
    args = parser.parse_args(argv)
    sources = [Path(source) for source in args.sources]
    if not sources:
        sources = list((Path(args.root) / ".research" / "repos").glob("*"))
    report = scan_originality(Path(args.root), sources, args.threshold)
    print(json.dumps(report, indent=2))
    if report["status"] == "PASS":
        return 0
    return 2 if report["status"] == "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
