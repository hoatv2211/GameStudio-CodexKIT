from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tests._meta.support import temporary_directory


class FakeUnavailableRunner:
    def __call__(self, argv: list[str], *, cwd: Path) -> object:
        raise FileNotFoundError("codegraph")


class ProjectSkillOverlayTests(unittest.TestCase):
    def _profile(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "workspace": {"name": "Synthetic Studio", "root_git": False, "default_concurrency": 2},
            "repositories": [
                {
                    "id": "client",
                    "path": "Client",
                    "git_root": True,
                    "subsystems": ["unity", "lua"],
                    "owner_skill": "studio-project-intake",
                    "validation": [],
                },
                {
                    "id": "server",
                    "path": "Server",
                    "git_root": True,
                    "subsystems": ["server", "database", "lua"],
                    "owner_skill": "studio-project-intake",
                    "validation": [],
                },
                {
                    "id": "native",
                    "path": "Native",
                    "git_root": True,
                    "subsystems": ["server"],
                    "owner_skill": "studio-project-intake",
                    "validation": [],
                },
                {
                    "id": "java-services",
                    "path": "JavaServices",
                    "git_root": True,
                    "subsystems": ["java"],
                    "owner_skill": "studio-project-intake",
                    "validation": [],
                },
                {
                    "id": "go-services",
                    "path": "GoServices",
                    "git_root": True,
                    "subsystems": ["server"],
                    "owner_skill": "studio-project-intake",
                    "validation": [],
                },
            ],
            "exclusions": [],
            "agents": {"specialists": []},
            "cross_project_contracts": [],
        }

    def _write_evidence(self, root: Path) -> None:
        (root / "Client" / "Assets").mkdir(parents=True)
        (root / "Client" / "ProjectSettings").mkdir()
        (root / "Client" / "Scripts").mkdir()
        (root / "Client" / "Scripts" / "player.cs").write_text("class Player {}", encoding="utf-8")
        (root / "Client" / "Lua").mkdir()
        (root / "Client" / "Lua" / "main.lua").write_text("return {}", encoding="utf-8")
        (root / "Server").mkdir()
        (root / "Server" / "Server.csproj").write_text("<Project />", encoding="utf-8")
        (root / "Server" / "logic.lua").write_text("return {}", encoding="utf-8")
        (root / "Server" / "schema.sql").write_text("-- schema", encoding="utf-8")
        (root / "Native").mkdir()
        (root / "Native" / "CMakeLists.txt").write_text("project(native)", encoding="utf-8")
        (root / "Native" / "main.cpp").write_text("int main() {}", encoding="utf-8")
        (root / "JavaServices").mkdir()
        (root / "JavaServices" / "pom.xml").write_text("<project />", encoding="utf-8")
        (root / "JavaServices" / "Main.java").write_text("class Main {}", encoding="utf-8")
        (root / "GoServices").mkdir()
        (root / "GoServices" / "go.mod").write_text("module example.invalid/game", encoding="utf-8")
        (root / "GoServices" / "main.go").write_text("package main", encoding="utf-8")
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "build.yml").write_text("name: build", encoding="utf-8")

    def test_plans_workspace_customization_and_evidence_backed_domain_skills(self) -> None:
        from scripts.project_skill_overlay import plan_project_skill_overlay

        with temporary_directory() as temp:
            root = Path(temp)
            self._write_evidence(root)

            plan = plan_project_skill_overlay(root, self._profile())

        self.assertEqual(
            [
                "project-build-release",
                "project-cpp-server",
                "project-customization",
                "project-data-pipeline",
                "project-dotnet-server",
                "project-go-services",
                "project-java-services",
                "project-lua-gameplay",
                "project-unity-client",
                "project-workspace",
            ],
            plan["skill_ids"],
        )
        repositories = {item["id"]: item["repositories"] for item in plan["skills"]}
        self.assertEqual(["client"], repositories["project-unity-client"])
        self.assertEqual(["server"], repositories["project-dotnet-server"])
        self.assertEqual(["native"], repositories["project-cpp-server"])
        self.assertEqual(["java-services"], repositories["project-java-services"])
        self.assertEqual(["go-services"], repositories["project-go-services"])

    def test_renders_identical_skill_content_for_agents_and_codex(self) -> None:
        from scripts.project_skill_overlay import plan_project_skill_overlay

        with temporary_directory() as temp:
            root = Path(temp)
            self._write_evidence(root)

            first = plan_project_skill_overlay(root, self._profile())
            second = plan_project_skill_overlay(root, self._profile())

        self.assertEqual(first, second)
        operations = {item["path"]: item["content"] for item in first["operations"]}
        for skill_id in first["skill_ids"]:
            agents_path = f".agents/skills/{skill_id}/SKILL.md"
            codex_path = f".codex/skills/{skill_id}/SKILL.md"
            self.assertEqual(operations[agents_path], operations[codex_path])
            self.assertIn("generated_by: scripts/project_skill_overlay.py", operations[agents_path])

    def test_preserves_unmanaged_collisions_on_both_runtime_surfaces(self) -> None:
        from scripts.project_skill_overlay import plan_project_skill_overlay

        with temporary_directory() as temp:
            root = Path(temp)
            agents_skill = root / ".agents" / "skills" / "project-workspace" / "SKILL.md"
            codex_skill = root / ".codex" / "skills" / "project-workspace" / "SKILL.md"
            agents_skill.parent.mkdir(parents=True)
            codex_skill.parent.mkdir(parents=True)
            agents_skill.write_text("local agents skill\n", encoding="utf-8")
            codex_skill.write_text("local codex skill\n", encoding="utf-8")

            plan = plan_project_skill_overlay(root, self._profile())

        proposed = {item["path"] for item in plan["operations"]}
        self.assertNotIn(".agents/skills/project-workspace/SKILL.md", proposed)
        self.assertNotIn(".codex/skills/project-workspace/SKILL.md", proposed)
        self.assertEqual(
            [
                ".agents/skills/project-workspace/SKILL.md",
                ".codex/skills/project-workspace/SKILL.md",
            ],
            plan["preserved"],
        )
        self.assertEqual(2, len(plan["collisions"]))


    def test_scaffold_reports_project_skills_without_writing(self) -> None:
        from scripts.project_scaffold import scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            self._write_evidence(root)
            for repository in ("Client", "Server", "Native", "JavaServices", "GoServices"):
                (root / repository / ".git").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )

            report = scaffold_project(root, codegraph_runner=FakeUnavailableRunner())

        self.assertIn("project-workspace", report["project_skills"]["skill_ids"])
        self.assertIn(".agents/skills/project-workspace/SKILL.md", report["proposed"])
        self.assertIn(".codex/skills/project-workspace/SKILL.md", report["proposed"])
        self.assertFalse((root / ".agents" / "skills" / "project-workspace" / "SKILL.md").exists())

    def test_project_skill_evidence_activates_repository_scoped_specialists(self) -> None:
        from scripts.agent_overlay import plan_agent_overlay
        from scripts.project_skill_overlay import plan_project_skill_overlay

        kit_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            root = Path(temp)
            self._write_evidence(root)
            profile = self._profile()
            profile_path = root / "profile.yaml"
            profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
            skill_plan = plan_project_skill_overlay(root, profile)

            agent_plan = plan_agent_overlay(
                root,
                template_root=kit_root / "skills" / "studio-project-scaffold" / "templates" / "agents",
                profile_path=profile_path,
                known_skills={"studio-project-intake"},
                project_skills=skill_plan["skills"],
            )

        activated = set(agent_plan["activated_roles"])
        self.assertTrue(
            {
                "unity-csharp-client",
                "csharp-backend",
                "cpp-game-server",
                "golang-services",
                "game-data-engineer",
                "lua-gameplay-client",
                "lua-gameplay-server",
            }.issubset(activated)
        )
        operations = {item["path"]: item["content"] for item in agent_plan["operations"]}
        self.assertIn("Client/Assets/**", operations[".codex/agents/unity-csharp-client.toml"])
        self.assertIn("Server/**/*.cs", operations[".codex/agents/csharp-backend.toml"])
        self.assertIn("Client/**/*.lua", operations[".codex/agents/lua-gameplay-client.toml"])
        self.assertIn("Server/**/*.lua", operations[".codex/agents/lua-gameplay-server.toml"])

    def test_scaffold_reports_inferred_agents_without_writing(self) -> None:
        from scripts.project_scaffold import scaffold_project

        with temporary_directory() as temp:
            root = Path(temp)
            self._write_evidence(root)
            for repository in ("Client", "Server", "Native", "JavaServices", "GoServices"):
                (root / repository / ".git").mkdir(parents=True)
                (root / repository / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main", encoding="utf-8"
                )

            report = scaffold_project(root, codegraph_runner=FakeUnavailableRunner())

        self.assertIn("investigator", report["project_agents"]["activated_roles"])
        self.assertIn("unity-csharp-client", report["project_agents"]["activated_roles"])
        self.assertIn("csharp-backend", report["project_agents"]["activated_roles"])
        self.assertFalse((root / ".codex" / "agents" / "unity-csharp-client.toml").exists())

if __name__ == "__main__":
    unittest.main()
