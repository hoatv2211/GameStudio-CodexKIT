from __future__ import annotations

from typing import Any

try:
    from scripts.lua_contract_audit import audit_contract
except ModuleNotFoundError:
    from lua_contract_audit import audit_contract


def review_protocol(client: dict[str, Any], server: dict[str, Any]) -> dict[str, Any]:
    client_version = client.get("version")
    server_version = server.get("version")
    client_packets = client.get("packets") if isinstance(client.get("packets"), dict) else {}
    server_packets = server.get("packets") if isinstance(server.get("packets"), dict) else {}
    contract = audit_contract(client_packets, server_packets)
    version_mismatch = client_version != server_version
    return {
        "status": "PASS" if not version_mismatch and contract["status"] == "PASS" else "FAIL",
        "version_mismatch": version_mismatch,
        "client_version": client_version,
        "server_version": server_version,
        "contract": contract,
    }
