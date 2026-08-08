from __future__ import annotations

import unittest


class ExtendedP1Tests(unittest.TestCase):
    def field(self, name: str, type_name: str) -> dict[str, object]:
        return {"name": name, "type": type_name, "optional": False}

    def packet(self, opcode: int, direction: str = "client_to_server") -> dict[str, object]:
        return {
            "opcode": opcode,
            "direction": direction,
            "authority": "server",
            "response": None,
            "fields": [self.field("id", "uint32")],
        }

    def test_unity_guid_audit_detects_duplicates_missing_meta_and_stale_references(self) -> None:
        from scripts.unity_guid_audit import audit_guid_manifest

        report = audit_guid_manifest(
            [
                {"path": "Assets/A.prefab", "guid": "abc", "meta_exists": True},
                {"path": "Assets/B.prefab", "guid": "abc", "meta_exists": True},
                {"path": "Assets/C.mat", "guid": "def", "meta_exists": False},
            ],
            [{"source": "Assets/Scene.unity", "guid": "missing"}],
        )
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(["Assets/A.prefab", "Assets/B.prefab"], report["duplicate_guids"]["abc"])
        self.assertEqual(["Assets/C.mat"], report["missing_meta"])
        self.assertEqual([{"source": "Assets/Scene.unity", "guid": "missing"}], report["stale_references"])

    def test_build_evidence_requires_expected_artifact_even_with_zero_exit(self) -> None:
        from scripts.build_evidence import validate_build_evidence

        report = validate_build_evidence(
            {
                "command": "Unity -batchmode -buildWindows64Player build/game.exe",
                "exit_code": 0,
                "log_path": "logs/unity.log",
                "artifact_path": "build/game.exe",
                "artifact_exists": False,
                "limitations": ["No playmode tests"],
            }
        )
        self.assertEqual("FAIL", report["verdict"])
        self.assertIn("artifact", " ".join(report["reasons"]).lower())

    def test_crash_triage_normalizes_addresses_into_stable_signature(self) -> None:
        from scripts.crash_triage import triage_crash

        first = triage_crash(
            {
                "build_id": "server-42",
                "exception": "ACCESS_VIOLATION",
                "symbols_loaded": True,
                "frames": ["0x7ff1 Game::Tick+12", "0x7ff2 main+4"],
            }
        )
        second = triage_crash(
            {
                "build_id": "server-42",
                "exception": "ACCESS_VIOLATION",
                "symbols_loaded": True,
                "frames": ["0x9aa1 Game::Tick+12", "0x9aa2 main+4"],
            }
        )
        self.assertEqual(first["signature"], second["signature"])
        self.assertEqual("Game::Tick+12", first["normalized_frames"][0])

    def test_protocol_review_detects_version_and_direction_drift(self) -> None:
        from scripts.protocol_review import review_protocol

        report = review_protocol(
            {"version": "1", "packets": {"Move": self.packet(1)}},
            {"version": "2", "packets": {"Move": self.packet(1, "server_to_client")}},
        )
        self.assertEqual("FAIL", report["status"])
        self.assertTrue(report["version_mismatch"])
        self.assertIn("Move", report["contract"]["direction_mismatches"])

    def test_authority_review_flags_sensitive_client_authority_and_missing_guards(self) -> None:
        from scripts.authority_review import review_authority

        report = review_authority(
            [
                {
                    "name": "GrantCurrency",
                    "sensitive": True,
                    "authoritative_side": "client",
                    "server_validation": False,
                    "rate_limit": False,
                }
            ]
        )
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertEqual("FAIL", report["status"])
        self.assertIn("client-authority", kinds)
        self.assertIn("missing-server-validation", kinds)
        self.assertIn("missing-rate-limit", kinds)

    def test_save_migration_blocks_unknown_version_and_preserves_rollback(self) -> None:
        from scripts.save_migration import plan_save_migration

        migrations = [
            {
                "from_version": 1,
                "to_version": 2,
                "rename": {"gold": "coins"},
                "defaults": {"season": 1},
                "remove": [],
            }
        ]
        blocked = plan_save_migration({"schema_version": 0, "data": {}}, 2, migrations)
        self.assertEqual("BLOCKED", blocked["verdict"])

        source = {"schema_version": 1, "data": {"gold": 10}}
        report = plan_save_migration(source, 2, migrations)
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual({"schema_version": 2, "data": {"coins": 10, "season": 1}}, report["migrated"])
        self.assertEqual(source, report["rollback"])


if __name__ == "__main__":
    unittest.main()
