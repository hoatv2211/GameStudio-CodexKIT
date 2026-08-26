# Shared Code Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one vendor-neutral Code Intelligence contract that normalizes provider freshness, capabilities, graph evidence, blast radius, and implementer/verifier handoff while retaining honest source/test fallback and legacy CodeGraph behavior.

**Architecture:** Keep provider descriptors and evidence schemas canonical, use one pure Python contract helper for normalization and read-only identity checks, and bridge the existing CodeGraph adapter without changing its project-init semantics. Workflow skills and agents consume capability-based evidence rather than vendor commands; generated resources are synchronized from root sources.

**Tech Stack:** Python 3.11, standard library dataclasses/hashlib/json/subprocess/pathlib, PyYAML, JSON Schema Draft 2020-12, `unittest`, canonical YAML registries, Markdown skills, TOML agent templates.

---

## Execution constraints

- Repository: current GameStudio-CodexKIT repository root.
- Planning snapshot: `dev@341d15a91a65d4ed11300ea4b3c69fa33a8ced41`.
- Design authority: `docs/superpowers/specs/2026-08-26-code-intelligence-design.md`.
- Preserve all unrelated tracked and untracked work. The current Code Intelligence files are an unfinished draft and may be improved in place.
- The repository has no `.codegraph/` directory, so use source inspection instead of creating an index.
- Do not mutate `.research/` or either dogfood project.
- Never hand-edit generated files under `skills/*/scripts/` or `skills/studio-project-scaffold/templates/agents/`.
- Commit policy is `ask`. Checkpoint steps inspect diffs; they do not commit. Commit, push, publish, and release require separate user authorization.
- Graphify remains experimental and opt-in. No implementation step runs provider installation, extraction, refresh, query, hook, daemon, or cleanup commands.

## File map

| Path | Responsibility |
|---|---|
| `registry/code-intelligence-providers.yaml` | Canonical provider descriptors, roles, capabilities, limitations, opt-in and terms gates |
| `evals/schema/code-intelligence-evidence.schema.json` | Strict normalized status/query/evidence artifact schema |
| `scripts/code_intelligence.py` | Provider-neutral models, registry loading, repository identity, strict probe normalization, evidence classification, fallback and pre/post comparison |
| `scripts/codegraph_adapter.py` | Legacy CodeGraph status/install behavior plus a one-way bridge into the normalized contract |
| `skills/code-intelligence-contract/SKILL.md` | Single distributed provider-neutral workflow and evidence contract |
| `skills/studio-project-intake/SKILL.md` | Optional provider/version/freshness/language intake |
| `skills/evidence-first-debugging/SKILL.md` | Graph-assisted data/control-flow tracing with source/runtime confirmation |
| `skills/safe-project-mutation/SKILL.md` | Required pre-impact check or explicit reviewer-acknowledged source/test fallback |
| `skills/review-swarm/SKILL.md` | Independent read-only dependency/impact review lane |
| `skills/studio-project-scaffold/SKILL.md` | References bundled shared and legacy helpers |
| `agents/implementer.toml` | Pre-change impact artifact and scope escalation contract |
| `agents/verifier.toml` | Independent post-change freshness and pre/post impact comparison contract |
| `agents/investigator.toml` | Optional read-only provider context with explicit limitations |
| `registry/capabilities.yaml` | One shared skill capability with non-circular root dependency |
| `registry/packs.yaml` | Include the shared skill in `studio-core` |
| `registry/skill-resources.yaml` | Bundle helper/schema/provider registry into the shared skill and helper/registry into scaffold |
| `registry/upstream-sources.yaml` | Provider research provenance only; no copied implementation |
| `evals/routing/code-intelligence-contract.json` | Positive, negative, and collision routing cases |
| `tests/studio_project_scaffold/test_code_intelligence.py` | Strict helper behavior and negative tests |
| `tests/studio_project_scaffold/test_codegraph_adapter.py` | Legacy compatibility and bridge tests |
| `tests/evals/test_code_intelligence_schema.py` | JSON Schema acceptance and rejection tests |
| `tests/governance/test_code_intelligence_contracts.py` | Skill, agent, registry, no-vendor-skill, and resource ownership contracts |
| `docs/case-studies/graphify-code-intelligence-dogfood.md` | Sanitized durable dogfood evidence and remaining blockers |
| `.codex-plugin/plugin.json` | Distributed plugin version `1.7.0` |
| `pyproject.toml` | Matching package version `1.7.0` |
| `tests/packaging/test_codex_plugin.py` | Version synchronization expectation |
| Generated resource destinations | Regenerated only by `scripts/sync_skill_resources.py` |

### Task 1: Lock the provider registry and strict evidence schema

**Files:**
- Create: `registry/code-intelligence-providers.yaml`
- Create: `evals/schema/code-intelligence-evidence.schema.json`
- Create: `tests/evals/test_code_intelligence_schema.py`
- Create: `tests/studio_project_scaffold/test_code_intelligence.py`

- [ ] **Step 1: Add RED tests for the canonical provider registry**

Create `tests/studio_project_scaffold/test_code_intelligence.py` with a temporary-registry fixture and these initial tests:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._meta.support import temporary_directory


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registry" / "code-intelligence-providers.yaml"


class CodeIntelligenceRegistryTests(unittest.TestCase):
    def test_provider_registry_is_capability_driven_and_ordered(self) -> None:
        from scripts.code_intelligence import load_provider_descriptors

        providers = load_provider_descriptors(REGISTRY)
        self.assertEqual(
            ("graphify", "gitnexus", "understand-anything", "codegraph"),
            tuple(provider.id for provider in providers),
        )
        self.assertEqual("experimental-default", providers[0].role)
        self.assertTrue(providers[0].opt_in_required)
        self.assertIn("impact", providers[0].capabilities)
        self.assertIn("pdg", providers[1].capabilities)
        self.assertIn("taint", providers[1].capabilities)
        self.assertTrue(providers[1].terms_review_required)
        self.assertIn("domain-flow", providers[2].capabilities)
        self.assertEqual("legacy-compatible", providers[3].role)

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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the registry tests and verify RED**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: exit `1` with `ModuleNotFoundError` or `ImportError` for the missing strict registry loader/model.

- [ ] **Step 3: Add the canonical provider registry**

Create `registry/code-intelligence-providers.yaml` exactly as:

```yaml
schema_version: 1
providers:
- id: graphify
  display_name: Graphify
  role: experimental-default
  maturity: experimental
  priority: 10
  opt_in_required: true
  terms_review_required: false
  capabilities:
  - context
  - dependency-path
  - impact
  limitations:
  - No automatic install, extraction, refresh, query, hook, daemon, or cleanup.
  - Generated, dynamic, cross-language, and cross-repository coverage is not established.
  - Project-local cache isolation is not established by current dogfood.
  upstream_source: graphify-labs-graphify
- id: gitnexus
  display_name: GitNexus
  role: advanced-optional
  maturity: experimental
  priority: 20
  opt_in_required: true
  terms_review_required: true
  capabilities:
  - context
  - dependency-path
  - impact
  - cross-repo
  - pdg
  - taint
  limitations:
  - Capability and license suitability require explicit verification before use.
  - No deep integration exists before governed dogfood.
  upstream_source: abhigyanpatwari-gitnexus
- id: understand-anything
  display_name: Understand Anything
  role: onboarding-optional
  maturity: experimental
  priority: 30
  opt_in_required: true
  terms_review_required: false
  capabilities:
  - architecture
  - domain-flow
  - onboarding
  limitations:
  - Structural extraction and LLM-semantic descriptions require separate evidence labels.
  - No deep integration exists before governed dogfood.
  upstream_source: egonex-ai-understand-anything
- id: codegraph
  display_name: CodeGraph
  role: legacy-compatible
  maturity: experimental
  priority: 40
  opt_in_required: true
  terms_review_required: false
  capabilities:
  - status
  - context
  - dependency-path
  - impact
  limitations:
  - Existing ownership, preference, and install approval behavior remains authoritative.
  upstream_source: null
```

`upstream_source: null` is deliberate for the legacy CodeGraph descriptor: this integration extends the repository's existing adapter and structured CLI-status contract without claiming a copied upstream research snapshot.

- [ ] **Step 4: Add RED schema tests**

Create `tests/evals/test_code_intelligence_schema.py` with a complete valid payload and strict negative cases:

