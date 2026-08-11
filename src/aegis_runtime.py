from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from codex_app_server_client import (
    AppServerClient,
    TurnResult,
    default_app_server_command,
    read_codex_cli_version,
)
from project_seal_store import StoredProjectSeal, verify_expected_project_seal
from tracerelay_client import (
    EvidenceProcessResult,
    ManagedEvidenceProcess,
    TraceRelayClient,
    TraceRelayError,
    TraceRelayRegistration,
    parse_loopback_proxy_port,
    resolve_tracerelay_command,
)


RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
RESERVATION_TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}")
CHECKPOINT_RELATIVE_PATH = Path(".aegis/runtime/checkpoints.sqlite3")
RESERVATION_TABLE = "aegis_run_reservations"
RUN_STATE_SCHEMA = "aegis.run_state.v3"
PLANNING_STAGE_STATUSES = frozenset({"not_started", "active", "completed"})
PLANNING_ROUND_STATUSES = frozenset(
    {
        "allocating",
        "authoring",
        "review_pending",
        "rejected",
        "publishing",
        "approved",
    }
)
PLANNING_REVIEW_THRESHOLD = 95
EXECUTION_NODE_ROLES = {
    "C": "TEST_EXECUTOR",
    "D": "TEST_RESULT_REVIEWER",
}
EXECUTION_AGENT_STATUSES = frozenset({"allocating", "ready"})
EXECUTION_TURN_STATUSES = frozenset(
    {"preparing", "submitting", "inProgress", "completed"}
)


class RuntimeStateError(RuntimeError):
    pass


def new_run_id() -> str:
    created = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{created}_{uuid4().hex}"


_ACTIVE_COORDINATOR: ContextVar[RuntimeCoordinator | None] = ContextVar(
    "aegis_runtime_coordinator", default=None
)


