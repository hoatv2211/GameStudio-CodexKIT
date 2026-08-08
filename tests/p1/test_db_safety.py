from __future__ import annotations

import unittest


class DatabaseSafetyTests(unittest.TestCase):
    def complete_config(self) -> dict[str, object]:
        return {
            "project_owner": "Project Beta",
            "database": "game",
            "host": "127.0.0.1",
            "port": 3307,
            "schema_version": "beta-v1",
            "expected_schema": "beta-v1",
            "migration_sha256": "a" * 64,
            "backup_path": "backup.sql",
            "restore_command": "mysql game < backup.sql",
            "reviewer": "Network/Backend",
            "human_approval": True,
            "maintenance_window": "2026-08-09T02:00:00+07:00",
            "validation_queries": ["SELECT version FROM schema_version"],
        }

    def test_unknown_schema_is_blocked(self) -> None:
        from scripts.db_safety import plan_migration

        config = self.complete_config()
        config["schema_version"] = "unknown"
        plan = plan_migration(config)
        self.assertEqual("BLOCKED", plan["verdict"])
        self.assertIn("unknown schema", " ".join(plan["reasons"]).lower())

    def test_missing_target_identity_and_approval_are_blocked(self) -> None:
        from scripts.db_safety import plan_migration

        config = self.complete_config()
        config["database"] = ""
        config["project_owner"] = ""
        config["reviewer"] = ""
        config["human_approval"] = False
        plan = plan_migration(config)
        self.assertEqual("BLOCKED", plan["verdict"])
        reasons = " ".join(plan["reasons"])
        for expected in ("database", "project_owner", "reviewer", "human approval"):
            self.assertIn(expected, reasons)

    def test_recognized_isolated_schema_produces_dry_run_plan(self) -> None:
        from scripts.db_safety import plan_migration

        plan = plan_migration(self.complete_config())
        self.assertEqual("READY_FOR_REVIEW", plan["verdict"])
        self.assertTrue(plan["dry_run"])
        self.assertEqual("Project Beta", plan["project_owner"])
        self.assertEqual("Network/Backend", plan["reviewer"])
        self.assertTrue(plan["human_approval"])
        self.assertEqual(["SELECT version FROM schema_version"], plan["validation_queries"])
        self.assertNotIn("password", str(plan).lower())


if __name__ == "__main__":
    unittest.main()
