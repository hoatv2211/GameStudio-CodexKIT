from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import stat
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

try:
    from scripts.common import load_yaml, parse_frontmatter
    from scripts.dogfood_eval import load_profile
    from scripts.promotion_evidence import load_promotion_records, validate_promotion_record
    from scripts.release_preflight import load_release_preflight_schema
    from scripts.sync_skill_resources import load_skill_resources, sync_skill_resources
except ModuleNotFoundError:
    from common import load_yaml, parse_frontmatter
    from dogfood_eval import load_profile
    from promotion_evidence import load_promotion_records, validate_promotion_record
    from release_preflight import load_release_preflight_schema
    from sync_skill_resources import load_skill_resources, sync_skill_resources


TOP_LEVEL_FIELDS = {
    "name",
    "description",
    "version",
    "author",
    "license",
    "compatibility",
    "metadata",
}
COMPATIBILITY_FIELDS = {"engines", "versions", "platforms"}
METADATA_FIELDS = {"studio"}
STUDIO_FIELDS = {
    "type",
    "lifecycle_stage",
    "risk_level",
    "packs",
    "side_effects",
    "artifact",
    "required_evidence",
    "owner",
    "reviewer",
    "maturity",
    "last_reviewed",
    "provenance",
}
PROVENANCE_FIELDS = {"derived_from", "patterns_from", "copied_text"}
DERIVED_FIELDS = {"repo", "path", "commit", "license"}
SKILL_TYPES = {
    "root",
    "component",
    "interactive",
    "workflow",
    "discipline",
    "diagnostic",
    "gate",
    "safety",
    "governance",
    "router",
}
LIFECYCLE_STAGES = {"discover", "define", "plan", "build", "verify", "review", "ship", "operate"}
RISK_LEVELS = {"read-only", "low", "medium", "high"}
SIDE_EFFECTS = {"none", "files", "assets", "database", "network", "external_publish"}
MATURITY_LEVELS = {"draft", "experimental", "beta", "stable", "release", "deprecated", "archived"}
PROMOTED_MATURITY_LEVELS = {"beta", "stable", "release"}
PERMISSIVE_LICENSES = {
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
}
REQUIRED_HEADINGS = (
    "Overview",
    "When to use",
    "When NOT to use",
    "Required inputs and context discovery",
    "Safety and risk level",
    "Workflow",
    "Evidence and output contract",
    "Handoff contract",
    "Pitfalls and anti-rationalization",
    "Verification checklist",
    "References and scripts",
)
PLUGIN_NAME = "game-studio-codex-kit"
MARKETPLACE_NAME = "gamestudio-codex-kit"
PLUGIN_REPOSITORY = "https://github.com/hoatv2211/GameStudio-CodexKIT"
PLUGIN_GIT_URL = f"{PLUGIN_REPOSITORY}.git"


@dataclass(frozen=True)
class Issue:
    code: str
    path: Path
    message: str
    severity: str = "error"

    def render(self, root: Path) -> str:
        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        return f"{self.severity.upper()} {self.code} {display_path}: {self.message}"


FORBIDDEN_PATH_CHARACTERS = set('<>:"|?*')
RESERVED_DEVICE_BASENAMES = {
    "aux",
    "clock$",
    "con",
    "conin$",
    "conout$",
    "nul",
    "prn",
}
RESERVED_NUMBERED_DEVICE = re.compile(r"^(?:com|lpt)(?:[1-9¹²³])$", re.IGNORECASE)

def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _string_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )

def _safe_agent_role_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("agent role path must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in parts)
        or len(parts) < 2
        or parts[0] != "agents"
    ):
        raise ValueError(f"unsafe agent role path: {value}")
    for part in parts:
        device_basename = part.split(".", 1)[0].rstrip(" .").casefold()
        if (
            any(unicodedata.category(character) == "Cc" for character in part)
            or any(character in FORBIDDEN_PATH_CHARACTERS for character in part)
            or part.endswith((".", " "))
            or device_basename in RESERVED_DEVICE_BASENAMES
            or RESERVED_NUMBERED_DEVICE.fullmatch(device_basename)
        ):
            raise ValueError(f"unsafe agent role path component {part!r}: {value}")

    root_path = root.resolve()
    if _is_reparse_point(root_path):
        raise ValueError(f"repository root is a symlink or reparse point: {root_path}")
    candidate = root_path.joinpath(*parts)
    current = root_path
    for part in parts:
        current = current / part
        if _is_reparse_point(current):
            raise ValueError(f"symlink or reparse point is not allowed: {current}")
    resolved = candidate.resolve()
    agents_root = (root_path / "agents").resolve()
    try:
        resolved.relative_to(agents_root)
    except ValueError as error:
        raise ValueError(f"agent role path escapes repository agents/: {value}") from error
    return candidate