```python
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "evals" / "schema" / "code-intelligence-evidence.schema.json"

VALID = {
    "schema_version": 1,
    "provider": "graphify",
    "provider_version": "0.9.50",
    "repository": "repo://game",
    "revision": "abc123",
    "worktree_identity": "sha256:worktree",
    "index_revision": "abc123",
    "index_worktree_identity": "sha256:worktree",
    "index_state": "FRESH",
    "capability": "impact",
    "query": {"query_id": "impact:TaskChangeNotify", "subjects": ["TaskChangeNotify"]},
    "resolved_subjects": ["TaskChangeNotify@Assets/Scripts/Task.cs:12"],
    "required_languages": ["csharp"],
    "supported_languages": ["csharp"],
    "missing_languages": [],
    "affected_paths": ["Assets/Scripts/TaskConsumer.cs"],
    "generated_boundaries": [],
    "edges": [{
        "relation": "CALLS",
        "source": "TaskConsumer::.ctor",
        "target": "TaskChangeNotify::.ctor",
        "source_locator": "Assets/Scripts/TaskConsumer.cs:20",
        "origin": "ast",
        "confidence": "EXTRACTED",
        "provenance": "SOURCE_EXTRACTED",
    }],
    "query_state": "COMPLETE",
    "evidence_label": "Verified",
    "graph_verdict": "PASS",
    "source_confirmations": ["Exact source call inspected."],
    "test_confirmations": [],
    "side_effects": [],
    "limitations": ["Verified covers extraction at this snapshot, not runtime behavior."],
    "disagreements": [],
    "commands": [{"command": "provider status", "exit_code": 0}],
    "artifacts": ["evidence/local/code-intelligence/graph.json"],
    "next_action": "Confirm runtime behavior with a focused test.",
}


def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class CodeIntelligenceEvidenceSchemaTests(unittest.TestCase):
    def assert_invalid(self, payload: dict[str, object]) -> None:
        with self.assertRaises(ValidationError):
            validator().validate(payload)

    def test_valid_evidence(self) -> None:
        validator().validate(VALID)

    def test_schema_is_strict_and_requires_every_contract_field(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(VALID), schema["required"])
        for field in VALID:
            payload = copy.deepcopy(VALID)
            del payload[field]
            with self.subTest(field=field):
                self.assert_invalid(payload)

    def test_blocked_states_cannot_claim_graph_pass(self) -> None:
        for state in (
            "UNAVAILABLE", "NOT_INITIALIZED", "STALE_HEAD", "STALE_WORKTREE",
            "PARTIAL_LANGUAGE", "BROKEN", "SIDE_EFFECT_VIOLATION", "USER_DISABLED",
        ):
            payload = copy.deepcopy(VALID)
            payload.update(
                index_state=state,
                query_state="STATUS_BLOCKED",
                evidence_label="BLOCKED",
                graph_verdict="BLOCKED",
            )
            validator().validate(payload)
            payload["graph_verdict"] = "PASS"
            with self.subTest(state=state):
                self.assert_invalid(payload)

    def test_empty_result_is_unverified_and_never_pass(self) -> None:
        payload = copy.deepcopy(VALID)
        payload.update(
            resolved_subjects=[],
            affected_paths=[],
            edges=[],
            query_state="EMPTY_UNCERTAIN",
            evidence_label="Unverified",
            graph_verdict="UNVERIFIED",
        )
        validator().validate(payload)
        payload["graph_verdict"] = "PASS"
        self.assert_invalid(payload)

    def test_inferred_edge_cannot_be_verified(self) -> None:
        payload = copy.deepcopy(VALID)
        payload["edges"][0].update(confidence="INFERRED", provenance="INFERRED")
        payload.update(evidence_label="Snapshot", graph_verdict="UNVERIFIED")
        validator().validate(payload)
        payload["evidence_label"] = "Verified"
        self.assert_invalid(payload)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run the schema tests and verify RED**

Run:

```powershell
python -B -m unittest tests.evals.test_code_intelligence_schema -v
```

Expected: exit `1` because `evals/schema/code-intelligence-evidence.schema.json` does not exist.

- [ ] **Step 6: Create the strict Draft 2020-12 schema**

Create `evals/schema/code-intelligence-evidence.schema.json` with this complete schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://gamestudio-codexkit.local/schema/code-intelligence-evidence.schema.json",
  "title": "GameStudio normalized Code Intelligence evidence",
  "type": "object",
  "required": [
    "schema_version",
    "provider",
    "provider_version",
    "repository",
    "revision",
    "worktree_identity",
    "index_revision",
    "index_worktree_identity",
    "index_state",
    "capability",
    "query",
    "resolved_subjects",
    "required_languages",
    "supported_languages",
    "missing_languages",
    "affected_paths",
    "generated_boundaries",
    "edges",
    "query_state",
    "evidence_label",
    "graph_verdict",
    "source_confirmations",
    "test_confirmations",
    "side_effects",
    "limitations",
    "disagreements",
    "commands",
    "artifacts",
    "next_action"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "provider": {"$ref": "#/$defs/kebab"},
    "provider_version": {"$ref": "#/$defs/nullableText"},
    "repository": {"$ref": "#/$defs/text"},
    "revision": {"$ref": "#/$defs/nullableText"},
    "worktree_identity": {"$ref": "#/$defs/nullableText"},
    "index_revision": {"$ref": "#/$defs/nullableText"},
    "index_worktree_identity": {"$ref": "#/$defs/nullableText"},
    "index_state": {
      "enum": [
        "UNAVAILABLE",
        "NOT_INITIALIZED",
        "FRESH",
        "STALE_HEAD",
        "STALE_WORKTREE",
        "PARTIAL_LANGUAGE",
        "BROKEN",
        "SIDE_EFFECT_VIOLATION",
        "USER_DISABLED"
      ]
    },
    "capability": {"$ref": "#/$defs/kebab"},
    "query": {"$ref": "#/$defs/query"},
    "resolved_subjects": {"$ref": "#/$defs/textArray"},
    "required_languages": {"$ref": "#/$defs/kebabArray"},
    "supported_languages": {"$ref": "#/$defs/kebabArray"},
    "missing_languages": {"$ref": "#/$defs/kebabArray"},
    "affected_paths": {"$ref": "#/$defs/textArray"},
    "generated_boundaries": {"$ref": "#/$defs/textArray"},
    "edges": {
      "type": "array",
      "items": {"$ref": "#/$defs/edge"}
    },
    "query_state": {
      "enum": [
        "COMPLETE",
        "STATUS_BLOCKED",
        "EMPTY_UNCERTAIN",
        "AMBIGUOUS",
        "CAPABILITY_MISMATCH"
      ]
    },
    "evidence_label": {
      "enum": ["Verified", "Snapshot", "Unverified", "BLOCKED"]
    },
    "graph_verdict": {
      "enum": ["PASS", "UNVERIFIED", "BLOCKED"]
    },
    "source_confirmations": {"$ref": "#/$defs/textArray"},
    "test_confirmations": {"$ref": "#/$defs/textArray"},
    "side_effects": {"$ref": "#/$defs/textArray"},
    "limitations": {"$ref": "#/$defs/textArray"},
    "disagreements": {"$ref": "#/$defs/textArray"},
    "commands": {
      "type": "array",
      "items": {"$ref": "#/$defs/command"}
    },
    "artifacts": {"$ref": "#/$defs/textArray"},
    "next_action": {"$ref": "#/$defs/text"}
  },
  "additionalProperties": false,
  "$defs": {
    "text": {
      "type": "string",
      "minLength": 1,
      "pattern": ".*\\S.*"
    },
    "nullableText": {
      "anyOf": [
        {"type": "null"},
        {"$ref": "#/$defs/text"}
      ]
    },
    "kebab": {
      "type": "string",
      "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"
    },
    "textArray": {
      "type": "array",
      "uniqueItems": true,
      "items": {"$ref": "#/$defs/text"}
    },
    "kebabArray": {
      "type": "array",
      "uniqueItems": true,
      "items": {"$ref": "#/$defs/kebab"}
    },
    "query": {
      "type": "object",
      "required": ["query_id", "subjects"],
      "properties": {
        "query_id": {"$ref": "#/$defs/text"},
        "subjects": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {"$ref": "#/$defs/text"}
        }
      },
      "additionalProperties": false
    },
    "edge": {
      "type": "object",
      "required": [
        "relation",
        "source",
        "target",
        "source_locator",
        "origin",
        "confidence",
        "provenance"
      ],
      "properties": {
        "relation": {"$ref": "#/$defs/text"},
        "source": {"$ref": "#/$defs/text"},
        "target": {"$ref": "#/$defs/text"},
        "source_locator": {"$ref": "#/$defs/text"},
        "origin": {"$ref": "#/$defs/text"},
        "confidence": {
          "enum": [
            "EXTRACTED",
            "INFERRED",
            "AMBIGUOUS",
            "SEMANTIC",
            "LLM",
            "UNKNOWN"
          ]
        },
        "provenance": {
          "enum": [
            "SOURCE_EXTRACTED",
            "INFERRED",
            "SEMANTIC",
            "LLM",
            "UNKNOWN"
          ]
        }
      },
      "additionalProperties": false
    },
    "command": {
      "type": "object",
      "required": ["command", "exit_code"],
      "properties": {
        "command": {"$ref": "#/$defs/text"},
        "exit_code": {
          "type": ["integer", "null"]
        }
      },
      "additionalProperties": false
    }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "index_state": {
            "enum": [
              "UNAVAILABLE",
              "NOT_INITIALIZED",
              "STALE_HEAD",
              "STALE_WORKTREE",
              "PARTIAL_LANGUAGE",
              "BROKEN",
              "SIDE_EFFECT_VIOLATION",
              "USER_DISABLED"
            ]
          }
        },
        "required": ["index_state"]
      },
      "then": {
        "properties": {
          "query_state": {"const": "STATUS_BLOCKED"},
          "evidence_label": {"const": "BLOCKED"},
          "graph_verdict": {"const": "BLOCKED"}
        }
      }
    },
    {
      "if": {
        "properties": {"query_state": {"const": "EMPTY_UNCERTAIN"}},
        "required": ["query_state"]
      },
      "then": {
        "properties": {
          "resolved_subjects": {"maxItems": 0},
          "affected_paths": {"maxItems": 0},
          "edges": {"maxItems": 0},
          "evidence_label": {"const": "Unverified"},
          "graph_verdict": {"const": "UNVERIFIED"}
        }
      }
    },
    {
      "if": {
        "properties": {
          "query_state": {
            "enum": ["AMBIGUOUS", "CAPABILITY_MISMATCH"]
          }
        },
        "required": ["query_state"]
      },
      "then": {
        "properties": {
          "evidence_label": {"const": "BLOCKED"},
          "graph_verdict": {"const": "BLOCKED"}
        }
      }
    },
    {
      "if": {
        "properties": {
          "edges": {
            "contains": {
              "type": "object",
              "properties": {
                "confidence": {
                  "enum": ["INFERRED", "AMBIGUOUS", "SEMANTIC", "LLM", "UNKNOWN"]
                }
              },
              "required": ["confidence"]
            }
          }
        },
        "required": ["edges"]
      },
      "then": {
        "properties": {
          "evidence_label": {
            "enum": ["Snapshot", "Unverified", "BLOCKED"]
          },
          "graph_verdict": {
            "enum": ["UNVERIFIED", "BLOCKED"]
          }
        }
      }
    },
    {
      "if": {
        "properties": {"graph_verdict": {"const": "PASS"}},
        "required": ["graph_verdict"]
      },
      "then": {
        "properties": {
          "index_state": {"const": "FRESH"},
          "query_state": {"const": "COMPLETE"},
          "evidence_label": {"const": "Verified"},
          "edges": {
            "minItems": 1,
            "items": {
              "type": "object",
              "properties": {
                "confidence": {"const": "EXTRACTED"},
                "provenance": {"const": "SOURCE_EXTRACTED"}
              },
              "required": ["confidence", "provenance"]
            }
          }
        }
      }
    }
  ]
}
```

