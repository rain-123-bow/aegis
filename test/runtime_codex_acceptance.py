from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import locale
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

REQUIRED_SOURCE_BINDINGS = (
    "src/aegis_runtime.py",
    "src/main.py",
    "src/tracerelay_client.py",
    "src/codex_app_server_client.py",
    "submodules/TraceRelay/src/tracerelay/cli.py",
    "submodules/TraceRelay/src/tracerelay/config.py",
    "submodules/TraceRelay/src/tracerelay/service.py",
    "submodules/TraceRelay/src/tracerelay/session.py",
    "submodules/TraceRelay/src/tracerelay/verify.py",
    "test/runtime_codex_acceptance.py",
)

import main as aegis_main
from project_seal_store import record_project_seal, verify_expected_project_seal
from tracerelay_client import TraceRelayClient


def _source_sha256() -> dict[str, str]:
    return {
        relative_path: hashlib.sha256(
            (PROJECT_ROOT / relative_path).read_bytes()
        ).hexdigest()
        for relative_path in REQUIRED_SOURCE_BINDINGS
    }


def _validate_report_source_binding(report: dict[str, object]) -> None:
    if report.get("verdict") != "PASS":
        raise AssertionError("acceptance report verdict is not PASS")
    source_sha256 = report.get("source_sha256")
    if not isinstance(source_sha256, dict):
        raise AssertionError("acceptance report source_sha256 is missing")
    current = _source_sha256()
    for relative_path in REQUIRED_SOURCE_BINDINGS:
        saved = source_sha256.get(relative_path)
        if (
            not isinstance(saved, str)
            or len(saved) != 64
            or any(character not in "0123456789abcdef" for character in saved)
            or saved != current[relative_path]
        ):
            raise AssertionError(
                f"acceptance report source_sha256 mismatch: {relative_path}"
            )
    tracerelay_command = report.get("tracerelay_command")
    command_sha256 = report.get("tracerelay_command_sha256")
    if not isinstance(tracerelay_command, str) or not tracerelay_command:
        raise AssertionError("acceptance report TraceRelay command is missing")
    command_path = Path(tracerelay_command)
    if not command_path.is_absolute() or not command_path.is_file():
        raise AssertionError("acceptance report TraceRelay command is unavailable")
    if (
        not isinstance(command_sha256, str)
        or len(command_sha256) != 64
        or any(character not in "0123456789abcdef" for character in command_sha256)
        or command_sha256 != hashlib.sha256(command_path.read_bytes()).hexdigest()
    ):
        raise AssertionError("acceptance report TraceRelay command hash mismatch")


