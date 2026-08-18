from __future__ import annotations

import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


class ProjectComplexityTests(unittest.TestCase):
    def test_classifies_low_medium_and_high_from_explicit_metrics(self) -> None:
        from scripts.project_complexity import ComplexityMetrics, evaluate_complexity

        low = evaluate_complexity(ComplexityMetrics(source_file_count=25))
        medium = evaluate_complexity(
            ComplexityMetrics(
                nested_git_roots=("client", "server"),
                root_git=True,
                language_count=4,
                languages=("csharp", "lua", "python", "sql"),
                subsystem_count=4,
                subsystems=("database", "lua", "server", "unity"),
            )
        )
        high = evaluate_complexity(
            ComplexityMetrics(
                nested_git_roots=("client", "server", "services"),
                root_git=False,
                source_file_count=10001,
                language_count=7,
                languages=("c", "cpp", "csharp", "java", "lua", "python", "sql"),
                subsystem_count=5,
                subsystems=("database", "java", "lua", "server", "unity"),
                cross_project_contracts=("api", "protocol"),
                generated_pipelines=("client-codegen", "schema-codegen"),
                build_systems=("dotnet", "gradle"),
                project_reference_signals=1,
            )
        )

        self.assertEqual((0, "LOW"), (low.score, low.classification))
        self.assertEqual((5, "MEDIUM"), (medium.score, medium.classification))
        self.assertGreaterEqual(high.score, 7)
        self.assertEqual("HIGH", high.classification)
        self.assertEqual("RECOMMEND_INSTALL_PLAN", high.codegraph_recommendation)
        self.assertFalse(high.interactive)

    def test_scoring_reasons_cover_each_approved_signal(self) -> None:
        from scripts.project_complexity import ComplexityMetrics, evaluate_complexity

        result = evaluate_complexity(
            ComplexityMetrics(
                nested_git_roots=("a", "b"),
                root_git=False,
                source_file_count=3001,
                language_count=4,
                languages=("cpp", "csharp", "lua", "python"),
                subsystem_count=4,
                subsystems=("database", "lua", "server", "unity"),
                cross_project_contracts=("protocol",),
                generated_pipelines=("client-codegen", "schema-codegen"),
                build_systems=("cmake", "dotnet"),
            )
        )

        self.assertEqual(12, result.score)
        self.assertEqual(
            {
                "nested_git_roots",
                "source_file_count",
                "languages",
                "subsystems",
                "cross_project_contracts",
                "generated_pipelines",
                "no_root_git",
                "multiple_build_systems",
            },
            {reason.code for reason in result.reasons},
        )

    def test_discovers_nested_repositories_source_languages_and_subsystems(self) -> None:
        from scripts.project_complexity import analyze_project_complexity

        with temporary_directory() as temp:
            root = Path(temp)
            for repository in ("Client", "Server"):
                (root / repository / ".git").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )
            (root / "Client" / "Assets").mkdir()
            (root / "Client" / "ProjectSettings").mkdir()
            (root / "Client" / "player.cs").write_text("class Player {}", encoding="utf-8")
            (root / "Server" / "GameServer.csproj").write_text("<Project />", encoding="utf-8")
            (root / "Server" / "main.lua").write_text("return {}", encoding="utf-8")
            (root / "database").mkdir()
            (root / "database" / "schema.sql").write_text("-- schema", encoding="utf-8")

            result = analyze_project_complexity(root)

        self.assertEqual(("Client", "Server"), result.metrics.nested_git_roots)
        self.assertFalse(result.metrics.root_git)
        self.assertEqual(3, result.metrics.source_file_count)
        self.assertEqual(("csharp", "lua", "sql"), result.metrics.languages)
        self.assertEqual(("database", "lua", "server", "unity"), result.metrics.subsystems)

    def test_discovers_contract_generation_and_build_reference_signals(self) -> None:
        from scripts.project_complexity import analyze_project_complexity

        with temporary_directory() as temp:
            root = Path(temp)
            for repository in ("Client", "Server"):
                (root / repository / ".git").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )
            (root / "Client" / "Contracts").mkdir()
            (root / "Client" / "Contracts" / "player.dto.cs").write_text(
                "class PlayerDto {}", encoding="utf-8"
            )
            (root / "Server" / "Protocol").mkdir()
            (root / "Server" / "Protocol" / "login.proto").write_text(
                "syntax = 'proto3';", encoding="utf-8"
            )
            (root / "Client" / "generate_client.py").write_text("pass", encoding="utf-8")
            (root / "Server" / "codegen_schema.ps1").write_text("", encoding="utf-8")
            (root / "Client" / "CMakeLists.txt").write_text("project(client)", encoding="utf-8")
            (root / "Server" / "Server.csproj").write_text(
                '<Project><ProjectReference Include="../Shared/Shared.csproj" /></Project>',
                encoding="utf-8",
            )

            result = analyze_project_complexity(root)

        self.assertEqual(("dto", "protocol"), result.metrics.cross_project_contracts)
        self.assertEqual(("codegen_schema", "generate_client"), result.metrics.generated_pipelines)
        self.assertEqual(("cmake", "dotnet"), result.metrics.build_systems)
        self.assertEqual(1, result.metrics.project_reference_signals)

    def test_non_interactive_report_recommends_codegraph_only_for_high_complexity(self) -> None:
        from scripts.project_complexity import ComplexityMetrics, evaluate_complexity

        medium = evaluate_complexity(
            ComplexityMetrics(
                nested_git_roots=("client", "server"),
                root_git=False,
                source_file_count=3001,
            )
        )
        high = evaluate_complexity(
            ComplexityMetrics(
                nested_git_roots=("client", "server", "services"),
                root_git=False,
                source_file_count=10001,
            )
        )

        self.assertEqual("CONSIDER", medium.codegraph_recommendation)
        self.assertEqual("RECOMMEND_INSTALL_PLAN", high.codegraph_recommendation)
        self.assertFalse(medium.interactive)
        self.assertFalse(high.interactive)


    def test_scaffold_report_includes_non_interactive_complexity_assessment(self) -> None:
        from scripts.project_scaffold import scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            for repository in ("Client", "Server"):
                (root / repository / ".git").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )
            (root / "Client" / "Assets").mkdir()
            (root / "Client" / "ProjectSettings").mkdir()
            (root / "Client" / "player.cs").write_text("class Player {}", encoding="utf-8")
            (root / "Server" / "GameServer.csproj").write_text("<Project />", encoding="utf-8")
            (root / "Server" / "main.lua").write_text("return {}", encoding="utf-8")
            (root / "Server" / "database").mkdir()
            (root / "Server" / "database" / "schema.sql").write_text(
                "-- schema", encoding="utf-8"
            )

            report = scaffold_project(root)

        self.assertEqual("MEDIUM", report["complexity"]["classification"])
        self.assertEqual("complexity likelihood", report["complexity"]["label"])
        self.assertEqual("CONSIDER", report["complexity"]["codegraph_recommendation"])
        self.assertFalse(report["complexity"]["interactive"])

if __name__ == "__main__":
    unittest.main()
