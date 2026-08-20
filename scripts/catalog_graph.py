from __future__ import annotations

from typing import Any, Iterable


def _index(items: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        raw_item_id = item.get("id")
        if not isinstance(raw_item_id, str) or not raw_item_id.strip():
            raise ValueError(f"invalid {label} id: {raw_item_id!r}")
        item_id = raw_item_id
        if item_id in indexed:
            raise ValueError(f"invalid or duplicate {label} id: {item_id}")
        indexed[item_id] = item
    return indexed


def _relationship_ids(
    item: dict[str, Any],
    owner_label: str,
    owner_id: str,
    field: str,
) -> list[str]:
    raw_values = item.get(field)
    if raw_values is None:
        return []
    if not isinstance(raw_values, list):
        raise ValueError(f"{owner_label} {owner_id} {field} must be a list")

    values: list[str] = []
    for index, raw_value in enumerate(raw_values):
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(
                f"{owner_label} {owner_id} {field}[{index}] "
                f"must be a nonblank string, got {raw_value!r}"
            )
        values.append(raw_value)
    return values


def resolve_pack_skill_closure(
    packs: Iterable[dict[str, Any]],
    capabilities: Iterable[dict[str, Any]],
    pack_id: str,
) -> list[str]:
    """Validate and return skills declared by the selected pack dependency closure.

    Missing or null relationship fields are empty; all other values must be lists.
    Capability dependencies must already be declared; undeclared skills are not auto-added.
    """
    pack_by_id = _index(packs, "pack")
    capability_by_id = _index(capabilities, "capability")
    if pack_id not in pack_by_id:
        raise ValueError(f"unknown pack: {pack_id}")

    pack_dependencies = {
        current_id: _relationship_ids(pack, "pack", current_id, "depends_on")
        for current_id, pack in pack_by_id.items()
    }
    pack_skills = {
        current_id: _relationship_ids(pack, "pack", current_id, "skills")
        for current_id, pack in pack_by_id.items()
    }
    capability_dependencies = {
        current_id: _relationship_ids(capability, "capability", current_id, "depends_on")
        for current_id, capability in capability_by_id.items()
    }

    selected_packs: set[str] = set()

    def visit_pack(current: str, trail: tuple[str, ...]) -> None:
        if current in trail:
            cycle = " -> ".join((*trail[trail.index(current):], current))
            raise ValueError(f"pack dependency cycle: {cycle}")
        pack = pack_by_id.get(current)
        if pack is None:
            raise ValueError(f"unknown pack dependency: {current}")
        if current in selected_packs:
            return
        for dependency in pack_dependencies[current]:
            visit_pack(dependency, (*trail, current))
        selected_packs.add(current)

    visit_pack(pack_id, ())
    available = {
        skill_id
        for selected_pack in selected_packs
        for skill_id in pack_skills[selected_pack]
    }

    for skill_id in sorted(available):
        if skill_id not in capability_by_id:
            raise ValueError(f"pack {pack_id} references unknown capability {skill_id}")

        pending = [skill_id]
        seen: set[str] = set()
        while pending:
            current_capability = pending.pop()
            if current_capability in seen:
                continue
            seen.add(current_capability)
            for dependency in capability_dependencies[current_capability]:
                if dependency not in capability_by_id:
                    raise ValueError(
                        f"capability {current_capability} references unknown dependency {dependency}"
                    )
                if dependency not in available:
                    raise ValueError(
                        f"pack {pack_id} is missing capability {dependency} "
                        f"required by {current_capability}"
                    )
                pending.append(dependency)
    return sorted(available)
