from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
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
VERIFY_TIMEOUT_SECONDS = 1_800.0
PROXY_ENVIRONMENT_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)
BYPASS_PROXY_ENVIRONMENT_NAMES = ("NO_PROXY", "no_proxy")
REGISTRATION_OPERATION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


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
ProcessCreationTimeReader = Callable[[int], int]
ProcessTerminator = Callable[[int, int], bool]


@dataclass(frozen=True, slots=True)
class TraceRelayRegistration:
    session_id: str
    proxy_host: str
    proxy_port: int
    upstream_port: int
    session_path: Path
    operation_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceProcessResult:
    completed: subprocess.CompletedProcess[str]
    registration: TraceRelayRegistration
    verification: dict[str, object]


class ManagedEvidenceProcess:
    """Popen-compatible process with continuous TraceRelay health monitoring."""

    def __init__(
        self,
        *,
        client: "TraceRelayClient",
        process: ProcessLike,
        registration: TraceRelayRegistration,
    ) -> None:
        self._client = client
        self._process = process
        self.registration = registration
        self.stdin = getattr(process, "stdin", None)
        self.stdout = getattr(process, "stdout", None)
        self.stderr = getattr(process, "stderr", None)
        self.pid = getattr(process, "pid", None)
        if isinstance(self.pid, bool) or not isinstance(self.pid, int) or self.pid <= 0:
            raise TraceRelayError("managed process has no valid PID")
        self.creation_time_100ns = client._process_creation_time_reader(self.pid)
        if (
            isinstance(self.creation_time_100ns, bool)
            or not isinstance(self.creation_time_100ns, int)
            or self.creation_time_100ns <= 0
        ):
            raise TraceRelayError("managed process has no valid creation time")
        self._stop = threading.Event()
        self._failure_lock = threading.Lock()
        self._failure: BaseException | None = None
        self._finalize_lock = threading.Lock()
        self._verification: dict[str, object] | None = None
        self._monitor = threading.Thread(
            target=self._monitor_loop,
            name="tracerelay-managed-process-monitor",
            daemon=True,
        )
        self._monitor.start()

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    def poll(self) -> int | None:
        return self._process.poll()

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return self._process.communicate(timeout=timeout)

    def wait(self, timeout: float | None = None) -> int:
        waiter = getattr(self._process, "wait", None)
        if not callable(waiter):
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.poll() is None:
                if deadline is not None and time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired("managed process", timeout)
                time.sleep(0.01)
            return int(self.returncode if self.returncode is not None else -1)
        return int(waiter(timeout=timeout))

    def terminate(self) -> None:
        self._process.terminate()

    def kill(self) -> None:
        self._process.kill()

    def failure(self) -> BaseException | None:
        with self._failure_lock:
            return self._failure

    def finalize(self) -> dict[str, object]:
        with self._finalize_lock:
            if self._verification is not None:
                return dict(self._verification)
            if self.poll() is None:
                raise TraceRelayError(
                    "managed process must stop before evidence finalization"
                )
            self._stop.set()
            self._monitor.join(timeout=5)
            primary = self.failure()
            try:
                verification = self._client._finish(self.registration)
                self._client.last_verification = verification
                _require_complete_verification(verification)
            except BaseException as cleanup_error:
                if primary is not None:
                    primary.add_note(
                        f"TraceRelay evidence finalization also failed: {cleanup_error}"
                    )
                    raise primary
                raise
            self._verification = dict(verification)
            if primary is not None:
                raise primary
            return dict(verification)

    def _monitor_loop(self) -> None:
        interval = max(self._client.monitor_interval_seconds, 0.01)
        while not self._stop.wait(interval):
            if self.poll() is not None:
                return
            try:
                completed = self._client._assert_healthy(self.registration)
                if completed:
                    if self.poll() is not None:
                        return
                    raise TraceRelayError(
                        "TraceRelay session ended while the managed process was running"
                    )
            except BaseException as error:
                with self._failure_lock:
                    if self._failure is None:
                        self._failure = error
                _terminate_interactive_preserving_error(self._process, error)
                return


