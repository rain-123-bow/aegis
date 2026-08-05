from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit


CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 43_190
CONTROL_MESSAGE_LIMIT = 64 * 1024
VALID_STATES = {"IDLE", "WAITING", "CONNECTING", "RELAYING", "FAULT"}
ACTIVE_STATES = {"WAITING", "CONNECTING", "RELAYING"}
STATUS_TIMEOUT_SECONDS = 2.0
CLI_TIMEOUT_SECONDS = 15.0


class TraceRelayError(RuntimeError):
    pass


class ProcessLike(Protocol):
    returncode: int | None

    def poll(self) -> int | None: ...

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


CliRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]
StatusRequester = Callable[[], dict[str, object]]
PopenFactory = Callable[..., ProcessLike]


@dataclass(frozen=True, slots=True)
class TraceRelayRegistration:
    session_id: str
    proxy_host: str
    proxy_port: int
    upstream_port: int
    session_path: Path


@dataclass(frozen=True, slots=True)
class EvidenceProcessResult:
    completed: subprocess.CompletedProcess[str]
    registration: TraceRelayRegistration
    verification: dict[str, object]


def parse_loopback_proxy_port(proxy_url: str) -> int:
    parsed = urlsplit(proxy_url)
    if parsed.scheme.lower() != "http":
        raise ValueError("TraceRelay upstream proxy must use the http scheme")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("TraceRelay upstream proxy must be loopback-local")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("TraceRelay upstream proxy has an invalid port") from error
    if port is None or not 1 <= port <= 65_535:
        raise ValueError("TraceRelay upstream proxy must include a valid port")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("TraceRelay upstream proxy credentials are not supported")
    return port


def resolve_tracerelay_command(explicit: str | Path | None = None) -> str:
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.is_file():
            raise TraceRelayError(f"TraceRelay command is missing: {candidate}")
        return str(candidate)
    discovered = shutil.which("tracerelay.exe") or shutil.which("tracerelay")
    if discovered is None:
        raise TraceRelayError(
            "tracerelay.exe is not installed or is not available on PATH"
        )
    return discovered


