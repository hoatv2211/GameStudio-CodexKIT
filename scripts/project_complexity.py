from __future__ import annotations

import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRECTORIES = {
    ".agents",
    ".archive",
    ".cache",
    ".codex",
    ".git",
    "Library",
    "Logs",
    "Temp",
    "bin",
    "node_modules",
    "obj",
}

LANGUAGE_EXTENSIONS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
    ".php": "php",
    ".proto": "protobuf",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}

CONTRACT_TOKENS = {
    "api": re.compile(r"(?:^|[._\-/])(?:api|openapi|swagger)(?:$|[._\-/])", re.IGNORECASE),
    "dto": re.compile(r"(?:^|[._\-/])dto(?:$|[._\-/])", re.IGNORECASE),
    "protocol": re.compile(r"(?:^|[._\-/])(?:protocol|proto)(?:$|[._\-/])", re.IGNORECASE),
    "schema": re.compile(r"(?:^|[._\-/])schema(?:$|[._\-/])", re.IGNORECASE),
}

GENERATOR_PATTERN = re.compile(
    r"(?:^|[._-])(?:codegen|generate|generator|protoc)(?:$|[._-])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ComplexityMetrics:
    nested_git_roots: tuple[str, ...] = ()
    root_git: bool = False
    source_file_count: int = 0
    language_count: int = 0
    languages: tuple[str, ...] = ()
    subsystem_count: int = 0
    subsystems: tuple[str, ...] = ()
    cross_project_contracts: tuple[str, ...] = ()
    generated_pipelines: tuple[str, ...] = ()
    build_systems: tuple[str, ...] = ()
    project_reference_signals: int = 0

    def __post_init__(self) -> None:
        if self.source_file_count < 0 or self.project_reference_signals < 0:
            raise ValueError("complexity counts cannot be negative")
        if self.language_count < 0 or self.subsystem_count < 0:
            raise ValueError("complexity counts cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ComplexityReason:
    code: str
    points: int
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ComplexityAssessment:
    score: int
    classification: str
    label: str
    codegraph_recommendation: str
    interactive: bool
    metrics: ComplexityMetrics
    reasons: tuple[ComplexityReason, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "classification": self.classification,
            "label": self.label,
            "codegraph_recommendation": self.codegraph_recommendation,
            "interactive": self.interactive,
            "metrics": self.metrics.to_dict(),
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


def _reason(code: str, points: int, detail: str) -> ComplexityReason:
    return ComplexityReason(code=code, points=points, detail=detail)


def evaluate_complexity(metrics: ComplexityMetrics) -> ComplexityAssessment:
    reasons: list[ComplexityReason] = []
    nested_count = len(metrics.nested_git_roots)
    if nested_count >= 3:
        reasons.append(_reason("nested_git_roots", 3, f"{nested_count} nested Git repositories"))
    elif nested_count == 2:
        reasons.append(_reason("nested_git_roots", 2, "2 nested Git repositories"))

    if metrics.source_file_count > 10000:
        reasons.append(
            _reason("source_file_count", 3, f"{metrics.source_file_count} source files")
        )
    elif metrics.source_file_count > 3000:
        reasons.append(
            _reason("source_file_count", 2, f"{metrics.source_file_count} source files")
        )

    language_count = metrics.language_count or len(metrics.languages)
    if language_count >= 7:
        reasons.append(_reason("languages", 2, f"{language_count} detected languages"))
    elif language_count >= 4:
        reasons.append(_reason("languages", 1, f"{language_count} detected languages"))

    subsystem_count = metrics.subsystem_count or len(metrics.subsystems)
    if subsystem_count >= 4:
        reasons.append(_reason("subsystems", 2, f"{subsystem_count} detected subsystems"))

    if metrics.cross_project_contracts:
        reasons.append(
            _reason(
                "cross_project_contracts",
                2,
                "cross-project DTO, protocol, schema, or API signals detected",
            )
        )

    if len(metrics.generated_pipelines) >= 2:
        reasons.append(
            _reason(
                "generated_pipelines",
                1,
                f"{len(metrics.generated_pipelines)} generation pipeline signals",
            )
        )

    if nested_count and not metrics.root_git:
        reasons.append(_reason("no_root_git", 1, "nested repositories without a root Git repository"))

    if len(metrics.build_systems) >= 2 or metrics.project_reference_signals:
        reasons.append(
            _reason(
                "multiple_build_systems",
                1,
                "multiple build systems or project-reference signals detected",
            )
        )

    score = sum(reason.points for reason in reasons)
    if score >= 7:
        classification = "HIGH"
        recommendation = "RECOMMEND_INSTALL_PLAN"
    elif score >= 4:
        classification = "MEDIUM"
        recommendation = "CONSIDER"
    else:
        classification = "LOW"
        recommendation = "NOT_RECOMMENDED"

    return ComplexityAssessment(
        score=score,
        classification=classification,
        label="complexity likelihood",
        codegraph_recommendation=recommendation,
        interactive=False,
        metrics=metrics,
        reasons=tuple(reasons),
    )


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _walk(root: Path, exclusions: Iterable[str]) -> Iterable[tuple[Path, tuple[str, ...], tuple[str, ...]]]:
    excluded = {name.casefold() for name in EXCLUDED_DIRECTORIES}
    excluded.update(name.casefold() for name in exclusions)
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in directory_names:
            candidate = current_path / name
            if name.casefold() in excluded or _is_reparse_point(candidate):
                continue
            kept.append(name)
        directory_names[:] = kept
        yield current_path, tuple(kept), tuple(file_names)


def _valid_git_marker(repository: Path) -> bool:
    marker = repository / ".git"
    if marker.is_dir():
        return (marker / "HEAD").is_file()
    if not marker.is_file():
        return False
    try:
        first_line = marker.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return False
    if not first_line.casefold().startswith("gitdir:"):
        return False
    target_text = first_line.split(":", 1)[1].strip()
    if not target_text:
        return False
    target = Path(target_text)
    if not target.is_absolute():
        target = repository / target
    return target.is_dir() and (target / "HEAD").is_file()


def _detect_git_roots(root: Path) -> tuple[str, ...]:
    roots: list[str] = []
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if (".git" in directory_names or ".git" in file_names) and _valid_git_marker(current_path):
            relative = current_path.relative_to(root).as_posix()
            roots.append(relative if relative != "." else ".")
        directory_names[:] = [
            name
            for name in directory_names
            if name != ".git"
            and name.casefold() not in {item.casefold() for item in EXCLUDED_DIRECTORIES if item != ".git"}
            and not _is_reparse_point(current_path / name)
        ]
    return tuple(sorted(set(roots)))


def _detect_subsystems(root: Path, exclusions: Iterable[str]) -> tuple[str, ...]:
    subsystems: set[str] = set()
    for current, directory_names, file_names in _walk(root, exclusions):
        if "Assets" in directory_names and "ProjectSettings" in directory_names:
            subsystems.add("unity")
        for name in file_names:
            path = current / name
            suffix = path.suffix.casefold()
            if suffix in {".csproj", ".sln", ".vcxproj"} or name == "CMakeLists.txt":
                subsystems.add("server")
            if suffix == ".lua":
                subsystems.add("lua")
            if name in {"pom.xml", "build.gradle", "build.gradle.kts"} or suffix == ".gradle":
                subsystems.add("java")
            if suffix == ".sql" or "database" in {part.casefold() for part in path.parts}:
                subsystems.add("database")
    return tuple(sorted(subsystems))


def _repository_for(relative: str, git_roots: tuple[str, ...]) -> str:
    candidates = [
        repository
        for repository in git_roots
        if repository != "." and (relative == repository or relative.startswith(f"{repository}/"))
    ]
    return max(candidates, key=len) if candidates else "."


def _build_system(name: str, suffix: str) -> str | None:
    if name == "CMakeLists.txt":
        return "cmake"
    if suffix in {".csproj", ".sln", ".vcxproj"}:
        return "dotnet"
    if name in {"build.gradle", "build.gradle.kts"} or suffix == ".gradle":
        return "gradle"
    if name == "pom.xml":
        return "maven"
    if name == "package.json":
        return "node"
    if name == "Cargo.toml":
        return "cargo"
    if name == "go.mod":
        return "go"
    return None


def analyze_project_complexity(
    root: Path | str,
    *,
    git_roots: Iterable[str] | None = None,
    subsystems: Iterable[str] | None = None,
    exclusions: Iterable[str] = (),
) -> ComplexityAssessment:
    root_path = Path(root).resolve()
    observed_git_roots = tuple(sorted(set(git_roots))) if git_roots is not None else _detect_git_roots(root_path)
    observed_subsystems = (
        tuple(sorted(set(subsystems)))
        if subsystems is not None
        else _detect_subsystems(root_path, exclusions)
    )
    nested_git_roots = tuple(root for root in observed_git_roots if root != ".")

    source_file_count = 0
    languages: set[str] = set()
    build_systems: set[str] = set()
    generator_pipelines: set[str] = set()
    contract_repositories: dict[str, set[str]] = {}
    project_reference_signals = 0

    for current, _directory_names, file_names in _walk(root_path, exclusions):
        for name in file_names:
            file_path = current / name
            relative = file_path.relative_to(root_path).as_posix()
            suffix = file_path.suffix.casefold()
            language = LANGUAGE_EXTENSIONS.get(suffix)
            if language:
                source_file_count += 1
                languages.add(language)

            system = _build_system(name, suffix)
            if system:
                build_systems.add(system)

            is_generator = GENERATOR_PATTERN.search(file_path.stem) is not None
            if is_generator:
                generator_pipelines.add(file_path.stem.casefold())

            repository = _repository_for(relative, observed_git_roots)
            normalized = f"/{relative.casefold()}/"
            if not is_generator:
                for contract, pattern in CONTRACT_TOKENS.items():
                    if pattern.search(normalized) or (contract == "protocol" and suffix == ".proto"):
                        contract_repositories.setdefault(contract, set()).add(repository)

            if suffix in {".csproj", ".props", ".targets"}:
                try:
                    if file_path.stat().st_size <= 1024 * 1024:
                        text = file_path.read_text(encoding="utf-8", errors="replace")
                        project_reference_signals += text.casefold().count("<projectreference")
                except OSError:
                    continue

    contract_repo_union = set().union(*contract_repositories.values()) if contract_repositories else set()
    cross_project_contracts = (
        tuple(sorted(contract_repositories)) if len(contract_repo_union) >= 2 else ()
    )
    metrics = ComplexityMetrics(
        nested_git_roots=nested_git_roots,
        root_git="." in observed_git_roots,
        source_file_count=source_file_count,
        language_count=len(languages),
        languages=tuple(sorted(languages)),
        subsystem_count=len(observed_subsystems),
        subsystems=observed_subsystems,
        cross_project_contracts=cross_project_contracts,
        generated_pipelines=tuple(sorted(generator_pipelines)),
        build_systems=tuple(sorted(build_systems)),
        project_reference_signals=project_reference_signals,
    )
    return evaluate_complexity(metrics)