def parse_loopback_proxy_port(proxy_url: str) -> int:
    parsed = urlsplit(proxy_url)
    if parsed.scheme.lower() != "http":
        raise ValueError("TraceRelay upstream proxy must use the http scheme")
    if parsed.hostname != CONTROL_HOST:
        raise ValueError("TraceRelay upstream proxy must use 127.0.0.1")
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
        process_creation_time_reader: ProcessCreationTimeReader | None = None,
        process_terminator: ProcessTerminator | None = None,
        alarm_directory: str | Path | None = None,
        monitor_interval_seconds: float = 1.0,
        verification_timeout_seconds: float = VERIFY_TIMEOUT_SECONDS,
    ) -> None:
        self.command = str(command)
        self._cli_runner = cli_runner or _run_cli
        self._status_requester = status_requester or _request_status
        self._popen_factory = popen_factory or subprocess.Popen
        self._process_creation_time_reader = (
            process_creation_time_reader or _windows_process_creation_time_100ns
        )
        self._process_terminator = (
            process_terminator or _terminate_windows_process_by_identity
        )
        self.alarm_directory = (
            Path(alarm_directory).resolve()
            if alarm_directory is not None
            else _default_alarm_directory()
        )
        if monitor_interval_seconds < 0:
            raise ValueError("monitor_interval_seconds must not be negative")
        if verification_timeout_seconds <= 0:
            raise ValueError("verification_timeout_seconds must be positive")
        self.monitor_interval_seconds = monitor_interval_seconds
        self.verification_timeout_seconds = verification_timeout_seconds
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

    def recover_managed_session(
        self,
        registration: TraceRelayRegistration,
        *,
        process_pid: int,
        process_creation_time_100ns: int,
    ) -> dict[str, object]:
        """Stop and seal the exact managed session left by a crashed coordinator."""
        if (
            isinstance(process_pid, bool)
            or not isinstance(process_pid, int)
            or process_pid <= 0
        ):
            raise ValueError("process_pid must be a positive integer")
        if (
            isinstance(process_creation_time_100ns, bool)
            or not isinstance(process_creation_time_100ns, int)
            or process_creation_time_100ns <= 0
        ):
            raise ValueError("process_creation_time_100ns must be a positive integer")
        self._alarm_baseline = self._alarm_names()
        payload = self._invoke(["start"])
        self._validate_identity(payload, "start", pin_pids=True)
        self._assert_no_new_alarms()
        self._require_registration_status(payload, registration)
        self._process_terminator(process_pid, process_creation_time_100ns)
        verification = self._finish(registration)
        _require_complete_verification(verification)
        self.last_registration = registration
        self.last_verification = dict(verification)
        return dict(verification)

    def resolve_registration_operation(
        self, operation_id: str
    ) -> TraceRelayRegistration | None:
        """Resolve a registration result from durable TraceRelay metadata."""
        expected_operation_id = _validate_registration_operation_id(operation_id)
        payload = self._invoke(
            ["resolve-registration", "--operation-id", expected_operation_id]
        )
        if payload.get("command") != "resolve-registration":
            raise TraceRelayError("TraceRelay registration resolution identity mismatch")
        found = payload.get("found")
        if found is False:
            return None
        if found is not True:
            raise TraceRelayError("TraceRelay registration resolution has no verdict")
        returned_operation_id = _string(payload, "operation_id")
        if returned_operation_id != expected_operation_id:
            raise TraceRelayError("TraceRelay resolved a different registration operation")
        proxy_host = _string(payload, "proxy_host")
        upstream_host = _string(payload, "upstream_host")
        if proxy_host != CONTROL_HOST or upstream_host != CONTROL_HOST:
            raise TraceRelayError("TraceRelay resolved a non-loopback endpoint")
        return TraceRelayRegistration(
            session_id=_string(payload, "session_id"),
            proxy_host=proxy_host,
            proxy_port=_port(payload, "proxy_port"),
            upstream_port=_port(payload, "upstream_port"),
            session_path=Path(_string(payload, "session_path")).resolve(),
            operation_id=returned_operation_id,
        )

    def recover_uncheckpointed_registration(
        self, registration: TraceRelayRegistration
    ) -> dict[str, object]:
        """Seal and verify a resolved session without trusting a child PID."""
        if registration.operation_id is None:
            raise ValueError("registration operation identity is required")
        _validate_registration_operation_id(registration.operation_id)
        self._alarm_baseline = self._alarm_names()
        try:
            payload = self._status_requester()
            self._validate_identity(payload, "status", pin_pids=True)
            self._assert_no_new_alarms()
            state = payload.get("state")
            if state in ACTIVE_STATES:
                self._require_registration_status(payload, registration)
                verification = self._finish(registration)
            elif state == "IDLE":
                if payload.get("last_session_id") == registration.session_id:
                    self._require_registration_status(payload, registration)
                verification = self._verify_resolved_registration(registration)
            else:
                raise TraceRelayError(
                    f"TraceRelay cannot recover registration from state={state}"
                )
        except (OSError, TimeoutError, TraceRelayError):
            verification = self._verify_resolved_registration(registration)
        self.last_registration = registration
        self.last_verification = dict(verification)
        return dict(verification)

    def _verify_resolved_registration(
        self, registration: TraceRelayRegistration
    ) -> dict[str, object]:
        verification = self._invoke(
            ["verify", str(registration.session_path)],
            require_ok=False,
            allow_nonzero=True,
        )
        if verification.get("status") not in {
            "VALID_COMPLETE",
            "VALID_INCOMPLETE",
            "INVALID",
        }:
            raise TraceRelayError(
                "resolved TraceRelay registration did not produce valid evidence"
            )
        return verification

    def verify_session(self, session_path: str | Path) -> dict[str, object]:
        """Re-read a sealed journal instead of trusting cached RUN_STATE fields."""
        if self._service_pid is None or self._supervisor_pid is None:
            raise TraceRelayError("TraceRelay start must complete before verification")
        resolved_path = Path(session_path).resolve()
        verification = self._invoke(["verify", str(resolved_path)], require_ok=False)
        _require_complete_verification(verification)
        self._assert_no_new_alarms()
        return verification

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
        for name in BYPASS_PROXY_ENVIRONMENT_NAMES:
            environment.pop(name, None)
        for name in PROXY_ENVIRONMENT_NAMES:
            environment[name] = proxy_url
        managed_command = _windows_job_command(
            command,
            process_time_limit_seconds=timeout_seconds,
        )

        try:
            process = self._popen_factory(
                managed_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                env=environment,
            )
        except OSError as error:
            try:
                self.last_verification = self._finish(registration)
            except BaseException as cleanup_error:
                error.add_note(
                    f"TraceRelay evidence finalization also failed: {cleanup_error}"
                )
            raise

        deadline = time.monotonic() + timeout_seconds
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(list(command), timeout_seconds)
                self._assert_healthy(registration)
                if self.monitor_interval_seconds:
                    time.sleep(self.monitor_interval_seconds)
        except subprocess.TimeoutExpired as error:
            _terminate_preserving_error(process, error)
            try:
                self.last_verification = self._finish(registration)
            except BaseException as cleanup_error:
                error.add_note(
                    f"TraceRelay evidence finalization also failed: {cleanup_error}"
                )
            raise
        except BaseException as error:
            _terminate_preserving_error(process, error)
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

    def open_managed_process(
        self,
        command: Sequence[str],
        *,
        upstream_port: int,
        registration_operation_id: str | None = None,
        base_environment: Mapping[str, str] | None = None,
        **popen_options: object,
    ) -> ManagedEvidenceProcess:
        if self._service_pid is None or self._supervisor_pid is None:
            raise TraceRelayError("TraceRelay start must complete before registration")
        if not command:
            raise ValueError("process command must not be empty")
        caller_environment = popen_options.pop("env", None)
        if base_environment is not None and caller_environment is not None:
            raise ValueError("base_environment and env cannot both be supplied")
        if caller_environment is not None and not isinstance(
            caller_environment, Mapping
        ):
            raise TypeError("env must be a mapping")

        self.last_registration = None
        self.last_verification = None
        self._require_idle()
        registration = self._register(
            upstream_port, operation_id=registration_operation_id
        )
        self.last_registration = registration
        environment_source = (
            base_environment
            if base_environment is not None
            else caller_environment
            if isinstance(caller_environment, Mapping)
            else os.environ
        )
        environment = _proxy_environment(registration, environment_source)
        options = dict(popen_options)
        options.setdefault("stdin", subprocess.PIPE)
        options.setdefault("stdout", subprocess.PIPE)
        options.setdefault("stderr", subprocess.PIPE)
        options.setdefault("text", True)
        options.setdefault("encoding", "utf-8")
        options.setdefault("errors", "strict")
        options["env"] = environment
        managed_command = _windows_job_command(command)
        try:
            process = self._popen_factory(managed_command, **options)
        except BaseException as error:
            try:
                self.last_verification = self._finish(registration)
            except BaseException as cleanup_error:
                error.add_note(
                    f"TraceRelay evidence finalization also failed: {cleanup_error}"
                )
            raise
        try:
            return ManagedEvidenceProcess(
                client=self,
                process=process,
                registration=registration,
            )
        except BaseException as error:
            _terminate_interactive_preserving_error(process, error)
            try:
                self.last_verification = self._finish(registration)
            except BaseException as cleanup_error:
                error.add_note(
                    f"TraceRelay evidence finalization also failed: {cleanup_error}"
                )
            raise

    def _require_idle(self) -> None:
        payload = self._status_requester()
        self._validate_identity(payload, "status")
        self._assert_no_new_alarms()
        if payload["state"] != "IDLE":
            raise TraceRelayError(
                f"TraceRelay must be IDLE before registration: state={payload['state']}"
            )

    def _register(
        self, upstream_port: int, *, operation_id: str | None = None
    ) -> TraceRelayRegistration:
        if isinstance(upstream_port, bool) or not isinstance(upstream_port, int):
            raise ValueError("upstream_port must be an integer")
        if not 1 <= upstream_port <= 65_535:
            raise ValueError("upstream_port must be between 1 and 65535")
        arguments = ["register", "--upstream-port", str(upstream_port)]
        if operation_id is not None:
            operation_id = _validate_registration_operation_id(operation_id)
            arguments.extend(["--operation-id", operation_id])
        payload = self._invoke(arguments)
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
        returned_operation_id = payload.get("operation_id")
        if operation_id is not None and returned_operation_id != operation_id:
            raise TraceRelayError("TraceRelay returned a different registration operation")
        if returned_operation_id is not None:
            returned_operation_id = _validate_registration_operation_id(
                returned_operation_id
            )
        return TraceRelayRegistration(
            session_id=session_id,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            upstream_port=returned_upstream,
            session_path=Path(_string(payload, "session_path")).resolve(),
            operation_id=returned_operation_id,
        )

    def _assert_healthy(self, registration: TraceRelayRegistration) -> bool:
        payload = self._status_requester()
        self._validate_identity(payload, "status")
        self._assert_no_new_alarms()
        if payload["state"] == "IDLE":
            if payload.get("last_session_id") != registration.session_id:
                raise TraceRelayError("TraceRelay completed a different session")
            return True
        if payload["state"] not in ACTIVE_STATES:
            raise TraceRelayError(
                "TraceRelay session stopped while the child process was running: "
                f"{payload['state']}"
            )
        if payload.get("session_id") != registration.session_id:
            raise TraceRelayError("TraceRelay active session identity changed")
        return False

    def _finish(self, registration: TraceRelayRegistration) -> dict[str, object]:
        payload = self._status_requester()
        self._validate_identity(payload, "status")
        self._assert_no_new_alarms()
        self._require_registration_status(payload, registration)
        if payload["state"] in ACTIVE_STATES:
            closed = self._invoke(["close"])
            self._validate_identity(closed, "close")
            if closed.get("state") != "IDLE":
                raise TraceRelayError("TraceRelay did not close the active session")
            payload = self._status_requester()
            self._validate_identity(payload, "status")
            self._assert_no_new_alarms()
            self._require_registration_status(payload, registration)
        if payload["state"] == "IDLE":
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

    def _require_registration_status(
        self,
        payload: Mapping[str, object],
        registration: TraceRelayRegistration,
    ) -> None:
        state = payload.get("state")
        if state in ACTIVE_STATES:
            session_id = payload.get("session_id")
            session_path = payload.get("session_path")
        elif state == "IDLE":
            session_id = payload.get("last_session_id")
            session_path = payload.get("last_session_path")
        else:
            raise TraceRelayError(
                f"TraceRelay cannot identify session from state={state}"
            )
        if session_id != registration.session_id:
            raise TraceRelayError("TraceRelay status identifies a different session")
        if not isinstance(session_path, str) or not session_path:
            raise TraceRelayError("TraceRelay status has no session path")
        if Path(session_path).resolve() != registration.session_path.resolve():
            raise TraceRelayError(
                "TraceRelay status identifies a different session path"
            )

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
        self,
        arguments: list[str],
        *,
        require_ok: bool = True,
        allow_nonzero: bool = False,
    ) -> dict[str, object]:
        command = [self.command, *arguments]
        try:
            timeout = (
                self.verification_timeout_seconds
                if arguments[0] == "verify"
                else CLI_TIMEOUT_SECONDS
            )
            completed = self._cli_runner(command, timeout)
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
            raise TraceRelayError(f"TraceRelay CLI failed: {error}") from error
        raw = completed.stdout.strip() or completed.stderr.strip()
        try:
            payload = json.loads(raw, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as error:
            raise TraceRelayError("TraceRelay CLI did not return valid JSON") from error
        if not isinstance(payload, dict):
            raise TraceRelayError("TraceRelay CLI response must be a JSON object")
        if completed.returncode != 0 and not allow_nonzero:
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
            raise TraceRelayError(
                f"cannot inspect TraceRelay alarms: {error}"
            ) from error

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


def _terminate_preserving_error(process: ProcessLike, primary: BaseException) -> None:
    try:
        _terminate(process)
    except BaseException as cleanup_error:
        primary.add_note(f"managed child termination also failed: {cleanup_error}")


def _terminate_interactive_preserving_error(
    process: ProcessLike, primary: BaseException
) -> None:
    try:
        if process.poll() is not None:
            return
        process.terminate()
        waiter = getattr(process, "wait", None)
        if callable(waiter):
            try:
                waiter(timeout=5)
            except (subprocess.TimeoutExpired, TimeoutError):
                process.kill()
                waiter(timeout=5)
    except BaseException as cleanup_error:
        primary.add_note(f"interactive child termination also failed: {cleanup_error}")


def _proxy_environment(
    registration: TraceRelayRegistration,
    base_environment: Mapping[str, str],
) -> dict[str, str]:
    proxy_url = f"http://{registration.proxy_host}:{registration.proxy_port}"
    environment = dict(base_environment)
    for name in BYPASS_PROXY_ENVIRONMENT_NAMES:
        environment.pop(name, None)
    for name in PROXY_ENVIRONMENT_NAMES:
        environment[name] = proxy_url
    return environment


def _require_bidirectional_evidence(verification: Mapping[str, object]) -> None:
    observed = verification.get("observed_bytes")
    if not isinstance(observed, Mapping):
        raise TraceRelayError("TraceRelay verification has no observed byte counts")
    client_to_upstream = observed.get("client_to_upstream")
    upstream_to_client = observed.get("upstream_to_client")
    if (
        isinstance(client_to_upstream, bool)
        or not isinstance(client_to_upstream, int)
        or client_to_upstream <= 0
        or isinstance(upstream_to_client, bool)
        or not isinstance(upstream_to_client, int)
        or upstream_to_client <= 0
    ):
        raise TraceRelayError(
            "managed process produced no bidirectional TraceRelay traffic evidence"
        )


def _require_complete_verification(verification: Mapping[str, object]) -> str:
    if verification.get("status") != "VALID_COMPLETE":
        raise TraceRelayError(
            "TraceRelay evidence verification did not return VALID_COMPLETE"
        )
    final_hash = verification.get("final_hash")
    if (
        not isinstance(final_hash, str)
        or len(final_hash) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in final_hash)
    ):
        raise TraceRelayError("TraceRelay verification has an invalid final hash")
    _require_bidirectional_evidence(verification)
    return final_hash.lower()


