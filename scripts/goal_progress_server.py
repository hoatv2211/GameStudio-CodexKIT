from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from scripts.goal_progress_core import (
        EVENT_KEYS,
        GoalProgressError,
        canonical_json,
        sanitize_summary,
    )
    from scripts.goal_progress_store import (
        GoalLock,
        GoalPaths,
        ProgressWriter,
        _assert_goal_target,
        _assert_path_safe,
        atomic_write_json,
        replay_goal,
    )
except ModuleNotFoundError:
    from goal_progress_core import (
        EVENT_KEYS,
        GoalProgressError,
        canonical_json,
        sanitize_summary,
    )
    from goal_progress_store import (
        GoalLock,
        GoalPaths,
        ProgressWriter,
        _assert_goal_target,
        _assert_path_safe,
        atomic_write_json,
        replay_goal,
    )


DEFAULT_IDLE_TIMEOUT_SECONDS = 1800
MAX_EVENT_BYTES = 256 * 1024
MAX_CONCURRENT_REQUESTS = 8
REQUEST_READ_DEADLINE_SECONDS = 0.75
RUNTIME_IDENTITY_LOCK = "runtime-identity.lock"
RUNTIME_RECOVERY_JOURNAL = "recovery-journal.json"
SHUTDOWN_COMPLETE_KEY = "shutdown_complete"
PUBLIC_SESSION_COOKIE_PREFIX = "goal_progress_session_"
PUBLIC_TOKEN_LIFETIME_SECONDS = 60.0
PUBLIC_EVENT_POLL_SECONDS = 0.25
PUBLIC_EVENT_HEARTBEAT_SECONDS = 15.0
PUBLIC_EVENT_LIMIT = 100
PUBLIC_EVENT_SCAN_BYTES = 2 * 1024 * 1024
PUBLIC_JSON_LIMIT = 1024 * 1024
PUBLIC_PARTIAL_HISTORY_WARNING = (
    "Earlier events are excluded by the bounded public history window; "
    "attempt and elapsed values are unavailable, and displayed evidence and "
    "trigger history may be partial."
)
PUBLIC_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; font-src 'none'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'none'"
)
PUBLIC_ARTIFACT_TYPES = {
    ".json": "text/plain; charset=utf-8",
    ".jsonl": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}
PUBLIC_FORCED_DOWNLOAD_TYPES = frozenset({".htm", ".html", ".svg", ".xml"})
PUBLIC_STATE_FIELDS = (
    "goal_state",
    "plan_version",
    "packets",
    "progress",
    "eta",
    "revision_history",
    "latest_evidence",
    "next_action",
    "stale",
    "warnings",
)
PUBLIC_PACKET_FIELDS = ("id", "objective", "owner", "status", "progress_weight")
PUBLIC_PROGRESS_FIELDS = (
    "verified_weight",
    "active_planned_weight",
    "percent",
    "display_percent",
)
PUBLIC_ETA_FIELDS = (
    "status",
    "summary",
    "low_seconds",
    "high_seconds",
    "calibration_factor",
    "confidence",
    "warnings",
    "reason",
)
PUBLIC_REVISION_FIELDS = (
    "event_id",
    "sequence",
    "previous_plan_version",
    "plan_version",
    "revision_reason",
    "approval_ref",
    "previous_manifest_hash",
    "new_manifest_hash",
    "progress_recalculated",
    "eta_recalculated",
)
PUBLIC_CONTEXT_FIELDS = (
    "status",
    "count_kind",
    "count",
    "target",
    "hard_cap",
    "text",
    "required_fact_refs",
    "evidence_label",
)
PUBLIC_EVENT_FIELDS = (
    "sequence",
    "emitted_at",
    "event_type",
    "summary",
    "packet_id",
    "plan_version",
)
PUBLIC_DIAGNOSTIC_STATES = frozenset({"waiting_input", "blocked", "failed"})
PUBLIC_ETA_TRIGGER_TYPES = frozenset(
    {
        "goal.started",
        "plan.revised",
        "packet.started",
        "packet.retry_started",
        "packet.resumed",
        "packet.waiting_input",
        "packet.blocked",
        "packet.failed",
        "packet.verified",
        "runtime.heartbeat",
    }
)
PUBLIC_INTEGRATION_FIELDS = (
    "status",
    "reason",
    "runtime_version",
    "recognized_methods",
    "portable_progress_available",
)
DOS_SHORT_NAME_COMPONENT = re.compile(
    r"^[^~]{1,6}~[0-9]+(?:\.[^.]*)?$", re.IGNORECASE
)
PUBLIC_COMMAND_SCAN_LIMIT = 4096
PUBLIC_COMMAND_REDACTION = "[REDACTED]"
PUBLIC_COMMAND_INVALID = "[REDACTED: command omitted]"
PUBLIC_COMMAND_TOO_LONG = "[OMITTED: command exceeds public limit]"
PUBLIC_COMMAND_SECRET_IDENTIFIERS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "xapikey",
        "apikey",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "token",
        "password",
        "passwd",
        "secret",
    }
)
PUBLIC_COMMAND_ENV_SUFFIXES = (
    "api_key",
    "token",
    "secret",
    "password",
    "private_key",
    "access_key",
)
PUBLIC_COMMAND_WORD_SEPARATORS = frozenset({";", "|", "&"})
PUBLIC_COMMAND_ESCAPE_CHARACTERS = frozenset({"\\", "`", "^"})
RECOVERY_STATES = frozenset({"launching", "pending-start", "cleanup-ready"})
PENDING_RUNTIME_INFO_KEYS = frozenset(
    {
        "recovery_state",
        "goal_root",
        "pid",
        "submission_token_sha256",
        "process_creation_time",
        "process_fingerprint",
    }
)
RUNTIME_INFO_KEYS = frozenset(
    {
        "goal_root",
        "pid",
        "private_port",
        "writer_epoch_id",
        "instance_nonce",
        "idle_timeout_seconds",
    }
)


