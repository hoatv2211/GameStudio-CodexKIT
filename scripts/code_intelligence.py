from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

try:
    from scripts.common import load_yaml
except ModuleNotFoundError:
    from common import load_yaml


PROVIDERS = ("graphify", "gitnexus", "understand-anything", "codegraph")

CANONICAL_STATES = frozenset(
    {
        "UNAVAILABLE",
        "NOT_INITIALIZED",
        "FRESH",
        "STALE_HEAD",
        "STALE_WORKTREE",
        "PARTIAL_LANGUAGE",
        "BROKEN",
        "SIDE_EFFECT_VIOLATION",
        "USER_DISABLED",
    }
)
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

# Kept for callers of the provisional helper. New status values are always
# canonical; legacy values are normalized before evidence classification.
FRESH_STATES = frozenset({"FRESH", "INITIALIZED_HEALTHY"})

ALLOWED_ROLES = frozenset(
    {
        "experimental-default",
        "advanced-optional",
        "onboarding-optional",
        "legacy-compatible",
    }
)
ALLOWED_CAPABILITIES = frozenset(
    {
        "status",
        "context",
        "dependency-path",
        "impact",
        "cross-repo",
        "pdg",
        "taint",
        "architecture",
        "domain-flow",
        "onboarding",
    }
)
PROVIDER_KEYS = frozenset(
    {
        "id",
        "display_name",
        "role",
        "maturity",
        "priority",
        "opt_in_required",
        "terms_review_required",
        "capabilities",
        "limitations",
        "upstream_source",
    }
)

SOURCE_EDGE_KINDS = {"EXTRACTED", "AST", "SOURCE"}
INFERRED_EDGE_KINDS = {"INFERRED", "AMBIGUOUS", "SEMANTIC", "LLM"}
CONFIDENCE_TO_PROVENANCE = {
    "EXTRACTED": "SOURCE_EXTRACTED",
    "INFERRED": "INFERRED",
    "AMBIGUOUS": "INFERRED",
    "SEMANTIC": "SEMANTIC",
    "LLM": "LLM",
    "UNKNOWN": "UNKNOWN",
}
ORIGIN_TO_PROVENANCE = {
    "ast": "SOURCE_EXTRACTED",
    "source": "SOURCE_EXTRACTED",
    "inferred": "INFERRED",
    "semantic": "SEMANTIC",
    "llm": "LLM",
}
SOURCE_DERIVED_ORIGINS = frozenset({"ast", "source"})
EDGE_FIELDS = frozenset(
    {"relation", "source", "target", "source_locator", "origin", "confidence"}
)
COMMAND_FIELDS = frozenset({"command", "exit_code"})
NO_GRAPH_RESULT_LIMITATION = (
    "No graph result is not proof that no dependency exists."
)
_KEBAB_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SHA256_ID_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


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


class GitTextRunner(Protocol):
    """Read-only runner for one Git command returning text stdout."""

    def __call__(self, args: list[str], *, cwd: Path) -> str:
        ...


def _default_git_text_runner(args: list[str], *, cwd: Path) -> str:
    """Run a Git text command without invoking a shell or writing state."""

    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        shell=False,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() if result.stderr else ""
        suffix = f": {detail}" if detail else ""
        command = " ".join(["git", *args])
        raise ValueError(
            f"git command failed ({command!s}, return code {result.returncode}){suffix}"
        )
    return result.stdout or ""


def capture_repository_identity(
    root: Path | str,
    *,
    runner: GitTextRunner | None = None,
    untracked_content_identity: str | None = None,
) -> RepositoryIdentity:
    """Capture a deterministic, read-only identity for a repository snapshot.

    The worktree digest includes Git's status stream and binary staged/unstaged
    diffs, but deliberately never opens files named by the status stream.
    """

    root_path = Path(root)
    command = runner or _default_git_text_runner
    try:
        root_path = root_path.resolve()
        repository = command(["rev-parse", "--show-toplevel"], cwd=root_path).strip()
        revision = command(["rev-parse", "HEAD"], cwd=root_path).strip()
        status = command(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root_path,
        )
        unstaged = command(["diff", "--binary"], cwd=root_path)
        staged = command(["diff", "--binary", "--cached"], cwd=root_path)
        repository_path = (
            Path(repository).resolve().as_posix()
            if repository
            else root_path.as_posix()
        )
    except (OSError, ValueError) as error:
        return RepositoryIdentity(
            repository=root_path.as_posix(),
            revision=None,
            worktree_identity=None,
            complete=False,
            limitations=(f"repository identity unavailable: {error}",),
        )

    has_untracked = any(
        entry.startswith("?? ")
        for entry in status.split("\0")
        if entry
    )
    supplied_untracked_identity = (
        untracked_content_identity.strip().casefold()
        if isinstance(untracked_content_identity, str)
        else None
    )
    if (
        supplied_untracked_identity is not None
        and _SHA256_ID_RE.fullmatch(supplied_untracked_identity) is None
    ):
        supplied_untracked_identity = None

    digest = hashlib.sha256()
    for value in (repository, revision, status, unstaged, staged):
        encoded = value.encode("utf-8", errors="surrogateescape")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    if has_untracked and supplied_untracked_identity is not None:
        encoded = supplied_untracked_identity.encode("ascii")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)

    limitations: tuple[str, ...] = ()
    if has_untracked and supplied_untracked_identity is None:
        limitations = (
            "untracked worktree content identity is unavailable; path-only metadata cannot prove freshness",
        )

    return RepositoryIdentity(
        repository=repository_path,
        revision=revision or None,
        worktree_identity=f"sha256:{digest.hexdigest()}",
        complete=bool(
            repository
            and revision
            and (not has_untracked or supplied_untracked_identity is not None)
        ),
        limitations=limitations,
    )


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