class RuntimeCoordinator:
    def __init__(
        self,
        *,
        project_root: str | Path,
        artifact_path: str | Path,
        run_id: str,
        upstream_port: int,
        relay_client: TraceRelayClient,
        start_node: str,
        prior_state: Mapping[str, object] | None = None,
    ) -> None:
        if RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
            raise ValueError("run_id contains unsupported path characters")
        self.project_root = Path(project_root).resolve()
        self.artifact_path = Path(artifact_path).resolve()
        self.run_id = run_id
        self.upstream_port = upstream_port
        self.relay_client = relay_client
        self.start_node = start_node
        self.run_state_path = (
            self.artifact_path / ".aegis" / "runs" / run_id / "RUN_STATE.json"
        )
        self._created_at_utc = _utc_now_text()
        self._current_node: str | None = None
        self._last_completed_node: str | None = None
        self._last_state: dict[str, Any] | None = None
        self._seal: StoredProjectSeal | None = None
        self._evidence_sessions: list[dict[str, object]] = []
        self._planning_app_server: AppServerClient | None = None
        self._planning_process: ManagedEvidenceProcess | None = None
        self._planning_agents: dict[str, dict[str, object]] = {}
        self._planning_turns: list[dict[str, object]] = []
        self._planning_rounds: list[dict[str, object]] = []
        self._execution_agents: dict[str, dict[str, object]] = {}
        self._execution_turns: list[dict[str, object]] = []
        self._execution_attempts: list[dict[str, object]] = []
        self._active_execution_attempt: dict[str, object] | None = None
        self._planning_ready_roles: set[str] = set()
        self._planning_stage_status = "not_started"
        self._codex_cli_path: str | None = None
        self._codex_cli_version: str | None = None
        self._is_resume = prior_state is not None
        self._reservation_token: str | None = None
        self._state_writable = False
        if prior_state is not None:
            self._restore(prior_state)

    def _restore(self, state: Mapping[str, object]) -> None:
        if state.get("schema") in {"aegis.run_state.v1", "aegis.run_state.v2"}:
            raise RuntimeStateError(
                "run state predates C/D App Server transactions; start a new run"
            )
        if state.get("schema") != RUN_STATE_SCHEMA:
            raise RuntimeStateError("run state schema is unsupported")
        if state.get("run_id") != self.run_id:
            raise RuntimeStateError("prior run state identity mismatch")
        if state.get("start_node") != self.start_node:
            raise RuntimeStateError("prior run state start node mismatch")
        stored_root = state.get("project_root")
        if (
            not isinstance(stored_root, str)
            or Path(stored_root).resolve() != self.project_root
        ):
            raise RuntimeStateError("prior run state project root mismatch")
        created_at = state.get("created_at_utc")
        graph_state = state.get("graph_state")
        evidence = state.get("evidence_sessions")
        planning_agents = state.get("planning_agents", {})
        planning_turns = state.get("planning_turns", [])
        planning_rounds = state.get("planning_rounds")
        execution_agents = state.get("execution_agents")
        execution_turns = state.get("execution_turns")
        execution_attempts = state.get("execution_attempts")
        codex_cli_path = state.get("codex_cli_path")
        codex_cli_version = state.get("codex_cli_version")
        planning_stage_status = state.get("planning_stage_status")
        reservation_token = state.get("reservation_token")
        if not isinstance(created_at, str) or not created_at:
            raise RuntimeStateError("prior run state has no creation time")
        if graph_state is not None and not isinstance(graph_state, dict):
            raise RuntimeStateError("prior run graph state must be an object or null")
        if not isinstance(evidence, list) or not all(
            isinstance(x, dict) for x in evidence
        ):
            raise RuntimeStateError("prior evidence sessions must be a list of objects")
        _validate_execution_evidence_records(evidence)
        if not isinstance(planning_agents, dict) or not all(
            isinstance(role, str) and isinstance(value, dict)
            for role, value in planning_agents.items()
        ):
            raise RuntimeStateError("prior planning agents must be an object")
        if not isinstance(planning_turns, list) or not all(
            isinstance(item, dict) for item in planning_turns
        ):
            raise RuntimeStateError("prior planning turns must be a list of objects")
        _validate_planning_turns(planning_turns)
        if not isinstance(planning_rounds, list) or not all(
            isinstance(item, dict) for item in planning_rounds
        ):
            raise RuntimeStateError("prior planning rounds must be a list of objects")
        _validate_planning_rounds(planning_rounds)
        if not isinstance(execution_agents, dict) or not all(
            isinstance(role, str) and isinstance(value, dict)
            for role, value in execution_agents.items()
        ):
            raise RuntimeStateError("prior execution agents must be an object")
        _validate_execution_agents(execution_agents)
        if not isinstance(execution_turns, list) or not all(
            isinstance(item, dict) for item in execution_turns
        ):
            raise RuntimeStateError("prior execution turns must be a list of objects")
        _validate_execution_turns(execution_turns)
        if not isinstance(execution_attempts, list) or not all(
            isinstance(item, dict) for item in execution_attempts
        ):
            raise RuntimeStateError(
                "prior execution attempts must be a list of objects"
            )
        _validate_execution_attempts(execution_attempts)
        _validate_execution_bindings(
            execution_attempts,
            execution_agents,
            execution_turns,
            evidence,
            run_id=self.run_id,
        )
        if codex_cli_path is not None and not isinstance(codex_cli_path, str):
            raise RuntimeStateError("prior Codex CLI path must be a string or null")
        if codex_cli_version is not None and not isinstance(codex_cli_version, str):
            raise RuntimeStateError("prior Codex CLI version must be a string or null")
        if planning_stage_status not in PLANNING_STAGE_STATUSES:
            raise RuntimeStateError("prior planning stage status is invalid")
        if (
            not isinstance(reservation_token, str)
            or RESERVATION_TOKEN_PATTERN.fullmatch(reservation_token) is None
        ):
            raise RuntimeStateError("prior run state has an invalid reservation token")
        self._created_at_utc = created_at
        self._current_node = _optional_string(state.get("current_node"))
        self._last_completed_node = _optional_string(state.get("last_completed_node"))
        self._last_state = dict(graph_state) if graph_state is not None else None
        self._evidence_sessions = [dict(item) for item in evidence]
        self._planning_agents = {
            str(role): dict(value) for role, value in planning_agents.items()
        }
        self._planning_turns = [dict(item) for item in planning_turns]
        self._planning_rounds = [dict(item) for item in planning_rounds]
        self._execution_agents = {
            str(role): dict(value) for role, value in execution_agents.items()
        }
        self._execution_turns = [dict(item) for item in execution_turns]
        self._execution_attempts = [dict(item) for item in execution_attempts]
        if (
            self._execution_attempts
            and self._execution_attempts[-1].get("status") == "running"
            and state.get("current_node") != self._execution_attempts[-1].get("node")
        ):
            raise RuntimeStateError(
                "running execution attempt does not match the current node"
            )
        self._codex_cli_path = codex_cli_path
        self._codex_cli_version = codex_cli_version
        self._planning_stage_status = str(planning_stage_status)
        self._reservation_token = reservation_token

    @property
    def planning_stage_status(self) -> str:
        return self._planning_stage_status

    def preflight(self) -> None:
        self._seal = verify_expected_project_seal(self.project_root)
        try:
            if self._is_resume:
                assert self._reservation_token is not None
                _validate_run_reservation(
                    self.project_root,
                    self.artifact_path,
                    self.run_id,
                    self._reservation_token,
                )
                self._state_writable = True
            else:
                reservation_token = uuid4().hex
                payload = self._build_state_payload(
                    "reserved", reservation_token=reservation_token
                )
                _reserve_new_run(
                    self.project_root,
                    self.run_state_path,
                    self.run_id,
                    reservation_token,
                    payload,
                )
                self._reservation_token = reservation_token
                self._state_writable = True
            if self._planning_stage_status == "completed":
                self._validate_completed_planning_stage()
            self._validate_persisted_execution_receipt_cache()
            self._recover_persisted_execution_sessions()
            self.relay_client.start()
            self._validate_persisted_execution_receipts()
        except BaseException as error:
            if self._state_writable:
                self._write_state("failed", error)
            raise
        self._write_state("ready")

    def execute_node(
        self,
        node_name: str,
        operation: Callable[[dict[str, Any]], dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        self._current_node = node_name
        self._last_state = dict(state)
        execution_attempt: dict[str, object] | None = None
        if node_name in EXECUTION_NODE_ROLES:
            execution_attempt = self._begin_execution_attempt(node_name, state)
            self._active_execution_attempt = execution_attempt
        self._write_state("running")
        token = _ACTIVE_COORDINATOR.set(self)
        try:
            result = operation(state)
        except BaseException as error:
            self._write_state("failed", error)
            raise
        finally:
            _ACTIVE_COORDINATOR.reset(token)
            self._active_execution_attempt = None
        try:
            if execution_attempt is not None:
                output_sha256 = _state_sha256(result)
                if execution_attempt["status"] == "completed":
                    if execution_attempt.get("output_sha256") != output_sha256:
                        raise RuntimeStateError(
                            "replayed execution attempt produced a different graph state"
                        )
                else:
                    execution_attempt.update(
                        status="completed",
                        output_sha256=output_sha256,
                    )
        except BaseException as error:
            self._write_state("failed", error)
            raise
        self._last_completed_node = node_name
        self._current_node = None
        self._last_state = dict(result)
        self._write_state("running")
        return result

    def run_codex_process(
        self, command: Sequence[str], *, timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self.relay_client.run_process(
                command,
                upstream_port=self.upstream_port,
                timeout_seconds=timeout_seconds,
            )
        except BaseException:
            registration = getattr(self.relay_client, "last_registration", None)
            if isinstance(registration, TraceRelayRegistration):
                verification = getattr(self.relay_client, "last_verification", None)
                self._record_evidence(
                    registration,
                    verification if isinstance(verification, Mapping) else None,
                )
                self._write_state("running")
            raise
        self._record_evidence(result.registration, result.verification)
        self._write_state("running")
        return result.completed

    def run_execution_agent(
        self,
        role_key: str,
        prompt: str,
        *,
        output_schema: Mapping[str, Any],
        developer_instructions: str,
        timeout_seconds: float,
    ) -> str:
        attempt = self._active_execution_attempt
        if attempt is None:
            raise RuntimeStateError(
                "execution agent turns require an active C or D node attempt"
            )
        node = attempt.get("node")
        if EXECUTION_NODE_ROLES.get(str(node)) != role_key:
            raise RuntimeStateError("execution role does not match the active node")
        if not developer_instructions:
            raise ValueError("execution developer instructions must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("execution timeout_seconds must be positive")

        job_id = str(attempt["job_id"])
        request_sha256 = _planning_request_sha256(prompt, output_schema)
        instructions_sha256 = hashlib.sha256(
            developer_instructions.encode("utf-8")
        ).hexdigest()
        agent = self._execution_agents.get(role_key)
        if agent is not None:
            if agent.get("developer_instructions_sha256") != instructions_sha256:
                raise RuntimeStateError(
                    "execution developer instructions changed for a persistent role"
                )
            if agent.get("status") == "allocating":
                raise RuntimeStateError(
                    "execution thread allocation outcome is unknown; refusing replacement"
                )
        receipt = self._execution_turn_for_job(job_id)
        if receipt is not None:
            self._require_matching_execution_request(
                receipt,
                role_key=role_key,
                request_sha256=request_sha256,
                instructions_sha256=instructions_sha256,
            )
            if receipt.get("status") == "completed":
                self._require_execution_receipt_evidence(receipt)
                return self._read_completed_execution_response(receipt)
            if receipt.get("status") == "submitting":
                raise RuntimeStateError(
                    "execution turn submission outcome is unknown; refusing resubmission"
                )
            self._require_execution_receipt_evidence(
                receipt,
                allow_empty=receipt.get("status") == "preparing",
            )
        else:
            receipt = {
                "attempt_id": attempt["attempt_id"],
                "job_id": job_id,
                "node": node,
                "role": role_key,
                "client_message_id": f"{job_id}:submission",
                "request_sha256": request_sha256,
                "developer_instructions_sha256": instructions_sha256,
                "codex_thread_id": None,
                "codex_turn_id": None,
                "status": "preparing",
                "raw_response_path": None,
                "raw_response_sha256": None,
                "evidence_session_ids": [],
            }
            self._execution_turns.append(receipt)
            self._write_state("running")

        command = default_app_server_command()
        cli_path = str(Path(command[0]).resolve())
        cli_version = read_codex_cli_version(command[0])
        if (
            self._codex_cli_version is not None
            and self._codex_cli_version != cli_version
        ):
            raise RuntimeStateError(
                "Codex CLI version changed since this run was created: "
                f"saved={self._codex_cli_version!r}, current={cli_version!r}"
            )
        self._codex_cli_path = cli_path
        self._codex_cli_version = cli_version
        self._write_state("running")

        process: ManagedEvidenceProcess | None = None

        def process_factory(
            process_command: Sequence[str], **popen_options: object
        ) -> ManagedEvidenceProcess:
            nonlocal process
            if process is not None:
                raise RuntimeStateError("execution App Server process already exists")
            process = self.relay_client.open_managed_process(
                process_command,
                upstream_port=self.upstream_port,
                **popen_options,
            )
            session_ids = receipt["evidence_session_ids"]
            assert isinstance(session_ids, list)
            session_ids.append(process.registration.session_id)
            self._record_evidence(
                process.registration,
                None,
                node=str(node),
                process_pid=process.pid,
                process_creation_time_100ns=process.creation_time_100ns,
            )
            self._write_state("running")
            return process

        client = AppServerClient(
            cwd=self.project_root,
            command=command,
            process_factory=process_factory,
            turn_timeout_seconds=timeout_seconds,
        )
        primary: BaseException | None = None
        try:
            client.start()
            thread_id = self._ensure_execution_thread(
                client,
                receipt,
                role_key=role_key,
                developer_instructions=developer_instructions,
                instructions_sha256=instructions_sha256,
            )
            status = receipt.get("status")
            if status == "preparing":
                receipt.update(
                    codex_thread_id=thread_id,
                    status="submitting",
                )
                self._write_state("running")
                turn = client.start_turn(
                    thread_id,
                    prompt,
                    output_schema=output_schema,
                    client_message_id=str(receipt["client_message_id"]),
                )
                if turn.thread_id != thread_id:
                    raise RuntimeStateError(
                        "turn/start returned a different execution thread"
                    )
                receipt.update(
                    codex_thread_id=turn.thread_id,
                    codex_turn_id=turn.turn_id,
                    status="inProgress",
                )
                self._write_state("running")
                result = client.wait_turn(turn, timeout_seconds=timeout_seconds)
            elif status == "inProgress":
                pending_thread = receipt.get("codex_thread_id")
                pending_turn = receipt.get("codex_turn_id")
                if pending_thread != thread_id or not isinstance(pending_turn, str):
                    raise RuntimeStateError("pending execution turn identity mismatch")
                result = client.recover_turn(thread_id, pending_turn)
            else:
                raise RuntimeStateError("execution turn has an invalid pending status")
            self._complete_execution_turn(receipt, result)
        except BaseException as error:
            primary = error

        try:
            self._finish_execution_process(client, process, node=str(node))
        except BaseException as cleanup_error:
            if primary is None:
                primary = cleanup_error
            else:
                primary.add_note(
                    f"execution App Server cleanup also failed: {cleanup_error}"
                )
        if primary is not None:
            raise primary

        self._require_execution_receipt_evidence(receipt)
        return self._read_completed_execution_response(receipt)

    def run_planning_agent(
        self,
        role_key: str,
        prompt: str,
        *,
        output_schema: Mapping[str, Any],
        developer_instructions: str,
        job_id: str | None = None,
    ) -> str:
        if not role_key:
            raise ValueError("planning role_key must not be empty")
        client = self._ensure_planning_app_server()
        thread_id = self._ensure_planning_thread(
            role_key, developer_instructions=developer_instructions
        )
        resolved_job_id = job_id or f"{self.run_id}:planning"
        request_sha256 = _planning_request_sha256(prompt, output_schema)
        completed = self._completed_planning_turn(role_key, resolved_job_id)
        if completed is not None:
            self._require_matching_planning_request(completed, request_sha256)
            return self._read_completed_planning_response(completed)
        pending = self._pending_planning_turn(role_key, resolved_job_id)
        if pending is None:
            client_message_id = f"{resolved_job_id}:{role_key}:submission"
            pending = {
                "job_id": resolved_job_id,
                "node": self._current_node,
                "role": role_key,
                "client_message_id": client_message_id,
                "request_sha256": request_sha256,
                "codex_thread_id": thread_id,
                "codex_turn_id": None,
                "status": "submitting",
                "raw_response_path": None,
                "raw_response_sha256": None,
            }
            self._planning_turns.append(pending)
            self._write_state("running")
            turn = client.start_turn(
                thread_id,
                prompt,
                output_schema=output_schema,
                client_message_id=client_message_id,
            )
            if turn.thread_id != thread_id:
                raise RuntimeStateError(
                    "turn/start returned a different planning thread"
                )
            pending.update(
                codex_thread_id=turn.thread_id,
                codex_turn_id=turn.turn_id,
                status="inProgress",
            )
            self._write_state("running")
            result = client.wait_turn(turn)
        else:
            self._require_matching_planning_request(pending, request_sha256)
            if pending.get("status") == "submitting":
                raise RuntimeStateError(
                    "planning turn submission outcome is unknown; refusing resubmission"
                )
            pending_thread = pending.get("codex_thread_id")
            pending_turn = pending.get("codex_turn_id")
            if pending_thread != thread_id or not isinstance(pending_turn, str):
                raise RuntimeStateError("pending planning turn identity mismatch")
            result = client.recover_turn(thread_id, pending_turn)
        return self._complete_planning_turn(pending, result)

    def prepare_planning_agents(self, role_instructions: Mapping[str, str]) -> None:
        if not role_instructions:
            raise ValueError("at least one planning role is required")
        self._ensure_planning_app_server()
        for role_key, instructions in role_instructions.items():
            if not role_key or not instructions:
                raise ValueError("planning roles require instructions")
            self._ensure_planning_thread(role_key, developer_instructions=instructions)

    def prepare_planning_author(
        self, context_pack_path: str | Path
    ) -> dict[str, object]:
        if self._seal is None:
            raise RuntimeStateError("planning handoff requires a verified project seal")
        context_path = Path(context_pack_path).resolve()
        context_bytes = _read_required_file(context_path, "reasoning context pack")
        context_sha256 = hashlib.sha256(context_bytes).hexdigest()
        if self._planning_rounds:
            self._validate_closed_planning_rounds()
            current = self._planning_rounds[-1]
            status = current["status"]
            if status in {"allocating", "authoring", "review_pending", "rejected"}:
                if current["context_pack_path"] != str(context_path):
                    raise RuntimeStateError(
                        "planning context path changed during an active round"
                    )
                if current["context_pack_sha256"] != context_sha256:
                    raise RuntimeStateError(
                        "planning context changed during an active round"
                    )
            if status == "allocating":
                self._finish_round_allocation(current)
                status = "authoring"
            if status in {"authoring", "review_pending"}:
                self._validate_planning_project_seal(current)
                if status == "review_pending":
                    self._validate_frozen_plan(current)
                return self._author_control(
                    current,
                    skip_turn=status == "review_pending",
                )
            if status in {"publishing", "approved"}:
                raise RuntimeStateError("planning handoff is already approved")

        round_id = f"round-{len(self._planning_rounds) + 1:04d}"
        round_directory = (
            self.artifact_path / ".aegis" / "planning" / self.run_id / round_id
        )
        record: dict[str, object] = {
            "round_id": round_id,
            "status": "allocating",
            "project_seal": self._seal.expected_seal,
            "context_pack_path": str(context_path),
            "context_pack_sha256": context_sha256,
            "plan_path": str((round_directory / "TEST_PLAN.md").resolve()),
            "plan_sha256": None,
            "review_report_path": str(
                (round_directory / "TEST_PLAN_REVIEW.md").resolve()
            ),
            "review_report_sha256": None,
            "reviewed_plan_sha256": None,
            "score": None,
            "error_count": None,
            "warning_count": None,
            "verdict": None,
            "created_at_utc": _utc_now_text(),
        }
        self._planning_rounds.append(record)
        self._write_state("running")
        self._finish_round_allocation(record)
        return self._author_control(record, skip_turn=False)

    def freeze_planning_plan(self, round_id: str) -> dict[str, object]:
        record = self._current_planning_round(round_id)
        self._validate_closed_planning_rounds(exclude_round_id=round_id)
        self._validate_planning_context(record)
        self._validate_planning_project_seal(record)
        if record["status"] == "review_pending":
            self._validate_frozen_plan(record)
            return dict(record)
        if record["status"] != "authoring":
            raise RuntimeStateError("only an authoring round can be frozen")
        plan_path = Path(str(record["plan_path"]))
        plan_bytes = _read_required_file(plan_path, "test plan")
        record["plan_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
        record["status"] = "review_pending"
        record["frozen_at_utc"] = _utc_now_text()
        self._write_state("running")
        return dict(record)

    def prepare_planning_review(self) -> dict[str, object]:
        if not self._planning_rounds:
            raise RuntimeStateError("planning review has no authored round")
        record = self._planning_rounds[-1]
        status = record["status"]
        if status not in {"review_pending", "rejected", "publishing", "approved"}:
            raise RuntimeStateError("planning review requires a frozen plan")
        self._validate_closed_planning_rounds(exclude_round_id=str(record["round_id"]))
        self._validate_planning_context(record)
        self._validate_planning_project_seal(record)
        self._validate_frozen_plan(record)
        if status in {"rejected", "publishing", "approved"}:
            self._validate_review_report(record)
            self._validate_review_decision(record)
        if status == "publishing":
            self._finish_planning_publication(record)
            status = "approved"
        if status == "approved":
            self._validate_published_planning_handoff(record)
        return {
            "schema": "aegis.planning_review_control.v1",
            "run_id": self.run_id,
            "round_id": record["round_id"],
            "job_id": f"{self.run_id}:planning:{record['round_id']}:review",
            "project_root": str(self.project_root),
            "project_seal": record["project_seal"],
            "context_pack_path": record["context_pack_path"],
            "context_pack_sha256": record["context_pack_sha256"],
            "plan_path": record["plan_path"],
            "reviewed_plan_sha256": record["plan_sha256"],
            "review_report_path": record["review_report_path"],
            "acceptance_threshold": PLANNING_REVIEW_THRESHOLD,
            "instructions": (
                "Review only plan_path at reviewed_plan_sha256. Write the complete "
                "review to review_report_path. Return reviewed_plan_sha256, score, "
                "error_count, warning_count, and verdict. Do not modify the plan or "
                "any prior round."
            ),
            "skip_turn": status in {"rejected", "approved"},
            "accepted": status == "approved",
        }

    def record_planning_review(
        self, round_id: str, node_output: Mapping[str, object]
    ) -> bool:
        record = self._current_planning_round(round_id)
        if record["status"] != "review_pending":
            raise RuntimeStateError("planning round is not awaiting review")
        self._validate_closed_planning_rounds(exclude_round_id=round_id)
        self._validate_planning_context(record)
        self._validate_planning_project_seal(record)
        self._validate_frozen_plan(record)
        reviewed_plan_sha256 = _require_sha256(
            node_output.get("reviewed_plan_sha256"), "reviewed_plan_sha256"
        )
        if reviewed_plan_sha256 != record["plan_sha256"]:
            raise RuntimeStateError("reviewed plan SHA-256 does not match frozen plan")
        score = _require_bounded_integer(node_output.get("score"), "score", 0, 100)
        error_count = _require_bounded_integer(
            node_output.get("error_count"), "error_count", 0, None
        )
        warning_count = _require_bounded_integer(
            node_output.get("warning_count"), "warning_count", 0, None
        )
        verdict = node_output.get("verdict")
        if verdict not in {"PASS", "FAIL"}:
            raise RuntimeStateError("planning review verdict must be PASS or FAIL")
        report_path = Path(str(record["review_report_path"]))
        report_bytes = _read_required_file(report_path, "planning review report")
        accepted = (
            verdict == "PASS"
            and score >= PLANNING_REVIEW_THRESHOLD
            and error_count == 0
        )
        record.update(
            status="publishing" if accepted else "rejected",
            review_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
            reviewed_plan_sha256=reviewed_plan_sha256,
            score=score,
            error_count=error_count,
            warning_count=warning_count,
            verdict=verdict,
            reviewed_at_utc=_utc_now_text(),
        )
        if accepted:
            approved_path, handoff_path = self._expected_planning_handoff_paths()
            record["approved_plan_path"] = str(approved_path)
            record["handoff_path"] = str(handoff_path)
        self._write_state("running")
        if accepted:
            self._finish_planning_publication(record)
        return accepted

    def _author_control(
        self,
        record: Mapping[str, object],
        *,
        skip_turn: bool,
    ) -> dict[str, object]:
        previous: Mapping[str, object] | None = None
        for index, candidate in enumerate(self._planning_rounds):
            if candidate.get("round_id") == record.get("round_id") and index > 0:
                previous = self._planning_rounds[index - 1]
                break
        return {
            "schema": "aegis.planning_author_control.v1",
            "run_id": self.run_id,
            "round_id": record["round_id"],
            "job_id": f"{self.run_id}:planning:{record['round_id']}:author",
            "project_root": str(self.project_root),
            "project_seal": record["project_seal"],
            "context_pack_path": record["context_pack_path"],
            "context_pack_sha256": record["context_pack_sha256"],
            "plan_path": record["plan_path"],
            "previous_review_report_path": (
                previous["review_report_path"] if previous is not None else None
            ),
            "previous_review_report_sha256": (
                previous["review_report_sha256"] if previous is not None else None
            ),
            "instructions": (
                "Write the complete test plan to plan_path. If a previous review path "
                "is present, address all of it in one revision. Do not modify any prior "
                "round. Return only the node-message JSON after the file is durable."
            ),
            "skip_turn": skip_turn,
        }

    def _finish_round_allocation(self, record: dict[str, object]) -> None:
        if record.get("status") != "allocating":
            raise RuntimeStateError("planning round is not awaiting allocation")
        round_directory = Path(str(record["plan_path"])).parent
        try:
            if round_directory.exists():
                if not round_directory.is_dir() or any(round_directory.iterdir()):
                    raise RuntimeStateError(
                        f"allocating planning round contains unknown content: {round_directory}"
                    )
            else:
                round_directory.mkdir(parents=True, exist_ok=False)
        except RuntimeStateError:
            raise
        except OSError as error:
            raise RuntimeStateError(
                f"cannot allocate planning round directory: {round_directory}: {error}"
            ) from error
        record["status"] = "authoring"
        self._write_state("running")

    def _current_planning_round(self, round_id: str) -> dict[str, object]:
        if not self._planning_rounds:
            raise RuntimeStateError("planning round does not exist")
        record = self._planning_rounds[-1]
        if record.get("round_id") != round_id:
            raise RuntimeStateError("planning round identity mismatch")
        return record

    def _validate_frozen_plan(self, record: Mapping[str, object]) -> None:
        expected = _require_sha256(record.get("plan_sha256"), "plan_sha256")
        actual = hashlib.sha256(
            _read_required_file(Path(str(record["plan_path"])), "frozen test plan")
        ).hexdigest()
        if actual != expected:
            raise RuntimeStateError("test plan changed after it was frozen")

    def _validate_planning_context(self, record: Mapping[str, object]) -> None:
        expected = _require_sha256(
            record.get("context_pack_sha256"), "context_pack_sha256"
        )
        actual = hashlib.sha256(
            _read_required_file(
                Path(str(record["context_pack_path"])), "reasoning context pack"
            )
        ).hexdigest()
        if actual != expected:
            raise RuntimeStateError("reasoning context changed during planning review")

    def _validate_planning_project_seal(self, record: Mapping[str, object]) -> None:
        current = verify_expected_project_seal(self.project_root)
        if current.expected_seal != record.get("project_seal"):
            raise RuntimeStateError("project seal changed during planning review")

    def _validate_review_report(self, record: Mapping[str, object]) -> None:
        expected = _require_sha256(
            record.get("review_report_sha256"), "review_report_sha256"
        )
        actual = hashlib.sha256(
            _read_required_file(
                Path(str(record["review_report_path"])), "planning review report"
            )
        ).hexdigest()
        if actual != expected:
            raise RuntimeStateError("planning review report changed after review")

    def _validate_closed_planning_rounds(
        self, *, exclude_round_id: str | None = None
    ) -> None:
        for record in self._planning_rounds:
            if record.get("round_id") == exclude_round_id:
                continue
            status = record.get("status")
            if status not in {"rejected", "approved"}:
                continue
            self._validate_planning_context(record)
            self._validate_planning_project_seal(record)
            self._validate_frozen_plan(record)
            self._validate_review_report(record)
            self._validate_review_decision(record)
            if status == "approved":
                self._validate_published_planning_handoff(record)

    def _validate_completed_planning_stage(self) -> None:
        if (
            not self._planning_rounds
            or self._planning_rounds[-1].get("status") != "approved"
        ):
            raise RuntimeStateError("completed planning stage has no approved handoff")
        self._validate_all_planning_evidence_complete()
        self._validate_closed_planning_rounds()

    def _validate_review_decision(self, record: Mapping[str, object]) -> None:
        if record.get("reviewed_plan_sha256") != record.get("plan_sha256"):
            raise RuntimeStateError("reviewed plan SHA-256 does not match frozen plan")
        accepted = _planning_review_is_accepted(record)
        status = record.get("status")
        if status == "rejected" and accepted:
            raise RuntimeStateError("rejected planning round satisfies approval rules")
        if status in {"publishing", "approved"} and not accepted:
            raise RuntimeStateError("approved planning round violates approval rules")

    def _expected_planning_handoff_paths(self) -> tuple[Path, Path]:
        return (
            (self.artifact_path / "APPROVED_TEST_PLAN.md").resolve(),
            (self.artifact_path / "PLANNING_HANDOFF.json").resolve(),
        )

    def _planning_handoff_payload(
        self, record: Mapping[str, object]
    ) -> dict[str, object]:
        approved_path, _handoff_path = self._expected_planning_handoff_paths()
        return {
            "schema": "aegis.planning_handoff.v1",
            "run_id": self.run_id,
            "round_id": record["round_id"],
            "project_seal": record["project_seal"],
            "context_pack_path": record["context_pack_path"],
            "context_pack_sha256": record["context_pack_sha256"],
            "approved_plan_path": str(approved_path),
            "approved_plan_sha256": record["plan_sha256"],
            "reviewed_plan_sha256": record["reviewed_plan_sha256"],
            "review_report_path": record["review_report_path"],
            "review_report_sha256": record["review_report_sha256"],
            "score": record["score"],
            "error_count": record["error_count"],
            "warning_count": record["warning_count"],
            "verdict": record["verdict"],
        }

    def _finish_planning_publication(self, record: dict[str, object]) -> None:
        if record.get("status") != "publishing":
            raise RuntimeStateError("planning round is not awaiting publication")
        self._validate_planning_context(record)
        self._validate_planning_project_seal(record)
        self._validate_frozen_plan(record)
        self._validate_review_report(record)
        self._validate_review_decision(record)
        self._publish_approved_planning_handoff(record)
        self._validate_published_planning_handoff(record)
        record["status"] = "approved"
        self._write_state("running")

    def _publish_approved_planning_handoff(self, record: dict[str, object]) -> None:
        plan_bytes = _read_required_file(
            Path(str(record["plan_path"])), "frozen test plan"
        )
        approved_path, handoff_path = self._expected_planning_handoff_paths()
        if record.get("approved_plan_path") != str(approved_path) or record.get(
            "handoff_path"
        ) != str(handoff_path):
            raise RuntimeStateError("planning publication paths are inconsistent")
        _atomic_write_bytes(approved_path, plan_bytes)
        approved_sha256 = hashlib.sha256(plan_bytes).hexdigest()
        if approved_sha256 != record["plan_sha256"]:
            raise RuntimeStateError("approved test plan does not match frozen plan")
        _atomic_write_json(handoff_path, self._planning_handoff_payload(record))

    def _validate_published_planning_handoff(
        self, record: Mapping[str, object]
    ) -> None:
        approved_path, handoff_path = self._expected_planning_handoff_paths()
        if record.get("approved_plan_path") != str(approved_path) or record.get(
            "handoff_path"
        ) != str(handoff_path):
            raise RuntimeStateError("planning publication paths are inconsistent")
        approved_sha256 = hashlib.sha256(
            _read_required_file(approved_path, "approved test plan")
        ).hexdigest()
        if approved_sha256 != record.get("plan_sha256"):
            raise RuntimeStateError("approved test plan does not match frozen plan")
        try:
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeStateError(
                f"cannot read planning handoff: {handoff_path}: {error}"
            ) from error
        if handoff != self._planning_handoff_payload(record):
            raise RuntimeStateError("planning handoff does not match approved round")

    def complete_planning_stage(self) -> None:
        if (
            not self._planning_rounds
            or self._planning_rounds[-1]["status"] != "approved"
        ):
            raise RuntimeStateError("planning stage has no approved handoff")
        current = self._planning_rounds[-1]
        self._validate_frozen_plan(current)
        self._validate_planning_context(current)
        self._validate_planning_project_seal(current)
        self._validate_review_report(current)
        self._validate_review_decision(current)
        self._validate_published_planning_handoff(current)
        self._validate_closed_planning_rounds()
        self._finish_planning_stage(mark_completed=True)

    def finish_planning_stage(self) -> None:
        self._finish_planning_stage(mark_completed=False)

    def _finish_planning_stage(self, *, mark_completed: bool) -> None:
        client = self._planning_app_server
        process = self._planning_process
        if client is None and process is None:
            if mark_completed and self._planning_stage_status != "completed":
                raise RuntimeStateError(
                    "planning stage cannot complete without an active traced process"
                )
            return
        primary: BaseException | None = None
        if client is not None:
            try:
                client.close()
            except BaseException as error:
                primary = error
        verification: Mapping[str, object] | None = None
        application_verification_status = "INVALID"
        if process is not None:
            try:
                verification = process.finalize()
                application_verification_status = "VALID_COMPLETE"
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(
                        f"planning evidence finalization also failed: {error}"
                    )
                last_verification = getattr(
                    self.relay_client, "last_verification", None
                )
                if isinstance(last_verification, Mapping):
                    verification = last_verification
            self._record_evidence(
                process.registration,
                verification,
                node="planning",
                application_verification_status=application_verification_status,
            )
        self._planning_app_server = None
        self._planning_process = None
        self._planning_ready_roles.clear()
        if primary is None and mark_completed:
            try:
                self._validate_all_planning_evidence_complete()
            except BaseException as error:
                primary = error
            else:
                self._planning_stage_status = "completed"
        self._write_state("running")
        if primary is not None:
            raise primary

    def _validate_all_planning_evidence_complete(self) -> None:
        planning_evidence = [
            entry
            for entry in self._evidence_sessions
            if entry.get("node") == "planning"
        ]
        if not planning_evidence:
            raise RuntimeStateError(
                "completed planning stage has no verified TraceRelay evidence"
            )
        if any(
            entry.get("verification_status") != "VALID_COMPLETE"
            or entry.get("application_verification_status") != "VALID_COMPLETE"
            for entry in planning_evidence
        ):
            raise RuntimeStateError("planning stage has incomplete TraceRelay evidence")

    def _begin_execution_attempt(
        self, node: str, state: Mapping[str, Any]
    ) -> dict[str, object]:
        input_sha256 = _state_sha256(state)
        latest = self._execution_attempts[-1] if self._execution_attempts else None
        if latest is not None and latest.get("node") == node:
            if latest.get("input_sha256") != input_sha256:
                raise RuntimeStateError(
                    "the same execution node was re-entered with different state"
                )
            return latest
        if latest is not None and latest.get("status") != "completed":
            raise RuntimeStateError(
                "a new execution node cannot start while the prior attempt is incomplete"
            )
        sequence = len(self._execution_attempts) + 1
        attempt_id = f"attempt-{sequence:04d}"
        attempt = {
            "attempt_id": attempt_id,
            "job_id": f"{self.run_id}:execution:{attempt_id}",
            "node": node,
            "role": EXECUTION_NODE_ROLES[node],
            "input_sha256": input_sha256,
            "status": "running",
            "output_sha256": None,
        }
        self._execution_attempts.append(attempt)
        return attempt

    def _execution_turn_for_job(self, job_id: str) -> dict[str, object] | None:
        for receipt in reversed(self._execution_turns):
            if receipt.get("job_id") == job_id:
                return receipt
        return None

    def _require_matching_execution_request(
        self,
        receipt: Mapping[str, object],
        *,
        role_key: str,
        request_sha256: str,
        instructions_sha256: str,
    ) -> None:
        if receipt.get("role") != role_key:
            raise RuntimeStateError("execution turn role changed during recovery")
        if receipt.get("request_sha256") != request_sha256:
            raise RuntimeStateError("execution turn request changed during recovery")
        if receipt.get("developer_instructions_sha256") != instructions_sha256:
            raise RuntimeStateError(
                "execution developer instructions changed during recovery"
            )

    def _ensure_execution_thread(
        self,
        client: AppServerClient,
        receipt: dict[str, object],
        *,
        role_key: str,
        developer_instructions: str,
        instructions_sha256: str,
    ) -> str:
        existing = self._execution_agents.get(role_key)
        if existing is None:
            existing = {
                "status": "allocating",
                "developer_instructions_sha256": instructions_sha256,
                "codex_thread_id": None,
                "model": None,
                "reasoning_effort": None,
            }
            self._execution_agents[role_key] = existing
            self._write_state("running")
            handle = client.start_thread(
                ephemeral=False,
                sandbox="danger-full-access",
                approval_policy="never",
                developer_instructions=developer_instructions,
            )
            existing.update(
                status="ready",
                codex_thread_id=handle.thread_id,
                model=handle.model,
                reasoning_effort=handle.reasoning_effort,
            )
        else:
            if existing.get("status") != "ready":
                raise RuntimeStateError(
                    "execution thread allocation outcome is unknown; refusing replacement"
                )
            thread_id = existing.get("codex_thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeStateError("saved execution agent has no Codex thread ID")
            handle = client.resume_thread(
                thread_id,
                sandbox="danger-full-access",
                approval_policy="never",
            )
            existing.update(
                model=handle.model,
                reasoning_effort=handle.reasoning_effort,
            )
        if any(
            other_role != role_key
            and other.get("status") == "ready"
            and other.get("codex_thread_id") == handle.thread_id
            for other_role, other in self._execution_agents.items()
        ):
            raise RuntimeStateError(
                "execution roles cannot share one persistent Codex thread"
            )
        saved_thread = receipt.get("codex_thread_id")
        if saved_thread is not None and saved_thread != handle.thread_id:
            raise RuntimeStateError("execution turn changed persistent thread identity")
        receipt["codex_thread_id"] = handle.thread_id
        self._write_state("running")
        return handle.thread_id

    def _complete_execution_turn(
        self,
        receipt: dict[str, object],
        result: TurnResult,
    ) -> None:
        if result.status != "completed":
            raise RuntimeStateError("execution turn did not complete successfully")
        if result.thread_id != receipt.get(
            "codex_thread_id"
        ) or result.turn_id != receipt.get("codex_turn_id"):
            raise RuntimeStateError("completed execution turn identity mismatch")
        raw_response = result.final_message
        response_directory = self.run_state_path.parent / "responses"
        response_directory.mkdir(parents=True, exist_ok=True)
        response_path = response_directory / (
            f"execution-{receipt['attempt_id']}-{uuid4().hex}.json"
        )
        _atomic_write_text(response_path, raw_response)
        receipt.update(
            status=result.status,
            raw_response_path=str(response_path),
            raw_response_sha256=hashlib.sha256(
                raw_response.encode("utf-8")
            ).hexdigest(),
        )
        self._write_state("running")

    def _finish_execution_process(
        self,
        client: AppServerClient,
        process: ManagedEvidenceProcess | None,
        *,
        node: str,
    ) -> None:
        primary: BaseException | None = None
        try:
            client.close()
        except BaseException as error:
            primary = error
        verification: Mapping[str, object] | None = None
        application_verification_status = "INVALID"
        if process is not None:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except BaseException as error:
                    if primary is None:
                        primary = error
                    else:
                        primary.add_note(
                            f"execution process termination also failed: {error}"
                        )
            finalization_succeeded = False
            try:
                verification = process.finalize()
                finalization_succeeded = True
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(
                        f"execution evidence finalization also failed: {error}"
                    )
                last_verification = getattr(
                    self.relay_client, "last_verification", None
                )
                if isinstance(last_verification, Mapping):
                    verification = last_verification
            if finalization_succeeded and primary is None:
                application_verification_status = "VALID_COMPLETE"
            self._record_evidence(
                process.registration,
                verification,
                node=node,
                application_verification_status=application_verification_status,
            )
            self._write_state("running")
        if primary is not None:
            raise primary

    def _read_completed_execution_response(self, receipt: Mapping[str, object]) -> str:
        response_path = receipt.get("raw_response_path")
        expected_sha256 = _require_sha256(
            receipt.get("raw_response_sha256"), "raw_response_sha256"
        )
        if not isinstance(response_path, str) or not response_path:
            raise RuntimeStateError("completed execution turn has no response path")
        response_bytes = _read_required_file(
            Path(response_path), "completed execution response"
        )
        if hashlib.sha256(response_bytes).hexdigest() != expected_sha256:
            raise RuntimeStateError("completed execution response SHA-256 mismatch")
        try:
            return response_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeStateError(
                "completed execution response is not valid UTF-8"
            ) from error

    def _require_execution_receipt_evidence(
        self,
        receipt: Mapping[str, object],
        *,
        allow_empty: bool = False,
    ) -> None:
        session_ids = receipt.get("evidence_session_ids")
        if not isinstance(session_ids, list) or not all(
            isinstance(item, str) and item for item in session_ids
        ):
            raise RuntimeStateError("execution turn has invalid evidence session IDs")
        if not session_ids:
            if allow_empty:
                return
            raise RuntimeStateError("execution turn has no TraceRelay evidence")
        evidence_by_id = {
            entry.get("session_id"): entry for entry in self._evidence_sessions
        }
        for session_id in session_ids:
            entry = evidence_by_id.get(session_id)
            if (
                entry is None
                or entry.get("node") != receipt.get("node")
                or entry.get("verification_status") != "VALID_COMPLETE"
                or entry.get("application_verification_status") != "VALID_COMPLETE"
            ):
                raise RuntimeStateError(
                    "execution turn has incomplete TraceRelay evidence"
                )
            _validate_execution_evidence_record(entry)
            expected_hash = _require_sha256(entry.get("final_hash"), "final_hash")
            verification = self.relay_client.verify_session(str(entry["session_path"]))
            actual_hash = _require_sha256(
                verification.get("final_hash"), "verified final_hash"
            )
            if actual_hash != expected_hash:
                raise RuntimeStateError(
                    "execution TraceRelay evidence final hash mismatch"
                )

    def _validate_persisted_execution_receipt_cache(self) -> None:
        evidence_by_id = {
            entry.get("session_id"): entry for entry in self._evidence_sessions
        }
        for receipt in self._execution_turns:
            status = receipt.get("status")
            session_ids = receipt.get("evidence_session_ids")
            assert isinstance(session_ids, list)
            if not session_ids and status != "preparing":
                raise RuntimeStateError("execution turn has no TraceRelay evidence")
            for session_id in session_ids:
                entry = evidence_by_id.get(session_id)
                if entry is None or entry.get("node") != receipt.get("node"):
                    raise RuntimeStateError(
                        "execution turn has incomplete TraceRelay evidence"
                    )
                _validate_execution_evidence_record(entry)
                raw_status = entry.get("verification_status")
                application_status = entry.get("application_verification_status")
                if (
                    raw_status == "VALID_COMPLETE"
                    and application_status == "VALID_COMPLETE"
                ):
                    continue
                if raw_status == "UNVERIFIED" and application_status is None:
                    continue
                raise RuntimeStateError(
                    "execution turn has incomplete TraceRelay evidence"
                )
            if status == "completed":
                self._read_completed_execution_response(receipt)

    def _recover_persisted_execution_sessions(self) -> None:
        if not self._is_resume:
            return
        recoverable: list[dict[str, object]] = []
        linked_ids = {
            session_id
            for receipt in self._execution_turns
            for session_id in receipt["evidence_session_ids"]
        }
        for entry in self._evidence_sessions:
            if entry.get("session_id") not in linked_ids:
                continue
            if (
                entry.get("verification_status") == "UNVERIFIED"
                and entry.get("application_verification_status") is None
            ):
                recoverable.append(entry)
        if len(recoverable) > 1:
            raise RuntimeStateError(
                "multiple unfinished execution TraceRelay sessions cannot be recovered"
            )
        if not recoverable:
            return
        entry = recoverable[0]
        _validate_execution_evidence_record(entry)
        registration = TraceRelayRegistration(
            session_id=str(entry["session_id"]),
            proxy_host="127.0.0.1",
            proxy_port=1,
            upstream_port=self.upstream_port,
            session_path=Path(str(entry["session_path"])),
        )
        verification = self.relay_client.recover_managed_session(
            registration,
            process_pid=int(entry["process_pid"]),
            process_creation_time_100ns=int(entry["process_creation_time_100ns"]),
        )
        _require_complete_execution_verification(verification)
        self._record_evidence(
            registration,
            verification,
            node=str(entry["node"]),
            application_verification_status="VALID_COMPLETE",
            process_pid=int(entry["process_pid"]),
            process_creation_time_100ns=int(entry["process_creation_time_100ns"]),
        )
        self._write_state("running")

    def _validate_persisted_execution_receipts(self) -> None:
        for receipt in self._execution_turns:
            status = receipt.get("status")
            self._require_execution_receipt_evidence(
                receipt,
                allow_empty=status == "preparing",
            )
            if status == "completed":
                self._read_completed_execution_response(receipt)

    def _validate_execution_stage_complete(self) -> None:
        if any(
            agent.get("status") != "ready" for agent in self._execution_agents.values()
        ):
            raise RuntimeStateError("Aegis run has an unresolved C/D thread allocation")
        if any(
            attempt.get("status") != "completed" for attempt in self._execution_attempts
        ):
            raise RuntimeStateError("Aegis run has an incomplete C/D node attempt")
        turns_by_attempt = {
            turn.get("attempt_id"): turn for turn in self._execution_turns
        }
        for attempt in self._execution_attempts:
            receipt = turns_by_attempt.get(attempt.get("attempt_id"))
            if receipt is None or receipt.get("status") != "completed":
                raise RuntimeStateError(
                    "Aegis run has an incomplete C/D App Server turn"
                )
        self._validate_persisted_execution_receipts()

    def _ensure_planning_app_server(self) -> AppServerClient:
        if self._planning_stage_status == "completed":
            raise RuntimeStateError("planning stage is already completed")
        if self._planning_app_server is not None:
            return self._planning_app_server
        if self._planning_stage_status == "not_started":
            self._planning_stage_status = "active"
            self._write_state("running")
        command = default_app_server_command()
        cli_path = str(Path(command[0]).resolve())
        cli_version = read_codex_cli_version(command[0])
        if (
            self._codex_cli_version is not None
            and self._codex_cli_version != cli_version
        ):
            raise RuntimeStateError(
                "Codex CLI version changed since this run was created: "
                f"saved={self._codex_cli_version!r}, current={cli_version!r}"
            )
        self._codex_cli_path = cli_path
        self._codex_cli_version = cli_version
        self._write_state("running")

        def process_factory(
            process_command: Sequence[str], **popen_options: object
        ) -> ManagedEvidenceProcess:
            if self._planning_process is not None:
                raise RuntimeStateError("planning App Server process already exists")
            process = self.relay_client.open_managed_process(
                process_command,
                upstream_port=self.upstream_port,
                **popen_options,
            )
            self._planning_process = process
            self._record_evidence(process.registration, None, node="planning")
            self._write_state("running")
            return process

        client = AppServerClient(
            cwd=self.project_root,
            command=command,
            process_factory=process_factory,
        )
        self._planning_app_server = client
        try:
            client.start()
        except BaseException as error:
            try:
                self.finish_planning_stage()
            except BaseException as cleanup_error:
                error.add_note(
                    f"planning App Server cleanup also failed: {cleanup_error}"
                )
            raise
        return client

    def _ensure_planning_thread(
        self, role_key: str, *, developer_instructions: str
    ) -> str:
        assert self._planning_app_server is not None
        existing = self._planning_agents.get(role_key)
        if role_key in self._planning_ready_roles:
            if existing is None or not isinstance(existing.get("codex_thread_id"), str):
                raise RuntimeStateError("planning agent state is incomplete")
            return str(existing["codex_thread_id"])
        if existing is None:
            handle = self._planning_app_server.start_thread(
                ephemeral=False,
                sandbox="danger-full-access",
                approval_policy="never",
                developer_instructions=developer_instructions,
            )
            self._planning_agents[role_key] = {
                "codex_thread_id": handle.thread_id,
                "model": handle.model,
                "reasoning_effort": handle.reasoning_effort,
            }
        else:
            thread_id = existing.get("codex_thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeStateError("saved planning agent has no Codex thread ID")
            handle = self._planning_app_server.resume_thread(
                thread_id,
                sandbox="danger-full-access",
                approval_policy="never",
            )
            existing.update(
                model=handle.model,
                reasoning_effort=handle.reasoning_effort,
            )
        self._planning_ready_roles.add(role_key)
        self._write_state("running")
        return handle.thread_id

    def _pending_planning_turn(
        self, role_key: str, job_id: str
    ) -> dict[str, object] | None:
        for turn in reversed(self._planning_turns):
            if (
                turn.get("role") == role_key
                and turn.get("job_id") == job_id
                and turn.get("status") in {"submitting", "inProgress"}
            ):
                return turn
        return None

    def _completed_planning_turn(
        self, role_key: str, job_id: str
    ) -> dict[str, object] | None:
        for turn in reversed(self._planning_turns):
            if (
                turn.get("role") == role_key
                and turn.get("job_id") == job_id
                and turn.get("status") == "completed"
            ):
                return turn
        return None

    def _read_completed_planning_response(self, receipt: Mapping[str, object]) -> str:
        response_path = receipt.get("raw_response_path")
        expected_sha256 = _require_sha256(
            receipt.get("raw_response_sha256"), "raw_response_sha256"
        )
        if not isinstance(response_path, str) or not response_path:
            raise RuntimeStateError("completed planning turn has no response path")
        response_bytes = _read_required_file(
            Path(response_path), "completed planning response"
        )
        if hashlib.sha256(response_bytes).hexdigest() != expected_sha256:
            raise RuntimeStateError("completed planning response SHA-256 mismatch")
        try:
            return response_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeStateError(
                "completed planning response is not valid UTF-8"
            ) from error

    def _require_matching_planning_request(
        self, receipt: Mapping[str, object], request_sha256: str
    ) -> None:
        if receipt.get("request_sha256") != request_sha256:
            raise RuntimeStateError("planning turn request changed during recovery")

    def _complete_planning_turn(
        self,
        receipt: dict[str, object],
        result: TurnResult,
    ) -> str:
        if result.thread_id != receipt.get(
            "codex_thread_id"
        ) or result.turn_id != receipt.get("codex_turn_id"):
            raise RuntimeStateError("completed planning turn identity mismatch")
        raw_response = result.final_message
        response_directory = self.run_state_path.parent / "responses"
        response_directory.mkdir(parents=True, exist_ok=True)
        response_path = response_directory / f"planning-{uuid4().hex}.json"
        _atomic_write_text(response_path, raw_response)
        receipt.update(
            status=result.status,
            raw_response_path=str(response_path),
            raw_response_sha256=hashlib.sha256(
                raw_response.encode("utf-8")
            ).hexdigest(),
        )
        self._write_state("running")
        return raw_response

    def new_response_path(self) -> Path:
        if not self._state_writable:
            raise RuntimeStateError("run state has not been durably reserved")
        node_name = self._current_node or "unknown"
        directory = self.run_state_path.parent / "responses"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{node_name}-{uuid4().hex}.txt"

    def _record_evidence(
        self,
        registration: TraceRelayRegistration,
        verification: Mapping[str, object] | None,
        *,
        node: str | None = None,
        application_verification_status: str | None = None,
        process_pid: int | None = None,
        process_creation_time_100ns: int | None = None,
    ) -> None:
        resolved_node = node or self._current_node
        if (
            resolved_node in EXECUTION_NODE_ROLES
            and application_verification_status == "VALID_COMPLETE"
        ):
            if verification is None:
                raise RuntimeStateError(
                    "valid execution evidence requires a verification payload"
                )
            _require_complete_execution_verification(verification)
        prior = next(
            (
                entry
                for entry in self._evidence_sessions
                if entry.get("session_id") == registration.session_id
            ),
            None,
        )
        if process_pid is None and prior is not None:
            saved_pid = prior.get("process_pid")
            process_pid = saved_pid if isinstance(saved_pid, int) else None
        if process_creation_time_100ns is None and prior is not None:
            saved_creation_time = prior.get("process_creation_time_100ns")
            process_creation_time_100ns = (
                saved_creation_time if isinstance(saved_creation_time, int) else None
            )
        entry = {
            "node": resolved_node,
            "session_id": registration.session_id,
            "session_path": str(registration.session_path),
            "verification_status": (
                verification.get("status") if verification else "UNVERIFIED"
            ),
            "application_verification_status": application_verification_status,
            "final_hash": verification.get("final_hash") if verification else None,
            "process_pid": process_pid,
            "process_creation_time_100ns": process_creation_time_100ns,
        }
        if resolved_node in EXECUTION_NODE_ROLES:
            _validate_execution_evidence_record(entry)
        for index, existing in enumerate(self._evidence_sessions):
            if existing.get("session_id") == registration.session_id:
                self._evidence_sessions[index] = entry
                return
        self._evidence_sessions.append(entry)

    def complete(self, state: dict[str, Any]) -> None:
        self.finish_planning_stage()
        self._validate_execution_stage_complete()
        self._current_node = None
        self._last_state = dict(state)
        self._write_state("completed")

    def fail(self, error: BaseException) -> None:
        try:
            self.finish_planning_stage()
        except BaseException as cleanup_error:
            error.add_note(f"planning stage cleanup also failed: {cleanup_error}")
        self._write_state("failed", error)

    def _write_state(self, status: str, error: BaseException | None = None) -> None:
        if not self._state_writable or self._reservation_token is None:
            raise RuntimeStateError("run state has not been durably reserved")
        payload = self._build_state_payload(status, error)
        _atomic_write_json(self.run_state_path, payload)

    def _build_state_payload(
        self,
        status: str,
        error: BaseException | None = None,
        *,
        reservation_token: str | None = None,
    ) -> dict[str, object]:
        token = reservation_token or self._reservation_token
        if token is None:
            raise RuntimeStateError("run reservation token is unavailable")
        payload: dict[str, object] = {
            "schema": RUN_STATE_SCHEMA,
            "run_id": self.run_id,
            "reservation_token": token,
            "status": status,
            "project_root": str(self.project_root),
            "artifact_path": str(self.artifact_path),
            "start_node": self.start_node,
            "current_node": self._current_node,
            "last_completed_node": self._last_completed_node,
            "graph_state": self._last_state,
            "evidence_sessions": list(self._evidence_sessions),
            "planning_agents": {
                role: dict(value) for role, value in self._planning_agents.items()
            },
            "planning_turns": [dict(item) for item in self._planning_turns],
            "planning_rounds": [dict(item) for item in self._planning_rounds],
            "planning_stage_status": self._planning_stage_status,
            "execution_agents": {
                role: dict(value) for role, value in self._execution_agents.items()
            },
            "execution_turns": [dict(item) for item in self._execution_turns],
            "execution_attempts": [dict(item) for item in self._execution_attempts],
            "codex_cli_path": self._codex_cli_path,
            "codex_cli_version": self._codex_cli_version,
            "created_at_utc": self._created_at_utc,
            "updated_at_utc": _utc_now_text(),
        }
        if self._seal is not None:
            payload.update(
                seal_sequence=self._seal.sequence,
                expected_seal=self._seal.expected_seal,
            )
        if error is not None:
            payload["error"] = {"type": type(error).__name__, "message": str(error)}
        return payload


def active_runtime_coordinator() -> RuntimeCoordinator | None:
    return _ACTIVE_COORDINATOR.get()


def load_run_state(artifact_path: str | Path, run_id: str) -> dict[str, object]:
    if RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
        raise ValueError("run_id contains unsupported path characters")
    path = Path(artifact_path).resolve() / ".aegis" / "runs" / run_id / "RUN_STATE.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeStateError(f"cannot load run state: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeStateError("run state must be an object")
    if payload.get("schema") in {"aegis.run_state.v1", "aegis.run_state.v2"}:
        raise RuntimeStateError(
            "run state predates C/D App Server transactions; start a new run"
        )
    if payload.get("schema") != RUN_STATE_SCHEMA:
        raise RuntimeStateError("run state has an unsupported schema")
    if payload.get("run_id") != run_id:
        raise RuntimeStateError("run state identity mismatch")
    reservation_token = payload.get("reservation_token")
    if (
        not isinstance(reservation_token, str)
        or RESERVATION_TOKEN_PATTERN.fullmatch(reservation_token) is None
    ):
        raise RuntimeStateError("run state has an invalid reservation token")
    return payload


@contextmanager
def open_graph_checkpointer(project_root: str | Path) -> Iterator[SqliteSaver]:
    path = Path(project_root).resolve() / CHECKPOINT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        yield SqliteSaver(connection)
    finally:
        connection.close()


def _reserve_new_run(
    project_root: Path,
    run_state_path: Path,
    run_id: str,
    reservation_token: str,
    state_payload: Mapping[str, object],
) -> None:
    database_path = project_root / CHECKPOINT_RELATIVE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.parent.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
    transaction_started = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {RESERVATION_TABLE} (
                run_id TEXT PRIMARY KEY,
                reservation_token TEXT NOT NULL UNIQUE,
                artifact_path TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        if _sqlite_thread_exists(connection, run_id):
            raise RuntimeStateError(
                f"LangGraph checkpoint thread already exists for run ID: {run_id}"
            )
        if connection.execute(
            f"SELECT 1 FROM {RESERVATION_TABLE} WHERE run_id = ? LIMIT 1",
            (run_id,),
        ).fetchone():
            raise RuntimeStateError(f"run ID is already reserved: {run_id}")
        try:
            run_state_path.parent.mkdir()
        except FileExistsError as error:
            raise RuntimeStateError(f"run ID is already reserved: {run_id}") from error
        _write_json_exclusive(run_state_path, state_payload)
        connection.execute(
            f"""
            INSERT INTO {RESERVATION_TABLE}
                (run_id, reservation_token, artifact_path, created_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                reservation_token,
                str(run_state_path.parents[3].resolve()),
                str(state_payload["created_at_utc"]),
            ),
        )
        connection.execute("COMMIT")
        transaction_started = False
    except RuntimeStateError:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    except (OSError, sqlite3.Error, KeyError) as error:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise RuntimeStateError(f"cannot reserve run ID {run_id}: {error}") from error
    finally:
        connection.close()


def _validate_run_reservation(
    project_root: Path,
    artifact_path: Path,
    run_id: str,
    reservation_token: str,
) -> None:
    database_path = project_root / CHECKPOINT_RELATIVE_PATH
    if not database_path.is_file():
        raise RuntimeStateError("run reservation database is missing")
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro", uri=True, timeout=30
        )
        try:
            row = connection.execute(
                f"""
                SELECT reservation_token, artifact_path
                FROM {RESERVATION_TABLE}
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise RuntimeStateError(f"cannot validate run reservation: {error}") from error
    if row is None:
        raise RuntimeStateError("run reservation does not exist")
    stored_token, stored_artifact_path = row
    if stored_token != reservation_token:
        raise RuntimeStateError("run reservation does not match RUN_STATE.json")
    if (
        not isinstance(stored_artifact_path, str)
        or Path(stored_artifact_path).resolve() != artifact_path
    ):
        raise RuntimeStateError("run reservation artifact path does not match")


def _sqlite_thread_exists(connection: sqlite3.Connection, run_id: str) -> bool:
    for table in ("checkpoints", "writes"):
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if (
            exists
            and connection.execute(
                f"SELECT 1 FROM {table} WHERE thread_id = ? LIMIT 1", (run_id,)
            ).fetchone()
        ):
            return True
    return False


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RuntimeStateError("run state node names must be strings or null")
    return value


def _planning_request_sha256(prompt: str, output_schema: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {"output_schema": dict(output_schema), "prompt": prompt},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _state_sha256(state: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            dict(state),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RuntimeStateError(
            f"execution graph state is not deterministic JSON: {error}"
        ) from error
    return hashlib.sha256(encoded).hexdigest()


def _require_complete_execution_verification(
    verification: Mapping[str, object],
) -> str:
    if verification.get("status") != "VALID_COMPLETE":
        raise RuntimeStateError(
            "execution TraceRelay verification is not VALID_COMPLETE"
        )
    final_hash = _require_sha256(verification.get("final_hash"), "final_hash")
    observed = verification.get("observed_bytes")
    if not isinstance(observed, Mapping):
        raise RuntimeStateError(
            "execution TraceRelay verification has no observed byte counts"
        )
    for direction in ("client_to_upstream", "upstream_to_client"):
        value = observed.get(direction)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeStateError(
                "execution TraceRelay verification has no bidirectional traffic"
            )
    return final_hash


def _validate_execution_evidence_records(
    evidence: Sequence[Mapping[str, object]],
) -> None:
    for entry in evidence:
        if entry.get("node") in EXECUTION_NODE_ROLES:
            _validate_execution_evidence_record(entry)


def _validate_execution_evidence_record(entry: Mapping[str, object]) -> None:
    node = entry.get("node")
    if node not in EXECUTION_NODE_ROLES:
        raise RuntimeStateError("execution evidence has an invalid node")
    session_id = entry.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeStateError("execution evidence has an invalid session ID")
    session_path = entry.get("session_path")
    if not isinstance(session_path, str) or not session_path:
        raise RuntimeStateError("execution evidence has an invalid session path")
    path = Path(session_path)
    if not path.is_absolute() or path.name != session_id:
        raise RuntimeStateError(
            "execution evidence session path does not match its session ID"
        )
    process_pid = entry.get("process_pid")
    if (
        isinstance(process_pid, bool)
        or not isinstance(process_pid, int)
        or process_pid <= 0
    ):
        raise RuntimeStateError("execution turn evidence has no valid App Server PID")
    creation_time = entry.get("process_creation_time_100ns")
    if (
        isinstance(creation_time, bool)
        or not isinstance(creation_time, int)
        or creation_time <= 0
    ):
        raise RuntimeStateError(
            "execution turn evidence has no valid App Server creation time"
        )
    raw_status = entry.get("verification_status")
    if not isinstance(raw_status, str) or not raw_status:
        raise RuntimeStateError("execution evidence has an invalid verification status")
    application_status = entry.get("application_verification_status")
    if application_status not in {None, "VALID_COMPLETE", "INVALID"}:
        raise RuntimeStateError(
            "execution evidence has an invalid application verification status"
        )
    final_hash = entry.get("final_hash")
    if final_hash is not None:
        _require_sha256(final_hash, "final_hash")
    if raw_status == "VALID_COMPLETE":
        _require_sha256(final_hash, "final_hash")
    if application_status == "VALID_COMPLETE" and raw_status != "VALID_COMPLETE":
        raise RuntimeStateError(
            "execution evidence application status contradicts raw verification"
        )


def _validate_execution_agents(agents: Mapping[str, Mapping[str, object]]) -> None:
    valid_roles = set(EXECUTION_NODE_ROLES.values())
    ready_thread_ids: set[str] = set()
    for role, agent in agents.items():
        if role not in valid_roles:
            raise RuntimeStateError("prior execution agents contain an unknown role")
        status = agent.get("status")
        if status not in EXECUTION_AGENT_STATUSES:
            raise RuntimeStateError("prior execution agent has an invalid status")
        _require_sha256(
            agent.get("developer_instructions_sha256"),
            "developer_instructions_sha256",
        )
        thread_id = agent.get("codex_thread_id")
        if status == "allocating":
            if thread_id is not None:
                raise RuntimeStateError(
                    "allocating execution agent already has a thread ID"
                )
        elif not isinstance(thread_id, str) or not thread_id:
            raise RuntimeStateError("ready execution agent has no thread ID")
        elif thread_id in ready_thread_ids:
            raise RuntimeStateError(
                "prior execution roles share one persistent thread ID"
            )
        else:
            ready_thread_ids.add(thread_id)
        for field in ("model", "reasoning_effort"):
            value = agent.get(field)
            if value is not None and not isinstance(value, str):
                raise RuntimeStateError(f"prior execution agent has an invalid {field}")


def _validate_execution_attempts(
    attempts: Sequence[Mapping[str, object]],
) -> None:
    for index, attempt in enumerate(attempts, start=1):
        attempt_id = f"attempt-{index:04d}"
        if attempt.get("attempt_id") != attempt_id:
            raise RuntimeStateError("prior execution attempts are not contiguous")
        job_id = attempt.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeStateError("prior execution attempt has an invalid job ID")
        node = attempt.get("node")
        if node not in EXECUTION_NODE_ROLES:
            raise RuntimeStateError("prior execution attempt has an invalid node")
        if attempt.get("role") != EXECUTION_NODE_ROLES[str(node)]:
            raise RuntimeStateError(
                "prior execution attempt role does not match its node"
            )
        _require_sha256(attempt.get("input_sha256"), "input_sha256")
        status = attempt.get("status")
        if status == "running":
            if index != len(attempts):
                raise RuntimeStateError(
                    "only the latest execution attempt may remain running"
                )
            if attempt.get("output_sha256") is not None:
                raise RuntimeStateError("running execution attempt already has output")
        elif status == "completed":
            _require_sha256(attempt.get("output_sha256"), "output_sha256")
        else:
            raise RuntimeStateError("prior execution attempt has an invalid status")
        if index > 1 and attempts[index - 2].get("node") == node:
            raise RuntimeStateError("prior execution attempts repeat a graph node")


def _validate_execution_turns(turns: Sequence[Mapping[str, object]]) -> None:
    seen_jobs: set[str] = set()
    seen_attempts: set[str] = set()
    for receipt in turns:
        attempt_id = receipt.get("attempt_id")
        job_id = receipt.get("job_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise RuntimeStateError("prior execution turn has an invalid attempt ID")
        if attempt_id in seen_attempts:
            raise RuntimeStateError("prior execution turns contain a duplicate attempt")
        seen_attempts.add(attempt_id)
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeStateError("prior execution turn has an invalid job ID")
        if job_id in seen_jobs:
            raise RuntimeStateError("prior execution turns contain a duplicate job")
        seen_jobs.add(job_id)
        node = receipt.get("node")
        if node not in EXECUTION_NODE_ROLES:
            raise RuntimeStateError("prior execution turn has an invalid node")
        if receipt.get("role") != EXECUTION_NODE_ROLES[str(node)]:
            raise RuntimeStateError("prior execution turn role does not match its node")
        if (
            not isinstance(receipt.get("client_message_id"), str)
            or not receipt["client_message_id"]
        ):
            raise RuntimeStateError(
                "prior execution turn has an invalid client_message_id"
            )
        _require_sha256(receipt.get("request_sha256"), "request_sha256")
        _require_sha256(
            receipt.get("developer_instructions_sha256"),
            "developer_instructions_sha256",
        )
        thread_id = receipt.get("codex_thread_id")
        turn_id = receipt.get("codex_turn_id")
        status = receipt.get("status")
        if status not in EXECUTION_TURN_STATUSES:
            raise RuntimeStateError("prior execution turn has an invalid status")
        if status == "preparing":
            if thread_id is not None and (
                not isinstance(thread_id, str) or not thread_id
            ):
                raise RuntimeStateError(
                    "preparing execution turn has invalid thread ID"
                )
            if turn_id is not None:
                raise RuntimeStateError(
                    "preparing execution turn already has a turn ID"
                )
        elif status == "submitting":
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeStateError("submitting execution turn has no thread ID")
            if turn_id is not None:
                raise RuntimeStateError(
                    "submitting execution turn already has a turn ID"
                )
        else:
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeStateError("execution turn has no thread ID")
            if not isinstance(turn_id, str) or not turn_id:
                raise RuntimeStateError("execution turn has no turn ID")
        if status == "completed":
            if not isinstance(receipt.get("raw_response_path"), str):
                raise RuntimeStateError("completed execution turn has no response path")
            _require_sha256(receipt.get("raw_response_sha256"), "raw_response_sha256")
        session_ids = receipt.get("evidence_session_ids")
        if not isinstance(session_ids, list) or not all(
            isinstance(item, str) and item for item in session_ids
        ):
            raise RuntimeStateError(
                "prior execution turn has invalid evidence session IDs"
            )
        if len(session_ids) != len(set(session_ids)):
            raise RuntimeStateError(
                "prior execution turn repeats an evidence session ID"
            )


def _validate_execution_bindings(
    attempts: Sequence[Mapping[str, object]],
    agents: Mapping[str, Mapping[str, object]],
    turns: Sequence[Mapping[str, object]],
    evidence: Sequence[Mapping[str, object]],
    *,
    run_id: str,
) -> None:
    attempts_by_id = {attempt["attempt_id"]: attempt for attempt in attempts}
    turns_by_attempt = {turn["attempt_id"]: turn for turn in turns}
    evidence_by_id: dict[object, Mapping[str, object]] = {}
    for entry in evidence:
        session_id = entry.get("session_id")
        if session_id in evidence_by_id:
            raise RuntimeStateError("prior evidence sessions contain a duplicate ID")
        evidence_by_id[session_id] = entry
    linked_sessions: set[str] = set()
    for attempt in attempts:
        expected_job_id = f"{run_id}:execution:{attempt['attempt_id']}"
        if attempt.get("job_id") != expected_job_id:
            raise RuntimeStateError(
                "execution attempt job ID does not match the run identity"
            )
    for receipt in turns:
        attempt = attempts_by_id.get(receipt["attempt_id"])
        if attempt is None or any(
            receipt.get(field) != attempt.get(field)
            for field in ("job_id", "node", "role")
        ):
            raise RuntimeStateError("execution turn does not match its node attempt")
        if receipt.get("client_message_id") != f"{receipt['job_id']}:submission":
            raise RuntimeStateError(
                "execution turn client message ID does not match its job"
            )
        agent = agents.get(str(receipt["role"]))
        thread_id = receipt.get("codex_thread_id")
        if thread_id is not None:
            if (
                agent is None
                or agent.get("status") != "ready"
                or agent.get("codex_thread_id") != thread_id
                or agent.get("developer_instructions_sha256")
                != receipt.get("developer_instructions_sha256")
            ):
                raise RuntimeStateError(
                    "execution turn does not match its persistent agent"
                )
        for session_id in receipt["evidence_session_ids"]:
            if session_id in linked_sessions:
                raise RuntimeStateError(
                    "one TraceRelay session is linked to multiple execution turns"
                )
            linked_sessions.add(session_id)
            entry = evidence_by_id.get(session_id)
            if entry is None or entry.get("node") != receipt.get("node"):
                raise RuntimeStateError(
                    "execution turn evidence binding is missing or inconsistent"
                )
            process_pid = entry.get("process_pid")
            if (
                isinstance(process_pid, bool)
                or not isinstance(process_pid, int)
                or process_pid <= 0
            ):
                raise RuntimeStateError(
                    "execution turn evidence has no valid App Server PID"
                )
    for session_id, entry in evidence_by_id.items():
        if (
            entry.get("node") in EXECUTION_NODE_ROLES
            and session_id not in linked_sessions
        ):
            raise RuntimeStateError(
                "execution TraceRelay evidence is not linked to a turn"
            )
    for attempt in attempts:
        if attempt.get("status") == "completed":
            receipt = turns_by_attempt.get(attempt["attempt_id"])
            if receipt is None or receipt.get("status") != "completed":
                raise RuntimeStateError(
                    "completed execution attempt has no completed turn"
                )


def _validate_planning_turns(turns: Sequence[Mapping[str, object]]) -> None:
    seen_jobs: set[tuple[object, object]] = set()
    for receipt in turns:
        role = receipt.get("role")
        job_id = receipt.get("job_id")
        if not isinstance(role, str) or not role:
            raise RuntimeStateError("prior planning turn has an invalid role")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeStateError("prior planning turn has an invalid job ID")
        identity = (role, job_id)
        if identity in seen_jobs:
            raise RuntimeStateError("prior planning turns contain a duplicate job")
        seen_jobs.add(identity)
        for field in ("client_message_id", "codex_thread_id"):
            if not isinstance(receipt.get(field), str) or not receipt[field]:
                raise RuntimeStateError(f"prior planning turn has an invalid {field}")
        _require_sha256(receipt.get("request_sha256"), "request_sha256")
        status = receipt.get("status")
        turn_id = receipt.get("codex_turn_id")
        if status == "submitting":
            if turn_id is not None:
                raise RuntimeStateError(
                    "submitting planning turn already has a turn ID"
                )
        elif status in {"inProgress", "completed"}:
            if not isinstance(turn_id, str) or not turn_id:
                raise RuntimeStateError("planning turn has no Codex turn ID")
        else:
            raise RuntimeStateError("prior planning turn has an invalid status")
        if status == "completed":
            if not isinstance(receipt.get("raw_response_path"), str):
                raise RuntimeStateError("completed planning turn has no response path")
            _require_sha256(receipt.get("raw_response_sha256"), "raw_response_sha256")


def _validate_planning_rounds(rounds: Sequence[Mapping[str, object]]) -> None:
    for index, record in enumerate(rounds, start=1):
        expected_round_id = f"round-{index:04d}"
        if record.get("round_id") != expected_round_id:
            raise RuntimeStateError("prior planning rounds are not contiguous")
        status = record.get("status")
        if status not in PLANNING_ROUND_STATUSES:
            raise RuntimeStateError("prior planning round has an invalid status")
        for field in (
            "project_seal",
            "context_pack_path",
            "context_pack_sha256",
            "plan_path",
            "review_report_path",
            "created_at_utc",
        ):
            if not isinstance(record.get(field), str) or not record[field]:
                raise RuntimeStateError(f"prior planning round has an invalid {field}")
        _require_sha256(record.get("context_pack_sha256"), "context_pack_sha256")
        if status in {"review_pending", "rejected", "publishing", "approved"}:
            _require_sha256(record.get("plan_sha256"), "plan_sha256")
        if status in {"rejected", "publishing", "approved"}:
            _require_sha256(record.get("review_report_sha256"), "review_report_sha256")
            _require_sha256(record.get("reviewed_plan_sha256"), "reviewed_plan_sha256")
            if record.get("reviewed_plan_sha256") != record.get("plan_sha256"):
                raise RuntimeStateError(
                    "reviewed plan SHA-256 does not match frozen plan"
                )
            _require_bounded_integer(record.get("score"), "score", 0, 100)
            _require_bounded_integer(record.get("error_count"), "error_count", 0, None)
            _require_bounded_integer(
                record.get("warning_count"), "warning_count", 0, None
            )
            if record.get("verdict") not in {"PASS", "FAIL"}:
                raise RuntimeStateError("prior planning round has an invalid verdict")
            accepted = _planning_review_is_accepted(record)
            if status == "rejected" and accepted:
                raise RuntimeStateError(
                    "prior rejected planning round satisfies approval rules"
                )
            if status in {"publishing", "approved"} and not accepted:
                raise RuntimeStateError(
                    "prior approved planning round violates approval rules"
                )
        if status in {"publishing", "approved"}:
            for field in ("approved_plan_path", "handoff_path"):
                if not isinstance(record.get(field), str) or not record[field]:
                    raise RuntimeStateError(
                        f"prior planning round has an invalid {field}"
                    )
        if index < len(rounds) and status != "rejected":
            raise RuntimeStateError(
                "only a rejected planning round may have a successor"
            )


def _planning_review_is_accepted(record: Mapping[str, object]) -> bool:
    score = record.get("score")
    error_count = record.get("error_count")
    return (
        isinstance(score, int)
        and not isinstance(score, bool)
        and score >= PLANNING_REVIEW_THRESHOLD
        and isinstance(error_count, int)
        and not isinstance(error_count, bool)
        and error_count == 0
        and record.get("verdict") == "PASS"
    )


def _read_required_file(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise RuntimeStateError(f"{label} is missing: {path}")
        value = path.read_bytes()
    except RuntimeStateError:
        raise
    except OSError as error:
        raise RuntimeStateError(f"cannot read {label}: {path}: {error}") from error
    if not value:
        raise RuntimeStateError(f"{label} is empty: {path}")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RuntimeStateError(f"{field_name} must be a lowercase SHA-256 value")
    return value


def _require_bounded_integer(
    value: object,
    field_name: str,
    minimum: int,
    maximum: int | None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeStateError(f"{field_name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise RuntimeStateError(f"{field_name} is outside its allowed range")
    return value


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = value.encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
