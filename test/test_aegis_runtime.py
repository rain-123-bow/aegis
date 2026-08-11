from __future__ import annotations

import hashlib
import json
import io
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aegis_runtime
import project_seal_store
import tracerelay_client


def relay_payload(command: str, state: str = "IDLE") -> dict[str, object]:
    return {
        "ok": True,
        "command": command,
        "state": state,
        "mode": "managed",
        "product": "TraceRelay",
        "protocol_version": 1,
        "service_pid": 101,
        "supervisor_pid": 202,
    }


class FakeProcess:
    def __init__(self, *, keep_running: bool = False) -> None:
        self.keep_running = keep_running
        self.poll_count = 0
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        self.poll_count += 1
        if self.keep_running or self.poll_count == 1:
            return None
        self.returncode = 0
        return 0

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self.returncode is None and not self.terminated and not self.killed:
            self.returncode = 0
        return "response", ""

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 1

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


class InteractiveFakeProcess(FakeProcess):
    def __init__(self, *, keep_running: bool = True) -> None:
        super().__init__(keep_running=keep_running)
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.pid = 303
        self.communicate_called = False

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        return super().poll()

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        del timeout
        self.communicate_called = True
        return "", ""


class TraceRelayClientTests(unittest.TestCase):
    def make_client(
        self,
        root: Path,
        *,
        status_payloads: Sequence[dict[str, object]],
        process: FakeProcess,
        close_payload: dict[str, object] | None = None,
        verification_timeout_seconds: float = 1_800,
    ) -> tuple[aegis_runtime.TraceRelayClient, list[list[str]], dict[str, Any]]:
        commands: list[list[str]] = []
        captured_popen: dict[str, Any] = {}
        statuses = iter(status_payloads)

        registration = {
            "ok": True,
            "command": "register",
            "state": "WAITING",
            "service_pid": 101,
            "supervisor_pid": 202,
            "session_id": "session-1",
            "proxy_host": "127.0.0.1",
            "proxy_port": 45000,
            "upstream_host": "127.0.0.1",
            "upstream_port": 7899,
            "session_path": str(root / "sessions" / "session-1"),
        }

        def cli_runner(
            arguments: list[str], timeout: float
        ) -> subprocess.CompletedProcess[str]:
            commands.append(arguments)
            operation = arguments[1]
            captured_popen.setdefault("cli_timeouts", []).append((operation, timeout))
            if operation == "start":
                payload = relay_payload("start")
            elif operation == "register":
                payload = registration
            elif operation == "verify":
                payload = {
                    "status": "VALID_COMPLETE",
                    "record_count": 3,
                    "observed_bytes": {"client_to_upstream": 1},
                    "sent_success_bytes": {"client_to_upstream": 1},
                    "sent_error_bytes": {},
                    "unknown_bytes": {},
                    "final_hash": "ab" * 32,
                }
            elif operation == "close":
                payload = close_payload or {
                    "ok": True,
                    "command": "close",
                    "state": "IDLE",
                    "service_pid": 101,
                    "supervisor_pid": 202,
                    "closed": True,
                }
            else:
                raise AssertionError(f"unexpected operation: {operation}")
            return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

        def popen_factory(command: list[str], **kwargs: Any) -> FakeProcess:
            captured_popen.update({"command": command, **kwargs})
            return process

        client = aegis_runtime.TraceRelayClient(
            command="C:/TraceRelay/tracerelay.exe",
            cli_runner=cli_runner,
            status_requester=lambda: next(statuses),
            popen_factory=popen_factory,
            process_creation_time_reader=lambda pid: pid * 10_000,
            alarm_directory=root / "alarms",
            monitor_interval_seconds=0,
            verification_timeout_seconds=verification_timeout_seconds,
        )
        return client, commands, captured_popen

    def test_process_is_started_behind_registered_proxy_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            idle = relay_payload("status")
            relaying = {
                **relay_payload("status", "RELAYING"),
                "session_id": "session-1",
                "session_path": str(root / "sessions" / "session-1"),
            }
            closed = {
                **relay_payload("status"),
                "last_session_id": "session-1",
                "last_session_path": str(root / "sessions" / "session-1"),
            }
            client, commands, captured = self.make_client(
                root,
                status_payloads=[idle, relaying, closed],
                process=FakeProcess(),
            )

            client.start()
            result = client.run_process(
                ["codex.exe", "exec"],
                upstream_port=7899,
                timeout_seconds=5,
                base_environment={
                    "PATH": "value",
                    "NO_PROXY": "*",
                    "no_proxy": "*",
                    "ALL_PROXY": "http://127.0.0.1:1",
                    "all_proxy": "http://127.0.0.1:2",
                },
            )

            self.assertEqual(result.completed.returncode, 0)
            self.assertEqual(result.verification["status"], "VALID_COMPLETE")
            self.assertEqual(captured["env"]["HTTPS_PROXY"], "http://127.0.0.1:45000")
            self.assertEqual(captured["env"]["HTTP_PROXY"], "http://127.0.0.1:45000")
            self.assertEqual(
                {
                    captured["env"][name]
                    for name in (
                        "HTTP_PROXY",
                        "HTTPS_PROXY",
                        "http_proxy",
                        "https_proxy",
                        "ALL_PROXY",
                        "all_proxy",
                    )
                },
                {"http://127.0.0.1:45000"},
            )
            self.assertNotIn("NO_PROXY", captured["env"])
            self.assertNotIn("no_proxy", captured["env"])
            self.assertEqual(captured["env"]["PATH"], "value")
            self.assertEqual(
                [Path(command[0]).name for command in commands],
                ["tracerelay.exe", "tracerelay.exe", "tracerelay.exe"],
            )
            self.assertIn(("verify", 1_800), captured["cli_timeouts"])

    def test_runtime_fault_terminates_the_child_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fault = {
                **relay_payload("status", "FAULT"),
                "session_id": "session-1",
                "last_error": "journal failed",
            }
            process = FakeProcess(keep_running=True)
            client, _commands, _captured = self.make_client(
                root,
                status_payloads=[relay_payload("status"), fault],
                process=process,
            )
            client.start()

            with self.assertRaisesRegex(aegis_runtime.TraceRelayError, "FAULT"):
                client.run_process(
                    ["codex.exe", "exec"],
                    upstream_port=7899,
                    timeout_seconds=5,
                    base_environment={},
                )

            self.assertTrue(process.terminated)

    def test_child_timeout_seals_available_evidence_before_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            closed = {
                **relay_payload("status"),
                "last_session_id": "session-1",
                "last_session_path": str(root / "sessions" / "session-1"),
            }
            process = FakeProcess(keep_running=True)
            client, _commands, _captured = self.make_client(
                root,
                status_payloads=[relay_payload("status"), closed],
                process=process,
            )
            client.start()

            with self.assertRaises(subprocess.TimeoutExpired):
                client.run_process(
                    ["codex.exe", "exec"],
                    upstream_port=7899,
                    timeout_seconds=1e-9,
                    base_environment={},
                )

            self.assertTrue(process.terminated)
            self.assertEqual(client.last_verification["status"], "VALID_COMPLETE")

    def test_natural_completion_between_status_and_close_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relaying = {
                **relay_payload("status", "RELAYING"),
                "session_id": "session-1",
                "session_path": str(root / "sessions" / "session-1"),
            }
            completed = {
                **relay_payload("status"),
                "last_session_id": "session-1",
                "last_session_path": str(root / "sessions" / "session-1"),
            }
            close_race = {
                "ok": True,
                "command": "close",
                "state": "IDLE",
                "service_pid": 101,
                "supervisor_pid": 202,
                "closed": False,
            }
            client, commands, _captured = self.make_client(
                root,
                status_payloads=[
                    relay_payload("status"),
                    relaying,
                    relaying,
                    completed,
                ],
                process=FakeProcess(),
                close_payload=close_race,
            )
            client.start()

            result = client.run_process(
                ["codex.exe", "exec"],
                upstream_port=7899,
                timeout_seconds=5,
                base_environment={},
            )

            self.assertEqual(result.verification["status"], "VALID_COMPLETE")
            self.assertEqual(
                [command[1] for command in commands],
                ["start", "register", "close", "verify"],
            )

    def test_alarm_created_during_start_is_not_absorbed_into_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alarms = root / "alarms"
            alarms.mkdir()
            (alarms / "old.json").write_text("{}", encoding="utf-8")

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                (alarms / "new.json").write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(relay_payload("start")), ""
                )

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=lambda: relay_payload("status"),
                alarm_directory=alarms,
            )

            with self.assertRaisesRegex(aegis_runtime.TraceRelayError, "new alarm"):
                client.start()

    def test_only_loopback_http_proxy_is_accepted_as_upstream(self) -> None:
        self.assertEqual(
            aegis_runtime.parse_loopback_proxy_port("http://127.0.0.1:7899"),
            7899,
        )
        with self.assertRaises(ValueError):
            aegis_runtime.parse_loopback_proxy_port("http://proxy.example:7899")
        with self.assertRaises(ValueError):
            aegis_runtime.parse_loopback_proxy_port("http://localhost:7899")
        with self.assertRaises(ValueError):
            aegis_runtime.parse_loopback_proxy_port("http://[::1]:7899")

    def test_managed_process_keeps_interactive_pipes_and_seals_on_finalize(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = InteractiveFakeProcess()
            state = {"value": "IDLE"}
            commands: list[list[str]] = []
            captured: dict[str, Any] = {}

            def status() -> dict[str, object]:
                if state["value"] == "IDLE":
                    return {
                        **relay_payload("status"),
                        "last_session_id": "session-managed",
                        "last_session_path": str(root / "sessions" / "session-managed"),
                    }
                return {
                    **relay_payload("status", state["value"]),
                    "session_id": "session-managed",
                    "session_path": str(root / "sessions" / "session-managed"),
                }

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                del timeout
                commands.append(arguments)
                operation = arguments[1]
                if operation == "start":
                    payload = relay_payload("start")
                elif operation == "register":
                    state["value"] = "WAITING"
                    payload = {
                        "ok": True,
                        "command": "register",
                        "state": "WAITING",
                        "service_pid": 101,
                        "supervisor_pid": 202,
                        "session_id": "session-managed",
                        "proxy_host": "127.0.0.1",
                        "proxy_port": 45000,
                        "upstream_host": "127.0.0.1",
                        "upstream_port": 7899,
                        "session_path": str(root / "sessions" / "session-managed"),
                    }
                elif operation == "close":
                    state["value"] = "IDLE"
                    payload = {
                        "ok": True,
                        "command": "close",
                        "state": "IDLE",
                        "service_pid": 101,
                        "supervisor_pid": 202,
                        "closed": True,
                    }
                elif operation == "verify":
                    payload = {
                        "status": "VALID_COMPLETE",
                        "observed_bytes": {
                            "client_to_upstream": 1,
                            "upstream_to_client": 1,
                        },
                        "final_hash": "ab" * 32,
                    }
                else:
                    raise AssertionError(operation)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload), ""
                )

            def popen_factory(
                command: list[str], **kwargs: Any
            ) -> InteractiveFakeProcess:
                captured.update(command=command, **kwargs)
                return process

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=status,
                popen_factory=popen_factory,
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
                monitor_interval_seconds=0.001,
            )
            client.start()
            managed = client.open_managed_process(
                ["codex.exe", "app-server"],
                upstream_port=7899,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertIs(managed.stdin, process.stdin)
            self.assertIs(managed.stdout, process.stdout)
            self.assertEqual(captured["env"]["HTTPS_PROXY"], "http://127.0.0.1:45000")
            managed.terminate()
            managed.wait(timeout=1)
            verification = managed.finalize()

            self.assertEqual(verification["status"], "VALID_COMPLETE")
            self.assertEqual(
                [command[1] for command in commands],
                ["start", "register", "close", "verify"],
            )

    def test_managed_process_monitor_terminates_child_on_relay_fault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = InteractiveFakeProcess()
            fault_enabled = {"value": False}
            registered = {"value": False}

            def status() -> dict[str, object]:
                if not registered["value"]:
                    return relay_payload("status")
                if fault_enabled["value"]:
                    return {
                        **relay_payload("status", "FAULT"),
                        "session_id": "session-managed",
                        "last_error": "journal failed",
                    }
                return {
                    **relay_payload("status", "WAITING"),
                    "session_id": "session-managed",
                }

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                del timeout
                operation = arguments[1]
                if operation == "start":
                    payload = relay_payload("start")
                elif operation == "register":
                    registered["value"] = True
                    payload = {
                        "ok": True,
                        "command": "register",
                        "state": "WAITING",
                        "service_pid": 101,
                        "supervisor_pid": 202,
                        "session_id": "session-managed",
                        "proxy_host": "127.0.0.1",
                        "proxy_port": 45000,
                        "upstream_host": "127.0.0.1",
                        "upstream_port": 7899,
                        "session_path": str(root / "sessions" / "session-managed"),
                    }
                else:
                    raise AssertionError(operation)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload), ""
                )

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=status,
                popen_factory=lambda *args, **kwargs: process,
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
                monitor_interval_seconds=0.001,
            )
            client.start()
            managed = client.open_managed_process(
                ["codex.exe", "app-server"], upstream_port=7899
            )
            fault_enabled["value"] = True
            deadline = time.monotonic() + 1
            while not process.terminated and time.monotonic() < deadline:
                time.sleep(0.005)

            self.assertTrue(process.terminated)
            self.assertFalse(process.communicate_called)
            self.assertIsInstance(managed.failure(), aegis_runtime.TraceRelayError)

    def test_invalid_managed_environment_is_rejected_before_registration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client, commands, _captured = self.make_client(
                root,
                status_payloads=[relay_payload("status")],
                process=FakeProcess(),
            )
            client.start()

            with self.assertRaisesRegex(TypeError, "env must be a mapping"):
                client.open_managed_process(
                    ["codex.exe", "app-server"],
                    upstream_port=7899,
                    env=object(),
                )

            self.assertEqual([command[1] for command in commands], ["start"])

    def test_crash_recovery_seals_saved_session_when_process_identity_is_gone(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_path = root / "sessions" / "session-recover"
            events: list[str] = []
            statuses = iter(
                [
                    {
                        **relay_payload("status", "RELAYING"),
                        "session_id": "session-recover",
                        "session_path": str(session_path),
                    },
                    {
                        **relay_payload("status"),
                        "last_session_id": "session-recover",
                        "last_session_path": str(session_path),
                    },
                ]
            )

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                del timeout
                operation = arguments[1]
                events.append(operation)
                if operation == "start":
                    payload = {
                        **relay_payload("start", "RELAYING"),
                        "session_id": "session-recover",
                        "session_path": str(session_path),
                    }
                elif operation == "close":
                    payload = {
                        **relay_payload("close"),
                        "closed": True,
                    }
                elif operation == "verify":
                    payload = {
                        "status": "VALID_COMPLETE",
                        "final_hash": "ab" * 32,
                        "observed_bytes": {
                            "client_to_upstream": 10,
                            "upstream_to_client": 20,
                        },
                    }
                else:
                    raise AssertionError(operation)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload), ""
                )

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=lambda: next(statuses),
                process_terminator=lambda pid, created: (
                    events.append(f"identity-missing:{pid}:{created}") or False
                ),
                alarm_directory=root / "alarms",
            )
            registration = aegis_runtime.TraceRelayRegistration(
                session_id="session-recover",
                proxy_host="127.0.0.1",
                proxy_port=45_000,
                upstream_port=7_899,
                session_path=session_path,
            )

            verification = client.recover_managed_session(
                registration,
                process_pid=3_030,
                process_creation_time_100ns=4_040,
            )

            self.assertEqual(verification["final_hash"], "ab" * 32)
            self.assertEqual(
                events,
                ["start", "identity-missing:3030:4040", "close", "verify"],
            )

    def test_crash_recovery_refuses_a_different_active_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            terminated: list[tuple[int, int]] = []

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                del timeout
                payload = {
                    **relay_payload("start", "RELAYING"),
                    "session_id": "other-session",
                    "session_path": str(root / "sessions" / "other-session"),
                }
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload), ""
                )

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=lambda: relay_payload("status"),
                process_terminator=lambda pid, created: (
                    terminated.append((pid, created)) or True
                ),
                alarm_directory=root / "alarms",
            )
            registration = aegis_runtime.TraceRelayRegistration(
                session_id="saved-session",
                proxy_host="127.0.0.1",
                proxy_port=45_000,
                upstream_port=7_899,
                session_path=root / "sessions" / "saved-session",
            )

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "different session"
            ):
                client.recover_managed_session(
                    registration,
                    process_pid=3_030,
                    process_creation_time_100ns=4_040,
                )

            self.assertEqual(terminated, [])

    @unittest.skipUnless(sys.platform == "win32", "Windows process identity test")
    def test_windows_process_termination_requires_matching_creation_time(self) -> None:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            creation_time = tracerelay_client._windows_process_creation_time_100ns(
                process.pid
            )
            self.assertFalse(
                tracerelay_client._terminate_windows_process_by_identity(
                    process.pid,
                    creation_time + 1,
                )
            )
            self.assertIsNone(process.poll())
            self.assertTrue(
                tracerelay_client._terminate_windows_process_by_identity(
                    process.pid,
                    creation_time,
                )
            )
            process.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


