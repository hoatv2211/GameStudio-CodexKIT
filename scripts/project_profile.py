from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

import yaml

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

PROFILE_TOP_LEVEL_FIELDS = {
    "schema_version",
    "workspace",
    "repositories",
    "exclusions",
    "agents",
    "cross_project_contracts",
}
WORKSPACE_FIELDS = {"name", "root_git", "default_concurrency"}
REPOSITORY_FIELDS = {
    "id",
    "path",
    "git_root",
    "subsystems",
    "owner_skill",
    "validation",
}
VALIDATION_FIELDS = {"name", "command", "risk"}
SPECIALIST_FIELDS = {
    "id",
    "repository",
    "reasoning_effort",
    "constraints",
    "owned_scope_patterns",
    "read_scope_patterns",
}
CONTRACT_FIELDS = {"id", "repositories", "authority"}
RISK_LEVELS = {"read-only", "low", "medium", "high"}
REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_SPECIALIST_IDS = {
    "default",
    "worker",
    "explorer",
    "investigator",
    "implementer",
    "verifier",
}
RESERVED_WINDOWS_BASENAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "conin$",
    "conout$",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
WINDOWS_SUPERSCRIPT_DEVICE_DIGITS = {"¹", "²", "³"}
WINDOWS_FORBIDDEN_PATH_CHARACTERS = set('<>:"|?*')


def _reserved_windows_segment(segment: str) -> bool:
    basename = segment.split(".", 1)[0].casefold()
    if basename in RESERVED_WINDOWS_BASENAMES:
        return True
    if (
        basename[:3] in {"com", "lpt"}
        and basename[3:] in WINDOWS_SUPERSCRIPT_DEVICE_DIGITS
    ):
        return True
    is_reserved = getattr(PureWindowsPath(segment), "is_reserved", None)
    return bool(is_reserved and is_reserved())


