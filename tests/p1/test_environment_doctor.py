from __future__ import annotations

import unittest


class EnvironmentDoctorTests(unittest.TestCase):
    def test_detects_duplicate_ports_and_config_mismatch(self) -> None:
        from scripts.environment_doctor import analyze_services

        services = [
            {"name": "project-beta", "host": "127.0.0.1", "port": 27000, "configured_port": 27000},
            {"name": "mu", "host": "127.0.0.1", "port": 27000, "configured_port": 27001},
        ]
        report = analyze_services(services)
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(1, len(report["port_conflicts"]))
        self.assertEqual(["mu"], report["config_mismatches"])

    def test_clean_static_topology_passes(self) -> None:
        from scripts.environment_doctor import analyze_services

        report = analyze_services(
            [
                {"name": "mysql-beta", "host": "127.0.0.1", "port": 3307, "configured_port": 3307},
                {"name": "mysql-mu", "host": "127.0.0.1", "port": 3306, "configured_port": 3306},
            ]
        )
        self.assertEqual("PASS", report["status"])


if __name__ == "__main__":
    unittest.main()
