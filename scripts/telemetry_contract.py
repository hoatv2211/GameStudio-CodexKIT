from __future__ import annotations

from collections import Counter
from typing import Any


def validate_telemetry_contract(
    current: list[dict[str, Any]], previous: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    ids = [str(event.get("id", "")) for event in current]
    duplicate_event_ids = sorted(
        event_id for event_id, count in Counter(ids).items() if event_id and count > 1
    )
    invalid_events: list[str] = []
    current_by_id: dict[str, dict[str, Any]] = {}
    for event in current:
        event_id = str(event.get("id", ""))
        properties = event.get("required_properties")
        if not event_id or not isinstance(properties, dict) or any(
            not isinstance(name, str) or not isinstance(type_name, str)
            for name, type_name in properties.items()
        ):
            invalid_events.append(event_id or "<missing-id>")
            continue
        current_by_id.setdefault(event_id, event)
    type_changes: list[str] = []
    removed_properties: list[str] = []
    previous_by_id = {
        str(event.get("id")): event
        for event in previous or []
        if isinstance(event, dict) and event.get("id")
    }
    for event_id, old_event in previous_by_id.items():
        new_event = current_by_id.get(event_id)
        if not new_event:
            continue
        old_properties = old_event.get("required_properties", {})
        new_properties = new_event.get("required_properties", {})
        for property_name, old_type in old_properties.items():
            qualified = f"{event_id}.{property_name}"
            if property_name not in new_properties:
                removed_properties.append(qualified)
            elif new_properties[property_name] != old_type:
                type_changes.append(qualified)
    failures = duplicate_event_ids or invalid_events or type_changes or removed_properties
    return {
        "status": "FAIL" if failures else "PASS",
        "duplicate_event_ids": duplicate_event_ids,
        "invalid_events": invalid_events,
        "type_changes": sorted(type_changes),
        "removed_properties": sorted(removed_properties),
    }
