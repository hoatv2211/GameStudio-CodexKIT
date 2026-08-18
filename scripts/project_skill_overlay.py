from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


GENERATED_BY = "scripts/project_skill_overlay.py"
GENERATED_FIELD = f"generated_by: {GENERATED_BY}"
EXCLUDED_DIRECTORIES = {
    ".agents", ".archive", ".cache", ".codex", ".git",
    "Library", "Logs", "Temp", "bin", "node_modules", "obj",
}
SKILL_DESCRIPTIONS = {
    "project-workspace": "Route work across this project's repositories, owners, contracts, and validation slices.",
    "project-customization": "Maintain project-local conventions and customization without changing canonical kit workflows.",
    "project-unity-client": "Route Unity client work through this project's Assets, ProjectSettings, and validation evidence.",
    "project-dotnet-server": "Route .NET server and service work through project-local build and test contracts.",
    "project-cpp-server": "Route native C or C++ server work through project-local build and runtime contracts.",
    "project-java-services": "Route Java service work through project-local build, test, and deployment boundaries.",
    "project-go-services": "Route Go service work through project-local module, test, and service boundaries.",
    "project-lua-gameplay": "Route Lua gameplay and contract work through project-local authority and validation.",
    "project-data-pipeline": "Route schema, migration, configuration, and generated-data work through project-local ownership.",
    "project-build-release": "Route build, CI, packaging, and release work through project-local gates without publishing.",
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _safe_skill_path(project: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(relative)
    parts = pure.parts
    valid = (
        len(parts) == 4
        and parts[0] in {".agents", ".codex"}
        and parts[1] == "skills"
        and parts[3] == "SKILL.md"
    )
    if pure.is_absolute() or windows.is_absolute() or windows.drive or not valid or ".." in parts:
        raise ValueError(f"unsafe project skill path: {relative}")
    project_root = project.resolve()
    current = project_root
    if _is_reparse_point(current):
        raise ValueError(f"project root is a symlink or reparse point: {current}")
    for part in parts:
        current = current / part
        if current.exists() and _is_reparse_point(current):
            raise ValueError(f"symlink or reparse point is not allowed: {current}")
    target = project_root.joinpath(*parts).resolve()
    try:
        target.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"project skill path escapes root: {relative}") from error
    return target


def _walk_files(root: Path, exclusions: Iterable[str]) -> list[Path]:
    excluded = {name.casefold() for name in EXCLUDED_DIRECTORIES}
    excluded.update(name.casefold() for name in exclusions)
    files: list[Path] = []
    if not root.is_dir():
        return files
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [
            name for name in directory_names
            if name.casefold() not in excluded and not _is_reparse_point(current_path / name)
        ]
        files.extend(current_path / name for name in file_names)
    return files


def _repository_evidence(project: Path, repository: dict[str, Any], exclusions: Iterable[str]) -> set[str]:
    relative = str(repository["path"])
    repository_root = project if relative == "." else project / relative
    files = _walk_files(repository_root, exclusions)
    names = {path.name for path in files}
    suffixes = {path.suffix.casefold() for path in files}
    subsystems = {str(value).casefold() for value in repository.get("subsystems", [])}
    evidence: set[str] = set()
    if "unity" in subsystems or ((repository_root / "Assets").is_dir() and (repository_root / "ProjectSettings").is_dir()):
        evidence.add("unity")
    if suffixes.intersection({".csproj", ".sln"}):
        evidence.add("dotnet")
    if "CMakeLists.txt" in names or suffixes.intersection({".c", ".cc", ".cpp", ".cxx", ".vcxproj"}):
        evidence.add("cpp")
    if "java" in subsystems or "pom.xml" in names or {"build.gradle", "build.gradle.kts"}.intersection(names):
        evidence.add("java")
    if "go.mod" in names or ".go" in suffixes:
        evidence.add("go")
    if "lua" in subsystems or ".lua" in suffixes:
        evidence.add("lua")
    if "database" in subsystems or suffixes.intersection({".sql", ".csv"}):
        evidence.add("data")
    return evidence


def _workspace_has_build_release(project: Path, repositories: list[dict[str, Any]]) -> bool:
    if len(repositories) > 1:
        return True
    indicators = (
        project / ".github" / "workflows", project / ".circleci",
        project / "Jenkinsfile", project / "azure-pipelines.yml", project / "build",
    )
    return any(path.exists() for path in indicators)


def _render_skill(skill_id: str, *, workspace_name: str, repositories: list[dict[str, Any]]) -> str:
    repository_ids = [str(repository["id"]) for repository in repositories]
    repository_text = ", ".join(f"`{value}`" for value in repository_ids) or "workspace-wide"
    lines = [
        "---",
        f"name: {skill_id}",
        f"description: {SKILL_DESCRIPTIONS[skill_id]}",
        f"generated_by: {GENERATED_BY}",
        "---",
        f"# {skill_id}",
        "",
        f"Project-local workflow for **{workspace_name}**.",
        "",
        "## Scope",
        f"- Repositories: {repository_text}.",
        "- Read-only discovery is the default.",
        "- One writer owns each file or generated output.",
        "- Canonical kit skills remain reusable; this file only carries local routes and evidence.",
        "",
        "## Workflow",
        "1. Verify the selected repository, current Git state, and project-local ownership.",
        "2. Select the narrowest canonical skill that matches the requested work.",
        "3. Declare owned paths, do-not-touch paths, validation, and rollback before mutation.",
        "4. Run the narrowest available verification and label unavailable checks BLOCKED.",
        "5. Return changed paths, commands, exit codes, artifacts, assumptions, and remaining risk.",
        "",
        "## Repository Evidence",
    ]
    if repositories:
        for repository in repositories:
            subsystems = ", ".join(repository.get("subsystems", [])) or "unclassified"
            validation = repository.get("validation", [])
            validation_text = ", ".join(item["command"] for item in validation) or "not declared"
            lines.append(
                f"- `{repository['id']}` at `{repository['path']}`: subsystems {subsystems}; validation {validation_text}."
            )
    else:
        lines.append("- Workspace-wide project customization; repository route required before edits.")
    lines.extend([
        "", "## Safety",
        "Do not publish, deploy, alter credentials, run destructive database actions, or overwrite unmanaged project-local files without explicit approval.",
        "",
    ])
    return "\n".join(lines)


def plan_project_skill_overlay(project: Path | str, profile: dict[str, Any]) -> dict[str, object]:
    project_path = Path(project).resolve()
    repositories = list(profile.get("repositories", []))
    exclusions = list(profile.get("exclusions", []))
    by_domain: dict[str, list[dict[str, Any]]] = {
        "unity": [], "dotnet": [], "cpp": [], "java": [], "go": [], "lua": [], "data": [],
    }
    for repository in repositories:
        for domain in _repository_evidence(project_path, repository, exclusions):
            by_domain[domain].append(repository)

    skill_repositories: dict[str, list[dict[str, Any]]] = {
        "project-workspace": repositories,
        "project-customization": [],
    }
    domain_skills = {
        "unity": "project-unity-client", "dotnet": "project-dotnet-server",
        "cpp": "project-cpp-server", "java": "project-java-services",
        "go": "project-go-services", "lua": "project-lua-gameplay",
        "data": "project-data-pipeline",
    }
    for domain, skill_id in domain_skills.items():
        if by_domain[domain]:
            skill_repositories[skill_id] = sorted(by_domain[domain], key=lambda item: str(item["id"]))
    if _workspace_has_build_release(project_path, repositories):
        skill_repositories["project-build-release"] = repositories

    skills: list[dict[str, object]] = []
    operations: list[dict[str, str]] = []
    preserved: list[str] = []
    collisions: list[dict[str, str]] = []
    workspace_name = str(profile.get("workspace", {}).get("name", project_path.name))
    for skill_id in sorted(skill_repositories):
        scoped_repositories = skill_repositories[skill_id]
        content = _render_skill(skill_id, workspace_name=workspace_name, repositories=scoped_repositories)
        skills.append({
            "id": skill_id,
            "repositories": [str(repository["id"]) for repository in scoped_repositories],
            "sha256": _sha256_text(content),
        })
        for runtime_root in (".agents", ".codex"):
            relative = PurePosixPath(runtime_root, "skills", skill_id, "SKILL.md").as_posix()
            destination = _safe_skill_path(project_path, relative)
            existing = destination.read_text(encoding="utf-8", errors="replace") if destination.is_file() else ""
            if destination.exists() and (not destination.is_file() or GENERATED_FIELD not in existing):
                preserved.append(relative)
                collisions.append({"path": relative, "kind": "unmanaged-skill", "skill_id": skill_id})
                continue
            operations.append({"path": relative, "content": content})

    operations.sort(key=lambda item: item["path"])
    preserved.sort()
    collisions.sort(key=lambda item: item["path"])
    return {
        "skills": skills,
        "skill_ids": [str(skill["id"]) for skill in skills],
        "operations": operations,
        "preserved": preserved,
        "collisions": collisions,
        "owned_files": [
            {"path": operation["path"], "sha256": _sha256_text(operation["content"])}
            for operation in operations
        ],
    }