- [ ] **Step 7: Run Task 1 tests**

Run:

```powershell
python -B -m unittest tests.evals.test_code_intelligence_schema tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: schema tests pass; registry tests still fail until the loader is implemented in Task 2.

- [ ] **Step 8: Checkpoint the Task 1 diff without committing**

Run:

```powershell
git diff --check
git status --short
```

Expected: only the planned new schema, registry, tests, existing draft, and preserved unrelated work appear. Do not run `git add` or `git commit`.

### Task 2: Implement provider-neutral models and registry loading

**Files:**
- Modify: `scripts/code_intelligence.py`
- Test: `tests/studio_project_scaffold/test_code_intelligence.py`

- [ ] **Step 1: Add RED model and loader tests**

Append:

```python
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
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: exit `1` because strict descriptor dataclasses and state mapping are missing.

- [ ] **Step 3: Replace provisional constants and descriptors with strict models**

In `scripts/code_intelligence.py` define:

```python
CANONICAL_STATES = frozenset({
    "UNAVAILABLE", "NOT_INITIALIZED", "FRESH", "STALE_HEAD",
    "STALE_WORKTREE", "PARTIAL_LANGUAGE", "BROKEN",
    "SIDE_EFFECT_VIOLATION", "USER_DISABLED",
})
BLOCKED_STATES = CANONICAL_STATES - {"FRESH"}
LEGACY_STATE_MAP = {
    "INITIALIZED_HEALTHY": "FRESH",
    "AVAILABLE_NOT_INITIALIZED": "NOT_INITIALIZED",
    "INITIALIZING": "BROKEN",
    "INITIALIZED_STALE": "STALE_HEAD",
    "INITIALIZED_BROKEN": "BROKEN",
    "PARTIAL": "PARTIAL_LANGUAGE",
    "UNSUPPORTED_LANGUAGE": "PARTIAL_LANGUAGE",
}
ALLOWED_ROLES = frozenset({
    "experimental-default", "advanced-optional",
    "onboarding-optional", "legacy-compatible",
})
ALLOWED_CAPABILITIES = frozenset({
    "status", "context", "dependency-path", "impact",
    "cross-repo", "pdg", "taint", "architecture",
    "domain-flow", "onboarding",
})


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    display_name: str
    role: str
    maturity: str
    priority: int
    opt_in_required: bool
    terms_review_required: bool
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    upstream_source: str | None


@dataclass(frozen=True)
class RepositoryIdentity:
    repository: str
    revision: str | None
    worktree_identity: str | None
    complete: bool
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodeIntelligenceStatus:
    provider: str
    provider_version: str | None
    repository: str
    revision: str | None
    worktree_identity: str | None
    index_revision: str | None
    index_worktree_identity: str | None
    index_state: str
    capabilities: tuple[str, ...]
    required_languages: tuple[str, ...]
    supported_languages: tuple[str, ...]
    missing_languages: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    side_effects: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

- [ ] **Step 4: Implement strict YAML registry loading**

Use `scripts.common.load_yaml` in the full clone and `common.load_yaml` only for the existing packaged fallback pattern. Reject unknown keys and unstable ordering:

```python
PROVIDER_KEYS = {
    "id", "display_name", "role", "maturity", "priority",
    "opt_in_required", "terms_review_required", "capabilities",
    "limitations", "upstream_source",
}


