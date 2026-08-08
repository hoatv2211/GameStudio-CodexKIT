from __future__ import annotations

import unittest


class ContractAuditTests(unittest.TestCase):
    def packet(
        self,
        opcode: int,
        fields: list[dict[str, object]],
        *,
        direction: str = "client_to_server",
        authority: str = "server",
        response: str | None = None,
    ) -> dict[str, object]:
        return {
            "opcode": opcode,
            "direction": direction,
            "authority": authority,
            "response": response,
            "fields": fields,
        }

    def field(self, name: str, type_name: str) -> dict[str, object]:
        return {"name": name, "type": type_name, "optional": False}

    def test_lua_contract_reports_packet_and_field_drift(self) -> None:
        from scripts.lua_contract_audit import audit_contract

        report = audit_contract(
            {
                "Login": self.packet(1, [self.field("account", "string"), self.field("token", "string")]),
                "Move": self.packet(2, [self.field("x", "int32"), self.field("y", "int32")]),
            },
            {
                "Login": self.packet(1, [self.field("account", "string")]),
                "Chat": self.packet(3, [self.field("text", "string")]),
            },
        )
        self.assertEqual(["Move"], report["missing_on_server"])
        self.assertEqual(["Chat"], report["missing_on_client"])
        self.assertIn("Login", report["field_mismatches"])

    def test_lua_contract_rejects_field_order_type_direction_and_pairing_drift(self) -> None:
        from scripts.lua_contract_audit import audit_contract

        client = {
            "Move": self.packet(
                2,
                [self.field("x", "int32"), self.field("y", "int32")],
                response="MoveAck",
            )
        }
        server = {
            "Move": self.packet(
                2,
                [self.field("y", "int32"), self.field("x", "float")],
                direction="server_to_client",
                response="OtherAck",
            )
        }
        report = audit_contract(client, server)
        self.assertEqual("FAIL", report["status"])
        self.assertIn("Move", report["field_mismatches"])
        self.assertIn("Move", report["direction_mismatches"])
        self.assertIn("Move", report["pairing_mismatches"])

    def test_localization_reports_missing_extra_and_mismatch(self) -> None:
        from scripts.localization_audit import audit_localization

        report = audit_localization(
            {"hello": "Hello", "bye": "Bye"},
            {"client": {"hello": "Hello", "extra": "Extra"}, "server": {"hello": "Xin chao", "bye": "Bye"}},
        )
        self.assertEqual(["bye"], report["copies"]["client"]["missing"])
        self.assertEqual(["extra"], report["copies"]["client"]["extra"])
        self.assertEqual(["hello"], report["copies"]["server"]["mismatched"])


if __name__ == "__main__":
    unittest.main()