class SystemClock:
    def utc_now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def monotonic(self) -> float:
        return time.monotonic()


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_CONCURRENT_REQUESTS

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        self._request_count_lock = threading.Lock()
        self._active_request_count = 0
        super().__init__(*args, **kwargs)

    @property
    def active_request_count(self) -> int:
        with self._request_count_lock:
            return self._active_request_count

    def process_request(self, request: object, client_address: object) -> None:
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self._request_count_lock:
            self._active_request_count += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_finished()
            raise

    def process_request_thread(self, request: object, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_finished()

    def _request_finished(self) -> None:
        with self._request_count_lock:
            self._active_request_count -= 1
        self._request_slots.release()


def _json_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


def _safe_reason(value: object) -> str:
    text, _warnings = sanitize_summary(str(value), limit=500)
    return text or "runtime request failed"


def _read_capability(path: Path) -> str:
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise GoalProgressError("runtime credential is unavailable")
    if target.stat().st_size > 4096:
        raise GoalProgressError("runtime credential file is invalid")
    capability = target.read_text(encoding="utf-8")
    if not capability or capability != capability.strip():
        raise GoalProgressError("runtime credential file is invalid")
    return capability


def _read_runtime_info(path: Path) -> dict[str, object]:
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise GoalProgressError("runtime metadata is unavailable")
    if target.stat().st_size > 64 * 1024:
        raise GoalProgressError("runtime metadata is invalid")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoalProgressError("runtime metadata is invalid") from exc
    if not isinstance(value, dict) or not RUNTIME_INFO_KEYS.issubset(value):
        raise GoalProgressError("runtime metadata is invalid")
    return value


def _read_pending_runtime_info(path: Path) -> dict[str, object] | None:
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        return None
    if target.stat().st_size > 64 * 1024:
        raise GoalProgressError("pending runtime recovery identity is invalid")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoalProgressError(
            "pending runtime recovery identity is invalid"
        ) from exc
    if not isinstance(value, dict) or value.get("recovery_state") != "pending-start":
        return None
    if (
        frozenset(value) != PENDING_RUNTIME_INFO_KEYS
        or not isinstance(value.get("goal_root"), str)
        or isinstance(value.get("pid"), bool)
        or not isinstance(value.get("pid"), int)
        or int(value["pid"]) <= 0
        or not isinstance(value.get("submission_token_sha256"), str)
        or len(str(value["submission_token_sha256"])) != 64
        or not isinstance(value.get("process_creation_time"), str)
        or not str(value["process_creation_time"]).strip()
        or not isinstance(value.get("process_fingerprint"), str)
        or len(str(value["process_fingerprint"])) != 64
    ):
        raise GoalProgressError("pending runtime recovery identity is invalid")
    return value


def _recovery_journal_path(paths: GoalPaths) -> Path:
    return paths.runtime / RUNTIME_RECOVERY_JOURNAL


def _read_recovery_journal(paths: GoalPaths) -> dict[str, object] | None:
    target = _recovery_journal_path(paths)
    if not target.exists():
        return None
    if not target.is_file() or target.is_symlink() or target.stat().st_size > 64 * 1024:
        raise GoalProgressError("runtime recovery journal is invalid")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoalProgressError("runtime recovery journal is invalid") from exc
    if not isinstance(value, dict) or value.get("recovery_state") not in RECOVERY_STATES:
        raise GoalProgressError("runtime recovery journal is invalid")
    state = value["recovery_state"]
    common = {
        "recovery_state",
        "goal_root",
        "submission_token_sha256",
        "command_fingerprint",
    }
    if (
        not isinstance(value.get("goal_root"), str)
        or not isinstance(value.get("submission_token_sha256"), str)
        or len(str(value["submission_token_sha256"])) != 64
        or not isinstance(value.get("command_fingerprint"), str)
        or len(str(value["command_fingerprint"])) != 64
    ):
        raise GoalProgressError("runtime recovery journal is invalid")
    if state == "launching" and set(value) != common:
        raise GoalProgressError("runtime recovery journal is invalid")
    if state == "pending-start":
        required = common | {"pid", "process_creation_time", "process_fingerprint"}
        if (
            set(value) != required
            or isinstance(value.get("pid"), bool)
            or not isinstance(value.get("pid"), int)
            or int(value["pid"]) <= 0
            or not isinstance(value.get("process_creation_time"), str)
            or not str(value["process_creation_time"]).strip()
            or not isinstance(value.get("process_fingerprint"), str)
            or len(str(value["process_fingerprint"])) != 64
        ):
            raise GoalProgressError("runtime recovery journal is invalid")
    if state == "cleanup-ready":
        required = common | {"writer_info_sha256", "remaining_files"}
        remaining = value.get("remaining_files")
        if (
            set(value) != required
            or value.get("writer_info_sha256") is not None
            and (
                not isinstance(value.get("writer_info_sha256"), str)
                or len(str(value["writer_info_sha256"])) != 64
            )
            or not isinstance(remaining, list)
            or remaining != ["submission-token", "server-info.json", "writer-info.json"]
        ):
            raise GoalProgressError("runtime recovery journal is invalid")
    return value


def _legacy_or_journal_pending(paths: GoalPaths) -> dict[str, object] | None:
    journal = _read_recovery_journal(paths)
    if journal is not None and journal.get("recovery_state") == "pending-start":
        return journal
    return _read_pending_runtime_info(paths.writer_info)


def request_private_json(
    runtime_info: dict[str, object],
    capability: str,
    method: str,
    route: str,
    payload: object | None = None,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    port = runtime_info.get("private_port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise GoalProgressError("runtime private port is invalid")
    data = None
    headers = {"Authorization": f"Bearer {capability}"}
    if method == "POST":
        data = b"" if payload is None else _json_bytes(payload)
        if payload is not None:
            headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{route}",
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read(MAX_EVENT_BYTES + 1)
    if len(raw) > MAX_EVENT_BYTES:
        raise GoalProgressError("runtime response is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GoalProgressError("runtime response is invalid") from exc
    if not isinstance(value, dict):
        raise GoalProgressError("runtime response is invalid")
    return value


def _pid_is_running(pid: object) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def _identity_matches(
    goal_root: Path,
    runtime_info: dict[str, object],
    health: dict[str, object],
) -> bool:
    expected_root = str(Path(goal_root).resolve())
    if set(health) != {
        "goal_root",
        "pid",
        "writer_epoch_id",
        "instance_nonce",
    }:
        return False
    return (
        runtime_info.get("goal_root") == expected_root
        and health.get("goal_root") == expected_root
        and runtime_info.get("pid") == health.get("pid")
        and _pid_is_running(runtime_info.get("pid"))
        and runtime_info.get("writer_epoch_id") == health.get("writer_epoch_id")
        and runtime_info.get("instance_nonce") == health.get("instance_nonce")
        and isinstance(runtime_info.get("private_port"), int)
        and not isinstance(runtime_info.get("private_port"), bool)
    )


def _shutdown_completion_matches(
    paths: GoalPaths, expected: dict[str, object]
) -> bool:
    try:
        completed = _read_runtime_info(paths.writer_info)
    except GoalProgressError:
        return False
    return completed.get(SHUTDOWN_COMPLETE_KEY) is True and all(
        completed.get(key) == expected.get(key) for key in RUNTIME_INFO_KEYS
    )


def _writer_lock_is_available(paths: GoalPaths) -> bool:
    try:
        with GoalLock(paths.runtime / "writer.lock", timeout_seconds=0.05):
            return True
    except (GoalProgressError, TimeoutError):
        return False


def runtime_is_reusable(
    goal_root: Path,
    runtime_token_file: Path,
    *,
    timeout_seconds: float = 5.0,
) -> bool:
    try:
        paths = GoalPaths.from_root(Path(goal_root))
        info = _read_runtime_info(paths.writer_info)
        capability = _read_capability(Path(runtime_token_file))
        health = request_private_json(
            info,
            capability,
            "GET",
            "/health",
            timeout_seconds=timeout_seconds,
        )
    except (GoalProgressError, OSError, urllib.error.URLError):
        return False
    return _identity_matches(paths.root, info, health)


def detached_process_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        )
    else:
        options["start_new_session"] = True
    return options


def _runtime_python_executable() -> str:
    if os.name == "nt":
        base_executable = getattr(sys, "_base_executable", None)
        if isinstance(base_executable, str) and Path(base_executable).is_file():
            return base_executable
    return sys.executable


def discover_dashboard_assets(script_path: Path | None = None) -> Path:
    script = Path(script_path or __file__).resolve()
    candidates = (
        script.parent.parent / "resources" / "goal-progress",
        script.parent.parent / "assets",
    )
    for candidate in candidates:
        try:
            safe = _assert_path_safe(
                candidate, must_exist=True, require_directory=True
            )
        except GoalProgressError:
            continue
        if all((safe / name).is_file() for name in ("index.html", "styles.css", "app.js")):
            return safe
    raise GoalProgressError("dashboard assets are unavailable")


def _read_public_json(path: Path, label: str) -> dict[str, object] | None:
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink() or path.stat().st_size > PUBLIC_JSON_LIMIT:
        raise GoalProgressError(f"{label} is unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoalProgressError(f"{label} is unavailable") from exc
    if not isinstance(value, dict):
        raise GoalProgressError(f"{label} is unavailable")
    return value


def _public_fields(
    value: dict[str, object], fields: tuple[str, ...]
) -> dict[str, object]:
    return {field: value[field] for field in fields if field in value}


def _public_text(value: object, *, limit: int = 500) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    sanitized, _warnings = sanitize_summary(value, limit=limit)
    return sanitized or None


def _public_revision(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    required_integer_fields = ("sequence", "previous_plan_version", "plan_version")
    required_hash_fields = ("previous_manifest_hash", "new_manifest_hash")
    event_id = _public_text(value.get("event_id"), limit=200)
    reason = _public_text(value.get("revision_reason"))
    approval = _public_text(value.get("approval_ref"))
    if event_id is None or reason is None or approval is None:
        return None
    if any(
        not isinstance(value.get(field), int) or isinstance(value.get(field), bool)
        for field in required_integer_fields
    ):
        return None
    if any(
        not isinstance(value.get(field), str)
        or re.fullmatch(r"[a-f0-9]{64}", str(value.get(field))) is None
        for field in required_hash_fields
    ):
        return None
    if value.get("progress_recalculated") is not True or value.get("eta_recalculated") is not True:
        return None
    projected = _public_fields(value, PUBLIC_REVISION_FIELDS)
    projected["event_id"] = event_id
    projected["revision_reason"] = reason
    projected["approval_ref"] = approval
    return projected


def _public_command_identifier_end(value: str, start: int) -> int:
    end = start
    while end < len(value) and (value[end].isalnum() or value[end] in "_-"):
        end += 1
    return end


def _public_command_shell_words(
    value: str,
    contexts: list[str | None],
    escaped: list[bool],
) -> list[tuple[int, int, str, tuple[int, ...]]]:
    words: list[tuple[int, int, str, tuple[int, ...]]] = []
    index = 0
    while index < len(value):
        if contexts[index] is None and not escaped[index] and (
            value[index].isspace() or value[index] in PUBLIC_COMMAND_WORD_SEPARATORS
        ):
            index += 1
            continue

        start = index
        semantic: list[str] = []
        positions: list[int] = []
        while index < len(value):
            character = value[index]
            if contexts[index] is None and not escaped[index] and (
                character.isspace() or character in PUBLIC_COMMAND_WORD_SEPARATORS
            ):
                break
            if (
                character in PUBLIC_COMMAND_ESCAPE_CHARACTERS
                and index + 1 < len(value)
                and escaped[index + 1]
            ):
                index += 1
                continue
            if character in {"'", '"'} and not escaped[index]:
                index += 1
                continue
            semantic.append(character)
            positions.append(index)
            index += 1
        words.append((start, index, "".join(semantic), tuple(positions)))
    return words


def _public_command_raw_identifier(
    value: str,
    word: tuple[int, int, str, tuple[int, ...]],
    semantic_stop: int,
    escaped: list[bool],
) -> str:
    start, end, _semantic, positions = word
    raw_stop = positions[semantic_stop - 1] + 1
    while (
        raw_stop < end
        and value[raw_stop] in {"'", '"'}
        and not escaped[raw_stop]
    ):
        raw_stop += 1
    return value[start:raw_stop]


def _public_command_identifier_spelling_supported(
    raw_identifier: str, semantic_identifier: str
) -> bool:
    return raw_identifier == semantic_identifier or (
        len(raw_identifier) == len(semantic_identifier) + 2
        and raw_identifier[0] in {"'", '"'}
        and raw_identifier[-1] == raw_identifier[0]
        and raw_identifier[1:-1] == semantic_identifier
    )


def _public_command_sensitive_option_end(value: str) -> int | None:
    if value.startswith("--"):
        name_start = 2
    elif value.startswith(("-", "/")):
        name_start = 1
    else:
        return None
    name_end = _public_command_identifier_end(value, name_start)
    if name_end == name_start or not _public_command_secret_identifier(
        value[name_start:name_end], environment=False
    ):
        return None
    return name_end


def _public_command_sensitive_assignment_end(value: str) -> int | None:
    environment = value[:5].casefold() == "$env:"
    name_start = 5 if environment else 0
    name_end = _public_command_identifier_end(value, name_start)
    identifier = value[name_start:name_end]
    if name_end == name_start or not (
        identifier.casefold() == "key"
        or _public_command_secret_identifier(identifier, environment=True)
    ):
        return None
    if name_end >= len(value) or value[name_end] not in "=:":
        return None
    return name_end


def _public_command_has_unsafe_credential_syntax(
    value: str,
    contexts: list[str | None],
    escaped: list[bool],
) -> bool:
    words = _public_command_shell_words(value, contexts, escaped)
    for word_index, word in enumerate(words):
        start, end, semantic, _positions = word
        identifier_end = _public_command_sensitive_option_end(semantic)
        assignment = False
        if identifier_end is None:
            identifier_end = _public_command_sensitive_assignment_end(semantic)
            assignment = identifier_end is not None
        if identifier_end is None:
            continue

        semantic_identifier = semantic[:identifier_end]
        raw_identifier = _public_command_raw_identifier(
            value, word, identifier_end, escaped
        )
        raw_word = value[start:end]
        whole_word_quoted_assignment = (
            assignment
            and len(raw_word) >= 2
            and raw_word[0] in {"'", '"'}
            and raw_word[-1] == raw_word[0]
            and contexts[start] is None
            and not escaped[start]
            and not escaped[end - 1]
            and all(
                contexts[position] == raw_word[0]
                for position in range(start + 1, end)
            )
        )
        if (
            not whole_word_quoted_assignment
            and not _public_command_identifier_spelling_supported(
                raw_identifier, semantic_identifier
            )
        ):
            return True

        trailing = semantic[identifier_end:]
        needs_separate_value = not trailing or trailing in {"=", ":"}
        if not needs_separate_value:
            continue
        value_index = word_index + 1
        if value_index >= len(words):
            return True
        candidate = words[value_index][2]
        if candidate.casefold() == "bearer":
            value_index += 1
            if value_index >= len(words):
                return True
            candidate = words[value_index][2]
        if candidate.startswith(("-", "/")):
            return True
    return False


def _public_command_secret_identifier(value: str, *, environment: bool) -> bool:
    lowered = value.casefold()
    normalized = lowered.replace("-", "").replace("_", "")
    if normalized in PUBLIC_COMMAND_SECRET_IDENTIFIERS:
        return True
    return environment and any(
        lowered == suffix or lowered.endswith(f"_{suffix}")
        for suffix in PUBLIC_COMMAND_ENV_SUFFIXES
    )


def _public_command_quote_state(
    value: str,
) -> tuple[list[str | None], list[bool]] | None:
    contexts: list[str | None] = [None] * (len(value) + 1)
    escaped = [False] * len(value)
    quote: str | None = None
    index = 0
    while index < len(value):
        contexts[index] = quote
        character = value[index]
        if quote == "'":
            if character == quote:
                quote = None
            index += 1
            continue
        if character in PUBLIC_COMMAND_ESCAPE_CHARACTERS:
            if index + 1 >= len(value):
                return None
            escaped[index + 1] = True
            contexts[index + 1] = quote
            index += 2
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        index += 1
    contexts[len(value)] = quote
    if quote is not None:
        return None
    return contexts, escaped


def _public_command_quoted_value_end(value: str, start: int) -> int | None:
    quote = value[start]
    index = start + 1
    while index < len(value):
        character = value[index]
        if quote == '"' and character in PUBLIC_COMMAND_ESCAPE_CHARACTERS:
            if index + 1 >= len(value):
                return None
            index += 2
            continue
        if character == quote:
            index += 1
            if index < len(value) and value[index] == quote:
                index += 1
                continue
            return index
        index += 1
    return None


def _public_command_bearer_end(value: str, start: int, stop: int) -> int | None:
    end = start + len("bearer")
    if value[start:end].casefold() != "bearer" or end >= stop:
        return None
    if not value[end].isspace():
        return None
    while end < stop and value[end].isspace():
        end += 1
    return end


def _public_command_unquoted_value_end(
    value: str,
    start: int,
    contexts: list[str | None],
    escaped: list[bool],
) -> int:
    outer_quote = contexts[start]
    end = start
    while end < len(value):
        character = value[end]
        context = contexts[end]
        if (
            outer_quote is not None
            and character == outer_quote
            and context == outer_quote
            and not escaped[end]
        ):
            break
        if context == outer_quote and not escaped[end]:
            if character in PUBLIC_COMMAND_WORD_SEPARATORS or character in "}]":
                break
            if outer_quote is None and character.isspace():
                break
        end += 1
    return end


def _public_command_word_end(
    value: str,
    start: int,
    contexts: list[str | None],
    escaped: list[bool],
) -> int:
    end = start
    while end < len(value):
        if contexts[end] is None and not escaped[end] and (
            value[end].isspace() or value[end] in PUBLIC_COMMAND_WORD_SEPARATORS
        ):
            break
        end += 1
    return end


def _public_command_word_redaction(
    value: str,
    start: int,
    contexts: list[str | None],
    escaped: list[bool],
) -> tuple[int, int, str]:
    end = _public_command_word_end(value, start, contexts, escaped)
    if end == start:
        raise ValueError("credential value is missing")
    quote = value[start]
    if quote in {"'", '"'} and contexts[start] is None and not escaped[start]:
        if (
            value[end - 1] != quote
            or contexts[end - 1] != quote
            or escaped[end - 1]
        ):
            raise ValueError("credential quote is ambiguous")
        bearer_end = _public_command_bearer_end(value, start + 1, end - 1)
        bearer = value[start + 1 : bearer_end] if bearer_end is not None else ""
        return start, end, f"{quote}{bearer}{PUBLIC_COMMAND_REDACTION}{quote}"
    return start, end, PUBLIC_COMMAND_REDACTION


def _public_command_value_redaction(
    value: str,
    start: int,
    contexts: list[str | None],
    escaped: list[bool],
    *,
    allow_empty: bool,
) -> tuple[int, int, str]:
    if start >= len(value) or value[start] in PUBLIC_COMMAND_WORD_SEPARATORS:
        if allow_empty:
            return start, start, PUBLIC_COMMAND_REDACTION
        raise ValueError("credential value is missing")
    if (
        contexts[start] is None
        and not escaped[start]
        and value[start] in {"-", "/"}
    ):
        raise ValueError("credential value is missing")

    character = value[start]
    if (
        character in PUBLIC_COMMAND_ESCAPE_CHARACTERS
        and start + 1 < len(value)
        and value[start + 1] in {"'", '"'}
        and escaped[start + 1]
    ):
        raise ValueError("credential quote is ambiguous")
    if character in {"'", '"'} and (
        contexts[start] != character or escaped[start]
    ):
        end = _public_command_quoted_value_end(value, start)
        if end is None:
            raise ValueError("credential quote is ambiguous")
        content_stop = end - 1
        bearer_end = _public_command_bearer_end(value, start + 1, content_stop)
        bearer = value[start + 1 : bearer_end] if bearer_end is not None else ""
        replacement = f"{character}{bearer}{PUBLIC_COMMAND_REDACTION}{character}"
        if end < len(value):
            following = value[end]
            closes_outer_quote = (
                following in {"'", '"'}
                and contexts[end] == following
                and not escaped[end]
            )
            if not (
                following.isspace()
                or following in PUBLIC_COMMAND_WORD_SEPARATORS
                or following in ",}]"
                or closes_outer_quote
            ):
                raise ValueError("credential quote is ambiguous")
        return start, end, replacement

    bearer_end = _public_command_bearer_end(value, start, len(value))
    redaction_start = bearer_end if bearer_end is not None else start
    end = _public_command_unquoted_value_end(
        value, redaction_start, contexts, escaped
    )
    if end == redaction_start and not allow_empty:
        raise ValueError("credential value is missing")
    return redaction_start, end, PUBLIC_COMMAND_REDACTION


def _public_command_flag_redaction(
    value: str,
    index: int,
    contexts: list[str | None],
    escaped: list[bool],
) -> tuple[int, int, str] | None:
    if value[index] not in {"-", "/"}:
        return None
    if index > 0 and not (
        value[index - 1].isspace()
        or value[index - 1] in PUBLIC_COMMAND_WORD_SEPARATORS
        or value[index - 1] in "\"'(["
    ):
        return None
    name_start = index + 1
    if value[index] == "-" and name_start < len(value) and value[name_start] == "-":
        name_start += 1
    name_end = _public_command_identifier_end(value, name_start)
    if name_end == name_start or not _public_command_secret_identifier(
        value[name_start:name_end], environment=False
    ):
        return None

    cursor = name_end
    if cursor < len(value) and value[cursor] in "=:":
        cursor += 1
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        return _public_command_value_redaction(
            value, cursor, contexts, escaped, allow_empty=False
        )
    if (
        cursor < len(value)
        and value[cursor] in {"'", '"'}
        and contexts[cursor] == value[cursor]
        and not escaped[cursor]
    ):
        cursor += 1
    if cursor >= len(value) or not value[cursor].isspace():
        return None
    while cursor < len(value) and value[cursor].isspace():
        cursor += 1
    if (
        cursor < len(value)
        and contexts[cursor] is None
        and not escaped[cursor]
        and value[cursor] in {"-", "/"}
    ):
        raise ValueError("credential value is missing")
    first_word_end = _public_command_word_end(value, cursor, contexts, escaped)
    if value[cursor:first_word_end].casefold() == "bearer":
        cursor = first_word_end
        if cursor >= len(value) or not value[cursor].isspace():
            raise ValueError("credential value is missing")
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if (
            cursor < len(value)
            and contexts[cursor] is None
            and not escaped[cursor]
            and value[cursor] in {"-", "/"}
        ):
            raise ValueError("credential value is missing")
    return _public_command_word_redaction(value, cursor, contexts, escaped)


def _public_command_assignment_redaction(
    value: str,
    index: int,
    contexts: list[str | None],
    escaped: list[bool],
) -> tuple[int, int, str] | None:
    if index > 0 and not (
        value[index - 1].isspace()
        or value[index - 1] in "\"'?$&;,({["
    ):
        return None

    environment = value[index : index + 5].casefold() == "$env:"
    name_start = index + 5 if environment else index
    name_end = _public_command_identifier_end(value, name_start)
    identifier = value[name_start:name_end]
    if name_end == name_start or not (
        identifier.casefold() == "key"
        or _public_command_secret_identifier(identifier, environment=True)
    ):
        return None

    cursor = name_end
    if cursor < len(value) and name_start > 0:
        key_quote = value[name_start - 1]
        if value[cursor] in {"'", '"'} and key_quote == value[cursor]:
            cursor += 1
        elif (
            cursor + 1 < len(value)
            and value[cursor] in PUBLIC_COMMAND_ESCAPE_CHARACTERS
            and value[cursor + 1] in {"'", '"'}
            and key_quote == value[cursor + 1]
            and escaped[cursor + 1]
        ):
            cursor += 2
    while cursor < len(value) and value[cursor].isspace():
        cursor += 1
    if cursor >= len(value) or value[cursor] not in "=:":
        return None
    cursor += 1
    while cursor < len(value) and value[cursor].isspace():
        cursor += 1
    return _public_command_value_redaction(
        value, cursor, contexts, escaped, allow_empty=False
    )


def _redact_public_command(value: str) -> str:
    quote_state = _public_command_quote_state(value)
    if quote_state is None:
        return PUBLIC_COMMAND_INVALID
    contexts, escaped = quote_state
    if _public_command_has_unsafe_credential_syntax(value, contexts, escaped):
        return PUBLIC_COMMAND_INVALID
    parts: list[str] = []
    copied_until = 0
    index = 0
    try:
        while index < len(value):
            redaction = _public_command_flag_redaction(
                value, index, contexts, escaped
            ) or _public_command_assignment_redaction(
                value, index, contexts, escaped
            )
            if redaction is None:
                index += 1
                continue
            start, end, replacement = redaction
            parts.extend((value[copied_until:start], replacement))
            copied_until = end
            index = max(end, index + 1)
    except ValueError:
        return PUBLIC_COMMAND_INVALID
    parts.append(value[copied_until:])
    return "".join(parts)


def _public_command(value: object, *, limit: int = 500) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if len(value) > PUBLIC_COMMAND_SCAN_LIMIT:
        return PUBLIC_COMMAND_TOO_LONG
    normalized = " ".join(
        re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", value).split()
    )
    redacted = _redact_public_command(normalized)
    if len(redacted) > min(limit, 500):
        return PUBLIC_COMMAND_TOO_LONG
    return redacted or None


def _public_evidence(
    value: object, paths: GoalPaths
) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    identifier = _public_text(value.get("id"), limit=200)
    label = value.get("label")
    kind = value.get("kind")
    summary = _public_text(value.get("summary"))
    if (
        identifier is None
        or label not in {"Verified", "Snapshot", "Unverified", "BLOCKED"}
        or kind not in {"command", "artifact"}
        or summary is None
    ):
        return None
    projected: dict[str, object] = {
        "id": identifier,
        "label": label,
        "kind": kind,
        "summary": summary,
    }
    if kind == "command":
        command = _public_command(value.get("command"))
        exit_code = value.get("exit_code")
        if command is not None:
            projected["command"] = command
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            projected["exit_code"] = exit_code
        return projected

    sha256 = value.get("sha256")
    if isinstance(sha256, str) and re.fullmatch(r"[a-f0-9]{64}", sha256):
        projected["sha256"] = sha256
    artifact_path = value.get("artifact_path")
    if isinstance(artifact_path, str):
        try:
            _target, _content_type, _attachment = _artifact_target(
                paths, artifact_path
            )
        except GoalProgressError:
            pass
        else:
            normalized = artifact_path.replace("\\", "/")
            projected["artifact_path"] = normalized
            projected["artifact_href"] = "/artifact?" + urllib.parse.urlencode(
                {"path": normalized}
            )
    return projected


def _public_event_records(
    paths: GoalPaths,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if not paths.progress.exists():
        return [], _public_history_window([], byte_truncated=False, event_truncated=False)
    progress = _assert_goal_target(paths.root, paths.progress)
    if not progress.is_file() or progress.is_symlink():
        raise GoalProgressError("progress history is unavailable")
    records: deque[dict[str, object]] = deque(maxlen=PUBLIC_EVENT_LIMIT)
    try:
        lines, byte_truncated, event_truncated = _bounded_progress_tail(progress)
        for line in lines:
            if len(line) > MAX_EVENT_BYTES:
                raise GoalProgressError("progress history is unavailable")
            event = json.loads(line.decode("utf-8"))
            if not isinstance(event, dict):
                raise GoalProgressError("progress history is unavailable")
            records.append(event)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoalProgressError("progress history is unavailable") from exc
    values = list(records)
    return values, _public_history_window(
        values,
        byte_truncated=byte_truncated,
        event_truncated=event_truncated,
    )


def _public_history_window(
    events: list[dict[str, object]],
    *,
    byte_truncated: bool,
    event_truncated: bool,
) -> dict[str, object]:
    sequences = [
        int(sequence)
        for event in events
        if isinstance((sequence := event.get("sequence")), int)
        and not isinstance(sequence, bool)
    ]
    truncated_by = []
    if byte_truncated:
        truncated_by.append("bytes")
    if event_truncated:
        truncated_by.append("events")
    partial = bool(truncated_by)
    return {
        "max_events": PUBLIC_EVENT_LIMIT,
        "max_bytes": PUBLIC_EVENT_SCAN_BYTES,
        "available_events": len(events),
        "partial": partial,
        "truncated": partial,
        "truncated_by": truncated_by,
        "first_available_sequence": sequences[0] if sequences else None,
        "last_available_sequence": sequences[-1] if sequences else None,
    }


def _public_event_summaries(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for event in events:
        projected = _public_fields(event, PUBLIC_EVENT_FIELDS)
        summary = _public_text(projected.get("summary"))
        if summary is not None:
            projected["summary"] = summary
        else:
            projected.pop("summary", None)
        summaries.append(projected)
    return summaries


def _packet_runtime_details(
    packets: list[dict[str, object]],
    events: list[dict[str, object]],
    paths: GoalPaths,
    history_window: dict[str, object],
) -> dict[str, dict[str, object]]:
    history_partial = history_window.get("partial") is True
    details = {
        str(packet.get("id")): {
            "attempt": 0,
            "elapsed_seconds": 0.0,
            "evidence": [],
            "history_status": "partial" if history_partial else "complete",
            "history_warning": (
                PUBLIC_PARTIAL_HISTORY_WARNING if history_partial else None
            ),
        }
        for packet in packets
        if isinstance(packet.get("id"), str)
    }
    active: dict[str, tuple[str, int]] = {}
    latest_offsets: dict[str, int] = {}
    evidence_ids: dict[str, set[str]] = {packet_id: set() for packet_id in details}
    for event in events:
        epoch = event.get("writer_epoch_id")
        offset = event.get("monotonic_offset_ms")
        if isinstance(epoch, str) and isinstance(offset, int) and not isinstance(offset, bool):
            latest_offsets[epoch] = max(latest_offsets.get(epoch, offset), offset)
        packet_id = event.get("packet_id")
        if not isinstance(packet_id, str) or packet_id not in details:
            continue
        event_type = event.get("event_type")
        if event_type in {"packet.started", "packet.retry_started"}:
            details[packet_id]["attempt"] = int(details[packet_id]["attempt"]) + 1
            if isinstance(epoch, str) and isinstance(offset, int) and not isinstance(offset, bool):
                active[packet_id] = (epoch, offset)
        elif event_type == "packet.resumed":
            if isinstance(epoch, str) and isinstance(offset, int) and not isinstance(offset, bool):
                active[packet_id] = (epoch, offset)
        elif event_type in {
            "packet.waiting_input",
            "packet.blocked",
            "packet.failed",
            "packet.verified",
        }:
            started = active.pop(packet_id, None)
            if (
                started is not None
                and started[0] == epoch
                and isinstance(offset, int)
                and not isinstance(offset, bool)
            ):
                details[packet_id]["elapsed_seconds"] = round(
                    float(details[packet_id]["elapsed_seconds"])
                    + max(0, offset - started[1]) / 1000.0,
                    3,
                )
        evidence = event.get("evidence")
        if isinstance(evidence, list):
            for item in evidence:
                projected = _public_evidence(item, paths)
                if projected is None or projected["id"] in evidence_ids[packet_id]:
                    continue
                evidence_ids[packet_id].add(str(projected["id"]))
                details[packet_id]["evidence"].append(projected)  # type: ignore[union-attr]
    for packet_id, (epoch, start) in active.items():
        details[packet_id]["elapsed_seconds"] = round(
            float(details[packet_id]["elapsed_seconds"])
            + max(0, latest_offsets.get(epoch, start) - start) / 1000.0,
            3,
        )
    if history_partial:
        for item in details.values():
            item["attempt"] = None
            item["elapsed_seconds"] = None
    return details


def _public_diagnostics(
    packets: list[dict[str, object]],
    events: list[dict[str, object]],
    history_window: dict[str, object],
) -> list[dict[str, object]]:
    history_status = "partial" if history_window.get("partial") is True else "complete"
    diagnostics: list[dict[str, object]] = []
    for packet in packets:
        packet_id = packet.get("id")
        status = packet.get("status")
        if not isinstance(packet_id, str) or status not in PUBLIC_DIAGNOSTIC_STATES:
            continue
        matching = next(
            (
                event
                for event in reversed(events)
                if event.get("packet_id") == packet_id
                and event.get("event_type") == f"packet.{status}"
            ),
            None,
        )
        summary = _public_text(matching.get("summary")) if matching else None
        diagnostics.append(
            {
                "packet_id": packet_id,
                "status": status,
                "summary": summary or "No public diagnostic summary available.",
                "sequence": matching.get("sequence") if matching else None,
                "history_status": history_status,
            }
        )
    return diagnostics


def _public_state_projection(
    state: dict[str, object],
    events: list[dict[str, object]],
    paths: GoalPaths,
    history_window: dict[str, object],
) -> dict[str, object]:
    packets = state.get("packets")
    progress = state.get("progress")
    eta = state.get("eta")
    if (
        not isinstance(packets, list)
        or not all(isinstance(packet, dict) for packet in packets)
        or not isinstance(progress, dict)
        or not isinstance(eta, dict)
    ):
        raise GoalProgressError("goal state is unavailable")
    revisions = state.get("revision_history")
    evidence = state.get("latest_evidence")
    if not isinstance(revisions, list) or not isinstance(evidence, list):
        raise GoalProgressError("goal state is unavailable")
    details = _packet_runtime_details(packets, events, paths, history_window)
    projected = _public_fields(state, PUBLIC_STATE_FIELDS)
    projected["packets"] = []
    for order, packet in enumerate(packets, start=1):
        item = _public_fields(packet, PUBLIC_PACKET_FIELDS)
        item["order"] = order
        item.update(details.get(str(packet.get("id")), {}))
        projected["packets"].append(item)  # type: ignore[union-attr]
    projected["progress"] = _public_fields(progress, PUBLIC_PROGRESS_FIELDS)
    projected["eta"] = _public_fields(eta, PUBLIC_ETA_FIELDS)
    projected["revision_history"] = [
        item
        for value in revisions
        if (item := _public_revision(value)) is not None
    ]
    projected["latest_evidence"] = [
        item
        for value in evidence
        if (item := _public_evidence(value, paths)) is not None
    ]
    projected["warnings"] = [
        item
        for value in state.get("warnings", [])
        if (item := _public_text(value, limit=200)) is not None
    ]
    projected["diagnostics"] = _public_diagnostics(
        packets, events, history_window
    )
    history_partial = history_window.get("partial") is True
    eta_history_warning = "Historical ETA range snapshots are not recorded."
    if history_partial:
        eta_history_warning += (
            " Earlier triggers may also be outside the bounded public history window."
        )
    projected["eta_recent_trigger_history"] = {
        "kind": "recent_trigger_history",
        "history_status": "partial" if history_partial else "complete",
        "historical_range_snapshots_available": False,
        "warning": eta_history_warning,
        "entries": [
            {
                key: event.get(source)
                for key, source in (
                    ("sequence", "sequence"),
                    ("emitted_at", "emitted_at"),
                    ("plan_version", "plan_version"),
                    ("trigger", "event_type"),
                )
            }
            for event in events
            if event.get("event_type") in PUBLIC_ETA_TRIGGER_TYPES
        ],
    }
    return projected


def _bounded_progress_tail(progress: Path) -> tuple[list[bytes], bool, bool]:
    try:
        with progress.open("rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            start = max(0, size - PUBLIC_EVENT_SCAN_BYTES)
            handle.seek(start)
            data = handle.read(PUBLIC_EVENT_SCAN_BYTES)
    except OSError as exc:
        raise GoalProgressError("progress history is unavailable") from exc
    if start:
        first_break = data.find(b"\n")
        data = b"" if first_break < 0 else data[first_break + 1 :]
    if data and not data.endswith(b"\n"):
        last_break = data.rfind(b"\n")
        data = b"" if last_break < 0 else data[: last_break + 1]
    lines = data.splitlines()
    event_truncated = len(lines) > PUBLIC_EVENT_LIMIT
    return lines[-PUBLIC_EVENT_LIMIT:], start > 0, event_truncated


def _artifact_target(paths: GoalPaths, requested: str) -> tuple[Path, str, bool]:
    if not requested or "\x00" in requested:
        raise GoalProgressError("artifact path is forbidden")
    normalized = requested.replace("\\", "/")
    relative = Path(normalized)
    if relative.is_absolute() or ".." in relative.parts or relative.drive:
        raise GoalProgressError("artifact path is forbidden")
    if any(part != part.rstrip(" .") or ":" in part for part in relative.parts):
        raise GoalProgressError("artifact path is forbidden")
    if any(DOS_SHORT_NAME_COMPONENT.fullmatch(part) for part in relative.parts):
        raise GoalProgressError("artifact path is forbidden")
    if not relative.parts or relative.parts[0].lower() in {"runtime", "quarantine"}:
        raise GoalProgressError("artifact path is forbidden")
    if any(part.startswith(".") for part in relative.parts):
        raise GoalProgressError("artifact path is forbidden")
    target = _assert_goal_target(paths.root, paths.root / relative)
    target = _assert_path_safe(target, must_exist=True, require_directory=False)
    if not target.is_file() or target.is_symlink():
        raise GoalProgressError("artifact path is forbidden")
    try:
        canonical_relative = target.resolve(strict=True).relative_to(
            paths.root.resolve(strict=True)
        )
    except (OSError, ValueError) as exc:
        raise GoalProgressError("artifact path is forbidden") from exc
    if canonical_relative.parts[0].casefold() in {"runtime", "quarantine"}:
        raise GoalProgressError("artifact path is forbidden")
    suffix = target.suffix.lower()
    if suffix in PUBLIC_FORCED_DOWNLOAD_TYPES:
        return target, "application/octet-stream", True
    content_type = PUBLIC_ARTIFACT_TYPES.get(suffix, "application/octet-stream")
    return target, content_type, content_type == "application/octet-stream"


def _content_disposition(filename: str) -> str:
    cleaned = "".join(
        "_" if ord(character) < 32 or ord(character) == 127 else character
        for character in filename
    )
    fallback = "".join(
        character
        if character.isascii() and (character.isalnum() or character in "._-")
        else "_"
        for character in cleaned
    ).strip(". ")
    fallback = fallback or "artifact"
    encoded = urllib.parse.quote(cleaned, safe="!#$&+-.^_`|~")
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{encoded}"
    )


class GoalProgressRuntime:
    def __init__(
        self,
        goal_root: Path,
        submission_capability: str,
        *,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        if isinstance(idle_timeout_seconds, bool) or idle_timeout_seconds <= 0:
            raise GoalProgressError("idle timeout must be a positive integer")
        self.paths = GoalPaths.from_root(Path(goal_root))
        self.submission_capability = submission_capability
        self.idle_timeout_seconds = idle_timeout_seconds
        self.instance_nonce = secrets.token_urlsafe(24)
        self.public_cookie_name = (
            f"{PUBLIC_SESSION_COOKIE_PREFIX}{secrets.token_hex(12)}"
        )
        self.public_session_key = secrets.token_urlsafe(32)
        self._bootstrap_tokens: dict[str, tuple[float, str]] = {}
        self._bootstrap_mutex = threading.Lock()
        self._state_condition = threading.Condition()
        self.writer = ProgressWriter(self.paths.root, submission_capability, SystemClock())
        self._event_mutex = threading.Lock()
        self._stop_event = threading.Event()
        self._accepting_events = True
        self._last_activity = time.monotonic()
        try:
            self._server = _BoundedThreadingHTTPServer(
                ("127.0.0.1", 0), self._handler_type()
            )
            self._server.timeout = 0.05
            self._server.runtime = self  # type: ignore[attr-defined]
            self._public_server = _BoundedThreadingHTTPServer(
                ("127.0.0.1", 0), _PublicHandler
            )
            self._public_server.runtime = self  # type: ignore[attr-defined]
            self._public_thread: threading.Thread | None = None
            self.assets = discover_dashboard_assets()
            self.runtime_info: dict[str, object] = {
                "goal_root": str(self.paths.root.resolve()),
                "pid": os.getpid(),
                "private_port": int(self._server.server_address[1]),
                "public_port": int(self._public_server.server_address[1]),
                "writer_epoch_id": self.writer.epoch_id,
                "instance_nonce": self.instance_nonce,
                "idle_timeout_seconds": idle_timeout_seconds,
            }
            atomic_write_json(self.paths.writer_info, self.runtime_info)
            atomic_write_json(
                self.paths.server_info,
                {
                    "goal_root": str(self.paths.root.resolve()),
                    "public_port": self.runtime_info["public_port"],
                },
            )
        except BaseException:
            server = getattr(self, "_server", None)
            if server is not None:
                server.server_close()
            public_server = getattr(self, "_public_server", None)
            if public_server is not None:
                public_server.server_close()
            self.writer.close()
            raise

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        return _PrivateHandler

    def health(self) -> dict[str, object]:
        return {
            "goal_root": self.runtime_info["goal_root"],
            "pid": self.runtime_info["pid"],
            "writer_epoch_id": self.runtime_info["writer_epoch_id"],
            "instance_nonce": self.runtime_info["instance_nonce"],
        }

    @property
    def active_request_count(self) -> int:
        return self._server.active_request_count

    def authorized(self, header: str | None) -> bool:
        prefix = "Bearer "
        if not isinstance(header, str) or not header.startswith(prefix):
            return False
        return hmac.compare_digest(
            self.submission_capability, header[len(prefix) :]
        )

    def public_authorized(self, cookie_header: str | None) -> bool:
        if not isinstance(cookie_header, str):
            return False
        try:
            cookies = SimpleCookie(cookie_header)
        except Exception:
            return False
        morsel = cookies.get(self.public_cookie_name)
        if morsel is None:
            return False
        return hmac.compare_digest(self.public_session_key, morsel.value)

    def mint_dashboard_url(self, view: str) -> str:
        if view not in {"compact", "full"}:
            raise GoalProgressError("dashboard view is invalid")
        token = secrets.token_urlsafe(24)
        with self._bootstrap_mutex:
            now = time.monotonic()
            self._bootstrap_tokens = {
                candidate: item
                for candidate, item in self._bootstrap_tokens.items()
                if item[0] > now
            }
            self._bootstrap_tokens[token] = (
                now + PUBLIC_TOKEN_LIFETIME_SECONDS,
                view,
            )
        query = urllib.parse.urlencode({"token": token, "view": view})
        return f"http://127.0.0.1:{self.runtime_info['public_port']}/open?{query}"

    def consume_bootstrap_token(self, token: str, view: str) -> bool:
        with self._bootstrap_mutex:
            matched = next(
                (
                    candidate
                    for candidate in self._bootstrap_tokens
                    if hmac.compare_digest(candidate, token)
                ),
                None,
            )
            item = self._bootstrap_tokens.pop(matched, None) if matched else None
        return (
            item is not None
            and item[0] >= time.monotonic()
            and item[1] == view
        )

    def accept(self, candidate: dict[str, object]) -> dict[str, object]:
        with self._event_mutex:
            if not self._accepting_events:
                raise GoalProgressError("runtime is stopping")
            accepted = self.writer.accept(candidate, self.submission_capability)
            self._last_activity = time.monotonic()
            with self._state_condition:
                self._state_condition.notify_all()
            return accepted

    def touch_authenticated_activity(self) -> None:
        self._last_activity = time.monotonic()

    def request_stop(self) -> None:
        with self._event_mutex:
            self._accepting_events = False
        self._stop_event.set()
        with self._state_condition:
            self._state_condition.notify_all()

    def current_sequence(self) -> int:
        with self._event_mutex:
            events = getattr(self.writer, "_events", [])
            return int(events[-1]["sequence"]) if events else 0

    def wait_for_state_change(self, sequence: int, timeout: float) -> int:
        current = self.current_sequence()
        if current != sequence or self._stop_event.is_set():
            return current
        with self._state_condition:
            self._state_condition.wait(timeout)
        return self.current_sequence()

    def public_state(self) -> dict[str, object]:
        manifest = _read_public_json(self.paths.goal, "goal metadata")
        state = _read_public_json(self.paths.state, "goal state")
        if manifest is None or state is None:
            raise GoalProgressError("goal state is unavailable")
        context: dict[str, object | None] = {}
        for projection in ("brief", "working", "resume"):
            value = _read_public_json(
                self.paths.context / f"{projection}.json",
                f"{projection} context",
            )
            if value is None:
                context[projection] = None
                continue
            public_context = _public_fields(value, PUBLIC_CONTEXT_FIELDS)
            required_refs = public_context.get("required_fact_refs")
            public_context["required_fact_refs"] = [
                item
                for ref in (required_refs if isinstance(required_refs, list) else [])[:100]
                if (item := _public_text(ref, limit=500)) is not None
            ]
            blocked = public_context.get("status") == "BLOCKED"
            public_context["standalone_safe"] = not blocked
            public_context["presentation_warning"] = (
                "BLOCKED: this projection must not be used as standalone context."
                if blocked
                else None
            )
            context[projection] = public_context
        integration = _read_public_json(
            self.paths.integration_status, "integration status"
        ) or {
            "status": "BLOCKED",
            "reason": "integration_status_unavailable",
            "portable_progress_available": True,
        }
        event_records, history_window = _public_event_records(self.paths)
        events = _public_event_summaries(event_records)
        return {
            "session": {
                "goal_id": manifest.get("goal_id"),
                "title": manifest.get("title"),
                "repository_snapshot": manifest.get("repository_snapshot"),
                "updated_at": state.get("updated_at"),
            },
            "state": _public_state_projection(
                state, event_records, self.paths, history_window
            ),
            "events": events,
            "history_window": history_window,
            "context": context,
            "integration": _public_fields(integration, PUBLIC_INTEGRATION_FIELDS),
        }

    def run(self) -> None:
        self._public_thread = threading.Thread(
            target=self._public_server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="goal-progress-public",
        )
        self._public_thread.start()
        try:
            while not self._stop_event.is_set():
                if time.monotonic() - self._last_activity >= self.idle_timeout_seconds:
                    self._stop_event.set()
                    break
                self._server.handle_request()
        finally:
            self._stop_event.set()
            with self._state_condition:
                self._state_condition.notify_all()
            self._public_server.shutdown()
            self._public_server.server_close()
            if self._public_thread is not None:
                self._public_thread.join(timeout=2.0)
            self._server.server_close()
            with self._event_mutex:
                self._accepting_events = False
                self.writer.close()
            if self.paths.progress.is_file():
                replay_goal(self.paths.root, now_utc=SystemClock().utc_now())
            atomic_write_json(
                self.paths.writer_info,
                {**self.runtime_info, SHUTDOWN_COMPLETE_KEY: True},
            )


class _PrivateHandler(BaseHTTPRequestHandler):
    server_version = "GoalProgressPrivate/1"

    def setup(self) -> None:
        self._read_deadline_expired = threading.Event()
        self._read_deadline_timer: threading.Timer | None = None
        super().setup()
        self.close_connection = True
        self.connection.settimeout(REQUEST_READ_DEADLINE_SECONDS)
        self._read_deadline_timer = threading.Timer(
            REQUEST_READ_DEADLINE_SECONDS, self._expire_read_deadline
        )
        self._read_deadline_timer.daemon = True
        self._read_deadline_timer.start()

    def finish(self) -> None:
        self._cancel_read_deadline()
        try:
            super().finish()
        except OSError:
            if not self._read_deadline_expired.is_set():
                raise

    def _expire_read_deadline(self) -> None:
        self._read_deadline_expired.set()
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _cancel_read_deadline(self) -> None:
        timer = self._read_deadline_timer
        if timer is not None:
            timer.cancel()
            self._read_deadline_timer = None

    def _read_body(self, length: int) -> bytes | None:
        try:
            body = self.rfile.read(length)
        except (OSError, TimeoutError):
            return None
        if len(body) != length:
            return None
        self._cancel_read_deadline()
        return body

    @property
    def runtime(self) -> GoalProgressRuntime:
        return self.server.runtime  # type: ignore[attr-defined, no-any-return]

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: int, value: object) -> None:
        body = _json_bytes(value)
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _authorized(self) -> bool:
        if self.runtime.authorized(self.headers.get("Authorization")):
            return True
        self._send(HTTPStatus.UNAUTHORIZED, {"status": "FAIL", "reason": "unauthorized"})
        return False

    def _content_length(self) -> int | None:
        if self.headers.get("Transfer-Encoding") is not None:
            return None
        raw = self.headers.get("Content-Length")
        if raw is None:
            return 0
        try:
            length = int(raw)
        except ValueError:
            return None
        return length if length >= 0 else None

    def do_GET(self) -> None:
        self._cancel_read_deadline()
        if self.path != "/health":
            self._send(HTTPStatus.NOT_FOUND, {"status": "FAIL", "reason": "not found"})
            return
        if not self._authorized():
            return
        self._send(HTTPStatus.OK, self.runtime.health())

    def do_POST(self) -> None:
        if self.path not in {"/events", "/shutdown", "/dashboard/open"}:
            self._cancel_read_deadline()
            self._send(HTTPStatus.NOT_FOUND, {"status": "FAIL", "reason": "not found"})
            return
        if not self._authorized():
            self._cancel_read_deadline()
            return
        length = self._content_length()
        if length is None:
            self._cancel_read_deadline()
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"status": "FAIL", "reason": "invalid request body length"},
            )
            return
        if self.path == "/shutdown":
            if length != 0:
                self._cancel_read_deadline()
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "FAIL", "reason": "shutdown accepts no body"},
                )
                return
            self._cancel_read_deadline()
            self.runtime.request_stop()
            self._send(HTTPStatus.OK, {"status": "READY", "writer_status": "stopping"})
            return
        if self.path == "/dashboard/open":
            if length == 0 or length > 4096:
                self._cancel_read_deadline()
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "FAIL", "reason": "dashboard request is invalid"},
                )
                return
            raw = self._read_body(length)
            if raw is None:
                return
            try:
                request = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                request = None
            if (
                not isinstance(request, dict)
                or set(request) != {"view"}
                or request.get("view") not in {"compact", "full"}
            ):
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "FAIL", "reason": "dashboard request is invalid"},
                )
                return
            self._send(
                HTTPStatus.OK,
                {
                    "status": "READY",
                    "url": self.runtime.mint_dashboard_url(str(request["view"])),
                },
            )
            return
        if length > MAX_EVENT_BYTES:
            if self._read_body(MAX_EVENT_BYTES + 1) is None:
                return
            self._send(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"status": "FAIL", "reason": "event body exceeds 256 KiB"},
            )
            return
        if length == 0:
            self._cancel_read_deadline()
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"status": "FAIL", "reason": "event body is required"},
            )
            return
        raw = self._read_body(length)
        if raw is None:
            return
        try:
            candidate = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"status": "FAIL", "reason": "event body must be JSON"},
            )
            return
        if not isinstance(candidate, dict) or frozenset(candidate) != EVENT_KEYS:
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"status": "FAIL", "reason": "candidate event keys mismatch"},
            )
            return
        try:
            accepted = self.runtime.accept(candidate)
        except (GoalProgressError, PermissionError) as exc:
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"status": "FAIL", "reason": _safe_reason(exc)},
            )
            return
        self._send(
            HTTPStatus.OK,
            {
                "status": "READY",
                "accepted": {
                    "goal_id": accepted["goal_id"],
                    "event_id": accepted["event_id"],
                    "sequence": accepted["sequence"],
                },
            },
        )


