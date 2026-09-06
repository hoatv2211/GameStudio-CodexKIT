from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

from tests._meta.support import temporary_directory


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registry" / "code-intelligence-providers.yaml"


class CodeIntelligenceRegistryTests(unittest.TestCase):
    def test_provider_registry_is_capability_driven_and_ordered(self) -> None:
        from scripts.code_intelligence import load_provider_descriptors

        providers = load_provider_descriptors(REGISTRY)
        expected = (
            (
                "graphify",
                "Graphify",
                "experimental-default",
                "experimental",
                10,
                True,
                False,
                ("context", "dependency-path", "impact"),
                (
                    "No automatic install, extraction, refresh, query, hook, daemon, or cleanup.",
                    "Generated, dynamic, cross-language, and cross-repository coverage is not established.",
                    "Project-local cache isolation is not established by current dogfood.",
                ),
                "graphify-labs-graphify",
            ),
            (
                "gitnexus",
                "GitNexus",
                "advanced-optional",
                "experimental",
                20,
                True,
                True,
                ("context", "dependency-path", "impact", "cross-repo", "pdg", "taint"),
                (
                    "Capability and license suitability require explicit verification before use.",
                    "No deep integration exists before governed dogfood.",
                ),
                "abhigyanpatwari-gitnexus",
            ),
            (
                "understand-anything",
                "Understand Anything",
                "onboarding-optional",
                "experimental",
                30,
                True,
                False,
                ("architecture", "domain-flow", "onboarding"),
                (
                    "Structural extraction and LLM-semantic descriptions require separate evidence labels.",
                    "No deep integration exists before governed dogfood.",
                ),
                "egonex-ai-understand-anything",
            ),
            (
                "codegraph",
                "CodeGraph",
                "legacy-compatible",
                "experimental",
                40,
                True,
                False,
                ("status", "context", "dependency-path", "impact"),
                (
                    "Existing ownership, preference, and install approval behavior remains authoritative.",
                ),
                None,
            ),
        )
        actual = tuple(
            (
                provider.id,
                provider.display_name,
                provider.role,
                provider.maturity,
                provider.priority,
                provider.opt_in_required,
                provider.terms_review_required,
                provider.capabilities,
                provider.limitations,
                provider.upstream_source,
            )
            for provider in providers
        )
        self.assertEqual(
            expected,
            actual,
        )

    def test_registry_rejects_duplicate_ids_capabilities_and_unknown_keys(self) -> None:
        from scripts.code_intelligence import load_provider_descriptors

        invalid_documents = (
            """schema_version: 1
providers:
- id: graphify
  display_name: Graphify
  role: experimental-default
  maturity: experimental
  priority: 10
  opt_in_required: true
  terms_review_required: false
  capabilities: [impact]
  limitations: []
  upstream_source: graphify-labs-graphify
- id: graphify
  display_name: Duplicate
  role: advanced-optional
  maturity: experimental
  priority: 20
  opt_in_required: true
  terms_review_required: false
  capabilities: [impact]
  limitations: []
  upstream_source: graphify-labs-graphify
""",
            """schema_version: 1
providers:
- id: graphify
  display_name: Graphify
  role: experimental-default
  maturity: experimental
  priority: 10
  opt_in_required: true
  terms_review_required: false
  capabilities: [impact, impact]
  limitations: []
  upstream_source: graphify-labs-graphify
""",
            """schema_version: 1
providers:
- id: graphify
  display_name: Graphify
  role: experimental-default
  maturity: experimental
  priority: 10
  opt_in_required: true
  terms_review_required: false
  capabilities: [impact]
  limitations: []
  upstream_source: graphify-labs-graphify
  executable_argv: [graphify, extract]
""",
        )
        with temporary_directory() as temp:
            path = Path(temp) / "providers.yaml"
            for document in invalid_documents:
                with self.subTest(document=document):
                    path.write_text(document, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_provider_descriptors(path)


class CodeIntelligenceModelTests(unittest.TestCase):
    def test_legacy_states_map_to_canonical_states(self) -> None:
        from scripts.code_intelligence import normalize_index_state

        expected = {
            "INITIALIZED_HEALTHY": "FRESH",
            "AVAILABLE_NOT_INITIALIZED": "NOT_INITIALIZED",
            "INITIALIZED_STALE": "STALE_HEAD",
            "INITIALIZED_BROKEN": "BROKEN",
            "UNSUPPORTED_LANGUAGE": "PARTIAL_LANGUAGE",
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(target, normalize_index_state(source))

    def test_unknown_state_is_broken_not_fresh(self) -> None:
        from scripts.code_intelligence import normalize_index_state

        self.assertEqual("BROKEN", normalize_index_state("provider-new-state"))

    def test_descriptor_lookup_rejects_unknown_provider(self) -> None:
        from scripts.code_intelligence import get_provider_descriptor

        with self.assertRaisesRegex(ValueError, "unsupported code-intelligence provider"):
            get_provider_descriptor("missing-provider", registry_path=REGISTRY)


class CodeIntelligenceSemanticProducerTests(unittest.TestCase):
    @staticmethod
    def _manifest(**overrides: object) -> dict[str, object]:
        manifest: dict[str, object] = {
            "provider": "graphify",
            "provider_version": "0.9.50",
            "repository": "repo://game",
            "revision": "abc",
            "worktree_identity": "sha256:one",
            "capabilities": ["context", "dependency-path", "impact"],
            "languages": ["csharp", "lua"],
            "artifact_paths": ["evidence/graph.json"],
            "artifacts_validated": True,
        }
        manifest.update(overrides)
        return manifest

    def test_semantic_language_coverage_constraint_never_emits_fresh(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        identity = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            identity,
            provider="graphify",
            manifest=self._manifest(languages=["csharp"]),
            required_capability="impact",
            required_languages=("csharp", "lua"),
            registry_path=REGISTRY,
        )

        self.assertNotEqual("FRESH", status.index_state)
        self.assertEqual("PARTIAL_LANGUAGE", status.index_state)
        self.assertEqual(("lua",), status.missing_languages)

    def test_semantic_index_identity_mismatch_constraint_never_emits_fresh(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        identity = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        for field, value, expected in (
            ("revision", "old", "STALE_HEAD"),
            ("worktree_identity", "sha256:old", "STALE_WORKTREE"),
        ):
            with self.subTest(field=field):
                status = inspect_provider(
                    identity,
                    provider="graphify",
                    manifest=self._manifest(**{field: value}),
                    required_capability="impact",
                    required_languages=("csharp",),
                    registry_path=REGISTRY,
                )

                self.assertNotEqual("FRESH", status.index_state)
                self.assertEqual(expected, status.index_state)


class GitTextRunnerTests(unittest.TestCase):
    def test_default_runner_uses_exact_safe_subprocess_contract(self) -> None:
        from unittest import mock

        from scripts.code_intelligence import _default_git_text_runner

        completed = mock.Mock(returncode=0, stdout="git output\n", stderr="")
        root = Path("D:/game")
        with mock.patch(
            "scripts.code_intelligence.subprocess.run",
            return_value=completed,
        ) as run:
            output = _default_git_text_runner(
                ["status", "--porcelain=v1"],
                cwd=root,
            )

        self.assertEqual("git output\n", output)
        run.assert_called_once_with(
            ["git", "status", "--porcelain=v1"],
            cwd=root,
            shell=False,
            check=False,
            text=True,
            capture_output=True,
        )

    def test_default_runner_nonzero_exit_raises_value_error_with_context(self) -> None:
        from unittest import mock

        from scripts.code_intelligence import _default_git_text_runner

        completed = mock.Mock(
            returncode=7,
            stdout="",
            stderr="safe git failure",
        )
        with mock.patch(
            "scripts.code_intelligence.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaisesRegex(ValueError, "return code 7") as raised:
                _default_git_text_runner(["rev-parse", "HEAD"], cwd=Path("D:/game"))

        self.assertIn("safe git failure", str(raised.exception))

    def test_default_runner_oserror_is_captured_as_incomplete_identity(self) -> None:
        from unittest import mock

        from scripts.code_intelligence import capture_repository_identity

        with mock.patch(
            "scripts.code_intelligence.subprocess.run",
            side_effect=OSError("git unavailable"),
        ) as run:
            identity = capture_repository_identity(Path("D:/game"))

        self.assertFalse(identity.complete)
        self.assertIsNone(identity.revision)
        self.assertIsNone(identity.worktree_identity)
        self.assertIn("repository identity unavailable", " ".join(identity.limitations))
        run.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path("D:/game").resolve(),
            shell=False,
            check=False,
            text=True,
            capture_output=True,
        )


class CodeIntelligenceStatusTests(unittest.TestCase):
    @staticmethod
    def _manifest(**overrides: object) -> dict[str, object]:
        manifest: dict[str, object] = {
            "provider": "graphify",
            "provider_version": "0.9.50",
            "repository": "repo://game",
            "revision": "abc",
            "worktree_identity": "sha256:one",
            "capabilities": ["context", "dependency-path", "impact"],
            "languages": ["csharp", "lua"],
            "artifact_paths": ["evidence/graph.json"],
            "artifacts_validated": True,
        }
        manifest.update(overrides)
        return manifest

    def test_probe_requires_revision_worktree_capability_and_languages(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        manifest = self._manifest()

        fresh = inspect_provider(
            current,
            provider="graphify",
            manifest=manifest,
            required_capability="impact",
            required_languages=("csharp", "lua"),
            registry_path=REGISTRY,
        )
        self.assertEqual("FRESH", fresh.index_state)

        stale_head = inspect_provider(
            current,
            provider="graphify",
            manifest={**manifest, "revision": "old"},
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
        )
        self.assertEqual("STALE_HEAD", stale_head.index_state)

        stale_worktree = inspect_provider(
            current,
            provider="graphify",
            manifest={**manifest, "worktree_identity": "sha256:old"},
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
        )
        self.assertEqual("STALE_WORKTREE", stale_worktree.index_state)

        partial = inspect_provider(
            current,
            provider="graphify",
            manifest=manifest,
            required_capability="impact",
            required_languages=("cpp", "lua"),
            registry_path=REGISTRY,
        )
        self.assertEqual("PARTIAL_LANGUAGE", partial.index_state)
        self.assertEqual(("cpp",), partial.missing_languages)

        mismatch = inspect_provider(
            current,
            provider="graphify",
            manifest=manifest,
            required_capability="taint",
            required_languages=("csharp",),
            registry_path=REGISTRY,
        )
        self.assertEqual("BROKEN", mismatch.index_state)
        self.assertIn("capability mismatch: taint", mismatch.limitations)

    def test_probe_detects_exact_provider_side_effects(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        before = RepositoryIdentity("repo://game", "abc", "sha256:before", True)
        after = RepositoryIdentity("repo://game", "abc", "sha256:after", True)
        status = inspect_provider(
            before,
            provider="graphify",
            manifest=None,
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
            after_identity=after,
            observed_side_effects=("graphify-out/cache/stat-index.json",),
        )
        self.assertEqual("SIDE_EFFECT_VIOLATION", status.index_state)
        self.assertEqual(
            ("graphify-out/cache/stat-index.json",),
            status.side_effects,
        )

    def test_artifact_without_manifest_is_never_fresh(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            current,
            provider="graphify",
            manifest=None,
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
            discovered_artifacts=("graphify-out/graph.json",),
        )
        self.assertEqual("STALE_HEAD", status.index_state)

    def test_required_language_tokens_are_normalized_deterministically(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            current,
            provider="graphify",
            manifest=self._manifest(languages=[" CSharp ", "LUA"]),
            required_capability="impact",
            required_languages=(" CSharp ", "lua "),
            registry_path=REGISTRY,
        )
        self.assertEqual("FRESH", status.index_state)
        self.assertEqual(("csharp", "lua"), status.required_languages)
        self.assertEqual(("csharp", "lua"), status.supported_languages)

    def test_required_language_tokens_reject_malformed_values(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        for required_languages in (
            (None,),
            ("   ",),
            (1,),
            ("csharp", None),
        ):
            with self.subTest(required_languages=required_languages):
                with self.assertRaisesRegex(ValueError, "required_languages"):
                    inspect_provider(
                        current,
                        provider="graphify",
                        manifest=self._manifest(),
                        required_capability="impact",
                        required_languages=required_languages,
                        registry_path=REGISTRY,
                    )

    def test_manifest_rejects_casefolded_duplicate_languages(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            current,
            provider="graphify",
            manifest=self._manifest(languages=[" CSharp ", "csharp"]),
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
        )
        self.assertEqual("BROKEN", status.index_state)
        self.assertIn("provider index manifest languages is invalid", status.limitations)

    def test_manifest_rejects_unknown_capability(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            current,
            provider="graphify",
            manifest=self._manifest(
                capabilities=["context", "dependency-path", "impact", "root-access"]
            ),
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
        )
        self.assertEqual("BROKEN", status.index_state)
        self.assertIn("provider index manifest capabilities is invalid", status.limitations)

    def test_manifest_capabilities_must_be_subset_of_provider_descriptor(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            current,
            provider="graphify",
            manifest=self._manifest(
                capabilities=["context", "dependency-path", "impact", "taint"]
            ),
            required_capability=None,
            required_languages=("csharp",),
            registry_path=REGISTRY,
        )
        self.assertEqual("BROKEN", status.index_state)
        self.assertIn(
            "provider manifest capabilities unsupported by graphify: taint",
            status.limitations,
        )

    def test_observed_side_effects_override_user_disabled_state(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        status = inspect_provider(
            current,
            provider="graphify",
            manifest=None,
            required_capability="impact",
            required_languages=("csharp",),
            registry_path=REGISTRY,
            observed_side_effects=("graphify-out/cache/stat-index.json",),
            user_disabled=True,
        )
        self.assertEqual("SIDE_EFFECT_VIOLATION", status.index_state)
        self.assertEqual(
            ("graphify-out/cache/stat-index.json",),
            status.side_effects,
        )

    def test_capture_identity_hashes_git_snapshot_without_writing(self) -> None:
        from hashlib import sha256

        from scripts.code_intelligence import capture_repository_identity

        calls: list[tuple[str, ...]] = []
        outputs = {
            ("rev-parse", "--show-toplevel"): "D:/game\n",
            ("rev-parse", "HEAD"): "abc123\n",
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"): " M server/a.cpp\0",
            ("diff", "--binary"): "diff --git a/server/a.cpp b/server/a.cpp\n",
            ("diff", "--binary", "--cached"): "",
        }

        def runner(args: list[str], *, cwd: Path) -> str:
            calls.append(tuple(args))
            return outputs[tuple(args)]

        identity = capture_repository_identity(Path("D:/game"), runner=runner)
        expected_calls = [
            ("rev-parse", "--show-toplevel"),
            ("rev-parse", "HEAD"),
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
            ("diff", "--binary"),
            ("diff", "--binary", "--cached"),
        ]
        digest = sha256()
        for value in (
            "D:/game",
            "abc123",
            " M server/a.cpp\0",
            "diff --git a/server/a.cpp b/server/a.cpp\n",
            "",
        ):
            encoded = value.encode("utf-8", errors="surrogateescape")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)

        self.assertEqual("D:/game", identity.repository)
        self.assertEqual("abc123", identity.revision)
        self.assertEqual(f"sha256:{digest.hexdigest()}", identity.worktree_identity)
        self.assertTrue(identity.complete)
        self.assertEqual(expected_calls, calls)

    def test_git_repository_identity_preserves_foreign_absolute_path_syntax(self) -> None:
        from unittest import mock

        from scripts.code_intelligence import _normalize_git_repository_path

        with mock.patch("scripts.code_intelligence.os.name", "posix"):
            self.assertEqual("D:/game", _normalize_git_repository_path("D:/game"))
            self.assertEqual("D:/game", _normalize_git_repository_path(r"D:\game"))
        self.assertEqual("/srv/game", _normalize_git_repository_path("/srv/game"))

    def test_untracked_worktree_requires_privacy_safe_content_identity(self) -> None:
        from inspect import signature
        from unittest import mock

        from scripts.code_intelligence import capture_repository_identity

        self.assertIn(
            "untracked_content_identity",
            signature(capture_repository_identity).parameters,
        )
        outputs = {
            ("rev-parse", "--show-toplevel"): "D:/game\n",
            ("rev-parse", "HEAD"): "abc123\n",
            (
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ): "?? Assets/NewFeature.cs\0",
            ("diff", "--binary"): "",
            ("diff", "--binary", "--cached"): "",
        }

        def runner(args: list[str], *, cwd: Path) -> str:
            return outputs[tuple(args)]

        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("untracked contents must not be read"),
        ):
            before = capture_repository_identity(Path("D:/game"), runner=runner)
            same_path_changed_bytes = capture_repository_identity(
                Path("D:/game"),
                runner=runner,
            )
            supplied_before = capture_repository_identity(
                Path("D:/game"),
                runner=runner,
                untracked_content_identity=f"sha256:{'a' * 64}",
            )
            supplied_after = capture_repository_identity(
                Path("D:/game"),
                runner=runner,
                untracked_content_identity=f"sha256:{'b' * 64}",
            )
            unsafe_identity = capture_repository_identity(
                Path("D:/game"),
                runner=runner,
                untracked_content_identity="raw untracked contents",
            )

        self.assertFalse(before.complete)
        self.assertFalse(same_path_changed_bytes.complete)
        self.assertEqual(before.worktree_identity, same_path_changed_bytes.worktree_identity)
        self.assertIn("untracked", " ".join(before.limitations).casefold())
        self.assertTrue(supplied_before.complete)
        self.assertTrue(supplied_after.complete)
        self.assertNotEqual(
            supplied_before.worktree_identity,
            supplied_after.worktree_identity,
        )
        self.assertFalse(unsafe_identity.complete)

    def test_capture_identity_failure_is_incomplete_without_file_access(self) -> None:
        from scripts.code_intelligence import capture_repository_identity

        expected_repository = Path("D:/game").resolve().as_posix()
        for error in (OSError("git unavailable"), ValueError("git failed")):
            with self.subTest(error=type(error).__name__):
                calls: list[tuple[str, ...]] = []

                def runner(args: list[str], *, cwd: Path) -> str:
                    calls.append(tuple(args))
                    raise error

                identity = capture_repository_identity(Path("D:/game"), runner=runner)
                self.assertEqual(expected_repository, identity.repository)
                self.assertFalse(identity.complete)
                self.assertIsNone(identity.revision)
                self.assertIsNone(identity.worktree_identity)
                self.assertIn(
                    "repository identity unavailable",
                    " ".join(identity.limitations),
                )
                self.assertEqual(1, len(calls))

    def test_capture_identity_resolution_failure_returns_incomplete_identity(self) -> None:
        from unittest import mock

        from scripts.code_intelligence import capture_repository_identity

        runner = mock.Mock(side_effect=AssertionError("runner must not be called"))
        with mock.patch.object(
            Path,
            "resolve",
            side_effect=OSError("path resolution unavailable"),
        ):
            identity = capture_repository_identity(Path("D:/game"), runner=runner)

        self.assertFalse(identity.complete)
        self.assertIsNone(identity.revision)
        self.assertIsNone(identity.worktree_identity)
        self.assertIn("repository identity unavailable", " ".join(identity.limitations))
        runner.assert_not_called()

    def test_capture_identity_reported_repository_resolution_failure_is_incomplete(self) -> None:
        from unittest import mock

        from scripts.code_intelligence import capture_repository_identity

        reported_repository = Path.cwd().as_posix()
        outputs = {
            ("rev-parse", "--show-toplevel"): f"{reported_repository}\n",
            ("rev-parse", "HEAD"): "abc123\n",
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"): "",
            ("diff", "--binary"): "",
            ("diff", "--binary", "--cached"): "",
        }

        def runner(args: list[str], *, cwd: Path) -> str:
            return outputs[tuple(args)]

        for error in (
            OSError("reported repository resolution unavailable"),
            ValueError("reported repository path invalid"),
        ):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(
                    Path,
                    "resolve",
                    side_effect=(Path("D:/game"), error),
                ):
                    identity = capture_repository_identity(
                        Path("D:/game"),
                        runner=runner,
                    )

                self.assertFalse(identity.complete)
                self.assertIsNone(identity.revision)
                self.assertIsNone(identity.worktree_identity)
                self.assertIn(
                    "repository identity unavailable",
                    " ".join(identity.limitations),
                )


class CodeIntelligenceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_path = ROOT / "evals" / "schema" / "code-intelligence-evidence.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.schema = schema
        cls.validator = Draft202012Validator(schema)

    @staticmethod
    def fresh_status():
        from scripts.code_intelligence import CodeIntelligenceStatus

        return CodeIntelligenceStatus(
            provider="graphify",
            provider_version="0.9.50",
            repository="repo://game",
            revision="abc",
            worktree_identity="sha256:one",
            index_revision="abc",
            index_worktree_identity="sha256:one",
            index_state="FRESH",
            capabilities=("context", "dependency-path", "impact"),
            required_languages=("csharp",),
            supported_languages=("csharp",),
            missing_languages=(),
            artifact_paths=("evidence/graph.json",),
            side_effects=(),
            limitations=(),
        )

    @staticmethod
    def extracted_edge(**overrides: object) -> dict[str, object]:
        edge: dict[str, object] = {
            "relation": "CALLS",
            "source": "Bar",
            "target": "Foo",
            "source_locator": "src/bar.cpp:20",
            "origin": "ast",
            "confidence": "EXTRACTED",
        }
        edge.update(overrides)
        return edge

    def normalize(self, **overrides: object) -> dict[str, object]:
        from scripts.code_intelligence import normalize_evidence

        arguments: dict[str, object] = {
            "status": self.fresh_status(),
            "capability": "impact",
            "query": {"query_id": "impact:Foo", "subjects": ["Foo"]},
            "resolved_subjects": ("Foo@src/foo.cpp:10",),
            "edges": (self.extracted_edge(),),
            "affected_paths": ("src/bar.cpp",),
        }
        arguments.update(overrides)
        result = normalize_evidence(**arguments)
        self.validator.validate(result)
        return result

    def assert_legacy_evidence_is_canonical_blocked(
        self,
        result: dict[str, object],
    ) -> None:
        errors = list(self.validator.iter_errors(result))
        self.assertEqual([], errors, errors[0].message if errors else "")
        self.assertEqual("BROKEN", result["index_state"])
        self.assertEqual("STATUS_BLOCKED", result["query_state"])
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])
        self.assertNotIn("verdict", result)
        self.assertNotIn("edge_kind", result)
        self.assertNotIn("result", result)

    def test_ast_origin_with_inferred_confidence_is_snapshot(self) -> None:
        result = self.normalize(
            edges=(self.extracted_edge(confidence="INFERRED"),),
        )

        self.assertEqual("Snapshot", result["evidence_label"])
        self.assertEqual("UNVERIFIED", result["graph_verdict"])
        self.assertEqual("INFERRED", result["edges"][0]["provenance"])

    def test_extracted_confidence_cannot_override_non_source_origin(self) -> None:
        cases = (
            ("AST", "ast", "SOURCE_EXTRACTED", "Verified", "PASS"),
            (" source ", "source", "SOURCE_EXTRACTED", "Verified", "PASS"),
            (" LLM ", "llm", "LLM", "Snapshot", "UNVERIFIED"),
            ("SEMANTIC", "semantic", "SEMANTIC", "Snapshot", "UNVERIFIED"),
            ("Inferred", "inferred", "INFERRED", "Snapshot", "UNVERIFIED"),
            ("provider-specific", "provider-specific", "UNKNOWN", "Snapshot", "UNVERIFIED"),
        )

        for origin, normalized_origin, provenance, label, verdict in cases:
            with self.subTest(origin=origin):
                result = self.normalize(
                    edges=(self.extracted_edge(origin=origin),),
                )
                self.assertEqual(normalized_origin, result["edges"][0]["origin"])
                self.assertEqual(provenance, result["edges"][0]["provenance"])
                self.assertEqual(label, result["evidence_label"])
                self.assertEqual(verdict, result["graph_verdict"])

    def test_empty_result_preserves_exact_uncertainty(self) -> None:
        result = self.normalize(
            query={"query_id": "impact:Missing", "subjects": ["Missing"]},
            resolved_subjects=(),
            edges=(),
            affected_paths=(),
        )

        self.assertEqual("EMPTY_UNCERTAIN", result["query_state"])
        self.assertEqual("Unverified", result["evidence_label"])
        self.assertEqual("UNVERIFIED", result["graph_verdict"])
        self.assertIn(
            "No graph result is not proof that no dependency exists.",
            result["limitations"],
        )

    def test_extracted_edge_without_resolved_subject_blocks(self) -> None:
        result = self.normalize(
            resolved_subjects=(),
        )

        self.assertEqual("AMBIGUOUS", result["query_state"])
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_extracted_edge_with_multiple_resolved_subjects_blocks(self) -> None:
        result = self.normalize(
            resolved_subjects=("Foo@src/a.cpp:10", "Foo@src/b.cpp:20"),
        )

        self.assertEqual("AMBIGUOUS", result["query_state"])
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_ambiguous_subject_blocks_instead_of_guessing(self) -> None:
        result = self.normalize(
            resolved_subjects=("Foo@src/a.cpp:10", "Foo@src/b.cpp:20"),
            edges=(),
            affected_paths=(),
        )

        self.assertEqual("AMBIGUOUS", result["query_state"])
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_blocked_status_cannot_be_upgraded_by_extracted_edge(self) -> None:
        status = replace(self.fresh_status(), index_state="PARTIAL_LANGUAGE")
        result = self.normalize(status=status)

        self.assertEqual("STATUS_BLOCKED", result["query_state"])
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_declared_fresh_requires_version_and_bound_index_artifact(self) -> None:
        cases = (
            (replace(self.fresh_status(), provider_version=None), "provider version"),
            (replace(self.fresh_status(), artifact_paths=()), "index artifact"),
        )
        for status, limitation in cases:
            with self.subTest(limitation=limitation):
                result = self.normalize(status=status)
                self.assertEqual("BROKEN", result["index_state"])
                self.assertEqual("BLOCKED", result["graph_verdict"])
                self.assertIn(limitation, " ".join(result["limitations"]).casefold())

    def test_language_coverage_is_recomputed_instead_of_trusting_declared_missing(self) -> None:
        status = replace(
            self.fresh_status(),
            required_languages=("lua",),
            supported_languages=("csharp",),
            missing_languages=(),
        )

        result = self.normalize(status=status)

        self.assertEqual(["lua"], result["missing_languages"])
        self.assertEqual("PARTIAL_LANGUAGE", result["index_state"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_side_effects_override_every_other_blocked_state(self) -> None:
        status = replace(
            self.fresh_status(),
            index_state="STALE_HEAD",
            side_effects=("graphify-out/cache/stat-index.json",),
        )

        result = self.normalize(status=status)

        self.assertEqual("SIDE_EFFECT_VIOLATION", result["index_state"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_fresh_status_with_mismatched_index_binding_blocks(self) -> None:
        cases = (
            ({"index_revision": "different"}, "revision identity mismatch"),
            (
                {"index_worktree_identity": "sha256:different"},
                "worktree identity mismatch",
            ),
        )

        for overrides, limitation in cases:
            with self.subTest(overrides=overrides):
                result = self.normalize(
                    status=replace(self.fresh_status(), **overrides),
                )
                self.assertEqual("STATUS_BLOCKED", result["query_state"])
                self.assertEqual("BLOCKED", result["evidence_label"])
                self.assertEqual("BLOCKED", result["graph_verdict"])
                self.assertIn(limitation, " ".join(result["limitations"]).casefold())

    def test_fresh_status_with_null_index_binding_blocks(self) -> None:
        for field in (
            "revision",
            "worktree_identity",
            "index_revision",
            "index_worktree_identity",
        ):
            with self.subTest(field=field):
                result = self.normalize(
                    status=replace(self.fresh_status(), **{field: None}),
                )
                self.assertEqual("STATUS_BLOCKED", result["query_state"])
                self.assertEqual("BLOCKED", result["evidence_label"])
                self.assertEqual("BLOCKED", result["graph_verdict"])
                self.assertIn(
                    "identity is incomplete",
                    " ".join(result["limitations"]).casefold(),
                )

    def test_extracted_result_emits_exact_schema_contract(self) -> None:
        result = self.normalize()

        self.assertEqual(self.schema["required"], list(result))
        self.assertEqual(29, len(result))
        self.assertEqual("Verified", result["evidence_label"])
        self.assertEqual("PASS", result["graph_verdict"])
        self.assertEqual("SOURCE_EXTRACTED", result["edges"][0]["provenance"])
        self.assertIn(
            "Verified applies to source extraction at this snapshot, not runtime behavior or complete recall.",
            result["limitations"],
        )

    def test_disagreement_downgrades_extracted_result(self) -> None:
        result = self.normalize(
            disagreements=("Provider output disagrees with source.",),
        )

        self.assertEqual("Snapshot", result["evidence_label"])
        self.assertEqual("UNVERIFIED", result["graph_verdict"])

    def test_edge_requires_exact_fields(self) -> None:
        unknown = self.extracted_edge(unexpected="value")
        missing = self.extracted_edge()
        del missing["target"]

        for edge in (unknown, missing):
            with self.subTest(edge=edge), self.assertRaises(ValueError):
                self.normalize(edges=(edge,))

    def test_edge_rejects_blank_required_strings(self) -> None:
        for field in ("relation", "source", "target", "source_locator", "origin"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.normalize(edges=(self.extracted_edge(**{field: "   "}),))

    def test_unknown_confidence_normalizes_without_verified_pass(self) -> None:
        result = self.normalize(
            edges=(self.extracted_edge(confidence="provider-specific"),),
        )

        self.assertEqual("UNKNOWN", result["edges"][0]["confidence"])
        self.assertEqual("UNKNOWN", result["edges"][0]["provenance"])
        self.assertNotEqual("Verified", result["evidence_label"])
        self.assertNotEqual("PASS", result["graph_verdict"])

    def test_query_requires_exact_keys_one_subject_and_nonblank_strings(self) -> None:
        invalid_queries = (
            {"query_id": "impact:Foo", "subjects": ["Foo"], "extra": True},
            {"query_id": "impact:Foo"},
            {"query_id": "   ", "subjects": ["Foo"]},
            {"query_id": "impact:Foo", "subjects": []},
            {"query_id": "impact:Foo", "subjects": ["Foo", "Bar"]},
            {"query_id": "impact:Foo", "subjects": ["   "]},
        )

        for query in invalid_queries:
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.normalize(query=query)

    def test_commands_require_exact_fields_nonblank_command_and_integer_or_null_exit(self) -> None:
        invalid_commands = (
            {"command": "provider query", "exit_code": 0, "extra": True},
            {"command": "provider query"},
            {"command": "   ", "exit_code": 0},
            {"command": "provider query", "exit_code": True},
            {"command": "provider query", "exit_code": "0"},
        )

        for command in invalid_commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.normalize(commands=(command,))

        self.assertEqual(
            [
                {"command": "provider status", "exit_code": 0},
                {"command": "provider query", "exit_code": None},
            ],
            self.normalize(
                commands=(
                    {"command": "provider status", "exit_code": 0},
                    {"command": "provider query", "exit_code": None},
                )
            )["commands"],
        )

    def test_next_action_must_be_nonblank(self) -> None:
        for next_action in ("", "   ", None):
            with self.subTest(next_action=next_action), self.assertRaises(ValueError):
                self.normalize(next_action=next_action)

    def test_legacy_fresh_empty_dependency_result_is_canonical_blocked(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        empty_results = (
            {},
            [],
            "",
            None,
            {"affected_paths": []},
            {"resolved_subjects": [], "edges": [], "affected_paths": []},
        )
        for empty_result in empty_results:
            with self.subTest(result=empty_result):
                result = normalize_evidence(
                    provider="graphify",
                    provider_version="0.9.50",
                    repository="repo://game",
                    revision="abc",
                    index_state="FRESH",
                    edge_kind="EXTRACTED",
                    result=empty_result,
                )
                self.assert_legacy_evidence_is_canonical_blocked(result)
                self.assertIn(
                    "No graph result is not proof that no dependency exists.",
                    result["limitations"],
                )

    def test_legacy_declared_fresh_extracted_result_is_canonical_blocked(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        def normalize(result: object) -> dict[str, object]:
            return normalize_evidence(
                provider="graphify",
                provider_version="0.9.50",
                repository="repo://game",
                revision="abc",
                index_state="FRESH",
                edge_kind="EXTRACTED",
                result=result,
            )

        legacy_results = (
            "provider error",
            1,
            True,
            {"results": {"error": "failed"}},
            {"affected_paths": "server/a.cpp"},
            {"edges": {"source": "a"}},
            {
                "resolved_subjects": ["Foo@server/foo.cpp:10"],
                "affected_paths": ["server/a.cpp"],
                "edges": [{"source": "A", "target": "B"}],
            },
        )
        for legacy_result in legacy_results:
            with self.subTest(result=legacy_result):
                self.assert_legacy_evidence_is_canonical_blocked(
                    normalize(legacy_result)
                )

    def test_legacy_dependency_fields_never_bypass_canonical_identity(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        def normalize(result: object) -> dict[str, object]:
            return normalize_evidence(
                provider="graphify",
                provider_version="0.9.50",
                repository="repo://game",
                revision="abc",
                index_state="FRESH",
                edge_kind="EXTRACTED",
                result=result,
            )

        invalid_results = (
            {"affected_paths": [{"path": "server/a.cpp"}]},
            {"resolved_subjects": [{"symbol": "Foo"}]},
            {"paths": [1]},
            {"dependency_paths": [None]},
            {"results": ["provider error"]},
            {"results": [{"error": "failed"}]},
            {"results": [{"results": [{"affected_paths": ["server/a.cpp"]}]}]},
            {"nodes": [{"name": "Node"}]},
            {"symbols": [{"name": "Foo"}]},
            {"dependencies": [{"source": "A", "target": "B"}]},
        )
        for invalid in invalid_results:
            with self.subTest(result=invalid):
                self.assert_legacy_evidence_is_canonical_blocked(normalize(invalid))

        valid_results = (
            {"affected_paths": ["server/a.cpp"]},
            {"resolved_subjects": ["Foo@server/a.cpp:10"]},
            {"edges": [{"source": "A", "target": "B"}]},
            {"results": [{"affected_paths": ["server/a.cpp"]}]},
        )
        for valid in valid_results:
            with self.subTest(result=valid):
                self.assert_legacy_evidence_is_canonical_blocked(normalize(valid))


class CodeIntelligenceHandoffTests(unittest.TestCase):
    @staticmethod
    def impact_evidence(
        *,
        revision: str,
        worktree_identity: str,
        affected_paths: list[str],
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "provider": "graphify",
            "provider_version": "0.9.50",
            "repository": "repo://game",
            "revision": revision,
            "worktree_identity": worktree_identity,
            "index_revision": revision,
            "index_worktree_identity": worktree_identity,
            "index_state": "FRESH",
            "capability": "impact",
            "query": {"query_id": "impact:Foo", "subjects": ["Foo"]},
            "resolved_subjects": ["Foo@src/foo.cpp:10"],
            "required_languages": ["cpp"],
            "supported_languages": ["cpp"],
            "missing_languages": [],
            "affected_paths": affected_paths,
            "generated_boundaries": [],
            "edges": [],
            "query_state": "COMPLETE",
            "evidence_label": "Snapshot",
            "graph_verdict": "UNVERIFIED",
            "source_confirmations": [],
            "test_confirmations": [],
            "side_effects": [],
            "limitations": [],
            "disagreements": [],
            "commands": [],
            "artifacts": ["evidence/local/code-intelligence/impact.json"],
            "next_action": "Confirm against source and tests.",
        }

    def test_compare_impact_exposes_new_unexpected_and_missing_paths(self) -> None:
        from scripts.code_intelligence import compare_impact

        result = compare_impact(
            pre=self.impact_evidence(
                revision="abc",
                worktree_identity="sha256:before",
                affected_paths=["b.cpp", "a.cpp"],
            ),
            post=self.impact_evidence(
                revision="abc",
                worktree_identity="sha256:after",
                affected_paths=["c.cpp", "b.cpp"],
            ),
            changed_paths=("d.cpp", "a.cpp"),
        )

        self.assertEqual("impact:Foo", result["query_id"])
        self.assertEqual(["c.cpp"], result["added_affected_paths"])
        self.assertEqual(["a.cpp"], result["removed_affected_paths"])
        self.assertEqual(["b.cpp"], result["unchanged_affected_paths"])
        self.assertEqual(["d.cpp"], result["changed_not_predicted"])
        self.assertEqual(["a.cpp"], result["changed_no_longer_affected"])

    def test_compare_impact_rejects_identity_free_partial_objects(self) -> None:
        from scripts.code_intelligence import compare_impact

        with self.assertRaisesRegex(ValueError, "canonical"):
            compare_impact(
                pre={
                    "query": {"query_id": "impact:Foo"},
                    "affected_paths": ["a.cpp"],
                },
                post={
                    "query": {"query_id": "impact:Foo"},
                    "affected_paths": ["b.cpp"],
                },
                changed_paths=("b.cpp",),
            )

    def test_compare_impact_requires_fresh_bound_and_distinct_transition(self) -> None:
        from scripts.code_intelligence import compare_impact

        pre = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:before",
            affected_paths=["a.cpp"],
        )
        post = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:after",
            affected_paths=["b.cpp"],
        )
        invalid_posts = (
            {**post, "schema_version": 2},
            {**post, "schema_version": True},
            {**post, "unexpected": True},
            {**post, "affected_paths": ["b.cpp", "b.cpp"]},
            {
                **post,
                "edges": [
                    {
                        "relation": "CALLS",
                        "source": "Bar",
                        "target": "Foo",
                        "source_locator": "src/bar.cpp:20",
                        "origin": "ast",
                        "confidence": "EXTRACTED",
                        "provenance": "LLM",
                    }
                ],
            },
            {
                **post,
                "resolved_subjects": ["Foo@a.cpp:1", "Foo@b.cpp:2"],
            },
            {
                **post,
                "query_state": "AMBIGUOUS",
                "evidence_label": "Verified",
                "graph_verdict": "PASS",
            },
            {
                **post,
                "evidence_label": "BLOCKED",
                "graph_verdict": "PASS",
            },
            {**post, "edges": tuple(post["edges"])},
            {**post, "source_test_fallback": None},
            {**post, "source_test_fallback": {}},
            {
                **post,
                "source_test_fallback": {
                    "decision": "REVIEWER_ACKNOWLEDGED_FALLBACK",
                    "graph_verdict": "BLOCKED",
                    "graph_blocker": "PARTIAL_LANGUAGE: lua",
                    "source_owners": ["server/packet.cpp"],
                    "known_callers": ["PacketRouter::dispatch"],
                    "known_consumers": ["LuaPacketBridge"],
                    "generated_authorities": ["NOT_APPLICABLE"],
                    "test_commands": ["python -B -m unittest tests.packet"],
                    "reviewer": "QA Lead",
                    "residual_risk": "Lua reflection remains outside graph coverage.",
                    "missing_requirements": [],
                },
            },
            {**post, "index_revision": "old"},
            {**post, "index_worktree_identity": "sha256:old"},
            {**post, "index_state": "STALE_HEAD"},
            {**post, "capability": "context"},
            {**post, "provider": "gitnexus"},
            {**post, "repository": "repo://other"},
            {**post, "worktree_identity": "sha256:before", "index_worktree_identity": "sha256:before"},
        )
        for invalid_post in invalid_posts:
            with self.subTest(invalid_post=invalid_post), self.assertRaises(ValueError):
                compare_impact(
                    pre=pre,
                    post=invalid_post,
                    changed_paths=("b.cpp",),
                )

    def test_compare_impact_requires_matching_nonblank_query_identities(self) -> None:
        from scripts.code_intelligence import compare_impact

        pre = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:before",
            affected_paths=[],
        )
        post = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:after",
            affected_paths=[],
        )
        invalid_pairs = (
            ({**pre, "query": {}}, post),
            ({**pre, "query": "impact:Foo"}, post),
            ({**pre, "query": {"query_id": "   ", "subjects": ["Foo"]}}, post),
            (
                pre,
                {**post, "query": {"query_id": "impact:Bar", "subjects": ["Foo"]}},
            ),
        )
        for pre, post in invalid_pairs:
            with self.subTest(pre=pre, post=post), self.assertRaises(ValueError):
                compare_impact(pre=pre, post=post, changed_paths=())

    def test_compare_impact_requires_affected_paths_in_both_artifacts(self) -> None:
        from scripts.code_intelligence import compare_impact

        pre = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:before",
            affected_paths=[],
        )
        post = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:after",
            affected_paths=[],
        )
        for pre, post in (
            ({key: value for key, value in pre.items() if key != "affected_paths"}, post),
            (pre, {key: value for key, value in post.items() if key != "affected_paths"}),
        ):
            with self.subTest(pre=pre, post=post), self.assertRaises(ValueError):
                compare_impact(pre=pre, post=post, changed_paths=())

    def test_compare_impact_rejects_malformed_path_collections(self) -> None:
        from scripts.code_intelligence import compare_impact

        valid_pre = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:before",
            affected_paths=["a.cpp"],
        )
        valid_post = self.impact_evidence(
            revision="abc",
            worktree_identity="sha256:after",
            affected_paths=["b.cpp"],
        )
        invalid_collections = ("a.cpp", {"path": "a.cpp"}, ["   "], [True])
        for invalid in invalid_collections:
            cases = (
                ({**valid_pre, "affected_paths": invalid}, valid_post, ()),
                (valid_pre, {**valid_post, "affected_paths": invalid}, ()),
                (valid_pre, valid_post, invalid),
            )
            for pre, post, changed in cases:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    compare_impact(
                        pre=pre,
                        post=post,
                        changed_paths=changed,
                    )

    def test_source_test_fallback_requires_reviewer_and_generated_authority(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        result = evaluate_source_test_fallback(
            graph_blocker="PARTIAL_LANGUAGE: lua",
            source_owners=("server/packet.cpp",),
            known_callers=("PacketRouter::dispatch",),
            known_consumers=("LuaPacketBridge",),
            generated_authorities=(),
            test_commands=("python -B -m unittest tests.packet",),
            reviewer="",
            residual_risk="Lua dispatch remains unmapped.",
        )

        self.assertEqual("BLOCKED", result["decision"])
        self.assertEqual("BLOCKED", result["graph_verdict"])
        self.assertEqual(
            ["generated authorities", "reviewer"],
            result["missing_requirements"],
        )

    def test_source_test_fallback_requires_and_preserves_callers_and_consumers(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        arguments = {
            "graph_blocker": "PARTIAL_LANGUAGE: lua",
            "source_owners": ("server/packet.cpp",),
            "generated_authorities": ("tools/generate_packet.py",),
            "test_commands": ("python -B -m unittest tests.packet",),
            "reviewer": "QA Lead",
            "residual_risk": "Lua reflection remains outside graph coverage.",
        }
        try:
            ready = evaluate_source_test_fallback(
                **arguments,
                known_callers=("PacketRouter::dispatch", "PacketRouter::dispatch"),
                known_consumers=("LuaPacketBridge",),
            )
        except TypeError as error:
            self.fail(f"fallback must accept caller and consumer evidence: {error}")

        self.assertEqual("REVIEWER_ACKNOWLEDGED_FALLBACK", ready["decision"])
        self.assertEqual("BLOCKED", ready["graph_verdict"])
        self.assertEqual(["PacketRouter::dispatch"], ready["known_callers"])
        self.assertEqual(["LuaPacketBridge"], ready["known_consumers"])

        for field, requirement in (
            ("known_callers", "known callers"),
            ("known_consumers", "known consumers"),
        ):
            blocked_arguments = {
                **arguments,
                "known_callers": ("PacketRouter::dispatch",),
                "known_consumers": ("LuaPacketBridge",),
                field: (),
            }
            blocked = evaluate_source_test_fallback(**blocked_arguments)
            with self.subTest(field=field):
                self.assertEqual("BLOCKED", blocked["decision"])
                self.assertEqual("BLOCKED", blocked["graph_verdict"])
                self.assertIn(requirement, blocked["missing_requirements"])

    def test_source_test_fallback_never_upgrades_graph_blocker(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        result = evaluate_source_test_fallback(
            graph_blocker="PARTIAL_LANGUAGE: lua",
            source_owners=("server/packet.cpp", "server/packet.cpp"),
            known_callers=("PacketRouter::dispatch",),
            known_consumers=("LuaPacketBridge",),
            generated_authorities=("tools/generate_packet.py",),
            test_commands=(
                "python -B -m unittest tests.packet",
                "python -B -m unittest tests.packet",
            ),
            reviewer="QA Lead",
            residual_risk="Lua reflection remains outside graph coverage.",
        )

        self.assertEqual("REVIEWER_ACKNOWLEDGED_FALLBACK", result["decision"])
        self.assertEqual("BLOCKED", result["graph_verdict"])
        self.assertEqual(["server/packet.cpp"], result["source_owners"])
        self.assertEqual(
            ["python -B -m unittest tests.packet"],
            result["test_commands"],
        )

    def test_source_test_fallback_reports_all_empty_requirements(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        result = evaluate_source_test_fallback(
            graph_blocker=" ",
            source_owners=(),
            generated_authorities=(),
            test_commands=(),
            reviewer=" ",
            residual_risk=" ",
        )

        self.assertEqual("BLOCKED", result["decision"])
        self.assertEqual(
            [
                "graph blocker",
                "source owners",
                "known callers",
                "known consumers",
                "generated authorities",
                "test commands",
                "reviewer",
                "residual risk",
            ],
            result["missing_requirements"],
        )

    def test_source_test_fallback_accepts_explicit_no_generated_output_sentinel(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        result = evaluate_source_test_fallback(
            graph_blocker="UNAVAILABLE",
            source_owners=(" src/a.cpp ", "src/a.cpp"),
            known_callers=(" A::call ", "A::call"),
            known_consumers=("ConsumerA",),
            generated_authorities=("NOT_APPLICABLE",),
            test_commands=(" python -B -m unittest tests.a ",),
            reviewer=" QA Lead ",
            residual_risk=" Source-only review. ",
        )

        self.assertEqual("REVIEWER_ACKNOWLEDGED_FALLBACK", result["decision"])
        self.assertEqual(["src/a.cpp"], result["source_owners"])
        self.assertEqual(["NOT_APPLICABLE"], result["generated_authorities"])
        self.assertEqual("QA Lead", result["reviewer"])

    def test_source_test_fallback_blocks_mixed_or_duplicate_generated_sentinel(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        invalid_authorities = (
            ("NOT_APPLICABLE", "tools/generate.py"),
            ("tools/generate.py", "NOT_APPLICABLE"),
            ("NOT_APPLICABLE", "NOT_APPLICABLE"),
            ("NOT_APPLICABLE", "not_applicable"),
            ("not_applicable",),
        )
        for authorities in invalid_authorities:
            with self.subTest(authorities=authorities):
                result = evaluate_source_test_fallback(
                    graph_blocker="UNAVAILABLE",
                    source_owners=("src/a.cpp",),
                    known_callers=("A::call",),
                    known_consumers=("ConsumerA",),
                    generated_authorities=authorities,
                    test_commands=("python -B -m unittest tests.a",),
                    reviewer="QA Lead",
                    residual_risk="Source-only review.",
                )

                self.assertEqual("BLOCKED", result["decision"])
                self.assertEqual("BLOCKED", result["graph_verdict"])
                self.assertIn(
                    "generated authorities",
                    result["missing_requirements"],
                )

    def test_source_test_fallback_accepts_exact_singleton_generated_sentinel(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        result = evaluate_source_test_fallback(
            graph_blocker="UNAVAILABLE",
            source_owners=("src/a.cpp",),
            known_callers=("A::call",),
            known_consumers=("ConsumerA",),
            generated_authorities=("NOT_APPLICABLE",),
            test_commands=("python -B -m unittest tests.a",),
            reviewer="QA Lead",
            residual_risk="Source-only review.",
        )

        self.assertEqual("REVIEWER_ACKNOWLEDGED_FALLBACK", result["decision"])
        self.assertEqual(["NOT_APPLICABLE"], result["generated_authorities"])

    def test_source_test_fallback_rejects_malformed_values(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        valid = {
            "graph_blocker": "UNAVAILABLE",
            "source_owners": ("src/a.cpp",),
            "known_callers": ("A::call",),
            "known_consumers": ("ConsumerA",),
            "generated_authorities": ("NOT_APPLICABLE",),
            "test_commands": ("python -B -m unittest tests.a",),
            "reviewer": "QA Lead",
            "residual_risk": "Source-only review.",
        }
        invalid_overrides = (
            {"graph_blocker": True},
            {"source_owners": "src/a.cpp"},
            {"source_owners": (True,)},
            {"known_callers": "A::call"},
            {"known_consumers": (True,)},
            {"generated_authorities": ({"path": "generator.py"},)},
            {"test_commands": ("   ",)},
            {"reviewer": False},
            {"residual_risk": None},
        )
        for override in invalid_overrides:
            with self.subTest(override=override), self.assertRaises(ValueError):
                evaluate_source_test_fallback(**{**valid, **override})


if __name__ == "__main__":
    unittest.main()
