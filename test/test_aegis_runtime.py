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
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aegis_runtime
import agent_registry
import project_seal_store
import tracerelay_client
from mutation_accountability import record_frozen_input_mutation_reason
from aegis_test_support import (
    initialize_test_git_repository,
    write_test_execution_request,
    write_test_execution_policy,
    write_test_reasoning_context_pack,
    write_test_runtime_scope_policy,
)


TEST_RUNTIME_NONCE = "11" * 16
TEST_SDK_MANIFEST_SHA256 = "22" * 32
TEST_PYTHON_SHA256 = "33" * 32
TEST_TRACERELAY_COMMAND = "C:/TraceRelay/tracerelay.exe"


def relay_payload(command: str, state: str = "IDLE") -> dict[str, object]:
    return {
        "ok": True,
        "command": command,
        "state": state,
        "mode": "managed",
        "product": "TraceRelay",
        "protocol_version": 2,
        "service_pid": 101,
        "supervisor_pid": 202,
        "runtime_identity": {
            "schema": "tracerelay.runtime_identity.v1",
            "runtime_nonce": TEST_RUNTIME_NONCE,
            "sdk_manifest_sha256": TEST_SDK_MANIFEST_SHA256,
            "python_executable_sha256": TEST_PYTHON_SHA256,
            "processes": {
                "supervisor": _relay_process_identity("supervisor", 202),
                "service": _relay_process_identity("service", 101),
            },
        },
    }


def _relay_process_identity(role: str, pid: int) -> dict[str, object]:
    return {
        "role": role,
        "pid": pid,
        "creation_time_100ns": pid * 10_000,
        "python_executable": TEST_TRACERELAY_COMMAND,
        "python_executable_sha256": TEST_PYTHON_SHA256,
        "sdk_manifest_sha256": TEST_SDK_MANIFEST_SHA256,
        "python_flags": {
            "isolated": True,
            "dont_write_bytecode": True,
            "safe_path": True,
        },
    }


def bind_test_runtime(client: aegis_runtime.TraceRelayClient) -> None:
    client.bind_runtime_expectation(
        runtime_nonce=TEST_RUNTIME_NONCE,
        sdk_manifest_sha256=TEST_SDK_MANIFEST_SHA256,
        python_executable_sha256=TEST_PYTHON_SHA256,
    )


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
            **relay_payload("register", "WAITING"),
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
                payload = dict(registration)
                if "--operation-id" in arguments:
                    payload["operation_id"] = arguments[
                        arguments.index("--operation-id") + 1
                    ]
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
                    **relay_payload("close"),
                    "closed": True,
                }
            else:
                raise AssertionError(f"unexpected operation: {operation}")
            return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

        def popen_factory(command: list[str], **kwargs: Any) -> FakeProcess:
            captured_popen.update({"command": command, **kwargs})
            return process

        client = aegis_runtime.TraceRelayClient(
            command=TEST_TRACERELAY_COMMAND,
            cli_runner=cli_runner,
            status_requester=lambda: next(statuses),
            popen_factory=popen_factory,
            process_creation_time_reader=lambda pid: pid * 10_000,
            alarm_directory=root / "alarms",
            monitor_interval_seconds=0,
            verification_timeout_seconds=verification_timeout_seconds,
        )
        bind_test_runtime(client)
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
            self.assertEqual(
                commands[0][2:],
                [
                    "--runtime-nonce",
                    TEST_RUNTIME_NONCE,
                    "--expected-sdk-manifest-sha256",
                    TEST_SDK_MANIFEST_SHA256,
                    "--expected-python-sha256",
                    TEST_PYTHON_SHA256,
                ],
            )

    def test_runtime_identity_mismatch_is_not_accepted_or_downgraded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                del timeout
                payload = relay_payload("start")
                identity = dict(payload["runtime_identity"])
                identity["runtime_nonce"] = "44" * 16
                payload["runtime_identity"] = identity
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload), ""
                )

            client = aegis_runtime.TraceRelayClient(
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=lambda: relay_payload("status"),
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
            )
            bind_test_runtime(client)

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "differs from expectation"
            ):
                client.start()

    def test_resume_rejects_new_processes_with_the_same_nonce_and_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved_identity = relay_payload("start")["runtime_identity"]
            replacement = relay_payload("start")
            replacement["service_pid"] = 303
            replacement["supervisor_pid"] = 404
            replacement["runtime_identity"] = {
                "schema": "tracerelay.runtime_identity.v1",
                "runtime_nonce": TEST_RUNTIME_NONCE,
                "sdk_manifest_sha256": TEST_SDK_MANIFEST_SHA256,
                "python_executable_sha256": TEST_PYTHON_SHA256,
                "processes": {
                    "supervisor": _relay_process_identity("supervisor", 404),
                    "service": _relay_process_identity("service", 303),
                },
            }

            client = aegis_runtime.TraceRelayClient(
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=lambda _arguments, _timeout: self.fail(
                    "resume must not launch a replacement TraceRelay runtime"
                ),
                status_requester=lambda: replacement,
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
            )
            client.bind_runtime_expectation(
                runtime_nonce=TEST_RUNTIME_NONCE,
                sdk_manifest_sha256=TEST_SDK_MANIFEST_SHA256,
                python_executable_sha256=TEST_PYTHON_SHA256,
                observed_identity=saved_identity,
            )

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "different runtime process"
            ):
                client.start()

    def test_resume_without_observed_identity_never_launches_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = aegis_runtime.TraceRelayClient(
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=lambda _arguments, _timeout: self.fail(
                    "resume must not launch a replacement TraceRelay runtime"
                ),
                status_requester=lambda: (_ for _ in ()).throw(
                    ConnectionRefusedError("TraceRelay is absent")
                ),
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
            )
            client.bind_runtime_expectation(
                runtime_nonce=TEST_RUNTIME_NONCE,
                sdk_manifest_sha256=TEST_SDK_MANIFEST_SHA256,
                python_executable_sha256=TEST_PYTHON_SHA256,
                require_existing_runtime=True,
            )

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError,
                "no persisted observed identity",
            ):
                client.establish_runtime(require_idle=False)

    def test_resume_without_observed_identity_rejects_even_a_live_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = aegis_runtime.TraceRelayClient(
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=lambda _arguments, _timeout: self.fail(
                    "resume must probe rather than launch TraceRelay"
                ),
                status_requester=lambda: self.fail(
                    "unbound live runtime must not be accepted"
                ),
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
            )
            client.bind_runtime_expectation(
                runtime_nonce=TEST_RUNTIME_NONCE,
                sdk_manifest_sha256=TEST_SDK_MANIFEST_SHA256,
                python_executable_sha256=TEST_PYTHON_SHA256,
                require_existing_runtime=True,
            )

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError,
                "no persisted observed identity",
            ):
                client.establish_runtime(require_idle=False)

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
                **relay_payload("close"),
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
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=lambda: relay_payload("status"),
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=alarms,
            )
            bind_test_runtime(client)

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
                        **relay_payload("register", "WAITING"),
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
                        **relay_payload("close"),
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
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=status,
                popen_factory=popen_factory,
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
                monitor_interval_seconds=0.001,
            )
            bind_test_runtime(client)
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
                        **relay_payload("register", "WAITING"),
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
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=status,
                popen_factory=lambda *args, **kwargs: process,
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
                monitor_interval_seconds=0.001,
            )
            bind_test_runtime(client)
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

    def test_creation_time_failure_keeps_the_registered_session_and_verification(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_path = root / "sessions" / "session-1"
            process = InteractiveFakeProcess()
            client, _commands, _captured = self.make_client(
                root,
                status_payloads=[
                    relay_payload("status"),
                    {
                        **relay_payload("status", "WAITING"),
                        "session_id": "session-1",
                        "session_path": str(session_path),
                    },
                    {
                        **relay_payload("status"),
                        "last_session_id": "session-1",
                        "last_session_path": str(session_path),
                    },
                ],
                process=process,
            )
            client.start()
            client._process_creation_time_reader = lambda pid: (
                pid * 10_000
                if pid in {101, 202}
                else (_ for _ in ()).throw(OSError("FILETIME read failed"))
            )

            with self.assertRaisesRegex(OSError, "FILETIME read failed"):
                client.open_managed_process(
                    ["codex.exe", "app-server"], upstream_port=7_899
                )

            self.assertTrue(process.terminated)
            self.assertEqual(client.last_registration.session_id, "session-1")
            self.assertEqual(
                client.last_verification["status"],
                "VALID_COMPLETE",
            )

    def test_registration_operation_is_echoed_into_the_managed_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            operation_id = "ab" * 16
            client, commands, _captured = self.make_client(
                root,
                status_payloads=[relay_payload("status")],
                process=InteractiveFakeProcess(),
            )
            client.start()

            managed = client.open_managed_process(
                ["codex.exe", "app-server"],
                upstream_port=7_899,
                registration_operation_id=operation_id,
            )

            self.assertEqual(managed.registration.operation_id, operation_id)
            self.assertEqual(
                commands[1][1:],
                [
                    "register",
                    "--upstream-port",
                    "7899",
                    "--operation-id",
                    operation_id,
                    "--runtime-nonce",
                    TEST_RUNTIME_NONCE,
                ],
            )
            managed.terminate()
            managed.wait(timeout=1)

    def test_uncheckpointed_registration_resolves_and_seals_without_a_pid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_path = root / "sessions" / "resolved-session"
            operation_id = "cd" * 16
            events: list[str] = []
            statuses = iter(
                [
                    {
                        **relay_payload("status", "WAITING"),
                        "session_id": "resolved-session",
                        "session_path": str(session_path),
                    },
                    {
                        **relay_payload("status", "WAITING"),
                        "session_id": "resolved-session",
                        "session_path": str(session_path),
                    },
                    {
                        **relay_payload("status"),
                        "last_session_id": "resolved-session",
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
                if operation == "resolve-registration":
                    payload = {
                        "ok": True,
                        "command": operation,
                        "found": True,
                        "operation_id": operation_id,
                        "session_id": "resolved-session",
                        "proxy_host": "127.0.0.1",
                        "proxy_port": 45_000,
                        "upstream_host": "127.0.0.1",
                        "upstream_port": 7_899,
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
                            "client_to_upstream": 0,
                            "upstream_to_client": 0,
                        },
                    }
                else:
                    raise AssertionError(operation)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload), ""
                )

            client = aegis_runtime.TraceRelayClient(
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=lambda: next(statuses),
                process_creation_time_reader=lambda pid: pid * 10_000,
                process_terminator=lambda *_args: self.fail(
                    "uncheckpointed recovery must not terminate an unverified PID"
                ),
                alarm_directory=root / "alarms",
            )
            bind_test_runtime(client)

            registration = client.resolve_registration_operation(operation_id)
            assert registration is not None
            verification = client.recover_uncheckpointed_registration(registration)

            self.assertEqual(verification["status"], "VALID_COMPLETE")
            self.assertEqual(events, ["resolve-registration", "close", "verify"])

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
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=lambda: next(statuses),
                process_creation_time_reader=lambda pid: pid * 10_000,
                process_terminator=lambda pid, created: (
                    events.append(f"identity-missing:{pid}:{created}") or False
                ),
                alarm_directory=root / "alarms",
            )
            bind_test_runtime(client)
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
                command=TEST_TRACERELAY_COMMAND,
                cli_runner=cli_runner,
                status_requester=lambda: relay_payload("status"),
                process_creation_time_reader=lambda pid: pid * 10_000,
                process_terminator=lambda pid, created: (
                    terminated.append((pid, created)) or True
                ),
                alarm_directory=root / "alarms",
            )
            bind_test_runtime(client)
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
        self.instruction_receipts: dict[str, tuple[Path, bytes]] = {}
        self.turn_statuses: list[bool] = []
        self.current_node: str | None = None
        self.current_artifact_path: Path | None = None