def default_provider_registry_path(module_path: Path | str = __file__) -> Path:
    module = Path(module_path).resolve()
    candidates = (
        module.parent.parent / "registry" / "code-intelligence-providers.yaml",
        module.parent.parent / "references" / "code-intelligence-providers.yaml",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError("code-intelligence provider registry is unavailable")


def load_provider_descriptors(
    path: Path | str | None = None,
) -> tuple[ProviderDescriptor, ...]:
    document = load_yaml(Path(path) if path is not None else default_provider_registry_path())
    if not isinstance(document, dict) or set(document) != {"schema_version", "providers"}:
        raise ValueError("code-intelligence provider registry has an invalid top-level schema")
    if document["schema_version"] != 1 or not isinstance(document["providers"], list):
        raise ValueError("code-intelligence provider registry schema_version must be 1")
    providers: list[ProviderDescriptor] = []
    seen: set[str] = set()
    for raw in document["providers"]:
        if not isinstance(raw, dict) or set(raw) != PROVIDER_KEYS:
            raise ValueError("code-intelligence provider descriptor has invalid keys")
        provider_id = raw["id"]
        capabilities = raw["capabilities"]
        limitations = raw["limitations"]
        if (
            not isinstance(provider_id, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", provider_id)
            or provider_id in seen
        ):
            raise ValueError(f"invalid or duplicate provider id: {provider_id!r}")
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or len(capabilities) != len(set(capabilities))
            or any(item not in ALLOWED_CAPABILITIES for item in capabilities)
        ):
            raise ValueError(f"invalid capabilities for provider {provider_id}")
        if (
            raw["role"] not in ALLOWED_ROLES
            or not isinstance(raw["display_name"], str)
            or not raw["display_name"].strip()
            or not isinstance(raw["maturity"], str)
            or not raw["maturity"].strip()
            or not isinstance(raw["priority"], int)
            or isinstance(raw["priority"], bool)
            or not isinstance(raw["opt_in_required"], bool)
            or not isinstance(raw["terms_review_required"], bool)
            or (
                raw["upstream_source"] is not None
                and (
                    not isinstance(raw["upstream_source"], str)
                    or not re.fullmatch(
                        r"[a-z0-9]+(?:-[a-z0-9]+)*",
                        raw["upstream_source"],
                    )
                )
            )
            or not isinstance(limitations, list)
            or len(limitations) != len(set(limitations))
            or any(not isinstance(item, str) or not item.strip() for item in limitations)
        ):
            raise ValueError(f"invalid descriptor for provider {provider_id}")
        seen.add(provider_id)
        providers.append(ProviderDescriptor(
            id=provider_id,
            display_name=str(raw["display_name"]),
            role=str(raw["role"]),
            maturity=str(raw["maturity"]),
            priority=raw["priority"],
            opt_in_required=raw["opt_in_required"],
            terms_review_required=raw["terms_review_required"],
            capabilities=tuple(capabilities),
            limitations=tuple(limitations),
            upstream_source=(
                str(raw["upstream_source"])
                if raw["upstream_source"] is not None
                else None
            ),
        ))
    providers.sort(key=lambda item: item.priority)
    return tuple(providers)


def get_provider_descriptor(
    provider: str,
    *,
    registry_path: Path | str,
) -> ProviderDescriptor:
    provider_id = provider.casefold()
    for descriptor in load_provider_descriptors(registry_path):
        if descriptor.id == provider_id:
            return descriptor
    raise ValueError(f"unsupported code-intelligence provider: {provider}")


def normalize_index_state(state: str) -> str:
    normalized = state.upper()
    if normalized in CANONICAL_STATES:
        return normalized
    return LEGACY_STATE_MAP.get(normalized, "BROKEN")
```

- [ ] **Step 5: Run Task 2 tests**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: registry/model tests pass; later probe/evidence tests are not added yet.

- [ ] **Step 6: Checkpoint without committing**

Run `git diff --check` and inspect `git diff -- scripts/code_intelligence.py registry/code-intelligence-providers.yaml tests/studio_project_scaffold/test_code_intelligence.py`. Do not stage or commit.

### Task 3: Enforce repository identity, strict provider status, and isolation

**Files:**
- Modify: `scripts/code_intelligence.py`
- Test: `tests/studio_project_scaffold/test_code_intelligence.py`

- [ ] **Step 1: Add RED tests for HEAD/worktree drift, language coverage, capability mismatch, and side effects**

Append tests using explicit identities and an index manifest:

```python
class CodeIntelligenceStatusTests(unittest.TestCase):
    def test_probe_requires_revision_worktree_capability_and_languages(self) -> None:
        from scripts.code_intelligence import RepositoryIdentity, inspect_provider

        current = RepositoryIdentity("repo://game", "abc", "sha256:one", True)
        manifest = {
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
```

- [ ] **Step 2: Add a RED test for read-only repository identity**

Append this method to `CodeIntelligenceStatusTests`. Use a fake git runner so tests never depend on the developer's checkout:

```python
    def test_capture_identity_hashes_git_snapshot_without_writing(self) -> None:
        from scripts.code_intelligence import capture_repository_identity

        calls: list[tuple[str, ...]] = []
        outputs = {
            ("rev-parse", "--show-toplevel"): "/example/game\n",
            ("rev-parse", "HEAD"): "abc123\n",
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"): " M server/a.cpp\\0",
            ("diff", "--binary"): "diff --git a/server/a.cpp b/server/a.cpp\n",
            ("diff", "--binary", "--cached"): "",
        }

        def runner(args: list[str], *, cwd: Path) -> str:
            calls.append(tuple(args))
            return outputs[tuple(args)]

        identity = capture_repository_identity(Path("/example/game"), runner=runner)
        self.assertEqual("/example/game", identity.repository)
        self.assertEqual("abc123", identity.revision)
        self.assertTrue(identity.worktree_identity.startswith("sha256:"))
        self.assertTrue(identity.complete)
        self.assertEqual(5, len(calls))
```

- [ ] **Step 3: Run RED**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: exit `1` because identity capture and strict `inspect_provider` behavior are missing.

- [ ] **Step 4: Implement deterministic read-only identity capture**

Add a `GitTextRunner` protocol, a `_default_git_text_runner` using `subprocess.run(..., shell=False, check=False)`, and:

```python
def capture_repository_identity(
    root: Path | str,
    *,
    runner: GitTextRunner | None = None,
) -> RepositoryIdentity:
    root_path = Path(root).resolve()
    command = runner or _default_git_text_runner
    limitations: list[str] = []
    try:
        repository = command(["rev-parse", "--show-toplevel"], cwd=root_path).strip()
        revision = command(["rev-parse", "HEAD"], cwd=root_path).strip()
        status = command(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root_path,
        )
        unstaged = command(["diff", "--binary"], cwd=root_path)
        staged = command(["diff", "--binary", "--cached"], cwd=root_path)
    except (OSError, ValueError) as error:
        return RepositoryIdentity(
            repository=str(root_path),
            revision=None,
            worktree_identity=None,
            complete=False,
            limitations=(f"repository identity unavailable: {error}",),
        )
    digest = hashlib.sha256()
    for value in (repository, revision, status, unstaged, staged):
        encoded = value.encode("utf-8", errors="surrogateescape")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return RepositoryIdentity(
        repository=Path(repository).resolve().as_posix(),
        revision=revision or None,
        worktree_identity=f"sha256:{digest.hexdigest()}",
        complete=bool(repository and revision),
        limitations=tuple(limitations),
    )
```

The status stream records all untracked names. Do not open or hash untracked file contents such as `.env`. If a provider manifest claims to index untracked content, require its own content identity and retain a limitation when that identity is absent.

- [ ] **Step 5: Implement strict manifest-only status normalization**

Add an exact manifest validator:

```python
INDEX_MANIFEST_KEYS = {
    "provider", "provider_version", "repository", "revision",
    "worktree_identity", "capabilities", "languages",
    "artifact_paths", "artifacts_validated",
}


def _validated_index_manifest(
    raw: Mapping[str, object],
    *,
    provider: str,
) -> dict[str, object]:
    if set(raw) != INDEX_MANIFEST_KEYS or raw.get("provider") != provider:
        raise ValueError("provider index manifest has invalid keys or provider")
    for field in ("provider_version", "repository", "revision", "worktree_identity"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"provider index manifest {field} is invalid")
    for field in ("capabilities", "languages", "artifact_paths"):
        values = raw.get(field)
        if (
            not isinstance(values, list)
            or not values
            or len(values) != len(set(values))
            or any(not isinstance(item, str) or not item.strip() for item in values)
        ):
            raise ValueError(f"provider index manifest {field} is invalid")
    if raw.get("artifacts_validated") is not True:
        raise ValueError("provider index artifacts are not validated")
    return dict(raw)
```

Replace the provisional artifact-only probe with a pure function that never runs provider commands. Before reading manifest fields, call `_validated_index_manifest` inside `try/except ValueError`; on failure return the same complete status object with `index_state="BROKEN"` and the validation error in `limitations`:

```python
def inspect_provider(
    identity: RepositoryIdentity,
    provider: str,
    *,
    manifest: Mapping[str, object] | None,
    required_capability: str,
    required_languages: Sequence[str],
    registry_path: Path | str,
    after_identity: RepositoryIdentity | None = None,
    observed_side_effects: Sequence[str] = (),
    discovered_artifacts: Sequence[str] = (),
    user_disabled: bool = False,
) -> CodeIntelligenceStatus:
    descriptor = get_provider_descriptor(provider, registry_path=registry_path)
    required = tuple(dict.fromkeys(language.casefold() for language in required_languages))
    limitations = list(descriptor.limitations)
    side_effects = tuple(dict.fromkeys(observed_side_effects))
    if user_disabled:
        state = "USER_DISABLED"
    elif side_effects:
        state = "SIDE_EFFECT_VIOLATION"
    elif after_identity is not None and (
        after_identity.revision != identity.revision
        or after_identity.worktree_identity != identity.worktree_identity
    ):
        state = "STALE_WORKTREE"
        limitations.append("repository identity changed during provider operation")
    elif not identity.complete:
        state = "BROKEN"
        limitations.extend(identity.limitations)
    elif manifest is None:
        state = "STALE_HEAD" if discovered_artifacts else "NOT_INITIALIZED"
        limitations.append("provider artifact lacks a repository/index identity manifest")
    else:
        try:
            manifest = _validated_index_manifest(manifest, provider=descriptor.id)
        except ValueError as error:
            return CodeIntelligenceStatus(
                provider=descriptor.id,
                provider_version=None,
                repository=identity.repository,
                revision=identity.revision,
                worktree_identity=identity.worktree_identity,
                index_revision=None,
                index_worktree_identity=None,
                index_state="BROKEN",
                capabilities=(),
                required_languages=required,
                supported_languages=(),
                missing_languages=required,
                artifact_paths=tuple(discovered_artifacts),
                side_effects=side_effects,
                limitations=tuple(dict.fromkeys([*limitations, str(error)])),
            )
        capabilities = tuple(str(item) for item in manifest["capabilities"])
        languages = tuple(str(item).casefold() for item in manifest["languages"])
        missing = tuple(item for item in required if item not in languages)
        if manifest.get("repository") != identity.repository:
            state = "BROKEN"
            limitations.append("provider manifest repository mismatch")
        elif manifest.get("revision") != identity.revision:
            state = "STALE_HEAD"
        elif manifest.get("worktree_identity") != identity.worktree_identity:
            state = "STALE_WORKTREE"
        elif required_capability not in descriptor.capabilities or required_capability not in capabilities:
            state = "BROKEN"
            limitations.append(f"capability mismatch: {required_capability}")
        elif missing:
            state = "PARTIAL_LANGUAGE"
        else:
            state = "FRESH"
        return CodeIntelligenceStatus(
            provider=descriptor.id,
            provider_version=str(manifest["provider_version"]),
            repository=identity.repository,
            revision=identity.revision,
            worktree_identity=identity.worktree_identity,
            index_revision=str(manifest.get("revision") or "") or None,
            index_worktree_identity=str(manifest.get("worktree_identity") or "") or None,
            index_state=state,
            capabilities=capabilities,
            required_languages=required,
            supported_languages=languages,
            missing_languages=missing,
            artifact_paths=tuple(str(item) for item in manifest["artifact_paths"]),
            side_effects=side_effects,
            limitations=tuple(dict.fromkeys(limitations)),
        )
    return CodeIntelligenceStatus(
        provider=descriptor.id,
        provider_version=None,
        repository=identity.repository,
        revision=identity.revision,
        worktree_identity=identity.worktree_identity,
        index_revision=None,
        index_worktree_identity=None,
        index_state=state,
        capabilities=descriptor.capabilities,
        required_languages=required,
        supported_languages=(),
        missing_languages=required,
        artifact_paths=tuple(discovered_artifacts),
        side_effects=side_effects,
        limitations=tuple(dict.fromkeys(limitations)),
    )
```

The wrapper that creates the manifest owns artifact validation. The shared probe consumes only `artifacts_validated: true` and never infers validity from artifact existence alone.

- [ ] **Step 6: Run Task 3 tests**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: exit `0` and `OK`.

- [ ] **Step 7: Checkpoint without committing**

Run `git diff --check` and inspect only the Task 3 files. Confirm no provider process or dogfood project was touched.

### Task 4: Normalize per-edge evidence, ambiguity, and empty results

**Files:**
- Modify: `scripts/code_intelligence.py`
- Test: `tests/studio_project_scaffold/test_code_intelligence.py`

- [ ] **Step 1: Add RED evidence tests**

Append:

```python
class CodeIntelligenceEvidenceTests(unittest.TestCase):
    def test_ast_origin_with_inferred_confidence_is_snapshot(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        result = normalize_evidence(
            status=self.fresh_status(),
            capability="impact",
            query={"query_id": "impact:Foo", "subjects": ["Foo"]},
            resolved_subjects=("Foo@src/foo.cpp:10",),
            edges=({
                "relation": "CALLS",
                "source": "Bar",
                "target": "Foo",
                "source_locator": "src/bar.cpp:20",
                "origin": "ast",
                "confidence": "INFERRED",
            },),
            affected_paths=("src/bar.cpp",),
        )
        self.assertEqual("Snapshot", result["evidence_label"])
        self.assertEqual("UNVERIFIED", result["graph_verdict"])
        self.assertEqual("INFERRED", result["edges"][0]["provenance"])

    def test_empty_result_preserves_uncertainty(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        result = normalize_evidence(
            status=self.fresh_status(),
            capability="impact",
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

    def test_ambiguous_subject_blocks_instead_of_guessing(self) -> None:
        from scripts.code_intelligence import normalize_evidence

        result = normalize_evidence(
            status=self.fresh_status(),
            capability="impact",
            query={"query_id": "impact:Foo", "subjects": ["Foo"]},
            resolved_subjects=("Foo@src/a.cpp:10", "Foo@src/b.cpp:20"),
            edges=(),
            affected_paths=(),
        )
        self.assertEqual("AMBIGUOUS", result["query_state"])
        self.assertEqual("BLOCKED", result["graph_verdict"])

    def test_blocked_status_cannot_be_upgraded_by_extracted_edge(self) -> None:
        from dataclasses import replace
        from scripts.code_intelligence import normalize_evidence

        status = replace(self.fresh_status(), index_state="PARTIAL_LANGUAGE")
        result = normalize_evidence(
            status=status,
            capability="impact",
            query={"query_id": "impact:Foo", "subjects": ["Foo"]},
            resolved_subjects=("Foo@src/foo.cpp:10",),
            edges=({
                "relation": "CALLS",
                "source": "Bar",
                "target": "Foo",
                "source_locator": "src/bar.cpp:20",
                "origin": "ast",
                "confidence": "EXTRACTED",
            },),
            affected_paths=("src/bar.cpp",),
        )
        self.assertEqual("BLOCKED", result["evidence_label"])
        self.assertEqual("BLOCKED", result["graph_verdict"])
```

Define `fresh_status()` in the test class exactly as:

```python
    def fresh_status(self):
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
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence.CodeIntelligenceEvidenceTests -v
```

Expected: exit `1` because the provisional `normalize_evidence` accepts a single `edge_kind` and cannot classify per-edge confidence, ambiguity, or empty results.

- [ ] **Step 3: Implement per-edge normalization**

Add:

```python
CONFIDENCE_TO_PROVENANCE = {
    "EXTRACTED": "SOURCE_EXTRACTED",
    "INFERRED": "INFERRED",
    "AMBIGUOUS": "INFERRED",
    "SEMANTIC": "SEMANTIC",
    "LLM": "LLM",
    "UNKNOWN": "UNKNOWN",
}


def _normalize_edge(raw: Mapping[str, object]) -> dict[str, str]:
    required = {"relation", "source", "target", "source_locator", "origin", "confidence"}
    if set(raw) != required:
        raise ValueError("code-intelligence edge has invalid fields")
    confidence = str(raw["confidence"]).upper()
    if confidence not in CONFIDENCE_TO_PROVENANCE:
        confidence = "UNKNOWN"
    return {
        "relation": str(raw["relation"]),
        "source": str(raw["source"]),
        "target": str(raw["target"]),
        "source_locator": str(raw["source_locator"]),
        "origin": str(raw["origin"]),
        "confidence": confidence,
        "provenance": CONFIDENCE_TO_PROVENANCE[confidence],
    }
```

- [ ] **Step 4: Replace `normalize_evidence` with the normalized artifact contract**

Use the schema field names exactly. The decision order is status blocker, capability mismatch, ambiguity, empty result, all-source-extracted, then inferred/unknown:

```python
def normalize_evidence(
    *,
    status: CodeIntelligenceStatus,
    capability: str,
    query: Mapping[str, object],
    resolved_subjects: Sequence[str],
    edges: Sequence[Mapping[str, object]],
    affected_paths: Sequence[str],
    generated_boundaries: Sequence[str] = (),
    source_confirmations: Sequence[str] = (),
    test_confirmations: Sequence[str] = (),
    disagreements: Sequence[str] = (),
    commands: Sequence[Mapping[str, object]] = (),
    artifacts: Sequence[str] = (),
    next_action: str = "Confirm important graph findings against authoritative source and tests.",
) -> dict[str, object]:
    normalized_edges = tuple(_normalize_edge(edge) for edge in edges)
    subjects = tuple(dict.fromkeys(str(item) for item in resolved_subjects))
    limitations = list(status.limitations)
    limitations.append("No graph result is not proof that no dependency exists.")
    if status.index_state in BLOCKED_STATES:
        query_state, evidence_label, graph_verdict = "STATUS_BLOCKED", "BLOCKED", "BLOCKED"
    elif capability not in status.capabilities:
        query_state, evidence_label, graph_verdict = "CAPABILITY_MISMATCH", "BLOCKED", "BLOCKED"
        limitations.append(f"capability mismatch: {capability}")
    elif len(subjects) > 1:
        query_state, evidence_label, graph_verdict = "AMBIGUOUS", "BLOCKED", "BLOCKED"
    elif not subjects and not normalized_edges and not affected_paths:
        query_state, evidence_label, graph_verdict = "EMPTY_UNCERTAIN", "Unverified", "UNVERIFIED"
    elif normalized_edges and all(
        edge["provenance"] == "SOURCE_EXTRACTED" for edge in normalized_edges
    ):
        query_state, evidence_label, graph_verdict = "COMPLETE", "Verified", "PASS"
        limitations.append(
            "Verified applies to source extraction at this snapshot, not runtime behavior or complete recall."
        )
    else:
        query_state, evidence_label, graph_verdict = "COMPLETE", "Snapshot", "UNVERIFIED"
        limitations.append("Inferred, semantic, LLM, or unknown edges require source or runtime confirmation.")
    return {
        "schema_version": 1,
        "provider": status.provider,
        "provider_version": status.provider_version,
        "repository": status.repository,
        "revision": status.revision,
        "worktree_identity": status.worktree_identity,
        "index_revision": status.index_revision,
        "index_worktree_identity": status.index_worktree_identity,
        "index_state": status.index_state,
        "capability": capability,
        "query": dict(query),
        "resolved_subjects": list(subjects),
        "required_languages": list(status.required_languages),
        "supported_languages": list(status.supported_languages),
        "missing_languages": list(status.missing_languages),
        "affected_paths": list(dict.fromkeys(affected_paths)),
        "generated_boundaries": list(dict.fromkeys(generated_boundaries)),
        "edges": list(normalized_edges),
        "query_state": query_state,
        "evidence_label": evidence_label,
        "graph_verdict": graph_verdict,
        "source_confirmations": list(dict.fromkeys(source_confirmations)),
        "test_confirmations": list(dict.fromkeys(test_confirmations)),
        "side_effects": list(status.side_effects),
        "limitations": list(dict.fromkeys(limitations)),
        "disagreements": list(dict.fromkeys(disagreements)),
        "commands": [dict(item) for item in commands],
        "artifacts": list(dict.fromkeys(artifacts)),
        "next_action": next_action,
    }
```

If multiple subjects are legitimate inputs, require the query to resolve each input separately before calling this function. The first contract only accepts zero or one resolved candidate for one subject; it never guesses overloads.

- [ ] **Step 5: Validate normalized output against the JSON Schema in tests**

For each evidence test, call `Draft202012Validator` on the returned object after the semantic assertions. This prevents Python and schema field drift.

- [ ] **Step 6: Run Task 4 tests**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_code_intelligence tests.evals.test_code_intelligence_schema -v
```

Expected: exit `0` and `OK`.

- [ ] **Step 7: Checkpoint without committing**

Run `git diff --check` and inspect the module/tests/schema diff. Confirm `_origin=ast` never bypasses `confidence=INFERRED`.

### Task 5: Bridge legacy CodeGraph and add pre/post impact plus fallback artifacts

**Files:**
- Modify: `scripts/codegraph_adapter.py`
- Modify: `scripts/code_intelligence.py`
- Modify: `tests/studio_project_scaffold/test_codegraph_adapter.py`
- Modify: `tests/studio_project_scaffold/test_code_intelligence.py`

- [ ] **Step 1: Move provisional shared-layer tests out of the legacy test class**

Remove the four provisional `code_intelligence` tests currently at the top of `CodeGraphAdapterTests`. Their strict replacements live in `test_code_intelligence.py`. Preserve every existing legacy CodeGraph test unchanged.

- [ ] **Step 2: Add RED bridge tests without changing core-init semantics**

Append to `test_codegraph_adapter.py`:

```python
    def test_legacy_status_maps_to_blocked_graph_lane_without_blocking_core_init(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        with temporary_directory() as temp:
            root = Path(temp)
            legacy = inspect_codegraph(
                root,
                runner=FakeRunner(FakeResult(stdout=json.dumps({
                    "initialized": True,
                    "version": "1.5.0",
                    "index": {"state": "stale", "reindexRecommended": True},
                    "worktree": {},
                }))),
            )
            normalized = to_code_intelligence_status(
                legacy,
                repository=root.resolve().as_posix(),
                revision="abc",
                worktree_identity="sha256:current",
                required_languages=("csharp",),
            )

        self.assertFalse(legacy.blocking)
        self.assertEqual("STALE_HEAD", normalized.index_state)
        self.assertEqual("codegraph", normalized.provider)

    def test_legacy_bridge_never_executes_payload_argv(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph

        payload = {
            "initialized": True,
            "version": "1.5.0",
            "index": {"state": "complete"},
            "worktree": {},
            "actions": [{"argv": ["powershell", "-Command", "Write-Host unsafe"]}],
        }
        runner = FakeRunner(FakeResult(stdout=json.dumps(payload)))
        with temporary_directory() as temp:
            inspect_codegraph(Path(temp), runner=runner)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual("codegraph", runner.calls[0][0][0])

    def test_legacy_healthy_status_without_language_evidence_is_partial(self) -> None:
        from scripts.codegraph_adapter import inspect_codegraph, to_code_intelligence_status

        payload = {
            "initialized": True,
            "version": "1.5.0",
            "revision": "abc",
            "worktreeIdentity": "sha256:current",
            "index": {"state": "complete"},
            "worktree": {},
        }
        with temporary_directory() as temp:
            root = Path(temp)
            legacy = inspect_codegraph(
                root,
                runner=FakeRunner(FakeResult(stdout=json.dumps(payload))),
            )
            normalized = to_code_intelligence_status(
                legacy,
                repository=root.resolve().as_posix(),
                revision="abc",
                worktree_identity="sha256:current",
                required_languages=("csharp",),
            )
        self.assertEqual("PARTIAL_LANGUAGE", normalized.index_state)
        self.assertEqual(("csharp",), normalized.missing_languages)
```

- [ ] **Step 3: Run RED**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_codegraph_adapter -v
```

Expected: exit `1` because `to_code_intelligence_status` is missing; existing legacy tests remain green before that missing-symbol error.

- [ ] **Step 4: Implement the one-way legacy bridge**

In `scripts/codegraph_adapter.py` add a lazy import inside the bridge to avoid circular import:

```python
def to_code_intelligence_status(
    status: CodeGraphStatus,
    *,
    repository: str,
    revision: str | None,
    worktree_identity: str | None,
    required_languages: tuple[str, ...] = (),
):
    try:
        from scripts.code_intelligence import CodeIntelligenceStatus, normalize_index_state
    except ModuleNotFoundError:
        from code_intelligence import CodeIntelligenceStatus, normalize_index_state

    raw = status.raw_status if isinstance(status.raw_status, dict) else {}
    index = _index_payload(raw)
    worktree = _worktree_payload(raw)
    index_revision = index.get("revision") or raw.get("revision")
    index_worktree_identity = (
        worktree.get("identity") or worktree.get("digest") or raw.get("worktreeIdentity")
    )
    raw_languages = raw.get("languages")
    supported_languages = (
        tuple(str(item).casefold() for item in raw_languages)
        if isinstance(raw_languages, list)
        and all(isinstance(item, str) and item for item in raw_languages)
        else ()
    )
    missing_languages = tuple(
        language for language in required_languages
        if language.casefold() not in supported_languages
    )
    normalized_state = normalize_index_state(status.state)
    limitations = [status.detail]
    if normalized_state == "FRESH" and (
        index_revision != revision or index_worktree_identity != worktree_identity
    ):
        normalized_state = "STALE_HEAD" if index_revision != revision else "STALE_WORKTREE"
        limitations.append("legacy status does not prove current repository/worktree binding")
    if normalized_state == "FRESH" and missing_languages:
        normalized_state = "PARTIAL_LANGUAGE"
        limitations.append("legacy status does not prove required language coverage")
    return CodeIntelligenceStatus(
        provider="codegraph",
        provider_version=status.version,
        repository=repository,
        revision=revision,
        worktree_identity=worktree_identity,
        index_revision=str(index_revision) if index_revision is not None else None,
        index_worktree_identity=(
            str(index_worktree_identity) if index_worktree_identity is not None else None
        ),
        index_state=normalized_state,
        capabilities=("status", "context", "dependency-path", "impact"),
        required_languages=required_languages,
        supported_languages=supported_languages,
        missing_languages=missing_languages,
        artifact_paths=(".codegraph/",) if status.existing_index else (),
        side_effects=(),
        limitations=tuple(dict.fromkeys(limitations)),
    )
```

Do not change `inspect_codegraph(...).blocking`, install planning, canonical action construction, preference behavior, ownership, or restore logic. The shared graph lane may be blocked while core init remains non-blocking.

- [ ] **Step 5: Add RED pre/post comparison and fallback tests**

Append to `test_code_intelligence.py`:

```python
class CodeIntelligenceHandoffTests(unittest.TestCase):
    def test_compare_impact_exposes_new_unexpected_and_missing_paths(self) -> None:
        from scripts.code_intelligence import compare_impact

        result = compare_impact(
            pre={"query": {"query_id": "impact:Foo"}, "affected_paths": ["a.cpp", "b.cpp"]},
            post={"query": {"query_id": "impact:Foo"}, "affected_paths": ["b.cpp", "c.cpp"]},
            changed_paths=("a.cpp", "d.cpp"),
        )
        self.assertEqual(["c.cpp"], result["added_affected_paths"])
        self.assertEqual(["a.cpp"], result["removed_affected_paths"])
        self.assertEqual(["d.cpp"], result["changed_not_predicted"])
        self.assertEqual(["a.cpp"], result["changed_no_longer_affected"])

    def test_source_test_fallback_requires_reviewer_and_all_authorities(self) -> None:
        from scripts.code_intelligence import evaluate_source_test_fallback

        blocked = evaluate_source_test_fallback(
            graph_blocker="PARTIAL_LANGUAGE: lua",
            source_owners=("server/packet.cpp",),
            generated_authorities=(),
            test_commands=("python -B -m unittest tests.packet",),
            reviewer="",
            residual_risk="Lua dispatch remains unmapped.",
        )
        self.assertEqual("BLOCKED", blocked["decision"])

        ready = evaluate_source_test_fallback(
            graph_blocker="PARTIAL_LANGUAGE: lua",
            source_owners=("server/packet.cpp",),
            generated_authorities=("tools/generate_packet.py",),
            test_commands=("python -B -m unittest tests.packet",),
            reviewer="QA Lead",
            residual_risk="Lua reflection remains outside graph coverage.",
        )
        self.assertEqual("REVIEWER_ACKNOWLEDGED_FALLBACK", ready["decision"])
        self.assertEqual("BLOCKED", ready["graph_verdict"])
```

- [ ] **Step 6: Implement deterministic comparison and explicit fallback**

Add:

```python
def compare_impact(
    *,
    pre: Mapping[str, object],
    post: Mapping[str, object],
    changed_paths: Sequence[str],
) -> dict[str, object]:
    pre_query = pre.get("query")
    post_query = post.get("query")
    if not isinstance(pre_query, dict) or not isinstance(post_query, dict):
        raise ValueError("pre/post impact artifacts require query objects")
    if pre_query.get("query_id") != post_query.get("query_id"):
        raise ValueError("pre/post impact query identities do not match")
    pre_paths = set(str(item) for item in pre.get("affected_paths", ()))
    post_paths = set(str(item) for item in post.get("affected_paths", ()))
    changed = set(str(item) for item in changed_paths)
    return {
        "query_id": str(pre_query["query_id"]),
        "added_affected_paths": sorted(post_paths - pre_paths),
        "removed_affected_paths": sorted(pre_paths - post_paths),
        "unchanged_affected_paths": sorted(pre_paths & post_paths),
        "changed_not_predicted": sorted(changed - pre_paths),
        "changed_no_longer_affected": sorted(changed & (pre_paths - post_paths)),
    }


def evaluate_source_test_fallback(
    *,
    graph_blocker: str,
    source_owners: Sequence[str],
    generated_authorities: Sequence[str],
    test_commands: Sequence[str],
    reviewer: str,
    residual_risk: str,
) -> dict[str, object]:
    missing: list[str] = []
    if not graph_blocker.strip():
        missing.append("graph blocker")
    if not source_owners:
        missing.append("source owners")
    if not generated_authorities:
        missing.append("generated authorities")
    if not test_commands:
        missing.append("test commands")
    if not reviewer.strip():
        missing.append("reviewer")
    if not residual_risk.strip():
        missing.append("residual risk")
    return {
        "decision": "BLOCKED" if missing else "REVIEWER_ACKNOWLEDGED_FALLBACK",
        "graph_verdict": "BLOCKED",
        "graph_blocker": graph_blocker,
        "source_owners": list(dict.fromkeys(source_owners)),
        "generated_authorities": list(dict.fromkeys(generated_authorities)),
        "test_commands": list(dict.fromkeys(test_commands)),
        "reviewer": reviewer.strip() or None,
        "residual_risk": residual_risk,
        "missing_requirements": missing,
    }
```

If a change has no generated outputs, pass the explicit sentinel `("NOT_APPLICABLE",)` rather than an empty tuple. This prevents absence of generated ownership from being inferred.

- [ ] **Step 7: Run Task 5 tests**

Run:

```powershell
python -B -m unittest tests.studio_project_scaffold.test_codegraph_adapter tests.studio_project_scaffold.test_code_intelligence -v
```

Expected: exit `0` and `OK`. Existing legacy CodeGraph install and preference tests must remain green.

- [ ] **Step 8: Checkpoint without committing**

Run `git diff --check` and inspect the legacy/shared module diff. Confirm no raw provider payload command is executable and no legacy install gate was weakened.

### Task 6: Finalize the single skill, consuming workflows, and agent contracts

**Files:**
- Modify: `skills/code-intelligence-contract/SKILL.md`
- Modify: `skills/studio-project-intake/SKILL.md`
- Modify: `skills/evidence-first-debugging/SKILL.md`
- Modify: `skills/safe-project-mutation/SKILL.md`
- Modify: `skills/review-swarm/SKILL.md`
- Modify: `skills/studio-project-scaffold/SKILL.md`
- Modify: `agents/implementer.toml`
- Modify: `agents/verifier.toml`
- Modify: `agents/investigator.toml`
- Create: `tests/governance/test_code_intelligence_contracts.py`
- Modify: `evals/routing/code-intelligence-contract.json`

- [ ] **Step 1: Add RED governance tests**

Create tests that inspect canonical sources, not generated copies:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CodeIntelligenceContractTests(unittest.TestCase):
    def text(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_exactly_one_vendor_neutral_skill_owns_provider_work(self) -> None:
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        vendor_named = {
            path.parent.name for path in skills
            if path.parent.name in {"graphify", "gitnexus", "understand-anything", "codegraph"}
        }
        self.assertEqual(set(), vendor_named)
        self.assertTrue((ROOT / "skills/code-intelligence-contract/SKILL.md").is_file())

    def test_skill_has_strict_freshness_provenance_and_fallback_rules(self) -> None:
        text = self.text("skills/code-intelligence-contract/SKILL.md")
        required = (
            "STALE_HEAD", "STALE_WORKTREE", "PARTIAL_LANGUAGE",
            "SIDE_EFFECT_VIOLATION", "EMPTY_UNCERTAIN",
            "confidence=INFERRED", "No graph result is not proof",
            "reviewer", "source/test fallback",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertEqual(1, text.count("## Evidence and output contract"))

    def test_consumers_and_agents_own_the_required_pre_post_behavior(self) -> None:
        expected = {
            "skills/studio-project-intake/SKILL.md": ("provider", "index state", "required languages"),
            "skills/evidence-first-debugging/SKILL.md": ("data and control", "source", "runtime"),
            "skills/safe-project-mutation/SKILL.md": ("pre-change impact", "reviewer", "fallback"),
            "skills/review-swarm/SKILL.md": ("dependency/impact lane", "read-only", "runtime PASS"),
            "agents/implementer.toml": ("pre-change impact", "write scope", "escalate"),
            "agents/verifier.toml": ("post-change", "pre/post", "source/tests"),
        }
        for relative, phrases in expected.items():
            text = self.text(relative)
            for phrase in phrases:
                with self.subTest(relative=relative, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_routing_fixture_keeps_neighboring_skills_distinct(self) -> None:
        payload = json.loads(
            self.text("evals/routing/code-intelligence-contract.json")
        )
        self.assertEqual("code-intelligence-contract", payload["target_skill"])
        self.assertGreaterEqual(
            sum(case["type"] == "positive" for case in payload["cases"]), 3
        )
        self.assertGreaterEqual(
            sum(case["type"] == "negative" for case in payload["cases"]), 4
        )
        self.assertGreaterEqual(
            sum(case["type"] == "collision" for case in payload["cases"]), 1
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -B -m unittest tests.governance.test_code_intelligence_contracts -v
```

Expected: exit `1` because the draft skill duplicates output sections and the draft consumers/agents do not yet contain the exact pre/post/fallback contract.

- [ ] **Step 3: Rewrite the shared skill as one normalized contract**

Keep one section for each canonical skill heading in `docs/authoring/skills.md`. Remove the duplicate `Evidence contract`, `Safety`, and `Output` sections from the draft by folding their unique rules into:

- `Required inputs and context discovery`
- `Safety and risk level`
- `Workflow`
- `Provider roles`
- `Evidence and output contract`
- `Handoff contract`
- `Pitfalls and anti-rationalization`
- `Verification checklist`
- `References and scripts`
- `Negative scope`

Use the canonical status names and exact fallback rule from the design. State that Graphify is the experimental opt-in default candidate, not an automatic dependency or mutation gate.

- [ ] **Step 4: Tighten workflow consumers**

Apply these exact ownership rules:

- Intake records provider/version, repository/revision/worktree binding, capability, required languages, artifacts, side effects, and graph blocker. Intake itself may still succeed with a blocked optional graph lane.
- Debugging uses a fresh provider only to guide data/control-path inspection; source/log/test/runtime confirmation owns root cause.
- Safe mutation requires a pre-change impact artifact or `REVIEWER_ACKNOWLEDGED_FALLBACK`. It never widens write ownership automatically.
- Review swarm adds an independent dependency/impact lane only when useful; the lane remains read-only and cannot issue runtime PASS.
- Scaffold references both the shared helper and legacy adapter while retaining current install-plan boundaries.

- [ ] **Step 5: Tighten canonical agent templates**

Use complete instructions:

- Implementer: require pre-change impact query ID, graph status, affected paths, generated authorities, approved write scope, and escalation of newly discovered owners before editing.
- Verifier: require a fresh post-change identity, same query ID, deterministic `compare_impact` output, source/tests, and explicit `BLOCKED` on stale post-change graph.
- Investigator: keep read-only provider context optional and return provider/version/index identity, ambiguity, limitations, and source-confirmed owner paths.

Do not edit `skills/studio-project-scaffold/templates/agents/*.toml` directly.

- [ ] **Step 6: Finalize routing fixtures**

Retain the draft positive/negative/collision cases and add:

- Positive: an inferred AST edge must remain Snapshot.
- Positive: an empty graph result cannot prove absence.
- Negative: pure project intake routes to intake.
- Negative: pure debugging routes to debugging.
- Collision: impact analysis followed by safe mutation routes first to the shared graph contract, then hands off explicitly.

- [ ] **Step 7: Run Task 6 tests and routing**

Run:

```powershell
python -B -m unittest tests.governance.test_code_intelligence_contracts -v
python -B scripts/route_eval.py .
```

Expected: both commands exit `0`; all maintained routing cases pass.

- [ ] **Step 8: Checkpoint without committing**

Run `git diff --check` and inspect only canonical skill, agent, test, and eval paths. Do not stage or commit.

### Task 7: Integrate registries, generated resources, and distribution version

**Files:**
- Modify: `registry/capabilities.yaml`
- Modify: `registry/packs.yaml`
- Modify: `registry/skill-resources.yaml`
- Modify: `registry/upstream-sources.yaml`
- Modify: `scripts/validate.py`
- Modify: `tests/_meta/test_validate.py`
- Modify: `tests/packaging/test_skill_resources.py`
- Modify: `tests/packaging/test_codex_plugin.py`
- Modify: `.codex-plugin/plugin.json`
- Modify: `pyproject.toml`
- Generate: `skills/code-intelligence-contract/scripts/code_intelligence.py`
- Generate: `skills/code-intelligence-contract/schemas/code-intelligence-evidence.schema.json`
- Generate: `skills/code-intelligence-contract/references/code-intelligence-providers.yaml`
- Generate: `skills/studio-project-scaffold/scripts/code_intelligence.py`
- Generate: `skills/studio-project-scaffold/references/code-intelligence-providers.yaml`
- Generate: `skills/studio-project-scaffold/templates/agents/implementer.toml`
- Generate: `skills/studio-project-scaffold/templates/agents/verifier.toml`
- Generate: `skills/studio-project-scaffold/templates/agents/investigator.toml`

- [ ] **Step 1: Add RED registry/resource validation tests**

Add tests that require:

- `code-intelligence-contract` depends on `using-game-studio-skills`, not `studio-project-intake`, avoiding inverted intake ownership.
- `studio-core` includes exactly one `code-intelligence-contract` entry.
- Every provider `upstream_source` exists in `registry/upstream-sources.yaml`.
- Provider IDs are unique and no provider exposes executable argv in YAML.
- The shared helper, evidence schema, and provider registry are bundled inside `code-intelligence-contract` for Hermes individual-skill installs.
- The helper and provider registry are also bundled inside `studio-project-scaffold`.
- Every generated destination begins with the resource-sync ownership marker.

Use exact resource mappings:

```yaml
code-intelligence-contract:
- code_intelligence.py
- source: evals/schema/code-intelligence-evidence.schema.json
  destination: schemas/code-intelligence-evidence.schema.json
- source: registry/code-intelligence-providers.yaml
  destination: references/code-intelligence-providers.yaml
studio-project-scaffold:
- agent_overlay.py
- code_intelligence.py
- codegraph_adapter.py
- gamestudio_cli.py
- project_complexity.py
- project_profile.py
- project_scaffold.py
- project_skill_overlay.py
- safe_mutation.py
- studio_experience.py
- source: registry/code-intelligence-providers.yaml
  destination: references/code-intelligence-providers.yaml
```

Preserve every existing scaffold resource entry; the block above shows the required additions and stable sorted intent, not permission to remove current resources.

- [ ] **Step 2: Run RED validation/resource tests**

Run:

```powershell
python -B -m unittest tests._meta.test_validate tests.packaging.test_skill_resources -v
```

Expected: exit `1` until the provider registry validator and resource mappings are complete.

- [ ] **Step 3: Correct capability and pack ownership**

In `registry/capabilities.yaml` set:

```yaml
- id: code-intelligence-contract
  path: skills/code-intelligence-contract/SKILL.md
  type: gate
  packs:
  - studio-core
  risk_level: read-only
  maturity: experimental
  depends_on:
  - using-game-studio-skills
```

Do not make intake depend on Code Intelligence: the graph lane is optional and intake remains usable when every provider is blocked.

- [ ] **Step 4: Validate provider registry and provenance in `scripts/validate.py`**

Add a validator that calls the strict descriptor loader, verifies upstream IDs against `registry/upstream-sources.yaml`, and emits stable codes:

```python
def _validate_code_intelligence_providers(root: Path, issues: list[Issue]) -> None:
    registry_path = root / "registry" / "code-intelligence-providers.yaml"
    try:
        providers = load_provider_descriptors(registry_path)
    except (OSError, ValueError) as error:
        _issue(issues, "code_intelligence.providers", registry_path, str(error))
        return
    upstream = load_yaml(root / "registry" / "upstream-sources.yaml")
    source_ids = {
        item.get("id") for item in upstream.get("sources", [])
        if isinstance(item, dict)
    }
    for provider in providers:
        if (
            provider.upstream_source is not None
            and provider.upstream_source not in source_ids
        ):
            _issue(
                issues,
                "code_intelligence.upstream",
                registry_path,
                f"{provider.id} references unknown upstream source {provider.upstream_source}",
            )
```

Import from `scripts.code_intelligence` with the same full-clone fallback pattern used by other validator helpers. Call it from the main validation sequence.

- [ ] **Step 5: Verify upstream provenance without mutating research snapshots**

Inspect the existing draft entries and the existing CodeGraph source record. Retain exact commit IDs, license fields, restore paths, and “no copied implementation” wording only when the referenced read-only snapshot or official metadata supports them. If a snapshot is absent or identity cannot be verified, keep the provider descriptor but label provenance verification `BLOCKED` in the case study; do not create or update `.research/`.

- [ ] **Step 6: Bump the distributed payload version**

Change:

- `.codex-plugin/plugin.json`: `1.6.5` to `1.7.0`.
- `pyproject.toml`: `1.6.5` to `1.7.0`.
- `tests/packaging/test_codex_plugin.py` expected version: `1.6.5` to `1.7.0`.

Run `rg -n "1\\.6\\.5" . --glob '!evidence/**' --glob '!.research/**'` and update only authoritative distribution-version assertions. Do not add a version field to `.claude-plugin/marketplace.json` because its current schema has no version field.

- [ ] **Step 7: Regenerate owned resources**

Run:

```powershell
python -B scripts/sync_skill_resources.py .
```

Expected: exit `0` and only declared generated destinations are synchronized. Inspect each listed path. Do not hand-edit any destination.

- [ ] **Step 8: Run Task 7 tests**

Run:

```powershell
python -B -m unittest tests._meta.test_validate tests.packaging.test_skill_resources tests.packaging.test_codex_plugin tests.packaging.test_specialist_agents -v
python -B scripts/sync_skill_resources.py . --check
python -B scripts/validate.py .
```

Expected: all commands exit `0`; resource check reports no drift; validate reports PASS.

- [ ] **Step 9: Checkpoint without committing**

Run `git diff --check` and inspect the version, registries, canonical sources, and generated copies. Confirm marketplace identity remains unchanged and no internal maintenance skill entered distributed registries.

### Task 8: Promote sanitized dogfood evidence and keep deep integration blocked

**Files:**
- Create: `docs/case-studies/graphify-code-intelligence-dogfood.md`
- Modify: `skills/code-intelligence-contract/SKILL.md`
- Modify: `registry/code-intelligence-providers.yaml` only if the documented limitation text needs exact alignment
- Test: `tests/governance/test_code_intelligence_contracts.py`

- [ ] **Step 1: Add a RED durable-evidence test**

Append:

```python
    def test_graphify_dogfood_case_study_preserves_blockers(self) -> None:
        text = self.text("docs/case-studies/graphify-code-intelligence-dogfood.md")
        required = (
            "Graphify 0.9.50",
            "88,955",
            "244,284",
            "84.85%",
            "sample precision 100%",
            "confidence=INFERRED",
            "generated",
            "Lua",
            "C++",
            "cross-repository",
            "The owner-constrained second private project is excluded; no data was accessed or reported.",
            "2026-08-26",
            "33 known C# TaskChangeNotify constructor sites",
            "28 matched",
            "0 extras",
            "28/28=100%",
            "28/33=84.85%",
            "BLOCKED",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -B -m unittest tests.governance.test_code_intelligence_contracts.CodeIntelligenceContractTests.test_graphify_dogfood_case_study_preserves_blockers -v
```

Expected: exit `1` because the durable sanitized case study does not exist.

- [ ] **Step 3: Create the sanitized case study from observed local evidence**

Use only the already summarized authorized private Unity project evidence; do not reopen project-local raw evidence or rerun a provider. Record:

- Exact provider version and AST-only command mode.
- Record the authorized private Unity project node/edge counts, C# sample precision/recall, generated wrapper misses, cross-language miss, parser gaps, and generated-authority gap as `Snapshot`.
- The owner-constrained second private project is excluded; no data was accessed or reported.
- Date the sanitized snapshot 2026-08-26. Record the source-truth comparison method: 33 known C# `TaskChangeNotify` constructor sites, 28 matched, 0 extras, precision 28/28=100%, and recall 28/33=84.85%.
- State that these metrics are a sanitized `Snapshot` of a locally `Verified` comparison. Omit private repository binding and artifact hash, so the durable document does not independently prove current freshness.
- The fact that raw `_origin=ast` included both `EXTRACTED` and `INFERRED` confidence.
- Cross-repository accuracy as `BLOCKED` because the current runs did not demonstrate named source-truth cases across separately bound repositories.
- No private absolute paths, raw mutation commands, raw logs, secrets, or untracked project file lists.
- Overall decision: Graphify remains experimental and opt-in; deep integration is blocked.

Do not copy raw provider output or copyrighted upstream documentation.

- [ ] **Step 4: Link the durable evidence from the shared skill**

In `References and scripts`, point full-clone maintainers to the sanitized case study and keep raw evidence under ignored `evidence/local/`.

- [ ] **Step 5: Run Task 8 tests**

Run:

```powershell
python -B -m unittest tests.governance.test_code_intelligence_contracts -v
python -B scripts/sync_skill_resources.py . --check
```

Expected: exit `0`. Current dogfood evidence is from one authorized private Unity project only; do not run a provider. If changing the canonical skill causes resource drift, run the sync command without `--check` once, inspect the generated files, then rerun `--check`.

- [ ] **Step 6: Checkpoint without committing**

Inspect the case study for sanitized paths and honest `Verified`, `Snapshot`, `Unverified`, and `BLOCKED` wording. Do not commit.

### Task 9: Run full verification and complete the requirement audit

**Files:**
- Verify all changed and generated paths.
- Do not create additional canonical files unless a failing required gate identifies an exact missing owner.

- [ ] **Step 1: Run focused Code Intelligence tests**

Run:

```powershell
python -B -m unittest tests.evals.test_code_intelligence_schema tests.studio_project_scaffold.test_code_intelligence tests.studio_project_scaffold.test_codegraph_adapter tests.governance.test_code_intelligence_contracts -v
```

Expected: exit `0` and `OK`.

- [ ] **Step 2: Run resource synchronization check**

Run:

```powershell
python -B scripts/sync_skill_resources.py . --check
```

Expected: exit `0` and `skill-resources: 0 generated file(s) already in sync`.

- [ ] **Step 3: Run the full unit suite**

Run:

```powershell
python -B -m unittest discover -s tests -p "test_*.py"
```

Expected: exit `0` and `OK`. Record the observed test count; do not reuse an earlier count.

- [ ] **Step 4: Run every required local gate**

Run each command separately and record its exit code:

```powershell
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
```

Expected: every command exits `0`. A lifecycle audit that lacks upstream, model, live-project, or session-history evidence remains `BLOCKED` rather than being converted to PASS.

- [ ] **Step 5: Run lifecycle audits required by this feature**

Run:

```powershell
python -B scripts/check_originality.py .
python -B scripts/catalog_audit.py .
```

Expected: record the actual exit code and artifact. `catalog_audit.py` may honestly remain `BLOCKED` under the repository contract; do not weaken its gate.

- [ ] **Step 6: Inspect the final diff and ownership**

Run:

```powershell
git diff --check
git status --short
git diff --stat
git diff -- .codex-plugin/plugin.json pyproject.toml registry scripts skills agents tests evals docs/case-studies
```

Expected:

- No edit under `.research/`.
- No vendor-named skill directory.
- Generated files carry the resource-sync marker and match canonical sources.
- Existing unrelated tracked/untracked work remains present.
- No commit, push, publish, provider install/index/query, or dogfood-project mutation occurred.

- [ ] **Step 7: Complete a requirement-by-requirement audit**

Create the final handoff matrix in the response, not a new repository file:

| Requirement | Authoritative evidence |
|---|---|
| Shared vendor-neutral layer | Shared skill, provider registry, helper tests |
| Graphify/GitNexus/Understand Anything/CodeGraph roles | Provider registry and validation |
| No vendor skills | Governance test and `skills/` inspection |
| Intake/debug/mutation/review integration | Canonical skill diffs and governance tests |
| Implementer pre-impact/verifier post-impact | Agent templates and comparison tests |
| Freshness/language/side-effect blocking | Strict status tests and schema |
| Extracted versus inferred evidence | Per-edge tests and schema |
| Empty result uncertainty | `EMPTY_UNCERTAIN` test and skill contract |
| Legacy CodeGraph compatibility | Full legacy adapter tests |
| Dogfood before deep integration | Sanitized case study and experimental provider descriptor |
| Distribution integrity | Resource sync, packaging tests, `1.7.0` metadata |
| Repository health | Full local gates with fresh exit codes |

Any missing, indirect, stale, or failing evidence keeps the corresponding item incomplete or `BLOCKED`.

- [ ] **Step 8: Handoff without committing**

Report repository/path, branch/HEAD, goal, owned scope, preserved do-not-touch scope, files changed, generated files, commands and exit codes, `Verified` results, `Snapshot` assumptions, `Unverified` hypotheses, `BLOCKED` items, failures, decisions, restore information, and next actions. State explicitly that no commit/push occurred and ask separately if the user wants a commit.
