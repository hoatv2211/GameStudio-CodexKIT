from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROFILE = "fpc-global-localization-runtime"
RUNTIME_CASE = "fpc-unity-localization-runtime"


class FpcLocalizationCertificationTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _artifact_ref(self, root: Path, path: Path, kind: str) -> dict[str, str]:
        return {
            "kind": kind,
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _snapshot(self, project: Path, timestamp: str) -> dict[str, object]:
        return {
            "repository": "FlyingPhoenixChronicles",
            "repository_path": str(project.resolve()),
            "branch": "dev/windown-server",
            "head": "abc1234",
            "dirty": True,
            "dirty_digest": "0" * 64,
            "scope_paths": ["tools/localization"],
            "scope_digest": "1" * 64,
            "captured_at": timestamp,
        }

    def _project_snapshot(self, snapshot: dict[str, object]) -> str:
        return (
            f"{snapshot['repository']}@{snapshot['head']}"
            f"+dirty:{str(snapshot['dirty_digest'])[:12]}"
        )

    def _write_static_result(
        self,
        project: Path,
        case: dict[str, object],
        output_root: Path,
        snapshot: dict[str, object],
        **_: object,
    ) -> dict[str, object]:
        from scripts.fpc_localization_certify import _base_result, _write_artifact

        result = _base_result(case, snapshot, "Codex certification runner")
        command = f"python -B static-audit {case['id']}"
        report_kind = (
            "doctor-report"
            if case["id"] == "fpc-localization-doctor"
            else "localization-report"
        )
        result.update(
            {
                "verdict": "PASS",
                "evidence_label": "Verified",
                "command": command,
                "exit_code": 0,
                "reason": None,
                "artifacts": [
                    {
                        "kind": "project-snapshot",
                        "path": "project-snapshot.json",
                        "sha256": hashlib.sha256(
                            (output_root / "project-snapshot.json").read_bytes()
                        ).hexdigest(),
                    },
                    _write_artifact(
                        output_root,
                        f"{case['id']}/command-log.json",
                        json.dumps(
                            {
                                "command": command,
                                "exit_code": 0,
                                "runtime_target": "Codex App/CLI",
                                "stdout": "static audit passed",
                                "stderr": "",
                                "captured_at": snapshot["captured_at"],
                            }
                        )
                        + "\n",
                        "command-log",
                    ),
                    _write_artifact(
                        output_root,
                        f"{case['id']}/{report_kind}.txt",
                        "Verified static localization audit output.\n",
                        report_kind,
                    ),
                    _write_artifact(
                        output_root,
                        f"{case['id']}/verdict.json",
                        json.dumps({"verdict": "PASS", "reason": None}) + "\n",
                        "verdict",
                    ),
                ],
            }
        )
        return result

    def _write_runtime_bundle(
        self,
        root: Path,
        snapshot: dict[str, object],
    ) -> Path:
        timestamp = str(snapshot["captured_at"])
        project_snapshot = self._project_snapshot(snapshot)
        case_root = root / RUNTIME_CASE
        case_root.mkdir(parents=True, exist_ok=True)
        command = "unity-mcp certify fpc-editor-8080"
        common = {
            "schema_version": 1,
            "case_id": RUNTIME_CASE,
            "profile": PROFILE,
            "runtime_target": "Codex App/CLI",
            "editor_instance_id": "fpc-editor-8080",
            "source_snapshot": project_snapshot,
            "timestamp": timestamp,
        }

        payloads: dict[str, object] = {
            "project-snapshot": snapshot,
            "command-log": {
                "command": command,
                "exit_code": 0,
                "runtime_target": "Codex App/CLI",
                "stdout": "Unity MCP runtime certification completed.",
                "stderr": "",
                "captured_at": timestamp,
                "case_id": RUNTIME_CASE,
                "profile": PROFILE,
                "source_snapshot": project_snapshot,
                "editor_instance_id": "fpc-editor-8080",
            },
            "runtime-audit": {
                **common,
                "kind": "runtime-audit",
                "workflow": "unity-localization-runtime-verification",
                "command": command,
                "runner_capabilities": ["file-audit", "unity-mcp", "play-mode"],
                "status": "PASS",
                "checks": {
                    "unity_mcp_connected": True,
                    "editor_ready": True,
                    "editmode_passed": True,
                    "playmode_passed": True,
                    "console_clean": True,
                    "assertions_passed": True,
                },
                "screenshot_available": False,
                "screenshot_unavailable_reason": (
                    "The connected Unity relay did not expose a usable frame capture endpoint."
                ),
                "artifact_manifest": [],
            },
            "mcp-transcript": {
                **common,
                "kind": "mcp-transcript",
                "tool_calls": [],
            },
            "editor-state": {
                **common,
                "kind": "editor-state",
                "ready": True,
                "compiling": False,
                "compile_errors": 0,
            },
            "editmode-result": {
                **common,
                "kind": "editmode-result",
                "status": "PASS",
                "tests": 4,
                "failures": 0,
            },
            "playmode-result": {
                **common,
                "kind": "playmode-result",
                "status": "PASS",
                "tests": 2,
                "failures": 0,
            },
            "console-report": {
                **common,
                "kind": "console-report",
                "errors": 0,
                "warnings": 0,
            },
            "runtime-assertion": {
                **common,
                "kind": "runtime-assertion",
                "status": "PASS",
                "assertions": [
                    {
                        "name": "update_prefab_text_is_english",
                        "passed": True,
                        "observed": "The active update prefab rendered the expected English copy.",
                    },
                    {
                        "name": "update_prefab_uses_horizontal_overflow_protection",
                        "passed": True,
                        "observed": (
                            "The English label uses HorizontalWrapMode.Overflow so the fixed "
                            "target is not horizontally truncated."
                        ),
                    },
                ],
            },
            "verdict": {"verdict": "PASS", "reason": None},
        }

        refs: dict[str, dict[str, str]] = {}
        for kind, payload in payloads.items():
            path = case_root / f"{kind}.json"
            self._write_json(path, payload)
            refs[kind] = self._artifact_ref(root, path, kind)

        transcript_path = root / refs["mcp-transcript"]["path"]
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        call_specs = [
            ("mcp-1", "read_mcp_resource", "mcpforunity://editor/state", "editor-state", None),
            ("mcp-2", "run_tests", "EditMode", "editmode-result", "edit-job-1"),
            ("mcp-3", "get_test_job", "EditMode", "editmode-result", "edit-job-1"),
            ("mcp-4", "run_tests", "PlayMode", "playmode-result", "play-job-1"),
            ("mcp-5", "get_test_job", "PlayMode", "playmode-result", "play-job-1"),
            ("mcp-6", "read_console", "get", "console-report", None),
            ("mcp-7", "execute_code", "execute", "runtime-assertion", None),
        ]
        transcript["tool_calls"] = [
            {
                "call_id": call_id,
                "tool": tool,
                "operation": operation,
                "status": "PASS",
                "case_id": RUNTIME_CASE,
                "editor_instance_id": "fpc-editor-8080",
                "source_snapshot": project_snapshot,
                "artifact_kind": artifact_kind,
                "artifact_path": refs[artifact_kind]["path"],
                "artifact_sha256": refs[artifact_kind]["sha256"],
                "job_id": job_id,
            }
            for call_id, tool, operation, artifact_kind, job_id in call_specs
        ]
        self._write_json(transcript_path, transcript)
        refs["mcp-transcript"] = self._artifact_ref(root, transcript_path, "mcp-transcript")

        audit_path = root / refs["runtime-audit"]["path"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["artifact_manifest"] = [
            refs[kind]
            for kind in (
                "command-log",
                "project-snapshot",
                "mcp-transcript",
                "editor-state",
                "editmode-result",
                "playmode-result",
                "console-report",
                "runtime-assertion",
            )
        ]
        self._write_json(audit_path, audit)
        refs["runtime-audit"] = self._artifact_ref(root, audit_path, "runtime-audit")

        manifest_path = root / "runtime-evidence-manifest.json"
        self._write_json(
            manifest_path,
            {
                "schema_version": 1,
                "case_id": RUNTIME_CASE,
                "profile": PROFILE,
                "workflow": "unity-localization-runtime-verification",
                "runtime_target": "Codex App/CLI",
                "command": command,
                "exit_code": 0,
                "reviewer": "Unity Runtime Reviewer",
                "timestamp": timestamp,
                "unauthorized_write": False,
                "restore": "Read-only Unity MCP certification; no project mutation performed",
                "project_snapshot": project_snapshot,
                "artifacts": list(refs.values()),
            },
        )
        return manifest_path

    def test_snapshot_digest_is_deterministic_for_same_scope(self) -> None:
        from scripts.fpc_localization_certify import scope_manifest_digest

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "client").mkdir()
            source = root / "client" / "sample.txt"
            source.write_text("English\n", encoding="utf-8")

            first = scope_manifest_digest(root, ["client"])
            second = scope_manifest_digest(root, ["client"])

        self.assertEqual(first, second)
        self.assertEqual(64, len(first))

    def test_boolean_mcp_availability_without_bundle_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=None,
                    mcp_available=True,
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("BLOCKED", runtime["verdict"])
        self.assertEqual("BLOCKED", runtime["evidence_label"])
        self.assertIn("deprecated", runtime["reason"])
        self.assertIn("runtime evidence", runtime["reason"])

    def test_valid_runtime_bundle_passes_strict_offline_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            evidence = Path(temp) / "runtime-source"
            self._write_runtime_bundle(evidence, snapshot)
            output = Path(temp) / "evidence"
            from scripts.fpc_localization_certify import certify
            from scripts.dogfood_eval import evaluate_results

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=output,
                    runtime_evidence=evidence,
                )
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            runtime = next(item for item in payload["results"] if item["id"] == RUNTIME_CASE)
            report = evaluate_results(
                Path(__file__).resolve().parents[2],
                result_path,
                artifact_root=output,
                profile=PROFILE,
            )

        self.assertEqual("PASS", runtime["verdict"])
        self.assertEqual("Verified", runtime["evidence_label"])
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual(3, report["passed"])

    def test_malformed_runtime_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            manifest = Path(temp) / "runtime-evidence-manifest.json"
            manifest.write_text("{not-json", encoding="utf-8")
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=manifest,
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("FAIL", runtime["verdict"])
        self.assertIn("UTF-8 JSON object", runtime["reason"])

    def test_missing_runtime_manifest_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=Path(temp) / "missing-runtime-evidence",
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("BLOCKED", runtime["verdict"])
        self.assertIn("runtime evidence manifest", runtime["reason"])

    def test_runtime_artifact_hash_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            evidence = Path(temp) / "runtime-source"
            manifest = self._write_runtime_bundle(evidence, snapshot)
            editor_state = evidence / RUNTIME_CASE / "editor-state.json"
            editor_state.write_text(editor_state.read_text(encoding="utf-8") + " ", encoding="utf-8")
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=manifest,
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("FAIL", runtime["verdict"])
        self.assertIn("sha256 mismatch", runtime["reason"])

    def test_runtime_project_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            evidence = Path(temp) / "runtime-source"
            manifest = self._write_runtime_bundle(evidence, snapshot)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["project_snapshot"] = "OtherProject@abc1234+dirty:000000000000"
            self._write_json(manifest, payload)
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=manifest,
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("FAIL", runtime["verdict"])
        self.assertIn("does not match current project snapshot", runtime["reason"])

    def test_runtime_bundle_survives_unrelated_dirty_state_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            evidence_snapshot = self._snapshot(project, timestamp)
            current_snapshot = dict(evidence_snapshot)
            current_snapshot["dirty_digest"] = "2" * 64
            evidence = Path(temp) / "runtime-source"
            manifest = self._write_runtime_bundle(evidence, evidence_snapshot)
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=current_snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=manifest,
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("PASS", runtime["verdict"])
        self.assertEqual(self._project_snapshot(evidence_snapshot), runtime["project_snapshot"])

    def test_runtime_bundle_rejects_head_or_scope_drift(self) -> None:
        drift_cases = {
            "repository": "OtherProject",
            "head": "def5678",
            "scope_paths": ["client/LineRWebGL/Assets/Game/RunTimeRes"],
            "scope_digest": "3" * 64,
        }
        for field, value in drift_cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                project = Path(temp) / "FlyingPhoenixChronicles"
                project.mkdir()
                timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
                evidence_snapshot = self._snapshot(project, timestamp)
                current_snapshot = dict(evidence_snapshot)
                current_snapshot[field] = value
                evidence = Path(temp) / "runtime-source"
                manifest = self._write_runtime_bundle(evidence, evidence_snapshot)
                from scripts.fpc_localization_certify import certify

                with mock.patch(
                    "scripts.fpc_localization_certify.snapshot_project",
                    return_value=current_snapshot,
                ), mock.patch(
                    "scripts.fpc_localization_certify.run_static_case",
                    side_effect=self._write_static_result,
                ):
                    result_path = certify(
                        project,
                        profile=PROFILE,
                        output_root=Path(temp) / "evidence",
                        runtime_evidence=manifest,
                    )
                results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
                runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

                self.assertEqual("FAIL", runtime["verdict"])
                self.assertIn(field, runtime["reason"])

    def test_runtime_project_snapshot_requires_canonical_repository_path(self) -> None:
        from scripts.fpc_localization_certify import (
            RuntimeEvidenceInvalid,
            _validate_runtime_project_snapshot,
        )

        invalid_paths = {
            "missing": None,
            "non-string": 42,
            "relative": "FlyingPhoenixChronicles",
        }
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            current_snapshot = self._snapshot(project, timestamp)
            snapshot_path = Path(temp) / "project-snapshot.json"
            for label, repository_path in invalid_paths.items():
                with self.subTest(label=label):
                    evidence_snapshot = dict(current_snapshot)
                    if repository_path is None:
                        evidence_snapshot.pop("repository_path")
                    else:
                        evidence_snapshot["repository_path"] = repository_path
                    self._write_json(snapshot_path, evidence_snapshot)
                    artifacts = {
                        "project-snapshot": (
                            {
                                "kind": "project-snapshot",
                                "path": snapshot_path.name,
                                "sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                            },
                            snapshot_path,
                        )
                    }
                    manifest = {
                        "project_snapshot": self._project_snapshot(evidence_snapshot),
                    }

                    with self.assertRaisesRegex(
                        RuntimeEvidenceInvalid,
                        "repository_path must be a canonical absolute path",
                    ):
                        _validate_runtime_project_snapshot(
                            Path(temp),
                            artifacts,
                            manifest,
                            current_snapshot,
                        )

    def test_transcript_without_completed_playmode_job_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "FlyingPhoenixChronicles"
            project.mkdir()
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            snapshot = self._snapshot(project, timestamp)
            evidence = Path(temp) / "runtime-source"
            manifest = self._write_runtime_bundle(evidence, snapshot)
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            refs = {item["kind"]: item for item in manifest_payload["artifacts"]}
            transcript_path = evidence / refs["mcp-transcript"]["path"]
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            transcript["tool_calls"] = [
                call
                for call in transcript["tool_calls"]
                if not (call["tool"] == "get_test_job" and call["operation"] == "PlayMode")
            ]
            self._write_json(transcript_path, transcript)
            refs["mcp-transcript"]["sha256"] = hashlib.sha256(
                transcript_path.read_bytes()
            ).hexdigest()
            audit_path = evidence / refs["runtime-audit"]["path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            for artifact in audit["artifact_manifest"]:
                if artifact["kind"] == "mcp-transcript":
                    artifact["sha256"] = refs["mcp-transcript"]["sha256"]
            self._write_json(audit_path, audit)
            refs["runtime-audit"]["sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
            self._write_json(manifest, manifest_payload)
            from scripts.fpc_localization_certify import certify

            with mock.patch(
                "scripts.fpc_localization_certify.snapshot_project",
                return_value=snapshot,
            ), mock.patch(
                "scripts.fpc_localization_certify.run_static_case",
                side_effect=self._write_static_result,
            ):
                result_path = certify(
                    project,
                    profile=PROFILE,
                    output_root=Path(temp) / "evidence",
                    runtime_evidence=manifest,
                )
            results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
            runtime = next(item for item in results if item["id"] == RUNTIME_CASE)

        self.assertEqual("BLOCKED", runtime["verdict"])
        self.assertIn("get_test_job/playmode", runtime["reason"])

    def test_hash_manifest_uses_sha256(self) -> None:
        from scripts.fpc_localization_certify import _sha256_file

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.txt"
            path.write_text("report", encoding="utf-8")
            expected = hashlib.sha256(b"report").hexdigest()
            self.assertEqual(expected, _sha256_file(path))


if __name__ == "__main__":
    unittest.main()