def _unknown_fields(data: Any, allowed: set[str]) -> set[str]:
    if not isinstance(data, dict):
        return set()
    return set(data) - allowed


def _issue(issues: list[Issue], code: str, path: Path, message: str, severity: str = "error") -> None:
    issues.append(Issue(code=code, path=path, message=message, severity=severity))


def _validate_mapping_fields(
    issues: list[Issue], path: Path, data: Any, allowed: set[str], label: str
) -> None:
    if not isinstance(data, dict):
        _issue(issues, f"skill.{label}.mapping", path, f"{label} must be a mapping")
        return
    unknown = _unknown_fields(data, allowed)
    if unknown:
        _issue(
            issues,
            "skill.frontmatter.unknown",
            path,
            f"unknown {label} fields: {', '.join(sorted(unknown))}",
        )
    missing = allowed - set(data)
    if missing:
        _issue(
            issues,
            f"skill.{label}.missing",
            path,
            f"missing {label} fields: {', '.join(sorted(missing))}",
        )


def _validate_links(path: Path, body: str, issues: list[Issue]) -> None:
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
        clean_target = target.split("#", 1)[0].strip()
        if not clean_target or re.match(r"^[a-z]+://", clean_target, re.IGNORECASE):
            continue
        if clean_target.startswith("mailto:"):
            continue
        resolved = (path.parent / clean_target).resolve()
        if not resolved.exists():
            _issue(issues, "skill.link.missing", path, f"missing local link target: {clean_target}")