def _windows_process_creation_time_100ns(process_pid: int) -> int:
    if sys.platform != "win32":
        raise TraceRelayError("managed process identity requires Windows")

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process_query_limited_information = 0x1000
    process = kernel32.OpenProcess(
        process_query_limited_information, False, process_pid
    )
    if not process:
        error = ctypes.get_last_error()
        raise TraceRelayError(
            f"cannot read managed process PID {process_pid}: Windows error {error}"
        )
    try:
        return _process_creation_time_from_handle(kernel32, process, process_pid)
    finally:
        kernel32.CloseHandle(process)


def _terminate_windows_process_by_identity(
    process_pid: int,
    expected_creation_time_100ns: int,
) -> bool:
    if sys.platform != "win32":
        raise TraceRelayError("managed process recovery requires Windows")

    import ctypes
    from ctypes import wintypes

    process_terminate = 0x0001
    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    error_invalid_parameter = 87

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process = kernel32.OpenProcess(
        process_terminate | process_query_limited_information | synchronize,
        False,
        process_pid,
    )
    if not process:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return False
        raise TraceRelayError(
            f"cannot open stale managed process PID {process_pid}: Windows error {error}"
        )
    try:
        actual_creation_time = _process_creation_time_from_handle(
            kernel32, process, process_pid
        )
        if actual_creation_time != expected_creation_time_100ns:
            return False
        wait_result = kernel32.WaitForSingleObject(process, 0)
        if wait_result == wait_object_0:
            return False
        if wait_result != wait_timeout:
            raise TraceRelayError(
                f"cannot inspect stale managed process PID {process_pid}"
            )
        if not kernel32.TerminateProcess(process, 1):
            error = ctypes.get_last_error()
            raise TraceRelayError(
                f"cannot terminate stale managed process PID {process_pid}: "
                f"Windows error {error}"
            )
        if kernel32.WaitForSingleObject(process, 5_000) != wait_object_0:
            raise TraceRelayError(
                f"stale managed process PID {process_pid} did not terminate"
            )
        return True
    finally:
        kernel32.CloseHandle(process)


