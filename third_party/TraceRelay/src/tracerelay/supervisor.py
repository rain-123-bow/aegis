"""Detached Supervisor process and heartbeat owner for TraceRelay M2."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import time
from multiprocessing.connection import Connection

from .config import (
    CONTROL_PROTOCOL_VERSION,
    HEARTBEAT_TIMEOUT_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    PROCESS_POLL_INTERVAL_SECONDS,
    PRODUCT_NAME,
    RuntimePaths,
    write_alarm,
)
from .service import managed_service_main
from .runtime_identity import RuntimeExpectation, capture_process_identity
from .session import SessionState


class SupervisorLaunchError(RuntimeError):
    pass


class ServiceProcessExit(RuntimeError):
    pass


class ServiceHeartbeatTimeout(TimeoutError):
    pass


def launch_detached_supervisor(
    expectation: RuntimeExpectation,
    timeout: float = 5.0,
) -> None:
    """Use a short-lived launcher so the real Supervisor inherits no CLI pipes."""

    if os.name != "nt":
        raise SupervisorLaunchError("TraceRelay M2 only supports Windows")
    command = [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "tracerelay.supervisor",
        "--detach",
        *expectation.command_arguments(),
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SupervisorLaunchError(f"cannot launch Supervisor: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SupervisorLaunchError(detail or "Supervisor launcher failed")
    try:
        payload = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SupervisorLaunchError(
            "Supervisor launcher returned invalid JSON"
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("product") != PRODUCT_NAME
        or payload.get("protocol_version") != CONTROL_PROTOCOL_VERSION
        or payload.get("launched") is not True
    ):
        raise SupervisorLaunchError("Supervisor launcher response is invalid")


def run_supervisor(
    paths: RuntimePaths | None = None,
    *,
    expectation: RuntimeExpectation,
) -> int:
    """Launch one Service, exchange heartbeats, and persist exit alarms."""

    runtime_paths = paths or RuntimePaths.default()
    runtime_paths.ensure()
    supervisor_pid = os.getpid()
    try:
        supervisor_identity = capture_process_identity(
            "supervisor", supervisor_pid, expectation
        )
    except (OSError, RuntimeError, ValueError) as error:
        _write_supervisor_alarm(
            runtime_paths,
            reason="runtime_identity_failed",
            supervisor_pid=supervisor_pid,
            service_pid=None,
            session_id=None,
            error=error,
        )
        return 1
    context = multiprocessing.get_context("spawn")
    supervisor_connection, service_connection = context.Pipe(duplex=True)
    service_process = context.Process(
        target=managed_service_main,
        args=(
            service_connection,
            supervisor_pid,
            str(runtime_paths.root),
            expectation,
            supervisor_identity,
        ),
        name="TraceRelay-Service",
        daemon=False,
    )
    try:
        service_process.start()
    except BaseException as error:
        supervisor_connection.close()
        service_connection.close()
        _write_supervisor_alarm(
            runtime_paths,
            reason="service_start_failed",
            supervisor_pid=supervisor_pid,
            service_pid=None,
            session_id=None,
            error=error,
        )
        return 1
    service_connection.close()

    expected_stop = False
    stop_deadline: float | None = None
    last_session_id: str | None = None
    next_heartbeat = 0.0
    heartbeat_sent_at: float | None = None
    runtime_error: BaseException | None = None
    try:
        while True:
            now = time.monotonic()
            if expected_stop:
                if not service_process.is_alive():
                    service_process.join(timeout=1.0)
                    if service_process.exitcode == 0:
                        return 0
                    error = ServiceProcessExit(
                        f"Service process exited with code {service_process.exitcode}"
                    )
                    _write_supervisor_alarm(
                        runtime_paths,
                        reason="service_process_exited",
                        supervisor_pid=supervisor_pid,
                        service_pid=service_process.pid,
                        session_id=last_session_id,
                        error=error,
                    )
                    return 1
                if stop_deadline is not None and now >= stop_deadline:
                    error = TimeoutError(
                        "Service did not exit after stop acknowledgement"
                    )
                    _write_supervisor_alarm(
                        runtime_paths,
                        reason="service_stop_timeout",
                        supervisor_pid=supervisor_pid,
                        service_pid=service_process.pid,
                        session_id=last_session_id,
                        error=error,
                    )
                    _terminate_service_process(service_process)
                    return 1
                time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
                continue

            while supervisor_connection.poll(0.0):
                try:
                    message = supervisor_connection.recv()
                except EOFError:
                    break
                message_type = _message_type(message)
                if message_type == "status":
                    last_session_id = _validate_status_message(
                        message, service_process.pid
                    )
                    heartbeat_sent_at = None
                elif message_type == "stop_request":
                    last_session_id = _validate_stop_request(
                        message, service_process.pid
                    )
                    expected_stop = True
                    stop_deadline = (
                        time.monotonic() + HEARTBEAT_TIMEOUT_SECONDS
                    )
                    supervisor_connection.send(
                        {
                            "type": "stop_ack",
                            "supervisor_pid": supervisor_pid,
                        }
                    )
                    break
                else:
                    raise ValueError(f"unexpected Service message: {message_type}")

            if expected_stop:
                continue
            if not service_process.is_alive():
                service_process.join(timeout=1.0)
                exit_code = service_process.exitcode
                if expected_stop and exit_code == 0:
                    return 0
                error = ServiceProcessExit(
                    f"Service process exited with code {exit_code}"
                )
                _write_supervisor_alarm(
                    runtime_paths,
                    reason="service_process_exited",
                    supervisor_pid=supervisor_pid,
                    service_pid=service_process.pid,
                    session_id=last_session_id,
                    error=error,
                )
                return 1

            now = time.monotonic()
            if (
                heartbeat_sent_at is not None
                and now - heartbeat_sent_at > HEARTBEAT_TIMEOUT_SECONDS
            ):
                raise ServiceHeartbeatTimeout(
                    f"no Service heartbeat response for "
                    f"{HEARTBEAT_TIMEOUT_SECONDS:g} seconds"
                )
            if heartbeat_sent_at is None and now >= next_heartbeat:
                supervisor_connection.send(
                    {
                        "type": "heartbeat",
                        "supervisor_pid": supervisor_pid,
                        "sent_monotonic": now,
                    }
                )
                heartbeat_sent_at = now
                next_heartbeat = now + HEARTBEAT_INTERVAL_SECONDS
            time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
    except BaseException as error:
        service_process.join(timeout=0.5)
        if service_process.is_alive():
            runtime_error = error
            _write_supervisor_alarm(
                runtime_paths,
                reason=(
                    "service_heartbeat_timeout"
                    if isinstance(error, ServiceHeartbeatTimeout)
                    else "supervisor_runtime_failed"
                ),
                supervisor_pid=supervisor_pid,
                service_pid=service_process.pid,
                session_id=last_session_id,
                error=error,
            )
            if isinstance(error, ServiceHeartbeatTimeout):
                _terminate_service_process(service_process)
        else:
            _write_service_exit_alarm(
                runtime_paths,
                supervisor_pid=supervisor_pid,
                service_process=service_process,
                session_id=last_session_id,
            )
        return 1
    finally:
        supervisor_connection.close()
        if runtime_error is not None and service_process.is_alive():
            service_process.join(timeout=HEARTBEAT_TIMEOUT_SECONDS + 2.0)
            if service_process.is_alive():
                _terminate_service_process(service_process)


def _detach(expectation: RuntimeExpectation) -> int:
    if os.name != "nt":
        _write_stderr("detached Supervisor is only supported on Windows")
        return 1
    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    command = [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "tracerelay.supervisor",
        "--run",
        *expectation.command_arguments(),
    ]
    try:
        # Keep the Popen object alive until os._exit; only status reports the
        # real Supervisor PID because a venv redirector PID is not authoritative.
        _supervisor_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as error:
        _write_stderr(str(error))
        return 1
    print(
        json.dumps(
            {
                "product": PRODUCT_NAME,
                "protocol_version": CONTROL_PROTOCOL_VERSION,
                "launched": True,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    os._exit(0)


def _validate_status_message(message: object, expected_pid: int | None) -> str | None:
    if not isinstance(message, dict) or set(message) != {
        "type",
        "service_pid",
        "state",
        "session_id",
    }:
        raise ValueError("Service status message fields are invalid")
    if (
        type(message.get("service_pid")) is not int
        or message["service_pid"] != expected_pid
    ):
        raise ValueError("Service status PID is invalid")
    if message.get("state") not in {state.value for state in SessionState}:
        raise ValueError("Service status state is invalid")
    session_id = message.get("session_id")
    if session_id is not None and (not isinstance(session_id, str) or not session_id):
        raise ValueError("Service status session_id is invalid")
    return session_id


def _validate_stop_request(message: object, expected_pid: int | None) -> str | None:
    if not isinstance(message, dict) or set(message) != {
        "type",
        "service_pid",
        "session_id",
    }:
        raise ValueError("Service stop request fields are invalid")
    if (
        type(message.get("service_pid")) is not int
        or message["service_pid"] != expected_pid
    ):
        raise ValueError("Service stop request PID is invalid")
    session_id = message.get("session_id")
    if session_id is not None and (not isinstance(session_id, str) or not session_id):
        raise ValueError("Service stop session_id is invalid")
    return session_id


def _message_type(message: object) -> str | None:
    if not isinstance(message, dict):
        return None
    value = message.get("type")
    return value if isinstance(value, str) else None


def _write_supervisor_alarm(
    paths: RuntimePaths,
    *,
    reason: str,
    supervisor_pid: int,
    service_pid: int | None,
    session_id: str | None,
    error: BaseException,
) -> None:
    try:
        write_alarm(
            paths,
            source="supervisor",
            reason=reason,
            service_pid=service_pid,
            supervisor_pid=supervisor_pid,
            session_id=session_id,
            error=error,
        )
    except BaseException as alarm_error:
        _write_stderr(f"alarm_write_failed: {alarm_error}")


def _write_service_exit_alarm(
    paths: RuntimePaths,
    *,
    supervisor_pid: int,
    service_process: multiprocessing.Process,
    session_id: str | None,
) -> None:
    error = ServiceProcessExit(
        f"Service process exited with code {service_process.exitcode}"
    )
    _write_supervisor_alarm(
        paths,
        reason="service_process_exited",
        supervisor_pid=supervisor_pid,
        service_pid=service_process.pid,
        session_id=session_id,
        error=error,
    )


def _terminate_service_process(service_process: multiprocessing.Process) -> None:
    if not service_process.is_alive():
        service_process.join(timeout=0.0)
        return
    service_process.terminate()
    service_process.join(timeout=2.0)
    if service_process.is_alive():
        service_process.kill()
        service_process.join(timeout=2.0)


def _write_stderr(message: str) -> None:
    print(
        json.dumps(
            {"ok": False, "reason": "supervisor_failed", "error": message},
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _parse_arguments() -> tuple[str, RuntimeExpectation]:
    parser = argparse.ArgumentParser(prog="python -m tracerelay.supervisor")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--detach", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--runtime-nonce", required=True)
    parser.add_argument("--expected-sdk-manifest-sha256", required=True)
    parser.add_argument("--expected-python-sha256", required=True)
    arguments = parser.parse_args()
    expectation = RuntimeExpectation.create(
        runtime_nonce=arguments.runtime_nonce,
        sdk_manifest_sha256=arguments.expected_sdk_manifest_sha256,
        python_executable_sha256=arguments.expected_python_sha256,
    )
    return ("detach" if arguments.detach else "run"), expectation


def main() -> int:
    multiprocessing.freeze_support()
    try:
        mode, expectation = _parse_arguments()
    except (SystemExit, ValueError) as error:
        if isinstance(error, SystemExit):
            return int(error.code or 0)
        _write_stderr(str(error))
        return 2
    if mode == "detach":
        return _detach(expectation)
    return run_supervisor(expectation=expectation)


if __name__ == "__main__":
    raise SystemExit(main())