class TraceRelayClient:
    def __init__(
        self,
        *,
        command: str | Path,
        cli_runner: CliRunner | None = None,
        status_requester: StatusRequester | None = None,
        popen_factory: PopenFactory | None = None,
        alarm_directory: str | Path | None = None,
        monitor_interval_seconds: float = 1.0,
    ) -> None:
        self.command = str(command)
        self._cli_runner = cli_runner or _run_cli
        self._status_requester = status_requester or _request_status
        self._popen_factory = popen_factory or subprocess.Popen
        self.alarm_directory = (
            Path(alarm_directory).resolve()
            if alarm_directory is not None
            else _default_alarm_directory()
        )
        if monitor_interval_seconds < 0:
            raise ValueError("monitor_interval_seconds must not be negative")
        self.monitor_interval_seconds = monitor_interval_seconds
        self._service_pid: int | None = None
        self._supervisor_pid: int | None = None
        self._alarm_baseline: set[str] = set()
        self.last_registration: TraceRelayRegistration | None = None
        self.last_verification: dict[str, object] | None = None

    def start(self) -> dict[str, object]:
        self._alarm_baseline = self._alarm_names()
        payload = self._invoke(["start"])
        self._validate_identity(payload, "start", pin_pids=True)
        self._assert_no_new_alarms()
        if payload["state"] != "IDLE":
            raise TraceRelayError(
                "TraceRelay is already occupied by another session: "
                f"state={payload['state']}"
            )
        return payload

    def run_process(
        self,
        command: Sequence[str],
        *,
        upstream_port: int,
        timeout_seconds: float,
        base_environment: Mapping[str, str] | None = None,
    ) -> EvidenceProcessResult:
        if self._service_pid is None or self._supervisor_pid is None:
            raise TraceRelayError("TraceRelay start must complete before registration")
        if not command:
            raise ValueError("process command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.last_registration = None
        self.last_verification = None
        self._require_idle()
        registration = self._register(upstream_port)
        self.last_registration = registration
        proxy_url = f"http://{registration.proxy_host}:{registration.proxy_port}"
        environment = dict(os.environ if base_environment is None else base_environment)
        environment.update(
            HTTP_PROXY=proxy_url,
            HTTPS_PROXY=proxy_url,
            http_proxy=proxy_url,
            https_proxy=proxy_url,
        )

        try:
            process = self._popen_factory(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                env=environment,
            )
        except OSError:
            self.last_verification = self._finish(registration)
            raise

        deadline = time.monotonic() + timeout_seconds
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(list(command), timeout_seconds)
                self._assert_healthy(registration)
                if self.monitor_interval_seconds:
                    time.sleep(self.monitor_interval_seconds)
        except subprocess.TimeoutExpired:
            _terminate(process)
            self.last_verification = self._finish(registration)
            raise
        except BaseException:
            _terminate(process)
            raise

        stdout, stderr = process.communicate()
        completed = subprocess.CompletedProcess(
            list(command),
            int(process.returncode if process.returncode is not None else -1),
            stdout,
            stderr,
        )
        verification = self._finish(registration)
        self.last_verification = verification
        observed = verification.get("observed_bytes")
        observed_total = (
            sum(value for value in observed.values() if isinstance(value, int))
            if isinstance(observed, dict)
            else 0
        )
        if completed.returncode == 0 and observed_total <= 0:
            raise TraceRelayError(
                "the successful child process produced no TraceRelay traffic evidence"
            )
        return EvidenceProcessResult(completed, registration, verification)

    def _require_idle(self) -> None:
        payload = self._status_requester()
        self._validate_identity(payload, "status")
        self._assert_no_new_alarms()
        if payload["state"] != "IDLE":
            raise TraceRelayError(
                f"TraceRelay must be IDLE before registration: state={payload['state']}"
            )

    def _register(self, upstream_port: int) -> TraceRelayRegistration:
        if isinstance(upstream_port, bool) or not isinstance(upstream_port, int):
            raise ValueError("upstream_port must be an integer")
        if not 1 <= upstream_port <= 65_535:
            raise ValueError("upstream_port must be between 1 and 65535")
        payload = self._invoke(["register", "--upstream-port", str(upstream_port)])
        self._validate_identity(payload, "register")
        if payload["state"] != "WAITING":
            raise TraceRelayError("TraceRelay register did not enter WAITING")
        self._assert_no_new_alarms()

        session_id = _string(payload, "session_id")
        proxy_host = _string(payload, "proxy_host")
        proxy_port = _port(payload, "proxy_port")
        returned_upstream = _port(payload, "upstream_port")
        upstream_host = _string(payload, "upstream_host")
        if proxy_host != CONTROL_HOST or upstream_host != CONTROL_HOST:
            raise TraceRelayError("TraceRelay returned a non-loopback endpoint")
        if returned_upstream != upstream_port:
            raise TraceRelayError("TraceRelay returned a different upstream port")
        return TraceRelayRegistration(
            session_id=session_id,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            upstream_port=returned_upstream,
            session_path=Path(_string(payload, "session_path")).resolve(),
        )

    def _assert_healthy(self, registration: TraceRelayRegistration) -> None:
        payload = self._status_requester()
        self._validate_identity(payload, "status")
        self._assert_no_new_alarms()
        if payload["state"] not in ACTIVE_STATES:
            raise TraceRelayError(
                "TraceRelay session stopped while the child process was running: "
                f"{payload['state']}"
            )
        if payload.get("session_id") != registration.session_id:
            raise TraceRelayError("TraceRelay active session identity changed")

    def _finish(self, registration: TraceRelayRegistration) -> dict[str, object]:
        payload = self._status_requester()
        self._validate_identity(payload, "status")
        self._assert_no_new_alarms()
        if payload["state"] in ACTIVE_STATES:
            closed = self._invoke(["close"])
            self._validate_identity(closed, "close")
            if closed.get("closed") is not True or closed.get("state") != "IDLE":
                raise TraceRelayError("TraceRelay did not close the active session")
        elif payload["state"] == "IDLE":
            if payload.get("last_session_id") != registration.session_id:
                raise TraceRelayError("TraceRelay completed a different session")
        else:
            raise TraceRelayError(
                f"TraceRelay cannot seal session from state={payload['state']}"
            )

        verification = self._invoke(
            ["verify", str(registration.session_path)], require_ok=False
        )
        if verification.get("status") != "VALID_COMPLETE":
            raise TraceRelayError(
                "TraceRelay evidence verification did not return VALID_COMPLETE"
            )
        self._assert_no_new_alarms()
        return verification

    def _validate_identity(
        self,
        payload: dict[str, object],
        command: str,
        *,
        pin_pids: bool = False,
    ) -> None:
        required: dict[str, object] = {"ok": True, "command": command}
        if command in {"start", "status"}:
            required.update(
                product="TraceRelay",
                protocol_version=1,
                mode="managed",
            )
        if any(payload.get(field) != value for field, value in required.items()):
            raise TraceRelayError("TraceRelay response identity mismatch")
        if payload.get("state") not in VALID_STATES:
            raise TraceRelayError("TraceRelay returned an invalid state")
        if payload.get("state") == "FAULT" or payload.get("last_error") is not None:
            raise TraceRelayError(
                f"TraceRelay entered FAULT: {payload.get('last_error', '')}"
            )
        service_pid = _positive_integer(payload, "service_pid")
        supervisor_pid = _positive_integer(payload, "supervisor_pid")
        if pin_pids:
            self._service_pid = service_pid
            self._supervisor_pid = supervisor_pid
        elif (service_pid, supervisor_pid) != (
            self._service_pid,
            self._supervisor_pid,
        ):
            raise TraceRelayError("TraceRelay process identity changed")

    def _invoke(
        self, arguments: list[str], *, require_ok: bool = True
    ) -> dict[str, object]:
        command = [self.command, *arguments]
        try:
            completed = self._cli_runner(command, CLI_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
            raise TraceRelayError(f"TraceRelay CLI failed: {error}") from error
        raw = completed.stdout.strip() or completed.stderr.strip()
        try:
            payload = json.loads(raw, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as error:
            raise TraceRelayError("TraceRelay CLI did not return valid JSON") from error
        if not isinstance(payload, dict):
            raise TraceRelayError("TraceRelay CLI response must be a JSON object")
        if completed.returncode != 0:
            raise TraceRelayError(
                f"TraceRelay {arguments[0]} failed: {payload.get('error', raw)}"
            )
        if require_ok and payload.get("ok") is not True:
            raise TraceRelayError(f"TraceRelay {arguments[0]} returned ok=false")
        return payload

    def _alarm_names(self) -> set[str]:
        try:
            return {path.name for path in self.alarm_directory.glob("*.json")}
        except OSError as error:
            raise TraceRelayError(f"cannot inspect TraceRelay alarms: {error}") from error

    def _assert_no_new_alarms(self) -> None:
        new_alarms = self._alarm_names() - self._alarm_baseline
        if new_alarms:
            raise TraceRelayError(
                "TraceRelay emitted a new alarm: " + ", ".join(sorted(new_alarms))
            )


def _run_cli(arguments: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        timeout=timeout,
    )


def _request_status() -> dict[str, object]:
    try:
        with socket.create_connection(
            (CONTROL_HOST, CONTROL_PORT), timeout=STATUS_TIMEOUT_SECONDS
        ) as connection:
            connection.settimeout(STATUS_TIMEOUT_SECONDS)
            connection.sendall(b'{"command":"status"}\n')
            raw = bytearray()
            while b"\n" not in raw:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > CONTROL_MESSAGE_LIMIT:
                    raise TraceRelayError("TraceRelay status response exceeds 64 KiB")
    except (OSError, TimeoutError) as error:
        raise TraceRelayError(f"TraceRelay status is unavailable: {error}") from error
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise TraceRelayError("TraceRelay status response is not one JSON line")
    try:
        payload = json.loads(
            raw[:-1].decode("utf-8", errors="strict"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise TraceRelayError("TraceRelay status response is invalid JSON") from error
    if not isinstance(payload, dict):
        raise TraceRelayError("TraceRelay status response must be an object")
    return payload


def _terminate(process: ProcessLike) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)


def _default_alarm_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).resolve() / "TraceRelay" / "alarms"
    return Path.home() / "AppData" / "Local" / "TraceRelay" / "alarms"


def _string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise TraceRelayError(f"TraceRelay returned an invalid {field}")
    return value


def _positive_integer(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TraceRelayError(f"TraceRelay returned an invalid {field}")
    return value


def _port(payload: Mapping[str, object], field: str) -> int:
    value = _positive_integer(payload, field)
    if value > 65_535:
        raise TraceRelayError(f"TraceRelay returned an invalid {field}")
    return value


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")
