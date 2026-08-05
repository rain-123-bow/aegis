from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any


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


class TraceRelayClientTests(unittest.TestCase):
    def make_client(
        self,
        root: Path,
        *,
        status_payloads: Sequence[dict[str, object]],
        process: FakeProcess,
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
                payload = {
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
                base_environment={"PATH": "value"},
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
                [Path(command[0]).name for command in commands],
                ["tracerelay.exe", "tracerelay.exe", "tracerelay.exe"],
            )

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


if __name__ == "__main__":
    unittest.main()
