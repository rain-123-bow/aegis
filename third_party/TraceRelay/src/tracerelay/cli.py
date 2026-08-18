"""Command-line client for the TraceRelay v1 runtime."""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import sys
import time
from collections.abc import Sequence
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .config import (
    CONTROL_PROTOCOL_VERSION,
    HEARTBEAT_TIMEOUT_SECONDS,
    PRODUCT_NAME,
    SUPERVISOR_START_TIMEOUT_SECONDS,
    RuntimePaths,
    latest_alarm_summary,
)
from .control import ControlClient, ControlProtocolError
from .runtime_identity import (
    RuntimeExpectation,
    matches_expectation,
)
from .session import SessionError, SessionState, resolve_registration_operation
from .supervisor import SupervisorLaunchError, launch_detached_supervisor
from .verify import INVALID, verify_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tracerelay")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser(
        "start", help="start the detached Supervisor and Service"
    )
    start.add_argument("--runtime-nonce", required=True)
    start.add_argument("--expected-sdk-manifest-sha256", required=True)
    start.add_argument("--expected-python-sha256", required=True)
    commands.add_parser("status", help="show process and session state")
    register = commands.add_parser("register", help="register one local upstream")
    register.add_argument("--runtime-nonce")
    register.add_argument("--upstream-port", required=True, type=int)
    register.add_argument("--operation-id")
    resolve_registration = commands.add_parser(
        "resolve-registration", help="resolve one durable registration operation"
    )
    resolve_registration.add_argument("--operation-id", required=True)
    close = commands.add_parser("close", help="close the waiting or active session")
    close.add_argument("--runtime-nonce")
    stop = commands.add_parser("stop", help="close the session and stop both processes")
    stop.add_argument("--runtime-nonce")
    verify = commands.add_parser(
        "verify", help="verify one session directory read-only"
    )
    verify.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "verify":
        result = verify_session(arguments.path)
        _write_json(result.as_dict())
        return 1 if result.status == INVALID else 0
    if arguments.command == "resolve-registration":
        return _resolve_registration(arguments.operation_id)
    if arguments.command == "start":
        try:
            expectation = RuntimeExpectation.create(
                runtime_nonce=arguments.runtime_nonce,
                sdk_manifest_sha256=arguments.expected_sdk_manifest_sha256,
                python_executable_sha256=arguments.expected_python_sha256,
            )
        except ValueError as error:
            return _write_start_error(str(error))
        return _start_runtime(expectation)

    request: dict[str, Any] = {"command": arguments.command}
    if (
        arguments.command in {"register", "close", "stop"}
        and arguments.runtime_nonce is not None
    ):
        request["runtime_nonce"] = arguments.runtime_nonce
    if arguments.command == "register":
        request["upstream_port"] = arguments.upstream_port
        if arguments.operation_id is not None:
            request["operation_id"] = arguments.operation_id
    try:
        response = ControlClient().request(request)
    except (ControlProtocolError, OSError, TimeoutError) as error:
        response = _unavailable_response(arguments.command, error)
        _write_json(response, stream=sys.stderr)
        return 1

    if arguments.command == "stop" and response.get("stopping") is True:
        try:
            process_ids = _runtime_process_ids(response)
        except ValueError as error:
            response.update(
                {
                    "ok": False,
                    "stopped": False,
                    "error": str(error),
                }
            )
        else:
            try:
                stopped = _wait_for_process_shutdown(
                    process_ids, HEARTBEAT_TIMEOUT_SECONDS
                )
            except OSError as error:
                response.update(
                    {
                        "ok": False,
                        "stopped": False,
                        "error": f"cannot observe TraceRelay processes: {error}",
                    }
                )
            else:
                if stopped:
                    response["stopped"] = True
                else:
                    response.update(
                        {
                            "ok": False,
                            "stopped": False,
                            "error": (
                                "TraceRelay processes did not stop before the timeout"
                            ),
                        }
                    )
    _write_json(response)
    return 0 if response.get("ok") is True else 1


def _resolve_registration(operation_id: str) -> int:
    try:
        registration = resolve_registration_operation(
            RuntimePaths.default(), operation_id
        )
    except (OSError, UnicodeError, ValueError, SessionError) as error:
        _write_json(
            {
                "command": "resolve-registration",
                "error": str(error),
                "ok": False,
            },
            stream=sys.stderr,
        )
        return 1
    response: dict[str, object] = {
        "command": "resolve-registration",
        "found": registration is not None,
        "ok": True,
    }
    if registration is not None:
        response.update(registration.as_dict())
    _write_json(response)
    return 0


