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
            captured_popen.setdefault("cli_timeouts", []).append(
                (operation, timeout)
            )
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
            self.assertEqual(
                captured["env"]["HTTPS_PROXY"], "http://127.0.0.1:45000"
            )
            self.assertEqual(
                captured["env"]["HTTP_PROXY"], "http://127.0.0.1:45000"
            )
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

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "FAULT"
            ):
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

            with self.assertRaisesRegex(
                aegis_runtime.TraceRelayError, "new alarm"
            ):
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

    def test_managed_process_keeps_interactive_pipes_and_seals_on_finalize(self) -> None:
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
                return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

            def popen_factory(command: list[str], **kwargs: Any) -> InteractiveFakeProcess:
                captured.update(command=command, **kwargs)
                return process

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=status,
                popen_factory=popen_factory,
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
                return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=status,
                popen_factory=lambda *args, **kwargs: process,
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


class FakeRelayClient:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> dict[str, object]:
        self.started = True
        return relay_payload("start")


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

            saved = json.loads(
                coordinator.run_state_path.read_text(encoding="utf-8")
            )
            self.assertTrue(relay.started)
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["current_node"], "A")
            self.assertEqual(saved["graph_state"], {"status": True})
            self.assertEqual(saved["error"]["type"], "RuntimeError")

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

                def open_managed_process(self, *args: object, **kwargs: object) -> ManagedProcess:
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

                def start_turn(self, thread_id: str, prompt: str, **kwargs: Any) -> SimpleNamespace:
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
            with (
                patch.object(aegis_runtime, "AppServerClient", side_effect=make_app_server),
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
                author_response = coordinator.run_planning_agent(
                    "TEST_PLAN_AUTHOR",
                    "author prompt",
                    output_schema={"type": "object"},
                    developer_instructions="author",
                )
                interim = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
                reviewer_response = coordinator.run_planning_agent(
                    "TEST_PLAN_REVIEWER",
                    "reviewer prompt",
                    output_schema={"type": "object"},
                    developer_instructions="reviewer",
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
            self.assertEqual(interim["planning_turns"][0]["codex_turn_id"], "planning-turn-1")
            self.assertEqual(interim["planning_turns"][0]["status"], "completed")
            self.assertTrue(Path(interim["planning_turns"][0]["raw_response_path"]).is_file())
            self.assertEqual(interim["planning_stage_status"], "active")
            final_state = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(final_state["codex_cli_version"], "codex-cli 0.145.0")
            self.assertEqual(final_state["evidence_sessions"][0]["node"], "planning")
            self.assertEqual(final_state["planning_stage_status"], "completed")

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
            first_report.write_text("# Review\n\nOne blocking issue.\n", encoding="utf-8")
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
            self.assertEqual(handoff["approved_plan_sha256"], second_frozen["plan_sha256"])
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

    def test_resume_replays_a_completed_planning_turn_without_resubmitting(self) -> None:
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
            response_path = coordinator.run_state_path.parent / "responses" / "saved.json"
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

            saved = json.loads(
                coordinator.run_state_path.read_text(encoding="utf-8")
            )
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
            state_path = (
                artifact_path / ".aegis" / "runs" / run_id / "RUN_STATE.json"
            )
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
                    artifact_path
                    / ".aegis"
                    / "runs"
                    / run_id
                    / "RUN_STATE.json"
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

    def test_legacy_state_infers_completed_planning_from_verified_evidence(self) -> None:
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
            saved.pop("planning_stage_status")
            saved["planning_agents"] = {
                "TEST_PLAN_AUTHOR": {"codex_thread_id": "thread-author"}
            }
            saved["evidence_sessions"] = [
                {
                    "node": "planning",
                    "verification_status": "VALID_COMPLETE",
                }
            ]

            resumed = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=7899,
                relay_client=FakeRelayClient(),
                start_node="A",
                prior_state=saved,
            )

            self.assertEqual(resumed.planning_stage_status, "completed")


if __name__ == "__main__":
    unittest.main()
