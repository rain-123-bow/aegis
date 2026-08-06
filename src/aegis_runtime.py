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
PLANNING_STAGE_STATUSES = frozenset({"not_started", "active", "completed"})
PLANNING_ROUND_STATUSES = frozenset(
    {"authoring", "review_pending", "rejected", "approved"}
)
PLANNING_REVIEW_THRESHOLD = 95


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
        if state.get("run_id") != self.run_id:
            raise RuntimeStateError("prior run state identity mismatch")
        if state.get("start_node") != self.start_node:
            raise RuntimeStateError("prior run state start node mismatch")
        stored_root = state.get("project_root")
        if not isinstance(stored_root, str) or Path(stored_root).resolve() != self.project_root:
            raise RuntimeStateError("prior run state project root mismatch")
        created_at = state.get("created_at_utc")
        graph_state = state.get("graph_state")
        evidence = state.get("evidence_sessions")
        planning_agents = state.get("planning_agents", {})
        planning_turns = state.get("planning_turns", [])
        planning_rounds = state.get("planning_rounds", [])
        codex_cli_path = state.get("codex_cli_path")
        codex_cli_version = state.get("codex_cli_version")
        planning_stage_status = state.get("planning_stage_status")
        reservation_token = state.get("reservation_token")
        if not isinstance(created_at, str) or not created_at:
            raise RuntimeStateError("prior run state has no creation time")
        if graph_state is not None and not isinstance(graph_state, dict):
            raise RuntimeStateError("prior run graph state must be an object or null")
        if not isinstance(evidence, list) or not all(isinstance(x, dict) for x in evidence):
            raise RuntimeStateError("prior evidence sessions must be a list of objects")
        if not isinstance(planning_agents, dict) or not all(
            isinstance(role, str) and isinstance(value, dict)
            for role, value in planning_agents.items()
        ):
            raise RuntimeStateError("prior planning agents must be an object")
        if not isinstance(planning_turns, list) or not all(
            isinstance(item, dict) for item in planning_turns
        ):
            raise RuntimeStateError("prior planning turns must be a list of objects")
        if not isinstance(planning_rounds, list) or not all(
            isinstance(item, dict) for item in planning_rounds
        ):
            raise RuntimeStateError("prior planning rounds must be a list of objects")
        _validate_planning_rounds(planning_rounds)
        if codex_cli_path is not None and not isinstance(codex_cli_path, str):
            raise RuntimeStateError("prior Codex CLI path must be a string or null")
        if codex_cli_version is not None and not isinstance(codex_cli_version, str):
            raise RuntimeStateError("prior Codex CLI version must be a string or null")
        if planning_stage_status is None:
            planning_stage_status = _infer_planning_stage_status(
                evidence, planning_agents
            )
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
            self.relay_client.start()
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
        self._write_state("running")
        token = _ACTIVE_COORDINATOR.set(self)
        try:
            result = operation(state)
        except BaseException as error:
            self._write_state("failed", error)
            raise
        finally:
            _ACTIVE_COORDINATOR.reset(token)
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
        completed = self._completed_planning_turn(role_key, resolved_job_id)
        if completed is not None:
            return self._read_completed_planning_response(completed)
        pending = self._pending_planning_turn(role_key, resolved_job_id)
        if pending is None:
            client_message_id = (
                f"{self.run_id}:{role_key}:{len(self._planning_turns) + 1}"
            )
            turn = client.start_turn(
                thread_id,
                prompt,
                output_schema=output_schema,
                client_message_id=client_message_id,
            )
            pending = {
                "job_id": resolved_job_id,
                "node": self._current_node,
                "role": role_key,
                "client_message_id": client_message_id,
                "codex_thread_id": turn.thread_id,
                "codex_turn_id": turn.turn_id,
                "status": "inProgress",
                "raw_response_path": None,
                "raw_response_sha256": None,
            }
            self._planning_turns.append(pending)
            self._write_state("running")
            result = client.wait_turn(turn)
        else:
            pending_thread = pending.get("codex_thread_id")
            pending_turn = pending.get("codex_turn_id")
            if pending_thread != thread_id or not isinstance(pending_turn, str):
                raise RuntimeStateError("pending planning turn identity mismatch")
            result = client.recover_turn(thread_id, pending_turn)
        return self._complete_planning_turn(pending, result)

    def prepare_planning_agents(
        self, role_instructions: Mapping[str, str]
    ) -> None:
        if not role_instructions:
            raise ValueError("at least one planning role is required")
        self._ensure_planning_app_server()
        for role_key, instructions in role_instructions.items():
            if not role_key or not instructions:
                raise ValueError("planning roles require instructions")
            self._ensure_planning_thread(
                role_key, developer_instructions=instructions
            )

    def prepare_planning_author(
        self, context_pack_path: str | Path
    ) -> dict[str, object]:
        if self._seal is None:
            raise RuntimeStateError("planning handoff requires a verified project seal")
        context_path = Path(context_pack_path).resolve()
        context_bytes = _read_required_file(context_path, "reasoning context pack")
        context_sha256 = hashlib.sha256(context_bytes).hexdigest()
        previous_report_path: str | None = None
        if self._planning_rounds:
            current = self._planning_rounds[-1]
            status = current["status"]
            if status in {"authoring", "review_pending"}:
                if current["context_pack_path"] != str(context_path):
                    raise RuntimeStateError(
                        "planning context path changed during an active round"
                    )
                if current["context_pack_sha256"] != context_sha256:
                    raise RuntimeStateError(
                        "planning context changed during an active round"
                    )
                if status == "review_pending":
                    self._validate_frozen_plan(current)
                return self._author_control(
                    current,
                    skip_turn=status == "review_pending",
                    previous_review_report_path=None,
                )
            if status == "approved":
                raise RuntimeStateError("planning handoff is already approved")
            previous_report_path = str(current["review_report_path"])

        round_id = f"round-{len(self._planning_rounds) + 1:04d}"
        round_directory = (
            self.artifact_path / ".aegis" / "planning" / self.run_id / round_id
        )
        try:
            round_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise RuntimeStateError(
                f"planning round directory already exists: {round_directory}"
            ) from error
        record: dict[str, object] = {
            "round_id": round_id,
            "status": "authoring",
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
        return self._author_control(
            record,
            skip_turn=False,
            previous_review_report_path=previous_report_path,
        )

    def freeze_planning_plan(self, round_id: str) -> dict[str, object]:
        record = self._current_planning_round(round_id)
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
        if status not in {"review_pending", "rejected", "approved"}:
            raise RuntimeStateError("planning review requires a frozen plan")
        self._validate_planning_context(record)
        self._validate_planning_project_seal(record)
        self._validate_frozen_plan(record)
        if status in {"rejected", "approved"}:
            self._validate_review_report(record)
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
            status="approved" if accepted else "rejected",
            review_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
            reviewed_plan_sha256=reviewed_plan_sha256,
            score=score,
            error_count=error_count,
            warning_count=warning_count,
            verdict=verdict,
            reviewed_at_utc=_utc_now_text(),
        )
        if accepted:
            self._publish_approved_planning_handoff(record)
        self._write_state("running")
        return accepted

    def _author_control(
        self,
        record: Mapping[str, object],
        *,
        skip_turn: bool,
        previous_review_report_path: str | None,
    ) -> dict[str, object]:
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
            "previous_review_report_path": previous_review_report_path,
            "instructions": (
                "Write the complete test plan to plan_path. If a previous review path "
                "is present, address all of it in one revision. Do not modify any prior "
                "round. Return only the node-message JSON after the file is durable."
            ),
            "skip_turn": skip_turn,
        }

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

    def _validate_planning_project_seal(
        self, record: Mapping[str, object]
    ) -> None:
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

    def _publish_approved_planning_handoff(
        self, record: dict[str, object]
    ) -> None:
        self._validate_planning_context(record)
        self._validate_planning_project_seal(record)
        plan_bytes = _read_required_file(
            Path(str(record["plan_path"])), "frozen test plan"
        )
        approved_path = (self.artifact_path / "APPROVED_TEST_PLAN.md").resolve()
        _atomic_write_bytes(approved_path, plan_bytes)
        approved_sha256 = hashlib.sha256(plan_bytes).hexdigest()
        if approved_sha256 != record["plan_sha256"]:
            raise RuntimeStateError("approved test plan does not match frozen plan")
        handoff_path = (self.artifact_path / "PLANNING_HANDOFF.json").resolve()
        handoff = {
            "schema": "aegis.planning_handoff.v1",
            "run_id": self.run_id,
            "round_id": record["round_id"],
            "project_seal": record["project_seal"],
            "context_pack_path": record["context_pack_path"],
            "context_pack_sha256": record["context_pack_sha256"],
            "approved_plan_path": str(approved_path),
            "approved_plan_sha256": approved_sha256,
            "review_report_path": record["review_report_path"],
            "review_report_sha256": record["review_report_sha256"],
            "score": record["score"],
            "error_count": record["error_count"],
            "warning_count": record["warning_count"],
            "verdict": record["verdict"],
        }
        _atomic_write_json(handoff_path, handoff)
        record["approved_plan_path"] = str(approved_path)
        record["handoff_path"] = str(handoff_path)

    def complete_planning_stage(self) -> None:
        if self._planning_rounds:
            current = self._planning_rounds[-1]
            if current["status"] != "approved":
                raise RuntimeStateError("planning stage has no approved handoff")
            self._validate_frozen_plan(current)
            self._validate_planning_context(current)
            self._validate_planning_project_seal(current)
            self._validate_review_report(current)
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
        if process is not None:
            try:
                verification = process.finalize()
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(f"planning evidence finalization also failed: {error}")
                last_verification = getattr(self.relay_client, "last_verification", None)
                if isinstance(last_verification, Mapping):
                    verification = last_verification
            self._record_evidence(
                process.registration,
                verification,
                node="planning",
            )
        self._planning_app_server = None
        self._planning_process = None
        self._planning_ready_roles.clear()
        if primary is None and mark_completed:
            self._planning_stage_status = "completed"
        self._write_state("running")
        if primary is not None:
            raise primary

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
                error.add_note(f"planning App Server cleanup also failed: {cleanup_error}")
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
                and turn.get("status") == "inProgress"
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

    def _read_completed_planning_response(
        self, receipt: Mapping[str, object]
    ) -> str:
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

    def _complete_planning_turn(
        self,
        receipt: dict[str, object],
        result: TurnResult,
    ) -> str:
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
    ) -> None:
        entry = {
            "node": node or self._current_node,
            "session_id": registration.session_id,
            "session_path": str(registration.session_path),
            "verification_status": (
                verification.get("status") if verification else "UNVERIFIED"
            ),
            "final_hash": verification.get("final_hash") if verification else None,
        }
        for index, existing in enumerate(self._evidence_sessions):
            if existing.get("session_id") == registration.session_id:
                self._evidence_sessions[index] = entry
                return
        self._evidence_sessions.append(entry)

    def complete(self, state: dict[str, Any]) -> None:
        self.finish_planning_stage()
        self._current_node = None
        self._last_state = dict(state)
        self._write_state("completed")

    def fail(self, error: BaseException) -> None:
        try:
            self.finish_planning_stage()
        except BaseException as cleanup_error:
            error.add_note(f"planning stage cleanup also failed: {cleanup_error}")
        self._write_state("failed", error)

    def _write_state(
        self, status: str, error: BaseException | None = None
    ) -> None:
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
            "schema": "aegis.run_state.v1",
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
    if not isinstance(payload, dict) or payload.get("schema") != "aegis.run_state.v1":
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
        if exists and connection.execute(
            f"SELECT 1 FROM {table} WHERE thread_id = ? LIMIT 1", (run_id,)
        ).fetchone():
            return True
    return False


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RuntimeStateError("run state node names must be strings or null")
    return value


