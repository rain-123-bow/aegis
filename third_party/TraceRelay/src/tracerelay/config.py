"""Runtime constants, paths, and durable JSON helpers for TraceRelay v1."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


FORMAT_VERSION = 2
ALARM_FORMAT_VERSION = 1
PRODUCT_NAME = "TraceRelay"
CONTROL_PROTOCOL_VERSION = 2
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 43_190
CONTROL_MESSAGE_LIMIT = 64 * 1024
READ_CHUNK_SIZE = 64 * 1024
JOURNAL_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
SESSION_ADMISSION_RESERVE_BYTES = 16 * 1024 * 1024
UPSTREAM_CONNECT_TIMEOUT_SECONDS = 10.0
CLOSE_TIMEOUT_SECONDS = 10.0
HEARTBEAT_INTERVAL_SECONDS = 1.0
HEARTBEAT_TIMEOUT_SECONDS = 5.0
PROCESS_POLL_INTERVAL_SECONDS = 0.05
SUPERVISOR_START_TIMEOUT_SECONDS = 10.0
REGISTRATION_OPERATION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Filesystem locations used by one TraceRelay installation."""

    root: Path
    sessions: Path
    alarms: Path

    @classmethod
    def from_root(cls, root: Path) -> RuntimePaths:
        resolved_root = Path(root).expanduser().resolve()
        return cls(
            root=resolved_root,
            sessions=resolved_root / "sessions",
            alarms=resolved_root / "alarms",
        )

    @classmethod
    def default(cls) -> RuntimePaths:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            root = Path(local_app_data) / "TraceRelay"
        else:
            root = Path.home() / "AppData" / "Local" / "TraceRelay"
        return cls.from_root(root)

    def ensure(self) -> None:
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.alarms.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class AlarmRecord:
    """The durable identity and public summary of one runtime alarm."""

    incident_id: str
    reason: str
    path: Path

    def public_summary(self) -> dict[str, object]:
        return {
            "incident_id": self.incident_id,
            "reason": self.reason,
            "alarm_path": str(self.path),
        }


def utc_now_text() -> str:
    """Return a stable UTC timestamp suitable for JSON metadata."""

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_session_id() -> str:
    """Create the required UTC-and-random session identifier."""

    created = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{created}_{uuid4().hex}"


def new_incident_id() -> str:
    """Create a sortable UTC-and-random alarm identifier."""

    created = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{created}_{uuid4().hex}"


def validate_registration_operation_id(value: object) -> str:
    """Return one canonical caller-owned registration operation identity."""
    if (
        not isinstance(value, str)
        or REGISTRATION_OPERATION_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("operation_id must be 32 lowercase hexadecimal characters")
    return value


def write_alarm(
    paths: RuntimePaths,
    *,
    source: str,
    reason: str,
    service_pid: int | None,
    supervisor_pid: int | None,
    session_id: str | None,
    error: BaseException | None = None,
    message: str | None = None,
) -> AlarmRecord:
    """Write one complete alarm JSON file and return its public identity."""

    if source not in {"service", "supervisor"}:
        raise ValueError("alarm source must be service or supervisor")
    if not isinstance(reason, str) or not reason:
        raise ValueError("alarm reason must be a non-empty string")
    for field, process_id in (
        ("service_pid", service_pid),
        ("supervisor_pid", supervisor_pid),
    ):
        if process_id is not None and (
            isinstance(process_id, bool)
            or not isinstance(process_id, int)
            or process_id <= 0
        ):
            raise ValueError(f"{field} must be a positive integer or null")
    if session_id is not None and (not isinstance(session_id, str) or not session_id):
        raise ValueError("session_id must be a non-empty string or null")

    incident_id = new_incident_id()
    alarm_path = paths.alarms / f"{incident_id}.json"
    detail = str(error) if error is not None else ""
    if not detail:
        detail = message or reason
    exception_type = type(error).__name__ if error is not None else None
    atomic_write_json(
        alarm_path,
        {
            "format_version": ALARM_FORMAT_VERSION,
            "incident_id": incident_id,
            "created_at_utc": utc_now_text(),
            "source": source,
            "reason": reason,
            "service_pid": service_pid,
            "supervisor_pid": supervisor_pid,
            "session_id": session_id,
            "exception_type": exception_type,
            "message": detail,
        },
    )
    return AlarmRecord(incident_id, reason, alarm_path)


def latest_alarm_summary(paths: RuntimePaths) -> dict[str, object] | None:
    """Return the newest alarm's bounded public fields without exposing its body."""

    try:
        alarm_path = max(paths.alarms.glob("*.json"), key=lambda path: path.name)
    except ValueError:
        return None
    try:
        if alarm_path.stat().st_size > CONTROL_MESSAGE_LIMIT:
            raise ValueError("alarm file exceeds 64 KiB")
        value = json.loads(
            alarm_path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
        if not isinstance(value, dict):
            raise ValueError("alarm must be a JSON object")
        incident_id = value.get("incident_id")
        source = value.get("source")
        reason = value.get("reason")
        if not all(
            isinstance(item, str) and item for item in (incident_id, source, reason)
        ):
            raise ValueError("alarm public fields are invalid")
        return {
            "incident_id": incident_id,
            "reason": reason,
            "alarm_path": str(alarm_path),
        }
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return {
            "incident_id": alarm_path.stem,
            "reason": "unreadable_alarm",
            "alarm_path": str(alarm_path),
        }


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Durably write a small UTF-8 JSON object and atomically publish it."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")