class FakeRelayClient:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> dict[str, object]:
        self.started = True
        return relay_payload("start")


class ExecutionTurnHarness:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.open_count = 0
        self.finalize_count = 0
        self.thread_count = 0
        self.turn_count = 0
        self.start_turn_count = 0
        self.recover_turn_count = 0
        self.verify_count = 0
        self.recovered_session_ids: list[str] = []
        self.recovered_process_pids: list[int] = []
        self.recovered_process_creation_times: list[int] = []
        self.resume_thread_ids: list[str] = []
        self.processes: list[ExecutionManagedProcess] = []
        self.app_servers: list[ExecutionAppServer] = []
        self.wait_errors: list[BaseException] = []
        self.start_turn_errors: list[BaseException] = []
        self.finalize_errors: list[BaseException] = []
        self.close_errors: list[BaseException] = []


class ExecutionManagedProcess:
    def __init__(
        self,
        harness: ExecutionTurnHarness,
        relay: ExecutionRelayClient,
        session_index: int,
    ) -> None:
        self.harness = harness
        self.relay = relay
        self.registration = aegis_runtime.TraceRelayRegistration(
            session_id=f"execution-session-{session_index}",
            proxy_host="127.0.0.1",
            proxy_port=45_000 + session_index,
            upstream_port=7899,
            session_path=harness.root
            / "sessions"
            / f"execution-session-{session_index}",
        )
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.pid = 1_000 + session_index
        self.creation_time_100ns = 10_000_000 + session_index
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def failure(self) -> BaseException | None:
        return None

    def finalize(self) -> dict[str, object]:
        self.harness.finalize_count += 1
        verification = {
            "status": "VALID_COMPLETE",
            "final_hash": f"{self.pid:064x}"[-64:],
            "observed_bytes": {
                "client_to_upstream": 10,
                "upstream_to_client": 20,
            },
        }
        self.relay.last_verification = verification
        if self.harness.finalize_errors:
            raise self.harness.finalize_errors.pop(0)
        return verification