def _process_creation_time_from_handle(
    kernel32: object,
    process: object,
    process_pid: int,
) -> int:
    import ctypes
    from ctypes import wintypes

    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    if not kernel32.GetProcessTimes(
        process,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        error = ctypes.get_last_error()
        raise TraceRelayError(
            f"cannot read creation time for PID {process_pid}: Windows error {error}"
        )
    return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)


def _windows_job_command(
    command: Sequence[str],
    *,
    process_time_limit_seconds: float = 7_200,
) -> list[str]:
    if os.name != "nt":
        raise TraceRelayError("Aegis managed Codex execution requires Windows")
    if not 0 < process_time_limit_seconds <= 7_200:
        raise ValueError("process_time_limit_seconds must be positive and at most 7200")
    runner = Path(__file__).resolve().with_name("windows_job_runner.py")
    if not runner.is_file():
        raise TraceRelayError(f"Windows Job runner is missing: {runner}")
    return [
        _base_python_executable(),
        "-I",
        "-S",
        str(runner),
        "--active-process-limit",
        "64",
        "--job-memory-limit-bytes",
        str(4 * 1024**3),
        "--process-time-limit-100ns",
        str(max(10_000_000, int(process_time_limit_seconds * 10_000_000))),
        "--",
        *map(str, command),
    ]


def _base_python_executable() -> str:
    candidate = getattr(sys, "_base_executable", None)
    if not isinstance(candidate, str) or not candidate:
        raise TraceRelayError("CPython did not expose a base interpreter path")
    path = Path(candidate)
    if not path.is_absolute():
        raise TraceRelayError("CPython base interpreter path is not absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise TraceRelayError(
            f"CPython base interpreter is unavailable: {path}"
        ) from error
    if not resolved.is_file():
        raise TraceRelayError(f"CPython base interpreter is not a file: {resolved}")
    return str(resolved)


def _default_alarm_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).resolve() / "TraceRelay" / "alarms"
    return Path.home() / "AppData" / "Local" / "TraceRelay" / "alarms"


def _validate_registration_operation_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or REGISTRATION_OPERATION_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            "registration operation ID must be 32 lowercase hexadecimal characters"
        )
    return value


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