class _PublicHandler(BaseHTTPRequestHandler):
    server_version = "GoalProgressPublic/1"

    def handle(self) -> None:
        try:
            super().handle()
        except (
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionResetError,
            socket.timeout,
        ):
            return

    @property
    def runtime(self) -> GoalProgressRuntime:
        return self.server.runtime  # type: ignore[attr-defined, no-any-return]

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        del message, explain
        self._send_json(
            code,
            {"status": "FAIL", "reason": "request failed"},
        )

    def _begin(
        self,
        status: int,
        content_type: str,
        *,
        content_length: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", PUBLIC_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._begin(
            status,
            content_type,
            content_length=len(body),
            headers=headers,
        )
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            pass

    def _send_json(
        self,
        status: int,
        value: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._send_bytes(
            status,
            _json_bytes(value),
            "application/json; charset=utf-8",
            headers=headers,
        )

    def _authorized(self) -> bool:
        if self.runtime.public_authorized(self.headers.get("Cookie")):
            self.runtime.touch_authenticated_activity()
            return True
        self._send_json(
            HTTPStatus.UNAUTHORIZED,
            {"status": "FAIL", "reason": "unauthorized"},
        )
        return False

    def _bootstrap(self, query: str) -> None:
        values = urllib.parse.parse_qs(query, keep_blank_values=True)
        if set(values) != {"token", "view"} or any(len(item) != 1 for item in values.values()):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"status": "FAIL", "reason": "unauthorized"},
            )
            return
        token = values["token"][0]
        view = values["view"][0]
        if not self.runtime.consume_bootstrap_token(token, view):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"status": "FAIL", "reason": "unauthorized"},
            )
            return
        self.runtime.touch_authenticated_activity()
        self._begin(
            HTTPStatus.SEE_OTHER,
            "text/plain; charset=utf-8",
            content_length=0,
            headers={
                "Location": f"/{view}",
                "Set-Cookie": (
                    f"{self.runtime.public_cookie_name}="
                    f"{self.runtime.public_session_key}; "
                    "HttpOnly; SameSite=Strict; Path=/"
                ),
            },
        )

    def _serve_asset(self, name: str, content_type: str) -> None:
        try:
            target = _assert_path_safe(
                self.runtime.assets / name,
                must_exist=True,
                require_directory=False,
            )
            if target.parent != self.runtime.assets or not target.is_file() or target.is_symlink():
                raise GoalProgressError("dashboard asset is unavailable")
            body = target.read_bytes()
        except (GoalProgressError, OSError):
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "FAIL", "reason": "not found"},
            )
            return
        self._send_bytes(HTTPStatus.OK, body, content_type)

    def _serve_artifact(self, query: str) -> None:
        values = urllib.parse.parse_qs(query, keep_blank_values=True)
        if set(values) != {"path"} or len(values["path"]) != 1:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"status": "FAIL", "reason": "artifact path is forbidden"},
            )
            return
        try:
            target, content_type, attachment = _artifact_target(
                self.runtime.paths, values["path"][0]
            )
            body = target.read_bytes()
        except (GoalProgressError, OSError):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"status": "FAIL", "reason": "artifact path is forbidden"},
            )
            return
        headers = None
        if attachment:
            headers = {"Content-Disposition": _content_disposition(target.name)}
        self._send_bytes(HTTPStatus.OK, body, content_type, headers=headers)

    def _serve_events(self) -> None:
        self.connection.settimeout(1.0)
        self._begin(
            HTTPStatus.OK,
            "text/event-stream; charset=utf-8",
            headers={"Connection": "keep-alive"},
        )
        sequence = -1
        last_write = time.monotonic()
        try:
            while not self.runtime._stop_event.is_set():
                current = self.runtime.current_sequence()
                if current != sequence:
                    payload = _json_bytes({"sequence": current})
                    self.wfile.write(b"event: state\n")
                    self.wfile.write(b"data: " + payload + b"\n\n")
                    self.wfile.flush()
                    sequence = current
                    last_write = time.monotonic()
                elif time.monotonic() - last_write >= PUBLIC_EVENT_HEARTBEAT_SECONDS:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    last_write = time.monotonic()
                self.runtime.wait_for_state_change(sequence, PUBLIC_EVENT_POLL_SECONDS)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/open":
            self._bootstrap(parsed.query)
            return
        if not self._authorized():
            return
        if parsed.query and parsed.path != "/artifact":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "FAIL", "reason": "not found"},
            )
            return
        if parsed.path in {"/compact", "/full"}:
            self._serve_asset("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/assets/styles.css":
            self._serve_asset("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/assets/app.js":
            self._serve_asset("app.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/api/state":
            try:
                payload = self.runtime.public_state()
            except GoalProgressError:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"status": "BLOCKED", "reason": "goal state is unavailable"},
                )
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if parsed.path == "/api/events":
            self._serve_events()
            return
        if parsed.path == "/artifact":
            self._serve_artifact(parsed.query)
            return
        self._send_json(
            HTTPStatus.NOT_FOUND,
            {"status": "FAIL", "reason": "not found"},
        )

    def _method_not_allowed(self, *, head_only: bool = False) -> None:
        body = _json_bytes({"status": "FAIL", "reason": "method not allowed"})
        if head_only:
            self._begin(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "application/json; charset=utf-8",
                content_length=0,
                headers={"Allow": "GET"},
            )
            return
        self._send_bytes(
            HTTPStatus.METHOD_NOT_ALLOWED,
            body,
            "application/json; charset=utf-8",
            headers={"Allow": "GET"},
        )

    def do_HEAD(self) -> None:
        self._method_not_allowed(head_only=True)

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()


def _remove_runtime_metadata(paths: GoalPaths, token_file: Path) -> None:
    journal = _read_recovery_journal(paths)
    if journal is None or journal.get("recovery_state") != "cleanup-ready":
        raise GoalProgressError("runtime cleanup is not durable")
    _resume_cleanup_ready_locked(paths, token_file, journal)


def _write_cleanup_ready(
    paths: GoalPaths,
    token_file: Path,
    *,
    command_fingerprint: str = "0" * 64,
) -> dict[str, object]:
    token_sha256 = (
        _submission_token_sha256(token_file)
        if token_file.is_file() and not token_file.is_symlink()
        else "0" * 64
    )
    writer_hash = None
    if paths.writer_info.is_file() and not paths.writer_info.is_symlink():
        writer_hash = _sha256_bytes(paths.writer_info.read_bytes())
    cleanup = {
        "recovery_state": "cleanup-ready",
        "goal_root": str(paths.root.resolve()),
        "submission_token_sha256": token_sha256,
        "command_fingerprint": command_fingerprint,
        "writer_info_sha256": writer_hash,
        "remaining_files": [
            "submission-token",
            "server-info.json",
            "writer-info.json",
        ],
    }
    try:
        atomic_write_json(_recovery_journal_path(paths), cleanup)
    except (GoalProgressError, OSError) as exc:
        raise GoalProgressError("runtime cleanup state could not be persisted") from exc
    return cleanup


def _resume_cleanup_ready_locked(
    paths: GoalPaths,
    token_file: Path,
    cleanup: dict[str, object],
) -> None:
    if (
        cleanup.get("recovery_state") != "cleanup-ready"
        or cleanup.get("goal_root") != str(paths.root.resolve())
    ):
        raise GoalProgressError("runtime cleanup identity changed")
    if token_file.exists():
        if (
            not token_file.is_file()
            or token_file.is_symlink()
            or cleanup.get("submission_token_sha256")
            != _submission_token_sha256(token_file)
        ):
            raise GoalProgressError("runtime cleanup identity changed")
    if paths.writer_info.exists():
        expected_writer_hash = cleanup.get("writer_info_sha256")
        if (
            expected_writer_hash is None
            or not paths.writer_info.is_file()
            or paths.writer_info.is_symlink()
            or _sha256_bytes(paths.writer_info.read_bytes()) != expected_writer_hash
        ):
            raise GoalProgressError("runtime cleanup identity changed")
    for target in (Path(token_file), paths.server_info, paths.writer_info):
        try:
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    raise GoalProgressError("runtime cleanup identity changed")
                target.unlink()
        except FileNotFoundError:
            pass
    journal_path = _recovery_journal_path(paths)
    try:
        if journal_path.exists():
            if not journal_path.is_file() or journal_path.is_symlink():
                raise GoalProgressError("runtime cleanup identity changed")
            journal_path.unlink()
    except FileNotFoundError:
        pass


def _runtime_identity_still_matches(
    paths: GoalPaths,
    token_file: Path,
    expected_info: dict[str, object],
    expected_capability: str,
) -> bool:
    try:
        current_info = _read_runtime_info(paths.writer_info)
        current_capability = _read_capability(token_file)
    except (GoalProgressError, OSError):
        return False
    return all(
        current_info.get(key) == expected_info.get(key) for key in RUNTIME_INFO_KEYS
    ) and hmac.compare_digest(current_capability, expected_capability)


def _replay_before_runtime_cleanup(paths: GoalPaths) -> None:
    if not paths.progress.is_file():
        return
    try:
        replay_goal(paths.root, now_utc=SystemClock().utc_now())
    except (GoalProgressError, OSError) as exc:
        raise GoalProgressError(
            "runtime cleanup could not rebuild derived goal evidence"
        ) from exc


def _cleanup_runtime_identity(
    paths: GoalPaths,
    token_file: Path,
    *,
    expected_info: dict[str, object] | None = None,
    expected_capability: str | None = None,
) -> bool:
    try:
        with GoalLock(paths.runtime / RUNTIME_IDENTITY_LOCK):
            if expected_info is not None and expected_capability is not None:
                if not _runtime_identity_still_matches(
                    paths, token_file, expected_info, expected_capability
                ):
                    return False
            _replay_before_runtime_cleanup(paths)
            if expected_info is not None and expected_capability is not None:
                if not _runtime_identity_still_matches(
                    paths, token_file, expected_info, expected_capability
                ):
                    return False
            cleanup = _write_cleanup_ready(paths, token_file)
            _resume_cleanup_ready_locked(paths, token_file, cleanup)
            return True
    except (GoalProgressError, OSError, TimeoutError) as exc:
        if isinstance(exc, GoalProgressError):
            raise
        raise GoalProgressError("runtime cleanup identity is busy") from exc


def _write_new_capability(token_file: Path) -> str:
    capability = secrets.token_urlsafe(32)
    target = Path(token_file)
    temporary = target.with_name(
        f".{target.name}.{secrets.token_hex(8)}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="") as handle:
            handle.write(capability)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        try:
            if temporary.is_file() and not temporary.is_symlink():
                temporary.unlink()
        except FileNotFoundError:
            pass
    return capability


def _remove_stale_descriptors(
    paths: GoalPaths, stale_info: dict[str, object] | None
) -> None:
    if stale_info is not None:
        try:
            current = _read_runtime_info(paths.writer_info)
        except GoalProgressError:
            current = None
        if current is not None and any(
            current.get(key) != stale_info.get(key) for key in RUNTIME_INFO_KEYS
        ):
            return
    for target in (paths.writer_info, paths.server_info):
        try:
            if target.is_file() and not target.is_symlink():
                target.unlink()
        except FileNotFoundError:
            pass


def _snapshot_runtime_identity(
    paths: GoalPaths, token_file: Path
) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for target in (
        Path(token_file),
        paths.writer_info,
        paths.server_info,
        _recovery_journal_path(paths),
    ):
        if not target.exists():
            snapshot[target] = None
            continue
        if not target.is_file() or target.is_symlink():
            raise GoalProgressError("runtime recovery identity is unsafe")
        try:
            snapshot[target] = target.read_bytes()
        except OSError as exc:
            raise GoalProgressError(
                "runtime recovery identity could not be read"
            ) from exc
    return snapshot


def _atomic_write_identity_bytes(target: Path, value: bytes) -> None:
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt" and target.name == "submission-token":
            os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        try:
            if temporary.is_file() and not temporary.is_symlink():
                temporary.unlink()
        except FileNotFoundError:
            pass


def _restore_runtime_identity(snapshot: dict[Path, bytes | None]) -> None:
    try:
        for target, value in snapshot.items():
            if value is None:
                if target.is_file() and not target.is_symlink():
                    target.unlink()
                continue
            _atomic_write_identity_bytes(target, value)
    except OSError as exc:
        raise GoalProgressError(
            "runtime recovery identity could not be restored"
        ) from exc


def _submission_token_sha256(token_file: Path) -> str:
    capability = _read_capability(token_file)
    return hashlib.sha256(capability.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _process_command_fingerprint(
    executable: str, command: list[str] | str
) -> str:
    normalized_executable = os.path.normcase(
        os.path.abspath(str(Path(executable).resolve()))
    )
    if os.name == "nt":
        command_line = (
            command if isinstance(command, str) else subprocess.list2cmdline(command)
        )
        identity: dict[str, object] = {
            "executable": normalized_executable,
            "command_line": command_line,
        }
    else:
        if isinstance(command, str):
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            )
        identity = {
            "executable": normalized_executable,
            "command": command,
        }
    return hashlib.sha256(_json_bytes(identity)).hexdigest()


def _command_fingerprint(command: list[str]) -> str:
    if not command:
        raise GoalProgressError("runtime command is invalid")
    return _process_command_fingerprint(command[0], command)


def _read_process_identity(pid: int) -> dict[str, str] | None:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise GoalProgressError("pending runtime process identity could not be verified")
    if os.name == "nt":
        script = (
            "$ErrorActionPreference='Stop';"
            f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\";"
            "if($null -eq $p){exit 3};"
            "$o=[ordered]@{creation_time=$p.CreationDate.ToUniversalTime().ToString('o');"
            "executable=$p.ExecutablePath;command_line=$p.CommandLine};"
            "$o|ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            ) from exc
        if completed.returncode == 3:
            return None
        if completed.returncode != 0:
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            )
        try:
            observed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            ) from exc
        if not isinstance(observed, dict):
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            )
        creation = observed.get("creation_time")
        executable = observed.get("executable")
        command_line = observed.get("command_line")
        if not all(isinstance(item, str) and item for item in (creation, executable, command_line)):
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            )
        fingerprint = _process_command_fingerprint(
            str(executable), str(command_line)
        )
        return {
            "process_creation_time": str(creation),
            "process_fingerprint": fingerprint,
        }

    proc = Path("/proc") / str(pid)
    try:
        stat_fields = (proc / "stat").read_text(encoding="utf-8").split()
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="utf-8"
        ).strip()
        executable = str((proc / "exe").resolve(strict=True))
        command = [
            item.decode("utf-8", errors="surrogateescape")
            for item in (proc / "cmdline").read_bytes().split(b"\0")
            if item
        ]
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, IndexError) as exc:
        raise GoalProgressError(
            "pending runtime process identity could not be verified"
        ) from exc
    if len(stat_fields) <= 21 or not boot_id or not command:
        raise GoalProgressError("pending runtime process identity could not be verified")
    fingerprint = _process_command_fingerprint(executable, command)
    return {
        "process_creation_time": f"{boot_id}:{stat_fields[21]}",
        "process_fingerprint": fingerprint,
    }


