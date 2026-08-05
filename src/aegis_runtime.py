from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from project_seal_store import StoredProjectSeal, verify_expected_project_seal
from tracerelay_client import (
    EvidenceProcessResult,
    TraceRelayClient,
    TraceRelayError,
    TraceRelayRegistration,
    parse_loopback_proxy_port,
    resolve_tracerelay_command,
)


RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class RuntimeStateError(RuntimeError):
    pass


def new_run_id() -> str:
    created = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{created}_{uuid4().hex}"


_ACTIVE_COORDINATOR: ContextVar[RuntimeCoordinator | None] = ContextVar(
    "aegis_runtime_coordinator", default=None
)


class RuntimeCoordinator:
    def __init__(
        self,
        *,
        project_root: str | Path,
        artifact_path: str | Path,
        run_id: str,
        upstream_port: int,
        relay_client: TraceRelayClient,
        start_node: str,
        prior_state: Mapping[str, object] | None = None,
    ) -> None:
        if RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
            raise ValueError("run_id contains unsupported path characters")
        self.project_root = Path(project_root).resolve()
        self.artifact_path = Path(artifact_path).resolve()
        self.run_id = run_id
        self.upstream_port = upstream_port
        self.relay_client = relay_client
        self.start_node = start_node
        self.run_state_path = (
            self.artifact_path / ".aegis" / "runs" / run_id / "RUN_STATE.json"
        )
        self._created_at_utc = _utc_now_text()
        self._current_node: str | None = None
        self._last_completed_node: str | None = None
        self._last_state: dict[str, Any] | None = None
        self._seal: StoredProjectSeal | None = None
        self._evidence_sessions: list[dict[str, object]] = []
        if prior_state is not None:
            self._restore(prior_state)

    def _restore(self, state: Mapping[str, object]) -> None:
        if state.get("run_id") != self.run_id:
            raise RuntimeStateError("prior run state identity mismatch")
        if state.get("start_node") != self.start_node:
            raise RuntimeStateError("prior run state start node mismatch")
        stored_root = state.get("project_root")
        if not isinstance(stored_root, str) or Path(stored_root).resolve() != self.project_root:
            raise RuntimeStateError("prior run state project root mismatch")
        created_at = state.get("created_at_utc")
        graph_state = state.get("graph_state")
        evidence = state.get("evidence_sessions")
        if not isinstance(created_at, str) or not created_at:
            raise RuntimeStateError("prior run state has no creation time")
        if graph_state is not None and not isinstance(graph_state, dict):
            raise RuntimeStateError("prior run graph state must be an object or null")
        if not isinstance(evidence, list) or not all(isinstance(x, dict) for x in evidence):
            raise RuntimeStateError("prior evidence sessions must be a list of objects")
        self._created_at_utc = created_at
        self._current_node = _optional_string(state.get("current_node"))
        self._last_completed_node = _optional_string(state.get("last_completed_node"))
        self._last_state = dict(graph_state) if graph_state is not None else None
        self._evidence_sessions = [dict(item) for item in evidence]

    def preflight(self) -> None:
        try:
            self._seal = verify_expected_project_seal(self.project_root)
            self.relay_client.start()
        except BaseException as error:
            self._write_state("failed", error)
            raise
        self._write_state("ready")

    def execute_node(
        self,
        node_name: str,
        operation: Callable[[dict[str, Any]], dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        self._current_node = node_name
        self._last_state = dict(state)
        self._write_state("running")
        token = _ACTIVE_COORDINATOR.set(self)
        try:
            result = operation(state)
        except BaseException as error:
            self._write_state("failed", error)
            raise
        finally:
            _ACTIVE_COORDINATOR.reset(token)
        self._last_completed_node = node_name
        self._current_node = None
        self._last_state = dict(result)
        self._write_state("running")
        return result

    def run_codex_process(
        self, command: Sequence[str], *, timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self.relay_client.run_process(
                command,
                upstream_port=self.upstream_port,
                timeout_seconds=timeout_seconds,
            )
        except BaseException:
            registration = getattr(self.relay_client, "last_registration", None)
            if isinstance(registration, TraceRelayRegistration):
                verification = getattr(self.relay_client, "last_verification", None)
                self._record_evidence(
                    registration,
                    verification if isinstance(verification, Mapping) else None,
                )
                self._write_state("running")
            raise
        self._record_evidence(result.registration, result.verification)
        self._write_state("running")
        return result.completed

    def _record_evidence(
        self,
        registration: TraceRelayRegistration,
        verification: Mapping[str, object] | None,
    ) -> None:
        entry = {
            "node": self._current_node,
            "session_id": registration.session_id,
            "session_path": str(registration.session_path),
            "verification_status": (
                verification.get("status") if verification else "UNVERIFIED"
            ),
            "final_hash": verification.get("final_hash") if verification else None,
        }
        for index, existing in enumerate(self._evidence_sessions):
            if existing.get("session_id") == registration.session_id:
                self._evidence_sessions[index] = entry
                return
        self._evidence_sessions.append(entry)

    def complete(self, state: dict[str, Any]) -> None:
        self._current_node = None
        self._last_state = dict(state)
        self._write_state("completed")

    def fail(self, error: BaseException) -> None:
        self._write_state("failed", error)

    def _write_state(
        self, status: str, error: BaseException | None = None
    ) -> None:
        payload: dict[str, object] = {
            "schema": "aegis.run_state.v1",
            "run_id": self.run_id,
            "status": status,
            "project_root": str(self.project_root),
            "artifact_path": str(self.artifact_path),
            "start_node": self.start_node,
            "current_node": self._current_node,
            "last_completed_node": self._last_completed_node,
            "graph_state": self._last_state,
            "evidence_sessions": list(self._evidence_sessions),
            "created_at_utc": self._created_at_utc,
            "updated_at_utc": _utc_now_text(),
        }
        if self._seal is not None:
            payload.update(
                seal_sequence=self._seal.sequence,
                expected_seal=self._seal.expected_seal,
            )
        if error is not None:
            payload["error"] = {"type": type(error).__name__, "message": str(error)}
        _atomic_write_json(self.run_state_path, payload)


def active_runtime_coordinator() -> RuntimeCoordinator | None:
    return _ACTIVE_COORDINATOR.get()


def load_run_state(artifact_path: str | Path, run_id: str) -> dict[str, object]:
    if RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
        raise ValueError("run_id contains unsupported path characters")
    path = Path(artifact_path).resolve() / ".aegis" / "runs" / run_id / "RUN_STATE.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeStateError(f"cannot load run state: {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema") != "aegis.run_state.v1":
        raise RuntimeStateError("run state has an unsupported schema")
    if payload.get("run_id") != run_id:
        raise RuntimeStateError("run state identity mismatch")
    return payload


@contextmanager
def open_graph_checkpointer(project_root: str | Path) -> Iterator[SqliteSaver]:
    path = Path(project_root).resolve() / ".aegis" / "runtime" / "checkpoints.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        yield SqliteSaver(connection)
    finally:
        connection.close()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RuntimeStateError("run state node names must be strings or null")
    return value


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
