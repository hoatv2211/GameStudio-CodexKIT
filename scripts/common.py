from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("missing opening frontmatter delimiter")
    match = re.search(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", text, re.DOTALL)
    if not match:
        raise ValueError("missing closing frontmatter delimiter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, text[match.end() :]


def normalized_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_like = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.findall(r"[a-z0-9]+", ascii_like)