class ExecutionRelayClient(FakeRelayClient):
    def __init__(self, harness: ExecutionTurnHarness) -> None:
        super().__init__()
        self.harness = harness
        self.last_registration: aegis_runtime.TraceRelayRegistration | None = None
        self.last_verification: dict[str, object] | None = None

    def open_managed_process(
        self, *args: object, **kwargs: object
    ) -> ExecutionManagedProcess:
        del args, kwargs
        self.harness.open_count += 1
        process = ExecutionManagedProcess(self.harness, self, self.harness.open_count)
        self.harness.processes.append(process)
        self.last_registration = process.registration
        self.last_verification = None
        return process

    def verify_session(self, session_path: str | Path) -> dict[str, object]:
        self.harness.verify_count += 1
        index = int(Path(session_path).name.rsplit("-", 1)[1])
        return {
            "status": "VALID_COMPLETE",
            "final_hash": f"{1_000 + index:064x}"[-64:],
            "observed_bytes": {
                "client_to_upstream": 10,
                "upstream_to_client": 20,
            },
        }

    def recover_managed_session(
        self,
        registration: aegis_runtime.TraceRelayRegistration,
        *,
        process_pid: int,
        process_creation_time_100ns: int,
    ) -> dict[str, object]:
        self.started = True
        self.harness.recovered_session_ids.append(registration.session_id)
        self.harness.recovered_process_pids.append(process_pid)
        self.harness.recovered_process_creation_times.append(
            process_creation_time_100ns
        )
        return self.verify_session(registration.session_path)


class ExecutionAppServer:
    def __init__(self, harness: ExecutionTurnHarness, **kwargs: Any) -> None:
        self.harness = harness
        self.process_factory = kwargs["process_factory"]
        self.process: ExecutionManagedProcess | None = None
        self.closed = False
        harness.app_servers.append(self)

    def start(self) -> None:
        self.process = self.process_factory(["codex", "app-server"])

    def close(self) -> None:
        self.closed = True
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=1)
        if self.harness.close_errors:
            raise self.harness.close_errors.pop(0)

    def start_thread(self, **kwargs: Any) -> SimpleNamespace:
        self.harness.thread_count += 1
        return SimpleNamespace(
            thread_id=f"execution-thread-{self.harness.thread_count}",
            model="gpt-5.6-sol",
            reasoning_effort="high",
        )

    def resume_thread(self, thread_id: str, **kwargs: Any) -> SimpleNamespace:
        del kwargs
        self.harness.resume_thread_ids.append(thread_id)
        return SimpleNamespace(
            thread_id=thread_id,
            model="gpt-5.6-sol",
            reasoning_effort="high",
        )

    def start_turn(self, thread_id: str, prompt: str, **kwargs: Any) -> SimpleNamespace:
        del prompt, kwargs
        self.harness.start_turn_count += 1
        if self.harness.start_turn_errors:
            raise self.harness.start_turn_errors.pop(0)
        self.harness.turn_count += 1
        return SimpleNamespace(
            thread_id=thread_id,
            turn_id=f"execution-turn-{self.harness.turn_count}",
            started_at=time.monotonic(),
        )

    def wait_turn(
        self, turn: SimpleNamespace, *, timeout_seconds: float | None = None
    ) -> SimpleNamespace:
        del timeout_seconds
        if self.harness.wait_errors:
            raise self.harness.wait_errors.pop(0)
        return self._result(turn.thread_id, turn.turn_id)

    def recover_turn(self, thread_id: str, turn_id: str) -> SimpleNamespace:
        self.harness.recover_turn_count += 1
        return self._result(thread_id, turn_id)

    def _result(self, thread_id: str, turn_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            thread_id=thread_id,
            turn_id=turn_id,
            status="completed",
            final_message=json.dumps(
                {
                    "artifact_path": str(self.harness.root / "artifacts"),
                    "reasoning_ledger_context_pack": str(
                        self.harness.root / "artifacts" / "context.json"
                    ),
                    "status": True,
                }
            ),
        )


class FailingRelayClient(FakeRelayClient):
    def __init__(self, session_path: Path) -> None:
        super().__init__()
        self.last_registration = aegis_runtime.TraceRelayRegistration(
            session_id="failed-session",
            proxy_host="127.0.0.1",
            proxy_port=45000,
            upstream_port=7899,
            session_path=session_path,
        )

    def run_process(self, *args: object, **kwargs: object) -> object:
        raise aegis_runtime.TraceRelayError("journal failed")