def _write_launch_journal(
    paths: GoalPaths, token_file: Path, command: list[str]
) -> dict[str, object]:
    journal = {
        "recovery_state": "launching",
        "goal_root": str(paths.root.resolve()),
        "submission_token_sha256": _submission_token_sha256(token_file),
        "command_fingerprint": _command_fingerprint(command),
    }
    try:
        atomic_write_json(_recovery_journal_path(paths), journal)
    except (GoalProgressError, OSError) as exc:
        raise GoalProgressError("runtime launch journal could not be created") from exc
    return journal


def _write_pending_journal(
    paths: GoalPaths,
    launching: dict[str, object],
    pid: int,
    identity: dict[str, str],
) -> dict[str, object]:
    pending = {
        **launching,
        "recovery_state": "pending-start",
        "pid": pid,
        "process_creation_time": identity["process_creation_time"],
        "process_fingerprint": identity["process_fingerprint"],
    }
    try:
        atomic_write_json(_recovery_journal_path(paths), pending)
    except (GoalProgressError, OSError) as exc:
        raise GoalProgressError(
            "runtime launch identity could not be persisted"
        ) from exc
    return pending


def _process_identity_matches(
    pending: dict[str, object], observed: dict[str, str]
) -> bool:
    return hmac.compare_digest(
        str(pending.get("process_creation_time")),
        observed["process_creation_time"],
    ) and hmac.compare_digest(
        str(pending.get("process_fingerprint")),
        observed["process_fingerprint"],
    )


