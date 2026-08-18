from __future__ import annotations

import ctypes
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
from aegis_test_support import (
    initialize_test_git_repository,
    write_test_runtime_scope_policy,
)


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
                ["codex.exe", "exec", "resume"]
            )

        self.assertEqual(wrapped[0], base_executable)
        self.assertEqual(wrapped[1:3], ["-I", "-S"])
        self.assertEqual(
            wrapped[4:10],
            [
                "--active-process-limit",
                "64",
                "--job-memory-limit-bytes",
                str(4 * 1024**3),
                "--process-time-limit-100ns",
                str(7_200 * 10_000_000),
            ],
        )
        self.assertEqual(wrapped[-4:], ["--", "codex.exe", "exec", "resume"])

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

            def cli_runner(
                arguments: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                operation = arguments[1]
                if operation == "start":
                    payload = relay_payload("start")
                elif operation == "register":
                    payload = {
                        "ok": True,
                        "command": "register",
                        "state": "WAITING",
                        "service_pid": 101,
                        "supervisor_pid": 202,
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
                if status_calls == 1:
                    return relay_payload("status")
                deadline = time.monotonic() + 10
                pid_files = [root / "parent.pid", root / "child.pid", root / "grandchild.pid"]
                while not all(path.exists() for path in pid_files):
                    if time.monotonic() >= deadline:
                        raise AssertionError("descendant process tree did not start")
                    time.sleep(0.01)
                return {
                    **relay_payload("status", "FAULT"),
                    "session_id": "fault-session",
                    "last_error": "injected journal failure",
                }

            client = aegis_runtime.TraceRelayClient(
                command="C:/TraceRelay/tracerelay.exe",
                cli_runner=cli_runner,
                status_requester=status_requester,
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
            try:
                with patch.object(
                    coordinator,
                    "_capture_external_runtime_identity",
                    return_value=None,
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
