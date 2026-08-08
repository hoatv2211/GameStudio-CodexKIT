from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.common import load_yaml, parse_frontmatter
    from scripts.route_eval import rank_skills
except ModuleNotFoundError:
    from common import load_yaml, parse_frontmatter
    from route_eval import rank_skills


DEFAULT_FIXTURE = Path("evals/external-catalog/cases.json")


def _canonical_descriptions(root: Path) -> dict[str, str]:
    registry = load_yaml(root / "registry" / "capabilities.yaml")
    descriptions: dict[str, str] = {}
    for capability in registry.get("capabilities", []):
        skill_id = str(capability.get("id", ""))
        skill_path = root / str(capability.get("path", ""))
        if not skill_id or not skill_path.exists():
            continue
        frontmatter, _ = parse_frontmatter(skill_path)
        descriptions[skill_id] = f"{skill_id} {frontmatter.get('description', '')}"
    return descriptions


def _external_root_descriptions(roots: list[Path]) -> tuple[dict[str, str], list[str]]:
    descriptions: dict[str, str] = {}
    errors: list[str] = []
    for root_index, external_root in enumerate(roots, start=1):
        if not external_root.is_dir():
            errors.append(f"external catalog root is not a directory: {external_root}")
            continue
        for skill_path in sorted(external_root.rglob("SKILL.md")):
            try:
                frontmatter, _ = parse_frontmatter(skill_path)
            except (OSError, ValueError) as error:
                errors.append(f"{skill_path}: {error}")
                continue
            description = frontmatter.get("description")
            if not isinstance(description, str) or not description.strip():
                errors.append(f"{skill_path}: missing description")
                continue
            relative = skill_path.parent.relative_to(external_root).as_posix()
            slug = re.sub(r"[^a-z0-9-]+", "-", relative.lower()).strip("-") or "skill"
            skill_id = f"external-{root_index}-{slug}"
            descriptions[skill_id] = f"{skill_id} {description}"
    return descriptions, errors


def _failures_for_case(
    case: dict[str, Any], descriptions: dict[str, str], external_ids: set[str]
) -> list[dict[str, Any]]:
    ranking = rank_skills(str(case["prompt"]), descriptions)
    ranks = {skill: index for index, (skill, _) in enumerate(ranking, start=1)}
    expected = str(case["expected_skill"])
    failures: list[dict[str, Any]] = []
    if ranks.get(expected) != 1:
        failures.append(
            {
                "id": case["id"],
                "reason": "internal skill is not rank-1 against external catalog",
                "expected": expected,
                "actual": ranking[0][0] if ranking else None,
            }
        )
    for competitor in case.get("must_beat", []):
        if competitor not in external_ids:
            failures.append(
                {"id": case["id"], "reason": "must_beat entries must be external skills", "competitor": competitor}
            )
            continue
        if competitor not in ranks:
            failures.append(
                {"id": case["id"], "reason": "declared external competitor is missing", "competitor": competitor}
            )
        elif ranks[expected] >= ranks[competitor]:
            failures.append(
                {
                    "id": case["id"],
                    "reason": "internal skill does not outrank external competitor",
                    "expected": expected,
                    "competitor": competitor,
                    "expected_rank": ranks[expected],
                    "competitor_rank": ranks[competitor],
                }
            )
    return failures


def _validate_fixture(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["fixture must be an object"]
    errors: list[str] = []
    external = payload.get("external_skills")
    cases = payload.get("cases")
    if not isinstance(external, list) or not external:
        errors.append("external_skills must be a non-empty list")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
    ids: set[str] = set()
    for item in external if isinstance(external, list) else []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("description"):
            errors.append("external skills require id and description")
            continue
        skill_id = str(item["id"])
        if skill_id in ids:
            errors.append(f"duplicate external skill id: {skill_id}")
        ids.add(skill_id)
    case_ids: set[str] = set()
    for item in cases if isinstance(cases, list) else []:
        if not isinstance(item, dict):
            errors.append("cases must contain objects")
            continue
        for field in ("id", "prompt", "expected_skill"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"case requires non-empty {field}")
        case_id = str(item.get("id", ""))
        if case_id in case_ids:
            errors.append(f"duplicate case id: {case_id}")
        case_ids.add(case_id)
        if not isinstance(item.get("must_beat", []), list) or not all(
            isinstance(value, str) and value for value in item.get("must_beat", [])
        ):
            errors.append(f"case {case_id} must_beat must be a string list")
    return errors


def evaluate_external_collisions(
    root: Path | str,
    fixture: Path | str | None = None,
    external_roots: list[Path | str] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    fixture_path = root_path / DEFAULT_FIXTURE if fixture is None else Path(fixture).resolve()
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"verdict": "FAIL", "total": 0, "passed": 0, "failures": [str(error)]}
    errors = _validate_fixture(payload)
    if errors:
        return {"verdict": "FAIL", "total": 0, "passed": 0, "failures": errors}

    descriptions = _canonical_descriptions(root_path)
    canonical_ids = set(descriptions)
    external_ids = {str(item["id"]) for item in payload["external_skills"]}
    collisions = sorted(external_ids.intersection(descriptions))
    if collisions:
        return {
            "verdict": "FAIL",
            "total": len(payload["cases"]),
            "passed": 0,
            "external_skills": sorted(external_ids),
            "failures": [f"external ids collide with canonical skills: {collisions}"],
        }
    descriptions.update(
        {str(item["id"]): str(item["description"]) for item in payload["external_skills"]}
    )
    live_descriptions, live_errors = _external_root_descriptions(
        [Path(path).resolve() for path in (external_roots or [])]
    )
    if live_errors:
        return {
            "verdict": "FAIL",
            "total": len(payload["cases"]),
            "passed": 0,
            "external_skills": sorted(set(descriptions) - canonical_ids),
            "failures": live_errors,
        }
    descriptions.update(live_descriptions)
    failures: list[dict[str, Any]] = []
    passed = 0
    for case in payload["cases"]:
        if case["expected_skill"] not in descriptions or case["expected_skill"] in external_ids:
            failures.append({"id": case["id"], "reason": "expected skill is not canonical"})
            continue
        case_failures = _failures_for_case(case, descriptions, external_ids)
        if case_failures:
            failures.extend(case_failures)
        else:
            passed += 1
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "total": len(payload["cases"]),
        "passed": passed,
        "external_skills": sorted(set(descriptions) - canonical_ids),
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate routing against a catalog of generic external skills.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--external-root", action="append", type=Path, default=[])
    args = parser.parse_args(argv)
    report = evaluate_external_collisions(args.root, args.fixture, args.external_root)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