def pending_runtime_block_reason(
    goal_root: Path, runtime_token_file: Path
) -> str | None:
    paths = GoalPaths.from_root(Path(goal_root))
    journal = _read_recovery_journal(paths)
    if journal is not None and journal.get("recovery_state") == "launching":
        return "pending runtime process identity could not be verified"
    if journal is not None and journal.get("recovery_state") == "cleanup-ready":
        return "runtime cleanup is incomplete"
    pending = _legacy_or_journal_pending(paths)
    if pending is None:
        return None
    try:
        token_sha256 = _submission_token_sha256(Path(runtime_token_file))
    except (GoalProgressError, OSError):
        return "pending runtime recovery identity is invalid"
    if (
        pending.get("goal_root") != str(paths.root.resolve())
        or pending.get("submission_token_sha256") != token_sha256
    ):
        return "pending runtime recovery identity is invalid"
    return "runtime process exit could not be confirmed"


def _process_exit_is_confirmed(process: subprocess.Popen[bytes]) -> bool:
    try:
        return process.poll() is not None
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _stop_failed_runtime_process(process: subprocess.Popen[bytes]) -> bool:
    if _process_exit_is_confirmed(process):
        return True
    try:
        process.terminate()
    except (OSError, ValueError, subprocess.SubprocessError):
        return _process_exit_is_confirmed(process)
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass
    except (OSError, ValueError, subprocess.SubprocessError):
        return _process_exit_is_confirmed(process)
    if _process_exit_is_confirmed(process):
        return True
    try:
        process.kill()
    except (OSError, ValueError, subprocess.SubprocessError):
        return _process_exit_is_confirmed(process)
    try:
        process.wait(timeout=1.0)
    except (subprocess.TimeoutExpired, OSError, ValueError, subprocess.SubprocessError):
        pass
    return _process_exit_is_confirmed(process)