def default_provider_registry_path(module_path: Path | str = __file__) -> Path:
    """Resolve the canonical or bundled provider registry next to a helper."""

    module = Path(module_path).resolve()
    candidates = (
        module.parent.parent / "registry" / "code-intelligence-providers.yaml",
        module.parent.parent / "references" / "code-intelligence-providers.yaml",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError("code-intelligence provider registry is unavailable")


def _text_list(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and not value:
        return False
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return False
    return len(value) == len(set(value))


def load_provider_descriptors(
    path: Path | str | None = None,
) -> tuple[ProviderDescriptor, ...]:
    """Load and strictly validate the provider-neutral YAML registry."""

    registry_path = Path(path) if path is not None else default_provider_registry_path()
    document = load_yaml(registry_path)
    if not isinstance(document, dict) or set(document) != {"schema_version", "providers"}:
        raise ValueError("code-intelligence provider registry has an invalid top-level schema")
    schema_version = document["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
        or not isinstance(document["providers"], list)
    ):
        raise ValueError("code-intelligence provider registry schema_version must be 1")

    providers: list[ProviderDescriptor] = []
    seen_ids: set[str] = set()
    seen_priorities: set[int] = set()
    for raw in document["providers"]:
        if not isinstance(raw, dict) or set(raw) != PROVIDER_KEYS:
            raise ValueError("code-intelligence provider descriptor has invalid keys")

        provider_id = raw["id"]
        if (
            not isinstance(provider_id, str)
            or _KEBAB_RE.fullmatch(provider_id) is None
            or provider_id in seen_ids
        ):
            raise ValueError(f"invalid or duplicate provider id: {provider_id!r}")

        capabilities = raw["capabilities"]
        if (
            not _text_list(capabilities, allow_empty=False)
            or any(item not in ALLOWED_CAPABILITIES for item in capabilities)
        ):
            raise ValueError(f"invalid capabilities for provider {provider_id}")

        limitations = raw["limitations"]
        upstream_source = raw["upstream_source"]
        priority = raw["priority"]
        if (
            not isinstance(raw["display_name"], str)
            or not raw["display_name"].strip()
            or not isinstance(raw["role"], str)
            or raw["role"] not in ALLOWED_ROLES
            or not isinstance(raw["maturity"], str)
            or not raw["maturity"].strip()
            or not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority in seen_priorities
            or not isinstance(raw["opt_in_required"], bool)
            or not isinstance(raw["terms_review_required"], bool)
            or not _text_list(limitations, allow_empty=True)
            or (
                upstream_source is not None
                and (
                    not isinstance(upstream_source, str)
                    or _KEBAB_RE.fullmatch(upstream_source) is None
                )
            )
        ):
            raise ValueError(f"invalid descriptor for provider {provider_id}")

        seen_ids.add(provider_id)
        seen_priorities.add(priority)
        providers.append(
            ProviderDescriptor(
                id=provider_id,
                display_name=raw["display_name"],
                role=raw["role"],
                maturity=raw["maturity"],
                priority=priority,
                opt_in_required=raw["opt_in_required"],
                terms_review_required=raw["terms_review_required"],
                capabilities=tuple(capabilities),
                limitations=tuple(limitations),
                upstream_source=upstream_source,
            )
        )
    providers.sort(key=lambda item: item.priority)
    return tuple(providers)


def get_provider_descriptor(
    provider: str,
    *,
    registry_path: Path | str | None = None,
) -> ProviderDescriptor:
    provider_id = provider.casefold() if isinstance(provider, str) else ""
    for descriptor in load_provider_descriptors(registry_path):
        if descriptor.id == provider_id:
            return descriptor
    raise ValueError(f"unsupported code-intelligence provider: {provider}")


def provider_descriptors() -> list[dict[str, object]]:
    """Compatibility view retained for the legacy CodeGraph adapter."""

    return [asdict(descriptor) for descriptor in load_provider_descriptors()]


def normalize_index_state(state: str) -> str:
    normalized = state.upper() if isinstance(state, str) else ""
    if normalized in CANONICAL_STATES:
        return normalized
    return LEGACY_STATE_MAP.get(normalized, "BROKEN")


INDEX_MANIFEST_KEYS = frozenset(
    {
        "provider",
        "provider_version",
        "repository",
        "revision",
        "worktree_identity",
        "capabilities",
        "languages",
        "artifact_paths",
        "artifacts_validated",
    }
)


def _validated_index_manifest(
    raw: Mapping[str, object],
    *,
    provider: str,
) -> dict[str, object]:
    if not isinstance(raw, Mapping) or set(raw) != INDEX_MANIFEST_KEYS or raw.get("provider") != provider:
        raise ValueError("provider index manifest has invalid keys or provider")
    for field in ("provider_version", "repository", "revision", "worktree_identity"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"provider index manifest {field} is invalid")
    for field in ("capabilities", "languages", "artifact_paths"):
        values = raw.get(field)
        if not _text_list(values, allow_empty=False):
            raise ValueError(f"provider index manifest {field} is invalid")
        if field == "capabilities" and any(
            item not in ALLOWED_CAPABILITIES for item in values
        ):
            raise ValueError(f"provider index manifest {field} is invalid")
        if field == "languages" and len(_normalized_language_tokens(values)) != len(values):
            raise ValueError(f"provider index manifest {field} is invalid")
    if raw.get("artifacts_validated") is not True:
        raise ValueError("provider index artifacts are not validated")
    return dict(raw)


def _normalized_language_tokens(
    values: Sequence[object],
    *,
    field: str = "languages",
) -> tuple[str, ...]:
    """Normalize language names while preserving first-seen deterministic order."""

    if (
        isinstance(values, (str, bytes, Mapping))
        or not isinstance(values, Sequence)
        or any(not isinstance(item, str) or not item.strip() for item in values)
    ):
        raise ValueError(f"{field} must contain nonblank strings")
    return tuple(
        dict.fromkeys(
            item.strip().casefold() for item in values
        )
    )


def _status_for_identity(
    identity: RepositoryIdentity,
    descriptor: ProviderDescriptor,
    *,
    manifest: Mapping[str, object] | None,
    required_capability: str | None,
    required_languages: Sequence[str],
    after_identity: RepositoryIdentity | None,
    observed_side_effects: Sequence[str],
    discovered_artifacts: Sequence[str],
    user_disabled: bool,
) -> CodeIntelligenceStatus:
    required = _normalized_language_tokens(
        required_languages,
        field="required_languages",
    )
    limitations = list(descriptor.limitations)
    side_effects = tuple(dict.fromkeys(str(item) for item in observed_side_effects))
    artifacts = tuple(str(item) for item in discovered_artifacts)

    if side_effects:
        state = "SIDE_EFFECT_VIOLATION"
    elif user_disabled:
        state = "USER_DISABLED"
    elif after_identity is not None and (
        after_identity.repository != identity.repository
        or after_identity.revision != identity.revision
        or after_identity.worktree_identity != identity.worktree_identity
    ):
        state = "STALE_WORKTREE"
        limitations.append("repository identity changed during provider operation")
    elif not identity.complete:
        state = "BROKEN"
        limitations.extend(identity.limitations)
    elif manifest is None:
        state = "STALE_HEAD" if artifacts else "NOT_INITIALIZED"
        limitations.append("provider artifact lacks a repository/index identity manifest")
    else:
        try:
            checked = _validated_index_manifest(manifest, provider=descriptor.id)
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
                artifact_paths=artifacts,
                side_effects=side_effects,
                limitations=tuple(dict.fromkeys([*limitations, str(error)])),
            )

        capabilities = tuple(str(item) for item in checked["capabilities"])
        languages = _normalized_language_tokens(checked["languages"])
        missing = tuple(language for language in required if language not in languages)
        unsupported_capabilities = tuple(
            capability
            for capability in capabilities
            if capability not in descriptor.capabilities
        )
        if checked["repository"] != identity.repository:
            state = "BROKEN"
            limitations.append("provider manifest repository mismatch")
        elif checked["revision"] != identity.revision:
            # An index bound to another HEAD cannot be fresh.
            state = "STALE_HEAD"
        elif checked["worktree_identity"] != identity.worktree_identity:
            state = "STALE_WORKTREE"
        elif unsupported_capabilities:
            state = "BROKEN"
            limitations.append(
                "provider manifest capabilities unsupported by "
                f"{descriptor.id}: {', '.join(unsupported_capabilities)}"
            )
        elif (
            required_capability is not None
            and (
                required_capability not in descriptor.capabilities
                or required_capability not in capabilities
            )
        ):
            state = "BROKEN"
            limitations.append(f"capability mismatch: {required_capability}")
        elif missing:
            state = "PARTIAL_LANGUAGE"
        else:
            state = "FRESH"
        return CodeIntelligenceStatus(
            provider=descriptor.id,
            provider_version=str(checked["provider_version"]),
            repository=identity.repository,
            revision=identity.revision,
            worktree_identity=identity.worktree_identity,
            index_revision=str(checked["revision"]),
            index_worktree_identity=str(checked["worktree_identity"]),
            index_state=state,
            capabilities=capabilities,
            required_languages=required,
            supported_languages=languages,
            missing_languages=missing,
            artifact_paths=tuple(str(item) for item in checked["artifact_paths"]),
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
        artifact_paths=artifacts,
        side_effects=side_effects,
        limitations=tuple(dict.fromkeys(limitations)),
    )


def inspect_provider(
    root: str | Path | RepositoryIdentity,
    provider: str,
    *,
    manifest: Mapping[str, object] | None = None,
    required_capability: str | None = None,
    required_languages: Sequence[str] = (),
    registry_path: Path | str | None = None,
    after_identity: RepositoryIdentity | None = None,
    observed_side_effects: Sequence[str] = (),
    discovered_artifacts: Sequence[str] = (),
    user_disabled: bool = False,
) -> CodeIntelligenceStatus:
    """Inspect a provider without executing provider commands.

    The path-based form preserves the provisional artifact-only compatibility
    helper. The identity/manifest form validates semantic freshness: required
    language coverage and index identity must match before ``FRESH`` is emitted.
    """

    descriptor = get_provider_descriptor(provider, registry_path=registry_path)
    if isinstance(root, RepositoryIdentity):
        return _status_for_identity(
            root,
            descriptor,
            manifest=manifest,
            required_capability=required_capability,
            required_languages=required_languages,
            after_identity=after_identity,
            observed_side_effects=observed_side_effects,
            discovered_artifacts=discovered_artifacts,
            user_disabled=user_disabled,
        )

    root_path = Path(root).resolve()
    artifact_map = {
        "graphify": ("graphify-out/GRAPH_REPORT.md", "graphify-out/graph.json"),
        "gitnexus": (".gitnexus/",),
        "understand-anything": (
            ".ua/knowledge-graph.json",
            ".understand-anything/knowledge-graph.json",
        ),
        "codegraph": (".codegraph/",),
    }
    artifacts = tuple(path for path in artifact_map[descriptor.id] if (root_path / path).exists())
    identity = RepositoryIdentity(str(root_path), None, None, False)
    # Artifact-only probing cannot establish a complete identity, so it is
    # intentionally reported as stale/not initialized rather than fresh.
    state = "STALE_HEAD" if artifacts else "NOT_INITIALIZED"
    return CodeIntelligenceStatus(
        provider=descriptor.id,
        provider_version=None,
        repository=str(root_path),
        revision=identity.revision,
        worktree_identity=identity.worktree_identity,
        index_revision=None,
        index_worktree_identity=None,
        index_state=state,
        capabilities=descriptor.capabilities,
        required_languages=(),
        supported_languages=(),
        missing_languages=(),
        artifact_paths=artifacts,
        side_effects=(),
        limitations=descriptor.limitations,
    )


LEGACY_STRING_COLLECTION_FIELDS = (
    "resolved_subjects",
    "affected_paths",
    "dependencies",
    "dependency_paths",
    "paths",
    "nodes",
    "symbols",
)


def _legacy_string_collection(value: object) -> bool:
    return (
        not isinstance(value, (str, bytes))
        and isinstance(value, Sequence)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _legacy_edge_item(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    for source_field, target_field in (
        ("source", "target"),
        ("from", "to"),
        ("caller", "callee"),
    ):
        source = value.get(source_field)
        target = value.get(target_field)
        if (
            isinstance(source, str)
            and source.strip()
            and isinstance(target, str)
            and target.strip()
        ):
            return True
    return False


def _legacy_edge_collection(value: object) -> bool:
    return (
        not isinstance(value, (str, bytes))
        and isinstance(value, Sequence)
        and bool(value)
        and all(_legacy_edge_item(item) for item in value)
    )


def _legacy_has_direct_dependency_evidence(result: Mapping[str, object]) -> bool:
    if any(
        _legacy_string_collection(result.get(field))
        for field in LEGACY_STRING_COLLECTION_FIELDS
        if field in result
    ):
        return True
    return "edges" in result and _legacy_edge_collection(result["edges"])


def _legacy_has_dependency_evidence(result: object) -> bool:
    if not isinstance(result, Mapping):
        return False
    if _legacy_has_direct_dependency_evidence(result):
        return True
    nested_results = result.get("results")
    if (
        isinstance(nested_results, Sequence)
        and not isinstance(nested_results, (str, bytes))
        and bool(nested_results)
        and all(isinstance(item, Mapping) for item in nested_results)
    ):
        return any(
            _legacy_has_direct_dependency_evidence(item)
            for item in nested_results
        )
    return False


def _legacy_result_texts(
    result: object,
    *,
    fields: Sequence[str],
) -> tuple[str, ...]:
    if not isinstance(result, Mapping):
        return ()
    for field in fields:
        values = result.get(field)
        if _legacy_string_collection(values):
            return tuple(dict.fromkeys(item.strip() for item in values))
    return ()


def _normalize_legacy_evidence(
    *,
    provider: str,
    provider_version: str | None,
    repository: str,
    revision: str | None,
    index_state: str,
    edge_kind: str,
    result: object,
    limitations: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    """Route the legacy call shape through the canonical fail-closed contract."""

    provider_id = provider.casefold()
    if provider_id not in PROVIDERS:
        raise ValueError(f"unsupported code-intelligence provider: {provider}")
    state = normalize_index_state(index_state)
    notes = list(limitations)
    notes.append(
        "Legacy input lacks complete canonical repository/worktree/index identity; "
        "caller-declared freshness or edge provenance cannot establish PASS."
    )
    status = CodeIntelligenceStatus(
        provider=provider_id,
        provider_version=provider_version,
        repository=repository,
        revision=revision,
        worktree_identity=None,
        index_revision=revision,
        index_worktree_identity=None,
        index_state=state,
        capabilities=("dependency-path",),
        required_languages=(),
        supported_languages=(),
        missing_languages=(),
        artifact_paths=(),
        side_effects=(),
        limitations=tuple(notes),
    )
    return normalize_evidence(
        status=status,
        capability="dependency-path",
        query={
            "query_id": f"legacy:{provider_id}:dependency-path",
            "subjects": ["legacy provider query"],
        },
        resolved_subjects=_legacy_result_texts(
            result,
            fields=("resolved_subjects",),
        ),
        affected_paths=_legacy_result_texts(
            result,
            fields=("affected_paths", "dependency_paths", "paths"),
        ),
        next_action=(
            "Capture complete canonical repository/worktree/index identity before "
            "using legacy graph evidence."
        ),
    )


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"code-intelligence {field} must be a nonblank string")
    return value


def _optional_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field=field)


def _normalized_texts(values: Sequence[object], *, field: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"code-intelligence {field} must be a sequence")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _required_text(value, field=field)
        if text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _normalized_kebab_texts(values: Sequence[object], *, field: str) -> list[str]:
    normalized = _normalized_texts(values, field=field)
    result: list[str] = []
    seen: set[str] = set()
    for value in normalized:
        normalized_value = value.strip().casefold()
        if _KEBAB_RE.fullmatch(normalized_value) is None:
            raise ValueError(f"code-intelligence {field} contains an invalid token")
        if normalized_value not in seen:
            seen.add(normalized_value)
            result.append(normalized_value)
    return result


def _normalize_query(raw: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(raw, Mapping) or set(raw) != {"query_id", "subjects"}:
        raise ValueError("code-intelligence query has invalid fields")
    query_id = _required_text(raw["query_id"], field="query query_id")
    raw_subjects = raw["subjects"]
    if isinstance(raw_subjects, (str, bytes)) or not isinstance(raw_subjects, Sequence):
        raise ValueError("code-intelligence query subjects must be a sequence")
    subjects = _normalized_texts(raw_subjects, field="query subject")
    if len(subjects) != 1 or len(raw_subjects) != 1:
        raise ValueError("code-intelligence query must contain exactly one subject")
    return {"query_id": query_id, "subjects": subjects}


def _normalize_edge(raw: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(raw, Mapping) or set(raw) != EDGE_FIELDS:
        raise ValueError("code-intelligence edge has invalid fields")
    normalized = {
        field: _required_text(raw[field], field=f"edge {field}")
        for field in ("relation", "source", "target", "source_locator")
    }
    origin = _required_text(raw["origin"], field="edge origin").strip().casefold()
    raw_confidence = _required_text(raw["confidence"], field="edge confidence")
    confidence = raw_confidence.strip().upper()
    if confidence not in CONFIDENCE_TO_PROVENANCE:
        confidence = "UNKNOWN"
    if origin in SOURCE_DERIVED_ORIGINS:
        provenance = CONFIDENCE_TO_PROVENANCE[confidence]
    else:
        provenance = ORIGIN_TO_PROVENANCE.get(origin, "UNKNOWN")
    return {
        **normalized,
        "origin": origin,
        "confidence": confidence,
        "provenance": provenance,
    }


def _normalize_edges(
    edges: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    if isinstance(edges, (str, bytes)) or not isinstance(edges, Sequence):
        raise ValueError("code-intelligence edges must be a sequence")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for raw in edges:
        edge = _normalize_edge(raw)
        marker = tuple(edge[field] for field in (*EDGE_FIELDS, "provenance"))
        if marker not in seen:
            seen.add(marker)
            normalized.append(edge)
    return normalized


def _normalize_commands(
    commands: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(commands, (str, bytes)) or not isinstance(commands, Sequence):
        raise ValueError("code-intelligence commands must be a sequence")
    normalized: list[dict[str, object]] = []
    seen: set[tuple[str, int | None]] = set()
    for raw in commands:
        if not isinstance(raw, Mapping) or set(raw) != COMMAND_FIELDS:
            raise ValueError("code-intelligence command has invalid fields")
        command = _required_text(raw["command"], field="command")
        exit_code = raw["exit_code"]
        if exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            raise ValueError("code-intelligence command exit_code must be an integer or null")
        marker = (command, exit_code)
        if marker not in seen:
            seen.add(marker)
            normalized.append({"command": command, "exit_code": exit_code})
    return normalized


def normalize_evidence(
    *,
    status: CodeIntelligenceStatus | None = None,
    capability: str | None = None,
    query: Mapping[str, object] | None = None,
    resolved_subjects: Sequence[str] = (),
    edges: Sequence[Mapping[str, object]] = (),
    affected_paths: Sequence[str] = (),
    generated_boundaries: Sequence[str] = (),
    source_confirmations: Sequence[str] = (),
    test_confirmations: Sequence[str] = (),
    disagreements: Sequence[str] = (),
    commands: Sequence[Mapping[str, object]] = (),
    artifacts: Sequence[str] = (),
    next_action: str = (
        "Confirm important graph findings against authoritative source and tests."
    ),
    **legacy: Any,
) -> dict[str, object]:
    """Normalize provider-neutral evidence without upgrading inference into proof.

    The provisional provider-specific call form remains accepted until legacy
    CodeGraph callers migrate to this normalized artifact contract.
    """

    if status is None:
        if capability is not None or query is not None:
            raise ValueError("code-intelligence status is required")
        return _normalize_legacy_evidence(**legacy)
    if not isinstance(status, CodeIntelligenceStatus):
        raise ValueError("code-intelligence status is invalid")
    if legacy:
        raise ValueError("legacy evidence fields cannot be mixed with normalized fields")

    provider = _required_text(status.provider, field="provider").strip().casefold()
    if _KEBAB_RE.fullmatch(provider) is None:
        raise ValueError("code-intelligence provider is invalid")
    repository = _required_text(status.repository, field="repository")
    provider_version = _optional_text(status.provider_version, field="provider_version")
    revision = _optional_text(status.revision, field="revision")
    worktree_identity = _optional_text(
        status.worktree_identity, field="worktree_identity"
    )
    index_revision = _optional_text(status.index_revision, field="index_revision")
    index_worktree_identity = _optional_text(
        status.index_worktree_identity, field="index_worktree_identity"
    )
    capabilities = _normalized_kebab_texts(
        status.capabilities, field="capabilities"
    )
    required_languages = _normalized_kebab_texts(
        status.required_languages, field="required_languages"
    )
    supported_languages = _normalized_kebab_texts(
        status.supported_languages, field="supported_languages"
    )
    declared_missing_languages = _normalized_kebab_texts(
        status.missing_languages, field="missing_languages"
    )
    actual_missing_languages = [
        language
        for language in required_languages
        if language not in supported_languages
    ]
    side_effects = _normalized_texts(status.side_effects, field="side_effects")
    limitations = _normalized_texts(status.limitations, field="limitations")
    status_artifacts = _normalized_texts(
        status.artifact_paths,
        field="artifact_paths",
    )

    normalized_capability = _required_text(capability, field="capability").strip().casefold()
    if _KEBAB_RE.fullmatch(normalized_capability) is None:
        raise ValueError("code-intelligence capability is invalid")
    if query is None:
        raise ValueError("code-intelligence query is required")
    normalized_query = _normalize_query(query)
    subjects = _normalized_texts(resolved_subjects, field="resolved_subjects")
    normalized_edges = _normalize_edges(edges)
    paths = _normalized_texts(affected_paths, field="affected_paths")
    boundaries = _normalized_texts(
        generated_boundaries, field="generated_boundaries"
    )
    source_checks = _normalized_texts(
        source_confirmations, field="source_confirmations"
    )
    test_checks = _normalized_texts(test_confirmations, field="test_confirmations")
    normalized_disagreements = _normalized_texts(
        disagreements, field="disagreements"
    )
    normalized_commands = _normalize_commands(commands)
    supplied_artifacts = _normalized_texts(artifacts, field="artifacts")
    normalized_artifacts = list(
        dict.fromkeys([*status_artifacts, *supplied_artifacts])
    )
    normalized_next_action = _required_text(next_action, field="next_action")

    state = normalize_index_state(status.index_state)
    if declared_missing_languages != actual_missing_languages:
        limitations.append(
            "Declared missing-language coverage disagreed with required and supported languages."
        )
    missing_languages = actual_missing_languages
    if side_effects:
        state = "SIDE_EFFECT_VIOLATION"
        limitations.append("Observed provider side effects forced a blocked state.")
    elif missing_languages:
        if state != "PARTIAL_LANGUAGE":
            limitations.append(
                "Missing required language coverage forced a blocked partial-language state."
            )
        state = "PARTIAL_LANGUAGE"
    elif declared_missing_languages != actual_missing_languages:
        state = "BROKEN"
    elif state == "FRESH":
        identity_limitations: list[str] = []
        if provider_version is None:
            identity_limitations.append("Fresh provider version is unavailable.")
        if not status_artifacts:
            identity_limitations.append("Fresh index artifact binding is unavailable.")
        if any(
            value is None
            for value in (
                revision,
                worktree_identity,
                index_revision,
                index_worktree_identity,
            )
        ):
            identity_limitations.append("Fresh index identity is incomplete.")
        else:
            if revision != index_revision:
                identity_limitations.append("Fresh index revision identity mismatch.")
            if worktree_identity != index_worktree_identity:
                identity_limitations.append("Fresh index worktree identity mismatch.")
        if identity_limitations:
            state = "BROKEN"
            limitations.extend(identity_limitations)

    limitations.append(NO_GRAPH_RESULT_LIMITATION)
    if state in BLOCKED_STATES:
        query_state, evidence_label, graph_verdict = (
            "STATUS_BLOCKED",
            "BLOCKED",
            "BLOCKED",
        )
        limitations.append(
            "Graph evidence is unavailable until index status is fresh and supported."
        )
    elif normalized_capability not in capabilities:
        query_state, evidence_label, graph_verdict = (
            "CAPABILITY_MISMATCH",
            "BLOCKED",
            "BLOCKED",
        )
        limitations.append(f"capability mismatch: {normalized_capability}")
    elif len(subjects) != 1 and (subjects or normalized_edges or paths):
        query_state, evidence_label, graph_verdict = (
            "AMBIGUOUS",
            "BLOCKED",
            "BLOCKED",
        )
        if subjects:
            limitations.append("Multiple resolved candidates require explicit disambiguation.")
        else:
            limitations.append(
                "Dependency evidence without one resolved subject cannot support a graph conclusion."
            )
    elif not subjects and not normalized_edges and not paths:
        query_state, evidence_label, graph_verdict = (
            "EMPTY_UNCERTAIN",
            "Unverified",
            "UNVERIFIED",
        )
    elif normalized_edges and all(
        edge["provenance"] == "SOURCE_EXTRACTED" for edge in normalized_edges
    ) and not normalized_disagreements:
        query_state, evidence_label, graph_verdict = (
            "COMPLETE",
            "Verified",
            "PASS",
        )
        limitations.append(
            "Verified applies to source extraction at this snapshot, not runtime behavior or complete recall."
        )
    else:
        query_state, evidence_label, graph_verdict = (
            "COMPLETE",
            "Snapshot",
            "UNVERIFIED",
        )
        if normalized_disagreements:
            limitations.append(
                "Disagreements require authoritative source or runtime confirmation."
            )
        else:
            limitations.append(
                "Inferred, semantic, LLM, or unknown edges require source or runtime confirmation."
            )

    evidence = {
        "schema_version": 1,
        "provider": provider,
        "provider_version": provider_version,
        "repository": repository,
        "revision": revision,
        "worktree_identity": worktree_identity,
        "index_revision": index_revision,
        "index_worktree_identity": index_worktree_identity,
        "index_state": state,
        "capability": normalized_capability,
        "query": normalized_query,
        "resolved_subjects": subjects,
        "required_languages": required_languages,
        "supported_languages": supported_languages,
        "missing_languages": missing_languages,
        "affected_paths": paths,
        "generated_boundaries": boundaries,
        "edges": normalized_edges,
        "query_state": query_state,
        "evidence_label": evidence_label,
        "graph_verdict": graph_verdict,
        "source_confirmations": source_checks,
        "test_confirmations": test_checks,
        "side_effects": side_effects,
        "limitations": list(dict.fromkeys(limitations)),
        "disagreements": normalized_disagreements,
        "commands": normalized_commands,
        "artifacts": normalized_artifacts,
        "next_action": normalized_next_action,
    }
    validate_evidence_semantics(evidence)
    return evidence


CANONICAL_EVIDENCE_FIELDS = frozenset(
    {
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
        "next_action",
    }
)
SOURCE_TEST_FALLBACK_FIELDS = frozenset(
    {
        "decision",
        "graph_verdict",
        "graph_blocker",
        "source_owners",
        "known_callers",
        "known_consumers",
        "generated_authorities",
        "test_commands",
        "reviewer",
        "residual_risk",
        "missing_requirements",
    }
)


def _validate_source_test_fallback(raw: object) -> None:
    if not isinstance(raw, Mapping) or set(raw) != SOURCE_TEST_FALLBACK_FIELDS:
        raise ValueError("canonical source_test_fallback has invalid fields")
    decision = raw["decision"]
    if decision not in {"BLOCKED", "REVIEWER_ACKNOWLEDGED_FALLBACK"}:
        raise ValueError("canonical source_test_fallback decision is invalid")
    if raw["graph_verdict"] != "BLOCKED":
        raise ValueError("canonical source_test_fallback graph verdict must be BLOCKED")

    graph_blocker = _fallback_text(raw["graph_blocker"], field="graph blocker")
    residual_risk = _fallback_text(raw["residual_risk"], field="residual risk")
    if graph_blocker != raw["graph_blocker"] or residual_risk != raw["residual_risk"]:
        raise ValueError("canonical source_test_fallback text is not normalized")
    reviewer = raw["reviewer"]
    if reviewer is not None:
        normalized_reviewer = _required_text(reviewer, field="reviewer").strip()
        if reviewer != normalized_reviewer:
            raise ValueError("canonical source_test_fallback reviewer is not normalized")

    normalized_lists: dict[str, list[str]] = {}
    for field in (
        "source_owners",
        "known_callers",
        "known_consumers",
        "generated_authorities",
        "test_commands",
        "missing_requirements",
    ):
        values = raw[field]
        if not isinstance(values, list):
            raise ValueError(f"canonical source_test_fallback {field} must be an array")
        normalized = _normalized_handoff_texts(values, field=field)
        if normalized != values:
            raise ValueError(f"canonical source_test_fallback {field} is not normalized")
        normalized_lists[field] = normalized

    if decision == "REVIEWER_ACKNOWLEDGED_FALLBACK":
        authorities, authorities_valid = _generated_authority_status(
            normalized_lists["generated_authorities"]
        )
        if (
            not graph_blocker
            or not normalized_lists["source_owners"]
            or not normalized_lists["known_callers"]
            or not normalized_lists["known_consumers"]
            or not authorities_valid
            or authorities != normalized_lists["generated_authorities"]
            or not normalized_lists["test_commands"]
            or reviewer is None
            or not residual_risk
            or normalized_lists["missing_requirements"]
        ):
            raise ValueError(
                "acknowledged source_test_fallback is missing required evidence"
            )
    elif not normalized_lists["missing_requirements"]:
        raise ValueError("blocked source_test_fallback requires missing requirements")


def validate_evidence_semantics(evidence: Mapping[str, object]) -> None:
    """Fail closed on cross-field evidence rules JSON Schema cannot express."""

    if not isinstance(evidence, Mapping):
        raise ValueError("canonical code-intelligence evidence must be a mapping")
    missing_fields = sorted(CANONICAL_EVIDENCE_FIELDS - set(evidence))
    if missing_fields:
        raise ValueError(
            "canonical code-intelligence evidence is missing fields: "
            + ", ".join(missing_fields)
        )
    unexpected_fields = sorted(
        set(evidence) - CANONICAL_EVIDENCE_FIELDS - {"source_test_fallback"}
    )
    if unexpected_fields:
        raise ValueError(
            "canonical code-intelligence evidence has unexpected fields: "
            + ", ".join(unexpected_fields)
        )
    if "source_test_fallback" in evidence:
        _validate_source_test_fallback(evidence["source_test_fallback"])
        if (
            evidence["evidence_label"] != "BLOCKED"
            or evidence["graph_verdict"] != "BLOCKED"
        ):
            raise ValueError(
                "source_test_fallback requires top-level BLOCKED graph evidence"
            )
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        raise ValueError("canonical code-intelligence schema_version must be 1")

    provider = _required_text(evidence["provider"], field="provider").strip().casefold()
    capability = _required_text(
        evidence["capability"],
        field="capability",
    ).strip().casefold()
    if _KEBAB_RE.fullmatch(provider) is None or _KEBAB_RE.fullmatch(capability) is None:
        raise ValueError("canonical code-intelligence provider or capability is invalid")
    if evidence["provider"] != provider or evidence["capability"] != capability:
        raise ValueError("canonical code-intelligence provider or capability is not normalized")
    if _normalize_query(evidence["query"]) != evidence["query"]:
        raise ValueError("canonical code-intelligence query is not normalized")
    for field in (
        "resolved_subjects",
        "affected_paths",
        "generated_boundaries",
        "source_confirmations",
        "test_confirmations",
        "limitations",
        "disagreements",
        "artifacts",
        "side_effects",
    ):
        if not isinstance(evidence[field], list):
            raise ValueError(f"canonical code-intelligence {field} must be an array")
        if _normalized_texts(evidence[field], field=field) != evidence[field]:
            raise ValueError(f"canonical code-intelligence {field} is not normalized")
    for field in (
        "required_languages",
        "supported_languages",
        "missing_languages",
    ):
        if not isinstance(evidence[field], list):
            raise ValueError(f"canonical code-intelligence {field} must be an array")
        if _normalized_kebab_texts(evidence[field], field=field) != evidence[field]:
            raise ValueError(f"canonical code-intelligence {field} is not normalized")
    normalized_edges = evidence["edges"]
    if not isinstance(normalized_edges, list):
        raise ValueError("canonical code-intelligence edges must be an array")
    seen_edges: set[tuple[str, ...]] = set()
    normalized_edge_fields = EDGE_FIELDS | {"provenance"}
    for raw_edge in normalized_edges:
        if not isinstance(raw_edge, Mapping) or set(raw_edge) != normalized_edge_fields:
            raise ValueError("canonical code-intelligence edge has invalid fields")
        edge_values = {
            field: _required_text(raw_edge[field], field=f"edge {field}")
            for field in normalized_edge_fields
        }
        if edge_values["origin"] != edge_values["origin"].strip().casefold():
            raise ValueError("canonical code-intelligence edge origin is not normalized")
        if edge_values["confidence"] not in CONFIDENCE_TO_PROVENANCE:
            raise ValueError("canonical code-intelligence edge confidence is invalid")
        if edge_values["provenance"] not in set(CONFIDENCE_TO_PROVENANCE.values()) | {
            "UNKNOWN"
        }:
            raise ValueError("canonical code-intelligence edge provenance is invalid")
        reconstructed_edge = _normalize_edge(
            {
                field: raw_edge[field]
                for field in EDGE_FIELDS
            }
        )
        if reconstructed_edge != dict(raw_edge):
            raise ValueError(
                "canonical code-intelligence edge provenance is inconsistent"
            )
        edge_marker = tuple(edge_values[field] for field in sorted(normalized_edge_fields))
        if edge_marker in seen_edges:
            raise ValueError("canonical code-intelligence edges must be unique")
        seen_edges.add(edge_marker)
    if not isinstance(evidence["commands"], list):
        raise ValueError("canonical code-intelligence commands must be an array")
    if _normalize_commands(evidence["commands"]) != evidence["commands"]:
        raise ValueError("canonical code-intelligence commands are not normalized")
    _required_text(evidence["next_action"], field="next_action")
    if evidence["query_state"] not in {
        "COMPLETE",
        "STATUS_BLOCKED",
        "EMPTY_UNCERTAIN",
        "AMBIGUOUS",
        "CAPABILITY_MISMATCH",
    }:
        raise ValueError("canonical code-intelligence query_state is invalid")
    if evidence["evidence_label"] not in {
        "Verified",
        "Snapshot",
        "Unverified",
        "BLOCKED",
    }:
        raise ValueError("canonical code-intelligence evidence_label is invalid")
    if evidence["graph_verdict"] not in {"PASS", "UNVERIFIED", "BLOCKED"}:
        raise ValueError("canonical code-intelligence graph_verdict is invalid")

    state = evidence["index_state"]
    if not isinstance(state, str) or state not in CANONICAL_STATES:
        raise ValueError("canonical code-intelligence index state is invalid")
    provider_version = _optional_text(
        evidence["provider_version"],
        field="provider_version",
    )
    repository = _required_text(evidence["repository"], field="repository")
    revision = _optional_text(evidence["revision"], field="revision")
    worktree_identity = _optional_text(
        evidence["worktree_identity"],
        field="worktree_identity",
    )
    index_revision = _optional_text(
        evidence["index_revision"],
        field="index_revision",
    )
    index_worktree_identity = _optional_text(
        evidence["index_worktree_identity"],
        field="index_worktree_identity",
    )
    required = _normalized_kebab_texts(
        evidence["required_languages"],
        field="required_languages",
    )
    supported = _normalized_kebab_texts(
        evidence["supported_languages"],
        field="supported_languages",
    )
    declared_missing = _normalized_kebab_texts(
        evidence["missing_languages"],
        field="missing_languages",
    )
    actual_missing = [language for language in required if language not in supported]
    if declared_missing != actual_missing:
        raise ValueError(
            "canonical code-intelligence missing_languages do not match coverage"
        )
    artifacts = _normalized_texts(evidence["artifacts"], field="artifacts")
    side_effects = _normalized_texts(evidence["side_effects"], field="side_effects")

    if side_effects and state != "SIDE_EFFECT_VIOLATION":
        raise ValueError(
            "canonical code-intelligence side effects require SIDE_EFFECT_VIOLATION"
        )
    if state == "FRESH":
        if provider_version is None:
            raise ValueError("fresh code-intelligence evidence requires provider version")
        if not artifacts:
            raise ValueError("fresh code-intelligence evidence requires artifacts")
        if not repository:
            raise ValueError("fresh code-intelligence evidence requires repository")
        if any(
            value is None
            for value in (
                revision,
                worktree_identity,
                index_revision,
                index_worktree_identity,
            )
        ):
            raise ValueError("fresh code-intelligence evidence requires complete identity")
        if revision != index_revision:
            raise ValueError("fresh code-intelligence revision binding does not match")
        if worktree_identity != index_worktree_identity:
            raise ValueError("fresh code-intelligence worktree binding does not match")
        if actual_missing:
            raise ValueError("fresh code-intelligence evidence lacks language coverage")
        if side_effects:
            raise ValueError("fresh code-intelligence evidence contains side effects")

    graph_verdict = evidence["graph_verdict"]
    query_state = evidence["query_state"]
    evidence_label = evidence["evidence_label"]
    resolved_subjects = evidence["resolved_subjects"]
    disagreements = evidence["disagreements"]

    if state in BLOCKED_STATES and (
        query_state != "STATUS_BLOCKED"
        or evidence_label != "BLOCKED"
        or graph_verdict != "BLOCKED"
    ):
        raise ValueError("blocked index state requires blocked graph evidence")
    if query_state in {"AMBIGUOUS", "CAPABILITY_MISMATCH"} and (
        evidence_label != "BLOCKED" or graph_verdict != "BLOCKED"
    ):
        raise ValueError("blocked query state requires blocked graph evidence")
    if query_state == "EMPTY_UNCERTAIN" and (
        resolved_subjects
        or evidence["affected_paths"]
        or normalized_edges
        or evidence_label != "Unverified"
        or graph_verdict != "UNVERIFIED"
        or NO_GRAPH_RESULT_LIMITATION not in evidence["limitations"]
    ):
        raise ValueError("empty graph result requires explicit unverified evidence")
    if evidence_label == "BLOCKED" and graph_verdict != "BLOCKED":
        raise ValueError("BLOCKED evidence label requires BLOCKED graph verdict")
    if graph_verdict == "BLOCKED" and evidence_label != "BLOCKED":
        raise ValueError("BLOCKED graph verdict requires BLOCKED evidence label")
    if graph_verdict == "UNVERIFIED" and evidence_label not in {
        "Snapshot",
        "Unverified",
    }:
        raise ValueError("UNVERIFIED graph verdict requires non-verified evidence")
    if graph_verdict == "PASS":
        if (
            state != "FRESH"
            or query_state != "COMPLETE"
            or evidence_label != "Verified"
            or len(resolved_subjects) != 1
            or not normalized_edges
            or disagreements
            or any(
                edge["confidence"] != "EXTRACTED"
                or edge["provenance"] != "SOURCE_EXTRACTED"
                for edge in normalized_edges
            )
        ):
            raise ValueError(
                "graph PASS requires fresh, complete, unambiguous source-extracted evidence"
            )


def _normalized_handoff_texts(
    values: Sequence[object],
    *,
    field: str,
) -> list[str]:
    if (
        isinstance(values, (str, bytes, Mapping))
        or not isinstance(values, Sequence)
    ):
        raise ValueError(f"code-intelligence {field} must be a sequence")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _required_text(value, field=field).strip()
        if text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def compare_impact(
    *,
    pre: Mapping[str, object],
    post: Mapping[str, object],
    changed_paths: Sequence[str],
) -> dict[str, object]:
    """Compare identity-bound impact artifacts deterministically."""

    if not isinstance(pre, Mapping) or not isinstance(post, Mapping):
        raise ValueError("pre/post impact artifacts must be mappings")
    validate_evidence_semantics(pre)
    validate_evidence_semantics(post)
    for name, artifact in (("pre", pre), ("post", post)):
        if artifact["index_state"] != "FRESH":
            raise ValueError(f"{name} impact artifact must have a fresh index")
        if artifact["capability"] != "impact":
            raise ValueError(f"{name} impact artifact must use the impact capability")
        if artifact["query_state"] != "COMPLETE":
            raise ValueError(f"{name} impact artifact must have a complete query")
        if len(artifact["resolved_subjects"]) != 1:
            raise ValueError(
                f"{name} impact artifact must resolve exactly one subject"
            )
        if artifact["graph_verdict"] == "BLOCKED":
            raise ValueError(f"{name} impact artifact cannot be graph-blocked")

    for field in ("provider", "provider_version", "repository"):
        if pre[field] != post[field]:
            raise ValueError(f"pre/post impact {field} identities do not match")
    pre_query = pre.get("query")
    post_query = post.get("query")
    if not isinstance(pre_query, Mapping) or not isinstance(post_query, Mapping):
        raise ValueError("pre/post impact artifacts require query objects")
    normalized_pre_query = _normalize_query(pre_query)
    normalized_post_query = _normalize_query(post_query)
    pre_query_id = str(normalized_pre_query["query_id"]).strip()
    post_query_id = str(normalized_post_query["query_id"]).strip()
    if pre_query_id != post_query_id:
        raise ValueError("pre/post impact query identities do not match")
    if normalized_pre_query != normalized_post_query:
        raise ValueError("pre/post impact query subjects do not match")
    if "affected_paths" not in pre or "affected_paths" not in post:
        raise ValueError("pre/post impact artifacts require affected_paths")

    pre_paths = set(
        _normalized_handoff_texts(
            pre["affected_paths"],
            field="pre affected_paths",
        )
    )
    post_paths = set(
        _normalized_handoff_texts(
            post["affected_paths"],
            field="post affected_paths",
        )
    )
    changed = set(
        _normalized_handoff_texts(changed_paths, field="changed_paths")
    )
    if changed and (
        pre["revision"] == post["revision"]
        and pre["worktree_identity"] == post["worktree_identity"]
    ):
        raise ValueError(
            "pre/post impact transition must bind distinct repository snapshots"
        )
    removed = pre_paths - post_paths
    return {
        "query_id": pre_query_id,
        "added_affected_paths": sorted(post_paths - pre_paths),
        "removed_affected_paths": sorted(removed),
        "unchanged_affected_paths": sorted(pre_paths & post_paths),
        "changed_not_predicted": sorted(changed - pre_paths),
        "changed_no_longer_affected": sorted(changed & removed),
    }


def _fallback_text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"code-intelligence {field} must be a string")
    return value.strip()


def _generated_authority_status(
    values: Sequence[str],
) -> tuple[list[str], bool]:
    normalized = _normalized_handoff_texts(
        values,
        field="generated authorities",
    )
    raw = [value.strip() for value in values]
    sentinel_tokens = [
        value for value in raw if value.casefold() == "not_applicable"
    ]
    if sentinel_tokens and (
        raw != ["NOT_APPLICABLE"]
        or sentinel_tokens != ["NOT_APPLICABLE"]
    ):
        return [], False
    return normalized, bool(normalized)


def evaluate_source_test_fallback(
    *,
    graph_blocker: str,
    source_owners: Sequence[str],
    known_callers: Sequence[str] = (),
    known_consumers: Sequence[str] = (),
    generated_authorities: Sequence[str],
    test_commands: Sequence[str],
    reviewer: str,
    residual_risk: str,
) -> dict[str, object]:
    """Record reviewer-owned source/test fallback without upgrading the graph."""

    blocker = _fallback_text(graph_blocker, field="graph blocker")
    owners = _normalized_handoff_texts(source_owners, field="source owners")
    callers = _normalized_handoff_texts(known_callers, field="known callers")
    consumers = _normalized_handoff_texts(known_consumers, field="known consumers")
    authorities, authorities_valid = _generated_authority_status(
        generated_authorities,
    )
    commands = _normalized_handoff_texts(test_commands, field="test commands")
    reviewer_name = _fallback_text(reviewer, field="reviewer")
    risk = _fallback_text(residual_risk, field="residual risk")

    missing: list[str] = []
    if not blocker:
        missing.append("graph blocker")
    if not owners:
        missing.append("source owners")
    if not callers:
        missing.append("known callers")
    if not consumers:
        missing.append("known consumers")
    if not authorities_valid:
        missing.append("generated authorities")
    if not commands:
        missing.append("test commands")
    if not reviewer_name:
        missing.append("reviewer")
    if not risk:
        missing.append("residual risk")
    return {
        "decision": "BLOCKED" if missing else "REVIEWER_ACKNOWLEDGED_FALLBACK",
        "graph_verdict": "BLOCKED",
        "graph_blocker": blocker,
        "source_owners": owners,
        "known_callers": callers,
        "known_consumers": consumers,
        "generated_authorities": authorities,
        "test_commands": commands,
        "reviewer": reviewer_name or None,
        "residual_risk": risk,
        "missing_requirements": missing,
    }