class ExecutionManagedProcess:
    def __init__(
        self,
        harness: ExecutionTurnHarness,
        relay: ExecutionRelayClient,
        session_index: int,
        operation_id: str,
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
            operation_id=operation_id,
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
        del args
        operation_id = kwargs.pop("registration_operation_id")
        assert isinstance(operation_id, str)
        del kwargs
        self.harness.open_count += 1
        process = ExecutionManagedProcess(
            self.harness,
            self,
            self.harness.open_count,
            operation_id,
        )
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


class RegisteredProcessStartFailureRelay(FakeRelayClient):
    def __init__(
        self,
        root: Path,
        *,
        session_id: str,
        error: BaseException,
        verification: dict[str, object] | None,
    ) -> None:
        super().__init__()
        self.registration = aegis_runtime.TraceRelayRegistration(
            session_id=session_id,
            proxy_host="127.0.0.1",
            proxy_port=45_000,
            upstream_port=7_899,
            session_path=root / "sessions" / session_id,
        )
        self.error = error
        self.verification = verification
        self.last_registration: aegis_runtime.TraceRelayRegistration | None = None
        self.last_verification: dict[str, object] | None = None
        self.open_count = 0

    def open_managed_process(self, *args: object, **kwargs: object) -> object:
        del args
        operation_id = kwargs.pop("registration_operation_id")
        assert isinstance(operation_id, str)
        del kwargs
        self.open_count += 1
        self.last_registration = aegis_runtime.TraceRelayRegistration(
            session_id=self.registration.session_id,
            proxy_host=self.registration.proxy_host,
            proxy_port=self.registration.proxy_port,
            upstream_port=self.registration.upstream_port,
            session_path=self.registration.session_path,
            operation_id=operation_id,
        )
        self.last_verification = (
            dict(self.verification) if self.verification is not None else None
        )
        raise self.error


class RegistrationIntentRecoveryRelay(FakeRelayClient):
    def __init__(
        self,
        registration: aegis_runtime.TraceRelayRegistration | None,
        *,
        verification_status: str = "VALID_COMPLETE",
    ) -> None:
        super().__init__()
        self.registration = registration
        self.verification_status = verification_status
        self.resolve_count = 0
        self.recover_count = 0

    def resolve_registration_operation(
        self, operation_id: str
    ) -> aegis_runtime.TraceRelayRegistration | None:
        self.resolve_count += 1
        if self.registration is not None:
            assert self.registration.operation_id == operation_id
        return self.registration

    def recover_uncheckpointed_registration(
        self, registration: aegis_runtime.TraceRelayRegistration
    ) -> dict[str, object]:
        self.recover_count += 1
        assert registration == self.registration
        return {
            "status": self.verification_status,
            "final_hash": "de" * 32,
            "observed_bytes": {
                "client_to_upstream": 0,
                "upstream_to_client": 0,
            },
        }


class ExecutionAppServer:
    def __init__(self, harness: ExecutionTurnHarness, **kwargs: Any) -> None:
        self.harness = harness
        self.process_factory = kwargs["process_factory"]
        self.process: ExecutionManagedProcess | None = None
        self.closed = False
        self.last_prompt: str | None = None
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
        thread_id = f"execution-thread-{self.harness.thread_count}"
        instructions = str(kwargs.get("developer_instructions", ""))
        marker = "Before every role task, atomically write the exact UTF-8 JSON below to `"
        start = instructions.find(marker)
        if start >= 0:
            path_start = start + len(marker)
            path_end = instructions.index("`", path_start)
            json_start = instructions.index("```json\n", path_end) + len("```json\n")
            json_end = instructions.index("\n```", json_start)
            self.harness.instruction_receipts[thread_id] = (
                Path(instructions[path_start:path_end]),
                instructions[json_start:json_end].encode("utf-8"),
            )
        return SimpleNamespace(
            thread_id=thread_id,
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
        del kwargs
        self.last_prompt = prompt
        receipt = self.harness.instruction_receipts.get(thread_id)
        if receipt is not None:
            path, encoded = receipt
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded)
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
        try:
            prompt = json.loads(self.last_prompt or "{}")
        except json.JSONDecodeError:
            prompt = {}
        control = prompt.get("test_execution_control") or prompt.get(
            "execution_control", {}
        )
        node = str(control.get("node") or self.harness.current_node)
        artifact_root = Path(
            str(control.get("artifact_path") or self.harness.current_artifact_path)
        )
        required = {
            "C": {"test-execution-request": "TEST_EXECUTION_REQUEST.json"},
            "D": {"test-result-review": "TEST_RESULT_REVIEW.md"},
            "E": {"test-report": "TEST_REPORT.md"},
            "F": {
                "final-review": "FINAL_REVIEW.md",
                "final-review-verdict": "FINAL_REVIEW_VERDICT.json",
            },
        }[node]
        outputs = []
        for artifact_id, name in required.items():
            path = artifact_root / name
            content = path.read_bytes()
            outputs.append(
                {
                    "artifact_id": artifact_id,
                    "path": str(path.resolve()),
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        status = self.harness.turn_statuses.pop(0) if self.harness.turn_statuses else True
        response: dict[str, object] = {
            "artifact_path": str(self.harness.root / "artifacts"),
            "reasoning_ledger_context_pack": str(
                self.harness.root / "artifacts" / "context.json"
            ),
        }
        if node in {"D", "F"}:
            response.update(
                review_conclusion="PASS" if status else "FAIL",
                finding_categories=(
                    []
                    if status
                    else [
                        "EXECUTION_INCOMPLETE"
                        if node == "D"
                        else "GOVERNANCE_DEFECT"
                    ]
                ),
                findings=(
                    []
                    if status
                    else [
                        {
                            "finding_id": "review-finding-1",
                            "category": (
                                "EXECUTION_INCOMPLETE"
                                if node == "D"
                                else "GOVERNANCE_DEFECT"
                            ),
                            "summary": "Required review evidence is incomplete.",
                            "reasoning": "The supplied evidence does not close the review.",
                            "evidence_ids": [outputs[0]["artifact_id"]],
                        }
                    ]
                ),
                review_output_artifacts=outputs,
            )
        else:
            response.update(output_artifacts=outputs, status=status)
        return SimpleNamespace(
            thread_id=thread_id,
            turn_id=turn_id,
            status="completed",
            final_message=json.dumps(response),
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
            operation_id="fa" * 16,
        )

    def run_process(self, *args: object, **kwargs: object) -> object:
        raise aegis_runtime.TraceRelayError("journal failed")


class RuntimeCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._coordinators: list[aegis_runtime.RuntimeCoordinator] = []
        original_init = aegis_runtime.RuntimeCoordinator.__init__

        def tracked_init(
            coordinator: aegis_runtime.RuntimeCoordinator,
            *args: object,
            **kwargs: object,
        ) -> None:
            original_init(coordinator, *args, **kwargs)
            self._coordinators.append(coordinator)

        self._coordinator_init_patch = patch.object(
            aegis_runtime.RuntimeCoordinator, "__init__", new=tracked_init
        )
        self._coordinator_init_patch.start()
        self.addCleanup(self._coordinator_init_patch.stop)
        self.addCleanup(
            lambda: [
                coordinator._close_run_wide_freeze()
                for coordinator in reversed(self._coordinators)
            ]
        )
        original_temporary_directory = tempfile.TemporaryDirectory
        coordinators = self._coordinators

        class TrackedTemporaryDirectory(original_temporary_directory):
            def __exit__(self, exc: object, value: object, traceback: object) -> object:
                temporary_root = Path(self.name).resolve()
                for coordinator in reversed(coordinators):
                    try:
                        coordinator.project_root.relative_to(temporary_root)
                    except ValueError:
                        continue
                    coordinator._close_run_wide_freeze()
                return super().__exit__(exc, value, traceback)

        self._temporary_directory_patch = patch.object(
            tempfile, "TemporaryDirectory", TrackedTemporaryDirectory
        )
        self._temporary_directory_patch.start()
        self.addCleanup(self._temporary_directory_patch.stop)

        def export_test_snapshot(
            project_root: str | Path, *, project_id_hex: str
        ) -> dict[str, object]:
            del project_id_hex
            path = (
                Path(project_root)
                / ".aegis"
                / "reasoning_ledger"
                / "test-live-snapshot.json"
            )
            return json.loads(path.read_text(encoding="utf-8"))

        self._ledger_snapshot_patch = patch.object(
            aegis_runtime,
            "export_live_reasoning_ledger_snapshot",
            side_effect=export_test_snapshot,
        )
        self._ledger_snapshot_patch.start()
        self.addCleanup(self._ledger_snapshot_patch.stop)
        self._dead_prior_owner_patch = patch.object(
            agent_registry,
            "_process_owner_is_alive",
            return_value=False,
        )
        self._dead_prior_owner_patch.start()
        self.addCleanup(self._dead_prior_owner_patch.stop)

    def write_engineering_input_manifest(self, project: Path) -> Path:
        requirements = project / "docs" / "REQUIREMENTS.md"
        implementation = project / "docs" / "IMPLEMENTATION_PLAN.md"
        requirements.parent.mkdir(parents=True, exist_ok=True)
        if not requirements.exists():
            requirements.write_text("requirement\n", encoding="utf-8")
        if not implementation.exists():
            implementation.write_text("implementation\n", encoding="utf-8")

        def descriptor(kind: str, path: Path) -> dict[str, object]:
            content = path.read_bytes()
            return {
                "kind": kind,
                "path": str(path.resolve()),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }

        manifest = project / "ENGINEERING_INPUT_MANIFEST.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "aegis.engineering_input_manifest.v1",
                    "project_id_hex": bytes(range(16)).hex(),
                    "created_at_utc": "2026-08-17T00:00:00Z",
                    "documents": [
                        descriptor("REQUIREMENTS", requirements),
                        descriptor("IMPLEMENTATION_PLAN", implementation),
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def write_reasoning_context_pack(
        self,
        project: Path,
        path: Path,
        engineering_manifest: Path,
    ) -> Path:
        seal = project_seal_store.verify_expected_project_seal(project)
        engineering = aegis_runtime.validate_engineering_input_manifest(
            engineering_manifest,
            project_root=project,
            project_id_hex=seal.project_id.hex(),
        )
        return write_test_reasoning_context_pack(
            project,
            path,
            project_id_hex=seal.project_id.hex(),
            project_seal=seal.expected_seal,
            engineering_documents_sha256=engineering.documents_sha256,
        )

    def test_instruction_receipt_accepts_exact_displayed_json_without_newline(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="instruction-receipt-exact-bytes",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            instructions = coordinator._compose_instruction_receipt_protocol(
                "TEST_PLAN_AUTHOR", "author"
            )
            json_start = instructions.index("```json\n") + len("```json\n")
            json_end = instructions.index("\n```", json_start)
            displayed = instructions[json_start:json_end].encode("utf-8")
            self.assertFalse(displayed.endswith(b"\n"))

            spec = coordinator._instruction_receipt_specs["TEST_PLAN_AUTHOR"]
            self.assertEqual(
                hashlib.sha256(displayed).hexdigest(), spec["encoded_sha256"]
            )
            staging_path = Path(str(spec["path"]))
            staging_path.parent.mkdir(parents=True, exist_ok=True)
            staging_path.write_bytes(displayed)
            receipt: dict[str, object] = {}
            coordinator._seal_instruction_receipt(
                "TEST_PLAN_AUTHOR", "instruction-receipt-job", receipt
            )

            snapshot_path = Path(str(receipt["instruction_receipt_path"]))
            self.assertEqual(snapshot_path.read_bytes(), displayed)
            self.assertEqual(
                receipt["instruction_receipt_sha256"],
                hashlib.sha256(displayed).hexdigest(),
            )
            coordinator._seal_instruction_receipt(
                "TEST_PLAN_AUTHOR", "instruction-receipt-job", receipt
            )
            self.assertEqual(snapshot_path.read_bytes(), displayed)

            staging_path.write_bytes(displayed + b"\n")
            receipt_with_newline: dict[str, object] = {}
            coordinator._seal_instruction_receipt(
                "TEST_PLAN_AUTHOR",
                "instruction-receipt-job-with-newline",
                receipt_with_newline,
            )
            normalized_path = Path(
                str(receipt_with_newline["instruction_receipt_path"])
            )
            self.assertEqual(normalized_path.read_bytes(), displayed)
            self.assertEqual(
                receipt_with_newline["instruction_receipt_sha256"],
                hashlib.sha256(displayed).hexdigest(),
            )

    def test_planning_rejects_arbitrary_json_as_reasoning_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            runtime_root = root / "runtime"
            artifacts = runtime_root / "runs" / "run-context-invalid" / "artifacts"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifacts,
                runtime_root=runtime_root,
                run_id="run-context-invalid",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            coordinator.preflight()
            invalid = root / "invalid-context.json"
            invalid.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "invalid reasoning context pack",
            ):
                coordinator.prepare_planning_author(invalid)

    def test_planning_uses_run_owned_context_and_engineering_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            runtime_root = root / "runtime"
            artifacts = runtime_root / "runs" / "run-context-snapshot" / "artifacts"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifacts,
                runtime_root=runtime_root,
                run_id="run-context-snapshot",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            coordinator.preflight()
            source_context = self.write_reasoning_context_pack(
                project,
                root / "source-context.json",
                manifest,
            )

            control = coordinator.prepare_planning_author(source_context)

            self.assertEqual(
                Path(str(control["context_pack_path"])),
                artifacts / "REASONING_LEDGER_CONTEXT_PACK.json",
            )
            engineering_control = coordinator._engineering_input_control()
            assert engineering_control is not None
            frozen_documents = engineering_control["documents"]
            self.assertEqual(len(frozen_documents), 2)
            for document in frozen_documents:
                snapshot_path = Path(str(document["snapshot_path"]))
                self.assertTrue(snapshot_path.is_relative_to(artifacts))
                self.assertTrue(snapshot_path.is_file())

    def test_role_runtime_profile_is_applied_to_app_server_command(self) -> None:
        command = aegis_runtime.configured_app_server_command(
            ("codex.cmd", "app-server", "--listen", "stdio://"),
            {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
        )

        self.assertEqual(
            command,
            (
                "codex.cmd",
                "-c",
                'model="gpt-5.6-sol"',
                "-c",
                'model_reasoning_effort="xhigh"',
                "app-server",
                "--listen",
                "stdio://",
            ),
        )

    def test_ultra_role_runtime_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported reasoning effort"):
            aegis_runtime.RuntimeCoordinator(
                project_root=Path.cwd(),
                artifact_path=Path.cwd() / "artifacts",
                run_id="invalid-ultra",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                role_runtime_profiles={
                    "FINAL_REVIEWER": {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "ultra",
                    }
                },
            )

    def test_runtime_state_and_checkpoints_stay_outside_project_aegis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            runtime_root = root / "local-runtime" / "project-1"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "run-storage" / "artifacts",
                runtime_root=runtime_root,
                run_id="run-storage",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )

            coordinator.preflight()
            with aegis_runtime.open_graph_checkpointer(runtime_root):
                pass

            self.assertEqual(
                coordinator.run_state_path,
                runtime_root / "runs" / "run-storage" / "RUN_STATE.json",
            )
            self.assertTrue(coordinator.run_state_path.is_file())
            self.assertTrue(
                (runtime_root / "project_state" / "checkpoints.sqlite3").is_file()
            )
            self.assertFalse((project / ".aegis" / "runtime").exists())

    def test_c_start_reuses_plan_only_when_engineering_inputs_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            runtime_root = root / "runtime"
            first_artifacts = runtime_root / "runs" / "parent" / "artifacts"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=first_artifacts,
                runtime_root=runtime_root,
                run_id="parent",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            first.preflight()
            self.attach_planning_evidence_process(
                first, root, session_id="planning-reuse-source"
            )
            self.approve_planning_round(first, first_artifacts)
            first.complete_planning_stage()
            first._write_state("terminated")
            source_state = aegis_runtime.load_run_state(runtime_root, "parent")

            current_context = self.write_reasoning_context_pack(
                project,
                root / "current-context.json",
                manifest,
            )
            second_artifacts = runtime_root / "runs" / "child" / "artifacts"
            second = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=second_artifacts,
                runtime_root=runtime_root,
                run_id="child",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
                engineering_input_manifest_path=manifest,
                planning_reuse_run_id="parent",
                planning_reuse_state=source_state,
                planning_reuse_context_pack_path=current_context,
            )
            second.preflight()

            self.assertEqual(second.planning_stage_status, "completed")
            self.assertIn(
                "AEGIS_TEST_EXECUTION_POLICY_BEGIN",
                (second_artifacts / "APPROVED_TEST_PLAN.md").read_text(
                    encoding="utf-8"
                ),
            )
            saved = aegis_runtime.load_run_state(runtime_root, "child")
            self.assertEqual(saved["planning_reuse"]["parent_run_id"], "parent")

            with self.assertRaises(PermissionError):
                (project / "docs" / "REQUIREMENTS.md").write_text(
                    "mutated\n", encoding="utf-8"
                )

    def test_c_start_rejects_changed_engineering_input_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            runtime_root = root / "runtime"
            first_artifacts = runtime_root / "runs" / "parent" / "artifacts"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=first_artifacts,
                runtime_root=runtime_root,
                run_id="parent",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            first.preflight()
            self.attach_planning_evidence_process(
                first, root, session_id="planning-reuse-mismatch"
            )
            self.approve_planning_round(first, first_artifacts)
            first.complete_planning_stage()
            first._write_state("terminated")
            source_state = aegis_runtime.load_run_state(runtime_root, "parent")

            (project / "docs" / "REQUIREMENTS.md").write_text(
                "new requirement\n", encoding="utf-8"
            )
            manifest = self.write_engineering_input_manifest(project)
            current_context = self.write_reasoning_context_pack(
                project,
                root / "current-context.json",
                manifest,
            )
            second = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "child" / "artifacts",
                runtime_root=runtime_root,
                run_id="child",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
                engineering_input_manifest_path=manifest,
                planning_reuse_run_id="parent",
                planning_reuse_state=source_state,
                planning_reuse_context_pack_path=current_context,
            )
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "rerun A-F from A",
            ):
                second.preflight()

    def test_c_start_rejects_parent_state_not_bound_to_reservation_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            runtime_root = root / "runtime"
            parent_artifacts = runtime_root / "runs" / "parent" / "artifacts"
            parent = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=parent_artifacts,
                runtime_root=runtime_root,
                run_id="parent",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            parent.preflight()
            context = self.write_reasoning_context_pack(
                project,
                root / "parent-context.json",
                manifest,
            )
            self.attach_planning_evidence_process(
                parent, root, session_id="planning-reuse-forgery"
            )
            self.approve_planning_round(parent, parent_artifacts, context_path=context)
            parent.complete_planning_stage()
            parent._write_state("terminated")
            forged_state = aegis_runtime.load_run_state(runtime_root, "parent")
            forged_state["project_root"] = str(root / "different-project")
            child_context = self.write_reasoning_context_pack(
                project,
                root / "child-context.json",
                manifest,
            )
            child = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "child" / "artifacts",
                runtime_root=runtime_root,
                run_id="child",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
                engineering_input_manifest_path=manifest,
                planning_reuse_run_id="parent",
                planning_reuse_state=forged_state,
                planning_reuse_context_pack_path=child_context,
            )

            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "authoritative state|reservation digest|source project",
            ):
                child.preflight()

    def test_execution_role_reuses_project_thread_across_workflow_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            runtime_root = root / "local-runtime" / "project-1"
            role_skill_bindings = {
                "TEST_EXECUTOR": [
                    {
                        "name": "aegis-test-executor",
                        "version": "1",
                        "sha256": "b" * 64,
                    }
                ]
            }

            class ThreadClient:
                def __init__(self) -> None:
                    self.started: list[str] = []
                    self.resumed: list[str] = []

                def start_thread(self, **kwargs: object) -> SimpleNamespace:
                    self.started.append(str(kwargs["developer_instructions"]))
                    return SimpleNamespace(
                        thread_id="thread-project-executor",
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )

                def resume_thread(
                    self, thread_id: str, **kwargs: object
                ) -> SimpleNamespace:
                    del kwargs
                    self.resumed.append(thread_id)
                    return SimpleNamespace(
                        thread_id=thread_id,
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )

            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "run-one" / "artifacts",
                runtime_root=runtime_root,
                role_skill_bindings=role_skill_bindings,
                run_id="run-one",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
            )
            first.preflight()
            first_client = ThreadClient()
            first_thread = first._ensure_execution_thread(
                first_client,
                {},
                role_key="TEST_EXECUTOR",
                developer_instructions="executor instructions",
                instructions_sha256="a" * 64,
            )
            first._write_state("completed")

            second = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "run-two" / "artifacts",
                runtime_root=runtime_root,
                role_skill_bindings=role_skill_bindings,
                run_id="run-two",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
            )
            second.preflight()
            second_client = ThreadClient()
            second_thread = second._ensure_execution_thread(
                second_client,
                {},
                role_key="TEST_EXECUTOR",
                developer_instructions="executor instructions",
                instructions_sha256="a" * 64,
            )

            self.assertEqual(first_thread, "thread-project-executor")
            self.assertEqual(second_thread, first_thread)
            self.assertEqual(len(first_client.started), 1)
            self.assertEqual(second_client.started, [])
            self.assertEqual(second_client.resumed, [first_thread])
            registry_payload = json.loads(
                (
                    runtime_root
                    / "project_state"
                    / "dynamic_agent_registry.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                registry_payload["roles"]["TEST_EXECUTOR"]["current"][
                    "skill_bindings"
                ],
                role_skill_bindings["TEST_EXECUTOR"],
            )

    def test_runtime_profile_change_retires_cross_run_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            runtime_root = root / "runtime"

            class ThreadClient:
                def __init__(self, thread_id: str, effort: str) -> None:
                    self.thread_id = thread_id
                    self.effort = effort
                    self.resume_calls: list[str] = []

                def start_thread(self, **kwargs: object) -> SimpleNamespace:
                    return SimpleNamespace(
                        thread_id=self.thread_id,
                        model="gpt-5.6-sol",
                        reasoning_effort=self.effort,
                    )

                def resume_thread(
                    self, thread_id: str, **kwargs: object
                ) -> SimpleNamespace:
                    self.resume_calls.append(thread_id)
                    return SimpleNamespace(
                        thread_id=thread_id,
                        model="gpt-5.6-sol",
                        reasoning_effort=self.effort,
                    )

            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "profile-one" / "artifacts",
                runtime_root=runtime_root,
                run_id="profile-one",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
                role_runtime_profiles={
                    "TEST_EXECUTOR": {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "high",
                    }
                },
            )
            first.preflight()
            first_thread = first._ensure_execution_thread(
                ThreadClient("thread-high", "high"),
                {},
                role_key="TEST_EXECUTOR",
                developer_instructions="executor",
                instructions_sha256="a" * 64,
            )
            first._write_state("completed")

            second = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "profile-two" / "artifacts",
                runtime_root=runtime_root,
                run_id="profile-two",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
                role_runtime_profiles={
                    "TEST_EXECUTOR": {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "xhigh",
                    }
                },
            )
            second.preflight()
            second_client = ThreadClient("thread-xhigh", "xhigh")
            second_thread = second._ensure_execution_thread(
                second_client,
                {},
                role_key="TEST_EXECUTOR",
                developer_instructions="executor",
                instructions_sha256="a" * 64,
            )

            self.assertEqual(first_thread, "thread-high")
            self.assertEqual(second_thread, "thread-xhigh")
            self.assertEqual(second_client.resume_calls, [])
            registry = second._require_agent_registry()
            self.assertEqual(
                registry.retired("TEST_EXECUTOR")[-1]["retired_reason"],
                "role contract changed",
            )

    def test_planning_role_reuses_project_thread_across_workflow_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            runtime_root = root / "local-runtime" / "project-1"

            class ThreadClient:
                def __init__(self) -> None:
                    self.started: list[str] = []
                    self.resumed: list[str] = []

                def start_thread(self, **kwargs: object) -> SimpleNamespace:
                    self.started.append(str(kwargs["developer_instructions"]))
                    return SimpleNamespace(
                        thread_id="thread-project-author",
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )

                def resume_thread(
                    self, thread_id: str, **kwargs: object
                ) -> SimpleNamespace:
                    del kwargs
                    self.resumed.append(thread_id)
                    return SimpleNamespace(
                        thread_id=thread_id,
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )

            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "plan-one" / "artifacts",
                runtime_root=runtime_root,
                run_id="plan-one",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            first_client = ThreadClient()
            first._planning_app_server = first_client
            first_thread = first._ensure_planning_thread(
                "TEST_PLAN_AUTHOR",
                developer_instructions="author instructions",
            )
            first._write_state("completed")

            second = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "plan-two" / "artifacts",
                runtime_root=runtime_root,
                run_id="plan-two",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            second.preflight()
            second_client = ThreadClient()
            second._planning_app_server = second_client
            second_thread = second._ensure_planning_thread(
                "TEST_PLAN_AUTHOR",
                developer_instructions="author instructions",
            )

            self.assertEqual(first_thread, "thread-project-author")
            self.assertEqual(second_thread, first_thread)
            self.assertEqual(len(first_client.started), 1)
            self.assertEqual(second_client.started, [])
            self.assertEqual(second_client.resumed, [first_thread])

    def make_sealed_project(self, root: Path) -> Path:
        project = root / "project"
        source = project / "src" / "module.py"
        source.parent.mkdir(parents=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        write_test_runtime_scope_policy(project)
        head = initialize_test_git_repository(project)
        project_seal_store.record_project_seal(
            project,
            git_head_before_record=head,
            project_id=bytes(range(16)),
            seal_chain_id=bytes(range(16, 32)),
        )
        return project

    def planning_review_result(
        self,
        coordinator: aegis_runtime.RuntimeCoordinator,
        review_control: Mapping[str, object],
        *,
        reviewed_plan_sha256: str,
        score: int,
        error_count: int,
        warning_count: int,
        review_conclusion: str,
        semantic_issues: list[dict[str, object]] | None = None,
        prior_issue_assessments: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        report_path = Path(str(review_control["review_report_path"]))
        report_bytes = report_path.read_bytes()
        has_findings = review_conclusion != "PASS"
        return {
            "artifact_path": str(coordinator.artifact_path),
            "reasoning_ledger_context_pack": str(
                review_control["context_pack_path"]
            ),
            "review_conclusion": review_conclusion,
            "finding_categories": ["TEST_PLAN_DEFECT"] if has_findings else [],
            "findings": (
                [
                    {
                        "finding_id": "test-plan-defect-1",
                        "category": "TEST_PLAN_DEFECT",
                        "summary": "The test plan does not close a required condition.",
                        "reasoning": "The review report records the unresolved condition.",
                        "evidence_ids": ["reviewed-test-plan"],
                    }
                ]
                if has_findings
                else []
            ),
            "review_output_artifacts": [
                {
                    "artifact_id": "test-plan-review",
                    "path": str(report_path.resolve()),
                    "size": len(report_bytes),
                    "sha256": hashlib.sha256(report_bytes).hexdigest(),
                }
            ],
            "reviewed_plan_sha256": reviewed_plan_sha256,
            "score": score,
            "error_count": error_count,
            "warning_count": warning_count,
            "semantic_issues": semantic_issues or [],
            "prior_issue_assessments": prior_issue_assessments or [],
        }

    def approve_planning_round(
        self,
        coordinator: aegis_runtime.RuntimeCoordinator,
        artifact_path: Path,
        *,
        context_path: Path | None = None,
    ) -> dict[str, object]:
        artifact_path.mkdir(parents=True, exist_ok=True)
        if context_path is None:
            assert coordinator._seal is not None
            assert coordinator._engineering_input_manifest is not None
            context_path = write_test_reasoning_context_pack(
                coordinator.project_root,
                artifact_path / "context-source.json",
                project_id_hex=coordinator._seal.project_id.hex(),
                project_seal=coordinator._seal.expected_seal,
                engineering_documents_sha256=str(
                    coordinator._engineering_input_manifest["documents_sha256"]
                ),
            )
        author = coordinator.prepare_planning_author(context_path)
        write_test_execution_policy(coordinator.project_root, artifact_path)
        authored_plan = artifact_path / "APPROVED_TEST_PLAN.md"
        Path(str(author["plan_path"])).write_bytes(authored_plan.read_bytes())
        frozen = coordinator.freeze_planning_plan(str(author["round_id"]))
        review = coordinator.prepare_planning_review()
        Path(str(review["review_report_path"])).write_text(
            "# Approved review\n", encoding="utf-8"
        )
        accepted = coordinator.record_planning_review(
            str(review["round_id"]),
            self.planning_review_result(
                coordinator,
                review,
                reviewed_plan_sha256=str(frozen["plan_sha256"]),
                score=95,
                error_count=0,
                warning_count=0,
                review_conclusion="PASS",
            ),
        )
        self.assertTrue(accepted)
        if not coordinator._planning_turns:
            responses = artifact_path / "responses" / "planning"
            responses.mkdir(parents=True, exist_ok=True)
            for role, suffix in (
                ("TEST_PLAN_AUTHOR", "author"),
                ("TEST_PLAN_REVIEWER", "review"),
            ):
                job_id = f"{coordinator.run_id}:planning:{author['round_id']}:{suffix}"
                response = responses / f"{suffix}.json"
                response.write_text('{"status":true}\n', encoding="utf-8")
                response_bytes = response.read_bytes()
                turn = {
                    "job_id": job_id,
                    "node": "A" if suffix == "author" else "B",
                    "role": role,
                    "client_message_id": f"{job_id}:{role}:submission",
                    "request_sha256": hashlib.sha256(job_id.encode()).hexdigest(),
                    "codex_thread_id": f"thread-{suffix}",
                    "codex_turn_id": f"turn-{suffix}",
                    "status": "completed",
                    "raw_response_path": str(response.resolve()),
                    "raw_response_sha256": hashlib.sha256(
                        response_bytes
                    ).hexdigest(),
                }
                coordinator._planning_turns.append(turn)
                coordinator._compose_instruction_receipt_protocol(
                    role, f"synthetic {role}"
                )
                receipt_spec = coordinator._instruction_receipt_specs[role]
                receipt_path = Path(str(receipt_spec["path"]))
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                receipt_path.write_bytes(
                    aegis_runtime._canonical_instruction_receipt_bytes(
                        receipt_spec["payload"]
                    )
                )
                coordinator._seal_instruction_receipt(role, job_id, turn)
            coordinator._write_state("running")
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
            operation_id="fb" * 16,
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
        result_status: bool | None = None,
    ) -> dict[str, object]:
        if (
            node == "C"
            and not coordinator._execution_attempts
            and coordinator.planning_stage_status != "completed"
        ):
            if coordinator._engineering_input_manifest is None:
                coordinator._engineering_input_source_path = (
                    self.write_engineering_input_manifest(
                        coordinator.project_root
                    )
                )
                coordinator._snapshot_engineering_inputs()
            self.approve_planning_round(coordinator, coordinator.artifact_path)
            if coordinator._planning_process is None:
                self.attach_planning_evidence_process(
                    coordinator,
                    coordinator.artifact_path,
                    session_id=f"{coordinator.run_id}-planning-session",
                )
            coordinator.complete_planning_stage()
        if node == "F":
            self.prepare_final_review_inputs(coordinator)
        if node == "C":
            latest_attempt = (
                coordinator._execution_attempts[-1]
                if coordinator._execution_attempts
                else None
            )
            if (
                isinstance(latest_attempt, dict)
                and latest_attempt.get("node") == "C"
                and latest_attempt.get("status") != "completed"
            ):
                request_attempt_id = str(latest_attempt["attempt_id"])
            else:
                request_attempt_id = (
                    f"attempt-{len(coordinator._execution_attempts) + 1:04d}"
                )
            write_test_execution_request(
                coordinator.project_root,
                coordinator.artifact_path,
                project_id_hex=coordinator._seal.project_id.hex(),
                workflow_run_id=coordinator.run_id,
                attempt_id=request_attempt_id,
            )

        def operation(node_state: dict[str, object]) -> dict[str, object]:
            coordinator.artifact_path.mkdir(parents=True, exist_ok=True)
            if node == "D":
                (coordinator.artifact_path / "TEST_RESULT_REVIEW.md").write_text(
                    "# Test result review\n", encoding="utf-8"
                )
            if node == "E":
                (coordinator.artifact_path / "TEST_REPORT.md").write_text(
                    "# Test report\n", encoding="utf-8"
                )
            if node == "F":
                verdict_status = (
                    bool(node_state["status"])
                    if result_status is None
                    else result_status
                )
                review_path = coordinator.artifact_path / "FINAL_REVIEW.md"
                review_path.write_text("# Final review\n", encoding="utf-8")
                review_bytes = review_path.read_bytes()
                input_manifest_path = (
                    coordinator.artifact_path / "FINAL_REVIEW_INPUT_MANIFEST.json"
                )
                input_manifest_bytes = input_manifest_path.read_bytes()
                input_manifest = json.loads(input_manifest_bytes)
                evidence_index = [
                    dict(item) for item in input_manifest["required_evidence"]
                ]
                evidence_index.extend(
                    [
                        {
                            "evidence_id": "final-review-input-manifest",
                            "path": str(input_manifest_path.resolve()),
                            "size": len(input_manifest_bytes),
                            "sha256": hashlib.sha256(
                                input_manifest_bytes
                            ).hexdigest(),
                        },
                        {
                            "evidence_id": "final-review",
                            "path": str(review_path.resolve()),
                            "size": len(review_bytes),
                            "sha256": hashlib.sha256(review_bytes).hexdigest(),
                        },
                    ]
                )
                (coordinator.artifact_path / "FINAL_REVIEW_VERDICT.json").write_text(
                    json.dumps(
                        {
                            "schema": "aegis.final_review_verdict.v1",
                            "workflow_run_id": coordinator.run_id,
                            "verdict": "PASS" if verdict_status else "FAIL",
                            "conclusion": "Synthetic final-review conclusion.",
                            "reasons": ["Synthetic evidence closes the test contract."],
                            "evidence_index": evidence_index,
                        }
                    ),
                    encoding="utf-8",
                )
            relay = coordinator.relay_client
            if isinstance(relay, ExecutionRelayClient):
                relay.harness.current_node = node
                relay.harness.current_artifact_path = coordinator.artifact_path
                relay.harness.turn_statuses.append(
                    bool(node_state.get("status"))
                    if result_status is None
                    else result_status
                )
            response = coordinator.run_execution_agent(
                role,
                prompt or f"{node} prompt",
                output_schema={"type": "object"},
                developer_instructions=f"persistent {role}",
                timeout_seconds=5,
            )
            response_data = json.loads(response)
            if node == "D":
                review_stage = aegis_runtime.coordinator_review_stage(
                    aegis_runtime.REVIEW_CONTRACT_TEST_RESULT_REVIEWER,
                    response_data,
                )
                response_data.update(
                    coordinator_review_stage=review_stage,
                    status=review_stage == "TEST_REPORTING",
                )
            elif node == "F":
                review_stage = aegis_runtime.coordinator_review_stage(
                    aegis_runtime.REVIEW_CONTRACT_FINAL_REVIEWER,
                    response_data,
                )
                response_data.update(
                    coordinator_review_stage=review_stage,
                    status=response_data["review_conclusion"] == "PASS",
                )
            return {
                **node_state,
                **response_data,
                "response": response,
                "current_node": node,
            }

        return coordinator.execute_node(node, operation, state)

    def run_execution_through(
        self,
        coordinator: aegis_runtime.RuntimeCoordinator,
        target_node: str,
        state: dict[str, object],
        *,
        target_status: bool = True,
    ) -> dict[str, object]:
        roles = {
            "C": "TEST_EXECUTOR",
            "D": "TEST_RESULT_REVIEWER",
            "E": "TEST_REPORT_WRITER",
            "F": "FINAL_REVIEWER",
        }
        current = dict(state)
        for node in ("C", "D", "E", "F"):
            current = self.run_execution_node(
                coordinator,
                node,
                roles[node],
                current,
                result_status=target_status if node == target_node else True,
            )
            if node == target_node:
                return current
        raise AssertionError(f"unsupported execution target: {target_node}")

    def prepare_final_review_inputs(
        self, coordinator: aegis_runtime.RuntimeCoordinator
    ) -> None:
        coordinator.artifact_path.mkdir(parents=True, exist_ok=True)
        if coordinator._engineering_input_manifest is None:
            coordinator._engineering_input_source_path = (
                self.write_engineering_input_manifest(coordinator.project_root)
            )
            coordinator._snapshot_engineering_inputs()
        if coordinator._reasoning_context_pack is None:
            assert coordinator._seal is not None
            assert coordinator._engineering_input_manifest is not None
            context_source = write_test_reasoning_context_pack(
                coordinator.project_root,
                coordinator.artifact_path / "context-source.json",
                project_id_hex=coordinator._seal.project_id.hex(),
                project_seal=coordinator._seal.expected_seal,
                engineering_documents_sha256=str(
                    coordinator._engineering_input_manifest["documents_sha256"]
                ),
            )
            coordinator._snapshot_reasoning_context_pack(context_source)
        for name, content in (
            ("APPROVED_TEST_PLAN.md", "# Approved test plan\n"),
            ("PLANNING_HANDOFF.json", '{"verdict":"PASS"}\n'),
            ("TEST_REPORT.md", "# Test report\n"),
        ):
            path = coordinator.artifact_path / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def assert_execution_registration_failure_is_durable(
        self,
        *,
        root: Path,
        run_id: str,
        session_id: str,
        error: BaseException,
        verification: dict[str, object] | None,
    ) -> None:
        project = self.make_sealed_project(root)
        harness = ExecutionTurnHarness(root)
        relay = RegisteredProcessStartFailureRelay(
            root,
            session_id=session_id,
            error=error,
            verification=verification,
        )
        coordinator = aegis_runtime.RuntimeCoordinator(
            project_root=project,
            artifact_path=root / "artifacts",
            run_id=run_id,
            upstream_port=7_899,
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
            with self.assertRaisesRegex(type(error), str(error)):
                self.run_execution_node(
                    coordinator,
                    "C",
                    "TEST_EXECUTOR",
                    {"status": True},
                )

        saved = aegis_runtime.load_run_state(root / "artifacts", run_id)
        self.assertEqual(saved["execution_turns"][0]["status"], "preparing")
        self.assertEqual(
            saved["execution_turns"][0]["evidence_session_ids"],
            [session_id],
        )
        execution_evidence = [
            entry for entry in saved["evidence_sessions"] if entry["node"] == "C"
        ]
        self.assertEqual(len(execution_evidence), 1)
        evidence = execution_evidence[0]
        self.assertEqual(evidence["session_id"], session_id)
        self.assertEqual(evidence["node"], "C")
        self.assertEqual(
            evidence["verification_status"],
            verification["status"] if verification is not None else "UNVERIFIED",
        )
        self.assertEqual(evidence["application_verification_status"], "INVALID")
        self.assertIsNone(evidence["process_pid"])
        self.assertIsNone(evidence["process_creation_time_100ns"])

        resumed_relay = ExecutionRelayClient(harness)
        resumed = aegis_runtime.RuntimeCoordinator(
            project_root=project,
            artifact_path=root / "artifacts",
            run_id=run_id,
            upstream_port=7_899,
            relay_client=resumed_relay,
            start_node="C",
            prior_state=saved,
        )
        with self.assertRaisesRegex(
            aegis_runtime.RuntimeStateError,
            "incomplete TraceRelay evidence",
        ):
            resumed.preflight()
        self.assertFalse(resumed_relay.started)
        self.assertEqual(harness.open_count, 0)

    def test_node_failure_is_saved_atomically_after_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            relay = FakeRelayClient()
            artifact_path = root / "artifacts"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
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

    def test_planning_registration_is_persisted_when_process_start_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            relay = RegisteredProcessStartFailureRelay(
                root,
                session_id="planning-registered-before-popen-failure",
                error=OSError("CreateProcess failed after TraceRelay registration"),
                verification=None,
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-registered-process-failure",
                upstream_port=7_899,
                relay_client=relay,
                start_node="A",
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
                with self.assertRaisesRegex(OSError, "CreateProcess failed"):
                    coordinator.run_planning_agent(
                        "TEST_PLAN_AUTHOR",
                        "planning prompt",
                        output_schema={"type": "object"},
                        developer_instructions="persistent planning author",
                    )

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "planning-registered-process-failure"
            )
            self.assertEqual(len(saved["evidence_sessions"]), 1)
            evidence = saved["evidence_sessions"][0]
            self.assertEqual(evidence["node"], "planning")
            self.assertEqual(
                evidence["session_id"],
                "planning-registered-before-popen-failure",
            )
            self.assertEqual(evidence["verification_status"], "UNVERIFIED")
            self.assertEqual(evidence["application_verification_status"], "INVALID")
            self.assertIsNone(evidence["process_pid"])
            self.assertIsNone(evidence["process_creation_time_100ns"])

            resumed_relay = FakeRelayClient()
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="planning-registered-process-failure",
                upstream_port=7_899,
                relay_client=resumed_relay,
                start_node="A",
                prior_state=saved,
            )
            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()
            self.assertFalse(resumed_relay.started)
            terminated = aegis_runtime.load_run_state(
                root / "artifacts", "planning-registered-process-failure"
            )
            self.assertEqual(terminated["status"], "terminated")
            self.assertEqual(
                terminated["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )

    def test_execution_popen_failure_persists_registered_invalid_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assert_execution_registration_failure_is_durable(
                root=Path(directory),
                run_id="execution-popen-after-register-failure",
                session_id="execution-registered-before-popen-failure",
                error=OSError("CreateProcess failed after TraceRelay registration"),
                verification=None,
            )

    def test_execution_creation_time_failure_persists_without_fake_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assert_execution_registration_failure_is_durable(
                root=Path(directory),
                run_id="execution-filetime-after-register-failure",
                session_id="execution-registered-before-filetime-failure",
                error=aegis_runtime.TraceRelayError("FILETIME read failed"),
                verification={
                    "status": "VALID_COMPLETE",
                    "final_hash": "ab" * 32,
                    "observed_bytes": {
                        "client_to_upstream": 0,
                        "upstream_to_client": 0,
                    },
                },
            )

    def test_active_takeover_cleans_execution_registration_intent_before_termination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "execution-registration-intent-crash"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            coordinator._engineering_input_source_path = (
                self.write_engineering_input_manifest(project)
            )
            coordinator._snapshot_engineering_inputs()
            self.approve_planning_round(coordinator, artifact_path)
            self.attach_planning_evidence_process(
                coordinator,
                root,
                session_id="registration-intent-planning-session",
            )
            coordinator.complete_planning_stage()
            state = {
                "artifact_path": str(artifact_path),
                "reasoning_ledger_context_pack": str(
                    coordinator._reasoning_context_pack["snapshot_path"]
                ),
                "status": True,
            }
            coordinator._current_node = "C"
            coordinator._last_state = dict(state)
            attempt = coordinator._begin_execution_attempt("C", state)
            receipt = {
                "attempt_id": attempt["attempt_id"],
                "job_id": attempt["job_id"],
                "node": "C",
                "role": "TEST_EXECUTOR",
                "client_message_id": f"{attempt['job_id']}:submission",
                "request_sha256": "ab" * 32,
                "developer_instructions_sha256": "cd" * 32,
                "codex_thread_id": None,
                "codex_turn_id": None,
                "status": "preparing",
                "raw_response_path": None,
                "raw_response_sha256": None,
                "evidence_session_ids": [],
            }
            coordinator._execution_turns.append(receipt)
            operation_id = coordinator._begin_registration_intent(
                node="C", receipt=receipt
            )
            interrupted = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(
                interrupted["registration_intent"]["operation_id"], operation_id
            )
            self.assertFalse(
                any(
                    entry["node"] == "C"
                    for entry in interrupted["evidence_sessions"]
                )
            )

            registration = aegis_runtime.TraceRelayRegistration(
                session_id="resolved-execution-session",
                proxy_host="127.0.0.1",
                proxy_port=45_000,
                upstream_port=7_899,
                session_path=root / "sessions" / "resolved-execution-session",
                operation_id=operation_id,
            )
            relay = RegistrationIntentRecoveryRelay(registration)
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=relay,
                start_node="A",
                prior_state=interrupted,
            )

            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()

            self.assertFalse(relay.started)
            self.assertEqual(relay.resolve_count, 1)
            self.assertEqual(relay.recover_count, 1)
            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )
            self.assertIsNone(saved["registration_intent"])
            self.assertEqual(
                saved["execution_turns"][0]["evidence_session_ids"],
                [registration.session_id],
            )
            evidence = next(
                entry
                for entry in saved["evidence_sessions"]
                if entry["session_id"] == registration.session_id
            )
            self.assertEqual(evidence["session_id"], registration.session_id)
            self.assertEqual(
                evidence["registration_operation_id"], operation_id
            )
            self.assertEqual(evidence["application_verification_status"], "INVALID")
            self.assertIsNone(evidence["process_pid"])
            self.assertIsNone(evidence["process_creation_time_100ns"])

    def test_active_takeover_cleans_planning_registration_intent_before_termination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "planning-registration-intent-crash"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            coordinator._planning_stage_status = "active"
            operation_id = coordinator._begin_registration_intent(node="planning")
            interrupted = aegis_runtime.load_run_state(artifact_path, run_id)
            registration = aegis_runtime.TraceRelayRegistration(
                session_id="resolved-planning-session",
                proxy_host="127.0.0.1",
                proxy_port=45_000,
                upstream_port=7_899,
                session_path=root / "sessions" / "resolved-planning-session",
                operation_id=operation_id,
            )
            relay = RegistrationIntentRecoveryRelay(
                registration, verification_status="VALID_INCOMPLETE"
            )
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=relay,
                start_node="A",
                prior_state=interrupted,
            )

            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()

            self.assertFalse(relay.started)
            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )
            self.assertIsNone(saved["registration_intent"])
            evidence = saved["evidence_sessions"][0]
            self.assertEqual(evidence["node"], "planning")
            self.assertEqual(evidence["verification_status"], "VALID_INCOMPLETE")
            self.assertEqual(evidence["application_verification_status"], "INVALID")
            self.assertIsNone(evidence["process_pid"])

    def test_unresolved_registration_intent_blocks_before_relay_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "unresolved-registration-intent"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            coordinator._planning_stage_status = "active"
            operation_id = coordinator._begin_registration_intent(node="planning")
            interrupted = aegis_runtime.load_run_state(artifact_path, run_id)
            relay = RegistrationIntentRecoveryRelay(None)
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=relay,
                start_node="A",
                prior_state=interrupted,
            )

            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()

            self.assertFalse(relay.started)
            self.assertEqual(relay.resolve_count, 1)
            self.assertEqual(relay.recover_count, 0)
            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )
            self.assertEqual(
                saved["registration_intent"]["operation_id"], operation_id
            )
            self.assertEqual(saved["evidence_sessions"], [])

    def test_c_through_f_roles_keep_threads_but_use_one_process_and_session_per_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            engineering_manifest = self.write_engineering_input_manifest(project)
            harness = ExecutionTurnHarness(root)
            relay = ExecutionRelayClient(harness)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-c-d-c-e-f",
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
                engineering_input_manifest_path=engineering_manifest,
            )
            coordinator.preflight()
            self.attach_planning_evidence_process(
                coordinator, root, session_id="execution-planning"
            )
            self.approve_planning_round(coordinator, root / "artifacts")
            coordinator.complete_planning_stage()

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
                    first_c,
                    result_status=False,
                )
                second_c = self.run_execution_node(
                    coordinator,
                    "C",
                    "TEST_EXECUTOR",
                    first_d,
                    result_status=True,
                )
                second_d = self.run_execution_node(
                    coordinator,
                    "D",
                    "TEST_RESULT_REVIEWER",
                    second_c,
                )
                reported = self.run_execution_node(
                    coordinator,
                    "E",
                    "TEST_REPORT_WRITER",
                    second_d,
                )
                self.run_execution_node(
                    coordinator,
                    "F",
                    "FINAL_REVIEWER",
                    reported,
                )

            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(harness.open_count, 6)
            self.assertEqual(harness.finalize_count, 6)
            self.assertEqual(len({process.pid for process in harness.processes}), 6)
            self.assertTrue(all(server.closed for server in harness.app_servers))
            self.assertEqual(harness.thread_count, 4)
            self.assertEqual(
                harness.resume_thread_ids,
                ["execution-thread-1", "execution-thread-2"],
            )
            self.assertEqual(
                [turn["codex_thread_id"] for turn in saved["execution_turns"]],
                [
                    "execution-thread-1",
                    "execution-thread-2",
                    "execution-thread-1",
                    "execution-thread-2",
                    "execution-thread-3",
                    "execution-thread-4",
                ],
            )
            self.assertEqual(
                [turn["status"] for turn in saved["execution_turns"]],
                ["completed"] * 6,
            )
            c_attempts = [
                attempt
                for attempt in saved["execution_attempts"]
                if attempt["node"] == "C"
            ]
            self.assertEqual(len(c_attempts), 2)
            self.assertEqual(
                {Path(item["test_evidence_manifest_path"]).name for item in c_attempts},
                {"attempt-0001.json", "attempt-0003.json"},
            )
            self.assertTrue(
                all(
                    Path(item["test_evidence_manifest_path"]).is_file()
                    and len(item["test_ids"]) == 1
                    for item in c_attempts
                )
            )
            self.assertEqual(
                [turn["evidence_session_ids"] for turn in saved["execution_turns"]],
                [
                    ["execution-session-1"],
                    ["execution-session-2"],
                    ["execution-session-3"],
                    ["execution-session-4"],
                    ["execution-session-5"],
                    ["execution-session-6"],
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
                {
                    entry["process_pid"]
                    for entry in saved["evidence_sessions"]
                    if entry["node"] in {"C", "D", "E", "F"}
                },
                {1_001, 1_002, 1_003, 1_004, 1_005, 1_006},
            )
            self.assertEqual(
                {
                    entry["process_creation_time_100ns"]
                    for entry in saved["evidence_sessions"]
                    if entry["node"] in {"C", "D", "E", "F"}
                },
                {
                    10_000_001,
                    10_000_002,
                    10_000_003,
                    10_000_004,
                    10_000_005,
                    10_000_006,
                },
            )
            instruction_receipts = [
                Path(str(turn["instruction_receipt_path"]))
                for turn in saved["execution_turns"]
            ]
            self.assertTrue(all(path.is_file() for path in instruction_receipts))
            with self.assertRaises(PermissionError):
                instruction_receipts[0].write_text("{}\n", encoding="utf-8")
            coordinator._close_run_wide_freeze()
            instruction_receipts[0].write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "instruction receipt snapshot SHA-256 mismatch",
            ):
                coordinator._validate_persisted_instruction_receipts()

    def test_completed_final_review_can_finish_after_terminal_checkpoint_gap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-final-checkpoint-gap",
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
                result = self.run_execution_through(
                    coordinator,
                    "F",
                    state,
                )
            open_count_before_resume = harness.open_count

            coordinator._write_state(
                "failed", RuntimeError("orderly terminal checkpoint gap")
            )

            interrupted = aegis_runtime.load_run_state(
                root / "artifacts", "execution-final-checkpoint-gap"
            )
            self.assertEqual(interrupted["status"], "failed")
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-final-checkpoint-gap",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
                prior_state=interrupted,
            )
            resumed.preflight()
            resumed.complete(result)

            completed = aegis_runtime.load_run_state(
                root / "artifacts", "execution-final-checkpoint-gap"
            )
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(harness.open_count, open_count_before_resume)

    def test_terminal_finalizing_failure_resumes_only_to_intended_terminal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "terminal-finalizing-failure"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            first._terminal_target_status = "failed"
            provisional = first._build_state_payload(
                "terminal_finalizing", RuntimeError("terminal failure")
            )
            encoded = aegis_runtime._canonical_json_bytes(provisional)
            first._close_run_wide_freeze()
            first._release_project_lease()
            aegis_runtime._update_run_reservation_state(
                first.runtime_root,
                first.artifact_path,
                run_id,
                str(provisional["reservation_token"]),
                status="terminal_finalizing",
                encoded_state=encoded,
                expected_state_sha256=first._authoritative_state_sha256,
                expected_state_status=first._authoritative_state_status,
            )
            aegis_runtime._atomic_write_bytes(first.run_state_path, encoded)

            relay = FakeRelayClient()
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
                prior_state=dict(provisional),
            )
            resumed.preflight()

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "failed")
            self.assertIsNone(saved["terminal_target_status"])
            self.assertFalse(relay.started)

    def test_terminal_finalizing_mutation_recovery_does_not_require_full_graph(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "terminal-finalizing-mutation"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            mutation = aegis_runtime.FrozenInputMutationError(
                "frozen input changed",
                mutation_event={"path": str(project / "src" / "module.py")},
            )
            first._terminal_target_status = "terminated"
            provisional = first._build_state_payload(
                "terminal_finalizing", mutation
            )
            encoded = aegis_runtime._canonical_json_bytes(provisional)
            first._close_run_wide_freeze()
            first._release_project_lease()
            aegis_runtime._update_run_reservation_state(
                first.runtime_root,
                first.artifact_path,
                run_id,
                str(provisional["reservation_token"]),
                status="terminal_finalizing",
                encoded_state=encoded,
                expected_state_sha256=first._authoritative_state_sha256,
                expected_state_status=first._authoritative_state_status,
            )
            aegis_runtime._atomic_write_bytes(first.run_state_path, encoded)

            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=dict(provisional),
            )
            resumed.preflight()

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )
            self.assertEqual(saved["master_review_status"], "REQUIRES_USER_REASON")

    def test_persisted_mutation_terminal_cannot_be_downgraded_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "mutation-terminal-immutable"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            mutation = aegis_runtime.FrozenInputMutationError(
                "frozen input changed",
                mutation_event={"path": str(project / "src" / "module.py")},
            )
            coordinator._write_state("terminated", mutation)
            coordinator.fail(RuntimeError("outer wrapper failure"))

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )

    def test_generic_failed_transition_normalizes_mutation_to_terminated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "generic-mutation-normalized"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            mutation = aegis_runtime.FrozenInputMutationError(
                "F manifest evidence hash changed",
                mutation_event={"path": str(artifact_path / "TEST_REPORT.md")},
            )

            coordinator._write_state("failed", mutation)

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )
            self.assertEqual(saved["master_review_status"], "REQUIRES_USER_REASON")

    def test_terminal_boundary_is_committed_before_freeze_guards_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "terminal-boundary-before-close"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            observed_statuses: list[str] = []
            close_freeze = coordinator._close_run_wide_freeze

            def inspect_boundary_then_close() -> list[BaseException]:
                observed = aegis_runtime.load_run_state(artifact_path, run_id)
                observed_statuses.append(str(observed["status"]))
                self.assertTrue(coordinator._run_watchers)
                return close_freeze()

            with patch.object(
                coordinator,
                "_close_run_wide_freeze",
                side_effect=inspect_boundary_then_close,
            ):
                coordinator._write_state("failed", RuntimeError("terminal failure"))

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(observed_statuses, ["terminal_committed"])
            self.assertEqual(saved["status"], "failed")

    def test_terminal_committed_crash_recovers_only_conservative_outcome(self) -> None:
        for mutation_detected in (False, True):
            with (
                self.subTest(mutation_detected=mutation_detected),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                artifact_path = root / "artifacts"
                run_id = (
                    "terminal-committed-mutation"
                    if mutation_detected
                    else "terminal-committed-pass-candidate"
                )
                first = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                )
                first.preflight()
                finalize = first._finalize_run_wide_freeze

                def finalize_or_report_mutation() -> None:
                    if mutation_detected:
                        raise aegis_runtime.FrozenInputMutationError(
                            "frozen input changed during terminal drain",
                            mutation_event={
                                "path": str(project / "src" / "module.py")
                            },
                        )
                    finalize()

                with (
                    patch.object(
                        first,
                        "_finalize_run_wide_freeze",
                        side_effect=finalize_or_report_mutation,
                    ),
                    patch.object(
                        first,
                        "_close_run_wide_freeze",
                        side_effect=SystemExit("simulated crash after boundary CAS"),
                    ),
                    self.assertRaises(SystemExit),
                ):
                    first._write_state("completed")

                first._close_run_wide_freeze()
                first._release_project_lease()
                provisional = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(provisional["status"], "terminal_committed")
                self.assertEqual(
                    provisional["terminal_target_status"],
                    "terminated" if mutation_detected else "failed",
                )

                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                    prior_state=provisional,
                )
                resumed.preflight()
                recovered = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(
                    recovered["status"],
                    "terminated" if mutation_detected else "failed",
                )
                if mutation_detected:
                    self.assertEqual(
                        recovered["termination_reason_code"],
                        "FROZEN_INPUT_MUTATION",
                    )

    def test_terminal_finalizing_crash_cannot_recover_completed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "terminal-finalizing-pass-candidate"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            update_state = aegis_runtime._update_run_reservation_state

            def crash_before_boundary(*args: object, **kwargs: object) -> str:
                if kwargs.get("status") == "terminal_committed":
                    raise SystemExit("simulated crash before drain boundary commit")
                return update_state(*args, **kwargs)

            with (
                patch.object(
                    aegis_runtime,
                    "_update_run_reservation_state",
                    side_effect=crash_before_boundary,
                ),
                self.assertRaises(SystemExit),
            ):
                first._write_state("completed")

            first._close_run_wide_freeze()
            first._release_project_lease()
            provisional = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(provisional["status"], "terminal_finalizing")
            self.assertEqual(provisional["terminal_target_status"], "completed")
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=provisional,
            )
            resumed.preflight()
            recovered = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(recovered["status"], "failed")

    def test_final_cas_failure_cannot_erase_committed_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "committed-mutation-final-cas-failure"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            update_state = aegis_runtime._update_run_reservation_state

            def fail_final_cas(*args: object, **kwargs: object) -> str:
                if kwargs.get("status") == "terminated":
                    raise aegis_runtime.RuntimeStateError("injected final CAS failure")
                return update_state(*args, **kwargs)

            mutation = aegis_runtime.FrozenInputMutationError(
                "mutation found while draining terminal watcher",
                mutation_event={"path": str(project / "src" / "module.py")},
            )
            with (
                patch.object(
                    coordinator,
                    "_finalize_run_wide_freeze",
                    side_effect=mutation,
                ),
                patch.object(
                    aegis_runtime,
                    "_update_run_reservation_state",
                    side_effect=fail_final_cas,
                ),
                self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError, "injected final CAS failure"
                ) as raised,
            ):
                coordinator._write_state("completed")

            coordinator.fail(raised.exception)
            committed = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(committed["status"], "terminal_committed")
            self.assertEqual(committed["terminal_target_status"], "terminated")
            self.assertEqual(
                committed["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )
            self.assertIn("mutation_event", committed)

    def test_active_run_takeover_terminates_when_freeze_continuity_was_lost(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "active-freeze-continuity-lost"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            first._close_run_wide_freeze()
            first._release_project_lease()
            prior = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(prior["status"], "ready")
            relay = FakeRelayClient()
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
                prior_state=prior,
            )

            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )
            self.assertEqual(saved["project_id_hex"], prior["project_id_hex"])
            self.assertEqual(saved["seal_sequence"], prior["seal_sequence"])
            self.assertEqual(saved["expected_seal"], prior["expected_seal"])
            self.assertFalse(saved["delivery_eligible"])
            self.assertFalse(relay.started)

    def test_active_takeover_cleans_checkpointed_planning_session_before_termination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "active-planning-session-cleanup"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            first._planning_stage_status = "active"
            operation_id = first._begin_registration_intent(node="planning")
            registration = aegis_runtime.TraceRelayRegistration(
                session_id="checkpointed-planning-session",
                proxy_host="127.0.0.1",
                proxy_port=45_000,
                upstream_port=7_899,
                session_path=root / "sessions" / "checkpointed-planning-session",
                operation_id=operation_id,
            )
            first._persist_registration_result(
                registration,
                None,
                node="planning",
            )
            first._close_run_wide_freeze()
            first._release_project_lease()
            prior = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertIsNone(prior["registration_intent"])
            self.assertEqual(
                prior["evidence_sessions"][0]["verification_status"],
                "UNVERIFIED",
            )

            relay = RegistrationIntentRecoveryRelay(registration)
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7_899,
                relay_client=relay,
                start_node="A",
                prior_state=prior,
            )
            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )
            self.assertIsNone(saved["registration_intent"])
            evidence = saved["evidence_sessions"][0]
            self.assertEqual(evidence["session_id"], registration.session_id)
            self.assertEqual(evidence["verification_status"], "VALID_COMPLETE")
            self.assertEqual(evidence["application_verification_status"], "INVALID")
            self.assertEqual(relay.resolve_count, 1)
            self.assertEqual(relay.recover_count, 1)
            self.assertFalse(relay.started)

    def test_continuity_loss_persistence_failure_cannot_downgrade_to_failed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            run_id = "continuity-loss-persist-retry"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            first._close_run_wide_freeze()
            first._release_project_lease()
            prior = aegis_runtime.load_run_state(artifact_path, run_id)
            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=prior,
            )
            persist = resumed._persist_authoritative_state
            attempted_statuses: list[str] = []

            def fail_first_termination(
                status: str,
                error: BaseException | None,
                *,
                projection_best_effort: bool = False,
            ) -> None:
                attempted_statuses.append(status)
                if len(attempted_statuses) == 1:
                    raise aegis_runtime.RuntimeStateError(
                        "injected continuity termination CAS failure"
                    )
                persist(
                    status,
                    error,
                    projection_best_effort=projection_best_effort,
                )

            with (
                patch.object(
                    resumed,
                    "_persist_authoritative_state",
                    side_effect=fail_first_termination,
                ),
                self.assertRaises(aegis_runtime.FreezeContinuityLostError),
            ):
                resumed.preflight()

            saved = aegis_runtime.load_run_state(artifact_path, run_id)
            self.assertEqual(attempted_statuses, ["terminated", "terminated"])
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )

    def test_terminal_recovery_drain_mutation_is_durably_accounted(self) -> None:
        for provisional_status in ("terminal_finalizing", "terminal_committed"):
            with (
                self.subTest(provisional_status=provisional_status),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                artifact_path = root / "artifacts"
                run_id = f"recovery-drain-mutation-{provisional_status}"
                first = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                )
                first.preflight()
                first._terminal_target_status = (
                    "completed"
                    if provisional_status == "terminal_finalizing"
                    else "failed"
                )
                provisional = first._build_state_payload(provisional_status)
                encoded = aegis_runtime._canonical_json_bytes(provisional)
                first._close_run_wide_freeze()
                first._release_project_lease()
                aegis_runtime._update_run_reservation_state(
                    first.runtime_root,
                    first.artifact_path,
                    run_id,
                    str(provisional["reservation_token"]),
                    status=provisional_status,
                    encoded_state=encoded,
                    expected_state_sha256=first._authoritative_state_sha256,
                    expected_state_status=first._authoritative_state_status,
                )
                aegis_runtime._atomic_write_bytes(first.run_state_path, encoded)
                resumed = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                    prior_state=dict(provisional),
                )
                recovery_mutation = aegis_runtime.FrozenInputMutationError(
                    "mutation observed while draining recovery watcher",
                    mutation_event={"path": str(project / ".git" / "HEAD")},
                )
                with patch.object(
                    resumed,
                    "_finalize_run_wide_freeze",
                    side_effect=recovery_mutation,
                ):
                    resumed.preflight()

                saved = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(saved["status"], "terminated")
                self.assertEqual(
                    saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
                )
                self.assertEqual(
                    saved["master_review_status"], "REQUIRES_USER_REASON"
                )

    def test_execution_response_output_artifact_contract_rejects_bad_descriptors(
        self,
    ) -> None:
        variants = (
            ("missing", "output artifact IDs do not match"),
            ("duplicate", "duplicate output artifact IDs"),
            ("wrong-id", "output artifact IDs do not match"),
            ("wrong-path", "output artifact path changed"),
            ("wrong-size", "does not match its GPT response"),
            ("wrong-hash", "does not match its GPT response"),
        )
        for variant, expected_error in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = self.make_sealed_project(root)
                artifact_path = root / "artifacts"
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=f"bad-output-{variant}",
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                )
                coordinator.preflight()
                source = artifact_path / "TEST_REPORT.md"
                source.write_text("# Test report\n", encoding="utf-8")
                instruction = artifact_path / "instruction-receipts" / "test.json"
                instruction.parent.mkdir(parents=True, exist_ok=True)
                instruction.write_text("{}", encoding="utf-8")
                content = source.read_bytes()
                good = {
                    "artifact_id": "test-report",
                    "path": str(source.resolve()),
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                outputs = [dict(good)]
                if variant == "missing":
                    outputs = []
                elif variant == "duplicate":
                    outputs.append(dict(good))
                elif variant == "wrong-id":
                    outputs[0]["artifact_id"] = "other"
                elif variant == "wrong-path":
                    outputs[0]["path"] = str((artifact_path / "OTHER.md").resolve())
                elif variant == "wrong-size":
                    outputs[0]["size"] = len(content) + 1
                elif variant == "wrong-hash":
                    outputs[0]["sha256"] = "0" * 64
                receipt = {
                    "attempt_id": "attempt-0001",
                    "node": "E",
                    "codex_thread_id": "thread-1",
                    "codex_turn_id": "turn-1",
                    "instruction_receipt_path": str(instruction.resolve()),
                }
                result = SimpleNamespace(
                    status="completed",
                    thread_id="thread-1",
                    turn_id="turn-1",
                    final_message=json.dumps(
                        {"output_artifacts": outputs, "status": True}
                    ),
                )
                coordinator._active_node_output_watcher = coordinator._run_watchers[0]
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError, expected_error
                ):
                    coordinator._complete_execution_turn(receipt, result)

    def test_graph_output_artifacts_must_equal_persisted_gpt_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifact_path = root / "artifacts"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="graph-output-mismatch",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            source = artifact_path / "TEST_REPORT.md"
            source.write_text("# Test report\n", encoding="utf-8")
            content = source.read_bytes()
            outputs = [
                {
                    "artifact_id": "test-report",
                    "path": str(source.resolve()),
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ]
            response = artifact_path / "responses" / "execution.json"
            response.parent.mkdir(parents=True, exist_ok=True)
            response.write_text(
                json.dumps({"output_artifacts": outputs, "status": True}),
                encoding="utf-8",
            )
            instruction = artifact_path / "instruction-receipts" / "test.json"
            instruction.parent.mkdir(parents=True, exist_ok=True)
            instruction.write_text("{}", encoding="utf-8")
            coordinator._execution_turns.append(
                {
                    "job_id": "job-1",
                    "status": "completed",
                    "raw_response_path": str(response.resolve()),
                    "raw_response_sha256": hashlib.sha256(
                        response.read_text(encoding="utf-8").encode("utf-8")
                    ).hexdigest(),
                    "instruction_receipt_path": str(instruction.resolve()),
                }
            )
            attempt = {
                "attempt_id": "attempt-0001",
                "job_id": "job-1",
                "node": "E",
            }
            with (
                patch.object(
                    coordinator,
                    "_read_completed_execution_response",
                    return_value=response.read_text(encoding="utf-8"),
                ),
                self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "graph output artifacts differ from the persisted GPT response",
                ),
            ):
                coordinator._seal_execution_role_outputs(
                    attempt,
                    {"output_artifacts": []},
                    coordinator._run_watchers[0],
                )

    def test_execution_route_rejects_skips_failed_d_to_e_and_repeated_nodes(
        self,
    ) -> None:
        invalid_paths = (
            [{"node": "F", "status": "completed", "node_status": True}],
            [
                {"node": "C", "status": "completed", "node_status": True},
                {"node": "D", "status": "completed", "node_status": False},
                {"node": "E", "status": "completed", "node_status": True},
            ],
            [
                {"node": "C", "status": "completed", "node_status": True},
                {"node": "C", "status": "completed", "node_status": True},
            ],
        )
        for attempts in invalid_paths:
            with self.subTest(nodes=[attempt["node"] for attempt in attempts]):
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "violate the Coordinator-owned C-F route",
                ):
                    aegis_runtime._validate_execution_path(attempts)

    def test_c_cannot_complete_without_a_valid_test_evidence_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-missing-test-evidence",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            artifacts = root / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            coordinator._engineering_input_source_path = (
                self.write_engineering_input_manifest(project)
            )
            coordinator._snapshot_engineering_inputs()
            self.approve_planning_round(coordinator, artifacts)
            self.attach_planning_evidence_process(
                coordinator,
                root,
                session_id="missing-evidence-planning-session",
            )
            coordinator.complete_planning_stage()
            (artifacts / "TEST_EXECUTION_REQUEST.json").write_text(
                "{}\n", encoding="utf-8"
            )
            harness.current_node = "C"
            harness.current_artifact_path = artifacts

            def operation(state: dict[str, object]) -> dict[str, object]:
                response = coordinator.run_execution_agent(
                    "TEST_EXECUTOR",
                    "C prompt",
                    output_schema={"type": "object"},
                    developer_instructions="persistent TEST_EXECUTOR",
                    timeout_seconds=5,
                )
                return {
                    **state,
                    **json.loads(response),
                    "response": response,
                    "current_node": "C",
                }

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
                self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "invalid test execution request",
                ),
            ):
                coordinator.execute_node("C", operation, {"status": True})

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "execution-missing-test-evidence"
            )
            self.assertEqual(saved["status"], "failed")

    def test_runtime_input_mutation_terminates_and_requires_user_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="frozen-input-mutation",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            def mutate(state: dict[str, object]) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "frozen project inputs changed; the run is terminated and "
                    "requires the user to provide a reason",
                    mutation_event={
                        "path": str(project / "src" / "module.py")
                    },
                )

            with self.assertRaisesRegex(
                aegis_runtime.FrozenInputMutationError,
                "requires the user to provide a reason",
            ):
                coordinator.execute_node("A", mutate, {"status": True})

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "frozen-input-mutation"
            )
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )

    def test_git_metadata_modify_then_restore_is_a_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="git-metadata-restored",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            git_head = project / ".git" / "HEAD"
            original = git_head.read_bytes()

            def mutate_and_restore(state: dict[str, object]) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic Git metadata modify-restore",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(git_head.resolve()),
                                "source": "git_metadata",
                                "observed_actions": ["modified"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                coordinator.execute_node("A", mutate_and_restore, {"status": True})

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "git-metadata-restored"
            )
            changes = saved["mutation_event"]["changes"]
            self.assertTrue(
                any(
                    change["path"] == str(git_head.resolve())
                    and change["source"] == "git_metadata"
                    for change in changes
                )
            )

    def test_project_seal_record_modify_then_restore_is_a_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="seal-record-restored",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            seal_record = project / project_seal_store.SEAL_RECORD_RELATIVE_PATH
            original = seal_record.read_bytes()

            def mutate_and_restore(state: dict[str, object]) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic Project Seal modify-restore",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(seal_record.resolve()),
                                "source": "project_seal_record",
                                "observed_actions": ["modified"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                coordinator.execute_node("A", mutate_and_restore, {"status": True})

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "seal-record-restored"
            )
            changes = saved["mutation_event"]["changes"]
            self.assertTrue(
                any(
                    change["path"] == str(seal_record.resolve())
                    and change["source"] == "project_seal_record"
                    for change in changes
                )
            )

    def test_watcher_startup_failure_preserves_earlier_mutation_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            source = project / "src" / "module.py"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="watcher-startup-mutation",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            operation_called = False

            class FailingSecondWatcher:
                instances = 0

                def __init__(self, watch_root: Path) -> None:
                    type(self).instances += 1
                    self.index = type(self).instances
                    self.root = Path(watch_root).resolve()
                    self.listening = False

                def start(self) -> None:
                    if self.index == 2:
                        raise RuntimeError("synthetic second watcher failure")
                    self.listening = True

                def stop(self) -> tuple[aegis_runtime.FileSystemEvent, ...]:
                    self.listening = False
                    if self.index == 1:
                        return (
                            aegis_runtime.FileSystemEvent(
                                "modified", source.resolve()
                            ),
                        )
                    return ()

                def events(self) -> tuple[aegis_runtime.FileSystemEvent, ...]:
                    return ()

            def operation(state: dict[str, object]) -> dict[str, object]:
                nonlocal operation_called
                operation_called = True
                return state

            with (
                patch.object(aegis_runtime, "FrozenInputWatcher", FailingSecondWatcher),
                self.assertRaises(aegis_runtime.FrozenInputMutationError),
            ):
                coordinator.execute_node("A", operation, {"status": True})

            self.assertFalse(operation_called)
            saved = aegis_runtime.load_run_state(
                root / "artifacts", "watcher-startup-mutation"
            )
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["master_review_status"], "REQUIRES_USER_REASON"
            )
            self.assertEqual(
                saved["master_review_status"], "REQUIRES_USER_REASON"
            )
            self.assertEqual(saved["engineering_verdict"], "INVALIDATED")
            event = saved["mutation_event"]
            self.assertEqual(event["attribution_status"], "UNATTRIBUTED")
            self.assertTrue(
                any(
                    change["path"].endswith("src\\module.py")
                    for change in event["changes"]
                )
            )

    def test_watcher_stop_error_does_not_hide_other_mutation_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            source = project / "src" / "module.py"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="watcher-stop-mutation",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            class FailingStopWatcher:
                instances = 0

                def __init__(self, watch_root: Path) -> None:
                    type(self).instances += 1
                    self.index = type(self).instances
                    self.root = Path(watch_root).resolve()
                    self.listening = False

                def start(self) -> None:
                    self.listening = True

                def stop(self) -> tuple[aegis_runtime.FileSystemEvent, ...]:
                    self.listening = False
                    if self.index == 2:
                        raise RuntimeError("synthetic watcher stop failure")
                    return ()

                def events(self) -> tuple[aegis_runtime.FileSystemEvent, ...]:
                    if self.index == 2:
                        return (
                            aegis_runtime.FileSystemEvent(
                                "modified", source.resolve()
                            ),
                        )
                    return ()

                def lock_files(self, paths: object) -> None:
                    del paths

            with (
                patch.object(aegis_runtime, "FrozenInputWatcher", FailingStopWatcher),
                self.assertRaises(aegis_runtime.FrozenInputMutationError),
            ):
                coordinator.execute_node("A", lambda state: state, {"status": True})

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "watcher-stop-mutation"
            )
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["master_review_status"], "REQUIRES_USER_REASON"
            )

    def test_primary_mutation_outranks_watcher_stop_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="primary-mutation-watcher-error",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            class StopErrorWatcher:
                def __init__(self, watch_root: Path) -> None:
                    self.root = Path(watch_root).resolve()
                    self.listening = False

                def start(self) -> None:
                    self.listening = True

                def stop(self) -> tuple[aegis_runtime.FileSystemEvent, ...]:
                    self.listening = False
                    raise RuntimeError("synthetic watcher stop failure")

                def events(self) -> tuple[aegis_runtime.FileSystemEvent, ...]:
                    return ()

                def lock_files(self, paths: object) -> None:
                    del paths

            def operation(_state: dict[str, object]) -> dict[str, object]:
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic trusted-operation mutation"
                )

            with (
                patch.object(aegis_runtime, "FrozenInputWatcher", StopErrorWatcher),
                self.assertRaises(aegis_runtime.FrozenInputMutationError),
            ):
                coordinator.execute_node("A", operation, {"status": True})

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "primary-mutation-watcher-error"
            )
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["master_review_status"], "REQUIRES_USER_REASON"
            )

    @unittest.skipUnless(sys.platform == "win32", "requires Windows change journal")
    def test_coordinator_prevents_test_from_mutating_locked_runtime_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            artifacts = root / "artifacts"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifacts,
                run_id="execution-test-mutates-runtime",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="C",
            )
            coordinator.preflight()
            request_path = write_test_execution_request(
                project,
                artifacts,
                project_id_hex=bytes(range(16)).hex(),
                workflow_run_id=coordinator.run_id,
                attempt_id="attempt-0001",
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))
            source = project / "src" / "module.py"
            mutation_script = artifacts / "test_demos" / "mutate_runtime.py"
            mutation_script.write_text(
                "from pathlib import Path\n"
                "import time\n"
                f"Path({str(source)!r}).write_text('VALUE = 2\\n', encoding='utf-8')\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            mutation_bytes = mutation_script.read_bytes()
            request["tests"][0]["command"] = [
                str(Path(sys._base_executable).resolve()),
                str(mutation_script.resolve()),
            ]
            request["tests"][0]["test_inputs"].append(
                {
                    "path": str(mutation_script.resolve()),
                    "size": len(mutation_bytes),
                    "sha256": hashlib.sha256(mutation_bytes).hexdigest(),
                }
            )
            manifest_path = artifacts / "evidence-manifests" / "attempt-0001.json"
            manifest_path.parent.mkdir(parents=True)
            started = time.monotonic()
            coordinator._execute_test_request(
                request,
                request_sha256=hashlib.sha256(
                    request_path.read_bytes()
                ).hexdigest(),
                execution_policy_sha256="a" * 64,
                session_ids=["execution-session-mutation"],
                manifest_path=manifest_path,
            )
            self.assertLess(time.monotonic() - started, 5)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotEqual(manifest["records"][0]["exit_code"], 0)
            self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 1\n")

    def test_modify_then_restore_during_node_is_still_a_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            source = project / "src" / "module.py"
            original = source.read_bytes()
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="frozen-input-restored",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()

            def mutate_and_restore(state: dict[str, object]) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic runtime input modify-restore",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(source.resolve()),
                                "source": "runtime_scope",
                                "observed_actions": ["modified"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                coordinator.execute_node(
                    "A", mutate_and_restore, {"status": True}
                )

            self.assertEqual(source.read_bytes(), original)
            saved = aegis_runtime.load_run_state(
                root / "artifacts", "frozen-input-restored"
            )
            changes = saved["mutation_event"]["changes"]
            change = next(
                item for item in changes if item["path"].endswith("src\\module.py")
            )
            self.assertIn("modified", change["observed_actions"])

    def test_new_run_is_blocked_until_mutation_reason_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            runtime_root = root / "runtime"
            mutated = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "mutated" / "artifacts",
                runtime_root=runtime_root,
                run_id="mutated",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            mutated.preflight()
            source = project / "src" / "module.py"
            original = source.read_bytes()

            def mutate_and_restore(state: dict[str, object]) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic accountable mutation",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(source.resolve()),
                                "source": "runtime_scope",
                                "observed_actions": ["modified"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                mutated.execute_node("A", mutate_and_restore, {"status": True})
            mutated.run_state_path.unlink()
            blocked = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "new-one" / "artifacts",
                runtime_root=runtime_root,
                run_id="new-one",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "requires a recorded user reason",
            ):
                blocked.preflight()
            rebuilt = aegis_runtime.load_run_state(runtime_root, "mutated")
            self.assertEqual(
                rebuilt["master_review_status"], "REQUIRES_USER_REASON"
            )
            self.assertTrue(mutated.run_state_path.is_file())

            reason = root / "reason.md"
            reason.write_text("The user changed the implementation plan.\n", encoding="utf-8")
            record_frozen_input_mutation_reason(
                runtime_root,
                "mutated",
                reason_path=reason,
                user_confirmation_id="confirmation-1",
            )
            recorded = aegis_runtime.load_run_state(runtime_root, "mutated")
            record_path = Path(str(recorded["mutation_reason_record"]["path"]))
            record_bytes = record_path.read_bytes()
            sealed_reason_path = (
                mutated.artifact_path / "FROZEN_INPUT_MUTATION_REASON.md"
            )
            sealed_reason_bytes = sealed_reason_path.read_bytes()

            record_path.unlink()
            missing_evidence = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=(
                    runtime_root / "runs" / "missing-reason-record" / "artifacts"
                ),
                runtime_root=runtime_root,
                run_id="missing-reason-record",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            with self.assertRaisesRegex(
                aegis_runtime.FrozenInputMutationError,
                "sealed project mutation-accountability evidence changed",
            ):
                missing_evidence.preflight()
            record_path.write_bytes(record_bytes)

            sealed_reason_path.write_text("rewritten reason\n", encoding="utf-8")
            changed_evidence = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=(
                    runtime_root / "runs" / "changed-reason" / "artifacts"
                ),
                runtime_root=runtime_root,
                run_id="changed-reason",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            with self.assertRaisesRegex(
                aegis_runtime.FrozenInputMutationError,
                "sealed project mutation-accountability evidence changed",
            ):
                changed_evidence.preflight()
            sealed_reason_path.write_bytes(sealed_reason_bytes)

            allowed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "new-two" / "artifacts",
                runtime_root=runtime_root,
                run_id="new-two",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            allowed.preflight()
            self.assertTrue(allowed.run_state_path.is_file())

            def attempt_delete_accountability(
                state: dict[str, object],
            ) -> dict[str, object]:
                record_path.unlink()
                return {**state, "current_node": "A"}

            with self.assertRaises(PermissionError):
                allowed.execute_node(
                    "A", attempt_delete_accountability, {"status": True}
                )
            self.assertEqual(record_path.read_bytes(), record_bytes)
            failed = aegis_runtime.load_run_state(runtime_root, "new-two")
            self.assertEqual(failed["status"], "failed")

    def test_deleting_authoritative_database_cannot_reset_project_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            runtime_root = root / "runtime"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "first" / "artifacts",
                runtime_root=runtime_root,
                run_id="first",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            first.preflight()
            first.fail(RuntimeError("synthetic terminal state"))
            database = runtime_root / aegis_runtime.CHECKPOINT_RELATIVE_PATH
            anchor = runtime_root / aegis_runtime.RUNTIME_AUTHORITY_RELATIVE_PATH
            self.assertTrue(database.is_file())
            self.assertTrue(anchor.is_file())
            database.unlink()

            second = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=runtime_root / "runs" / "second" / "artifacts",
                runtime_root=runtime_root,
                run_id="second",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "anchor/database pair is incomplete",
            ):
                second.preflight()

    def test_complete_requires_terminal_f_attempt_and_terminates_false_verdict(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-terminal-binding",
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
                before_f = self.run_execution_through(
                    coordinator,
                    "E",
                    {"status": True},
                )
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "terminal F node",
                ):
                    coordinator.complete(
                        {**before_f, "status": True, "current_node": "F"}
                    )
                final = self.run_execution_node(
                    coordinator,
                    "F",
                    "FINAL_REVIEWER",
                    before_f,
                    result_status=False,
                )
            coordinator.complete(final)

            completed = aegis_runtime.load_run_state(
                root / "artifacts", "execution-terminal-binding"
            )
            self.assertEqual(completed["status"], "terminated")
            self.assertIs(completed["graph_state"]["status"], False)
            self.assertEqual(completed["workflow_state"], "TERMINATED")
            self.assertEqual(completed["engineering_verdict"], "FAIL")
            self.assertFalse(completed["delivery_eligible"])
            self.assertEqual(completed["master_review_status"], "PENDING")

    def test_f_cannot_complete_without_structured_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="missing-final-verdict",
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
                before_f = self.run_execution_through(
                    coordinator,
                    "E",
                    {"status": True},
                )
            attempt = coordinator._begin_execution_attempt("F", before_f)
            coordinator._prepare_final_review_input_manifest(attempt)
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "F produced an invalid verdict",
            ):
                coordinator._seal_final_review_verdict(attempt, before_f)

    def test_f_manifest_requires_planning_turns_and_all_same_kind_documents(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            engineering_manifest_path = self.write_engineering_input_manifest(project)
            second_requirements = project / "docs" / "REQUIREMENTS_SECOND.md"
            second_requirements.write_text("second requirement\n", encoding="utf-8")
            engineering_manifest = json.loads(
                engineering_manifest_path.read_text(encoding="utf-8")
            )
            second_bytes = second_requirements.read_bytes()
            engineering_manifest["documents"].append(
                {
                    "kind": "REQUIREMENTS",
                    "path": str(second_requirements.resolve()),
                    "size": len(second_bytes),
                    "sha256": hashlib.sha256(second_bytes).hexdigest(),
                }
            )
            engineering_manifest_path.write_text(
                json.dumps(engineering_manifest), encoding="utf-8"
            )
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="complete-final-inputs",
                upstream_port=7899,
                relay_client=ExecutionRelayClient(harness),
                start_node="C",
            )
            coordinator.preflight()
            coordinator._engineering_input_source_path = engineering_manifest_path
            coordinator._snapshot_engineering_inputs()
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
                before_f = self.run_execution_through(
                    coordinator, "E", {"status": True}
                )

            attempt = coordinator._begin_execution_attempt("F", before_f)
            coordinator._prepare_final_review_input_manifest(attempt)
            manifest = json.loads(
                Path(str(attempt["final_review_input_manifest_path"])).read_text(
                    encoding="utf-8"
                )
            )
            required_ids = [
                item["evidence_id"] for item in manifest["required_evidence"]
            ]
            requirement_ids = [
                item
                for item in required_ids
                if item.startswith("engineering-input:requirements:")
            ]
            self.assertEqual(len(requirement_ids), 2)
            self.assertEqual(len(set(requirement_ids)), 2)
            self.assertIn("planning-response:0001", required_ids)
            self.assertIn("planning-response:0002", required_ids)
            self.assertIn("planning-instruction-receipt:0001", required_ids)
            self.assertIn("planning-instruction-receipt:0002", required_ids)
            self.assertEqual(len(manifest["planning"]["turns"]), 2)

    def test_f_required_evidence_modify_then_restore_is_a_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="final-required-evidence-restored",
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
                before_f = self.run_execution_through(
                    coordinator, "E", {"status": True}
                )
            report = coordinator.artifact_path / "TEST_REPORT.md"
            original = report.read_bytes()

            def report_mutation(
                state: dict[str, object],
            ) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic F required-evidence mutation",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(report.resolve()),
                                "source": "final_review_required_evidence",
                                "observed_actions": ["modified"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                coordinator.execute_node("F", report_mutation, before_f)

            self.assertEqual(report.read_bytes(), original)
            saved = aegis_runtime.load_run_state(
                root / "artifacts", "final-required-evidence-restored"
            )
            changed_paths = {
                item["path"] for item in saved["mutation_event"]["changes"]
            }
            self.assertIn(str(report.resolve()), changed_paths)

    def test_change_before_watcher_ready_is_caught_by_post_arm_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            source = project / "src" / "module.py"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="watcher-arm-gap",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
            )
            coordinator.preflight()
            coordinator._close_run_wide_freeze()
            operation_called = False

            class MutatingBeforeReadyWatcher:
                mutated = False

                def __init__(self, watch_root: Path) -> None:
                    self.root = Path(watch_root).resolve()
                    self.listening = False

                def start(self) -> None:
                    if self.root == project.resolve() and not type(self).mutated:
                        source.write_text("VALUE = 2\n", encoding="utf-8")
                        type(self).mutated = True
                    self.listening = True

                def stop(self) -> tuple[object, ...]:
                    self.listening = False
                    return ()

                def lock_files(self, paths: object) -> None:
                    del paths

                def events(self) -> tuple[object, ...]:
                    return ()

            def operation(state: dict[str, object]) -> dict[str, object]:
                nonlocal operation_called
                operation_called = True
                return state

            with (
                patch.object(
                    aegis_runtime, "FrozenInputWatcher", MutatingBeforeReadyWatcher
                ),
                self.assertRaises(aegis_runtime.FrozenInputMutationError),
            ):
                coordinator.execute_node("A", operation, {"status": True})

            self.assertFalse(operation_called)
            saved = aegis_runtime.load_run_state(
                root / "artifacts", "watcher-arm-gap"
            )
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )

    def test_f_required_evidence_parent_rename_is_a_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="final-required-parent-renamed",
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
                before_f = self.run_execution_through(
                    coordinator, "E", {"status": True}
                )
            assert coordinator._engineering_input_manifest is not None
            documents = coordinator._engineering_input_manifest["documents"]
            assert isinstance(documents, list) and documents
            snapshot = Path(str(documents[0]["snapshot_path"]))
            frozen_parent = snapshot.parent

            def parent_rename_mutation(
                state: dict[str, object],
            ) -> dict[str, object]:
                del state
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic F required-evidence parent rename",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(frozen_parent.resolve()),
                                "source": "final_review_required_evidence_ancestor",
                                "observed_actions": ["renamed_from", "renamed_to"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                coordinator.execute_node("F", parent_rename_mutation, before_f)

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "final-required-parent-renamed"
            )
            parent_change = next(
                item
                for item in saved["mutation_event"]["changes"]
                if item["path"] == str(frozen_parent.resolve())
            )
            self.assertTrue(
                {"renamed_from", "renamed_to"}
                & set(parent_change["observed_actions"])
            )

    def test_f_manifest_mutation_with_operation_error_still_records_accountability(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="final-manifest-error-mutation",
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
                before_f = self.run_execution_through(
                    coordinator, "E", {"status": True}
                )

            def manifest_mutation(
                _state: dict[str, object],
            ) -> dict[str, object]:
                manifest = (
                    coordinator.artifact_path
                    / "FINAL_REVIEW_INPUT_MANIFEST.json"
                )
                raise aegis_runtime.FrozenInputMutationError(
                    "synthetic F manifest mutation",
                    mutation_event={
                        "changes": [
                            {
                                "path": str(manifest.resolve()),
                                "source": "final_review_input_manifest",
                                "observed_actions": ["modified"],
                            }
                        ]
                    },
                )

            with self.assertRaises(aegis_runtime.FrozenInputMutationError):
                coordinator.execute_node("F", manifest_mutation, before_f)

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "final-manifest-error-mutation"
            )
            self.assertEqual(saved["status"], "terminated")
            self.assertEqual(
                saved["termination_reason_code"], "FROZEN_INPUT_MUTATION"
            )
            self.assertEqual(
                saved["master_review_status"], "REQUIRES_USER_REASON"
            )

    def test_complete_terminates_at_failed_report_without_running_f(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            harness = ExecutionTurnHarness(root)
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="execution-report-failed",
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
                report = self.run_execution_through(
                    coordinator,
                    "E",
                    {"status": True},
                    target_status=False,
                )

            coordinator.complete(report)
            terminated = aegis_runtime.load_run_state(
                root / "artifacts", "execution-report-failed"
            )
            self.assertEqual(terminated["status"], "terminated")
            self.assertEqual(terminated["last_completed_node"], "E")
            self.assertEqual(terminated["workflow_state"], "TERMINATED")
            self.assertEqual(terminated["engineering_verdict"], "INCOMPLETE")
            self.assertEqual(terminated["master_review_status"], "NOT_REQUIRED")

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
                coordinator._write_state(
                    "failed", RuntimeError("orderly node checkpoint gap")
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

    def test_d_creates_an_independent_reviewer_thread_after_c(self) -> None:
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
                c_result = self.run_execution_node(
                    coordinator,
                    "C",
                    "TEST_EXECUTOR",
                    {"status": True},
                )
                self.run_execution_node(
                    coordinator,
                    "D",
                    "TEST_RESULT_REVIEWER",
                    c_result,
                )

            saved = aegis_runtime.load_run_state(
                root / "artifacts", "execution-start-d"
            )
            self.assertEqual(
                list(saved["execution_agents"]),
                ["TEST_EXECUTOR", "TEST_RESULT_REVIEWER"],
            )
            self.assertEqual(
                [item["node"] for item in saved["execution_attempts"]],
                ["C", "D"],
            )
            self.assertTrue(
                all(item["status"] == "completed" for item in saved["execution_turns"])
            )
            self.assertEqual(harness.open_count, 2)

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

            coordinator._write_state(
                "failed", RuntimeError("orderly response validation boundary")
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
                aegis_runtime.FrozenInputMutationError,
                "frozen file changed before listener arming",
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
                execution_evidence = next(
                    entry
                    for entry in saved["evidence_sessions"]
                    if entry["node"] == "C"
                )
                self.assertEqual(
                    execution_evidence["verification_status"],
                    "VALID_COMPLETE",
                )
                self.assertEqual(
                    execution_evidence["application_verification_status"],
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
                saved_evidence = next(
                    entry
                    for entry in saved["evidence_sessions"]
                    if entry["node"] == "C"
                )
                saved_evidence.update(
                    verification_status="UNVERIFIED",
                    application_verification_status=None,
                    final_hash=None,
                )
                encoded_saved = aegis_runtime._canonical_json_bytes(saved)
                coordinator.run_state_path.write_bytes(encoded_saved)
                aegis_runtime._update_run_reservation_state(
                    coordinator.runtime_root,
                    coordinator.artifact_path,
                    coordinator.run_id,
                    str(saved["reservation_token"]),
                    status=str(saved["status"]),
                    encoded_state=encoded_saved,
                    expected_state_sha256=coordinator._authoritative_state_sha256,
                    expected_state_status=str(saved["status"]),
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

            coordinator._write_state(
                "failed", RuntimeError("orderly journal revalidation boundary")
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
                    coordinator,
                    "C",
                    "TEST_EXECUTOR",
                    {"status": True},
                )

            coordinator._write_state(
                "failed", RuntimeError("orderly journal hash validation boundary")
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
                start_node="C",
                prior_state=saved,
            )
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "final hash mismatch"
            ):
                resumed.preflight()

            missing_identity = json.loads(json.dumps(saved))
            next(
                entry
                for entry in missing_identity["evidence_sessions"]
                if entry["node"] == "C"
            ).pop("process_creation_time_100ns")
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "creation time"
            ):
                aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=root / "artifacts",
                    run_id="execution-journal-hash",
                    upstream_port=7899,
                    relay_client=ExecutionRelayClient(harness),
                    start_node="C",
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
                start_node="C",
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
                        coordinator, "C", "TEST_EXECUTOR", state
                    )
                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "thread allocation outcome is unknown",
                ):
                    self.run_execution_node(
                        coordinator, "C", "TEST_EXECUTOR", state
                    )

            self.assertEqual(harness.open_count, 1)
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["execution_agents"]["TEST_EXECUTOR"]["status"],
                "allocating",
            )

    def test_planning_roles_share_one_traced_app_server_and_persist_turn_receipts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
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
                    del args
                    operation_id = kwargs.pop("registration_operation_id")
                    assert isinstance(operation_id, str)
                    del kwargs
                    self.open_count += 1
                    self.managed.registration = aegis_runtime.TraceRelayRegistration(
                        session_id=self.managed.registration.session_id,
                        proxy_host=self.managed.registration.proxy_host,
                        proxy_port=self.managed.registration.proxy_port,
                        upstream_port=self.managed.registration.upstream_port,
                        session_path=self.managed.registration.session_path,
                        operation_id=operation_id,
                    )
                    self.last_registration = self.managed.registration
                    return self.managed

            class FakeAppServer:
                def __init__(self, **kwargs: Any) -> None:
                    self.process_factory = kwargs["process_factory"]
                    self.process: ManagedProcess | None = None
                    self.thread_index = 0
                    self.turn_index = 0
                    self.instruction_receipts: dict[
                        str, tuple[Path, bytes]
                    ] = {}

                def start(self) -> None:
                    self.process = self.process_factory(["codex", "app-server"])

                def close(self) -> None:
                    assert self.process is not None
                    self.process.terminate()
                    self.process.wait(timeout=1)

                def start_thread(self, **kwargs: Any) -> SimpleNamespace:
                    self.thread_index += 1
                    thread_id = f"planning-thread-{self.thread_index}"
                    instructions = str(kwargs.get("developer_instructions", ""))
                    marker = (
                        "Before every role task, atomically write the exact UTF-8 "
                        "JSON below to `"
                    )
                    start = instructions.find(marker)
                    if start >= 0:
                        path_start = start + len(marker)
                        path_end = instructions.index("`", path_start)
                        json_start = instructions.index(
                            "```json\n", path_end
                        ) + len("```json\n")
                        json_end = instructions.index("\n```", json_start)
                        self.instruction_receipts[thread_id] = (
                            Path(instructions[path_start:path_end]),
                            instructions[json_start:json_end].encode("utf-8"),
                        )
                    return SimpleNamespace(
                        thread_id=thread_id,
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
                    receipt = self.instruction_receipts.get(thread_id)
                    if receipt is not None:
                        path, encoded = receipt
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(encoded)
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
                artifact_path=artifact_path,
                run_id="planning-run",
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            coordinator.preflight()
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
                        self.planning_review_result(
                            coordinator,
                            review_control,
                            reviewed_plan_sha256=str(frozen["plan_sha256"]),
                            score=95,
                            error_count=0,
                            warning_count=0,
                            review_conclusion="PASS",
                        ),
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
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-handoff",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
            self.assertNotIn("finding_categories", review["instructions"])
            self.assertIn("derives finding categories", review["instructions"])
            first_report = Path(str(review["review_report_path"]))
            first_report.write_text(
                "# Review\n\nOne blocking issue.\n", encoding="utf-8"
            )
            accepted = coordinator.record_planning_review(
                "round-0001",
                self.planning_review_result(
                    coordinator,
                    review,
                    reviewed_plan_sha256=str(frozen["plan_sha256"]),
                    score=94,
                    error_count=1,
                    warning_count=0,
                    review_conclusion="FAIL",
                    semantic_issues=[
                        {
                            "semantic_issue_id": "issue-a-to-b-evidence",
                            "premises": ["A is asserted."],
                            "inference": "A is claimed to imply B.",
                            "conclusion": "B is required.",
                            "missing_evidence": ["Evidence connecting A to B."],
                            "alternative_explanations": ["C may also explain B."],
                            "closure_conditions": [
                                "Add evidence or narrow the conclusion."
                            ],
                        }
                    ],
                ),
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
                self.planning_review_result(
                    coordinator,
                    second_review,
                    reviewed_plan_sha256=str(second_frozen["plan_sha256"]),
                    score=95,
                    error_count=0,
                    warning_count=2,
                    review_conclusion="PASS",
                    prior_issue_assessments=[
                        {
                            "prior_semantic_issue_id": "issue-a-to-b-evidence",
                            "issue_status": "RESOLVED",
                            "current_semantic_issue_ids": [],
                            "rationale": "The revised plan adds the missing bridge.",
                            "evidence": ["TEST_PLAN.md section for A-to-B evidence"],
                        }
                    ],
                ),
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

    def test_planning_handoff_prevents_plan_change_after_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-tamper",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            coordinator.preflight()

            author = coordinator.prepare_planning_author(context_path)
            plan_path = Path(str(author["plan_path"]))
            plan_path.write_text("# Frozen\n", encoding="utf-8")
            coordinator.freeze_planning_plan("round-0001")
            with self.assertRaises(PermissionError):
                plan_path.write_text("# Changed\n", encoding="utf-8")

    def test_planning_review_rejects_changed_context_or_project_seal(self) -> None:
        for mutation in ("context", "project"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                project = self.make_sealed_project(root)
                manifest = self.write_engineering_input_manifest(project)
                artifact_path = root / "artifacts"
                artifact_path.mkdir()
                context_path = self.write_reasoning_context_pack(
                    project, root / "planning-context-source.json", manifest
                )
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=f"planning-{mutation}-tamper",
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                    engineering_input_manifest_path=manifest,
                )
                coordinator.preflight()
                author = coordinator.prepare_planning_author(context_path)
                Path(str(author["plan_path"])).write_text(
                    "# Frozen\n", encoding="utf-8"
                )
                coordinator.freeze_planning_plan("round-0001")
                with self.assertRaises(PermissionError):
                    if mutation == "context":
                        context_path.write_text(
                            '{"changed":true}\n', encoding="utf-8"
                        )
                    else:
                        (project / "src" / "module.py").write_text(
                            "VALUE = 2\n", encoding="utf-8"
                        )

    def test_rejected_review_cannot_be_changed_before_the_next_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-rejected-tamper",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
                    self.planning_review_result(
                        coordinator,
                        review,
                        reviewed_plan_sha256=str(frozen["plan_sha256"]),
                        score=90,
                        error_count=1,
                        warning_count=0,
                        review_conclusion="FAIL",
                        semantic_issues=[
                            {
                                "semantic_issue_id": "issue-a-to-b-evidence",
                                "premises": ["A is asserted."],
                                "inference": "A is claimed to imply B.",
                                "conclusion": "B is required.",
                                "missing_evidence": ["Evidence connecting A to B."],
                                "alternative_explanations": ["C may also explain B."],
                                "closure_conditions": [
                                    "Add evidence or narrow the conclusion."
                                ],
                            }
                        ],
                    ),
                )
            )
            with self.assertRaises(PermissionError):
                report_path.write_text(
                    "# Rewritten rejection\n", encoding="utf-8"
                )

    def test_repeated_semantic_issue_is_persisted_as_unresolved_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            context = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifacts,
                run_id="repeated-semantic-refusal",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
            )
            coordinator.preflight()
            issue = {
                "semantic_issue_id": "issue-a-to-b-evidence",
                "premises": ["A is asserted."],
                "inference": "A is claimed to imply B.",
                "conclusion": "B is required.",
                "missing_evidence": ["Evidence connecting A to B."],
                "alternative_explanations": ["C may also explain B."],
                "closure_conditions": ["Add evidence or narrow the conclusion."],
            }

            for index in (1, 2):
                author = coordinator.prepare_planning_author(context)
                Path(str(author["plan_path"])).write_text(
                    "# Unchanged claim\n", encoding="utf-8"
                )
                frozen = coordinator.freeze_planning_plan(str(author["round_id"]))
                review = coordinator.prepare_planning_review()
                Path(str(review["review_report_path"])).write_text(
                    "# Same unresolved issue\n", encoding="utf-8"
                )
                reviewed_issue = dict(issue)
                if index == 2:
                    reviewed_issue.update(
                        semantic_issue_id="issue-renamed-with-same-logic",
                        inference="B is still inferred from A without a bridge.",
                        predecessor_issue_ids=["issue-a-to-b-evidence"],
                    )
                assessments = []
                if index == 2:
                    assessments = [
                        {
                            "prior_semantic_issue_id": "issue-a-to-b-evidence",
                            "issue_status": "REPEATED_UNRESOLVED",
                            "current_semantic_issue_ids": [
                                "issue-renamed-with-same-logic"
                            ],
                            "rationale": "The logical A-to-B gap remains unchanged.",
                            "evidence": ["TEST_PLAN.md repeats the unsupported inference"],
                        }
                    ]
                self.assertFalse(
                    coordinator.record_planning_review(
                        str(review["round_id"]),
                        self.planning_review_result(
                            coordinator,
                            review,
                            reviewed_plan_sha256=str(frozen["plan_sha256"]),
                            score=80,
                            error_count=1,
                            warning_count=0,
                            review_conclusion="FAIL",
                            semantic_issues=[reviewed_issue],
                            prior_issue_assessments=assessments,
                        ),
                    )
                )
                if index == 2:
                    self.assertEqual(
                        coordinator._planning_rounds[-1][
                            "repeated_unresolved_issue_ids"
                        ],
                        ["issue-renamed-with-same-logic"],
                    )

            saved = aegis_runtime.load_run_state(
                artifacts, "repeated-semantic-refusal"
            )
            self.assertEqual(
                saved["repeated_semantic_refusal_issue_ids"],
                ["issue-renamed-with-same-logic"],
            )

    def test_round_allocation_crash_terminates_when_freeze_continuity_is_lost(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-allocation-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()
            terminated = aegis_runtime.load_run_state(
                artifact_path, "planning-allocation-recovery"
            )
            self.assertEqual(terminated["status"], "terminated")
            self.assertEqual(
                terminated["termination_reason_code"], "FREEZE_CONTINUITY_LOST"
            )

    def test_completed_author_handoff_is_reused_without_a_new_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-author-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
            coordinator._compose_instruction_receipt_protocol(
                "TEST_PLAN_AUTHOR", "author"
            )
            receipt_spec = coordinator._instruction_receipt_specs["TEST_PLAN_AUTHOR"]
            receipt_path = Path(str(receipt_spec["path"]))
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(
                aegis_runtime._canonical_instruction_receipt_bytes(
                    receipt_spec["payload"]
                )
            )
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
                coordinator.artifact_path / "responses" / "saved.json"
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
            coordinator._compose_instruction_receipt_protocol(
                "TEST_PLAN_AUTHOR", "author"
            )
            receipt_spec = coordinator._instruction_receipt_specs["TEST_PLAN_AUTHOR"]
            receipt_path = Path(str(receipt_spec["path"]))
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(
                aegis_runtime._canonical_instruction_receipt_bytes(
                    receipt_spec["payload"]
                )
            )
            coordinator._seal_instruction_receipt(
                "TEST_PLAN_AUTHOR",
                "planning-completed-replay:round-0001:author",
                coordinator._planning_turns[0],
            )
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
            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                resumed.preflight()

            self.assertEqual(client.start_count, 1)
            persisted = json.loads(resumed.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "terminated")
            self.assertEqual(persisted["planning_turns"][0]["status"], "submitting")

    def test_interrupted_approval_publication_is_rebuilt_before_acceptance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            artifact_path.mkdir()
            context_path = self.write_reasoning_context_pack(
                project, root / "planning-context-source.json", manifest
            )
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-publish-recovery",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
                    self.planning_review_result(
                        first,
                        review,
                        reviewed_plan_sha256=str(frozen["plan_sha256"]),
                        score=95,
                        error_count=0,
                        warning_count=0,
                        review_conclusion="PASS",
                    ),
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

            tampered_review = json.loads(json.dumps(final_state))
            tampered_review["planning_rounds"][0]["review_conclusion"] = "FAIL"
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "planning review facts",
            ):
                aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id="planning-publish-recovery",
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                    prior_state=tampered_review,
                )

            inconsistent = json.loads(json.dumps(final_state))
            inconsistent["planning_rounds"][0]["score"] = 10
            inconsistent["planning_rounds"][0]["error_count"] = 3
            inconsistent["planning_rounds"][0]["verdict"] = "FAIL"
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError,
                "planning review facts",
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

            with self.assertRaises(PermissionError):
                (artifact_path / "APPROVED_TEST_PLAN.md").write_text(
                    "# Changed\n", encoding="utf-8"
                )

    def test_restored_closed_round_rejects_a_different_reviewed_plan_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            first = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id="planning-reviewed-hash-binding",
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
                manifest = self.write_engineering_input_manifest(project)
                artifact_path = root / "artifacts"
                run_id = f"planning-evidence-{incomplete_status.lower()}"
                coordinator = aegis_runtime.RuntimeCoordinator(
                    project_root=project,
                    artifact_path=artifact_path,
                    run_id=run_id,
                    upstream_port=7899,
                    relay_client=FakeRelayClient(),
                    start_node="A",
                    engineering_input_manifest_path=manifest,
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
                operation_id="fc" * 16,
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
                manifest = self.write_engineering_input_manifest(project)
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
                    engineering_input_manifest_path=manifest,
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
                with self.assertRaisesRegex(
                    aegis_runtime.FreezeContinuityLostError,
                    "cannot resume safely",
                ):
                    resumed.preflight()
                self.assertFalse(second_relay.started)

                final_state = aegis_runtime.load_run_state(artifact_path, run_id)
                self.assertEqual(final_state["planning_stage_status"], "active")
                self.assertEqual(
                    [
                        entry["application_verification_status"]
                        for entry in final_state["evidence_sessions"]
                    ],
                    ["INVALID"],
                )

    def test_all_planning_evidence_sessions_allow_completion_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_sealed_project(root)
            manifest = self.write_engineering_input_manifest(project)
            artifact_path = root / "artifacts"
            run_id = "planning-all-evidence-valid"
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                engineering_input_manifest_path=manifest,
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
                    "registration_operation_id": "fd" * 16,
                }
            ]
            self.attach_planning_evidence_process(
                coordinator, root, session_id="new-valid-session"
            )

            coordinator.complete_planning_stage()
            coordinator._write_state(
                "failed", RuntimeError("orderly planning resume boundary")
            )

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
            state_path = artifact_path / "runs" / run_id / "RUN_STATE.json"
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
            runtime_root = root / "artifacts"
            aegis_runtime.initialize_runtime_authority(
                runtime_root,
                project_id_hex=bytes(range(16)).hex(),
                runtime_authority_id="ab" * 16,
            )
            database = runtime_root / "project_state" / "checkpoints.sqlite3"
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
                artifact_path=runtime_root,
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
                    artifact_path / "runs" / run_id / "RUN_STATE.json"
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

    def test_v1_through_v4_run_state_are_rejected_without_registration_intent(
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
            for schema in (
                "aegis.run_state.v1",
                "aegis.run_state.v2",
                "aegis.run_state.v3",
                "aegis.run_state.v4",
                "aegis.run_state.v5",
                "aegis.run_state.v6",
                "aegis.run_state.v7",
                "aegis.run_state.v8",
                "aegis.run_state.v9",
                "aegis.run_state.v10",
                "aegis.run_state.v11",
            ):
                with self.subTest(schema=schema):
                    legacy = dict(saved)
                    legacy["schema"] = schema

                with self.assertRaisesRegex(
                    aegis_runtime.RuntimeStateError,
                    "predates the v14 reviewer-authority contract",
                ):
                        aegis_runtime.RuntimeCoordinator(
                            project_root=project,
                            artifact_path=artifact_path,
                            run_id=run_id,
                            upstream_port=7899,
                            relay_client=FakeRelayClient(),
                            start_node="A",
                            prior_state=legacy,
                        )


if __name__ == "__main__":
    unittest.main()