def _preserve_failed_runtime_identity(
    paths: GoalPaths,
    token_file: Path,
    process: subprocess.Popen[bytes],
    launching: dict[str, object],
    identity: dict[str, str],
) -> None:
    pid = process.pid
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise GoalProgressError(
            "failed runtime process recovery identity could not be preserved"
        )
    pending = _write_pending_journal(paths, launching, pid, identity)
    try:
        current = _read_runtime_info(paths.writer_info)
    except GoalProgressError:
        current = None
    if (
        current is not None
        and current.get("goal_root") == str(paths.root.resolve())
        and current.get("pid") == pid
    ):
        return
    try:
        atomic_write_json(
            paths.writer_info,
            {
                "recovery_state": "pending-start",
                "goal_root": str(paths.root.resolve()),
                "pid": pid,
                "submission_token_sha256": _submission_token_sha256(token_file),
                "process_creation_time": pending["process_creation_time"],
                "process_fingerprint": pending["process_fingerprint"],
            },
        )
    except (GoalProgressError, OSError) as exc:
        raise GoalProgressError(
            "failed runtime process recovery identity could not be preserved"
        ) from exc


def _stop_pending_runtime_pid(pending: dict[str, object]) -> bool:
    pid = int(pending["pid"])
    observed = _read_process_identity(pid)
    if observed is None:
        return True
    if not _process_identity_matches(pending, observed):
        raise GoalProgressError(
            "pending runtime process identity could not be verified"
        )
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        raise GoalProgressError(
            "failed runtime process exit could not be confirmed"
        ) from exc
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        current = _read_process_identity(pid)
        if current is None or not _process_identity_matches(pending, current):
            return True
        time.sleep(0.02)
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    try:
        os.kill(pid, kill_signal)
    except OSError as exc:
        raise GoalProgressError(
            "failed runtime process exit could not be confirmed"
        ) from exc
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        current = _read_process_identity(pid)
        if current is None or not _process_identity_matches(pending, current):
            return True
        time.sleep(0.02)
    return False


