from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def audit_contract(client: dict[str, Any], server: dict[str, Any]) -> dict[str, Any]:
    client_names = set(client)
    server_names = set(server)
    opcode_mismatches: dict[str, dict[str, Any]] = {}
    field_mismatches: dict[str, dict[str, Any]] = {}
    direction_mismatches: dict[str, dict[str, Any]] = {}
    authority_mismatches: dict[str, dict[str, Any]] = {}
    pairing_mismatches: dict[str, dict[str, Any]] = {}
    normalization_errors: dict[str, list[str]] = {}

    def normalized_fields(packet_name: str, side: str, packet: dict[str, Any]) -> list[dict[str, Any]]:
        fields = packet.get("fields", [])
        errors: list[str] = []
        if not isinstance(fields, list):
            errors.append("fields must be a list")
            fields = []
        normalized: list[dict[str, Any]] = []
        for index, field in enumerate(fields):
            if not isinstance(field, dict) or set(field) != {"name", "type", "optional"}:
                errors.append(f"field {index} requires name, type, optional")
                continue
            if (
                not isinstance(field["name"], str)
                or not field["name"]
                or not isinstance(field["type"], str)
                or not field["type"]
                or not isinstance(field["optional"], bool)
            ):
                errors.append(f"field {index} has invalid value types")
                continue
            normalized.append(
                {"name": field["name"], "type": field["type"], "optional": field["optional"]}
            )
        if errors:
            normalization_errors[f"{side}:{packet_name}"] = errors
        return normalized

    for name in sorted(client_names.intersection(server_names)):
        client_packet = client[name]
        server_packet = server[name]
        if client_packet.get("opcode") != server_packet.get("opcode"):
            opcode_mismatches[name] = {
                "client": client_packet.get("opcode"),
                "server": server_packet.get("opcode"),
            }
        client_fields = normalized_fields(name, "client", client_packet)
        server_fields = normalized_fields(name, "server", server_packet)
        if client_fields != server_fields:
            field_mismatches[name] = {
                "client": client_fields,
                "server": server_fields,
            }
        if client_packet.get("direction") != server_packet.get("direction"):
            direction_mismatches[name] = {
                "client": client_packet.get("direction"),
                "server": server_packet.get("direction"),
            }
        if client_packet.get("authority") != server_packet.get("authority"):
            authority_mismatches[name] = {
                "client": client_packet.get("authority"),
                "server": server_packet.get("authority"),
            }
        if client_packet.get("response") != server_packet.get("response"):
            pairing_mismatches[name] = {
                "client": client_packet.get("response"),
                "server": server_packet.get("response"),
            }
    return {
        "status": "PASS"
        if (
            client_names == server_names
            and not opcode_mismatches
            and not field_mismatches
            and not direction_mismatches
            and not authority_mismatches
            and not pairing_mismatches
            and not normalization_errors
        )
        else "FAIL",
        "missing_on_server": sorted(client_names - server_names),
        "missing_on_client": sorted(server_names - client_names),
        "opcode_mismatches": opcode_mismatches,
        "field_mismatches": field_mismatches,
        "direction_mismatches": direction_mismatches,
        "authority_mismatches": authority_mismatches,
        "pairing_mismatches": pairing_mismatches,
        "normalization_errors": normalization_errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit normalized Lua client/server packet contracts.")
    parser.add_argument("client", type=Path)
    parser.add_argument("server", type=Path)
    args = parser.parse_args(argv)
    report = audit_contract(
        json.loads(args.client.read_text(encoding="utf-8")),
        json.loads(args.server.read_text(encoding="utf-8")),
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
