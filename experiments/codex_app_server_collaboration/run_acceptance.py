from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from experiments.codex_app_server_collaboration.app_server_client import (
    AppServerClient,
    resolve_codex_command,
)
from experiments.codex_app_server_collaboration.collaboration_graph import (
    CodexRoleExecutor,
    run_collaboration,
)


DEFAULT_ARTIFACT_ROOT = Path(
    r"C:\code\aegis_artifacts\app_server_collaboration_poc"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated Codex App Server multi-agent acceptance probe."
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Directory that receives durable probe evidence.",
    )
    parser.add_argument(
        "--codex-cli",
        type=Path,
        default=None,
        help="Explicit codex.cmd or codex.exe path. Defaults to PATH resolution.",
    )
    parser.add_argument(
        "--turn-timeout-seconds",
        type=float,
        default=300.0,
    )
    return parser.parse_args()


def run_acceptance(args: argparse.Namespace) -> tuple[int, Path, dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[2]
    codex_cli = (
        str(args.codex_cli.resolve())
        if args.codex_cli is not None
        else resolve_codex_command()
    )
    graph_run_id = _new_run_id()
    artifact_directory = args.artifact_root.resolve() / graph_run_id
    artifact_directory.mkdir(parents=True, exist_ok=False)
    report_path = artifact_directory / "ACCEPTANCE_REPORT.json"
    state_path = artifact_directory / "RUN_STATE.json"
    started_at = _utc_now()
    base_report: dict[str, Any] = {
        "schema_version": 1,
        "graph_run_id": graph_run_id,
        "started_at_utc": started_at,
        "project_root": str(project_root),
        "artifact_directory": str(artifact_directory),
        "codex_cli": codex_cli,
        "codex_cli_version": _command_output([codex_cli, "--version"], project_root),
        "app_server_command": [
            codex_cli,
            "app-server",
            "--listen",
            "stdio://",
        ],
        "git_branch": _git_output(project_root, "branch", "--show-current"),
        "git_head": _git_output(project_root, "rev-parse", "HEAD"),
    }
    _atomic_write_json(
        state_path,
        {
            **base_report,
            "status": "RUNNING",
            "last_checkpoint": "reserved_artifact_directory",
        },
    )

    try:
        command = tuple(base_report["app_server_command"])
        with AppServerClient(
            command=command,
            cwd=project_root,
            turn_timeout_seconds=args.turn_timeout_seconds,
        ) as client:
            graph_state = run_collaboration(
                CodexRoleExecutor(client, persistent_threads=True),
                graph_run_id=graph_run_id,
            )
            executions = _executions(graph_state)
            readable_before_restart = {
                execution["role"]: _thread_contains_turn(
                    client.read_thread(execution["codex_thread_id"]),
                    execution["codex_turn_id"],
                )
                for execution in executions
            }
            _atomic_write_json(
                state_path,
                {
                    **base_report,
                    "status": "RUNNING",
                    "last_checkpoint": "graph_completed_before_restart",
                    "graph_state": graph_state,
                    "readable_before_restart": readable_before_restart,
                },
            )

        final_execution = graph_state["final"]
        with AppServerClient(
            command=command,
            cwd=project_root,
            turn_timeout_seconds=args.turn_timeout_seconds,
        ) as resumed_client:
            resumed = resumed_client.resume_thread(
                final_execution["codex_thread_id"]
            )
            resumed_thread = resumed_client.read_thread(resumed.thread_id)
            resume_preserved_turn = _thread_contains_turn(
                resumed_thread, final_execution["codex_turn_id"]
            )

        acceptance = _acceptance_checks(
            graph_state,
            readable_before_restart=readable_before_restart,
            resumed_thread_id=resumed.thread_id,
            resume_preserved_turn=resume_preserved_turn,
        )
        verdict = "PASS" if all(acceptance.values()) else "FAIL"
        report = {
            **base_report,
            "completed_at_utc": _utc_now(),
            "verdict": verdict,
            "acceptance": acceptance,
            "graph_state": graph_state,
            "recovery": {
                "requested_codex_thread_id": final_execution["codex_thread_id"],
                "resumed_codex_thread_id": resumed.thread_id,
                "preserved_codex_turn_id": final_execution["codex_turn_id"],
                "turn_found_after_restart": resume_preserved_turn,
            },
        }
        _atomic_write_json(report_path, report)
        _atomic_write_json(
            state_path,
            {
                **base_report,
                "status": "COMPLETED" if verdict == "PASS" else "FAILED",
                "last_checkpoint": "acceptance_report_written",
                "report_path": str(report_path),
                "verdict": verdict,
            },
        )
        return (0 if verdict == "PASS" else 1), report_path, report
    except BaseException as error:
        report = {
            **base_report,
            "completed_at_utc": _utc_now(),
            "verdict": "FAIL",
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }
        _atomic_write_json(report_path, report)
        _atomic_write_json(
            state_path,
            {
                **base_report,
                "status": "FAILED",
                "last_checkpoint": "failure_report_written",
                "report_path": str(report_path),
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        return 1, report_path, report


def _acceptance_checks(
    graph_state: Mapping[str, Any],
    *,
    readable_before_restart: Mapping[str, bool],
    resumed_thread_id: str,
    resume_preserved_turn: bool,
) -> dict[str, bool]:
    executions = _executions(graph_state)
    reviews = list(graph_state["reviews"])
    producer_payload = graph_state["producer"]["payload"]
    final_payload = graph_state["final"]["payload"]
    reviewer_receipts = [
        review["payload"]["review_receipt"]
        for review in sorted(reviews, key=lambda value: value["role"])
    ]
    latest_reviewer_start = max(review["started_at"] for review in reviews)
    earliest_reviewer_completion = min(review["completed_at"] for review in reviews)
    return {
        "four_role_executions_completed": len(executions) == 4
        and all(execution["status"] == "completed" for execution in executions),
        "four_unique_codex_thread_ids": len(
            {execution["codex_thread_id"] for execution in executions}
        )
        == 4,
        "four_unique_codex_turn_ids": len(
            {execution["codex_turn_id"] for execution in executions}
        )
        == 4,
        "two_independent_reviews_received": len(reviews) == 2,
        "reviewers_overlapped_in_time": latest_reviewer_start
        < earliest_reviewer_completion,
        "producer_handoff_reached_both_reviewers": all(
            review["payload"]["handoff_token"]
            == producer_payload["handoff_token"]
            for review in reviews
        ),
        "aggregator_received_both_review_receipts": final_payload[
            "reviewer_receipts"
        ]
        == reviewer_receipts,
        "all_threads_readable_before_restart": all(
            readable_before_restart.values()
        ),
        "aggregator_thread_resumed_after_restart": resumed_thread_id
        == graph_state["final"]["codex_thread_id"],
        "aggregator_turn_readable_after_restart": resume_preserved_turn,
    }


def _executions(graph_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        graph_state["producer"],
        *sorted(graph_state["reviews"], key=lambda value: value["role"]),
        graph_state["final"],
    ]


def _thread_contains_turn(thread_read_result: Any, turn_id: str) -> bool:
    if thread_read_result == turn_id:
        return True
    if isinstance(thread_read_result, Mapping):
        return any(
            _thread_contains_turn(value, turn_id)
            for value in thread_read_result.values()
        )
    if isinstance(thread_read_result, list):
        return any(_thread_contains_turn(value, turn_id) for value in thread_read_result)
    return False


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"appserver-poc-{stamp}-{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _command_output(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: command={command!r}, exit_code={completed.returncode}, "
            f"stderr={completed.stderr!r}"
        )
    return completed.stdout.strip()


def _git_output(cwd: Path, *arguments: str) -> str:
    return _command_output(["git", *arguments], cwd)


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    exit_code, report_path, report = run_acceptance(parse_args())
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "graph_run_id": report["graph_run_id"],
                "report_path": str(report_path),
                "acceptance": report.get("acceptance"),
                "error": report.get("error"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
