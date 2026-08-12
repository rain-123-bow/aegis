from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aegis_runtime import RuntimeCoordinator, TraceRelayClient  # noqa: E402
from project_seal_store import record_project_seal  # noqa: E402


NODE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "artifact_path",
        "reasoning_ledger_context_pack",
        "status",
    ],
    "properties": {
        "artifact_path": {"type": "string", "minLength": 1},
        "reasoning_ledger_context_pack": {"type": "string", "minLength": 1},
        "status": {"type": "boolean"},
    },
}

REVIEW_NODE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "artifact_path",
        "reasoning_ledger_context_pack",
        "status",
        "reviewed_plan_sha256",
        "score",
        "error_count",
        "warning_count",
        "verdict",
    ],
    "properties": {
        **NODE_SCHEMA["properties"],
        "reviewed_plan_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "error_count": {"type": "integer", "minimum": 0},
        "warning_count": {"type": "integer", "minimum": 0},
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
    },
}


def _run_execution_crash_worker(config_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    project = Path(config["project"])
    artifact_path = Path(config["artifact_path"])
    state = dict(config["state"])
    coordinator = RuntimeCoordinator(
        project_root=project,
        artifact_path=artifact_path,
        run_id=str(config["run_id"]),
        upstream_port=int(config["upstream_port"]),
        relay_client=TraceRelayClient(
            command=str(config["tracerelay_command"]),
            monitor_interval_seconds=0.05,
        ),
        start_node="F",
    )
    coordinator.preflight()

    def crash_before_response_receipt(*_args: object) -> None:
        os._exit(91)

    coordinator._complete_execution_turn = crash_before_response_receipt  # type: ignore[method-assign]

    def operation(node_state: dict[str, object]) -> dict[str, object]:
        response = coordinator.run_execution_agent(
            "FINAL_REVIEWER",
            str(config["prompt"]),
            output_schema=NODE_SCHEMA,
            developer_instructions=str(config["developer_instructions"]),
            timeout_seconds=300,
        )
        return {**node_state, "response": response, "current_node": "F"}

    coordinator.execute_node("F", operation, state)
    raise AssertionError("crash worker unexpectedly returned")


def _windows_process_is_running(process_pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    error_invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process = kernel32.OpenProcess(synchronize, False, process_pid)
    if not process:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return False
        raise OSError(error, f"cannot inspect process PID {process_pid}")
    try:
        return kernel32.WaitForSingleObject(process, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(process)


@unittest.skipUnless(
    os.environ.get("TRACERELAY_COMMAND"),
    "set TRACERELAY_COMMAND to run the traced App Server acceptance",
)
class TracedAppServerRealIntegrationTests(unittest.TestCase):
    def test_planning_and_per_turn_execution_control_planes(self) -> None:
        tracerelay_command = str(Path(os.environ["TRACERELAY_COMMAND"]).resolve())
        initial = subprocess.run(
            [tracerelay_command, "status"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=15,
        )
        initial_raw = initial.stdout.strip() or initial.stderr.strip()
        initial_status = json.loads(initial_raw.decode("utf-8", errors="replace"))
        if initial_status.get("state") != "NOT_RUNNING":
            self.skipTest("TraceRelay is already running; ownership is ambiguous")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        short_id = uuid4().hex[:12]
        run_id = f"p-{short_id}"
        root = (
            Path(
                os.environ.get(
                    "AEGIS_APP_SERVER_ACCEPTANCE_ROOT", r"C:\code\aegis_artifacts"
                )
            )
            / "as_pilot"
            / short_id
        ).resolve()
        project = root / "project"
        artifact_path = root / "artifacts"
        source = project / "src" / "acceptance_target.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("ACCEPTANCE_TARGET = True\n", encoding="utf-8")
        record_project_seal(
            project,
            git_head_before_record="a" * 40,
            project_id=bytes(range(16)),
            run_id=bytes(range(16, 32)),
        )
        context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        artifact_path.mkdir(parents=True, exist_ok=True)
        context_path.write_text("{}\n", encoding="utf-8")
        expected = {
            "artifact_path": str(artifact_path),
            "reasoning_ledger_context_pack": str(context_path),
            "status": True,
        }
        relay = TraceRelayClient(
            command=tracerelay_command,
            monitor_interval_seconds=0.05,
        )
        coordinator = RuntimeCoordinator(
            project_root=project,
            artifact_path=artifact_path,
            run_id=run_id,
            upstream_port=int(os.environ.get("TRACERELAY_UPSTREAM_PORT", "7899")),
            relay_client=relay,
            start_node="A",
        )
        owned = False
        try:
            coordinator.preflight()
            owned = True
            coordinator.prepare_planning_agents(
                {
                    "TEST_PLAN_AUTHOR": (
                        "Acceptance author. Use tools only to write the coordinator-provided "
                        "plan_path. Do not use Aegis-specific skills. Return only schema-valid "
                        "JSON after the file is durable."
                    ),
                    "TEST_PLAN_REVIEWER": (
                        "Independent acceptance reviewer. Use tools only to read plan_path and "
                        "write review_report_path. Do not use Aegis-specific skills. Return only "
                        "schema-valid JSON after the report is durable."
                    ),
                }
            )
            expected_json = json.dumps(
                expected, ensure_ascii=False, separators=(",", ":")
            )
            author_raws: list[str] = []
            reviewer_outputs: list[dict[str, object]] = []
            accepted = False
            for _attempt in range(3):
                author_control = coordinator.prepare_planning_author(context_path)
                author_raw = coordinator.run_planning_agent(
                    "TEST_PLAN_AUTHOR",
                    (
                        "Write a complete executable acceptance plan to plan_path. The sealed "
                        "project contains src/acceptance_target.py with ACCEPTANCE_TARGET=True. "
                        "The required test runs from project_root with command `python -c "
                        '"from src.acceptance_target import ACCEPTANCE_TARGET; '
                        "print(ACCEPTANCE_TARGET); raise SystemExit(0 if "
                        'ACCEPTANCE_TARGET is True else 1)"`. The plan must state cwd, command, '
                        "input, expected stdout `True`, expected exit code 0, evidence file paths, "
                        "and the exact pass/fail rule. This synthetic acceptance has no other "
                        "requirements. Address every prior review item when present. Then return "
                        f"exactly this JSON object: {expected_json}\n"
                        f"CONTROL={json.dumps(author_control, ensure_ascii=False)}"
                    ),
                    output_schema=NODE_SCHEMA,
                    developer_instructions="author",
                    job_id=str(author_control["job_id"]),
                )
                author_raws.append(author_raw)
                self.assertEqual(json.loads(author_raw), expected)
                coordinator.freeze_planning_plan(str(author_control["round_id"]))
                review_control = coordinator.prepare_planning_review()
                reviewer_raw = coordinator.run_planning_agent(
                    "TEST_PLAN_REVIEWER",
                    (
                        "Independently review only the frozen plan and its stated synthetic "
                        "requirement. Apply the coordinator threshold without leniency. Write the "
                        "complete review Markdown to review_report_path. Return the exact reviewed "
                        "hash and your actual score, error_count, warning_count, and PASS/FAIL "
                        "verdict; model status does not control routing.\n"
                        f"CONTROL={json.dumps(review_control, ensure_ascii=False)}"
                    ),
                    output_schema=REVIEW_NODE_SCHEMA,
                    developer_instructions="reviewer",
                    job_id=str(review_control["job_id"]),
                )
                reviewer_output = json.loads(reviewer_raw)
                reviewer_outputs.append(reviewer_output)
                accepted = coordinator.record_planning_review(
                    str(review_control["round_id"]), reviewer_output
                )
                if accepted:
                    break
            self.assertTrue(accepted, reviewer_outputs)
            coordinator.complete_planning_stage()

            execution_instructions = {
                "TEST_EXECUTOR": (
                    "Persistent synthetic test executor. Use tools only for the requested "
                    "synthetic command and evidence files. Do not use Aegis-specific skills. "
                    "Return only schema-valid JSON after evidence is durable."
                ),
                "TEST_RESULT_REVIEWER": (
                    "Independent synthetic evidence reviewer. Read only the requested evidence "
                    "files. Do not use Aegis-specific skills. Return only schema-valid JSON."
                ),
                "TEST_REPORT_WRITER": (
                    "Persistent synthetic report writer. Read the accepted evidence and write "
                    "only the requested report. Do not use Aegis-specific skills. Return only "
                    "schema-valid JSON after the report is durable."
                ),
                "FINAL_REVIEWER": (
                    "Independent synthetic final reviewer. Read the requested report and source "
                    "evidence. Do not use Aegis-specific skills. Return only schema-valid JSON."
                ),
            }

            def execute_turn(
                node: str,
                role: str,
                prompt: str,
                node_state: dict[str, object],
                expected_output: dict[str, object] | None = None,
            ) -> dict[str, object]:
                def operation(input_state: dict[str, object]) -> dict[str, object]:
                    raw = coordinator.run_execution_agent(
                        role,
                        prompt,
                        output_schema=NODE_SCHEMA,
                        developer_instructions=execution_instructions[role],
                        timeout_seconds=1_800,
                    )
                    output = json.loads(raw)
                    self.assertEqual(output, expected_output or expected)
                    return {**input_state, **output, "current_node": node}

                return coordinator.execute_node(node, operation, node_state)

            first_c = execute_turn(
                "C",
                "TEST_EXECUTOR",
                (
                    'Run this exact command from project_root: `python -c "from '
                    "src.acceptance_target import ACCEPTANCE_TARGET; print(ACCEPTANCE_TARGET); "
                    'raise SystemExit(0 if ACCEPTANCE_TARGET is True else 1)"`. Write the '
                    "captured stdout and exit code to artifact_path/EXECUTION_EVIDENCE.txt. "
                    "Remember marker C-PERSISTENT-THREAD. Then return exactly this JSON object: "
                    f"{expected_json}"
                ),
                expected,
            )
            first_d = execute_turn(
                "D",
                "TEST_RESULT_REVIEWER",
                (
                    "Read artifact_path/EXECUTION_EVIDENCE.txt. Accept only when it records "
                    "stdout True and exit code 0. For this first review round, deliberately "
                    "request one retest by returning exactly this JSON object: "
                    f"{json.dumps({**expected, 'status': False}, ensure_ascii=False, separators=(',', ':'))}"
                ),
                first_c,
                {**expected, "status": False},
            )
            second_c = execute_turn(
                "C",
                "TEST_EXECUTOR",
                (
                    "This is a second turn on your persistent role. Write the marker you were "
                    "told to remember to artifact_path/THREAD_CONTINUITY.txt. Return exactly "
                    f"this JSON object: {expected_json}"
                ),
                {**first_d, "retry": 2},
            )
            second_d = execute_turn(
                "D",
                "TEST_RESULT_REVIEWER",
                (
                    "This is the second review turn on your persistent role. Re-read "
                    "artifact_path/EXECUTION_EVIDENCE.txt and accept only when it records "
                    "stdout True and exit code 0. Return exactly this JSON object when valid: "
                    f"{expected_json}"
                ),
                second_c,
            )
            reported = execute_turn(
                "E",
                "TEST_REPORT_WRITER",
                (
                    "Read artifact_path/EXECUTION_EVIDENCE.txt and write a concise final test "
                    "report to artifact_path/TEST_REPORT.md. It must state stdout True, exit "
                    "code 0, and PASS. Return exactly this JSON object after the report is "
                    f"durable: {expected_json}"
                ),
                second_d,
            )
            report_sha256 = hashlib.sha256(
                (artifact_path / "TEST_REPORT.md").read_bytes()
            ).hexdigest()
            finalized = execute_turn(
                "F",
                "FINAL_REVIEWER",
                (
                    "Independently read artifact_path/TEST_REPORT.md and "
                    "artifact_path/EXECUTION_EVIDENCE.txt. Accept only when both bind stdout "
                    "True and exit code 0 to PASS. Write artifact_path/FINAL_REVIEW.md with "
                    f"verdict PASS and the exact report SHA-256 {report_sha256}. Return exactly "
                    "this JSON object when valid: "
                    f"{expected_json}"
                ),
                reported,
            )
            coordinator.complete(finalized)

            state = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            planning_threads = {
                value["codex_thread_id"] for value in state["planning_agents"].values()
            }
            planning_turns = {item["codex_turn_id"] for item in state["planning_turns"]}
            execution_threads = {
                role: value["codex_thread_id"]
                for role, value in state["execution_agents"].items()
            }
            execution_turns = state["execution_turns"]
            self.assertEqual(len(planning_threads), 2)
            self.assertEqual(len(planning_turns), len(state["planning_rounds"]) * 2)
            self.assertEqual(len(execution_threads), 4)
            self.assertEqual(
                [item["node"] for item in state["execution_attempts"]],
                ["C", "D", "C", "D", "E", "F"],
            )
            self.assertEqual(
                [item["codex_thread_id"] for item in execution_turns],
                [
                    execution_threads["TEST_EXECUTOR"],
                    execution_threads["TEST_RESULT_REVIEWER"],
                    execution_threads["TEST_EXECUTOR"],
                    execution_threads["TEST_RESULT_REVIEWER"],
                    execution_threads["TEST_REPORT_WRITER"],
                    execution_threads["FINAL_REVIEWER"],
                ],
            )
            self.assertEqual(
                len({item["codex_turn_id"] for item in execution_turns}), 6
            )
            self.assertTrue(
                all(len(item["evidence_session_ids"]) == 1 for item in execution_turns)
            )
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["planning_stage_status"], "completed")
            self.assertEqual(state["planning_rounds"][-1]["status"], "approved")
            self.assertTrue((artifact_path / "APPROVED_TEST_PLAN.md").is_file())
            self.assertTrue((artifact_path / "PLANNING_HANDOFF.json").is_file())
            planning_evidence = [
                item
                for item in state["evidence_sessions"]
                if item["node"] == "planning"
            ]
            execution_evidence = [
                item
                for item in state["evidence_sessions"]
                if item["node"] in {"C", "D", "E", "F"}
            ]
            self.assertEqual(len(planning_evidence), 1)
            self.assertEqual(len(execution_evidence), 6)
            self.assertEqual(
                len({item["session_id"] for item in execution_evidence}), 6
            )
            self.assertEqual(
                len({item["process_pid"] for item in execution_evidence}), 6
            )
            self.assertFalse(
                any(
                    _windows_process_is_running(item["process_pid"])
                    for item in execution_evidence
                )
            )
            self.assertEqual(
                len(
                    {item["process_creation_time_100ns"] for item in execution_evidence}
                ),
                6,
            )
            self.assertTrue(
                all(
                    item["verification_status"] == "VALID_COMPLETE"
                    and item["application_verification_status"] == "VALID_COMPLETE"
                    for item in state["evidence_sessions"]
                )
            )
            self.assertTrue(
                all(
                    Path(item["raw_response_path"]).is_file()
                    for item in state["planning_turns"]
                )
            )
            self.assertTrue(
                all(
                    Path(item["raw_response_path"]).is_file()
                    for item in execution_turns
                )
            )
            self.assertEqual(
                (artifact_path / "THREAD_CONTINUITY.txt")
                .read_text(encoding="utf-8")
                .strip(),
                "C-PERSISTENT-THREAD",
            )
            report_text = (artifact_path / "TEST_REPORT.md").read_text(encoding="utf-8")
            self.assertIn("True", report_text)
            self.assertIn("0", report_text)
            self.assertIn("PASS", report_text.upper())
            final_review_text = (artifact_path / "FINAL_REVIEW.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("PASS", final_review_text.upper())
            self.assertIn(report_sha256, final_review_text.lower())

            report = {
                "schema": "aegis.app_server_control_acceptance.v3",
                "verdict": "PASS",
                "created_at_utc": stamp,
                "run_id": run_id,
                "run_state_path": str(coordinator.run_state_path),
                "codex_cli_path": state["codex_cli_path"],
                "codex_cli_version": state["codex_cli_version"],
                "planning_thread_ids": sorted(planning_threads),
                "planning_turn_ids": sorted(planning_turns),
                "execution_agents": state["execution_agents"],
                "execution_turns": execution_turns,
                "planning_rounds": state["planning_rounds"],
                "evidence_sessions": state["evidence_sessions"],
                "planning_handoff": json.loads(
                    (artifact_path / "PLANNING_HANDOFF.json").read_text(
                        encoding="utf-8"
                    )
                ),
                "source_sha256": {
                    str(path.relative_to(PROJECT_ROOT)).replace(
                        "\\", "/"
                    ): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (
                        PROJECT_ROOT / "src" / "codex_app_server_client.py",
                        PROJECT_ROOT / "src" / "tracerelay_client.py",
                        PROJECT_ROOT / "src" / "aegis_runtime.py",
                        PROJECT_ROOT / "src" / "main.py",
                    )
                },
            }
            report_path = root / "ACCEPTANCE_REPORT.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"ACCEPTANCE_REPORT={report_path}")
        except BaseException as error:
            try:
                coordinator.fail(error)
            except BaseException:
                pass
            raise
        finally:
            if owned:
                subprocess.run(
                    [tracerelay_command, "stop"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=30,
                )
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    status_result = subprocess.run(
                        [tracerelay_command, "status"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        check=False,
                        timeout=15,
                    )
                    status_raw = (
                        status_result.stdout.strip() or status_result.stderr.strip()
                    )
                    status = json.loads(status_raw.decode("utf-8", errors="replace"))
                    if status.get("state") == "NOT_RUNNING":
                        break
                    time.sleep(0.1)

    def test_hard_crash_recovers_exact_session_and_known_turn(self) -> None:
        tracerelay_command = str(Path(os.environ["TRACERELAY_COMMAND"]).resolve())
        initial = subprocess.run(
            [tracerelay_command, "status"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=15,
        )
        initial_raw = initial.stdout.strip() or initial.stderr.strip()
        initial_status = json.loads(initial_raw.decode("utf-8", errors="replace"))
        if initial_status.get("state") != "NOT_RUNNING":
            self.skipTest("TraceRelay is already running; ownership is ambiguous")

        short_id = uuid4().hex[:12]
        run_id = f"crash-{short_id}"
        root = (
            Path(
                os.environ.get(
                    "AEGIS_APP_SERVER_ACCEPTANCE_ROOT", r"C:\code\aegis_artifacts"
                )
            )
            / "as_crash_recovery"
            / short_id
        ).resolve()
        project = root / "project"
        artifact_path = root / "artifacts"
        source = project / "src" / "acceptance_target.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("ACCEPTANCE_TARGET = True\n", encoding="utf-8")
        record_project_seal(
            project,
            git_head_before_record="b" * 40,
            project_id=bytes(range(16)),
            run_id=bytes(range(16, 32)),
        )
        context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        artifact_path.mkdir(parents=True, exist_ok=True)
        context_path.write_text("{}\n", encoding="utf-8")
        state = {
            "artifact_path": str(artifact_path),
            "reasoning_ledger_context_pack": str(context_path),
            "status": True,
        }
        prompt = (
            "Return exactly one JSON object matching the output schema. Preserve "
            f"artifact_path as {artifact_path} and reasoning_ledger_context_pack as "
            f"{context_path}; set status to true. Do not use tools."
        )
        developer_instructions = (
            "You are the persistent FINAL_REVIEWER role in a deterministic crash "
            "recovery acceptance. Return only schema-valid JSON. Do not use "
            "Aegis-specific skills."
        )
        upstream_port = int(os.environ.get("TRACERELAY_UPSTREAM_PORT", "7899"))
        config = {
            "project": str(project),
            "artifact_path": str(artifact_path),
            "run_id": run_id,
            "upstream_port": upstream_port,
            "tracerelay_command": tracerelay_command,
            "state": state,
            "prompt": prompt,
            "developer_instructions": developer_instructions,
        }
        config_path = root / "CRASH_WORKER_CONFIG.json"
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        owned = False
        coordinator: RuntimeCoordinator | None = None
        try:
            crashed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(Path(__file__).resolve()),
                    "--execution-crash-worker",
                    str(config_path),
                ],
                cwd=PROJECT_ROOT,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=420,
            )
            self.assertEqual(
                crashed.returncode,
                91,
                msg=f"stdout={crashed.stdout}\nstderr={crashed.stderr}",
            )
            owned = True
            state_path = artifact_path / ".aegis" / "runs" / run_id / "RUN_STATE.json"
            interrupted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(interrupted["execution_turns"][0]["status"], "inProgress")
            old_evidence = interrupted["evidence_sessions"][0]
            self.assertEqual(old_evidence["verification_status"], "UNVERIFIED")
            self.assertIsNone(old_evidence["application_verification_status"])
            self.assertGreater(old_evidence["process_creation_time_100ns"], 0)

            relay = TraceRelayClient(
                command=tracerelay_command,
                monitor_interval_seconds=0.05,
            )
            coordinator = RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=upstream_port,
                relay_client=relay,
                start_node="F",
                prior_state=interrupted,
            )
            coordinator.preflight()

            def operation(node_state: dict[str, object]) -> dict[str, object]:
                response = coordinator.run_execution_agent(
                    "FINAL_REVIEWER",
                    prompt,
                    output_schema=NODE_SCHEMA,
                    developer_instructions=developer_instructions,
                    timeout_seconds=300,
                )
                return {**node_state, "response": response, "current_node": "F"}

            recovered = coordinator.execute_node("F", operation, state)
            coordinator.complete(recovered)
            completed = json.loads(state_path.read_text(encoding="utf-8"))
            receipt = completed["execution_turns"][0]
            evidence = completed["evidence_sessions"]
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(len(receipt["evidence_session_ids"]), 2)
            self.assertEqual(len(set(receipt["evidence_session_ids"])), 2)
            process_pids = [item["process_pid"] for item in evidence]
            process_creation_times = [
                item["process_creation_time_100ns"] for item in evidence
            ]
            self.assertEqual(len(set(process_pids)), 2)
            self.assertEqual(len(set(process_creation_times)), 2)
            self.assertFalse(
                any(_windows_process_is_running(pid) for pid in process_pids)
            )
            self.assertTrue(
                all(
                    item["verification_status"] == "VALID_COMPLETE"
                    and item["application_verification_status"] == "VALID_COMPLETE"
                    for item in evidence
                )
            )
            report = {
                "schema": "aegis.execution_crash_recovery_acceptance.v1",
                "verdict": "PASS",
                "run_id": run_id,
                "worker_exit_code": crashed.returncode,
                "codex_thread_id": receipt["codex_thread_id"],
                "codex_turn_id": receipt["codex_turn_id"],
                "evidence_session_ids": receipt["evidence_session_ids"],
                "process_pids": process_pids,
                "process_creation_times_100ns": process_creation_times,
                "processes_terminated": True,
                "source_sha256": {
                    str(path.relative_to(PROJECT_ROOT)).replace(
                        "\\", "/"
                    ): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (
                        PROJECT_ROOT / "src" / "tracerelay_client.py",
                        PROJECT_ROOT / "src" / "aegis_runtime.py",
                    )
                },
            }
            report_path = root / "CRASH_RECOVERY_REPORT.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"CRASH_RECOVERY_REPORT={report_path}")
        finally:
            if owned:
                subprocess.run(
                    [tracerelay_command, "stop"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=30,
                )
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    status_result = subprocess.run(
                        [tracerelay_command, "status"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        check=False,
                        timeout=15,
                    )
                    status_raw = (
                        status_result.stdout.strip() or status_result.stderr.strip()
                    )
                    status = json.loads(status_raw.decode("utf-8", errors="replace"))
                    if status.get("state") == "NOT_RUNNING":
                        break
                    time.sleep(0.1)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--execution-crash-worker":
        _run_execution_crash_worker(Path(sys.argv[2]).resolve())
    else:
        unittest.main()