def _start_runtime(expectation: RuntimeExpectation) -> int:
    probe = ControlClient(timeout=3.0)
    try:
        response = probe.request(
            {"command": "status", "runtime_nonce": expectation.runtime_nonce}
        )
    except OSError as error:
        if not _is_connection_refused(error):
            return _write_start_error(
                f"control port is occupied or unavailable: {error}"
            )
    except (ControlProtocolError, TimeoutError) as error:
        return _write_start_error(
            f"control port is occupied by a non-TraceRelay protocol: {error}"
        )
    else:
        if not _is_trace_relay_protocol(response):
            return _write_start_error(
                "control port is occupied by a non-TraceRelay protocol"
            )
        if not _is_trace_relay_status(response, expectation):
            return _write_start_error(
                "an existing TraceRelay runtime has a different or invalid identity"
            )
        response = dict(response)
        response.update(
            {
                "command": "start",
                "started": False,
                "already_running": True,
            }
        )
        _write_json(response)
        return 0

    try:
        launch_detached_supervisor(expectation)
    except SupervisorLaunchError as error:
        return _write_start_error(str(error))

    deadline = time.monotonic() + SUPERVISOR_START_TIMEOUT_SECONDS
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            response = ControlClient(timeout=0.5).request(
                {"command": "status", "runtime_nonce": expectation.runtime_nonce}
            )
        except (ControlProtocolError, OSError, TimeoutError) as error:
            last_error = error
            time.sleep(0.05)
            continue
        if not _is_trace_relay_status(response, expectation):
            return _write_start_error(
                "the started TraceRelay runtime has a different or invalid identity"
            )
        response = dict(response)
        response.update(
            {
                "command": "start",
                "started": True,
                "already_running": False,
            }
        )
        _write_json(response)
        return 0

    detail = f": {last_error}" if last_error is not None else ""
    return _write_start_error(f"TraceRelay did not become ready before timeout{detail}")


def _is_trace_relay_status(
    response: object,
    expectation: RuntimeExpectation,
) -> bool:
    if not isinstance(response, dict):
        return False
    mode = response.get("mode")
    supervisor_pid = response.get("supervisor_pid")
    runtime_identity = response.get("runtime_identity")
    processes = (
        runtime_identity.get("processes")
        if isinstance(runtime_identity, dict)
        else None
    )
    service_identity = (
        processes.get("service") if isinstance(processes, dict) else None
    )
    supervisor_identity = (
        processes.get("supervisor") if isinstance(processes, dict) else None
    )
    return (
        response.get("ok") is True
        and response.get("command") == "status"
        and response.get("product") == PRODUCT_NAME
        and response.get("protocol_version") == CONTROL_PROTOCOL_VERSION
        and matches_expectation(runtime_identity, expectation)
        and response.get("state") in {state.value for state in SessionState}
        and type(response.get("service_pid")) is int
        and response["service_pid"] > 0
        and mode == "managed"
        and type(supervisor_pid) is int
        and supervisor_pid > 0
        and isinstance(service_identity, dict)
        and service_identity.get("pid") == response["service_pid"]
        and isinstance(supervisor_identity, dict)
        and supervisor_identity.get("pid") == supervisor_pid
    )


def _is_trace_relay_protocol(response: object) -> bool:
    return (
        isinstance(response, dict)
        and response.get("command") == "status"
        and response.get("product") == PRODUCT_NAME
        and response.get("protocol_version") == CONTROL_PROTOCOL_VERSION
        and response.get("mode") == "managed"
    )


def _unavailable_response(command: str, error: BaseException) -> dict[str, Any]:
    state = (
        "NOT_RUNNING"
        if isinstance(error, OSError) and _is_connection_refused(error)
        else "UNAVAILABLE"
    )
    response: dict[str, Any] = {
        "ok": False,
        "command": command,
        "state": state,
        "error": str(error),
    }
    last_alarm = latest_alarm_summary(RuntimePaths.default())
    if last_alarm is not None:
        response["last_alarm"] = last_alarm
    return response


def _write_start_error(message: str) -> int:
    response: dict[str, Any] = {
        "ok": False,
        "command": "start",
        "state": "NOT_RUNNING",
        "error": message,
    }
    last_alarm = latest_alarm_summary(RuntimePaths.default())
    if last_alarm is not None:
        response["last_alarm"] = last_alarm
    _write_json(response, stream=sys.stderr)
    return 1


def _is_connection_refused(error: OSError) -> bool:
    return (
        isinstance(error, ConnectionRefusedError)
        or error.errno == errno.ECONNREFUSED
        or getattr(error, "winerror", None) == 10061
    )


def _runtime_process_ids(response: dict[str, Any]) -> tuple[int, ...]:
    process_ids: list[int] = []
    for field in ("service_pid", "supervisor_pid"):
        value = response.get(field)
        if value is None and field == "supervisor_pid":
            continue
        if type(value) is not int or value <= 0:
            raise ValueError(f"stop response contains an invalid {field}")
        process_ids.append(value)
    return tuple(process_ids)


def _wait_for_process_shutdown(process_ids: tuple[int, ...], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if not any(_process_is_running(process_id) for process_id in process_ids):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _process_is_running(process_id: int) -> bool:
    """Return whether a Windows process has not reached its signalled state."""

    if os.name != "nt":
        raise RuntimeError("TraceRelay process checks only support Windows")

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    wait_failed = 0xFFFFFFFF
    error_access_denied = 5
    error_invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = open_process(synchronize, False, process_id)
    if not handle:
        error_code = ctypes.get_last_error()
        if error_code == error_invalid_parameter:
            return False
        if error_code == error_access_denied:
            return True
        raise ctypes.WinError(error_code)
    try:
        wait_result = wait_for_single_object(handle, 0)
        if wait_result == wait_timeout:
            return True
        if wait_result == wait_object_0:
            return False
        if wait_result == wait_failed:
            raise ctypes.WinError(ctypes.get_last_error())
        raise OSError(f"unexpected process wait result: {wait_result}")
    finally:
        close_handle(handle)


def _write_json(value: dict[str, Any], *, stream: Any | None = None) -> None:
    destination = sys.stdout if stream is None else stream
    line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    binary = getattr(destination, "buffer", None)
    if binary is not None:
        binary.write(line.encode("utf-8"))
        binary.flush()
        return
    destination.write(line)
    destination.flush()
