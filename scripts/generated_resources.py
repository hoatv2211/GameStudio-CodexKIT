from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection


@dataclass(frozen=True)
class CapturedSource:
    path: Path
    data: bytes


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError(f"duplicate JSON key: {key}")
        parsed[key] = value
    return parsed


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _parse_json_object(text: str, path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON resource: {path}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON resource must be a JSON object: {path}")
    return parsed


def _generated_skill(text: str, marker: str) -> str:
    opening = re.match(r"\A---\s*\r?\n", text)
    if opening is None:
        raise ValueError("SKILL.md must start with YAML frontmatter")
    return f"---\n# {marker}\n{text[opening.end():]}"


def _generated_json(
    text: str,
    path: Path,
    marker: str,
    accepted_json_comments: Collection[str],
) -> str:
    parsed = _parse_json_object(text, path)
    existing_comment = parsed.get("$comment")
    if "$comment" in parsed and existing_comment not in {
        marker,
        *accepted_json_comments,
    }:
        raise ValueError(f"incompatible JSON $comment in resource: {path}")
    generated = {"$comment": marker}
    generated.update(
        (key, value) for key, value in parsed.items() if key != "$comment"
    )
    return json.dumps(generated, indent=2) + "\n"


def render_generated_resource(
    source: Path | CapturedSource,
    *,
    marker: str,
    accepted_json_comments: Collection[str] = (),
) -> str:
    path = source.path if isinstance(source, CapturedSource) else source
    data = source.data if isinstance(source, CapturedSource) else path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"binary or non-UTF-8 resource: {path}") from error
    if "\x00" in text:
        raise ValueError(f"binary or non-UTF-8 resource: {path}")
    if path.name == "SKILL.md":
        return _generated_skill(text, marker)
    if path.suffix.casefold() == ".json":
        return _generated_json(text, path, marker, accepted_json_comments)
    if path.suffix.casefold() in {".py", ".sh", ".ps1", ".yaml", ".yml", ".toml"}:
        return f"# {marker}\n\n{text}"
    if path.suffix.casefold() in {".md", ".txt"}:
        return f"<!-- {marker} -->\n{text}"
    if path.suffix.casefold() == ".html":
        return f"<!-- {marker} -->\n\n{text}"
    if path.suffix.casefold() == ".css":
        return f"/* {marker} */\n\n{text}"
    if path.suffix.casefold() == ".js":
        return f"// {marker}\n\n{text}"
    raise ValueError(f"unsupported skill resource type: {path}")


def is_generated_resource(
    path: Path,
    text: str,
    *,
    marker: str,
    metadata_names: Collection[str] = (),
) -> bool:
    lines = text.splitlines()
    if path.name in metadata_names:
        try:
            metadata = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(metadata, dict) and metadata.get("_generated") == marker
    if path.suffix.casefold() == ".json":
        try:
            resource = _parse_json_object(text, path)
        except ValueError:
            return False
        return resource.get("$comment") == marker
    if path.name == "SKILL.md":
        return len(lines) > 1 and lines[0] == "---" and lines[1] == f"# {marker}"
    if path.suffix.casefold() in {".py", ".sh", ".ps1", ".yaml", ".yml", ".toml"}:
        return bool(lines) and lines[0] == f"# {marker}"
    if path.suffix.casefold() in {".md", ".txt", ".html"}:
        return bool(lines) and lines[0] == f"<!-- {marker} -->"
    if path.suffix.casefold() == ".css":
        return bool(lines) and lines[0] == f"/* {marker} */"
    if path.suffix.casefold() == ".js":
        return bool(lines) and lines[0] == f"// {marker}"
    return False
