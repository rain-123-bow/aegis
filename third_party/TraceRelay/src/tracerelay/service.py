"""Relay Service control endpoint and managed v1 process runtime."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Mapping

from .config import (
    CLOSE_TIMEOUT_SECONDS,
    CONTROL_PROTOCOL_VERSION,
    CONTROL_HOST,
    CONTROL_PORT,
    HEARTBEAT_TIMEOUT_SECONDS,
    JOURNAL_LIMIT_BYTES,
    PROCESS_POLL_INTERVAL_SECONDS,
    PRODUCT_NAME,
    SESSION_ADMISSION_RESERVE_BYTES,
    RuntimePaths,
    latest_alarm_summary,
    write_alarm,
)
from .control import ControlServer
from .runtime_identity import (
    RuntimeExpectation,
    build_managed_runtime_identity,
    capture_process_identity,
)
from .session import (
    SessionAdmissionError,
    SessionError,
    SessionManager,
    SessionRegistration,
    SessionState,
)


class TraceRelayService:
    """Combine the local control endpoint with the single-session relay."""

    def __init__(
        self,
        *,
        paths: RuntimePaths | None = None,
        control_host: str = CONTROL_HOST,
        control_port: int = CONTROL_PORT,
        supervisor_pid: int | None = None,
        managed: bool = False,
        runtime_identity: dict[str, object] | None = None,
        journal_limit_bytes: int = JOURNAL_LIMIT_BYTES,
        admission_reserve_bytes: int = SESSION_ADMISSION_RESERVE_BYTES,
    ) -> None:
        if supervisor_pid is not None and (
            isinstance(supervisor_pid, bool)
            or not isinstance(supervisor_pid, int)
            or supervisor_pid <= 0
        ):
            raise ValueError("supervisor_pid must be a positive integer or null")
        self.paths = paths or RuntimePaths.default()
        self.service_pid = os.getpid()
        self.supervisor_pid = supervisor_pid
        self.managed = managed
        if managed and runtime_identity is None:
            raise ValueError("managed TraceRelay requires a runtime identity")
        if not managed and runtime_identity is not None:
            raise ValueError("foreground TraceRelay cannot claim a managed identity")
        self.runtime_identity = (
            dict(runtime_identity) if runtime_identity is not None else None
        )
        self._session_alarm_attempted = threading.Event()
        self._session_alarm_lock = threading.Lock()
        self.manager = SessionManager(
            self.paths,
            on_fault=self._write_session_fault_alarm,
            journal_limit_bytes=journal_limit_bytes,
            admission_reserve_bytes=admission_reserve_bytes,
        )
        self.stop_requested = threading.Event()
        self._stop_error: str | None = None
        self.control = ControlServer(
            self.handle_request,
            host=control_host,
            port=control_port,
            after_response=self._after_response,
        )
        self._close_lock = threading.Lock()
        self._closed = False

    @property
    def control_host(self) -> str:
        return self.control.host

    @property
    def control_port(self) -> int:
        return self.control.port

    @property
    def stop_error(self) -> str | None:
        return self._stop_error

    def serve_forever(self) -> None:
        self.control.serve_forever()

    def shutdown(self, *, session_timeout: float = CLOSE_TIMEOUT_SECONDS) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self.control.close()
            self.manager.shutdown(timeout=session_timeout)

    def status_payload(self) -> dict[str, object]:
        payload = self.manager.status()
        payload.update(
            {
                "mode": "managed" if self.managed else "foreground",
                "product": PRODUCT_NAME,
                "protocol_version": CONTROL_PROTOCOL_VERSION,
                "service_pid": self.service_pid,
                "supervisor_pid": self.supervisor_pid,
                "runtime_identity": self.runtime_identity,
            }
        )
        last_alarm = latest_alarm_summary(self.paths)
        if last_alarm is not None:
            payload["last_alarm"] = last_alarm
        return payload

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if not isinstance(command, str) or not command:
            return self._error(None, "command must be a non-empty string")

        try:
            if self.managed and command in {"register", "close", "stop"}:
                self._require_runtime_nonce(request)
            if command == "status":
                _require_fields(request, {"command", "runtime_nonce"})
                return self._success(command, self.status_payload())
            if command == "register":
                _require_fields(
                    request,
                    {"command", "runtime_nonce", "upstream_port", "operation_id"},
                )
                try:
                    registration = self.manager.register(
                        request.get("upstream_port"),
                        operation_id=request.get("operation_id"),
                    )
                except SessionAdmissionError as error:
                    return self._admission_error(command, error)
                payload = registration.as_dict()
                payload["state"] = self.manager.status()["state"]
                return self._success(command, payload)
            if command == "close":
                _require_fields(request, {"command", "runtime_nonce"})
                return self._success(command, self.manager.close())
            if command == "stop":
                _require_fields(request, {"command", "runtime_nonce"})
                return self._handle_stop(command)
            return self._error(command, f"unsupported command: {command}")
        except (SessionError, OSError, ValueError) as error:
            return self._error(command, str(error))

    def _require_runtime_nonce(self, request: Mapping[str, Any]) -> None:
        identity = self.runtime_identity
        expected = identity.get("runtime_nonce") if isinstance(identity, dict) else None
        if request.get("runtime_nonce") != expected:
            raise ValueError("runtime nonce differs from the managed TraceRelay instance")

    def _handle_stop(self, command: str) -> dict[str, Any]:
        try:
            payload = self.manager.close()
            if payload.get("state") == SessionState.FAULT.value:
                detail = self.manager.status().get(
                    "last_error", "session ended incomplete"
                )
                raise SessionError(f"session ended incomplete: {detail}")
        except (SessionError, OSError, ValueError) as error:
            self._stop_error = str(error)
            response = self._error(command, self._stop_error)
            response["stopping"] = True
            return response
        response = self._success(command, payload)
        response["stopping"] = True
        return response

    def _after_response(
        self, request: dict[str, Any], response: dict[str, Any]
    ) -> None:
        if request.get("command") == "stop" and response.get("stopping") is True:
            self.stop_requested.set()

    @property
    def session_alarm_attempted(self) -> bool:
        return self._session_alarm_attempted.is_set()

    def _write_session_fault_alarm(
        self,
        registration: SessionRegistration,
        error: BaseException,
    ) -> None:
        with self._session_alarm_lock:
            if self._session_alarm_attempted.is_set():
                return
            self._session_alarm_attempted.set()
            try:
                write_alarm(
                    self.paths,
                    source="service",
                    reason="session_fault",
                    service_pid=self.service_pid,
                    supervisor_pid=self.supervisor_pid,
                    session_id=registration.session_id,
                    error=error,
                )
            except BaseException as alarm_error:
                _write_stderr_error("alarm_write_failed", alarm_error)

    def _admission_error(
        self, command: str, error: SessionAdmissionError
    ) -> dict[str, Any]:
        public_alarm: dict[str, object] | None = None
        try:
            alarm = write_alarm(
                self.paths,
                source="service",
                reason="session_admission_failed",
                service_pid=self.service_pid,
                supervisor_pid=self.supervisor_pid,
                session_id=None,
                error=error,
            )
        except BaseException as alarm_error:
            _write_stderr_error("alarm_write_failed", alarm_error)
            self.manager.abort("alarm_write_failed")
        else:
            public_alarm = alarm.public_summary()
        response = self._error(command, str(error))
        if public_alarm is not None:
            response["last_alarm"] = public_alarm
        return response

    def _success(self, command: str, payload: dict[str, object]) -> dict[str, Any]:
        response: dict[str, Any] = {
            "ok": True,
            "command": command,
            "service_pid": self.service_pid,
            "supervisor_pid": self.supervisor_pid,
            "runtime_identity": self.runtime_identity,
        }
        response.update(payload)
        response.setdefault("state", self.manager.status()["state"])
        return response

    def _error(self, command: str | None, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "command": command,
            "state": self.manager.status()["state"],
            "service_pid": self.service_pid,
            "supervisor_pid": self.supervisor_pid,
            "runtime_identity": self.runtime_identity,
            "error": message,
        }


class _ServiceRuntimeFault(RuntimeError):
    def __init__(self, reason: str, error: BaseException) -> None:
        super().__init__(str(error))
        self.reason = reason
        self.error = error


def managed_service_main(
    connection: Connection,
    supervisor_pid: int,
    root: str,
    expectation: RuntimeExpectation,
    supervisor_identity: dict[str, object],
) -> None:
    """Multiprocessing target used only by the detached Supervisor."""

    try:
        exit_code = run_service(
            paths=RuntimePaths.from_root(Path(root)),
            connection=connection,
            supervisor_pid=supervisor_pid,
            expectation=expectation,
            supervisor_identity=supervisor_identity,
            announce=False,
        )
    finally:
        connection.close()
    raise SystemExit(exit_code)


def run_service(
    *,
    paths: RuntimePaths | None = None,
    connection: Connection | None = None,
    supervisor_pid: int | None = None,
    expectation: RuntimeExpectation | None = None,
    supervisor_identity: dict[str, object] | None = None,
    announce: bool = False,
) -> int:
    """Run a foreground or Supervisor-managed Service until stop or fault."""

    service: TraceRelayService | None = None
    control_thread: threading.Thread | None = None
    control_stopped = threading.Event()
    control_errors: list[BaseException] = []
    fatal_fault: _ServiceRuntimeFault | None = None
    try:
        runtime_identity: dict[str, object] | None = None
        if connection is not None:
            if expectation is None or supervisor_identity is None:
                raise ValueError("managed Service runtime expectation is unavailable")
            if supervisor_pid is None:
                raise ValueError("managed Service supervisor identity is unavailable")
            try:
                service_identity = capture_process_identity(
                    "service", os.getpid(), expectation
                )
                runtime_identity = build_managed_runtime_identity(
                    expectation,
                    supervisor_identity,
                    service_identity,
                )
            except (OSError, RuntimeError, ValueError) as error:
                raise ValueError(
                    f"managed Service runtime identity failed: {error}"
                ) from error
        service = TraceRelayService(
            paths=paths,
            supervisor_pid=supervisor_pid,
            managed=connection is not None,
            runtime_identity=runtime_identity,
        )
        if announce:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "mode": "foreground",
                        "state": SessionState.IDLE.value,
                        "control_host": service.control_host,
                        "control_port": service.control_port,
                        "service_pid": service.service_pid,
                        "runtime_identity": service.runtime_identity,
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )

        def serve_control() -> None:
            try:
                service.serve_forever()
            except BaseException as error:
                control_errors.append(error)
            finally:
                control_stopped.set()

        control_thread = threading.Thread(
            target=serve_control,
            name="TraceRelay-control",
            daemon=True,
        )
        control_thread.start()
        _service_runtime_loop(
            service=service,
            connection=connection,
            control_stopped=control_stopped,
            control_errors=control_errors,
        )
        return 0
    except KeyboardInterrupt:
        return 0
    except _ServiceRuntimeFault as error:
        fatal_fault = error
        if service is not None:
            status = service.manager.status()
            alarm_already_attempted = (
                service.session_alarm_attempted
                and error.reason in {"session_fault", "session_stop_failed"}
            )
            if not alarm_already_attempted:
                try:
                    write_alarm(
                        service.paths,
                        source="service",
                        reason=error.reason,
                        service_pid=service.service_pid,
                        supervisor_pid=service.supervisor_pid,
                        session_id=_session_id_from_status(status),
                        error=error.error,
                    )
                except BaseException as alarm_error:
                    _write_stderr_error("alarm_write_failed", alarm_error)
            service.manager.abort(error.reason)
        return 1
    except (OSError, ValueError) as error:
        _write_stderr_error("service_start_failed", error)
        return 1
    finally:
        if service is not None:
            service.shutdown(
                session_timeout=0.0
                if fatal_fault is not None
                else CLOSE_TIMEOUT_SECONDS
            )
        if control_thread is not None:
            control_thread.join(timeout=2.0)
        if (
            fatal_fault is not None
            and control_thread is not None
            and control_thread.is_alive()
        ):
            _write_stderr_error(
                "control_thread_did_not_stop",
                RuntimeError("control thread remained alive after fatal shutdown"),
            )


def _service_runtime_loop(
    *,
    service: TraceRelayService,
    connection: Connection | None,
    control_stopped: threading.Event,
    control_errors: list[BaseException],
) -> None:
    last_heartbeat = time.monotonic()
    stop_request_sent = False

    while True:
        if connection is not None:
            try:
                has_message = connection.poll(PROCESS_POLL_INTERVAL_SECONDS)
            except (OSError, BrokenPipeError) as error:
                raise _ServiceRuntimeFault("supervisor_pipe_failed", error) from error
            if has_message:
                try:
                    message = connection.recv()
                except (EOFError, OSError, BrokenPipeError) as error:
                    raise _ServiceRuntimeFault(
                        "supervisor_pipe_closed", error
                    ) from error
                message_type = _message_type(message)
                if message_type == "heartbeat":
                    _validate_heartbeat(message, service.supervisor_pid)
                    last_heartbeat = time.monotonic()
                    try:
                        connection.send(_heartbeat_status(service))
                    except (OSError, BrokenPipeError) as error:
                        raise _ServiceRuntimeFault(
                            "supervisor_pipe_failed", error
                        ) from error
                elif message_type == "stop_ack" and stop_request_sent:
                    return
                else:
                    raise _ServiceRuntimeFault(
                        "invalid_supervisor_message",
                        ValueError(f"unexpected supervisor message: {message_type}"),
                    )
        else:
            service.stop_requested.wait(PROCESS_POLL_INTERVAL_SECONDS)

        if service.stop_error is not None:
            raise _ServiceRuntimeFault(
                "session_stop_failed", SessionError(service.stop_error)
            )
        if service.manager.faulted.is_set():
            status = service.manager.status()
            raise _ServiceRuntimeFault(
                "session_fault",
                SessionError(str(status.get("last_error", "session failed"))),
            )
        if service.stop_requested.is_set():
            if connection is None:
                return
            if not stop_request_sent:
                try:
                    connection.send(
                        {
                            "type": "stop_request",
                            "service_pid": service.service_pid,
                            "session_id": _current_session_id(service.manager.status()),
                        }
                    )
                except (OSError, BrokenPipeError) as error:
                    raise _ServiceRuntimeFault(
                        "supervisor_pipe_failed", error
                    ) from error
                stop_request_sent = True

        if control_errors:
            raise _ServiceRuntimeFault("control_server_failed", control_errors[0])
        if control_stopped.is_set() and not service.stop_requested.is_set():
            raise _ServiceRuntimeFault(
                "control_server_stopped",
                RuntimeError("control server stopped unexpectedly"),
            )
        if (
            connection is not None
            and time.monotonic() - last_heartbeat > HEARTBEAT_TIMEOUT_SECONDS
        ):
            raise _ServiceRuntimeFault(
                "supervisor_heartbeat_timeout",
                TimeoutError(
                    f"no Supervisor heartbeat for {HEARTBEAT_TIMEOUT_SECONDS:g} seconds"
                ),
            )


def _heartbeat_status(service: TraceRelayService) -> dict[str, object]:
    status = service.manager.status()
    return {
        "type": "status",
        "service_pid": service.service_pid,
        "state": status["state"],
        "session_id": _current_session_id(status),
    }


def _validate_heartbeat(message: object, expected_pid: int | None) -> None:
    if not isinstance(message, dict):
        raise _ServiceRuntimeFault(
            "invalid_supervisor_message",
            ValueError("Supervisor heartbeat must be an object"),
        )
    if set(message) != {"type", "supervisor_pid", "sent_monotonic"}:
        raise _ServiceRuntimeFault(
            "invalid_supervisor_message",
            ValueError("Supervisor heartbeat fields are invalid"),
        )
    supervisor_pid = message.get("supervisor_pid")
    sent_monotonic = message.get("sent_monotonic")
    if (
        type(supervisor_pid) is not int
        or supervisor_pid <= 0
        or supervisor_pid != expected_pid
    ):
        raise _ServiceRuntimeFault(
            "invalid_supervisor_message",
            ValueError("Supervisor heartbeat PID is invalid"),
        )
    if isinstance(sent_monotonic, bool) or not isinstance(sent_monotonic, (int, float)):
        raise _ServiceRuntimeFault(
            "invalid_supervisor_message",
            ValueError("Supervisor heartbeat time is invalid"),
        )


def _message_type(message: object) -> str | None:
    if not isinstance(message, dict):
        return None
    value = message.get("type")
    return value if isinstance(value, str) else None


def _session_id_from_status(status: dict[str, object]) -> str | None:
    current = _current_session_id(status)
    if current is not None:
        return current
    previous = status.get("last_session_id")
    return previous if isinstance(previous, str) else None


def _current_session_id(status: dict[str, object]) -> str | None:
    current = status.get("session_id")
    return current if isinstance(current, str) else None


def _write_stderr_error(reason: str, error: BaseException) -> None:
    print(
        json.dumps(
            {"ok": False, "reason": reason, "error": str(error)},
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    return run_service(announce=True)


def _require_fields(request: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(request) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unexpected request field(s): {names}")


if __name__ == "__main__":
    raise SystemExit(main())
