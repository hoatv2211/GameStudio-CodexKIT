from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory, write_registries, write_routing_file, write_skill


def minimum_cases(
    target: str,
    owner: str,
    positive_phrase: str,
    negative_phrase: str,
    collision_phrase: str,
) -> list[dict[str, str]]:
    return [
        {"prompt": f"{positive_phrase} alpha", "expected_skill": target, "type": "positive"},
        {"prompt": f"{positive_phrase} beta", "expected_skill": target, "type": "positive"},
        {"prompt": f"{positive_phrase} gamma", "expected_skill": target, "type": "positive"},
        {"prompt": f"{negative_phrase} one", "expected_skill": owner, "type": "negative", "owner": owner},
        {"prompt": f"{negative_phrase} two", "expected_skill": owner, "type": "negative", "owner": owner},
        {"prompt": collision_phrase, "expected_skill": target, "type": "collision"},
    ]


class RouteEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = temporary_directory()
        self.root = Path(self.temp_dir.name)
        write_skill(
            self.root,
            "studio-intake",
            description="Use when collecting project goal scope engine version constraints and creating an intake task packet.",
        )
        write_skill(
            self.root,
            "runtime-verification",
            description="Use when running build runtime commands checking exit codes and producing verification verdict evidence.",
        )
        write_registries(self.root, ["studio-intake", "runtime-verification"])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ranks_positive_negative_and_collision_cases(self) -> None:
        write_routing_file(
            self.root,
            "runtime-verification",
            minimum_cases(
                "runtime-verification",
                "studio-intake",
                "run build runtime exit code verdict",
                "collect project goal scope engine version intake",
                "verify build runtime evidence not project intake",
            ),
        )
        write_routing_file(
            self.root,
            "studio-intake",
            minimum_cases(
                "studio-intake",
                "runtime-verification",
                "collect project goal scope engine version intake",
                "run build runtime exit code verdict",
                "collect goal scope engine version intake before build",
            ),
        )
        from scripts.route_eval import evaluate_repository

        summary = evaluate_repository(self.root)
        self.assertEqual([], summary.failures)
        self.assertEqual(12, summary.total)
        self.assertEqual(12, summary.passed)

    def test_enforces_minimum_case_counts(self) -> None:
        write_routing_file(
            self.root,
            "runtime-verification",
            [{"prompt": "run build", "expected_skill": "runtime-verification", "type": "positive"}],
        )
        from scripts.route_eval import evaluate_repository

        summary = evaluate_repository(self.root)
        self.assertTrue(any("minimum" in failure.message for failure in summary.failures))

    def test_cli_reports_vietnamese_failure_without_unicode_crash(self) -> None:
        cases = minimum_cases(
            "runtime-verification",
            "studio-intake",
            "run build runtime exit code verdict",
            "collect project goal scope engine version intake",
            "verify build runtime evidence not project intake",
        )
        cases[0]["prompt"] = "kiểm tra mục tiêu dự án và phạm vi intake"
        write_routing_file(self.root, "runtime-verification", cases)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).parents[2] / "scripts" / "route_eval.py"),
                str(self.root),
            ],
            capture_output=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertNotIn(b"UnicodeEncodeError", result.stderr)
        self.assertIn("FAIL", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