def _safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    pure = PurePosixPath(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if not (
        not pure.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
        and ".." not in pure.parts
    ):
        return False
    for segment in value.replace("\\", "/").split("/"):
        if segment == ".":
            continue
        if segment.endswith((".", " ")):
            return False
        if any(character in WINDOWS_FORBIDDEN_PATH_CHARACTERS for character in segment):
            return False
        if any(unicodedata.category(character) == "Cc" for character in segment):
            return False
        if _reserved_windows_segment(segment):
            return False
    return True


def _normalized_repository_path(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix()


def _valid_id(value: str) -> bool:
    return ID_PATTERN.fullmatch(value) is not None


def _unknown_fields(value: object, allowed: set[str]) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(str(field) for field in value if field not in allowed)


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _safe_scope_pattern(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if pure.is_absolute() or windows.is_absolute() or windows.drive or ".." in pure.parts:
        return False
    return not any(unicodedata.category(character) == "Cc" for character in value)


def _scope_prefix(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    wildcard = min(
        (index for index in (normalized.find("*"), normalized.find("?"), normalized.find("[")) if index >= 0),
        default=len(normalized),
    )
    return normalized[:wildcard].rstrip("/").casefold()


def validate_project_profile(
    profile: object,
    *,
    known_skills: Iterable[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    validate_known_skills = known_skills is not None
    known = set(known_skills or [])
    if not isinstance(profile, dict):
        return ["project profile must be a mapping"]
    unknown_top = _unknown_fields(profile, PROFILE_TOP_LEVEL_FIELDS)
    if unknown_top:
        errors.append(f"unknown project profile fields: {', '.join(unknown_top)}")
    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    workspace = profile.get("workspace")
    if not isinstance(workspace, dict):
        errors.append("workspace must be a mapping")
    else:
        unknown_workspace = _unknown_fields(workspace, WORKSPACE_FIELDS)
        if unknown_workspace:
            errors.append(f"unknown workspace fields: {', '.join(unknown_workspace)}")
        if not isinstance(workspace.get("name"), str) or not str(workspace.get("name", "")).strip():
            errors.append("workspace name is required")
        if not isinstance(workspace.get("root_git"), bool):
            errors.append("workspace root_git must be boolean")
        concurrency = workspace.get("default_concurrency")
        if not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency < 0 or concurrency > 3:
            errors.append("workspace default_concurrency must be an integer from 0 to 3")

    repositories = profile.get("repositories")
    repository_ids: list[str] = []
    repository_paths: set[str] = set()
    if not isinstance(repositories, list) or not repositories:
        errors.append("repositories must be a non-empty list")
        repositories = []
    for index, repository in enumerate(repositories):
        if not isinstance(repository, dict):
            errors.append(f"repository {index} must be a mapping")
            continue
        unknown_repository = _unknown_fields(repository, REPOSITORY_FIELDS)
        if unknown_repository:
            errors.append(
                f"unknown repository fields for {index}: {', '.join(unknown_repository)}"
            )
        repository_id = repository.get("id")
        if not isinstance(repository_id, str) or not repository_id.strip():
            errors.append(f"repository {index} id is required")
            continue
        if not _valid_id(repository_id):
            errors.append(f"invalid repository id: {repository_id}")
        repository_ids.append(repository_id)
        path_value = repository.get("path")
        if not _safe_relative_path(path_value):
            errors.append(f"unsafe repository path: {path_value}")
        else:
            normalized_path = _normalized_repository_path(path_value)
            comparison_path = normalized_path.casefold()
            if comparison_path in repository_paths:
                errors.append(f"duplicate repository path: {normalized_path}")
            repository_paths.add(comparison_path)
        if not isinstance(repository.get("git_root"), bool):
            errors.append(f"repository {repository_id} git_root must be boolean")
        if not _string_list(repository.get("subsystems")):
            errors.append(f"repository {repository_id} subsystems must be a string list")
        owner_skill = repository.get("owner_skill")
        if not isinstance(owner_skill, str) or not owner_skill.strip():
            errors.append(f"repository {repository_id} owner_skill is required")
        elif validate_known_skills and owner_skill not in known:
            errors.append(f"unknown owner skill for {repository_id}: {owner_skill}")
        validations = repository.get("validation", [])
        if not isinstance(validations, list):
            errors.append(f"repository {repository_id} validation must be a list")
            continue
        validation_names: set[str] = set()
        for validation_index, validation in enumerate(validations):
            if not isinstance(validation, dict):
                errors.append(
                    f"validation {validation_index} for {repository_id} must be a mapping"
                )
                continue
            unknown_validation = _unknown_fields(validation, VALIDATION_FIELDS)
            if unknown_validation:
                errors.append(
                    f"unknown validation fields for {repository_id}: {', '.join(unknown_validation)}"
                )
            validation_name = validation.get("name")
            if not isinstance(validation_name, str) or not validation_name.strip():
                errors.append(f"validation name is required for {repository_id}")
            else:
                validation_name_key = validation_name.strip().casefold()
                if validation_name_key in validation_names:
                    errors.append(
                        f"duplicate validation name for {repository_id}: {validation_name}"
                    )
                validation_names.add(validation_name_key)
            if not isinstance(validation.get("command"), str) or not validation["command"].strip():
                errors.append(f"validation command is required for {repository_id}")
            if validation.get("risk") not in RISK_LEVELS:
                errors.append(f"invalid validation risk for {repository_id}: {validation.get('risk')}")

    seen_repositories: set[str] = set()
    for repository_id in repository_ids:
        if repository_id in seen_repositories:
            errors.append(f"duplicate repository id: {repository_id}")
        seen_repositories.add(repository_id)

    exclusions = profile.get("exclusions", [])
    if not _string_list(exclusions):
        errors.append("exclusions must be a string list")

    agents = profile.get("agents", {"specialists": []})
    specialists: list[object] = []
    if not isinstance(agents, dict) or set(agents) - {"specialists"}:
        errors.append("agents must contain only specialists")
    else:
        specialists_value = agents.get("specialists", [])
        if not isinstance(specialists_value, list):
            errors.append("agents specialists must be a list")
        else:
            specialists = specialists_value
    specialist_ids: set[str] = set()
    specialist_writer_scopes: list[tuple[str, str, list[str]]] = []
    for index, specialist in enumerate(specialists):
        if not isinstance(specialist, dict):
            errors.append(f"specialist {index} must be a mapping")
            continue
        unknown_specialist = _unknown_fields(specialist, SPECIALIST_FIELDS)
        if unknown_specialist:
            errors.append(f"unknown specialist fields: {', '.join(unknown_specialist)}")
        specialist_id = specialist.get("id")
        if not isinstance(specialist_id, str) or not specialist_id.strip():
            errors.append(f"specialist {index} id is required")
            continue
        if not _valid_id(specialist_id):
            errors.append(f"invalid specialist id: {specialist_id}")
        if specialist_id.casefold() in RESERVED_SPECIALIST_IDS:
            errors.append(f"reserved specialist id: {specialist_id}")
        if specialist_id in specialist_ids:
            errors.append(f"duplicate specialist id: {specialist_id}")
        specialist_ids.add(specialist_id)
        repository_id = specialist.get("repository")
        if repository_id not in seen_repositories:
            errors.append(
                f"unknown specialist repository for {specialist_id}: {repository_id}"
            )
        if specialist.get("reasoning_effort") not in REASONING_EFFORTS:
            errors.append(
                f"invalid specialist reasoning effort for {specialist_id}: "
                f"{specialist.get('reasoning_effort')}"
            )
        if not _string_list(specialist.get("constraints")):
            errors.append(f"specialist constraints must be a string list: {specialist_id}")
        owned_scopes = specialist.get("owned_scope_patterns")
        read_scopes = specialist.get("read_scope_patterns")
        if (owned_scopes is None) != (read_scopes is None):
            errors.append(
                f"specialist scope metadata requires owned and read patterns: {specialist_id}"
            )
        if owned_scopes is not None:
            if not _string_list(owned_scopes) or not all(
                _safe_scope_pattern(scope) for scope in owned_scopes
            ):
                errors.append(f"invalid specialist owned scopes: {specialist_id}")
            if not _string_list(read_scopes) or not all(
                _safe_scope_pattern(scope) for scope in read_scopes
            ):
                errors.append(f"invalid specialist read scopes: {specialist_id}")
            if isinstance(repository_id, str) and _string_list(owned_scopes):
                specialist_writer_scopes.append(
                    (specialist_id, repository_id, [_scope_prefix(scope) for scope in owned_scopes])
                )

    for index, (left_id, left_repository, left_scopes) in enumerate(specialist_writer_scopes):
        for right_id, right_repository, right_scopes in specialist_writer_scopes[index + 1 :]:
            if left_repository != right_repository:
                continue
            if any(
                left and right and (
                    left == right
                    or left.startswith(right + "/")
                    or right.startswith(left + "/")
                )
                for left in left_scopes
                for right in right_scopes
            ):
                errors.append(
                    f"overlapping active specialist writer scopes: {left_id} and {right_id}"
                )

    contracts = profile.get("cross_project_contracts", [])
    if not isinstance(contracts, list):
        errors.append("cross_project_contracts must be a list")
        contracts = []
    contract_ids: set[str] = set()
    for index, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            errors.append(f"cross-project contract {index} must be a mapping")
            continue
        unknown_contract = _unknown_fields(contract, CONTRACT_FIELDS)
        if unknown_contract:
            errors.append(f"unknown cross-project contract fields: {', '.join(unknown_contract)}")
        contract_id = contract.get("id")
        if not isinstance(contract_id, str) or not contract_id.strip():
            errors.append(f"cross-project contract {index} id is required")
            continue
        if not _valid_id(contract_id):
            errors.append(f"invalid contract id: {contract_id}")
        if contract_id in contract_ids:
            errors.append(f"duplicate cross-project contract id: {contract_id}")
        contract_ids.add(contract_id)
        contract_repositories = contract.get("repositories")
        participant_ids: set[str] = set()
        if not _string_list(contract_repositories):
            errors.append(f"cross-project contract repositories are invalid: {contract_id}")
        else:
            for repository_id in contract_repositories:
                if repository_id in participant_ids:
                    errors.append(
                        f"duplicate contract repository for {contract_id}: {repository_id}"
                    )
                participant_ids.add(repository_id)
                if repository_id not in seen_repositories:
                    errors.append(
                        f"unknown contract repository for {contract_id}: {repository_id}"
                    )
            if len(participant_ids) < 2:
                errors.append(f"cross-project contract repositories are invalid: {contract_id}")
        authority = contract.get("authority")
        if authority not in seen_repositories:
            errors.append(
                f"unknown contract authority for {contract_id}: {authority}"
            )
        elif _string_list(contract_repositories) and authority not in participant_ids:
            errors.append(
                f"contract authority must participate in {contract_id}: {authority}"
            )
    return errors


def load_project_profile(
    path: Path | str,
    *,
    known_skills: Iterable[str] | None = None,
) -> dict[str, Any]:
    profile_path = Path(path)
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    errors = validate_project_profile(profile, known_skills=known_skills)
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def render_workspace_map(profile: dict[str, Any]) -> str:
    lines = [
        "# Workspace Map",
        "",
        "| Repository | Path | Subsystems | Owner skill | Git root |",
        "|---|---|---|---|---|",
    ]
    for repository in profile["repositories"]:
        subsystems = ", ".join(repository["subsystems"])
        git_root = "yes" if repository["git_root"] else "no"
        lines.append(
            f"| {repository['id']} | `{repository['path']}` | {subsystems} | "
            f"`{repository['owner_skill']}` | {git_root} |"
        )
    return "\n".join(lines) + "\n"


def render_validation_matrix(profile: dict[str, Any]) -> str:
    lines = [
        "# Validation Matrix",
        "",
        "| Repository | Validation | Command | Risk |",
        "|---|---|---|---|",
    ]
    for repository in profile["repositories"]:
        for validation in repository.get("validation", []):
            lines.append(
                f"| {repository['id']} | {validation['name']} | "
                f"`{validation['command']}` | {validation['risk']} |"
            )
    return "\n".join(lines) + "\n"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and render a game-studio project profile.")
    parser.add_argument("profile")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--workspace-map", action="store_true")
    output.add_argument("--validation-matrix", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = load_project_profile(Path(args.profile))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(json.dumps({"status": "FAIL", "errors": [str(error)]}, indent=2))
        return 1
    if args.workspace_map:
        print(render_workspace_map(profile), end="")
    elif args.validation_matrix:
        print(render_validation_matrix(profile), end="")
    else:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "workspace": profile["workspace"]["name"],
                    "repositories": len(profile["repositories"]),
                    "specialists": len(profile.get("agents", {}).get("specialists", [])),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
