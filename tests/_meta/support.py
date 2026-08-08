from __future__ import annotations

import json
import shutil
import stat
import uuid
from pathlib import Path

import yaml


TEST_TEMP_ROOT = Path(__file__).resolve().parents[2]


class WorkspaceTemporaryDirectory:
    def __init__(self) -> None:
        self.name = str(TEST_TEMP_ROOT / f".tmp-test-{uuid.uuid4().hex}")
        Path(self.name).mkdir()

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *_args: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        path = Path(self.name)
        if path.exists():
            def remove_readonly(function: object, target: str, _error: object) -> None:
                Path(target).chmod(stat.S_IWRITE)
                function(target)

            shutil.rmtree(path, onerror=remove_readonly)


def temporary_directory() -> WorkspaceTemporaryDirectory:
    return WorkspaceTemporaryDirectory()


REQUIRED_BODY = """# Example Skill

## Overview
Keep the workflow evidence-first.

## When to use
Use this for the fixture.

## When NOT to use
Do not use it outside the fixture.

## Required inputs and context discovery
Collect the repository path and task scope.

## Safety and risk level
This fixture is read-only.

## Workflow
1. Inspect the fixture.
   Completion criterion: the fixture is understood.

## Evidence and output contract
Return a report with paths.

## Handoff contract
Record verified, snapshot, unverified, and blocked facts.

## Pitfalls and anti-rationalization
Do not invent evidence.

## Verification checklist
- [ ] The fixture was inspected.

## References and scripts
Load [the reference](references/example.md) only when needed.
"""


def skill_document(
    name: str,
    *,
    description: str | None = None,
    skill_type: str = "workflow",
    risk_level: str = "read-only",
    reviewer: str | None = None,
    derived_from: object = "none",
    copied_text: str = "none",
    extra_top_level: str = "",
    body: str = REQUIRED_BODY,
) -> str:
    frontmatter = {
        "name": name,
        "description": description or f"Use when exercising the unique {name} fixture workflow.",
        "version": "0.1.0",
        "author": "GameStudio-CodexKIT",
        "license": "MIT",
        "compatibility": {
            "engines": ["engine-agnostic"],
            "versions": ["any"],
            "platforms": ["windows"],
        },
        "metadata": {
            "studio": {
                "type": skill_type,
                "lifecycle_stage": "verify",
                "risk_level": risk_level,
                "packs": ["studio-core"],
                "side_effects": "none",
                "artifact": "report.md",
                "required_evidence": ["file-list"],
                "owner": "Fixture Studio",
                "reviewer": reviewer,
                "maturity": "draft",
                "last_reviewed": "2026-08-07",
                "provenance": {
                    "derived_from": derived_from,
                    "patterns_from": ["test fixture"],
                    "copied_text": copied_text,
                },
            }
        },
    }
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False).rstrip()
    if extra_top_level:
        yaml_text += f"\n{extra_top_level.rstrip()}"
    return f"---\n{yaml_text}\n---\n{body}"


def write_skill(root: Path, name: str, **kwargs: object) -> Path:
    skill_dir = root / "skills" / name
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references" / "example.md").write_text("fixture\n", encoding="utf-8")
    path = skill_dir / "SKILL.md"
    path.write_text(skill_document(name, **kwargs), encoding="utf-8")
    return path


def write_registries(root: Path, skill_names: list[str]) -> None:
    registry = root / "registry"
    registry.mkdir(parents=True, exist_ok=True)
    capabilities = {
        "schema_version": 1,
        "capabilities": [
            {
                "id": name,
                "path": f"skills/{name}/SKILL.md",
                "type": "workflow",
                "packs": ["studio-core"],
                "risk_level": "read-only",
                "maturity": "draft",
                "depends_on": [],
            }
            for name in skill_names
        ],
    }
    packs = {
        "schema_version": 1,
        "packs": [
            {
                "id": "studio-core",
                "description": "Fixture pack",
                "skills": skill_names,
                "depends_on": [],
            }
        ],
    }
    personas = {"schema_version": 1, "personas": []}
    (registry / "capabilities.yaml").write_text(
        yaml.safe_dump(capabilities, sort_keys=False), encoding="utf-8"
    )
    (registry / "packs.yaml").write_text(
        yaml.safe_dump(packs, sort_keys=False), encoding="utf-8"
    )
    (registry / "personas.yaml").write_text(
        yaml.safe_dump(personas, sort_keys=False), encoding="utf-8"
    )
    (registry / "skill-resources.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "bundled": {},
                "repository_only": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def write_plugin_package(root: Path) -> None:
    manifest_path = root / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "name": "game-studio-codex-kit",
                "version": "1.0.0",
                "description": "Fixture plugin",
                "author": {"name": "Fixture"},
                "repository": "https://github.com/hoatv2211/GameStudio-CodexKIT",
                "license": "MIT",
                "skills": "./skills/",
                "interface": {
                    "displayName": "GameStudio Codex Kit",
                    "developerName": "Fixture",
                    "category": "Productivity",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    marketplace_path = root / ".claude-plugin" / "marketplace.json"
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_path.write_text(
        json.dumps(
            {
                "name": "gamestudio-codex-kit",
                "plugins": [
                    {
                        "name": "game-studio-codex-kit",
                        "source": {
                            "source": "url",
                            "url": "https://github.com/hoatv2211/GameStudio-CodexKIT.git",
                            "ref": "main",
                        },
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Productivity",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_routing_file(root: Path, target_skill: str, cases: list[dict[str, str]]) -> Path:
    eval_dir = root / "evals" / "routing"
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / f"{target_skill}.json"
    path.write_text(
        json.dumps({"target_skill": target_skill, "cases": cases}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
