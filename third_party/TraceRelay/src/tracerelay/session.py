"""Single-session state machine and foreground TCP relay for TraceRelay v1."""

from __future__ import annotations

import errno
import json
import select
import shutil
import socket
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from .config import (
    CLOSE_TIMEOUT_SECONDS,
    CONTROL_HOST,
    CONTROL_MESSAGE_LIMIT,
    FORMAT_VERSION,
    JOURNAL_LIMIT_BYTES,
    READ_CHUNK_SIZE,
    SESSION_ADMISSION_RESERVE_BYTES,
    UPSTREAM_CONNECT_TIMEOUT_SECONDS,
    RuntimePaths,
    atomic_write_json,
    new_session_id,
    utc_now_text,
    validate_registration_operation_id,
)
from .journal import Direction, JournalWriter


class SessionState(StrEnum):
    IDLE = "IDLE"
    WAITING = "WAITING"
    CONNECTING = "CONNECTING"
    RELAYING = "RELAYING"
    FAULT = "FAULT"


class SessionError(RuntimeError):
    """Base class for expected session-control failures."""


class SessionBusyError(SessionError):
    pass


class SessionAdmissionError(SessionError):
    pass


class SessionCloseTimeout(SessionError):
    pass


@dataclass(frozen=True, slots=True)
class SessionRegistration:
    session_id: str
    proxy_host: str
    proxy_port: int
    upstream_host: str
    upstream_port: int
    session_path: Path
    operation_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "session_id": self.session_id,
            "proxy_host": self.proxy_host,
            "proxy_port": self.proxy_port,
            "upstream_host": self.upstream_host,
            "upstream_port": self.upstream_port,
            "session_path": str(self.session_path),
        }
        if self.operation_id is not None:
            result["operation_id"] = self.operation_id
        return result