def _validate_skill(path: Path, issues: list[Issue]) -> dict[str, Any] | None:
    try:
        frontmatter, body = parse_frontmatter(path)
    except (OSError, ValueError) as error:
        _issue(issues, "skill.frontmatter.parse", path, str(error))
        return None

    _validate_mapping_fields(issues, path, frontmatter, TOP_LEVEL_FIELDS, "frontmatter")
    compatibility = frontmatter.get("compatibility")
    metadata = frontmatter.get("metadata")
    _validate_mapping_fields(issues, path, compatibility, COMPATIBILITY_FIELDS, "compatibility")
    _validate_mapping_fields(issues, path, metadata, METADATA_FIELDS, "metadata")
    studio = metadata.get("studio") if isinstance(metadata, dict) else None
    _validate_mapping_fields(issues, path, studio, STUDIO_FIELDS, "studio")
    provenance = studio.get("provenance") if isinstance(studio, dict) else None
    _validate_mapping_fields(issues, path, provenance, PROVENANCE_FIELDS, "provenance")

    value_errors: list[str] = []
    if not isinstance(frontmatter.get("version"), str) or not re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", str(frontmatter.get("version", ""))
    ):
        value_errors.append("version must be semantic-version text")
    for field in ("author", "license"):
        if not isinstance(frontmatter.get(field), str) or not frontmatter.get(field):
            value_errors.append(f"{field} must be non-empty text")
    if isinstance(compatibility, dict):
        for field in COMPATIBILITY_FIELDS:
            value = compatibility.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                value_errors.append(f"compatibility.{field} must be a string list")
    if isinstance(studio, dict):
        for field in ("packs", "required_evidence"):
            value = studio.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                value_errors.append(f"studio.{field} must be a string list")
        for field in ("artifact", "owner"):
            if not isinstance(studio.get(field), str) or not studio.get(field):
                value_errors.append(f"studio.{field} must be non-empty text")
        reviewer = studio.get("reviewer")
        if reviewer is not None and (not isinstance(reviewer, str) or not reviewer):
            value_errors.append("studio.reviewer must be null or non-empty text")
        reviewed = studio.get("last_reviewed")
        try:
            if isinstance(reviewed, dt.datetime):
                reviewed = reviewed.date()
            if not isinstance(reviewed, dt.date):
                dt.date.fromisoformat(str(reviewed))
        except ValueError:
            value_errors.append("studio.last_reviewed must be an ISO date")
    for message in value_errors:
        _issue(issues, "skill.frontmatter.value", path, message)

    name = frontmatter.get("name")
    if name != path.parent.name:
        _issue(
            issues,
            "skill.name.folder_mismatch",
            path,
            f"frontmatter name {name!r} must equal folder {path.parent.name!r}",
        )
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.startswith("Use when"):
        _issue(issues, "skill.description.trigger", path, "description must start with 'Use when'")
    if isinstance(description, str) and len(description) > 1024:
        _issue(issues, "skill.description.length", path, "description exceeds 1024 characters")

    if isinstance(studio, dict):
        skill_type = studio.get("type")
        if skill_type not in SKILL_TYPES:
            _issue(issues, "skill.type.invalid", path, f"invalid type: {skill_type!r}")
        if studio.get("lifecycle_stage") not in LIFECYCLE_STAGES:
            _issue(issues, "skill.lifecycle.invalid", path, "invalid lifecycle_stage")
        risk_level = studio.get("risk_level")
        if risk_level not in RISK_LEVELS:
            _issue(issues, "skill.risk.invalid", path, f"invalid risk_level: {risk_level!r}")
        if risk_level in {"medium", "high"} and not studio.get("reviewer"):
            _issue(issues, "skill.risk.reviewer", path, "medium/high risk skills require a reviewer")
        if studio.get("side_effects") not in SIDE_EFFECTS:
            _issue(issues, "skill.side_effects.invalid", path, "invalid side_effects")
        if studio.get("maturity") not in MATURITY_LEVELS:
            _issue(issues, "skill.maturity.invalid", path, "invalid maturity")
        if not isinstance(studio.get("packs"), list):
            _issue(issues, "skill.packs.invalid", path, "packs must be a list")
        if not isinstance(studio.get("required_evidence"), list):
            _issue(issues, "skill.evidence.invalid", path, "required_evidence must be a list")
        if skill_type == "root" and not re.search(r"^## Negative scope\s*$", body, re.MULTILINE):
            _issue(issues, "skill.root.negative_scope", path, "root skill requires a 'Negative scope' section")

    if isinstance(provenance, dict):
        derived = provenance.get("derived_from")
        copied_text = provenance.get("copied_text")
        if derived != "none":
            if not isinstance(derived, dict):
                _issue(issues, "skill.provenance.derived", path, "derived_from must be 'none' or a mapping")
            else:
                missing = DERIVED_FIELDS - set(derived)
                unknown = set(derived) - DERIVED_FIELDS
                if missing:
                    _issue(
                        issues,
                        "skill.provenance.incomplete",
                        path,
                        f"derived_from missing: {', '.join(sorted(missing))}",
                    )
                if unknown:
                    _issue(
                        issues,
                        "skill.provenance.derived_unknown",
                        path,
                        f"derived_from unknown fields: {', '.join(sorted(unknown))}",
                    )
                license_name = str(derived.get("license", ""))
                if license_name not in PERMISSIVE_LICENSES:
                    _issue(
                        issues,
                        "skill.provenance.non_permissive",
                        path,
                        f"derived source license is not permissive: {derived.get('license')!r}",
                    )
        if copied_text != "none" and not isinstance(derived, dict):
            _issue(
                issues,
                "skill.provenance.incomplete",
                path,
                "copied_text requires complete derived_from provenance",
            )

    for heading in REQUIRED_HEADINGS:
        if not re.search(rf"^## {re.escape(heading)}\s*$", body, re.MULTILINE):
            _issue(issues, "skill.body.section", path, f"missing required section: {heading}")
    workflow_match = re.search(r"^## Workflow\s*$\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    if workflow_match:
        workflow = workflow_match.group(1)
        step_matches = list(re.finditer(r"^\d+\.\s+", workflow, re.MULTILINE))
        for index, step in enumerate(step_matches):
            end = step_matches[index + 1].start() if index + 1 < len(step_matches) else len(workflow)
            if "Completion criterion:" not in workflow[step.start():end]:
                _issue(
                    issues,
                    "skill.workflow.completion",
                    path,
                    f"workflow step {index + 1} requires its own completion criterion",
                )
    if len(path.read_text(encoding="utf-8").splitlines()) >= 500:
        _issue(issues, "skill.length.warning", path, "SKILL.md is 500 lines or longer", severity="warning")
    if "PLAN_final.md" in body:
        _issue(
            issues,
            "skill.roadmap.active_reference",
            path,
            "active skill bodies must not depend on the completed roadmap",
        )
    _validate_links(path, body, issues)
    return frontmatter


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            start = visiting.index(node)
            cycle = visiting[start:] + [node]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.append(node)
        for dependency in graph.get(node, []):
            if dependency in graph:
                visit(dependency)
        visiting.pop()
        visited.add(node)

    for node in graph:
        visit(node)
    return cycles


def _load_registry(
    path: Path,
    top_key: str,
    issues: list[Issue],
    *,
    preserve_raw_entries: bool = False,
) -> list[Any]:
    if not path.exists():
        _issue(issues, "registry.file.missing", path, f"missing registry file for {top_key}")
        return []
    try:
        data = load_yaml(path)
    except (OSError, ValueError) as error:
        _issue(issues, "registry.parse", path, str(error))
        return []
    if not isinstance(data, dict) or set(data) != {"schema_version", top_key}:
        _issue(issues, "registry.schema", path, f"expected only schema_version and {top_key}")
        return []
    entries = data.get(top_key)
    if not isinstance(entries, list):
        _issue(issues, "registry.schema", path, f"{top_key} must be a list")
        return []
    if preserve_raw_entries:
        return entries
    return [entry for entry in entries if isinstance(entry, dict)]


def _validate_registries(root: Path, issues: list[Issue]) -> set[str]:
    registry = root / "registry"
    capabilities_path = registry / "capabilities.yaml"
    packs_path = registry / "packs.yaml"
    personas_path = registry / "personas.yaml"
    capabilities = _load_registry(capabilities_path, "capabilities", issues)
    packs = _load_registry(packs_path, "packs", issues)
    personas = _load_registry(personas_path, "personas", issues)

    capability_ids = [str(entry.get("id", "")) for entry in capabilities]
    pack_ids = [str(entry.get("id", "")) for entry in packs]
    persona_ids = [str(entry.get("id", "")) for entry in personas]
    for duplicate in _duplicates(capability_ids):
        _issue(issues, "registry.id.duplicate", capabilities_path, f"duplicate capability id: {duplicate}")
    for duplicate in _duplicates(pack_ids):
        _issue(issues, "registry.id.duplicate", packs_path, f"duplicate pack id: {duplicate}")
    for duplicate in _duplicates(persona_ids):
        _issue(issues, "registry.id.duplicate", personas_path, f"duplicate persona id: {duplicate}")

    capability_set = set(capability_ids)
    pack_set = set(pack_ids)
    capability_graph: dict[str, list[str]] = {}
    pack_graph: dict[str, list[str]] = {}
    for entry in capabilities:
        capability_id = str(entry.get("id", ""))
        expected = {"id", "path", "type", "packs", "risk_level", "maturity", "depends_on"}
        if set(entry) != expected:
            _issue(issues, "registry.schema", capabilities_path, f"invalid fields for capability {capability_id}")
        skill_path = root / str(entry.get("path", ""))
        if not skill_path.exists():
            _issue(issues, "registry.reference.missing", capabilities_path, f"missing skill path: {entry.get('path')}")
        else:
            try:
                skill_frontmatter, _ = parse_frontmatter(skill_path)
            except (OSError, ValueError):
                skill_frontmatter = {}
            skill_studio = (
                skill_frontmatter.get("metadata", {}).get("studio", {})
                if isinstance(skill_frontmatter, dict)
                else {}
            )
            expected_values = {
                "id": skill_frontmatter.get("name"),
                "type": skill_studio.get("type"),
                "packs": skill_studio.get("packs"),
                "risk_level": skill_studio.get("risk_level"),
                "maturity": skill_studio.get("maturity"),
            }
            for field, expected_value in expected_values.items():
                if entry.get(field) != expected_value:
                    _issue(
                        issues,
                        "registry.skill.mismatch",
                        capabilities_path,
                        f"capability {capability_id} {field}={entry.get(field)!r} does not match skill {expected_value!r}",
                    )
        for pack_id in entry.get("packs", []) or []:
            if pack_id not in pack_set:
                _issue(issues, "registry.reference.missing", capabilities_path, f"unknown pack: {pack_id}")
        dependencies = [str(item) for item in (entry.get("depends_on") or [])]
        capability_graph[capability_id] = dependencies
        for dependency in dependencies:
            if dependency not in capability_set:
                _issue(issues, "registry.reference.missing", capabilities_path, f"unknown capability: {dependency}")

    for entry in packs:
        pack_id = str(entry.get("id", ""))
        expected = {"id", "description", "skills", "depends_on"}
        if set(entry) != expected:
            _issue(issues, "registry.schema", packs_path, f"invalid fields for pack {pack_id}")
        for skill_id in entry.get("skills", []) or []:
            if skill_id not in capability_set:
                _issue(issues, "registry.reference.missing", packs_path, f"unknown capability: {skill_id}")
        dependencies = [str(item) for item in (entry.get("depends_on") or [])]
        pack_graph[pack_id] = dependencies
        for dependency in dependencies:
            if dependency not in pack_set:
                _issue(issues, "registry.reference.missing", packs_path, f"unknown pack: {dependency}")

    for entry in personas:
        persona_id = str(entry.get("id", ""))
        expected = {"id", "path", "description", "routes"}
        if set(entry) != expected:
            _issue(issues, "registry.schema", personas_path, f"invalid fields for persona {persona_id}")
        persona_path = root / str(entry.get("path", ""))
        if not persona_path.exists():
            _issue(issues, "registry.reference.missing", personas_path, f"missing persona path: {entry.get('path')}")
        else:
            body = persona_path.read_text(encoding="utf-8")
            if re.search(r"^## Workflow\s*$|Completion criterion:", body, re.MULTILINE):
                _issue(issues, "persona.workflow_body", persona_path, "personas must be lens-only and cannot embed workflows")
        for route in entry.get("routes", []) or []:
            if route not in capability_set:
                _issue(issues, "registry.reference.missing", personas_path, f"unknown persona route: {route}")

    for cycle in _find_cycles(capability_graph):
        _issue(issues, "registry.dependency.cycle", capabilities_path, " -> ".join(cycle))
    for cycle in _find_cycles(pack_graph):
        _issue(issues, "registry.dependency.cycle", packs_path, " -> ".join(cycle))
    if "release-candidate-preflight" in capability_set:
        schema_path = root / "evals" / "schema" / "release-preflight.schema.json"
        try:
            load_release_preflight_schema(schema_path)
        except (OSError, ValueError) as error:
            _issue(issues, "eval.release_preflight.schema", schema_path, str(error))
    _validate_promotion_evidence(root, capabilities, issues)
    return capability_set


def _validate_promotion_evidence(
    root: Path,
    capabilities: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    promotion_path = root / "registry" / "promotion-evidence.yaml"
    promoted = {
        str(entry.get("id", "")): str(entry.get("maturity", ""))
        for entry in capabilities
        if entry.get("maturity") in PROMOTED_MATURITY_LEVELS
    }
    if not promotion_path.is_file():
        for skill_id, maturity in sorted(promoted.items()):
            _issue(
                issues,
                "registry.promotion.missing",
                promotion_path,
                f"capability {skill_id} at {maturity} requires promotion evidence",
            )
        return

    try:
        records = load_promotion_records(promotion_path)
    except (OSError, ValueError) as error:
        _issue(issues, "registry.promotion.invalid", promotion_path, str(error))
        records = []

    profile_cases: dict[str, set[str]] = {}
    profiles_root = root / "evals" / "dogfood" / "profiles"
    for profile_path in sorted(profiles_root.glob("*.json")):
        try:
            profile = load_profile(root, profile_path.stem)
        except (OSError, ValueError) as error:
            _issue(
                issues,
                "registry.promotion.invalid",
                profile_path,
                f"promotion profile cannot be loaded: {error}",
            )
            continue
        profile_cases[profile_path.stem] = set(profile["case_ids"])

    known_skills = {
        str(entry.get("id", ""))
        for entry in capabilities
        if isinstance(entry.get("id"), str) and entry.get("id")
    }
    valid_targets: set[tuple[str, str]] = set()
    record_ids: list[str] = []
    for index, record in enumerate(records):
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id.strip():
            record_ids.append(record_id)
        else:
            _issue(
                issues,
                "registry.promotion.invalid",
                promotion_path,
                f"promotion record {index} requires a non-empty id",
            )
        errors = validate_promotion_record(
            record,
            known_skills=known_skills,
            known_profiles=profile_cases,
            profile_cases=profile_cases,
            artifact_root=root,
            repository_root=root,
        )
        for message in errors:
            _issue(
                issues,
                "registry.promotion.invalid",
                promotion_path,
                f"promotion record {record_id or index}: {message}",
            )
        if not errors:
            valid_targets.add((str(record.get("skill_id")), str(record.get("target_maturity"))))

    for duplicate in _duplicates(record_ids):
        _issue(
            issues,
            "registry.promotion.invalid",
            promotion_path,
            f"duplicate promotion record id: {duplicate}",
        )
    for skill_id, maturity in sorted(promoted.items()):
        if (skill_id, maturity) not in valid_targets:
            _issue(
                issues,
                "registry.promotion.missing",
                promotion_path,
                f"capability {skill_id} at {maturity} requires a valid matching promotion record",
            )


def _load_json_object(path: Path, issues: list[Issue], code_prefix: str) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _issue(issues, f"{code_prefix}.parse", path, str(error))
        return None
    if not isinstance(data, dict):
        _issue(issues, f"{code_prefix}.schema", path, "expected a JSON object")
        return None
    return data


def _validate_plugin_package(root: Path, capability_ids: set[str], issues: list[Issue]) -> None:
    manifest_path = root / ".codex-plugin" / "plugin.json"
    marketplace_path = root / ".claude-plugin" / "marketplace.json"

    if not manifest_path.is_file():
        _issue(issues, "plugin.manifest.missing", manifest_path, "missing root Codex plugin manifest")
        manifest = None
    else:
        manifest = _load_json_object(manifest_path, issues, "plugin.manifest")

    if not marketplace_path.is_file():
        _issue(
            issues,
            "plugin.marketplace.missing",
            marketplace_path,
            "missing repository marketplace metadata",
        )
        marketplace = None
    else:
        marketplace = _load_json_object(marketplace_path, issues, "plugin.marketplace")

    if manifest is not None:
        if manifest.get("name") != PLUGIN_NAME:
            _issue(issues, "plugin.manifest.value", manifest_path, f"name must be {PLUGIN_NAME!r}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
            _issue(issues, "plugin.manifest.value", manifest_path, "version must use strict semantic versioning")
        if manifest.get("repository") != PLUGIN_REPOSITORY:
            _issue(
                issues,
                "plugin.manifest.value",
                manifest_path,
                f"repository must be {PLUGIN_REPOSITORY!r}",
            )
        if manifest.get("skills") != "./skills/":
            _issue(issues, "plugin.manifest.value", manifest_path, "skills must point to './skills/'")
        skills_root = root / str(manifest.get("skills", ""))
        packaged_ids = {
            directory.name
            for directory in skills_root.iterdir()
            if directory.is_dir() and (directory / "SKILL.md").is_file()
        } if skills_root.is_dir() else set()
        if packaged_ids != capability_ids:
            missing = sorted(capability_ids - packaged_ids)
            extra = sorted(packaged_ids - capability_ids)
            _issue(
                issues,
                "plugin.skills.catalog_mismatch",
                manifest_path,
                f"missing={missing}, extra={extra}",
            )

    if marketplace is not None:
        if marketplace.get("name") != MARKETPLACE_NAME:
            _issue(
                issues,
                "plugin.marketplace.value",
                marketplace_path,
                f"name must be {MARKETPLACE_NAME!r}",
            )
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
            _issue(
                issues,
                "plugin.marketplace.schema",
                marketplace_path,
                "marketplace must contain exactly one plugin entry",
            )
            return
        entry = plugins[0]
        expected_source = {"source": "url", "url": PLUGIN_GIT_URL, "ref": "main"}
        expected_policy = {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
        if entry.get("name") != PLUGIN_NAME:
            _issue(issues, "plugin.marketplace.entry", marketplace_path, "plugin name does not match manifest")
        if entry.get("source") != expected_source:
            _issue(issues, "plugin.marketplace.entry", marketplace_path, "plugin source must target the GitHub root")
        if entry.get("policy") != expected_policy:
            _issue(issues, "plugin.marketplace.entry", marketplace_path, "plugin policy must be explicit")
        if entry.get("category") != "Productivity":
            _issue(issues, "plugin.marketplace.entry", marketplace_path, "category must be 'Productivity'")


def _validate_agent_roles(
    root: Path,
    issues: list[Issue],
    capability_ids: set[str] | None = None,
) -> None:
    registry_path = root / "registry" / "agent-roles.yaml"
    entries = _load_registry(
        registry_path,
        "agent_roles",
        issues,
        preserve_raw_entries=True,
    )
    role_ids = [
        str(entry.get("id", ""))
        for entry in entries
        if isinstance(entry, dict)
    ]
    for duplicate in _duplicates(role_ids):
        _issue(
            issues,
            "registry.agent_role.duplicate",
            registry_path,
            f"duplicate agent role id: {duplicate}",
        )
    base_fields = {
        "id",
        "path",
        "description",
        "sandbox_mode",
        "reasoning_effort",
    }
    specialist_fields = {
        "kind",
        "discipline",
        "required_skills",
        "owned_scope_patterns",
        "read_scope_patterns",
        "forbidden_actions",
        "validation_commands",
        "concurrency_group",
    }
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _issue(
                issues,
                "registry.agent_role.schema",
                registry_path,
                f"agent_roles[{index}] must be a mapping",
            )
            continue
        role_id = str(entry.get("id", ""))
        kind = entry.get("kind")
        expected_fields = base_fields | specialist_fields if kind == "specialist" else base_fields
        if set(entry) != expected_fields:
            _issue(
                issues,
                "registry.agent_role.schema",
                registry_path,
                f"agent role {role_id or '<missing>'} must contain {sorted(expected_fields)}",
            )
            continue
        if kind not in {None, "generic", "specialist"}:
            _issue(
                issues,
                "registry.agent_role.value",
                registry_path,
                f"invalid agent role kind for {role_id}: {kind}",
            )
        if kind == "specialist":
            for field in (
                "discipline",
                "concurrency_group",
            ):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    _issue(
                        issues,
                        "registry.agent_role.value",
                        registry_path,
                        f"specialist {role_id} requires non-empty {field}",
                    )
            for field in (
                "required_skills",
                "owned_scope_patterns",
                "read_scope_patterns",
                "forbidden_actions",
                "validation_commands",
            ):
                if not _string_list(entry.get(field)):
                    _issue(
                        issues,
                        "registry.agent_role.value",
                        registry_path,
                        f"specialist {role_id} requires a non-empty string list for {field}",
                    )
            if capability_ids is not None:
                for skill_id in entry.get("required_skills", []) or []:
                    if skill_id not in capability_ids:
                        _issue(
                            issues,
                            "registry.agent_role.reference",
                            registry_path,
                            f"unknown required skill for {role_id}: {skill_id}",
                        )
        relative = str(entry.get("path", ""))
        if (
            not role_id
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", role_id)
            or not relative.startswith("agents/")
            or not relative.endswith(".toml")
        ):
            _issue(
                issues,
                "registry.agent_role.schema",
                registry_path,
                f"invalid agent role id or path: {role_id} -> {relative}",
            )
            continue
        try:
            template_path = _safe_agent_role_path(root, relative)
        except ValueError as error:
            _issue(issues, "registry.agent_role.path", registry_path, str(error))
            continue
        if not template_path.is_file():
            _issue(
                issues,
                "registry.agent_role.path",
                template_path,
                f"missing agent role template for {role_id}",
            )
            continue
        if entry.get("sandbox_mode") not in {"read-only", "workspace-write"}:
            _issue(
                issues,
                "registry.agent_role.value",
                registry_path,
                f"invalid sandbox mode for {role_id}",
            )
        if entry.get("reasoning_effort") not in {"low", "medium", "high", "xhigh"}:
            _issue(
                issues,
                "registry.agent_role.value",
                registry_path,
                f"invalid reasoning effort for {role_id}",
            )
        try:
            template = tomllib.loads(template_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            _issue(issues, "registry.agent_role.toml", template_path, str(error))
            continue
        if template.get("name") != role_id:
            _issue(
                issues,
                "registry.agent_role.value",
                template_path,
                f"template name must be {role_id}",
            )
        if template.get("sandbox_mode") != entry.get("sandbox_mode"):
            _issue(
                issues,
                "registry.agent_role.value",
                template_path,
                f"template sandbox mode does not match registry for {role_id}",
            )
        if template.get("model_reasoning_effort") != entry.get("reasoning_effort"):
            _issue(
                issues,
                "registry.agent_role.value",
                template_path,
                f"template reasoning effort does not match registry for {role_id}",
            )
        if not isinstance(template.get("developer_instructions"), str) or not template["developer_instructions"].strip():
            _issue(
                issues,
                "registry.agent_role.value",
                template_path,
                f"template developer instructions are required for {role_id}",
            )
        if kind == "specialist":
            for field in (
                "discipline",
                "required_skills",
                "owned_scope_patterns",
                "read_scope_patterns",
                "forbidden_actions",
                "validation_commands",
                "concurrency_group",
            ):
                if template.get(field) != entry.get(field):
                    _issue(
                        issues,
                        "registry.agent_role.value",
                        template_path,
                        f"template {field} does not match registry for {role_id}",
                    )


def _validate_skill_resources(root: Path, issues: list[Issue]) -> None:
    registry_path = root / "registry" / "skill-resources.yaml"
    if not registry_path.is_file():
        _issue(
            issues,
            "skill.resources.registry_missing",
            registry_path,
            "missing standalone skill resource registry",
        )
        return
    try:
        bundled, _repository_only = load_skill_resources(root)
        drift = sync_skill_resources(root, check=True)
    except (OSError, ValueError) as error:
        _issue(issues, "skill.resources.registry_invalid", registry_path, str(error))
        return
    for path in drift:
        _issue(
            issues,
            "skill.resources.drift",
            path,
            "generated skill helper is missing, stale, or unexpected",
        )
    for resource in bundled:
        template_path = resource.destination
        if template_path.suffix.casefold() != ".toml" or not template_path.is_file():
            continue
        relative = template_path.relative_to(root / "skills" / resource.skill_id)
        is_agent_template = (
            len(relative.parts) == 3
            and relative.parts[:2] == ("templates", "agents")
        )
        if not is_agent_template:
            continue
        try:
            template = tomllib.loads(template_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            _issue(issues, "skill.resources.toml_parse", template_path, str(error))
            continue
        if template.get("name") != template_path.stem:
            _issue(
                issues,
                "skill.resources.toml_name",
                template_path,
                f"packaged template name must be {template_path.stem}",
            )
        for field in ("name", "description", "developer_instructions"):
            value = template.get(field)
            if not isinstance(value, str) or not value.strip():
                _issue(
                    issues,
                    "skill.resources.toml_required",
                    template_path,
                    f"packaged agent template requires non-empty {field}",
                )


def validate_repository(root: Path | str) -> list[Issue]:
    root_path = Path(root).resolve()
    issues: list[Issue] = []
    roadmap = root_path / "PLAN_final.md"
    if roadmap.exists():
        _issue(
            issues,
            "template.roadmap.active",
            roadmap,
            "completed roadmaps must leave the distributable root; keep them only in ignored local .archive if needed",
        )
    for name in ("README.md", "AGENTS.md"):
        path = root_path / name
        if path.exists() and "PLAN_final.md" in path.read_text(encoding="utf-8"):
            _issue(
                issues,
                "template.roadmap.active_reference",
                path,
                "active entry documentation must not depend on the completed roadmap",
            )
    for skill_path in sorted((root_path / "skills").glob("*/SKILL.md")):
        _validate_skill(skill_path, issues)
    capability_ids = _validate_registries(root_path, issues)
    _validate_agent_roles(root_path, issues, capability_ids)
    _validate_skill_resources(root_path, issues)
    _validate_plugin_package(root_path, capability_ids, issues)
    return sorted(issues, key=lambda issue: (str(issue.path), issue.code, issue.message))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate GameStudio-CodexKIT structure and provenance.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    issues = validate_repository(root)
    for issue in issues:
        print(issue.render(root))
    errors = [issue for issue in issues if issue.severity == "error"]
    print(f"validate: {len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