def _cli_json(command: str, *arguments: str) -> tuple[int, dict[str, object]]:
    completed = subprocess.run(
        [command, *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=30,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    raw: str | None = None
    for encoding in ("utf-8", locale.getpreferredencoding(False), "mbcs"):
        try:
            raw = output.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise RuntimeError("TraceRelay returned undecodable output")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f"TraceRelay returned a non-object response: {raw}")
    return completed.returncode, payload


def _wait_for_not_running(command: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _returncode, payload = _cli_json(command, "status")
        if payload.get("state") == "NOT_RUNNING":
            return
        time.sleep(0.1)
    raise RuntimeError("TraceRelay did not stop within the acceptance bound")


def _terminate_process(pid: int) -> None:
    process_terminate = 0x0001
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.TerminateProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(process_terminate, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"cannot open PID {pid}")
    try:
        if not kernel32.TerminateProcess(handle, 91):
            raise OSError(ctypes.get_last_error(), f"cannot terminate PID {pid}")
    finally:
        kernel32.CloseHandle(handle)


def _process_is_active(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
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


def _process_snapshot() -> list[dict[str, object]]:
    powershell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if powershell is None:
        raise RuntimeError("PowerShell is required for the process-tree snapshot")
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "Get-CimInstance Win32_Process | "
                "Select-Object ProcessId,ParentProcessId,Name | "
                "ConvertTo-Json -Compress"
            ),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout)
    rows = payload if isinstance(payload, list) else [payload]
    return [row for row in rows if isinstance(row, dict)]


def _descendants(root_pid: int) -> list[dict[str, object]]:
    rows = _process_snapshot()
    known = {root_pid}
    descendants: list[dict[str, object]] = []
    changed = True
    while changed:
        changed = False
        for row in rows:
            pid = row.get("ProcessId")
            parent = row.get("ParentProcessId")
            if (
                isinstance(pid, int)
                and isinstance(parent, int)
                and parent in known
                and pid not in known
            ):
                known.add(pid)
                descendants.append(row)
                changed = True
    return descendants


def _prepare_project(path: Path) -> None:
    source = path / "src" / "acceptance_target.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_text("ACCEPTANCE_TARGET = True\n", encoding="utf-8")
    seal = path / ".aegis/reasoning_ledger/artifacts/facts/project-seal.json"
    if seal.exists():
        verify_expected_project_seal(path)
    else:
        record_project_seal(
            path,
            git_head_before_record="a" * 40,
            project_id=bytes(range(16)),
            run_id=bytes(range(16, 32)),
        )


def _prompt(artifact_path: Path, *, sleep_marker: Path | None = None) -> str:
    response = json.dumps(
        {
            "artifact_path": str(artifact_path),
            "reasoning_ledger_context_pack": str(
                artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
            ),
            "status": True,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if sleep_marker is None:
        return f"Runtime acceptance. Return exactly this one-line JSON, no fence: {response}"
    return (
        "Runtime fault acceptance. First use the shell tool to run this exact PowerShell 7 "
        f"command: New-Item -ItemType File -Force -Path '{sleep_marker}'; "
        "Start-Sleep -Seconds 120. Only after it finishes, return exactly this one-line "
        f"JSON with no fence: {response}"
    )


def _run_graph_once(
    *,
    project: Path,
    artifact_path: Path,
    run_id: str,
    tracerelay_command: str,
    upstream_port: int,
    prompt: str,
    resume: bool,
    observation: dict[str, object],
) -> dict[str, Any]:
    client_box: dict[str, TraceRelayClient] = {}

    def popen_factory(*args: object, **kwargs: object) -> subprocess.Popen[str]:
        client = client_box["client"]
        observation["registration_before_process"] = (
            client.last_registration is not None
        )
        process = subprocess.Popen(*args, **kwargs)
        observation["runner_pid"] = process.pid
        return process

    client = TraceRelayClient(
        command=tracerelay_command,
        popen_factory=popen_factory,
        monitor_interval_seconds=0.1,
    )
    client_box["client"] = client
    arguments = [
        "--project-root",
        str(project),
        "--artifact-path",
        str(artifact_path),
        "--tracerelay-command",
        tracerelay_command,
        "--tracerelay-upstream-port",
        str(upstream_port),
    ]
    if resume:
        arguments.extend(["--resume-run-id", run_id])
    else:
        arguments.extend(["--run-id", run_id, "--start-node", "F"])
    with (
        patch.object(aegis_main, "TraceRelayClient", return_value=client),
        patch.object(
            aegis_main,
            "load_agent_config",
            return_value={
                "role_key": aegis_main.FINAL_REVIEWER_ROLE,
                "role_description": "runtime acceptance final reviewer",
            },
        ),
        patch.object(aegis_main, "build_node_prompt", return_value=prompt),
    ):
        return aegis_main.main(arguments)


def _verify_session(command: str, session_path: str) -> dict[str, object]:
    returncode, payload = _cli_json(command, "verify", session_path)
    if returncode != 0:
        raise RuntimeError(f"TraceRelay verify failed: {payload}")
    return payload


def run_acceptance(args: argparse.Namespace) -> dict[str, object]:
    if os.name != "nt":
        raise RuntimeError("runtime acceptance is Windows-only")
    tracerelay_command = str(Path(args.tracerelay_command).resolve())
    evidence_root = Path(args.evidence_root).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    project = evidence_root / "project"
    _prepare_project(project)
    source_sha256 = _source_sha256()
    tracerelay_command_sha256 = hashlib.sha256(
        Path(tracerelay_command).read_bytes()
    ).hexdigest()

    _returncode, initial_status = _cli_json(tracerelay_command, "status")
    if initial_status.get("state") != "NOT_RUNNING":
        raise RuntimeError("TraceRelay is already running; ownership is ambiguous")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    nonce = uuid4().hex[:8]
    normal_run_id = f"normal-{stamp}-{nonce}"
    fault_run_id = f"fault-{stamp}-{nonce}"
    normal_artifacts = evidence_root / "runs" / normal_run_id
    fault_artifacts = evidence_root / "runs" / fault_run_id
    report: dict[str, object] = {
        "schema": "aegis.runtime_codex_acceptance.v3",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "normal_run_id": normal_run_id,
        "fault_run_id": fault_run_id,
        "tracerelay_command": tracerelay_command,
        "tracerelay_command_sha256": tracerelay_command_sha256,
    }

    hostile = {
        "NO_PROXY": "*",
        "no_proxy": "*",
        "ALL_PROXY": "http://127.0.0.1:1",
        "all_proxy": "http://127.0.0.1:2",
    }
    os.environ.update(hostile)

    normal_observation: dict[str, object] = {}
    try:
        normal_result = _run_graph_once(
            project=project,
            artifact_path=normal_artifacts,
            run_id=normal_run_id,
            tracerelay_command=tracerelay_command,
            upstream_port=args.upstream_port,
            prompt=_prompt(normal_artifacts),
            resume=False,
            observation=normal_observation,
        )
        normal_state_path = (
            normal_artifacts / ".aegis" / "runs" / normal_run_id / "RUN_STATE.json"
        )
        normal_state = json.loads(normal_state_path.read_text(encoding="utf-8"))
        normal_session = normal_state["evidence_sessions"][-1]
        normal_verify = _verify_session(
            tracerelay_command, normal_session["session_path"]
        )
        if normal_result.get("status") is not True:
            raise AssertionError("real Codex response did not reach the graph")
        if normal_state.get("status") != "completed":
            raise AssertionError("normal run did not complete")
        if not normal_observation.get("registration_before_process"):
            raise AssertionError("process started before TraceRelay registration")
        if normal_verify.get("status") != "VALID_COMPLETE":
            raise AssertionError("normal evidence is not VALID_COMPLETE")
        observed = normal_verify.get("observed_bytes")
        if not isinstance(observed, dict) or not all(
            isinstance(value, int) and value > 0 for value in observed.values()
        ):
            raise AssertionError("normal evidence has no bidirectional bytes")
        report["normal"] = {
            "run_state_path": str(normal_state_path),
            "session_path": normal_session["session_path"],
            "verification": normal_verify,
            "registration_before_process": True,
        }
    finally:
        _cli_json(tracerelay_command, "stop")
        _wait_for_not_running(tracerelay_command)

    fault_observation: dict[str, object] = {}
    fault_error: list[BaseException] = []
    fault_marker = fault_artifacts / "fault-turn-started.marker"

    def fault_worker() -> None:
        try:
            _run_graph_once(
                project=project,
                artifact_path=fault_artifacts,
                run_id=fault_run_id,
                tracerelay_command=tracerelay_command,
                upstream_port=args.upstream_port,
                prompt=_prompt(fault_artifacts, sleep_marker=fault_marker),
                resume=False,
                observation=fault_observation,
            )
        except BaseException as error:
            fault_error.append(error)

    worker = threading.Thread(target=fault_worker, daemon=True)
    worker.start()
    service_pid: int | None = None
    descendants: list[dict[str, object]] = []
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        _returncode, status = _cli_json(tracerelay_command, "status")
        runner_pid = fault_observation.get("runner_pid")
        if (
            status.get("state") == "RELAYING"
            and isinstance(status.get("service_pid"), int)
            and isinstance(runner_pid, int)
        ):
            descendants = _descendants(runner_pid)
            names = {str(row.get("Name", "")).lower() for row in descendants}
            if "node.exe" in names and any("codex" in name for name in names):
                service_pid = int(status["service_pid"])
                break
        if not worker.is_alive():
            break
        time.sleep(0.2)
    if service_pid is None:
        raise RuntimeError(
            f"real Codex process tree was not observable before completion: {descendants}"
        )
    runner_pid = int(fault_observation["runner_pid"])
    captured_pids = [runner_pid] + [int(row["ProcessId"]) for row in descendants]
    _terminate_process(service_pid)
    worker.join(timeout=45)
    if worker.is_alive():
        subprocess.run(
            ["taskkill", "/PID", str(runner_pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        raise RuntimeError("fault-injected Aegis run did not terminate")
    if len(fault_error) != 1 or type(fault_error[0]).__name__ != "TraceRelayError":
        raise AssertionError(
            f"original TraceRelayError was not preserved: {fault_error}"
        )
    _wait_for_not_running(tracerelay_command)
    deadline = time.monotonic() + 10
    while (
        any(_process_is_active(pid) for pid in captured_pids)
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
    if any(_process_is_active(pid) for pid in captured_pids):
        raise AssertionError("real Codex process tree survived relay failure")

    fault_state_path = (
        fault_artifacts / ".aegis" / "runs" / fault_run_id / "RUN_STATE.json"
    )
    fault_state = json.loads(fault_state_path.read_text(encoding="utf-8"))
    if fault_state.get("status") != "failed" or fault_state.get("current_node") != "F":
        raise AssertionError("fault state was not saved at node F")
    if fault_state.get("error", {}).get("type") != "TraceRelayError":
        raise AssertionError("RUN_STATE did not preserve TraceRelayError")
    incomplete_session = fault_state["evidence_sessions"][-1]
    if (
        incomplete_session.get("verification_status") != "UNVERIFIED"
        or incomplete_session.get("application_verification_status") != "INVALID"
    ):
        raise AssertionError(
            "fault RUN_STATE did not persist UNVERIFIED/INVALID evidence"
        )
    incomplete_verify = _verify_session(
        tracerelay_command, incomplete_session["session_path"]
    )
    if incomplete_verify.get("status") != "VALID_INCOMPLETE":
        raise AssertionError("fault evidence is not VALID_INCOMPLETE")

    resume_observation: dict[str, object] = {}
    resume_error: BaseException | None = None
    try:
        try:
            _run_graph_once(
                project=project,
                artifact_path=fault_artifacts,
                run_id=fault_run_id,
                tracerelay_command=tracerelay_command,
                upstream_port=args.upstream_port,
                prompt=_prompt(fault_artifacts),
                resume=True,
                observation=resume_observation,
            )
        except BaseException as error:
            resume_error = error
    finally:
        _cli_json(tracerelay_command, "stop")
        _wait_for_not_running(tracerelay_command)
    if (
        resume_error is None
        or type(resume_error).__name__ != "RuntimeStateError"
        or "incomplete TraceRelay evidence" not in str(resume_error)
    ):
        raise AssertionError(
            f"same-run resume did not fail closed on incomplete evidence: {resume_error}"
        )
    if resume_observation:
        raise AssertionError("rejected resume started a new Codex process")
    rejected_state = json.loads(fault_state_path.read_text(encoding="utf-8"))
    if (
        rejected_state.get("status") != "failed"
        or rejected_state.get("error", {}).get("type") != "RuntimeStateError"
        or len(rejected_state.get("evidence_sessions", [])) != 1
    ):
        raise AssertionError("rejected resume did not preserve the failed run evidence")
    report["fault_and_rejection"] = {
        "run_state_path": str(fault_state_path),
        "captured_processes": descendants,
        "all_captured_pids_exited": True,
        "original_error": str(fault_error[0]),
        "incomplete_session_path": incomplete_session["session_path"],
        "incomplete_verification": incomplete_verify,
        "resume_error": str(resume_error),
        "resume_started_process": False,
    }

    report["verdict"] = "PASS"
    report["source_sha256"] = source_sha256
    _validate_report_source_binding(report)

    report_path = evidence_root / f"RUNTIME_CODEX_ACCEPTANCE_{stamp}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path = report_path.with_suffix(".md")
    markdown_path.write_text(
        "# Runtime Codex Acceptance\n\n"
        "- verdict: PASS\n"
        "- F control plane: persistent App Server thread with per-turn TraceRelay sessions\n"
        f"- normal_run_id: `{normal_run_id}`\n"
        f"- fault_run_id: `{fault_run_id}`\n"
        f"- JSON evidence: `{report_path}`\n"
        "- normal evidence: `VALID_COMPLETE`, bidirectional bytes > 0\n"
        "- injected failure: complete real Codex process tree exited\n"
        "- failure evidence: `VALID_INCOMPLETE`\n"
        "- same-run resume: rejected before TraceRelay restart or Codex process creation\n",
        encoding="utf-8",
    )
    report["report_path"] = str(report_path)
    report["markdown_path"] = str(markdown_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracerelay-command", required=True)
    parser.add_argument("--upstream-port", type=int, default=7899)
    parser.add_argument(
        "--evidence-root", default=r"C:\code\aegis-acceptance-artifacts"
    )
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(run_acceptance(parse_args()), ensure_ascii=False, indent=2))