def _recover_pending_runtime_locked(
    paths: GoalPaths, token_file: Path, pending: dict[str, object]
) -> None:
    if (
        pending.get("goal_root") != str(paths.root.resolve())
        or pending.get("submission_token_sha256")
        != _submission_token_sha256(token_file)
    ):
        raise GoalProgressError("pending runtime recovery identity is invalid")
    if not _stop_pending_runtime_pid(pending):
        raise GoalProgressError(
            "failed runtime process exit could not be confirmed"
        )

    current_journal = _read_recovery_journal(paths)
    if current_journal is not None and current_journal != pending:
        raise GoalProgressError("runtime recovery identity changed")
    current_pending = _read_pending_runtime_info(paths.writer_info)
    if current_pending is not None:
        if current_pending != pending:
            raise GoalProgressError("runtime recovery identity changed")
    elif paths.writer_info.exists():
        try:
            current = _read_runtime_info(paths.writer_info)
        except GoalProgressError as exc:
            raise GoalProgressError("runtime recovery identity changed") from exc
        if (
            current.get("goal_root") != pending.get("goal_root")
            or current.get("pid") != pending.get("pid")
        ):
            raise GoalProgressError("runtime recovery identity changed")
    elif current_journal is None:
        raise GoalProgressError("runtime recovery identity changed")
    if pending.get("submission_token_sha256") != _submission_token_sha256(token_file):
        raise GoalProgressError("runtime recovery identity changed")
    _replay_before_runtime_cleanup(paths)
    cleanup = _write_cleanup_ready(
        paths,
        token_file,
        command_fingerprint=str(pending.get("command_fingerprint") or "0" * 64),
    )
    _resume_cleanup_ready_locked(paths, token_file, cleanup)