class RuntimeCoordinatorTests(unittest.TestCase):
    def make_sealed_project(self, root: Path) -> Path:
        project = root / "project"
        source = project / "src" / "module.py"
        source.parent.mkdir(parents=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        project_seal_store.record_project_seal(
            project,
            git_head_before_record="a" * 40,
            project_id=bytes(range(16)),
            run_id=bytes(range(16, 32)),
        )
        return project

    def approve_planning_round(
        self,
        coordinator: aegis_runtime.RuntimeCoordinator,
        artifact_path: Path,
    ) -> dict[str, object]:
        artifact_path.mkdir(parents=True, exist_ok=True)
        context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        context_path.write_text("{}\n", encoding="utf-8")
        author = coordinator.prepare_planning_author(context_path)
        Path(str(author["plan_path"])).write_text("# Approved plan\n", encoding="utf-8")
        frozen = coordinator.freeze_planning_plan(str(author["round_id"]))
        review = coordinator.prepare_planning_review()
        Path(str(review["review_report_path"])).write_text(
            "# Approved review\n", encoding="utf-8"
        )
        accepted = coordinator.record_planning_review(
            str(review["round_id"]),
            {
                "reviewed_plan_sha256": frozen["plan_sha256"],
                "score": 95,
                "error_count": 0,
                "warning_count": 0,
                "verdict": "PASS",
            },
        )
        self.assertTrue(accepted)
        return frozen

    def attach_planning_evidence_process(
        self,
        coordinator: aegis_runtime.RuntimeCoordinator,
        root: Path,
        *,
        session_id: str,
        verification_status: str = "VALID_COMPLETE",
    ) -> None:
        registration = aegis_runtime.TraceRelayRegistration(
            session_id=session_id,
            proxy_host="127.0.0.1",
            proxy_port=45000,
            upstream_port=7899,
            session_path=root / "sessions" / session_id,
        )
        coordinator._planning_app_server = SimpleNamespace(  # type: ignore[assignment]
            close=lambda: None
        )
        coordinator._planning_process = SimpleNamespace(  # type: ignore[assignment]
            registration=registration,
            finalize=lambda: {
                "status": verification_status,
                "final_hash": "ef" * 32,
            },
        )
        coordinator._planning_stage_status = "active"

    def run_execution_node(
        self,
        coordinator: aegis_runtime.RuntimeCoordinator,
        node: str,
        role: str,
        state: dict[str, object],
        *,
        prompt: str | None = None,
    ) -> dict[str, object]:
        def operation(node_state: dict[str, object]) -> dict[str, object]:
            response = coordinator.run_execution_agent(
                role,
                prompt or f"{node} prompt",
                output_schema={"type": "object"},
                developer_instructions=f"persistent {role}",
                timeout_seconds=5,
            )
            return {**node_state, "response": response}

        return coordinator.execute_node(node, operation, state)

    def test_node_failure_is_saved_atomically_after_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            relay = FakeRelayClient()
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="20260805T000000.000000Z_" + "a" * 32,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
            )
            coordinator.preflight()

            def fail(_state: dict[str, object]) -> dict[str, object]:
                raise RuntimeError("node exploded")

            with self.assertRaisesRegex(RuntimeError, "node exploded"):
                coordinator.execute_node("A", fail, {"status": True})

            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertTrue(relay.started)
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["current_node"], "A")
            self.assertEqual(saved["graph_state"], {"status": True})
            self.assertEqual(saved["error"]["type"], "RuntimeError")

    def test_execution_roles_keep_threads_but_use_one_process_and_session_per_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            relay = ExecutionRelayClient(harness)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-c-d-c",
                upstream_port=7899,
                relay_client=relay,
                start_node="C",
            )
            coordinator.preflight()

            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                first_c = self.run_execution_node(
                    coordinator,
                    "C",
                    "TEST_EXECUTOR",
                    {"status": True, "cycle": 1},
                )
                first_d = self.run_execution_node(
                    coordinator,
                    "D",
                    "TEST_RESULT_REVIEWER",
                    {**first_c, "status": True},
                )
                self.run_execution_node(
                    coordinator,
                    "C",
                    "TEST_EXECUTOR",
                    {**first_d, "status": False, "cycle": 2},
                )

            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(harness.open_count, 3)
            self.assertEqual(harness.finalize_count, 3)
            self.assertEqual(len({process.pid for process in harness.processes}), 3)
            self.assertTrue(all(server.closed for server in harness.app_servers))
            self.assertEqual(harness.thread_count, 2)
            self.assertEqual(
                harness.resume_thread_ids,
                ["execution-thread-1"],
            )
            self.assertEqual(
                [turn["codex_thread_id"] for turn in saved["execution_turns"]],
                [
                    "execution-thread-1",
                    "execution-thread-2",
                    "execution-thread-1",
                ],
            )
            self.assertEqual(
                [turn["status"] for turn in saved["execution_turns"]],
                ["completed", "completed", "completed"],
            )
            self.assertEqual(
                [turn["evidence_session_ids"] for turn in saved["execution_turns"]],
                [
                    ["execution-session-1"],
                    ["execution-session-2"],
                    ["execution-session-3"],
                ],
            )
            self.assertTrue(
                all(
                    entry["verification_status"] == "VALID_COMPLETE"
                    and entry["application_verification_status"] == "VALID_COMPLETE"
                    for entry in saved["evidence_sessions"]
                )
            )
            self.assertEqual(
                {entry["process_pid"] for entry in saved["evidence_sessions"]},
                {1_001, 1_002, 1_003},
            )
            self.assertEqual(
                {
                    entry["process_creation_time_100ns"]
                    for entry in saved["evidence_sessions"]
                },
                {10_000_001, 10_000_002, 10_000_003},
            )

    def test_completed_execution_turn_replays_after_node_checkpoint_gap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-replay",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            state = {"status": True, "cycle": 1}

            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                first = self.run_execution_node(
                    coordinator, "C", "TEST_EXECUTOR", state
                )
                saved = aegis_runtime.load_run_state(
                    root / "artifacts", "execution-replay"
                )
                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id="execution-replay",
                    upstream_port=7899,
                    relay_client=ExecutionRelayClient(harness),
                    start_node="C",
                    prior_state=saved,
                )
                resumed.preflight()
                replayed = self.run_execution_node(resumed, "C", "TEST_EXECUTOR", state)

            self.assertEqual(replayed["response"], first["response"])
            self.assertEqual(harness.open_count, 1)
            self.assertEqual(harness.start_turn_count, 1)
            saved = json.loads(resumed.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["execution_attempts"]), 1)
            self.assertEqual(len(saved["execution_turns"]), 1)

    def test_start_node_d_creates_an_independent_reviewer_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-start-d",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="D",
            )
            coordinator.preflight()
            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                self.run_execution_node(
                    coordinator,
                    "D",
                    "TEST_RESULT_REVIEWER",
                    {"status": True},
                )

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "execution-start-d"
            )
            self.assertEqual(list(saved["execution_agents"]), ["TEST_RESULT_REVIEWER"])
            self.assertEqual(saved["execution_attempts"][0]["node"], "D")
            self.assertEqual(saved["execution_turns"][0]["status"], "completed")
            self.assertEqual(harness.open_count, 1)

    def test_tampered_execution_response_blocks_resume_before_relay_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-response-tamper",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                self.run_execution_node(
                    coordinator, "C", "TEST_EXECUTOR", {"status": True}
                )

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "execution-response-tamper"
            )
            response_path = Path(saved["execution_turns"][0]["raw_response_path"])
            response_path.write_text('{"status":false}', encoding="utf-8")
            resumed_relay = ExecutionRelayClient(harness)
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-response-tamper",
                upstream_port=7899,
                relay_client=resumed_relay,
                start_node="C",
                prior_state=saved,
            )

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "response SHA-256 mismatch"
            ):
                resumed.preflight()
            self.assertFalse(resumed_relay.started)

    def test_execution_turn_with_invalid_evidence_cannot_return_or_be_masked(
        self,
    ) -> None:
        for failure_source in ("finalize", "close"):
            with (
                self.subTest(failure_source=failure_source),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                harness = ExecutionTurnHarness(root)
                failure = RuntimeError(f"{failure_source} failed")
                if failure_source == "finalize":
                    harness.finalize_errors.append(failure)
                else:
                    harness.close_errors.append(failure)
                relay = ExecutionRelayClient(harness)
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id=f"execution-invalid-{failure_source}",
                    upstream_port=7899,
                    relay_client=relay,
                    start_node="C",
                )
                coordinator.preflight()
                with (
                    patch.object(
                        aegis_runtime,
                        "AppServerClient",
                        side_effect=lambda **kwargs: ExecutionAppServer(
                            harness, **kwargs
                        ),
                    ),
                    patch.object(
                        aegis_runtime,
                        "default_app_server_command",
                        return_value=(
                            "codex.cmd",
                            "app-server",
                            "--listen",
                            "stdio://",
                        ),
                    ),
                    patch.object(
                        aegis_runtime,
                        "read_codex_cli_version",
                        return_value="codex-cli 0.145.0",
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, f"{failure_source} failed"
                    ):
                        self.run_execution_node(
                            coordinator,
                            "C",
                            "TEST_EXECUTOR",
                            {"status": True},
                        )

                self.assertEqual(harness.open_count, 1)
                saved = aegis_runtime.load_run_state(
                    root / "artifacts", f"execution-invalid-{failure_source}"
                )
                self.assertEqual(
                    saved["evidence_sessions"][0]["verification_status"],
                    "VALID_COMPLETE",
                )
                self.assertEqual(
                    saved["evidence_sessions"][0]["application_verification_status"],
                    "INVALID",
                )
                resumed_relay = ExecutionRelayClient(harness)
                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id=f"execution-invalid-{failure_source}",
                    upstream_port=7899,
                    relay_client=resumed_relay,
                    start_node="C",
                    prior_state=saved,
                )
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError, "incomplete TraceRelay evidence"
                ):
                    resumed.preflight()
                self.assertFalse(resumed_relay.started)

    def test_execution_submission_intent_blocks_unknown_turn_resubmission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            harness.start_turn_errors.append(RuntimeError("turn/start reply was lost"))
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-submitting",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            state = {"status": True}

            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "reply was lost"):
                    self.run_execution_node(coordinator, "C", "TEST_EXECUTOR", state)
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError, "submission outcome is unknown"
                ):
                    self.run_execution_node(coordinator, "C", "TEST_EXECUTOR", state)

            self.assertEqual(harness.open_count, 1)
            self.assertEqual(harness.start_turn_count, 1)
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["execution_turns"][0]["status"], "submitting")

    def test_known_execution_turn_recovers_in_a_new_traced_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            harness.wait_errors.append(RuntimeError("App Server stream lost"))
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-known-turn",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            state = {"status": True}

            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "stream lost"):
                    self.run_execution_node(coordinator, "C", "TEST_EXECUTOR", state)
                saved = aegis_runtime.load_run_state(
                    root / "artifacts", "execution-known-turn"
                )
                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id="execution-known-turn",
                    upstream_port=7899,
                    relay_client=ExecutionRelayClient(harness),
                    start_node="C",
                    prior_state=saved,
                )
                resumed.preflight()
                recovered = self.run_execution_node(
                    resumed, "C", "TEST_EXECUTOR", state
                )

            self.assertIn('"status": true', str(recovered["response"]))
            self.assertEqual(harness.open_count, 2)
            self.assertEqual(harness.start_turn_count, 1)
            self.assertEqual(harness.recover_turn_count, 1)
            saved = json.loads(resumed.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["execution_turns"][0]["evidence_session_ids"],
                ["execution-session-1", "execution-session-2"],
            )
            self.assertEqual(saved["execution_turns"][0]["status"], "completed")

    def test_hard_crash_session_is_sealed_before_known_turn_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            harness.wait_errors.append(RuntimeError("coordinator disappeared"))
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-hard-crash",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            state = {"status": True}

            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "disappeared"):
                    self.run_execution_node(coordinator, "C", "TEST_EXECUTOR", state)

                saved = aegis_runtime.load_run_state(
                    root / "artifacts", "execution-hard-crash"
                )
                saved_evidence = saved["evidence_sessions"][0]
                saved_evidence.update(
                    verification_status="UNVERIFIED",
                    application_verification_status=None,
                    final_hash=None,
                )
                coordinator.run_state_path.write_text(
                    json.dumps(saved, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                resumed_relay = ExecutionRelayClient(harness)
                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id="execution-hard-crash",
                    upstream_port=7899,
                    relay_client=resumed_relay,
                    start_node="C",
                    prior_state=saved,
                )
                resumed.preflight()
                recovered = self.run_execution_node(
                    resumed, "C", "TEST_EXECUTOR", state
                )

            self.assertIn('"status": true', str(recovered["response"]))
            self.assertEqual(
                harness.recovered_session_ids,
                ["execution-session-1"],
            )
            self.assertEqual(harness.recovered_process_pids, [1_001])
            self.assertEqual(
                harness.recovered_process_creation_times,
                [10_000_001],
            )
            self.assertEqual(harness.start_turn_count, 1)
            self.assertEqual(harness.recover_turn_count, 1)
            final_state = aegis_runtime.load_run_state(
                root / "artifacts", "execution-hard-crash"
            )
            self.assertEqual(
                final_state["execution_turns"][0]["evidence_session_ids"],
                ["execution-session-1", "execution-session-2"],
            )
            self.assertTrue(
                all(
                    entry["verification_status"] == "VALID_COMPLETE"
                    and entry["application_verification_status"] == "VALID_COMPLETE"
                    for entry in final_state["evidence_sessions"]
                )
            )

    def test_persisted_execution_journal_is_reverified_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-journal-reverify",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                self.run_execution_node(
                    coordinator, "C", "TEST_EXECUTOR", {"status": True}
                )

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "execution-journal-reverify"
            )

            class MissingJournalRelay(ExecutionRelayClient):
                def verify_session(self, session_path: str | Path) -> dict[str, object]:
                    raise aegis_runtime.TraceRelayError(
                        f"journal is unavailable: {session_path}"
                    )

            resumed_relay = MissingJournalRelay(harness)
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-journal-reverify",
                upstream_port=7899,
                relay_client=resumed_relay,
                start_node="C",
                prior_state=saved,
            )
            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "journal is unavailable"
            ):
                resumed.preflight()
            self.assertTrue(resumed_relay.started)
            self.assertEqual(harness.open_count, 1)

    def test_persisted_execution_journal_final_hash_must_match_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-journal-hash",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="D",
            )
            coordinator.preflight()
            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: ExecutionAppServer(harness, **kwargs),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                self.run_execution_node(
                    coordinator,
                    "D",
                    "TEST_RESULT_REVIEWER",
                    {"status": True},
                )

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "execution-journal-hash"
            )

            class WrongHashRelay(ExecutionRelayClient):
                def verify_session(self, session_path: str | Path) -> dict[str, object]:
                    verification = super().verify_session(session_path)
                    verification["final_hash"] = "ff" * 32
                    return verification

            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-journal-hash",
                upstream_port=7899,
                relay_client=WrongHashRelay(harness),
                start_node="D",
                prior_state=saved,
            )
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "final hash mismatch"
            ):
                resumed.preflight()

            missing_identity = json.loads(json.dumps(saved))
            missing_identity["evidence_sessions"][0].pop("process_creation_time_100ns")
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "creation time"
            ):
                aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id="execution-journal-hash",
                    upstream_port=7899,
                    relay_client=ExecutionRelayClient(harness),
                    start_node="D",
                    prior_state=missing_identity,
                )

    def test_execution_thread_allocation_uncertainty_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-thread-allocating",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="D",
            )
            coordinator.preflight()
            state = {"status": True}

            class UncertainThreadAppServer(ExecutionAppServer):
                def start_thread(self, **kwargs: Any) -> SimpleNamespace:
                    del kwargs
                    raise RuntimeError("thread/start reply was lost")

            with (
                patch.object(
                    aegis_runtime,
                    "AppServerClient",
                    side_effect=lambda **kwargs: UncertainThreadAppServer(
                        harness, **kwargs
                    ),
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "thread/start reply was lost"
                ):
                    self.run_execution_node(
                        coordinator, "D", "TEST_RESULT_REVIEWER", state
                    )
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "thread allocation outcome is unknown",
                ):
                    self.run_execution_node(
                        coordinator, "D", "TEST_RESULT_REVIEWER", state
                    )

            self.assertEqual(harness.open_count, 1)
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["execution_agents"]["TEST_RESULT_REVIEWER"]["status"],
                "allocating",
            )

    def test_planning_roles_share_one_traced_app_server_and_persist_turn_receipts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            pending_observed: list[str] = []

            class ManagedProcess:
                def __init__(self) -> None:
                    self.registration = aegis_runtime.TraceRelayRegistration(
                        session_id="planning-session",
                        proxy_host="127.0.0.1",
                        proxy_port=45000,
                        upstream_port=7899,
                        session_path=root / "sessions" / "planning-session",
                    )
                    self.stdin = io.StringIO()
                    self.stdout = io.StringIO()
                    self.stderr = io.StringIO()
                    self.pid = 505
                    self.returncode: int | None = None
                    self.finalize_count = 0

                def poll(self) -> int | None:
                    return self.returncode

                def terminate(self) -> None:
                    self.returncode = 0

                def kill(self) -> None:
                    self.returncode = -9

                def wait(self, timeout: float | None = None) -> int:
                    del timeout
                    self.returncode = 0 if self.returncode is None else self.returncode
                    return self.returncode

                def failure(self) -> BaseException | None:
                    return None

                def finalize(self) -> dict[str, object]:
                    self.finalize_count += 1
                    return {
                        "status": "VALID_COMPLETE",
                        "final_hash": "cd" * 32,
                        "observed_bytes": {"client_to_upstream": 1},
                    }

            class PlanningRelay(FakeRelayClient):
                def __init__(self) -> None:
                    super().__init__()
                    self.open_count = 0
                    self.managed = ManagedProcess()

                def open_managed_process(
                    self, *args: object, **kwargs: object
                ) -> ManagedProcess:
                    del args, kwargs
                    self.open_count += 1
                    self.last_registration = self.managed.registration
                    return self.managed

            class FakeAppServer:
                def __init__(self, **kwargs: Any) -> None:
                    self.process_factory = kwargs["process_factory"]
                    self.process: ManagedProcess | None = None
                    self.thread_index = 0
                    self.turn_index = 0

                def start(self) -> None:
                    self.process = self.process_factory(["codex", "app-server"])

                def close(self) -> None:
                    assert self.process is not None
                    self.process.terminate()
                    self.process.wait(timeout=1)

                def start_thread(self, **kwargs: Any) -> SimpleNamespace:
                    del kwargs
                    self.thread_index += 1
                    return SimpleNamespace(
                        thread_id=f"planning-thread-{self.thread_index}",
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )

                def resume_thread(self, thread_id: str) -> SimpleNamespace:
                    return SimpleNamespace(
                        thread_id=thread_id,
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )

                def start_turn(
                    self, thread_id: str, prompt: str, **kwargs: Any
                ) -> SimpleNamespace:
                    del prompt, kwargs
                    self.turn_index += 1
                    return SimpleNamespace(
                        thread_id=thread_id,
                        turn_id=f"planning-turn-{self.turn_index}",
                        started_at=time.monotonic(),
                    )

                def wait_turn(self, turn: SimpleNamespace) -> SimpleNamespace:
                    pending_state = json.loads(
                        coordinator.run_state_path.read_text(encoding="utf-8")
                    )
                    pending_observed.append(
                        pending_state["planning_turns"][-1]["status"]
                    )
                    response = json.dumps(
                        {
                            "artifact_path": str(root / "artifacts"),
                            "reasoning_ledger_context_pack": str(root / "context.json"),
                            "status": True,
                        }
                    )
                    return SimpleNamespace(
                        thread_id=turn.thread_id,
                        turn_id=turn.turn_id,
                        status="completed",
                        final_message=response,
                    )

            relay = PlanningRelay()
            app_servers: list[FakeAppServer] = []

            def make_app_server(**kwargs: Any) -> FakeAppServer:
                app_server = FakeAppServer(**kwargs)
                app_servers.append(app_server)
                return app_server

            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-run",
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
            )
            coordinator.preflight()
            artifact_path = root / "artifacts"
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text("{}\n", encoding="utf-8")
            with (
                patch.object(
                    aegis_runtime, "AppServerClient", side_effect=make_app_server
                ),
                patch.object(
                    aegis_runtime,
                    "default_app_server_command",
                    return_value=("codex.cmd", "app-server", "--listen", "stdio://"),
                ),
                patch.object(
                    aegis_runtime,
                    "read_codex_cli_version",
                    return_value="codex-cli 0.145.0",
                ),
            ):
                author_control = coordinator.prepare_planning_author(context_path)
                author_response = coordinator.run_planning_agent(
                    "TEST_PLAN_AUTHOR",
                    "author prompt",
                    output_schema={"type": "object"},
                    developer_instructions="author",
                )
                Path(str(author_control["plan_path"])).write_text(
                    "# Plan\n", encoding="utf-8"
                )
                frozen = coordinator.freeze_planning_plan(
                    str(author_control["round_id"])
                )
                interim = json.loads(
                    coordinator.run_state_path.read_text(encoding="utf-8")
                )
                review_control = coordinator.prepare_planning_review()
                reviewer_response = coordinator.run_planning_agent(
                    "TEST_PLAN_REVIEWER",
                    "reviewer prompt",
                    output_schema={"type": "object"},
                    developer_instructions="reviewer",
                )
                Path(str(review_control["review_report_path"])).write_text(
                    "# Approved\n", encoding="utf-8"
                )
                self.assertTrue(
                    coordinator.record_planning_review(
                        str(review_control["round_id"]),
                        {
                            "reviewed_plan_sha256": frozen["plan_sha256"],
                            "score": 95,
                            "error_count": 0,
                            "warning_count": 0,
                            "verdict": "PASS",
                        },
                    )
                )
                coordinator.complete_planning_stage()

            self.assertEqual(json.loads(author_response)["status"], True)
            self.assertEqual(json.loads(reviewer_response)["status"], True)
            self.assertEqual(len(app_servers), 1)
            self.assertEqual(pending_observed, ["inProgress", "inProgress"])
            self.assertEqual(relay.open_count, 1)
            self.assertEqual(relay.managed.finalize_count, 1)
            self.assertEqual(
                interim["planning_agents"]["TEST_PLAN_AUTHOR"]["codex_thread_id"],
                "planning-thread-1",
            )
            self.assertEqual(
                interim["planning_turns"][0]["codex_turn_id"], "planning-turn-1"
            )
            self.assertEqual(interim["planning_turns"][0]["status"], "completed")
            self.assertTrue(
                Path(interim["planning_turns"][0]["raw_response_path"]).is_file()
            )
            self.assertEqual(interim["planning_stage_status"], "active")
            final_state = json.loads(
                coordinator.run_state_path.read_text(encoding="utf-8")
            )
            self.assertEqual(final_state["codex_cli_version"], "codex-cli 0.145.0")
            self.assertEqual(final_state["evidence_sessions"][0]["node"], "planning")
            self.assertEqual(
                final_state["evidence_sessions"][0]["application_verification_status"],
                "VALID_COMPLETE",
            )
            self.assertEqual(final_state["planning_stage_status"], "completed")

    def test_planning_stage_cannot_complete_without_an_approved_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-zero-round",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "no approved handoff"
            ):
                coordinator.complete_planning_stage()

            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["planning_rounds"], [])
            self.assertNotEqual(saved["planning_stage_status"], "completed")

    def test_planning_handoff_freezes_each_round_and_derives_the_review_result(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text('{"accepted":true}\n', encoding="utf-8")
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-handoff",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            first = coordinator.prepare_planning_author(context_path)
            self.assertEqual(first["round_id"], "round-0001")
            self.assertFalse(first["skip_turn"])
            first_plan = Path(str(first["plan_path"]))
            first_plan.write_text("# Plan v1\n", encoding="utf-8")
            frozen = coordinator.freeze_planning_plan("round-0001")
            self.assertEqual(
                frozen["plan_sha256"],
                hashlib.sha256(first_plan.read_bytes()).hexdigest(),
            )

            review = coordinator.prepare_planning_review()
            self.assertEqual(review["reviewed_plan_sha256"], frozen["plan_sha256"])
            first_report = Path(str(review["review_report_path"]))
            first_report.write_text(
                "# Review\n\nOne blocking issue.\n", encoding="utf-8"
            )
            accepted = coordinator.record_planning_review(
                "round-0001",
                {
                    "status": True,
                    "reviewed_plan_sha256": frozen["plan_sha256"],
                    "score": 94,
                    "error_count": 1,
                    "warning_count": 0,
                    "verdict": "PASS",
                },
            )
            self.assertFalse(accepted)

            second = coordinator.prepare_planning_author(context_path)
            self.assertEqual(second["round_id"], "round-0002")
            self.assertEqual(
                second["previous_review_report_path"], str(first_report.resolve())
            )
            second_plan = Path(str(second["plan_path"]))
            second_plan.write_text("# Plan v2\n", encoding="utf-8")
            second_frozen = coordinator.freeze_planning_plan("round-0002")
            second_review = coordinator.prepare_planning_review()
            second_report = Path(str(second_review["review_report_path"]))
            second_report.write_text("# Review\n\nApproved.\n", encoding="utf-8")
            accepted = coordinator.record_planning_review(
                "round-0002",
                {
                    "status": False,
                    "reviewed_plan_sha256": second_frozen["plan_sha256"],
                    "score": 95,
                    "error_count": 0,
                    "warning_count": 2,
                    "verdict": "PASS",
                },
            )

            self.assertTrue(accepted)
            approved_path = artifact_path / "APPROVED_TEST_PLAN.md"
            self.assertEqual(approved_path.read_bytes(), second_plan.read_bytes())
            handoff = json.loads(
                (artifact_path / "PLANNING_HANDOFF.json").read_text(encoding="utf-8")
            )
            self.assertEqual(handoff["round_id"], "round-0002")
            self.assertEqual(
                handoff["approved_plan_sha256"], second_frozen["plan_sha256"]
            )
            self.assertEqual(
                handoff["reviewed_plan_sha256"], second_frozen["plan_sha256"]
            )
            self.assertEqual(handoff["score"], 95)
            self.assertEqual(handoff["error_count"], 0)
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [item["status"] for item in saved["planning_rounds"]],
                ["rejected", "approved"],
            )

    def test_planning_handoff_rejects_a_plan_changed_after_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text("{}\n", encoding="utf-8")
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-tamper",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            author = coordinator.prepare_planning_author(context_path)
            plan_path = Path(str(author["plan_path"]))
            plan_path.write_text("# Frozen\n", encoding="utf-8")
            coordinator.freeze_planning_plan("round-0001")
            plan_path.write_text("# Changed\n", encoding="utf-8")

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "changed after it was frozen"
            ):
                coordinator.prepare_planning_review()

    def test_planning_review_rejects_changed_context_or_project_seal(self) -> None:
        for mutation in ("context", "project"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                artifact_path = root / "artifacts"
                artifact_path.mkdir()
                context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
                context_path.write_text("{}\n", encoding="utf-8")
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=f"planning-{mutation}-tamper",
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                )
                coordinator.preflight()
                author = coordinator.prepare_planning_author(context_path)
                Path(str(author["plan_path"])).write_text(
                    "# Frozen\n", encoding="utf-8"
                )
                coordinator.freeze_planning_plan("round-0001")
                if mutation == "context":
                    context_path.write_text('{"changed":true}\n', encoding="utf-8")
                    expected = "reasoning context changed"
                    expected_error = aegis_runtime.RuntimeStateError
                else:
                    (project / "src" / "module.py").write_text(
                        "VALUE = 2\n", encoding="utf-8"
                    )
                    expected = "project source does not match the recorded seal"
                    expected_error = project_seal_store.ProjectSealMismatchError

                with self.assertRaisesRegex(expected_error, expected):
                    coordinator.prepare_planning_review()

    def test_rejected_review_cannot_be_changed_before_the_next_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text("{}\n", encoding="utf-8")
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-rejected-tamper",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            author = coordinator.prepare_planning_author(context_path)
            Path(str(author["plan_path"])).write_text("# Plan\n", encoding="utf-8")
            frozen = coordinator.freeze_planning_plan("round-0001")
            review = coordinator.prepare_planning_review()
            report_path = Path(str(review["review_report_path"]))
            report_path.write_text("# Original rejection\n", encoding="utf-8")
            self.assertFalse(
                coordinator.record_planning_review(
                    "round-0001",
                    {
                        "reviewed_plan_sha256": frozen["plan_sha256"],
                        "score": 90,
                        "error_count": 1,
                        "warning_count": 0,
                        "verdict": "FAIL",
                    },
                )
            )
            report_path.write_text("# Rewritten rejection\n", encoding="utf-8")

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "review report changed after review",
            ):
                coordinator.prepare_planning_author(context_path)

    def test_round_allocation_recovers_after_directory_creation_before_state_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text("{}\n", encoding="utf-8")
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-allocation-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            original_write = first._write_state

            def crash_after_directory(
                status: str, error: BaseException | None = None
            ) -> None:
                if (
                    first._planning_rounds
                    and first._planning_rounds[-1]["status"] == "authoring"
                ):
                    raise RuntimeError("allocation checkpoint interrupted")
                original_write(status, error)

            with (
                patch.object(first, "_write_state", side_effect=crash_after_directory),
                self.assertRaisesRegex(
                    RuntimeError, "allocation checkpoint interrupted"
                ),
            ):
                first.prepare_planning_author(context_path)

            saved = aegis_runtime.load_run_state(
                artifact_path, "planning-allocation-recovery"
            )
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-allocation-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=saved,
            )
            resumed.preflight()

            recovered = resumed.prepare_planning_author(context_path)

            self.assertEqual(recovered["round_id"], "round-0001")
            self.assertFalse(recovered["skip_turn"])
            self.assertEqual(len(resumed._planning_rounds), 1)

    def test_completed_author_handoff_is_reused_without_a_new_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text("{}\n", encoding="utf-8")
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-author-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            author = coordinator.prepare_planning_author(context_path)
            Path(str(author["plan_path"])).write_text("# Plan\n", encoding="utf-8")
            coordinator.freeze_planning_plan("round-0001")

            recovered = coordinator.prepare_planning_author(context_path)

            self.assertEqual(recovered["round_id"], "round-0001")
            self.assertTrue(recovered["skip_turn"])
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["planning_rounds"]), 1)

    def test_resume_recovers_a_pending_planning_turn_without_resubmitting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            pending = {
                "job_id": "planning-recovery:planning",
                "node": "A",
                "role": "TEST_PLAN_AUTHOR",
                "client_message_id": "planning-recovery:TEST_PLAN_AUTHOR:1",
                "request_sha256": aegis_runtime._planning_request_sha256(
                    "must not be sent", {"type": "object"}
                ),
                "codex_thread_id": "thread-recover",
                "codex_turn_id": "turn-recover",
                "status": "inProgress",
                "raw_response_path": None,
                "raw_response_sha256": None,
            }
            coordinator._planning_agents = {
                "TEST_PLAN_AUTHOR": {
                    "codex_thread_id": "thread-recover",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                }
            }
            coordinator._planning_turns = [pending]
            coordinator._planning_ready_roles = {"TEST_PLAN_AUTHOR"}

            class RecoveringClient:
                def start_turn(self, *args: object, **kwargs: object) -> object:
                    raise AssertionError("pending turn was resubmitted")

                def recover_turn(self, thread_id: str, turn_id: str) -> SimpleNamespace:
                    self.recovered = (thread_id, turn_id)
                    return SimpleNamespace(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        status="completed",
                        final_message='{"status":true}',
                    )

            client = RecoveringClient()
            coordinator._planning_app_server = client  # type: ignore[assignment]
            response = coordinator.run_planning_agent(
                "TEST_PLAN_AUTHOR",
                "must not be sent",
                output_schema={"type": "object"},
                developer_instructions="author",
            )

            self.assertEqual(response, '{"status":true}')
            self.assertEqual(client.recovered, ("thread-recover", "turn-recover"))
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["planning_turns"][0]["status"], "completed")

    def test_resume_replays_a_completed_planning_turn_without_resubmitting(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-completed-replay",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            response = '{"status":true}'
            response_path = (
                coordinator.run_state_path.parent / "responses" / "saved.json"
            )
            response_path.parent.mkdir(parents=True)
            response_path.write_text(response, encoding="utf-8")
            coordinator._planning_agents = {
                "TEST_PLAN_AUTHOR": {
                    "codex_thread_id": "thread-replay",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                }
            }
            coordinator._planning_turns = [
                {
                    "job_id": "planning-completed-replay:round-0001:author",
                    "node": "A",
                    "role": "TEST_PLAN_AUTHOR",
                    "client_message_id": "message-replay",
                    "request_sha256": aegis_runtime._planning_request_sha256(
                        "must not be sent", {"type": "object"}
                    ),
                    "codex_thread_id": "thread-replay",
                    "codex_turn_id": "turn-replay",
                    "status": "completed",
                    "raw_response_path": str(response_path),
                    "raw_response_sha256": hashlib.sha256(
                        response.encode("utf-8")
                    ).hexdigest(),
                }
            ]
            coordinator._planning_ready_roles = {"TEST_PLAN_AUTHOR"}

            class ReplayOnlyClient:
                def start_turn(self, *args: object, **kwargs: object) -> object:
                    raise AssertionError("completed turn was resubmitted")

                def recover_turn(self, *args: object, **kwargs: object) -> object:
                    raise AssertionError("completed turn was recovered remotely")

            coordinator._planning_app_server = ReplayOnlyClient()  # type: ignore[assignment]

            replayed = coordinator.run_planning_agent(
                "TEST_PLAN_AUTHOR",
                "must not be sent",
                output_schema={"type": "object"},
                developer_instructions="author",
                job_id="planning-completed-replay:round-0001:author",
            )

            self.assertEqual(replayed, response)

    def test_submission_intent_prevents_resubmission_without_a_turn_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-submission-intent",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            coordinator._planning_agents = {
                "TEST_PLAN_AUTHOR": {
                    "codex_thread_id": "thread-intent",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                }
            }
            coordinator._planning_ready_roles = {"TEST_PLAN_AUTHOR"}

            class UncertainStartClient:
                def __init__(self) -> None:
                    self.start_count = 0

                def start_turn(self, *args: object, **kwargs: object) -> object:
                    del args, kwargs
                    self.start_count += 1
                    raise RuntimeError("turn/start reply was lost")

            client = UncertainStartClient()
            coordinator._planning_app_server = client  # type: ignore[assignment]
            coordinator._planning_stage_status = "active"

            def first_call() -> str:
                return coordinator.run_planning_agent(
                    "TEST_PLAN_AUTHOR",
                    "author prompt",
                    output_schema={"type": "object"},
                    developer_instructions="author",
                    job_id="planning-submission-intent:round-0001:author",
                )

            with self.assertRaisesRegex(RuntimeError, "reply was lost"):
                first_call()
            saved = aegis_runtime.load_run_state(
                root / "artifacts", "planning-submission-intent"
            )
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-submission-intent",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=saved,
            )
            resumed.preflight()
            resumed._planning_app_server = client  # type: ignore[assignment]
            resumed._planning_ready_roles = {"TEST_PLAN_AUTHOR"}

            def resumed_call() -> str:
                return resumed.run_planning_agent(
                    "TEST_PLAN_AUTHOR",
                    "author prompt",
                    output_schema={"type": "object"},
                    developer_instructions="author",
                    job_id="planning-submission-intent:round-0001:author",
                )

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "submission outcome is unknown"
            ):
                resumed_call()

            self.assertEqual(client.start_count, 1)
            persisted = json.loads(resumed.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["planning_turns"][0]["status"], "submitting")

    def test_interrupted_approval_publication_is_rebuilt_before_acceptance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            context_path.write_text("{}\n", encoding="utf-8")
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-publish-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            author = first.prepare_planning_author(context_path)
            Path(str(author["plan_path"])).write_text("# Plan\n", encoding="utf-8")
            frozen = first.freeze_planning_plan("round-0001")
            review = first.prepare_planning_review()
            Path(str(review["review_report_path"])).write_text(
                "# Approved\n", encoding="utf-8"
            )
            failure = RuntimeError("publication interrupted")
            with (
                patch.object(
                    first,
                    "_publish_approved_planning_handoff",
                    side_effect=failure,
                ),
                self.assertRaisesRegex(RuntimeError, "publication interrupted"),
            ):
                first.record_planning_review(
                    "round-0001",
                    {
                        "reviewed_plan_sha256": frozen["plan_sha256"],
                        "score": 95,
                        "error_count": 0,
                        "warning_count": 0,
                        "verdict": "PASS",
                    },
                )
            first.fail(failure)
            saved = aegis_runtime.load_run_state(
                artifact_path, "planning-publish-recovery"
            )
            self.assertEqual(saved["planning_rounds"][0]["status"], "publishing")

            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-publish-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=saved,
            )
            resumed.preflight()
            recovered = resumed.prepare_planning_review()

            self.assertTrue(recovered["skip_turn"])
            self.assertTrue(recovered["accepted"])
            self.assertTrue((artifact_path / "APPROVED_TEST_PLAN.md").is_file())
            self.assertTrue((artifact_path / "PLANNING_HANDOFF.json").is_file())
            final_state = json.loads(resumed.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(final_state["planning_rounds"][0]["status"], "approved")

            inconsistent = json.loads(json.dumps(final_state))
            inconsistent["planning_rounds"][0]["score"] = 10
            inconsistent["planning_rounds"][0]["error_count"] = 3
            inconsistent["planning_rounds"][0]["verdict"] = "FAIL"
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "approved planning round violates approval rules",
            ):
                aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id="planning-publish-recovery",
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                    prior_state=inconsistent,
                )

            (artifact_path / "APPROVED_TEST_PLAN.md").write_text(
                "# Changed\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "approved test plan"
            ):
                resumed.prepare_planning_review()

    def test_restored_closed_round_rejects_a_different_reviewed_plan_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-reviewed-hash-binding",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            self.approve_planning_round(first, artifact_path)
            approved_state = aegis_runtime.load_run_state(
                artifact_path, "planning-reviewed-hash-binding"
            )

            for status in ("rejected", "publishing", "approved"):
                with self.subTest(status=status):
                    tampered = json.loads(json.dumps(approved_state))
                    round_record = tampered["planning_rounds"][0]
                    round_record["status"] = status
                    round_record["reviewed_plan_sha256"] = "cd" * 32
                    if status == "rejected":
                        round_record.update(
                            score=90,
                            error_count=1,
                            verdict="FAIL",
                        )
                    with self.assertRaisesRegex(
                        aegis_runtime.RuntimeStateError,
                        "reviewed plan SHA-256 does not match frozen plan",
                    ):
                        aegis_runtime.RuntimeCoordinator(
                            project_root=project,
                            artifact_path=artifact_path,
                            run_id="planning-reviewed-hash-binding",
                            upstream_port=7899,
                            relay_client=FakeRelayClient(),
                            start_node="A",
                            prior_state=tampered,
                        )

    def test_incomplete_historical_planning_evidence_blocks_completion(self) -> None:
        for incomplete_status in ("UNVERIFIED", "INVALID"):
            with (
                self.subTest(status=incomplete_status),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                artifact_path = root / "artifacts"
                run_id = f"planning-evidence-{incomplete_status.lower()}"
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                )
                coordinator.preflight()
                self.approve_planning_round(coordinator, artifact_path)
                coordinator._evidence_sessions = [
                    {
                        "node": "planning",
                        "session_id": "older-session",
                        "session_path": str(root / "sessions" / "older-session"),
                        "verification_status": incomplete_status,
                        "final_hash": None,
                    }
                ]
                self.attach_planning_evidence_process(
                    coordinator, root, session_id="new-valid-session"
                )

                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "incomplete TraceRelay evidence",
                ):
                    coordinator.complete_planning_stage()

                saved = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(saved["planning_stage_status"], "active")
                self.assertEqual(
                    [
                        entry["verification_status"]
                        for entry in saved["evidence_sessions"]
                    ],
                    [incomplete_status, "VALID_COMPLETE"],
                )

    def test_zero_byte_application_failure_cannot_be_hidden_by_a_later_session(
        self,
    ) -> None:
        class ManagedRelay(FakeRelayClient):
            def __init__(self, observed_bytes: dict[str, int]) -> None:
                super().__init__()
                self.monitor_interval_seconds = 0
                self._process_creation_time_reader = lambda pid: pid * 10_000
                self.last_verification: dict[str, object] | None = None
                self.verification = {
                    "status": "VALID_COMPLETE",
                    "final_hash": "ab" * 32,
                    "observed_bytes": observed_bytes,
                }

            def _finish(
                self, registration: aegis_runtime.TraceRelayRegistration
            ) -> dict[str, object]:
                del registration
                return dict(self.verification)

            def _assert_healthy(
                self, registration: aegis_runtime.TraceRelayRegistration
            ) -> bool:
                del registration
                return False

        def attach_managed_process(
            coordinator: aegis_runtime.RuntimeCoordinator,
            relay: ManagedRelay,
            root: Path,
            session_id: str,
        ) -> None:
            registration = aegis_runtime.TraceRelayRegistration(
                session_id=session_id,
                proxy_host="127.0.0.1",
                proxy_port=45000,
                upstream_port=7899,
                session_path=root / "sessions" / session_id,
            )
            stopped_process = SimpleNamespace(
                pid=12_345,
                returncode=0,
                poll=lambda: 0,
                terminate=lambda: None,
                kill=lambda: None,
            )
            coordinator._planning_app_server = SimpleNamespace(  # type: ignore[assignment]
                close=lambda: None
            )
            coordinator._planning_process = aegis_runtime.ManagedEvidenceProcess(  # type: ignore[arg-type]
                client=relay,
                process=stopped_process,
                registration=registration,
            )
            coordinator._planning_stage_status = "active"

        for zero_direction in ("client_to_upstream", "upstream_to_client"):
            with (
                self.subTest(zero_direction=zero_direction),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                artifact_path = root / "artifacts"
                run_id = f"planning-zero-{zero_direction}"
                first_bytes = {
                    "client_to_upstream": 10,
                    "upstream_to_client": 10,
                }
                first_bytes[zero_direction] = 0
                first_relay = ManagedRelay(first_bytes)
                first = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=first_relay,  # type: ignore[arg-type]
                    start_node="A",
                )
                first.preflight()
                self.approve_planning_round(first, artifact_path)
                attach_managed_process(first, first_relay, root, "zero-byte-session")

                with self.assertRaisesRegex(
                    aegis_runtime.TraceRelayError,
                    "no bidirectional TraceRelay traffic evidence",
                ):
                    first.complete_planning_stage()

                interim = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(
                    interim["evidence_sessions"][0]["verification_status"],
                    "VALID_COMPLETE",
                )
                self.assertEqual(
                    interim["evidence_sessions"][0]["application_verification_status"],
                    "INVALID",
                )

                second_relay = ManagedRelay(
                    {
                        "client_to_upstream": 10,
                        "upstream_to_client": 10,
                    }
                )
                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=second_relay,  # type: ignore[arg-type]
                    start_node="A",
                    prior_state=interim,
                )
                resumed.preflight()
                attach_managed_process(
                    resumed, second_relay, root, "later-valid-session"
                )

                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "incomplete TraceRelay evidence",
                ):
                    resumed.complete_planning_stage()

                final_state = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(final_state["planning_stage_status"], "active")
                self.assertEqual(
                    [
                        entry["application_verification_status"]
                        for entry in final_state["evidence_sessions"]
                    ],
                    ["INVALID", "VALID_COMPLETE"],
                )

    def test_all_planning_evidence_sessions_allow_completion_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "planning-all-evidence-valid"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            self.approve_planning_round(coordinator, artifact_path)
            coordinator._evidence_sessions = [
                {
                    "node": "planning",
                    "session_id": "older-valid-session",
                    "session_path": str(root / "sessions" / "older-valid-session"),
                    "verification_status": "VALID_COMPLETE",
                    "application_verification_status": "VALID_COMPLETE",
                    "final_hash": "ab" * 32,
                }
            ]
            self.attach_planning_evidence_process(
                coordinator, root, session_id="new-valid-session"
            )

            coordinator.complete_planning_stage()

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["planning_stage_status"], "completed")
            self.assertTrue(
                all(
                    entry["verification_status"] == "VALID_COMPLETE"
                    for entry in saved["evidence_sessions"]
                    if entry["node"] == "planning"
                )
            )
            self.assertTrue(
                all(
                    entry["application_verification_status"] == "VALID_COMPLETE"
                    for entry in saved["evidence_sessions"]
                    if entry["node"] == "planning"
                )
            )
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=saved,
            )
            resumed.preflight()

    def test_relay_failure_saves_the_registered_session_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            relay = FailingRelayClient(root / "sessions" / "failed-session")
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="20260805T000000.000000Z_" + "b" * 32,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
            )
            coordinator.preflight()

            def invoke(_state: dict[str, object]) -> dict[str, object]:
                coordinator.run_codex_process(["codex.exe"], timeout_seconds=5)
                return {"status": True}

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "journal failed"
            ):
                coordinator.execute_node("A", invoke, {"status": True})

            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(
                saved["evidence_sessions"][0]["session_id"], "failed-session"
            )
            self.assertEqual(
                saved["evidence_sessions"][0]["verification_status"],
                "UNVERIFIED",
            )

    def test_new_run_refuses_existing_state_without_overwriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "run-collision"
            state_path = artifact_path / ".aegis" / "runs" / run_id / "RUN_STATE.json"
            state_path.parent.mkdir(parents=True)
            original = b'{"owner":"older-run"}\n'
            state_path.write_bytes(original)
            relay = FakeRelayClient()
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
            )

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "already reserved"
            ):
                coordinator.preflight()

            self.assertEqual(state_path.read_bytes(), original)
            self.assertFalse(relay.started)

    def test_new_run_refuses_existing_sqlite_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            run_id = "run-sqlite-collision"
            database = project / ".aegis" / "runtime" / "checkpoints.sqlite3"
            database.parent.mkdir(parents=True)
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE checkpoints(thread_id TEXT NOT NULL)")
                connection.execute(
                    "INSERT INTO checkpoints(thread_id) VALUES (?)", (run_id,)
                )
                connection.commit()
            finally:
                connection.close()
            relay = FakeRelayClient()
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id=run_id,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
            )

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "checkpoint thread already exists"
            ):
                coordinator.preflight()

            self.assertFalse(coordinator.run_state_path.exists())
            self.assertFalse(relay.started)

    def test_simultaneous_run_reservation_has_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "run-simultaneous"
            barrier = Barrier(2)

            def attempt() -> str:
                relay = FakeRelayClient()
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=relay,
                    start_node="A",
                )
                barrier.wait()
                try:
                    coordinator.preflight()
                except aegis_runtime.RuntimeStateError:
                    return "rejected"
                return "reserved"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _index: attempt(), range(2)))

            self.assertCountEqual(results, ["reserved", "rejected"])
            saved = json.loads(
                (
                    artifact_path / ".aegis" / "runs" / run_id / "RUN_STATE.json"
                ).read_text(encoding="utf-8")
            )
            self.assertRegex(saved["reservation_token"], r"^[0-9a-f]{32}$")

    def test_resume_requires_matching_reservation_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "run-resume-token"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            saved["reservation_token"] = "f" * 32
            relay = FakeRelayClient()
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
                prior_state=saved,
            )

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "reservation does not match"
            ):
                resumed.preflight()

            self.assertFalse(relay.started)

    def test_v1_and_v2_run_state_are_rejected_instead_of_guessing_c_d_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "legacy-planning-state"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            for schema in ("aegis.run_state.v1", "aegis.run_state.v2"):
                with self.subTest(schema=schema):
                    saved["schema"] = schema
                    first.run_state_path.write_text(
                        json.dumps(saved) + "\n", encoding="utf-8"
                    )

                    with self.assertRaisesRegex(
                        aegis_runtime.RuntimeStateError,
                        "predates C/D App Server transactions",
                    ):
                        aegis_runtime.load_run_state(artifact_path, run_id)


if __name__ == "__main__":
    unittest.main()