def _infer_planning_stage_status(
    evidence_sessions: list[object], planning_agents: Mapping[object, object]
) -> str:
    if any(
        isinstance(entry, Mapping)
        and entry.get("node") == "planning"
        and entry.get("verification_status") == "VALID_COMPLETE"
        for entry in evidence_sessions
    ):
        return "completed"
    return "active" if planning_agents else "not_started"


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
                raise RuntimeStateError(
                    f"prior planning round has an invalid {field}"
                )
        _require_sha256(record.get("context_pack_sha256"), "context_pack_sha256")
        if status != "authoring":
            _require_sha256(record.get("plan_sha256"), "plan_sha256")
        if status in {"rejected", "approved"}:
            _require_sha256(
                record.get("review_report_sha256"), "review_report_sha256"
            )
            _require_sha256(
                record.get("reviewed_plan_sha256"), "reviewed_plan_sha256"
            )
            _require_bounded_integer(record.get("score"), "score", 0, 100)
            _require_bounded_integer(
                record.get("error_count"), "error_count", 0, None
            )
            _require_bounded_integer(
                record.get("warning_count"), "warning_count", 0, None
            )
            if record.get("verdict") not in {"PASS", "FAIL"}:
                raise RuntimeStateError("prior planning round has an invalid verdict")
        if index < len(rounds) and status != "rejected":
            raise RuntimeStateError("only a rejected planning round may have a successor")


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
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