def ensure_runtime(
    goal_root: Path,
    *,
    runtime_token_file: Path | None = None,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    readiness_timeout_seconds: float = 5.0,
) -> dict[str, object]:
    paths = GoalPaths.from_root(Path(goal_root))
    paths.assert_safe()
    if not paths.runtime.exists():
        paths.runtime.mkdir()
    paths.assert_safe()
    token_file = Path(runtime_token_file or (paths.runtime / "submission-token"))
    if token_file.parent.resolve() != paths.runtime.resolve():
        raise GoalProgressError("runtime credential path must stay inside goal runtime")

    try:
        with GoalLock(paths.runtime / RUNTIME_IDENTITY_LOCK):
            stale_info: dict[str, object] | None = None
            journal = _read_recovery_journal(paths)
            if journal is not None:
                if runtime_is_reusable(paths.root, token_file):
                    _recovery_journal_path(paths).unlink()
                    info = _read_runtime_info(paths.writer_info)
                    return {**info, "writer_status": "reused"}
                if journal["recovery_state"] == "cleanup-ready":
                    _resume_cleanup_ready_locked(paths, token_file, journal)
                elif journal["recovery_state"] == "pending-start":
                    _recover_pending_runtime_locked(paths, token_file, journal)
                else:
                    raise GoalProgressError(
                        "pending runtime process identity could not be verified"
                    )
            pending_info = _read_pending_runtime_info(paths.writer_info)
            if pending_info is not None:
                _recover_pending_runtime_locked(paths, token_file, pending_info)
            if paths.writer_info.exists() or token_file.exists():
                if runtime_is_reusable(paths.root, token_file):
                    info = _read_runtime_info(paths.writer_info)
                    return {**info, "writer_status": "reused"}
                live_pid = False
                try:
                    stale_info = _read_runtime_info(paths.writer_info)
                    live_pid = _pid_is_running(stale_info.get("pid"))
                except GoalProgressError:
                    pass
                if live_pid:
                    raise GoalProgressError(
                        "existing runtime identity could not be authenticated"
                    )
                _replay_before_runtime_cleanup(paths)

            recovery_snapshot = _snapshot_runtime_identity(paths, token_file)
            process: subprocess.Popen[bytes] | None = None
            launching: dict[str, object] | None = None
            process_identity: dict[str, str] | None = None
            try:
                _write_new_capability(token_file)
            except OSError as exc:
                raise GoalProgressError(
                    "runtime credential could not be created"
                ) from exc
            try:
                _remove_stale_descriptors(paths, stale_info)
                command = [
                    _runtime_python_executable(),
                    str(Path(__file__).with_name("goal_progress.py")),
                    "serve",
                    "--goal-root",
                    str(paths.root),
                    "--runtime-token-file",
                    str(token_file),
                    "--idle-timeout-seconds",
                    str(idle_timeout_seconds),
                ]
                try:
                    launching = _write_launch_journal(paths, token_file, command)
                except (GoalProgressError, OSError) as exc:
                    raise GoalProgressError(
                        "runtime launch journal could not be created"
                    ) from exc
                process = subprocess.Popen(command, **detached_process_options())
                process_identity = _read_process_identity(process.pid)
                if process_identity is None:
                    raise GoalProgressError(
                        "pending runtime process identity could not be verified"
                    )
                if not hmac.compare_digest(
                    process_identity["process_fingerprint"],
                    str(launching["command_fingerprint"]),
                ):
                    process = None
                    raise GoalProgressError(
                        "pending runtime process identity could not be verified"
                    )
                _write_pending_journal(
                    paths, launching, process.pid, process_identity
                )
                deadline = time.monotonic() + readiness_timeout_seconds
                last_reason = "runtime readiness timed out"
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        last_reason = "runtime exited before readiness"
                        break
                    if runtime_is_reusable(paths.root, token_file):
                        info = _read_runtime_info(paths.writer_info)
                        try:
                            _recovery_journal_path(paths).unlink()
                        except FileNotFoundError:
                            pass
                        return {**info, "writer_status": "started"}
                    time.sleep(0.05)
                raise GoalProgressError(last_reason)
            except (GoalProgressError, OSError) as exc:
                if process is not None:
                    if not _stop_failed_runtime_process(process):
                        if launching is not None and process_identity is not None:
                            _preserve_failed_runtime_identity(
                                paths,
                                token_file,
                                process,
                                launching,
                                process_identity,
                            )
                        raise GoalProgressError(
                            "failed runtime process exit could not be confirmed"
                            if process_identity is not None
                            else "pending runtime process identity could not be verified"
                        ) from exc
                _restore_runtime_identity(recovery_snapshot)
                if isinstance(exc, GoalProgressError):
                    raise
                raise GoalProgressError(
                    "runtime process could not be started"
                ) from exc
    except (OSError, TimeoutError) as exc:
        raise GoalProgressError("runtime identity is busy") from exc


def stop_runtime(
    goal_root: Path,
    *,
    runtime_token_file: Path | None = None,
    wait_timeout_seconds: float = 5.0,
) -> dict[str, object]:
    paths = GoalPaths.from_root(Path(goal_root))
    token_file = Path(runtime_token_file or (paths.runtime / "submission-token"))
    journal = _read_recovery_journal(paths)
    if journal is not None and not runtime_is_reusable(paths.root, token_file):
        if journal["recovery_state"] == "launching":
            raise GoalProgressError(
                "pending runtime process identity could not be verified"
            )
        try:
            with GoalLock(paths.runtime / RUNTIME_IDENTITY_LOCK):
                current = _read_recovery_journal(paths)
                if current != journal:
                    raise GoalProgressError("runtime recovery identity changed")
                if journal["recovery_state"] == "cleanup-ready":
                    _resume_cleanup_ready_locked(paths, token_file, journal)
                else:
                    _recover_pending_runtime_locked(paths, token_file, journal)
        except (OSError, TimeoutError) as exc:
            raise GoalProgressError("runtime cleanup identity is busy") from exc
        return {
            "status": "READY",
            "goal_root": str(paths.root.resolve()),
            "writer_status": "already-stopped",
        }
    pending_info = _read_pending_runtime_info(paths.writer_info)
    if pending_info is not None:
        try:
            with GoalLock(paths.runtime / RUNTIME_IDENTITY_LOCK):
                current_pending = _read_pending_runtime_info(paths.writer_info)
                if current_pending is None:
                    raise GoalProgressError("runtime recovery identity changed")
                _recover_pending_runtime_locked(paths, token_file, current_pending)
        except (OSError, TimeoutError) as exc:
            raise GoalProgressError("runtime cleanup identity is busy") from exc
        return {
            "status": "READY",
            "goal_root": str(paths.root.resolve()),
            "writer_status": "already-stopped",
        }
    if not paths.writer_info.exists() and not token_file.exists():
        _cleanup_runtime_identity(paths, token_file)
        return {
            "status": "READY",
            "goal_root": str(paths.root.resolve()),
            "writer_status": "already-stopped",
        }
    info = _read_runtime_info(paths.writer_info)
    capability = _read_capability(token_file)
    try:
        health = request_private_json(info, capability, "GET", "/health")
    except (OSError, urllib.error.URLError) as exc:
        if _shutdown_completion_matches(paths, info) and _writer_lock_is_available(
            paths
        ):
            _cleanup_runtime_identity(
                paths,
                token_file,
                expected_info=info,
                expected_capability=capability,
            )
            return {
                "status": "READY",
                "goal_root": str(paths.root.resolve()),
                "writer_status": "already-stopped",
            }
        if _pid_is_running(info.get("pid")) or not _writer_lock_is_available(paths):
            raise GoalProgressError("runtime identity could not be authenticated") from exc
        _cleanup_runtime_identity(
            paths,
            token_file,
            expected_info=info,
            expected_capability=capability,
        )
        return {
            "status": "READY",
            "goal_root": str(paths.root.resolve()),
            "writer_status": "already-stopped",
        }
    if not _identity_matches(paths.root, info, health):
        raise GoalProgressError("runtime identity mismatch")
    request_private_json(info, capability, "POST", "/shutdown")

    deadline = time.monotonic() + wait_timeout_seconds
    stopped = False
    while time.monotonic() < deadline:
        listener_closed = False
        try:
            request_private_json(
                info,
                capability,
                "GET",
                "/health",
                timeout_seconds=0.1,
            )
        except (GoalProgressError, OSError, urllib.error.URLError):
            listener_closed = True
        if (
            listener_closed
            and _shutdown_completion_matches(paths, info)
            and _writer_lock_is_available(paths)
        ):
            runtime_pid = info.get("pid")
            if runtime_pid == os.getpid() or not _pid_is_running(runtime_pid):
                stopped = True
                break
        time.sleep(0.02)
    if not stopped:
        raise GoalProgressError("runtime did not stop within five seconds")
    _cleanup_runtime_identity(
        paths,
        token_file,
        expected_info=info,
        expected_capability=capability,
    )
    return {
        "status": "READY",
        "goal_root": str(paths.root.resolve()),
        "writer_status": "stopped",
    }


def serve_runtime(
    goal_root: Path,
    runtime_token_file: Path,
    *,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> None:
    capability = _read_capability(Path(runtime_token_file))
    runtime = GoalProgressRuntime(
        Path(goal_root),
        capability,
        idle_timeout_seconds=idle_timeout_seconds,
    )
    runtime.run()
