from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.common import load_yaml, normalized_tokens, parse_frontmatter
except ModuleNotFoundError:
    from common import load_yaml, normalized_tokens, parse_frontmatter


STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "the",
    "to",
    "use",
    "when",
    "with",
    "this",
    "that",
    "or",
    "not",
    "any",
    "before",
}


@dataclass(frozen=True)
class EvalFailure:
    message: str
    case_file: Path | None = None
    prompt: str | None = None
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True)
class EvalSummary:
    total: int
    passed: int
    failures: list[EvalFailure]


def _tokens(text: str) -> list[str]:
    return [token for token in normalized_tokens(text) if token not in STOPWORDS and len(token) > 1]


def _descriptions(root: Path, capabilities: list[dict[str, Any]]) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for capability in capabilities:
        path = root / str(capability["path"])
        if not path.exists():
            continue
        frontmatter, _ = parse_frontmatter(path)
        descriptions[str(capability["id"])] = f"{capability['id']} {frontmatter.get('description', '')}"
    return descriptions


def rank_skills(prompt: str, descriptions: dict[str, str]) -> list[tuple[str, float]]:
    query = Counter(_tokens(prompt))
    documents = {name: Counter(_tokens(text)) for name, text in descriptions.items()}
    document_count = max(len(documents), 1)
    average_length = sum(sum(document.values()) for document in documents.values()) / document_count
    document_frequency: Counter[str] = Counter()
    for document in documents.values():
        document_frequency.update(document.keys())

    rankings: list[tuple[str, float]] = []
    for name, document in documents.items():
        length = max(sum(document.values()), 1)
        score = 0.0
        for token, query_frequency in query.items():
            term_frequency = document.get(token, 0)
            if not term_frequency:
                continue
            frequency = document_frequency[token]
            inverse_document_frequency = math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
            denominator = term_frequency + 1.2 * (1 - 0.75 + 0.75 * length / max(average_length, 1))
            score += inverse_document_frequency * (term_frequency * 2.2 / denominator) * query_frequency
        name_tokens = set(_tokens(name))
        score += 0.35 * len(name_tokens.intersection(query))
        rankings.append((name, score))
    return sorted(rankings, key=lambda item: (-item[1], item[0]))


def _validate_case(case: Any) -> str | None:
    if not isinstance(case, dict):
        return "case must be an object"
    allowed = {"prompt", "expected_skill", "type", "owner"}
    if set(case) - allowed:
        return f"unknown case fields: {', '.join(sorted(set(case) - allowed))}"
    if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
        return "prompt must be a non-empty string"
    if not isinstance(case.get("expected_skill"), str):
        return "expected_skill must be a string"
    if case.get("type") not in {"positive", "negative", "collision"}:
        return "type must be positive, negative, or collision"
    if case.get("type") == "negative" and not isinstance(case.get("owner"), str):
        return "negative cases require owner"
    if case.get("type") == "negative" and case.get("owner") != case.get("expected_skill"):
        return "negative owner must equal expected_skill"
    return None


def evaluate_repository(root: Path | str) -> EvalSummary:
    root_path = Path(root).resolve()
    registry_path = root_path / "registry" / "capabilities.yaml"
    if not registry_path.exists():
        return EvalSummary(0, 0, [EvalFailure("missing registry/capabilities.yaml")])
    registry = load_yaml(registry_path)
    capabilities = registry.get("capabilities", []) if isinstance(registry, dict) else []
    descriptions = _descriptions(root_path, capabilities)
    failures: list[EvalFailure] = []
    total = 0
    passed = 0
    routing_dir = root_path / "evals" / "routing"

    for capability in capabilities:
        target = str(capability.get("id", ""))
        if capability.get("type") == "root":
            continue
        case_file = routing_dir / f"{target}.json"
        if not case_file.exists():
            failures.append(EvalFailure(f"missing routing cases for {target}", case_file=case_file))
            continue
        try:
            payload = json.loads(case_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            failures.append(EvalFailure(f"invalid JSON: {error}", case_file=case_file))
            continue
        if not isinstance(payload, dict) or payload.get("target_skill") != target or not isinstance(payload.get("cases"), list):
            failures.append(EvalFailure("invalid routing file envelope", case_file=case_file))
            continue
        cases = payload["cases"]
        counts = Counter(case.get("type") for case in cases if isinstance(case, dict))
        minimums = {"positive": 3, "negative": 2, "collision": 1}
        for case_type, minimum in minimums.items():
            if counts[case_type] < minimum:
                failures.append(
                    EvalFailure(
                        f"minimum {case_type} cases for {target}: expected {minimum}, got {counts[case_type]}",
                        case_file=case_file,
                    )
                )
        for case in cases:
            error = _validate_case(case)
            if error:
                failures.append(EvalFailure(error, case_file=case_file))
                continue
            total += 1
            expected = case["expected_skill"]
            ranking = rank_skills(case["prompt"], descriptions)
            actual = ranking[0][0] if ranking else None
            if actual == expected:
                passed += 1
            else:
                failures.append(
                    EvalFailure(
                        "rank-1 mismatch",
                        case_file=case_file,
                        prompt=case["prompt"],
                        expected=expected,
                        actual=actual,
                    )
                )
    return EvalSummary(total=total, passed=passed, failures=failures)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run deterministic Tier-A routing evaluation.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    summary = evaluate_repository(Path(args.root))
    for failure in summary.failures:
        location = f" [{failure.case_file}]" if failure.case_file else ""
        detail = ""
        if failure.prompt is not None:
            detail = f" prompt={failure.prompt!r} expected={failure.expected!r} actual={failure.actual!r}"
        print(f"FAIL{location}: {failure.message}{detail}")
    print(f"route-eval: {summary.passed}/{summary.total} cases passed; {len(summary.failures)} failure(s)")
    return 1 if summary.failures else 0


if __name__ == "__main__":
    sys.exit(main())
