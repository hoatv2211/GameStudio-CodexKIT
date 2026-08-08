from __future__ import annotations

import sys
from pathlib import Path

try:
    from scripts.runner_eval import RunnerEvalSummary, evaluate, run_cli
except ModuleNotFoundError:
    from runner_eval import RunnerEvalSummary, evaluate, run_cli


def evaluate_pressure(
    root: Path | str, results_path: Path | str | None = None
) -> RunnerEvalSummary:
    return evaluate(root, "pressure", results_path)


def main(argv: list[str] | None = None) -> int:
    return run_cli("pressure", "Export or validate governed pressure evaluation results.", argv)


if __name__ == "__main__":
    sys.exit(main())