class SessionManager:
    """Own the sole waiting or running session allowed by v1."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        on_fault: Callable[[SessionRegistration, BaseException], None] | None = None,
        journal_limit_bytes: int = JOURNAL_LIMIT_BYTES,
        admission_reserve_bytes: int = SESSION_ADMISSION_RESERVE_BYTES,
    ) -> None:
        if (
            type(journal_limit_bytes) is not int
            or not 1 <= journal_limit_bytes <= JOURNAL_LIMIT_BYTES
        ):
            raise ValueError(
                "journal_limit_bytes must be an integer between 1 and "
                f"{JOURNAL_LIMIT_BYTES}"
            )
        if (
            type(admission_reserve_bytes) is not int
            or not 0 <= admission_reserve_bytes <= SESSION_ADMISSION_RESERVE_BYTES
        ):
            raise ValueError(
                "admission_reserve_bytes must be an integer between 0 and "
                f"{SESSION_ADMISSION_RESERVE_BYTES}"
            )
        self.paths = paths
        self.paths.ensure()
        self._fault_callback = on_fault
        self._journal_limit_bytes = journal_limit_bytes
        self._admission_required_bytes = journal_limit_bytes + admission_reserve_bytes
        self._lock = threading.Lock()
        self._state = SessionState.IDLE
        self._active: _RelaySession | None = None
        self._last_session_id: str | None = None
        self._last_session_path: Path | None = None
        self._last_error: str | None = None
        self.faulted = threading.Event()

    def register(
        self, upstream_port: int, *, operation_id: str | None = None
    ) -> SessionRegistration:
        _validate_port(upstream_port)
        if operation_id is not None:
            operation_id = validate_registration_operation_id(operation_id)
        with self._lock:
            if self._state is not SessionState.IDLE or self._active is not None:
                raise SessionBusyError(f"cannot register while state is {self._state}")

            try:
                free_bytes = shutil.disk_usage(self.paths.sessions).free
            except OSError as error:
                raise SessionAdmissionError(
                    f"cannot determine available session storage: {error}"
                ) from error
            if free_bytes < self._admission_required_bytes:
                raise SessionAdmissionError(
                    "insufficient free space for a new session: "
                    f"{free_bytes} bytes available, "
                    f"{self._admission_required_bytes} bytes required"
                )

            session_id = new_session_id()
            session_path = self.paths.sessions / session_id
            session_path.mkdir(parents=False, exist_ok=False)
            listener: socket.socket | None = None
            journal: JournalWriter | None = None
            try:
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    listener.setsockopt(
                        socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                    )
                listener.bind((CONTROL_HOST, 0))
                proxy_port = int(listener.getsockname()[1])
                metadata = {
                    "format_version": FORMAT_VERSION,
                    "session_id": session_id,
                    "created_at_utc": utc_now_text(),
                    "proxy_host": CONTROL_HOST,
                    "proxy_port": proxy_port,
                    "upstream_host": CONTROL_HOST,
                    "upstream_port": upstream_port,
                    "limits": {
                        "read_chunk_size": READ_CHUNK_SIZE,
                        "control_message_limit": CONTROL_MESSAGE_LIMIT,
                        "journal_limit_bytes": self._journal_limit_bytes,
                        "admission_required_free_bytes": self._admission_required_bytes,
                        "upstream_connect_timeout_seconds": UPSTREAM_CONNECT_TIMEOUT_SECONDS,
                        "single_client": False,
                    },
                }
                if operation_id is not None:
                    metadata["operation_id"] = operation_id
                atomic_write_json(session_path / "session.json", metadata)
                journal = JournalWriter(
                    session_path / "journal.trr",
                    max_bytes=self._journal_limit_bytes,
                )
                listener.listen()
                registration = SessionRegistration(
                    session_id=session_id,
                    proxy_host=CONTROL_HOST,
                    proxy_port=proxy_port,
                    upstream_host=CONTROL_HOST,
                    upstream_port=upstream_port,
                    session_path=session_path,
                    operation_id=operation_id,
                )
                relay = _RelaySession(
                    registration=registration,
                    listener=listener,
                    journal=journal,
                    on_state=self._on_state,
                    on_fault=self._on_fault,
                    on_finished=self._on_finished,
                )
                self._active = relay
                self._state = SessionState.WAITING
                self._last_error = None
                self.faulted.clear()
                relay.start()
                return registration
            except BaseException:
                if listener is not None:
                    _close_socket(listener)
                if journal is not None:
                    journal.close()
                raise

    def status(self) -> dict[str, object]:
        with self._lock:
            result: dict[str, object] = {"state": self._state.value}
            if self._active is not None:
                result.update(self._active.registration.as_dict())
            if self._last_session_id is not None:
                result["last_session_id"] = self._last_session_id
            if self._last_session_path is not None:
                result["last_session_path"] = str(self._last_session_path)
            if self._last_error is not None:
                result["last_error"] = self._last_error
            return result

    def close(self, timeout: float = CLOSE_TIMEOUT_SECONDS) -> dict[str, object]:
        with self._lock:
            relay = self._active
            state = self._state
        if relay is None:
            return {"closed": False, "state": state.value}

        relay.request_close()
        if not relay.done.wait(timeout):
            relay.force_abort()
            raise SessionCloseTimeout(
                f"session did not close within {timeout:g} seconds"
            )
        result = self.status()
        if result["state"] == SessionState.FAULT.value:
            detail = result.get("last_error", "session ended incomplete")
            raise SessionError(f"session ended incomplete: {detail}")
        result["closed"] = True
        result["session_id"] = relay.registration.session_id
        return result

    def shutdown(self, timeout: float = CLOSE_TIMEOUT_SECONDS) -> None:
        with self._lock:
            relay = self._active
        if relay is None:
            return
        relay.request_close()
        if not relay.done.wait(timeout):
            relay.force_abort()

    def abort(self, reason: str, timeout: float = 2.0) -> None:
        """Force the active session incomplete after a process-level fault."""

        if not isinstance(reason, str) or not reason:
            raise ValueError("abort reason must be a non-empty string")
        with self._lock:
            relay = self._active
            if relay is None:
                self._state = SessionState.FAULT
                self._last_error = reason
                self.faulted.set()
                return
        relay.force_abort()
        if not relay.done.wait(timeout):
            with self._lock:
                if self._active is relay:
                    self._state = SessionState.FAULT
                    self._last_error = reason
                    self.faulted.set()

    def _on_state(self, relay: _RelaySession, state: SessionState) -> None:
        with self._lock:
            if self._active is relay:
                self._state = state

    def _on_fault(self, relay: _RelaySession, error: BaseException) -> None:
        with self._lock:
            if self._active is not relay:
                return
            self._state = SessionState.FAULT
            self._last_error = str(error)
        try:
            if self._fault_callback is not None:
                self._fault_callback(relay.registration, error)
        finally:
            with self._lock:
                if self._active is relay:
                    self.faulted.set()

    def _on_finished(
        self, relay: _RelaySession, completed: bool, error: BaseException | None
    ) -> None:
        with self._lock:
            if self._active is not relay:
                return
            self._last_session_id = relay.registration.session_id
            self._last_session_path = relay.registration.session_path
            self._active = None
            if completed:
                self._state = SessionState.IDLE
                self._last_error = None
                self.faulted.clear()
            else:
                self._state = SessionState.FAULT
                self._last_error = (
                    str(error) if error is not None else "session aborted"
                )
                self.faulted.set()


def resolve_registration_operation(
    paths: RuntimePaths, operation_id: str
) -> SessionRegistration | None:
    """Resolve one durable registration result without a running Service."""
    expected_operation_id = validate_registration_operation_id(operation_id)
    if not paths.sessions.exists():
        return None
    matches: list[SessionRegistration] = []
    for session_path in sorted(paths.sessions.iterdir(), key=lambda path: path.name):
        if not session_path.is_dir():
            continue
        metadata_path = session_path / "session.json"
        try:
            if metadata_path.stat().st_size > CONTROL_MESSAGE_LIMIT:
                raise ValueError("session metadata exceeds 64 KiB")
            with metadata_path.open("r", encoding="utf-8") as stream:
                metadata = json.load(stream, parse_constant=_reject_json_constant)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise SessionError(
                f"cannot resolve registration through {metadata_path}: {error}"
            ) from error
        if not isinstance(metadata, dict):
            raise SessionError(f"session metadata is not an object: {metadata_path}")
        if metadata.get("operation_id") != expected_operation_id:
            continue
        session_id = metadata.get("session_id")
        if not isinstance(session_id, str) or session_id != session_path.name:
            raise SessionError("resolved registration has an invalid session identity")
        proxy_host = metadata.get("proxy_host")
        upstream_host = metadata.get("upstream_host")
        if proxy_host != CONTROL_HOST or upstream_host != CONTROL_HOST:
            raise SessionError("resolved registration has a non-loopback endpoint")
        proxy_port = metadata.get("proxy_port")
        upstream_port = metadata.get("upstream_port")
        try:
            _validate_port(proxy_port)
            _validate_port(upstream_port)
        except ValueError as error:
            raise SessionError("resolved registration has an invalid port") from error
        matches.append(
            SessionRegistration(
                session_id=session_id,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                upstream_host=upstream_host,
                upstream_port=upstream_port,
                session_path=session_path.resolve(),
                operation_id=expected_operation_id,
            )
        )
    if len(matches) > 1:
        raise SessionError("registration operation resolves to multiple sessions")
    return matches[0] if matches else None


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


@dataclass(slots=True)
class _ConnectionState:
    connection_id: int
    client: socket.socket
    upstream: socket.socket | None = None
    phase: SessionState = SessionState.CONNECTING
    thread: threading.Thread | None = None


class _RelaySession:
    def __init__(
        self,
        *,
        registration: SessionRegistration,
        listener: socket.socket,
        journal: JournalWriter,
        on_state: Callable[[_RelaySession, SessionState], None],
        on_fault: Callable[[_RelaySession, BaseException], None],
        on_finished: Callable[[_RelaySession, bool, BaseException | None], None],
    ) -> None:
        self.registration = registration
        self.done = threading.Event()
        self._listener = listener
        self._journal = journal
        self._on_state = on_state
        self._on_fault = on_fault
        self._on_finished = on_finished
        self._stop = threading.Event()
        self._close_requested = threading.Event()
        self._forced = threading.Event()
        self._socket_lock = threading.Lock()
        self._failure_lock = threading.Lock()
        self._failure: BaseException | None = None
        self._fault_notified = False
        self._connections: dict[int, _ConnectionState] = {}
        self._next_connection_id = 1
        self._accepted_connections = 0
        self._thread = threading.Thread(
            target=self._run,
            name=f"TraceRelay-{registration.session_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def request_close(self) -> None:
        self._close_requested.set()
        self._stop.set()
        _close_socket(self._listener)
        self._shutdown_connections(close=True, connecting_only=True)

    def force_abort(self) -> None:
        self._forced.set()
        self.request_close()
        self._shutdown_connections(close=True)

    def _run(self) -> None:
        completed = False
        failure: BaseException | None = None
        try:
            try:
                self._listener.settimeout(0.25)
            except OSError:
                if not self._stop.is_set():
                    raise

            while not self._stop.is_set():
                try:
                    client, _address = self._listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                if self._stop.is_set():
                    _close_socket(client)
                    break
                client.settimeout(None)
                self._start_connection(client)

            self._join_connections()

            with self._failure_lock:
                failure = self._failure
            if failure is not None:
                raise failure
            if self._forced.is_set():
                raise SessionError("session was forcibly aborted")
            if not self._close_requested.is_set():
                raise SessionError("session listener stopped without an explicit close")
            reason = (
                "close_requested"
                if self._accepted_connections
                else "close_requested_waiting"
            )
            self._seal(reason)
            completed = True
        except BaseException as error:
            failure = error
            if self._forced.is_set():
                self._on_state(self, SessionState.FAULT)
            else:
                self._notify_failure(error)
        finally:
            self._stop.set()
            _close_socket(self._listener)
            if failure is not None or self._forced.is_set():
                self._shutdown_connections(close=True)
            self._join_connections()
            try:
                self._journal.close()
            except OSError as error:
                if failure is None:
                    failure = error
                    completed = False
                    if not self._forced.is_set():
                        self._notify_failure(error)
            self._close_connections()
            self._on_finished(self, completed, failure)
            self.done.set()

    def _start_connection(self, client: socket.socket) -> None:
        with self._socket_lock:
            connection_id = self._next_connection_id
            self._next_connection_id += 1
            self._accepted_connections += 1
            connection = _ConnectionState(connection_id, client)
            worker = threading.Thread(
                target=self._run_connection,
                args=(connection,),
                name=f"TraceRelay-connection-{connection_id}",
                daemon=True,
            )
            connection.thread = worker
            self._connections[connection_id] = connection
        try:
            worker.start()
        except BaseException:
            with self._socket_lock:
                self._connections.pop(connection_id, None)
            _close_socket(client)
            raise
        self._publish_aggregate_state()

    def _run_connection(self, connection: _ConnectionState) -> None:
        try:
            if self._stop.is_set():
                return
            upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream.settimeout(UPSTREAM_CONNECT_TIMEOUT_SECONDS)
            with self._socket_lock:
                current = self._connections.get(connection.connection_id)
                if current is not connection:
                    _close_socket(upstream)
                    return
                connection.upstream = upstream
            if self._stop.is_set():
                return
            upstream.connect(
                (self.registration.upstream_host, self.registration.upstream_port)
            )
            upstream.settimeout(None)
            if self._stop.is_set():
                return
            self._set_connection_phase(connection, SessionState.RELAYING)
            workers = [
                threading.Thread(
                    target=self._relay,
                    args=(
                        connection.connection_id,
                        connection.client,
                        upstream,
                        Direction.CLIENT_TO_UPSTREAM,
                    ),
                    name=(f"TraceRelay-{connection.connection_id}-client-to-upstream"),
                    daemon=True,
                ),
                threading.Thread(
                    target=self._relay,
                    args=(
                        connection.connection_id,
                        upstream,
                        connection.client,
                        Direction.UPSTREAM_TO_CLIENT,
                    ),
                    name=(f"TraceRelay-{connection.connection_id}-upstream-to-client"),
                    daemon=True,
                ),
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
        except BaseException as error:
            if not self._stop.is_set():
                self._record_failure(error)
        finally:
            _close_socket(connection.client)
            if connection.upstream is not None:
                _close_socket(connection.upstream)
            with self._socket_lock:
                if self._connections.get(connection.connection_id) is connection:
                    del self._connections[connection.connection_id]
            self._publish_aggregate_state()

    def _set_connection_phase(
        self,
        connection: _ConnectionState,
        phase: SessionState,
    ) -> None:
        with self._socket_lock:
            if self._connections.get(connection.connection_id) is not connection:
                return
            connection.phase = phase
        self._publish_aggregate_state()

    def _publish_aggregate_state(self) -> None:
        if self._stop.is_set():
            return
        with self._socket_lock:
            phases = {connection.phase for connection in self._connections.values()}
        if SessionState.RELAYING in phases:
            state = SessionState.RELAYING
        elif SessionState.CONNECTING in phases:
            state = SessionState.CONNECTING
        else:
            state = SessionState.WAITING
        self._on_state(self, state)

    def _join_connections(self) -> None:
        while True:
            with self._socket_lock:
                workers = [
                    connection.thread
                    for connection in self._connections.values()
                    if connection.thread is not None
                ]
            if not workers:
                return
            for worker in workers:
                worker.join(timeout=0.25)

    def _relay(
        self,
        connection_id: int,
        source: socket.socket,
        destination: socket.socket,
        direction: Direction,
    ) -> None:
        while not self._stop.is_set():
            try:
                readable, _writable, _exceptional = select.select(
                    [source], [], [], 0.25
                )
            except (OSError, ValueError) as error:
                if self._stop.is_set():
                    return
                if isinstance(error, OSError) and _is_connection_terminal_error(error):
                    self._terminate_connection(source, destination)
                    return
                self._record_failure(error)
                return
            if not readable or self._stop.is_set():
                continue
            try:
                payload = source.recv(READ_CHUNK_SIZE)
            except OSError as error:
                if self._stop.is_set():
                    return
                if _is_connection_terminal_error(error):
                    self._terminate_connection(source, destination)
                    return
                self._record_failure(error)
                return
            if not payload:
                _shutdown_socket(destination, socket.SHUT_WR)
                return

            try:
                reference = self._journal.append_data(
                    direction,
                    payload,
                    connection_id=connection_id,
                )
            except BaseException as error:
                self._record_failure(error)
                return

            try:
                destination.sendall(payload)
            except OSError as error:
                try:
                    self._journal.append_send_error(reference, _error_code(error))
                except BaseException as journal_error:
                    self._record_failure(journal_error)
                    return
                if _is_connection_terminal_error(error):
                    self._terminate_connection(source, destination)
                    return
                self._record_failure(error)
                return

            try:
                self._journal.append_send_ok(reference)
            except BaseException as error:
                self._record_failure(error)
                return

    @staticmethod
    def _terminate_connection(
        first: socket.socket,
        second: socket.socket,
    ) -> None:
        _shutdown_socket(first, socket.SHUT_RDWR)
        _shutdown_socket(second, socket.SHUT_RDWR)

    def _record_failure(self, error: BaseException) -> None:
        first_failure = False
        with self._failure_lock:
            if self._failure is None:
                self._failure = error
                first_failure = True
        self._stop.set()
        if not first_failure or self._forced.is_set():
            return
        _close_socket(self._listener)
        self._notify_failure(error)
        self._shutdown_connections(close=True)

    def _notify_failure(self, error: BaseException) -> None:
        with self._failure_lock:
            if self._fault_notified:
                return
            self._fault_notified = True
        self._on_fault(self, error)

    def _shutdown_connections(
        self,
        *,
        close: bool = False,
        connecting_only: bool = False,
    ) -> None:
        with self._socket_lock:
            sockets = [
                connection_socket
                for connection in self._connections.values()
                if not connecting_only or connection.phase is SessionState.CONNECTING
                for connection_socket in (connection.client, connection.upstream)
                if connection_socket is not None
            ]
        for connection_socket in sockets:
            _shutdown_socket(connection_socket, socket.SHUT_RDWR)
            if close:
                _close_socket(connection_socket)

    def _close_connections(self) -> None:
        with self._socket_lock:
            sockets = [
                connection_socket
                for connection in self._connections.values()
                for connection_socket in (connection.client, connection.upstream)
                if connection_socket is not None
            ]
        for connection_socket in sockets:
            _close_socket(connection_socket)

    def _seal(self, reason: str) -> None:
        summary = self._journal.summary()
        if summary.pending_results:
            raise SessionError("cannot seal a journal with unknown send results")
        self._journal.close()
        complete_path = self.registration.session_path / "complete.json"
        if complete_path.exists():
            raise SessionError("complete.json already exists")
        atomic_write_json(
            complete_path,
            {
                "format_version": FORMAT_VERSION,
                "session_id": self.registration.session_id,
                "closed_at_utc": utc_now_text(),
                "end_reason": reason,
                "final_sequence": summary.final_sequence,
                "final_hash": summary.final_hash,
                "observed_bytes": summary.observed_bytes,
                "sent_success_bytes": summary.sent_success_bytes,
            },
        )


def _validate_port(port: int) -> None:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65_535:
        raise ValueError("upstream_port must be an integer between 1 and 65535")


def _error_code(error: OSError) -> int:
    code = error.errno
    if code is None or code == 0:
        return -1
    if -(2**31) <= code < 2**31:
        return code
    return errno.EIO


def _is_connection_terminal_error(error: OSError) -> bool:
    portable_codes = {
        errno.ECONNABORTED,
        errno.ECONNRESET,
        errno.EPIPE,
        errno.ENOTCONN,
        getattr(errno, "ESHUTDOWN", -1),
    }
    windows_codes = {10053, 10054, 10057, 10058}
    return (
        error.errno in portable_codes | windows_codes
        or getattr(error, "winerror", None) in windows_codes
    )


def _shutdown_socket(connection: socket.socket, how: int) -> None:
    try:
        connection.shutdown(how)
    except OSError:
        pass


def _close_socket(connection: socket.socket) -> None:
    try:
        connection.close()
    except OSError:
        pass
