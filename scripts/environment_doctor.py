from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def analyze_services(services: list[dict[str, Any]]) -> dict[str, Any]:
    listeners: dict[tuple[str, int], list[str]] = defaultdict(list)
    config_mismatches: list[str] = []
    normalized: list[dict[str, Any]] = []
    for service in services:
        required = {"name", "host", "port", "configured_port"}
        if set(service) != required:
            raise ValueError(f"service requires only {sorted(required)}")
        name = str(service["name"])
        host = str(service["host"])
        port = int(service["port"])
        configured_port = int(service["configured_port"])
        listeners[(host, port)].append(name)
        if port != configured_port:
            config_mismatches.append(name)
        normalized.append(
            {"name": name, "host": host, "port": port, "configured_port": configured_port}
        )
    conflicts = [
        {"host": host, "port": port, "services": sorted(names)}
        for (host, port), names in sorted(listeners.items())
        if len(names) > 1
    ]
    return {
        "status": "PASS" if not conflicts and not config_mismatches else "FAIL",
        "services": normalized,
        "port_conflicts": conflicts,
        "config_mismatches": sorted(config_mismatches),
        "limitations": ["Static topology only; active process listeners were not queried."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a static multi-service port topology.")
    parser.add_argument("config", type=Path)
    args = parser.parse_args(argv)
    services = json.loads(args.config.read_text(encoding="utf-8"))
    report = analyze_services(services)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
