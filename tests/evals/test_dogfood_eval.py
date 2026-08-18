from __future__ import annotations

import hashlib
import json
import unittest
import datetime as dt
from pathlib import Path

import jsonschema

from tests._meta.support import temporary_directory


class DogfoodEvalTests(unittest.TestCase):
    def test_runtime_tool_operation_mapping_matches_supported_unity_relay(self) -> None:
        from scripts.dogfood_eval import UNITY_MCP_ARTIFACT_TOOL_OPERATIONS

        self.assertEqual(
            {
                "editor-state": {
                    ("read_mcp_resource", "mcpforunity://editor/state"),
                    ("resources/read", "mcpforunity://editor/state"),
                },
                "editmode-result": {
                    ("get_test_job", "editmode"),
                    ("run_tests", "editmode"),
                },
                "playmode-result": {
                    ("get_test_job", "playmode"),
                    ("manage_editor", "play"),
                    ("manage_editor", "stop"),
                    ("run_tests", "playmode"),
                },
                "console-report": {
                    ("read_console", "get"),
                },
                "runtime-assertion": {
                    ("execute_code", "execute"),
                    ("execute_custom_tool", "assert_localization"),
                },
            },
            UNITY_MCP_ARTIFACT_TOOL_OPERATIONS,
        )

    def _pass_payload_for_profile(
        self, root: Path, evidence_root: Path, profile: str
    ) -> dict[str, object]:
        from scripts.dogfood_eval import load_cases, load_profile

        results = []
        project_name = load_profile(root, profile)["project"]["name"]
        head = "abc1234"
        dirty_digest = "0" * 64
        scope_digest = "1" * 64
        timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        for case in load_cases(root, profile=profile):
            command = "python -B governed-fpc-audit"
            project_snapshot = f"{project_name}@{head}+dirty:{dirty_digest[:12]}"
            artifacts = []
            for kind in case["required_artifacts"]:
                suffix = ".txt" if kind == "report" or kind.endswith("-report") else ".json"
                artifact = evidence_root / case["id"] / f"{kind}{suffix}"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                if kind == "project-snapshot":
                    content = json.dumps(
                        {
                            "repository": project_name,
                            "head": head,
                            "dirty": True,
                            "dirty_digest": dirty_digest,
                            "scope_digest": scope_digest,
                            "captured_at": timestamp,
                        }
                    ) + "\n"
                elif kind == "command-log":
                    command_payload = {
                        "command": command,
                        "exit_code": 0,
                        "runtime_target": "Codex App/CLI",
                        "stdout": "governed audit completed",
                        "stderr": "",
                        "captured_at": timestamp,
                    }
                    if case["id"] == "fpc-unity-localization-runtime":
                        command_payload.update(
                            {
                                "case_id": case["id"],
                                "profile": profile,
                                "source_snapshot": project_snapshot,
                                "editor_instance_id": "fpc-editor-8080",
                            }
                        )
                    content = json.dumps(command_payload) + "\n"
                elif kind == "verdict":
                    content = json.dumps({"verdict": "PASS", "reason": None}) + "\n"
                elif kind == "runtime-audit":
                    content = json.dumps(
                        {
                            "schema_version": 1,
                            "kind": kind,
                            "case_id": case["id"],
                            "workflow": case["workflow"],
                            "profile": profile,
                            "runtime_target": "Codex App/CLI",
                            "source_snapshot": project_snapshot,
                            "editor_instance_id": "fpc-editor-8080",
                            "command": command,
                            "runner_capabilities": ["file-audit", "unity-mcp", "play-mode"],
                            "status": "PASS",
                            "timestamp": timestamp,
                            "checks": {
                                "unity_mcp_connected": True,
                                "editor_ready": True,
                                "editmode_passed": True,
                                "playmode_passed": True,
                                "console_clean": True,
                                "assertions_passed": True,
                            },
                            "screenshot_available": False,
                            "screenshot_unavailable_reason": "Headless MCP runner did not expose a frame capture endpoint.",
                            "artifact_manifest": [],
                        }
                    ) + "\n"
                elif kind == "mcp-transcript":
                    content = json.dumps(
                        {
                            "schema_version": 1,
                            "kind": kind,
                            "case_id": case["id"],
                            "profile": profile,
                            "runtime_target": "Codex App/CLI",
                            "editor_instance_id": "fpc-editor-8080",
                            "source_snapshot": project_snapshot,
                            "timestamp": timestamp,
                            "tool_calls": [],
                        }
                    ) + "\n"
                elif kind == "editor-state":
                    content = json.dumps(
                        {
                            "schema_version": 1,
                            "kind": kind,
                            "case_id": case["id"],
                            "profile": profile,
                            "runtime_target": "Codex App/CLI",
                            "editor_instance_id": "fpc-editor-8080",
                            "source_snapshot": project_snapshot,
                            "timestamp": timestamp,
                            "ready": True,
                            "compiling": False,
                            "compile_errors": 0,
                        }
                    ) + "\n"
                elif kind in {"editmode-result", "playmode-result"}:
                    content = json.dumps(
                        {
                            "schema_version": 1,
                            "kind": kind,
                            "case_id": case["id"],
                            "profile": profile,
                            "runtime_target": "Codex App/CLI",
                            "editor_instance_id": "fpc-editor-8080",
                            "source_snapshot": project_snapshot,
                            "timestamp": timestamp,
                            "status": "PASS",
                            "tests": 3,
                            "failures": 0,
                        }
                    ) + "\n"
                elif kind == "console-report":
                    content = json.dumps(
                        {
                            "schema_version": 1,
                            "kind": kind,
                            "case_id": case["id"],
                            "profile": profile,
                            "runtime_target": "Codex App/CLI",
                            "editor_instance_id": "fpc-editor-8080",
                            "source_snapshot": project_snapshot,
                            "timestamp": timestamp,
                            "errors": 0,
                            "warnings": 0,
                        }
                    ) + "\n"
                elif kind == "runtime-assertion":
                    content = json.dumps(
                        {
                            "schema_version": 1,
                            "kind": kind,
                            "case_id": case["id"],
                            "profile": profile,
                            "runtime_target": "Codex App/CLI",
                            "editor_instance_id": "fpc-editor-8080",
                            "source_snapshot": project_snapshot,
                            "timestamp": timestamp,
                            "status": "PASS",
                            "assertions": [
                                {
                                    "name": "localized_text_is_english",
                                    "passed": True,
                                    "observed": "Rendered target text contains English content.",
                                },
                                {
                                    "name": "localized_text_fits_target",
                                    "passed": True,
                                    "observed": "Rendered target has no overflow or truncation.",
                                },
                            ],
                        }
                    ) + "\n"
                elif kind == "report" or kind.endswith("-report"):
                    content = f"Verified governed report for {case['id']}.\n"
                else:
                    content = json.dumps({"case_id": case["id"], "kind": kind}) + "\n"
                artifact.write_text(content, encoding="utf-8")
                artifacts.append(
                    {
                        "kind": kind,
                        "path": artifact.relative_to(evidence_root).as_posix(),
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                )
            if case["id"] == "fpc-unity-localization-runtime":
                artifacts_by_kind = {artifact["kind"]: artifact for artifact in artifacts}
                transcript_ref = artifacts_by_kind["mcp-transcript"]
                transcript_path = evidence_root / transcript_ref["path"]
                transcript_payload = json.loads(transcript_path.read_text(encoding="utf-8"))
                call_specs = [
                    (
                        "mcp-1",
                        "read_mcp_resource",
                        "mcpforunity://editor/state",
                        "editor-state",
                        None,
                    ),
                    ("mcp-2", "run_tests", "EditMode", "editmode-result", "edit-job-1"),
                    ("mcp-3", "get_test_job", "EditMode", "editmode-result", "edit-job-1"),
                    ("mcp-4", "run_tests", "PlayMode", "playmode-result", "play-job-1"),
                    ("mcp-5", "get_test_job", "PlayMode", "playmode-result", "play-job-1"),
                    ("mcp-6", "read_console", "get", "console-report", None),
                    ("mcp-7", "execute_code", "execute", "runtime-assertion", None),
                ]
                transcript_payload["tool_calls"] = [
                    {
                        "call_id": call_id,
                        "tool": tool,
                        "operation": operation,
                        "status": "PASS",
                        "case_id": case["id"],
                        "editor_instance_id": "fpc-editor-8080",
                        "source_snapshot": project_snapshot,
                        "artifact_kind": artifact_kind,
                        "artifact_path": artifacts_by_kind[artifact_kind]["path"],
                        "artifact_sha256": artifacts_by_kind[artifact_kind]["sha256"],
                        "job_id": job_id,
                    }
                    for call_id, tool, operation, artifact_kind, job_id in call_specs
                ]
                transcript_path.write_text(json.dumps(transcript_payload) + "\n", encoding="utf-8")
                transcript_ref["sha256"] = hashlib.sha256(transcript_path.read_bytes()).hexdigest()

                audit_ref = artifacts_by_kind["runtime-audit"]
                audit_path = evidence_root / audit_ref["path"]
                audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
                manifested_kinds = {
                    "command-log",
                    "project-snapshot",
                    "mcp-transcript",
                    "editor-state",
                    "editmode-result",
                    "playmode-result",
                    "console-report",
                    "runtime-assertion",
                }
                audit_payload["artifact_manifest"] = [
                    {
                        "kind": artifact["kind"],
                        "path": artifact["path"],
                        "sha256": artifact["sha256"],
                    }
                    for artifact in artifacts
                    if artifact["kind"] in manifested_kinds
                ]
                audit_path.write_text(json.dumps(audit_payload) + "\n", encoding="utf-8")
                audit_ref["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            results.append(
                {
                    "id": case["id"],
                    "workflow": case["workflow"],
                    "verdict": "PASS",
                    "evidence_label": "Verified",
                    "runtime_target": "Codex App/CLI",
                    "command": command,
                    "exit_code": 0,
                    "artifacts": artifacts,
                    "project_snapshot": project_snapshot,
                    "reviewer": "Localization Lead",
                    "timestamp": timestamp,
                    "unauthorized_write": False,
                    "restore": "No mutation performed",
                    "reason": None,
                }
            )
        return {"results": results}

    def _pass_payload(self, root: Path, evidence_root: Path) -> dict[str, object]:
        from scripts.dogfood_eval import load_cases

        results = []
        project_name = "test-project"
        head = "abc1234"
        dirty_digest = "2" * 64
        scope_digest = "3" * 64
        timestamp = "2026-08-09T05:00:00+00:00"
        for case in load_cases(root):
            command = "hermes run governed-dogfood"
            project_snapshot = f"{project_name}@{head}+dirty:{dirty_digest[:12]}"
            artifacts = []
            for kind in case["required_artifacts"]:
                suffix = ".txt" if kind == "report" or kind.endswith("-report") else ".json"
                artifact = evidence_root / case["id"] / f"{kind}{suffix}"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                if kind == "project-snapshot":
                    content = json.dumps(
                        {
                            "repository": project_name,
                            "head": head,
                            "dirty": True,
                            "dirty_digest": dirty_digest,
                            "scope_digest": scope_digest,
                            "captured_at": timestamp,
                        }
                    ) + "\n"
                elif kind == "command-log":
                    content = json.dumps(
                        {
                            "command": command,
                            "exit_code": 0,
                            "runtime_target": "Hermes Agent",
                            "stdout": "governed dogfood completed",
                            "stderr": "",
                            "captured_at": timestamp,
                        }
                    ) + "\n"
                elif kind == "verdict":
                    content = json.dumps({"verdict": "PASS", "reason": None}) + "\n"
                elif kind == "report" or kind.endswith("-report"):
                    content = f"Verified governed report for {case['id']}.\n"
                else:
                    content = json.dumps({"case_id": case["id"], "kind": kind}) + "\n"
                artifact.write_text(content, encoding="utf-8")
                artifacts.append(
                    {
                        "kind": kind,
                        "path": artifact.relative_to(evidence_root).as_posix(),
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                )
            results.append(
                {
                    "id": case["id"],
                    "workflow": case["workflow"],
                    "verdict": "PASS",
                    "evidence_label": "Verified",
                    "runtime_target": "Hermes Agent",
                    "command": command,
                    "exit_code": 0,
                    "artifacts": artifacts,
                    "project_snapshot": project_snapshot,
                    "reviewer": "QA Lead",
                    "timestamp": timestamp,
                    "unauthorized_write": False,
                    "restore": "No mutation performed",
                    "reason": None,
                }
            )
        return {"results": results}

    def test_repository_pack_has_twelve_unique_game_scenarios(self) -> None:
        from scripts.dogfood_eval import load_cases

        root = Path(__file__).resolve().parents[2]
        cases = load_cases(root)
        self.assertEqual(12, len(cases))
        self.assertEqual(12, len({case["id"] for case in cases}))
        self.assertGreaterEqual(len({case["workflow"] for case in cases}), 8)

    def test_repository_pack_matches_schema(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "evals" / "schema" / "dogfood-case.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((root / "evals" / "dogfood" / "game-studio-scenarios.json").read_text(encoding="utf-8"))
        jsonschema.validate(fixture, schema)

    def test_result_schema_is_strict_structured_output_compatible(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "evals" / "schema" / "dogfood-result.schema.json").read_text(encoding="utf-8"))

        self.assertEqual("object", schema["type"])
        self.assertEqual(["results"], schema["required"])
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        result = schema["$defs"]["result"]
        self.assertEqual(set(result["properties"]), set(result["required"]))
        artifact = schema["$defs"]["artifact"]
        self.assertEqual(set(artifact["properties"]), set(artifact["required"]))
        self.assertFalse(result["additionalProperties"])
        self.assertFalse(artifact["additionalProperties"])

    def test_missing_runner_results_are_blocked(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        report = evaluate_results(root, None)
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertEqual(0, report["observed_cases"])

    def test_profile_results_ignore_unrelated_universal_cases(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            result_path = output_root / "results.json"
            result_path.write_text(
                json.dumps(
                    self._pass_payload_for_profile(
                        root, evidence_root, "fpc-global-localization-static"
                    )
                ),
                encoding="utf-8",
            )

            report = evaluate_results(
                root,
                result_path,
                profile="fpc-global-localization-static",
                artifact_root=evidence_root,
            )

        self.assertEqual("PASS", report["verdict"])
        self.assertEqual(2, report["total_cases"])
        self.assertEqual("fpc-global-localization-static", report["profile"])

    def test_runtime_profile_does_not_downgrade_missing_mcp(self) -> None:
        from scripts.dogfood_eval import evaluate_results, load_cases

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            result_path = output_root / "results.json"
            payload = {
                "results": [
                    {
                        "id": case["id"],
                        "workflow": case["workflow"],
                        "verdict": "BLOCKED",
                        "evidence_label": "BLOCKED",
                        "runtime_target": "Codex App/CLI",
                        "command": None,
                        "exit_code": None,
                        "artifacts": [],
                        "project_snapshot": None,
                        "reviewer": None,
                        "timestamp": None,
                        "unauthorized_write": None,
                        "restore": None,
                        "reason": "Unity MCP/editor unavailable",
                    }
                    for case in load_cases(root, profile="fpc-global-localization-runtime")
                ]
            }
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            report = evaluate_results(
                root,
                result_path,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn("fpc-unity-localization-runtime", report["blocked"])

    def test_valid_fail_result_makes_the_overall_report_fail(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            failed = next(
                item
                for item in payload["results"]
                if item["id"] == "fpc-unity-localization-runtime"
            )
            failed.update(
                verdict="FAIL",
                evidence_label="Verified",
                command=None,
                exit_code=None,
                artifacts=[],
                reason="runtime evidence project snapshot mismatch",
            )
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertEqual(2, report["passed"])
        self.assertIn(
            "fpc-unity-localization-runtime: runner reported FAIL",
            " ".join(report["failures"]),
        )

    def test_malformed_case_pack_is_rejected_before_runner_use(self) -> None:
        from scripts.dogfood_eval import load_cases

        with temporary_directory() as temp:
            root = Path(temp)
            fixture = root / "evals" / "dogfood" / "game-studio-scenarios.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                json.dumps({"schema_version": 1, "cases": [{"id": "broken"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_cases(root)

    def test_bare_pass_without_evidence_fails(self) -> None:
        from scripts.dogfood_eval import evaluate_results, load_cases

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            result_path = Path(temp) / "results.json"
            result_path.write_text(
                json.dumps(
                    [
                        {
                            "id": case["id"],
                            "workflow": case["workflow"],
                            "verdict": "PASS",
                        }
                        for case in load_cases(root)
                    ]
                ),
                encoding="utf-8",
            )

            report = evaluate_results(root, result_path)

            self.assertEqual("FAIL", report["verdict"])
            self.assertTrue(report["failures"])

    def test_pass_rejects_unknown_result_fields(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload(root, evidence_root)
            payload["results"][0]["unexpected"] = True
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(root, result_path, artifact_root=evidence_root)

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(report["failures"])

    def test_pass_rejects_missing_and_hash_drifted_artifacts(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload(root, evidence_root)
            payload["results"][0]["artifacts"][0]["path"] = "missing/file.json"
            payload["results"][1]["artifacts"][0]["sha256"] = "0" * 64
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(root, result_path, artifact_root=evidence_root)

        self.assertEqual("FAIL", report["verdict"])
        failures = " ".join(report["failures"])
        self.assertIn("does not exist", failures)
        self.assertIn("sha256 mismatch", failures)

    def test_pass_requires_timezone_aware_non_future_timestamp(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        for label, timestamp in (
            ("naive", "2026-08-17T12:00:00"),
            ("future", "2999-01-01T00:00:00+00:00"),
        ):
            with self.subTest(label=label), temporary_directory() as temp:
                output_root = Path(temp)
                evidence_root = output_root / "artifacts"
                payload = self._pass_payload_for_profile(
                    root, evidence_root, "fpc-global-localization-static"
                )
                payload["results"][0]["timestamp"] = timestamp
                result_path = output_root / "results.json"
                result_path.write_text(json.dumps(payload), encoding="utf-8")

                report = evaluate_results(
                    root,
                    result_path,
                    artifact_root=evidence_root,
                    profile="fpc-global-localization-static",
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(any("timestamp" in item for item in report["failures"]))

    def test_pass_rejects_placeholder_identity_and_restore_fields(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        for field, value in (
            ("command", "TODO"),
            ("project_snapshot", "TBD"),
            ("reviewer", "N/A"),
            ("restore", "placeholder"),
        ):
            with self.subTest(field=field), temporary_directory() as temp:
                output_root = Path(temp)
                evidence_root = output_root / "artifacts"
                payload = self._pass_payload_for_profile(
                    root, evidence_root, "fpc-global-localization-static"
                )
                payload["results"][0][field] = value
                result_path = output_root / "results.json"
                result_path.write_text(json.dumps(payload), encoding="utf-8")

                report = evaluate_results(
                    root,
                    result_path,
                    artifact_root=evidence_root,
                    profile="fpc-global-localization-static",
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(any(field in item and "placeholder" in item for item in report["failures"]))

    def test_pass_rejects_duplicate_normalized_artifact_paths(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            artifacts = payload["results"][0]["artifacts"]
            artifacts[1]["path"] = artifacts[0]["path"].replace("/", "\\")
            artifacts[1]["sha256"] = artifacts[0]["sha256"]
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("duplicate artifact path" in item for item in report["failures"]))

    def test_pass_requires_runtime_target_and_semantically_bound_artifacts(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            result = payload["results"][0]
            result["runtime_target"] = "Codex App/CLI"
            command_log = next(
                item for item in result["artifacts"] if item["kind"] == "command-log"
            )
            command_path = evidence_root / command_log["path"]
            command_path.write_text(
                json.dumps({"command": "different-command", "exit_code": 9}) + "\n",
                encoding="utf-8",
            )
            command_log["sha256"] = hashlib.sha256(command_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        failures = " ".join(report["failures"])
        self.assertIn("command-log", failures)
        self.assertIn("command", failures)

    def test_pass_without_runtime_target_is_rejected(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            del payload["results"][0]["runtime_target"]
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("runtime_target" in item for item in report["failures"]))

    def test_pass_runtime_target_must_be_allowed_by_profile(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            result = payload["results"][0]
            result["runtime_target"] = "PlayStation 9"
            command_log = next(
                item for item in result["artifacts"] if item["kind"] == "command-log"
            )
            command_path = evidence_root / command_log["path"]
            command_payload = json.loads(command_path.read_text(encoding="utf-8"))
            command_payload["runtime_target"] = "PlayStation 9"
            command_path.write_text(json.dumps(command_payload) + "\n", encoding="utf-8")
            command_log["sha256"] = hashlib.sha256(command_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("profile runtime_targets" in item for item in report["failures"]))

    def test_pass_runtime_target_must_match_command_log(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            result = payload["results"][0]
            command_log = next(
                item for item in result["artifacts"] if item["kind"] == "command-log"
            )
            command_path = evidence_root / command_log["path"]
            command_payload = json.loads(command_path.read_text(encoding="utf-8"))
            command_payload["runtime_target"] = "Hermes Agent"
            command_path.write_text(json.dumps(command_payload) + "\n", encoding="utf-8")
            command_log["sha256"] = hashlib.sha256(command_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("command-log runtime_target" in item for item in report["failures"]))

    def test_profile_rejects_stale_strict_evidence(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            payload["results"][0]["timestamp"] = "2020-01-01T00:00:00+00:00"
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("stale" in item for item in report["failures"]))

    def test_profile_rejects_stale_semantic_artifact(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-static"
            )
            result = payload["results"][0]
            project_snapshot = next(
                artifact for artifact in result["artifacts"] if artifact["kind"] == "project-snapshot"
            )
            snapshot_path = evidence_root / project_snapshot["path"]
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["captured_at"] = "2020-01-01T00:00:00+00:00"
            snapshot_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
            project_snapshot["sha256"] = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-static",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("project-snapshot" in item and "stale" in item for item in report["failures"]))

    def test_trivial_runtime_audit_cannot_pass_runtime_profile(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            runtime = next(
                result
                for result in payload["results"]
                if result["id"] == "fpc-unity-localization-runtime"
            )
            runtime_audit = next(
                artifact for artifact in runtime["artifacts"] if artifact["kind"] == "runtime-audit"
            )
            audit_path = evidence_root / runtime_audit["path"]
            audit_path.write_text('{"status": "PASS"}\n', encoding="utf-8")
            runtime_audit["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("runtime-audit" in item for item in report["failures"]))

    def test_runtime_profile_accepts_fully_bound_provenance_fixture(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("PASS", report["verdict"], report["failures"])

    def test_runtime_audit_must_manifest_every_provenance_artifact(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            runtime = next(
                result
                for result in payload["results"]
                if result["id"] == "fpc-unity-localization-runtime"
            )
            audit_ref = next(
                artifact for artifact in runtime["artifacts"] if artifact["kind"] == "runtime-audit"
            )
            audit_path = evidence_root / audit_ref["path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["artifact_manifest"] = audit["artifact_manifest"][:-1]
            audit_path.write_text(json.dumps(audit) + "\n", encoding="utf-8")
            audit_ref["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("artifact_manifest" in item for item in report["failures"]))

    def test_mcp_transcript_calls_bind_exact_result_artifacts(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            runtime = next(
                result
                for result in payload["results"]
                if result["id"] == "fpc-unity-localization-runtime"
            )
            refs = {artifact["kind"]: artifact for artifact in runtime["artifacts"]}
            transcript_path = evidence_root / refs["mcp-transcript"]["path"]
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            transcript["tool_calls"][0]["artifact_sha256"] = "0" * 64
            transcript_path.write_text(json.dumps(transcript) + "\n", encoding="utf-8")
            refs["mcp-transcript"]["sha256"] = hashlib.sha256(transcript_path.read_bytes()).hexdigest()
            audit_path = evidence_root / refs["runtime-audit"]["path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            transcript_manifest = next(
                item for item in audit["artifact_manifest"] if item["kind"] == "mcp-transcript"
            )
            transcript_manifest["sha256"] = refs["mcp-transcript"]["sha256"]
            audit_path.write_text(json.dumps(audit) + "\n", encoding="utf-8")
            refs["runtime-audit"]["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(
            any("mcp-transcript" in item and "artifact_sha256" in item for item in report["failures"])
        )

    def test_runtime_transcript_rejects_fake_tool_after_rehash(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            runtime = next(
                result
                for result in payload["results"]
                if result["id"] == "fpc-unity-localization-runtime"
            )
            refs = {artifact["kind"]: artifact for artifact in runtime["artifacts"]}
            transcript_path = evidence_root / refs["mcp-transcript"]["path"]
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            transcript["tool_calls"][0]["tool"] = "fake_unity_tool"
            transcript_path.write_text(json.dumps(transcript) + "\n", encoding="utf-8")
            refs["mcp-transcript"]["sha256"] = hashlib.sha256(transcript_path.read_bytes()).hexdigest()

            audit_path = evidence_root / refs["runtime-audit"]["path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            transcript_manifest = next(
                item for item in audit["artifact_manifest"] if item["kind"] == "mcp-transcript"
            )
            transcript_manifest["sha256"] = refs["mcp-transcript"]["sha256"]
            audit_path.write_text(json.dumps(audit) + "\n", encoding="utf-8")
            refs["runtime-audit"]["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(
            any("approved Unity MCP tool/operation" in item for item in report["failures"])
        )

    def test_runtime_transcript_rejects_manage_editor_as_editor_state_source(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            runtime = next(
                result
                for result in payload["results"]
                if result["id"] == "fpc-unity-localization-runtime"
            )
            refs = {artifact["kind"]: artifact for artifact in runtime["artifacts"]}
            transcript_path = evidence_root / refs["mcp-transcript"]["path"]
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            editor_call = next(
                call for call in transcript["tool_calls"] if call["artifact_kind"] == "editor-state"
            )
            editor_call.update({"tool": "manage_editor", "operation": "state"})
            transcript_path.write_text(json.dumps(transcript) + "\n", encoding="utf-8")
            refs["mcp-transcript"]["sha256"] = hashlib.sha256(
                transcript_path.read_bytes()
            ).hexdigest()
            audit_path = evidence_root / refs["runtime-audit"]["path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            next(
                item for item in audit["artifact_manifest"] if item["kind"] == "mcp-transcript"
            )["sha256"] = refs["mcp-transcript"]["sha256"]
            audit_path.write_text(json.dumps(audit) + "\n", encoding="utf-8")
            refs["runtime-audit"]["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("editor-state" in item for item in report["failures"]))

    def test_runtime_transcript_requires_paired_test_job_completion(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        for mutation in ("missing-completion", "wrong-job", "play-control-substitute"):
            with self.subTest(mutation=mutation), temporary_directory() as temp:
                output_root = Path(temp)
                evidence_root = output_root / "artifacts"
                payload = self._pass_payload_for_profile(
                    root, evidence_root, "fpc-global-localization-runtime"
                )
                runtime = next(
                    result
                    for result in payload["results"]
                    if result["id"] == "fpc-unity-localization-runtime"
                )
                refs = {artifact["kind"]: artifact for artifact in runtime["artifacts"]}
                transcript_path = evidence_root / refs["mcp-transcript"]["path"]
                transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
                if mutation == "missing-completion":
                    transcript["tool_calls"] = [
                        call
                        for call in transcript["tool_calls"]
                        if not (
                            call["artifact_kind"] == "editmode-result"
                            and call["tool"] == "get_test_job"
                        )
                    ]
                else:
                    completion = next(
                        call
                        for call in transcript["tool_calls"]
                        if call["artifact_kind"] == "playmode-result"
                        and call["tool"] == "get_test_job"
                    )
                    if mutation == "wrong-job":
                        completion["job_id"] = "different-play-job"
                    else:
                        completion.update({"tool": "manage_editor", "operation": "play", "job_id": None})
                transcript_path.write_text(json.dumps(transcript) + "\n", encoding="utf-8")
                refs["mcp-transcript"]["sha256"] = hashlib.sha256(
                    transcript_path.read_bytes()
                ).hexdigest()
                audit_path = evidence_root / refs["runtime-audit"]["path"]
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                next(
                    item
                    for item in audit["artifact_manifest"]
                    if item["kind"] == "mcp-transcript"
                )["sha256"] = refs["mcp-transcript"]["sha256"]
                audit_path.write_text(json.dumps(audit) + "\n", encoding="utf-8")
                refs["runtime-audit"]["sha256"] = hashlib.sha256(
                    audit_path.read_bytes()
                ).hexdigest()
                result_path = output_root / "results.json"
                result_path.write_text(json.dumps(payload), encoding="utf-8")

                report = evaluate_results(
                    root,
                    result_path,
                    artifact_root=evidence_root,
                    profile="fpc-global-localization-runtime",
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(
                    any("test job" in item or "get_test_job" in item for item in report["failures"]),
                    report["failures"],
                )

    def test_runtime_artifacts_bind_source_snapshot_even_after_rehash(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            payload = self._pass_payload_for_profile(
                root, evidence_root, "fpc-global-localization-runtime"
            )
            runtime = next(
                result
                for result in payload["results"]
                if result["id"] == "fpc-unity-localization-runtime"
            )
            refs = {artifact["kind"]: artifact for artifact in runtime["artifacts"]}
            editor_path = evidence_root / refs["editor-state"]["path"]
            editor = json.loads(editor_path.read_text(encoding="utf-8"))
            editor["source_snapshot"] = "DifferentProject@abcdef0+dirty:000000000000"
            editor_path.write_text(json.dumps(editor) + "\n", encoding="utf-8")
            refs["editor-state"]["sha256"] = hashlib.sha256(editor_path.read_bytes()).hexdigest()

            transcript_path = evidence_root / refs["mcp-transcript"]["path"]
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            editor_call = next(
                call for call in transcript["tool_calls"] if call["artifact_kind"] == "editor-state"
            )
            editor_call["artifact_sha256"] = refs["editor-state"]["sha256"]
            transcript_path.write_text(json.dumps(transcript) + "\n", encoding="utf-8")
            refs["mcp-transcript"]["sha256"] = hashlib.sha256(transcript_path.read_bytes()).hexdigest()

            audit_path = evidence_root / refs["runtime-audit"]["path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            for item in audit["artifact_manifest"]:
                if item["kind"] in {"editor-state", "mcp-transcript"}:
                    item["sha256"] = refs[item["kind"]]["sha256"]
            audit_path.write_text(json.dumps(audit) + "\n", encoding="utf-8")
            refs["runtime-audit"]["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

            report = evaluate_results(
                root,
                result_path,
                artifact_root=evidence_root,
                profile="fpc-global-localization-runtime",
            )

        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("source_snapshot" in item for item in report["failures"]))

    def test_runtime_profile_rejects_nonsemantic_runtime_artifacts(self) -> None:
        from scripts.dogfood_eval import evaluate_results

        root = Path(__file__).resolve().parents[2]
        mutations = {
            "mcp-transcript": ("tool_calls", []),
            "editor-state": ("ready", False),
            "editmode-result": ("tests", 0),
            "playmode-result": ("failures", 1),
            "console-report": ("errors", 1),
            "runtime-assertion": ("assertions", []),
        }
        for kind, (field, value) in mutations.items():
            with self.subTest(kind=kind), temporary_directory() as temp:
                output_root = Path(temp)
                evidence_root = output_root / "artifacts"
                payload = self._pass_payload_for_profile(
                    root, evidence_root, "fpc-global-localization-runtime"
                )
                runtime = next(
                    result
                    for result in payload["results"]
                    if result["id"] == "fpc-unity-localization-runtime"
                )
                artifact = next(item for item in runtime["artifacts"] if item["kind"] == kind)
                artifact_path = evidence_root / artifact["path"]
                artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                artifact_payload[field] = value
                artifact_path.write_text(json.dumps(artifact_payload) + "\n", encoding="utf-8")
                artifact["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                result_path = output_root / "results.json"
                result_path.write_text(json.dumps(payload), encoding="utf-8")

                report = evaluate_results(
                    root,
                    result_path,
                    artifact_root=evidence_root,
                    profile="fpc-global-localization-runtime",
                )

                self.assertEqual("FAIL", report["verdict"])
                self.assertTrue(any(kind in item for item in report["failures"]))

    def test_legacy_blocked_array_is_diagnostic_only(self) -> None:
        from scripts.dogfood_eval import evaluate_results, load_cases, write_summaries

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            result_path = output_root / "legacy-results.json"
            result_path.write_text(
                json.dumps(
                    [
                        {
                            "id": case["id"],
                            "workflow": case["workflow"],
                            "verdict": "BLOCKED",
                            "evidence_label": "BLOCKED",
                            "reason": "runner unavailable",
                        }
                        for case in load_cases(root)
                    ]
                ),
                encoding="utf-8",
            )

            report = evaluate_results(root, result_path)

            self.assertEqual("BLOCKED", report["verdict"])
            self.assertTrue(report["legacy_format"])
            with self.assertRaisesRegex(ValueError, "complete PASS"):
                write_summaries(root, result_path, output_root / "summaries")

    def test_verified_results_can_generate_catalog_summaries(self) -> None:
        from scripts.dogfood_eval import evaluate_results, load_cases, write_summaries

        root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output_root = Path(temp)
            evidence_root = output_root / "artifacts"
            result_path = output_root / "results.json"
            result_path.write_text(json.dumps(self._pass_payload(root, evidence_root)), encoding="utf-8")

            report = evaluate_results(root, result_path, artifact_root=evidence_root)
            written = write_summaries(
                root,
                result_path,
                output_root / "summaries",
                artifact_root=evidence_root,
            )

            self.assertEqual("PASS", report["verdict"])
            self.assertEqual(12, len(written))
            summary = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual("Verified", summary["label"])
            self.assertEqual(0, summary["exit_code"])
            self.assertTrue(summary["artifacts"])
            self.assertEqual(str(evidence_root.resolve()), summary["artifact_root"])


if __name__ == "__main__":
    unittest.main()
