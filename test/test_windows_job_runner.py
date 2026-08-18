from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aegis_runtime
import project_seal_store
import tracerelay_client
import windows_job_runner
from aegis_test_support import (
    initialize_test_git_repository,
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
                "supervisor": _process_identity("supervisor", 202),
                "service": _process_identity("service", 101),
            },
        },
    }


def _process_identity(role: str, pid: int) -> dict[str, object]:
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


def process_is_active(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


@unittest.skipUnless(os.name == "nt", "Windows Job Object acceptance is Windows-only")
class WindowsJobRunnerTests(unittest.TestCase):
    def test_job_wrapper_uses_the_base_interpreter(self) -> None:
        base_executable = str(Path(sys._base_executable).resolve())
        with (
            patch.object(
                tracerelay_client.sys,
                "executable",
                r"C:\temporary-venv\Scripts\python.exe",
            ),
            patch.object(
                tracerelay_client.sys,
                "_base_executable",
                base_executable,
            ),
        ):
            wrapped = tracerelay_client._windows_job_command(
                ["codex.exe", "exec", "resume"],
                job_identity="ab" * 16,
            )

        self.assertEqual(wrapped[0], base_executable)
        self.assertEqual(wrapped[1:3], ["-I", "-S"])
        self.assertEqual(
            wrapped[4:16],
            [
                "--job-name",
                "Local\\Aegis-" + "ab" * 16,
                "--active-process-limit",
                "64",
                "--job-memory-limit-bytes",
                str(4 * 1024**3),
                "--process-time-limit-100ns",
                str(7_200 * 10_000_000),
                "--parent-pid",
                str(os.getpid()),
                "--parent-creation-time-100ns",
                str(tracerelay_client._windows_process_creation_time_100ns(os.getpid())),
            ],
        )
        self.assertEqual(wrapped[-4:], ["--", "codex.exe", "exec", "resume"])

    def test_named_job_membership_can_be_frozen_and_fully_terminated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_pid_path = root / "child.pid"
            child_script = root / "child.py"
            child_script.write_text(
                "import os, pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
                "time.sleep(120)\n",
                encoding="utf-8",
            )
            identity = "cd" * 16
            job_name = tracerelay_client._windows_job_name(identity)
            runner = subprocess.Popen(
                tracerelay_client._windows_job_command(
                    [sys.executable, str(child_script), str(child_pid_path)],
                    job_identity=identity,
                )
            )
            child_pid: int | None = None
            try:
                deadline = time.monotonic() + 10
                while not child_pid_path.exists():
                    if runner.poll() is not None:
                        self.fail(f"runner exited before child startup: {runner.returncode}")
                    if time.monotonic() >= deadline:
                        self.fail("managed child did not start")
                    time.sleep(0.02)
                child_pid = int(child_pid_path.read_text(encoding="ascii"))
                members = windows_job_runner._freeze_named_job_members(
                    job_name, runner_pid=runner.pid
                )
                self.assertTrue({runner.pid, child_pid}.issubset(set(members)))
                identities = {
                    pid: tracerelay_client._windows_process_creation_time_100ns(pid)
                    for pid in members
                }
                self.assertTrue(process_is_active(runner.pid))
                self.assertTrue(process_is_active(child_pid))
                runner.kill()
                runner.wait(timeout=5)
                deadline = time.monotonic() + 10
                while process_is_active(child_pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(
                    all(
                        not process_is_active(pid)
                        or tracerelay_client._windows_process_creation_time_100ns(pid)
                        != creation_time
                        for pid, creation_time in identities.items()
                    )
                )
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.wait(timeout=5)
                if child_pid is not None and process_is_active(child_pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )

    def test_parent_exit_kills_runner_and_managed_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_pid_path = root / "child.pid"
            runner_pid_path = root / "runner.pid"
            child_script = root / "child.py"
            launcher_script = root / "launcher.py"
            child_script.write_text(
                "import os, pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
                "time.sleep(120)\n",
                encoding="utf-8",
            )
            launcher_script.write_text(
                "import pathlib, subprocess, sys, time\n"
                f"sys.path.insert(0, {str(PROJECT_ROOT / 'src')!r})\n"
                "from tracerelay_client import _windows_job_command\n"
                "root=pathlib.Path(sys.argv[1])\n"
                "process=subprocess.Popen(_windows_job_command([sys.executable, "
                "str(root/'child.py'), str(root/'child.pid')]))\n"
                "(root/'runner.pid').write_text(str(process.pid), encoding='ascii')\n"
                "time.sleep(120)\n",
                encoding="utf-8",
            )
            launcher = subprocess.Popen([sys.executable, str(launcher_script), str(root)])
            runner_pid: int | None = None
            child_pid: int | None = None
            try:
                deadline = time.monotonic() + 15
                while not child_pid_path.exists() or not runner_pid_path.exists():
                    if launcher.poll() is not None:
                        self.fail(f"launcher exited early: {launcher.returncode}")
                    if time.monotonic() >= deadline:
                        self.fail("managed process tree did not start")
                    time.sleep(0.02)
                runner_pid = int(runner_pid_path.read_text(encoding="ascii"))
                child_pid = int(child_pid_path.read_text(encoding="ascii"))
                self.assertTrue(process_is_active(runner_pid))
                self.assertTrue(process_is_active(child_pid))
                launcher.terminate()
                launcher.wait(timeout=5)
                deadline = time.monotonic() + 10
                while (
                    process_is_active(runner_pid) or process_is_active(child_pid)
                ) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(process_is_active(runner_pid))
                self.assertFalse(process_is_active(child_pid))
            finally:
                if launcher.poll() is None:
                    launcher.kill()
                    launcher.wait(timeout=5)
                if runner_pid is not None and process_is_active(runner_pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(runner_pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )

    def test_relay_fault_kills_real_descendant_tree_and_preserves_cause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
            scripts = root / "scripts"
            scripts.mkdir()
            grandchild = scripts / "grandchild.py"
            child = scripts / "child.py"
            parent = scripts / "parent.py"
            grandchild.write_text(
                "import os, pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
                "print('grandchild-ready', flush=True)\n"
                "time.sleep(120)\n",
                encoding="utf-8",
            )
            child.write_text(
                "import os, pathlib, subprocess, sys, time\n"
                "root=pathlib.Path(sys.argv[1])\n"
                "pathlib.Path(root/'child.pid').write_text(str(os.getpid()), encoding='ascii')\n"
                "subprocess.Popen([sys.executable, str(root/'scripts'/'grandchild.py'), "
                "str(root/'grandchild.pid')], stdout=sys.stdout, stderr=sys.stderr)\n"
                "print('child-ready', flush=True)\n"
                "time.sleep(120)\n",
                encoding="utf-8",
            )
            parent.write_text(
                "import os, pathlib, subprocess, sys, time\n"
                "root=pathlib.Path(sys.argv[1])\n"
                "pathlib.Path(root/'parent.pid').write_text(str(os.getpid()), encoding='ascii')\n"
                "subprocess.Popen([sys.executable, str(root/'scripts'/'child.py'), str(root)], "
                "stdout=sys.stdout, stderr=sys.stderr)\n"
                "print('parent-ready', flush=True)\n"
                "time.sleep(120)\n",
                encoding="utf-8",
            )
            runtime_python = Path(sys.executable).resolve()
            runtime_python_bytes = runtime_python.read_bytes()
            runtime_python_sha256 = hashlib.sha256(runtime_python_bytes).hexdigest()

            def actual_runtime_payload(
                command: str, state: str = "IDLE"
            ) -> dict[str, object]:
                payload = relay_payload(command, state)
                identity = payload["runtime_identity"]
                assert isinstance(identity, dict)
                identity["python_executable_sha256"] = runtime_python_sha256
                processes = identity["processes"]
                assert isinstance(processes, dict)
                for process in processes.values():
                    assert isinstance(process, dict)
                    process["python_executable"] = str(runtime_python)
                    process["python_executable_sha256"] = runtime_python_sha256
                return payload

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                operation = arguments[1]
                if operation == "start":
                    payload = actual_runtime_payload("start")
                elif operation == "register":
                    payload = {
                        **actual_runtime_payload("register", "WAITING"),
                        "session_id": "fault-session",
                        "proxy_host": "127.0.0.1",
                        "proxy_port": 45000,
                        "upstream_host": "127.0.0.1",
                        "upstream_port": 7899,
                        "session_path": str(root / "session"),
                    }
                else:
                    raise AssertionError(f"unexpected operation: {operation}")
                return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

            status_calls = 0

            def status_requester() -> dict[str, object]:
                nonlocal status_calls
                status_calls += 1
                if status_calls <= 2:
                    return actual_runtime_payload("status")
                deadline = time.monotonic() + 10
                pid_files = [root / "parent.pid", root / "child.pid", root / "grandchild.pid"]
                while not all(path.exists() for path in pid_files):
                    if time.monotonic() >= deadline:
                        raise AssertionError("descendant process tree did not start")
                    time.sleep(0.01)
                return {
                    **actual_runtime_payload("status", "FAULT"),
                    "session_id": "fault-session",
                    "last_error": "injected journal failure",
                }

            client = aegis_runtime.TraceRelayClient(
                command=str(runtime_python),
                cli_runner=cli_runner,
                status_requester=status_requester,
                process_creation_time_reader=lambda pid: pid * 10_000,
                alarm_directory=root / "alarms",
                monitor_interval_seconds=0,
            )
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=project,
                artifact_path=root / "artifacts",
                run_id="run-job-tree",
                upstream_port=7899,
                relay_client=client,
                start_node="A",
            )
            coordinator._tracerelay_runtime["runtime_nonce"] = TEST_RUNTIME_NONCE
            frozen_external = {
                "tracerelay_sdk": {
                    "snapshot_manifest_sha256": TEST_SDK_MANIFEST_SHA256,
                },
                "files": [
                    {
                        "source": "python_executable",
                        "path": str(runtime_python),
                        "size": len(runtime_python_bytes),
                        "sha256": runtime_python_sha256,
                    }
                ],
            }
            try:
                with patch.object(
                    coordinator,
                    "_capture_external_runtime_identity",
                    return_value=frozen_external,
                ):
                    coordinator.preflight()

                    def invoke(_state: dict[str, object]) -> dict[str, object]:
                        coordinator.run_codex_process(
                            [sys.executable, str(parent), str(root)],
                            timeout_seconds=30,
                        )
                        return {"status": True}

                    with self.assertRaisesRegex(
                        aegis_runtime.TraceRelayError, "injected journal failure"
                    ):
                        coordinator.execute_node("A", invoke, {"status": True})
            finally:
                pid_files = [root / "parent.pid", root / "child.pid", root / "grandchild.pid"]
                pids = [int(path.read_text(encoding="ascii")) for path in pid_files if path.exists()]
                if pids and any(process_is_active(pid) for pid in pids):
                    subprocess.run(
                        ["taskkill", "/PID", str(pids[0]), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )

            deadline = time.monotonic() + 5
            while any(process_is_active(pid) for pid in pids) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(pids)
            self.assertTrue(all(not process_is_active(pid) for pid in pids))
            saved = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["error"]["type"], "TraceRelayError")
            self.assertIn("injected journal failure", saved["error"]["message"])


if __name__ == "__main__":
    unittest.main()
