from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys

sys.dont_write_bytecode = True

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Iterator
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from agent_registry import DynamicAgentRegistry
from codex_app_server_client import (
    AppServerClient,
    TurnResult,
    default_app_server_command,
    read_codex_cli_version,
)
from engineering_input_manifest import (
    EngineeringInputManifestError,
    validate_engineering_input_manifest,
)
from final_review_verdict import (
    FinalReviewVerdictError,
    validate_final_review_verdict,
)
from frozen_input_watcher import FileSystemEvent, FrozenInputWatcher
from path_security import PathSecurityError, read_regular_file, require_no_reparse
from project_seal_store import (
    StoredProjectSeal,
    hold_verified_project_git_runtime,
    verify_expected_project_seal,
)
from runtime_behavior_scope import (
    SCOPE_DECISION_RELATIVE_PATH,
    SCOPE_POLICY_RELATIVE_PATH,
    SCOPE_REVIEW_RELATIVE_PATH,
    SCOPE_USER_STATEMENT_RELATIVE_PATH,
    RuntimeBehaviorScopeError,
    resolve_runtime_behavior_scope,
    runtime_behavior_path_is_selected,
)
from runtime_identity import RuntimeIdentityError, capture_production_runtime_identity
from remote_seal_witness import verify_remote_project_seal_witness
from reasoning_context_pack import (
    ReasoningContextPackError,
    validate_reasoning_context_pack,
)
from reasoning_ledger_provenance import (
    ReasoningLedgerProvenanceError,
    export_live_reasoning_ledger_snapshot,
    verify_context_pack_against_live_snapshot,
)
from test_evidence_manifest import (
    TestEvidenceManifestError,
    validate_test_evidence_manifest,
)
from test_execution_request import (
    TEST_EXECUTION_REQUEST_NAME,
    TestExecutionRequestError,
    hold_test_execution_inputs,
    validate_test_execution_request,
)
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
CHECKPOINT_RELATIVE_PATH = Path("project_state/checkpoints.sqlite3")
RESERVATION_TABLE = "aegis_run_reservations"
ACCOUNTABILITY_TABLE = "aegis_project_accountability"
RUNTIME_AUTHORITY_TABLE = "aegis_runtime_authority"
RUNTIME_AUTHORITY_RELATIVE_PATH = Path("project_state/runtime-authority.json")
RUN_STATE_SCHEMA = "aegis.run_state.v10"
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
PLANNING_AGENT_ROLES = frozenset({"TEST_PLAN_AUTHOR", "TEST_PLAN_REVIEWER"})
EXECUTION_NODE_ROLES = {
    "C": "TEST_EXECUTOR",
    "D": "TEST_RESULT_REVIEWER",
    "E": "TEST_REPORT_WRITER",
    "F": "FINAL_REVIEWER",
}
EXECUTION_AGENT_STATUSES = frozenset({"allocating", "ready"})
EXECUTION_TURN_STATUSES = frozenset(
    {"preparing", "submitting", "inProgress", "completed"}
)


class RuntimeStateError(RuntimeError):
    pass


class FrozenInputMutationError(RuntimeStateError):
    def __init__(
        self,
        message: str,
        *,
        mutation_event: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.mutation_event = (
            dict(mutation_event) if mutation_event is not None else None
        )


def new_run_id() -> str:
    created = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{created}_{uuid4().hex}"


def configured_app_server_command(
    command: Sequence[str],
    profile: Mapping[str, str] | None,
) -> tuple[str, ...]:
    if not command:
        raise ValueError("App Server command must not be empty")
    if profile is None:
        return tuple(command)
    return (
        command[0],
        "-c",
        f"model={json.dumps(profile['model'])}",
        "-c",
        f"model_reasoning_effort={json.dumps(profile['reasoning_effort'])}",
        *command[1:],
    )


def _validate_role_runtime_profiles(
    profiles: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    allowed_roles = set(PLANNING_AGENT_ROLES) | set(EXECUTION_NODE_ROLES.values())
    normalized: dict[str, dict[str, str]] = {}
    for role, profile in profiles.items():
        if role not in allowed_roles:
            raise ValueError(f"unsupported runtime profile role: {role}")
        if set(profile) != {"model", "reasoning_effort"}:
            raise ValueError(f"runtime profile for {role} has invalid fields")
        model = profile["model"]
        effort = profile["reasoning_effort"]
        if not isinstance(model, str) or not model:
            raise ValueError(f"runtime profile for {role} has no model")
        if effort not in {"low", "medium", "high", "xhigh"}:
            raise ValueError(
                f"runtime profile for {role} has unsupported reasoning effort"
            )
        normalized[role] = {"model": model, "reasoning_effort": effort}
    return normalized


_ACTIVE_COORDINATOR: ContextVar[RuntimeCoordinator | None] = ContextVar(
    "aegis_runtime_coordinator", default=None
)


class RuntimeCoordinator:
    def __init__(
        self,
        *,
        project_root: str | Path,
        artifact_path: str | Path,
        runtime_root: str | Path | None = None,
        role_skill_bindings: Mapping[
            str, Sequence[Mapping[str, object]]
        ] | None = None,
        role_runtime_profiles: Mapping[str, Mapping[str, str]] | None = None,
        run_id: str,
        upstream_port: int,
        relay_client: TraceRelayClient,
        start_node: str,
        prior_state: Mapping[str, object] | None = None,
        require_remote_witness: bool = False,
        engineering_input_manifest_path: str | Path | None = None,
        planning_reuse_run_id: str | None = None,
        planning_reuse_state: Mapping[str, object] | None = None,
        planning_reuse_context_pack_path: str | Path | None = None,
    ) -> None:
        if RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
            raise ValueError("run_id contains unsupported path characters")
        self.project_root = Path(project_root).resolve()
        self.artifact_path = Path(artifact_path).resolve()
        self.runtime_root = (
            Path(runtime_root).resolve()
            if runtime_root is not None
            else self.artifact_path
        )
        self._role_skill_bindings = {
            str(role): [dict(binding) for binding in bindings]
            for role, bindings in (role_skill_bindings or {}).items()
        }
        self._role_runtime_profiles = _validate_role_runtime_profiles(
            role_runtime_profiles or {}
        )
        self.run_id = run_id
        self.upstream_port = upstream_port
        self.relay_client = relay_client
        self.start_node = start_node
        self.require_remote_witness = require_remote_witness
        self._engineering_input_source_path = (
            Path(engineering_input_manifest_path).resolve()
            if engineering_input_manifest_path is not None
            else None
        )
        self._planning_reuse_run_id = planning_reuse_run_id
        self._planning_reuse_source_state = planning_reuse_state
        self._planning_reuse_context_pack_path = (
            Path(planning_reuse_context_pack_path).resolve()
            if planning_reuse_context_pack_path is not None
            else None
        )
        self.run_state_path = self.runtime_root / "runs" / run_id / "RUN_STATE.json"
        self._created_at_utc = _utc_now_text()
        self._current_node: str | None = None
        self._last_completed_node: str | None = None
        self._last_state: dict[str, Any] | None = None
        self._seal: StoredProjectSeal | None = None
        self._frozen_runtime_manifest: dict[str, object] | None = None
        self._remote_witness: dict[str, object] | None = None
        self._engineering_input_manifest: dict[str, object] | None = None
        self._reasoning_context_pack: dict[str, object] | None = None
        self._planning_reuse: dict[str, object] | None = None
        self._agent_registry: DynamicAgentRegistry | None = None
        self._project_lease_acquired = False
        self._instruction_receipt_specs: dict[str, dict[str, object]] = {}
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
        self._active_test_input_descriptors: list[dict[str, object]] = []
        self._registration_intent: dict[str, object] | None = None
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
        if state.get("schema") in {
            "aegis.run_state.v1",
            "aegis.run_state.v2",
            "aegis.run_state.v3",
            "aegis.run_state.v4",
            "aegis.run_state.v5",
            "aegis.run_state.v6",
            "aegis.run_state.v7",
            "aegis.run_state.v8",
            "aegis.run_state.v9",
        }:
            raise RuntimeStateError(
                "run state predates the v10 authoritative-state contract; "
                "start a new run"
            )
        if state.get("schema") != RUN_STATE_SCHEMA:
            raise RuntimeStateError("run state schema is unsupported")
        if state.get("run_id") != self.run_id:
            raise RuntimeStateError("prior run state identity mismatch")
        if state.get("start_node") != self.start_node:
            raise RuntimeStateError("prior run state start node mismatch")
        if state.get("remote_witness_required") is not self.require_remote_witness:
            raise RuntimeStateError(
                "prior run state remote witness requirement changed"
            )
        if state.get("role_runtime_profiles") != self._role_runtime_profiles:
            raise RuntimeStateError("prior run role runtime profiles changed")
        stored_root = state.get("project_root")
        if (
            not isinstance(stored_root, str)
            or Path(stored_root).resolve() != self.project_root
        ):
            raise RuntimeStateError("prior run state project root mismatch")
        stored_runtime_root = state.get("runtime_root")
        if (
            not isinstance(stored_runtime_root, str)
            or Path(stored_runtime_root).resolve() != self.runtime_root
        ):
            raise RuntimeStateError("prior run state runtime root mismatch")
        created_at = state.get("created_at_utc")
        graph_state = state.get("graph_state")
        evidence = state.get("evidence_sessions")
        planning_agents = state.get("planning_agents", {})
        planning_turns = state.get("planning_turns", [])
        planning_rounds = state.get("planning_rounds")
        execution_agents = state.get("execution_agents")
        execution_turns = state.get("execution_turns")
        execution_attempts = state.get("execution_attempts")
        registration_intent = state.get("registration_intent")
        stored_role_skill_bindings = state.get("role_skill_bindings", {})
        codex_cli_path = state.get("codex_cli_path")
        codex_cli_version = state.get("codex_cli_version")
        planning_stage_status = state.get("planning_stage_status")
        engineering_input_manifest = state.get("engineering_input_manifest")
        reasoning_context_pack = state.get("reasoning_context_pack")
        frozen_runtime_manifest = state.get("frozen_runtime_manifest")
        planning_reuse = state.get("planning_reuse")
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
        _validate_planning_evidence_records(evidence)
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
        if registration_intent is not None and not isinstance(
            registration_intent, dict
        ):
            raise RuntimeStateError("prior registration intent must be an object or null")
        _validate_registration_intent(
            registration_intent,
            run_id=self.run_id,
            upstream_port=self.upstream_port,
            execution_turns=execution_turns,
        )
        if codex_cli_path is not None and not isinstance(codex_cli_path, str):
            raise RuntimeStateError("prior Codex CLI path must be a string or null")
        if codex_cli_version is not None and not isinstance(codex_cli_version, str):
            raise RuntimeStateError("prior Codex CLI version must be a string or null")
        if planning_stage_status not in PLANNING_STAGE_STATUSES:
            raise RuntimeStateError("prior planning stage status is invalid")
        if stored_role_skill_bindings != self._role_skill_bindings:
            raise RuntimeStateError("role skill bindings changed during run recovery")
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
        self._registration_intent = (
            dict(registration_intent)
            if isinstance(registration_intent, dict)
            else None
        )
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
        if engineering_input_manifest is not None and not isinstance(
            engineering_input_manifest, dict
        ):
            raise RuntimeStateError(
                "prior engineering input manifest record must be an object or null"
            )
        if planning_reuse is not None and not isinstance(planning_reuse, dict):
            raise RuntimeStateError("prior planning reuse record must be an object or null")
        if reasoning_context_pack is not None and not isinstance(
            reasoning_context_pack, dict
        ):
            raise RuntimeStateError(
                "prior reasoning context pack record must be an object or null"
            )
        if frozen_runtime_manifest is not None and not isinstance(
            frozen_runtime_manifest, dict
        ):
            raise RuntimeStateError(
                "prior frozen runtime manifest must be an object or null"
            )
        self._engineering_input_manifest = (
            dict(engineering_input_manifest)
            if isinstance(engineering_input_manifest, dict)
            else None
        )
        self._reasoning_context_pack = (
            dict(reasoning_context_pack)
            if isinstance(reasoning_context_pack, dict)
            else None
        )
        self._frozen_runtime_manifest = (
            dict(frozen_runtime_manifest)
            if isinstance(frozen_runtime_manifest, dict)
            else None
        )
        self._planning_reuse = (
            dict(planning_reuse) if isinstance(planning_reuse, dict) else None
        )
        self._reservation_token = reservation_token

    @property
    def planning_stage_status(self) -> str:
        return self._planning_stage_status

    def preflight(self) -> None:
        with hold_verified_project_git_runtime(self.project_root) as git_command:
            self._seal = verify_expected_project_seal(
                self.project_root,
                git_executable=git_command,
                git_runtime_lock_held=True,
            )
            self._capture_frozen_runtime_manifest(git_command=git_command)
            if self.require_remote_witness:
                witness = verify_remote_project_seal_witness(
                    self.project_root,
                    self._seal,
                    git_executable=git_command,
                    git_runtime_lock_held=True,
                )
                self._remote_witness = {
                    "repository_url": witness.repository_url,
                    "protected_ref": witness.protected_ref,
                    "git_commit": witness.git_commit,
                    "sequence": witness.sequence,
                    "expected_seal": witness.expected_seal,
                    "runtime_authority_id": witness.runtime_authority_id,
                }
        _prepare_runtime_authority(
            self.runtime_root,
            project_id_hex=self._seal.project_id.hex(),
            runtime_authority_id=self._seal.runtime_authority_id,
            allow_initialize=not self.require_remote_witness,
        )
        if not self._is_resume:
            self._reject_unresolved_mutation_accountability()
        self._agent_registry = DynamicAgentRegistry(
            self.runtime_root,
            project_id=self._seal.project_id.hex(),
        )
        try:
            if self._is_resume:
                assert self._reservation_token is not None
                _validate_run_reservation(
                    self.runtime_root,
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
                    self.runtime_root,
                    self.artifact_path,
                    self.run_state_path,
                    self.run_id,
                    reservation_token,
                    payload,
                )
                self._reservation_token = reservation_token
                self._state_writable = True
            self._agent_registry.acquire_project_lease(self.run_id)
            self._project_lease_acquired = True
            if not self._is_resume:
                self._snapshot_engineering_inputs()
                if self._planning_reuse_source_state is not None:
                    self._import_planning_reuse()
            self._validate_engineering_inputs()
            if self._reasoning_context_pack is not None:
                self._validate_reasoning_context_snapshot()
            if self._planning_stage_status == "completed":
                self._validate_completed_planning_stage()
            self._reconcile_registration_intent()
            self._validate_persisted_planning_evidence_cache()
            self._validate_persisted_execution_receipt_cache()
            self._validate_persisted_instruction_receipts()
            self._recover_persisted_execution_sessions()
            self.relay_client.start()
            self._validate_persisted_execution_receipts()
        except BaseException as error:
            if self._state_writable:
                self._write_state("failed", error)
                self._release_project_lease()
            raise
        self._write_state("ready")

    def _reject_unresolved_mutation_accountability(self) -> None:
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable for accountability check")
        unresolved = _audit_run_reservation_catalog(
            self.runtime_root,
            project_id_hex=self._seal.project_id.hex(),
            project_root=self.project_root,
            runtime_authority_id=self._seal.runtime_authority_id,
        )
        if unresolved:
            raise RuntimeStateError(
                "prior frozen-input mutation still requires a recorded user reason: "
                + ", ".join(unresolved)
            )

    def execute_node(
        self,
        node_name: str,
        operation: Callable[[dict[str, Any]], dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        self._current_node = node_name
        self._last_state = dict(state)
        try:
            self._validate_frozen_project_inputs()
            if node_name in {"D", "E", "F"}:
                self._validate_completed_test_evidence_manifests()
        except FrozenInputMutationError as error:
            error = self._enrich_mutation_error(error)
            self._write_state("terminated", error)
            raise
        execution_attempt: dict[str, object] | None = None
        if node_name in EXECUTION_NODE_ROLES:
            execution_attempt = self._begin_execution_attempt(node_name, state)
            self._active_execution_attempt = execution_attempt
        self._write_state("running")
        watchers = self._start_frozen_input_watchers()
        token = _ACTIVE_COORDINATOR.set(self)
        try:
            result = operation(state)
        except BaseException as error:
            watch_events = self._stop_frozen_input_watchers(watchers)
            mutation = self._watcher_mutation_error(watch_events)
            if mutation is not None:
                self._write_state("terminated", mutation)
                raise mutation from error
            if isinstance(error, FrozenInputMutationError):
                error = self._enrich_mutation_error(error)
            self._write_state(
                "terminated" if isinstance(error, FrozenInputMutationError) else "failed",
                error,
            )
            raise
        finally:
            _ACTIVE_COORDINATOR.reset(token)
            self._active_execution_attempt = None
        try:
            watch_events = self._stop_frozen_input_watchers(watchers)
            mutation = self._watcher_mutation_error(watch_events)
            if mutation is not None:
                raise mutation
            self._validate_frozen_project_inputs()
            if execution_attempt is not None:
                if node_name == "C":
                    self._seal_test_evidence_manifest(execution_attempt)
                if node_name == "F":
                    self._seal_final_review_verdict(execution_attempt, result)
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
            if isinstance(error, FrozenInputMutationError):
                error = self._enrich_mutation_error(error)
            self._write_state(
                "terminated" if isinstance(error, FrozenInputMutationError) else "failed",
                error,
            )
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

    def test_execution_control(self) -> dict[str, object]:
        attempt = self._active_execution_attempt
        if attempt is None or attempt.get("node") != "C":
            raise RuntimeStateError(
                "test execution control is available only during an active C attempt"
            )
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable for C")
        attempt_id = str(attempt["attempt_id"])
        return {
            **self.execution_node_control(),
            "schema": "aegis.test_execution_control.v1",
            "project_id_hex": self._seal.project_id.hex(),
            "workflow_run_id": self.run_id,
            "attempt_id": attempt_id,
            "manifest_path": str(
                (self.artifact_path / "test_evidence_manifest.json").resolve()
            ),
            "request_path": str(
                (self.artifact_path / TEST_EXECUTION_REQUEST_NAME).resolve()
            ),
            "evidence_root": str(
                (self.artifact_path / "evidence" / attempt_id).resolve()
            ),
            "execution_mode": "COORDINATOR_WINDOWS_JOB_AFTER_TURN",
            "tracerelay_session_binding": "REQUEST_AUTHOR_TURN_ONLY",
        }

    def execution_node_control(self) -> dict[str, object]:
        attempt = self._active_execution_attempt
        if attempt is None:
            raise RuntimeStateError(
                "execution control is available only during an active C-F attempt"
            )
        node = str(attempt.get("node"))
        if node not in EXECUTION_NODE_ROLES:
            raise RuntimeStateError("execution control has an invalid active node")
        approved_path, handoff_path = self._expected_planning_handoff_paths()
        context_path: object = None
        context_sha256: object = None
        if self._planning_reuse is not None:
            context_path = self._planning_reuse.get("context_pack_path")
            context_sha256 = self._planning_reuse.get("context_pack_sha256")
        elif self._planning_rounds:
            context_path = self._planning_rounds[-1].get("context_pack_path")
            context_sha256 = self._planning_rounds[-1].get("context_pack_sha256")
        evidence_manifests = [
            {
                "attempt_id": prior["attempt_id"],
                "path": prior["test_evidence_manifest_path"],
                "sha256": prior["test_evidence_manifest_sha256"],
                "test_ids": list(prior["test_ids"]),
            }
            for prior in self._execution_attempts
            if prior.get("node") == "C" and prior.get("status") == "completed"
        ]
        return {
            "schema": "aegis.execution_control.v1",
            "project_root": str(self.project_root),
            "project_id_hex": (
                self._seal.project_id.hex() if self._seal is not None else None
            ),
            "artifact_path": str(self.artifact_path),
            "node": node,
            "role": EXECUTION_NODE_ROLES[node],
            "workflow_run_id": self.run_id,
            "attempt_id": attempt["attempt_id"],
            "engineering_input_manifest": self._engineering_input_control(),
            "planning_handoff": (
                _file_control_descriptor(handoff_path)
                if handoff_path.is_file()
                else None
            ),
            "approved_test_plan": (
                _file_control_descriptor(approved_path)
                if approved_path.is_file()
                else None
            ),
            "reasoning_ledger_context_pack": {
                "path": context_path,
                "sha256": context_sha256,
            },
            "test_evidence_manifests": evidence_manifests,
        }

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
                "execution agent turns require an active C-F node attempt"
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
        developer_instructions = self._compose_instruction_receipt_protocol(
            role_key, developer_instructions
        )
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

        command = configured_app_server_command(
            default_app_server_command(),
            self._role_runtime_profiles.get(role_key),
        )
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
            operation_id = self._begin_registration_intent(
                node=str(node), receipt=receipt
            )
            try:
                process = self.relay_client.open_managed_process(
                    process_command,
                    upstream_port=self.upstream_port,
                    registration_operation_id=operation_id,
                    **popen_options,
                )
            except BaseException as error:
                try:
                    self._record_registered_process_start_failure(
                        node=str(node), receipt=receipt
                    )
                except BaseException as persistence_error:
                    error.add_note(
                        "registered TraceRelay session persistence also failed: "
                        f"{persistence_error}"
                    )
                raise
            self._persist_registration_result(
                process.registration,
                None,
                node=str(node),
                receipt=receipt,
                process_pid=process.pid,
                process_creation_time_100ns=process.creation_time_100ns,
            )
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
                self._prepare_instruction_receipt(role_key)
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
            self._seal_instruction_receipt(
                role_key, job_id, receipt
            )
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
        if role_key not in PLANNING_AGENT_ROLES:
            raise ValueError(f"unsupported planning role: {role_key}")
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
            self._prepare_instruction_receipt(role_key)
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
        self._seal_instruction_receipt(role_key, resolved_job_id, pending)
        return self._complete_planning_turn(pending, result)

    def prepare_planning_agents(self, role_instructions: Mapping[str, str]) -> None:
        if not role_instructions:
            raise ValueError("at least one planning role is required")
        self._ensure_planning_app_server()
        for role_key, instructions in role_instructions.items():
            if role_key not in PLANNING_AGENT_ROLES or not instructions:
                raise ValueError("planning roles require instructions")
            self._ensure_planning_thread(role_key, developer_instructions=instructions)

    def _snapshot_engineering_inputs(self) -> None:
        source_path = self._engineering_input_source_path
        if source_path is None:
            return
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable for engineering inputs")
        try:
            source = validate_engineering_input_manifest(
                source_path,
                project_root=self.project_root,
                project_id_hex=self._seal.project_id.hex(),
            )
        except EngineeringInputManifestError as error:
            raise RuntimeStateError(f"invalid engineering input manifest: {error}") from error
        snapshot_path = (
            self.artifact_path / "ENGINEERING_INPUT_MANIFEST.json"
        ).resolve()
        source_bytes = source.path.read_bytes()
        if snapshot_path.exists():
            if snapshot_path.read_bytes() != source_bytes:
                raise FrozenInputMutationError(
                    "immutable engineering input manifest snapshot changed"
                )
        else:
            _atomic_write_bytes(snapshot_path, source_bytes)
        snapshot = validate_engineering_input_manifest(
            snapshot_path,
            project_root=self.project_root,
            project_id_hex=self._seal.project_id.hex(),
            expected_manifest_path=snapshot_path,
        )
        frozen_root = (self.artifact_path / "engineering-inputs").resolve()
        frozen_documents: list[dict[str, object]] = []
        documents = snapshot.payload["documents"]
        assert isinstance(documents, list)
        for index, document in enumerate(documents, start=1):
            assert isinstance(document, dict)
            kind = str(document["kind"])
            source_document_path = Path(str(document["path"])).resolve()
            source_document = _read_required_file(
                source_document_path,
                f"engineering input {kind}",
            )
            suffix = source_document_path.suffix.lower()
            if not suffix or len(suffix) > 16 or not suffix[1:].isalnum():
                suffix = ".bin"
            frozen_path = (
                frozen_root
                / f"{index:04d}-{kind}-{str(document['sha256'])[:16]}{suffix}"
            ).resolve()
            if frozen_path.exists():
                if frozen_path.read_bytes() != source_document:
                    raise FrozenInputMutationError(
                        f"immutable engineering input snapshot changed: {kind}"
                    )
            else:
                _atomic_write_bytes(frozen_path, source_document)
            frozen_documents.append(
                {
                    "kind": kind,
                    "source_path": str(source_document_path),
                    "source_size": document["size"],
                    "source_sha256": document["sha256"],
                    "snapshot_path": str(frozen_path),
                    "snapshot_size": len(source_document),
                    "snapshot_sha256": hashlib.sha256(source_document).hexdigest(),
                }
            )
        self._engineering_input_manifest = {
            "snapshot_path": str(snapshot_path),
            "snapshot_sha256": snapshot.sha256,
            "documents_sha256": snapshot.documents_sha256,
            "documents": frozen_documents,
        }

    def _validate_engineering_inputs(self) -> None:
        record = self._engineering_input_manifest
        if record is None:
            return
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable for engineering inputs")
        expected_path = (
            self.artifact_path / "ENGINEERING_INPUT_MANIFEST.json"
        ).resolve()
        raw_path = record.get("snapshot_path")
        if not isinstance(raw_path, str) or Path(raw_path).resolve() != expected_path:
            raise FrozenInputMutationError(
                "engineering input manifest snapshot path changed"
            )
        try:
            validated = validate_engineering_input_manifest(
                expected_path,
                project_root=self.project_root,
                project_id_hex=self._seal.project_id.hex(),
                expected_manifest_path=expected_path,
            )
        except EngineeringInputManifestError as error:
            raise FrozenInputMutationError(
                f"frozen engineering inputs changed during A-F: {error}"
            ) from error
        if (
            validated.sha256 != record.get("snapshot_sha256")
            or validated.documents_sha256 != record.get("documents_sha256")
        ):
            raise FrozenInputMutationError(
                "frozen engineering input manifest metadata changed during A-F"
            )
        documents = record.get("documents")
        if not isinstance(documents, list) or not documents:
            raise FrozenInputMutationError(
                "frozen engineering input snapshots are missing"
            )
        source_documents = validated.payload["documents"]
        assert isinstance(source_documents, list)
        if len(source_documents) != len(documents):
            raise FrozenInputMutationError(
                "frozen engineering input snapshot count changed"
            )
        frozen_root = (self.artifact_path / "engineering-inputs").resolve()
        for index, (source, frozen) in enumerate(
            zip(source_documents, documents, strict=True), start=1
        ):
            if not isinstance(source, dict) or not isinstance(frozen, dict):
                raise FrozenInputMutationError(
                    "frozen engineering input snapshot metadata is invalid"
                )
            expected_fields = {
                "kind",
                "source_path",
                "source_size",
                "source_sha256",
                "snapshot_path",
                "snapshot_size",
                "snapshot_sha256",
            }
            if set(frozen) != expected_fields:
                raise FrozenInputMutationError(
                    "frozen engineering input snapshot fields changed"
                )
            if (
                frozen["kind"] != source["kind"]
                or Path(str(frozen["source_path"])).resolve()
                != Path(str(source["path"])).resolve()
                or frozen["source_size"] != source["size"]
                or frozen["source_sha256"] != source["sha256"]
            ):
                raise FrozenInputMutationError(
                    "frozen engineering input source binding changed"
                )
            snapshot_document_path = Path(str(frozen["snapshot_path"])).resolve()
            expected_prefix = f"{index:04d}-{source['kind']}-{str(source['sha256'])[:16]}"
            if (
                snapshot_document_path.parent != frozen_root
                or not snapshot_document_path.name.startswith(expected_prefix)
            ):
                raise FrozenInputMutationError(
                    "frozen engineering input snapshot path changed"
                )
            snapshot_document = _read_required_file(
                snapshot_document_path,
                f"frozen engineering input {source['kind']}",
            )
            if (
                len(snapshot_document) != frozen["snapshot_size"]
                or hashlib.sha256(snapshot_document).hexdigest()
                != frozen["snapshot_sha256"]
                or frozen["snapshot_sha256"] != source["sha256"]
            ):
                raise FrozenInputMutationError(
                    "frozen engineering input snapshot content changed"
                )

    def _engineering_input_control(self) -> dict[str, object] | None:
        record = self._engineering_input_manifest
        if record is None:
            return None
        return {
            "path": record["snapshot_path"],
            "sha256": record["snapshot_sha256"],
            "documents_sha256": record["documents_sha256"],
            "documents": [dict(item) for item in record["documents"]],
        }

    def _snapshot_reasoning_context_pack(self, source_path: str | Path) -> None:
        if self._seal is None or self._engineering_input_manifest is None:
            raise RuntimeStateError(
                "reasoning context pack requires sealed engineering inputs"
            )
        source = Path(source_path).resolve()
        try:
            validated_source = validate_reasoning_context_pack(
                source,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                project_id_hex=self._seal.project_id.hex(),
                project_seal=self._seal.expected_seal,
                engineering_documents_sha256=str(
                    self._engineering_input_manifest["documents_sha256"]
                ),
            )
        except ReasoningContextPackError as error:
            raise RuntimeStateError(f"invalid reasoning context pack: {error}") from error
        snapshot_path = (
            self.artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        ).resolve()
        source_bytes = _read_required_file(source, "reasoning context pack")
        if snapshot_path.exists():
            if snapshot_path.read_bytes() != source_bytes:
                raise FrozenInputMutationError(
                    "immutable reasoning context pack snapshot changed"
                )
        else:
            _atomic_write_bytes(snapshot_path, source_bytes)
        try:
            snapshot = validate_reasoning_context_pack(
                snapshot_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                project_id_hex=self._seal.project_id.hex(),
                project_seal=self._seal.expected_seal,
                engineering_documents_sha256=str(
                    self._engineering_input_manifest["documents_sha256"]
                ),
                expected_path=snapshot_path,
            )
        except ReasoningContextPackError as error:
            raise RuntimeStateError(
                f"invalid reasoning context pack snapshot: {error}"
            ) from error
        try:
            live_snapshot = export_live_reasoning_ledger_snapshot(
                self.project_root,
                project_id_hex=self._seal.project_id.hex(),
            )
            live_proof = verify_context_pack_against_live_snapshot(
                snapshot.payload, live_snapshot
            )
        except ReasoningLedgerProvenanceError as error:
            raise RuntimeStateError(
                f"reasoning context pack has no live-ledger provenance: {error}"
            ) from error
        ledger_snapshot_path = (
            self.artifact_path / "REASONING_LEDGER_SNAPSHOT.json"
        ).resolve()
        if ledger_snapshot_path.exists():
            if ledger_snapshot_path.read_bytes() != live_proof.encoded:
                raise FrozenInputMutationError(
                    "immutable Coordinator ledger snapshot changed"
                )
        else:
            _atomic_write_bytes(ledger_snapshot_path, live_proof.encoded)
        self._reasoning_context_pack = {
            "source_path": str(source),
            "snapshot_path": str(snapshot_path),
            "size": len(source_bytes),
            "sha256": snapshot.sha256,
            "task_id": snapshot.task_id,
            "agent_role": snapshot.agent_role,
            "ledger_revision": snapshot.ledger_revision,
            "ledger_snapshot_sha256": snapshot.ledger_snapshot_sha256,
            "coordinator_ledger_snapshot_path": str(ledger_snapshot_path),
            "coordinator_ledger_snapshot_size": len(live_proof.encoded),
            "coordinator_ledger_snapshot_sha256": live_proof.sha256,
        }

    def _validate_reasoning_context_snapshot(self) -> None:
        record = self._reasoning_context_pack
        if record is None:
            raise FrozenInputMutationError("reasoning context pack snapshot is missing")
        if self._seal is None or self._engineering_input_manifest is None:
            raise RuntimeStateError(
                "reasoning context pack validation requires sealed engineering inputs"
            )
        expected_path = (
            self.artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        ).resolve()
        source_path_value = record.get("source_path")
        source_size = record.get("size")
        source_sha256 = record.get("sha256")
        if (
            not isinstance(source_path_value, str)
            or not isinstance(source_size, int)
            or isinstance(source_size, bool)
            or not isinstance(source_sha256, str)
        ):
            raise FrozenInputMutationError(
                "reasoning context pack source metadata changed"
            )
        source_bytes = _read_required_file(
            Path(source_path_value), "reasoning context pack source"
        )
        if (
            len(source_bytes) != source_size
            or hashlib.sha256(source_bytes).hexdigest() != source_sha256
        ):
            raise FrozenInputMutationError(
                "reasoning context changed after its source was frozen"
            )
        raw_path = record.get("snapshot_path")
        if not isinstance(raw_path, str) or Path(raw_path).resolve() != expected_path:
            raise FrozenInputMutationError(
                "reasoning context pack snapshot path changed"
            )
        try:
            validated = validate_reasoning_context_pack(
                expected_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                project_id_hex=self._seal.project_id.hex(),
                project_seal=self._seal.expected_seal,
                engineering_documents_sha256=str(
                    self._engineering_input_manifest["documents_sha256"]
                ),
                expected_path=expected_path,
            )
        except ReasoningContextPackError as error:
            raise FrozenInputMutationError(
                f"frozen reasoning context pack changed: {error}"
            ) from error
        if (
            validated.sha256 != record.get("sha256")
            or validated.task_id != record.get("task_id")
            or validated.agent_role != record.get("agent_role")
            or validated.ledger_revision != record.get("ledger_revision")
            or validated.ledger_snapshot_sha256
            != record.get("ledger_snapshot_sha256")
        ):
            raise FrozenInputMutationError(
                "frozen reasoning context pack metadata changed"
            )
        ledger_snapshot_path = record.get("coordinator_ledger_snapshot_path")
        expected_ledger_snapshot_path = (
            self.artifact_path / "REASONING_LEDGER_SNAPSHOT.json"
        ).resolve()
        if (
            not isinstance(ledger_snapshot_path, str)
            or Path(ledger_snapshot_path).resolve() != expected_ledger_snapshot_path
        ):
            raise FrozenInputMutationError(
                "Coordinator reasoning ledger snapshot path changed"
            )
        ledger_snapshot_bytes = _read_required_file(
            expected_ledger_snapshot_path, "Coordinator reasoning ledger snapshot"
        )
        if (
            len(ledger_snapshot_bytes)
            != record.get("coordinator_ledger_snapshot_size")
            or hashlib.sha256(ledger_snapshot_bytes).hexdigest()
            != record.get("coordinator_ledger_snapshot_sha256")
            or record.get("coordinator_ledger_snapshot_sha256")
            != record.get("ledger_snapshot_sha256")
        ):
            raise FrozenInputMutationError(
                "Coordinator reasoning ledger snapshot changed"
            )
        try:
            live_snapshot = export_live_reasoning_ledger_snapshot(
                self.project_root,
                project_id_hex=self._seal.project_id.hex(),
            )
            live_proof = verify_context_pack_against_live_snapshot(
                validated.payload, live_snapshot
            )
        except ReasoningLedgerProvenanceError as error:
            raise FrozenInputMutationError(
                f"live reasoning ledger changed or became unverifiable: {error}"
            ) from error
        if (
            live_proof.encoded != ledger_snapshot_bytes
            or live_proof.sha256
            != record.get("coordinator_ledger_snapshot_sha256")
        ):
            raise FrozenInputMutationError(
                "live reasoning ledger changed during A-F"
            )

    def _import_planning_reuse(self) -> None:
        source_state = self._planning_reuse_source_state
        parent_run_id = self._planning_reuse_run_id
        context_path = self._planning_reuse_context_pack_path
        if source_state is None or parent_run_id is None or context_path is None:
            raise RuntimeStateError(
                "planning reuse requires source state, parent run ID, and context pack"
            )
        if self.start_node != "C":
            raise RuntimeStateError("planning reuse is valid only for a new C-start run")
        if source_state.get("schema") != RUN_STATE_SCHEMA:
            raise RuntimeStateError("planning reuse source uses an unsupported run schema")
        if source_state.get("run_id") != parent_run_id:
            raise RuntimeStateError("planning reuse source run identity mismatch")
        self._validate_planning_reuse_source_state(source_state, parent_run_id)
        if source_state.get("status") not in {"completed", "terminated"}:
            raise RuntimeStateError("planning reuse source run is not terminal")
        if source_state.get("planning_stage_status") != "completed":
            raise RuntimeStateError("planning reuse source has no completed planning stage")
        source_inputs = source_state.get("engineering_input_manifest")
        current_inputs = self._engineering_input_manifest
        if not isinstance(source_inputs, dict) or current_inputs is None:
            raise RuntimeStateError("planning reuse requires sealed engineering inputs")
        if source_inputs.get("documents_sha256") != current_inputs.get(
            "documents_sha256"
        ):
            raise RuntimeStateError(
                "requirements or implementation plan changed; rerun A-F from A"
            )
        source_plan_path, source_plan_sha256, source_review_path, review = (
            self._planning_reuse_source_artifacts(source_state)
        )
        source_plan = _read_required_file(source_plan_path, "reused approved test plan")
        if hashlib.sha256(source_plan).hexdigest() != source_plan_sha256:
            raise FrozenInputMutationError("source approved test plan changed before reuse")
        source_review = _read_required_file(
            source_review_path, "reused planning review report"
        )
        source_review_sha256 = _require_sha256(
            review.get("review_report_sha256"), "review_report_sha256"
        )
        if hashlib.sha256(source_review).hexdigest() != source_review_sha256:
            raise FrozenInputMutationError("source planning review changed before reuse")
        self._snapshot_reasoning_context_pack(context_path)
        assert self._reasoning_context_pack is not None
        context_path = Path(
            str(self._reasoning_context_pack["snapshot_path"])
        ).resolve()
        context_sha256 = str(self._reasoning_context_pack["sha256"])

        reuse_root = (self.artifact_path / "planning-reuse").resolve()
        approved_path, handoff_path = self._expected_planning_handoff_paths()
        review_path = (reuse_root / "SOURCE_TEST_PLAN_REVIEW.md").resolve()
        source_state_path = (reuse_root / "SOURCE_RUN_STATE.json").resolve()
        _atomic_write_bytes(approved_path, source_plan)
        _atomic_write_bytes(review_path, source_review)
        source_state_bytes = json.dumps(
            source_state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write_bytes(source_state_path, source_state_bytes)
        self._planning_reuse = {
            "schema": "aegis.planning_reuse.v1",
            "parent_run_id": parent_run_id,
            "source_run_state_snapshot_path": str(source_state_path),
            "source_run_state_snapshot_sha256": hashlib.sha256(
                source_state_bytes
            ).hexdigest(),
            "approved_plan_path": str(approved_path),
            "approved_plan_sha256": source_plan_sha256,
            "review_report_path": str(review_path),
            "review_report_sha256": source_review_sha256,
            "score": review["score"],
            "error_count": review["error_count"],
            "warning_count": review["warning_count"],
            "verdict": review["verdict"],
            "context_pack_path": str(context_path),
            "context_pack_sha256": context_sha256,
            "engineering_documents_sha256": current_inputs["documents_sha256"],
            "handoff_path": str(handoff_path),
            "created_at_utc": _utc_now_text(),
        }
        _atomic_write_json(handoff_path, self._planning_reuse_handoff_payload())
        self._planning_stage_status = "completed"
        self._validate_planning_reuse()
        self._write_state("ready")

    def _validate_planning_reuse_source_state(
        self,
        source_state: Mapping[str, object],
        parent_run_id: str,
    ) -> None:
        if self._seal is None:
            raise RuntimeStateError("planning reuse requires a verified project seal")
        reservation_token = source_state.get("reservation_token")
        if (
            not isinstance(reservation_token, str)
            or RESERVATION_TOKEN_PATTERN.fullmatch(reservation_token) is None
        ):
            raise RuntimeStateError(
                "planning reuse source has an invalid reservation token"
            )
        expected_artifacts = (
            self.runtime_root / "runs" / parent_run_id / "artifacts"
        ).resolve()
        _validate_run_reservation(
            self.runtime_root,
            expected_artifacts,
            parent_run_id,
            reservation_token,
            state_payload=source_state,
        )
        stored_project_root = source_state.get("project_root")
        stored_runtime_root = source_state.get("runtime_root")
        stored_artifacts = source_state.get("artifact_path")
        if (
            not isinstance(stored_project_root, str)
            or Path(stored_project_root).resolve() != self.project_root
        ):
            raise RuntimeStateError("planning reuse source project root differs")
        if (
            not isinstance(stored_runtime_root, str)
            or Path(stored_runtime_root).resolve() != self.runtime_root
        ):
            raise RuntimeStateError("planning reuse source runtime root differs")
        if (
            not isinstance(stored_artifacts, str)
            or Path(stored_artifacts).resolve() != expected_artifacts
        ):
            raise RuntimeStateError("planning reuse source artifact path differs")
        if (
            source_state.get("project_id_hex") != self._seal.project_id.hex()
            or source_state.get("seal_sequence") != self._seal.sequence
            or source_state.get("expected_seal") != self._seal.expected_seal
        ):
            raise RuntimeStateError("planning reuse source project seal differs")
        if source_state.get("remote_witness_required") is not self.require_remote_witness:
            raise RuntimeStateError("planning reuse source witness requirement differs")
        if self.require_remote_witness and source_state.get("remote_witness") != (
            self._remote_witness
        ):
            raise RuntimeStateError("planning reuse source remote witness differs")

        evidence = source_state.get("evidence_sessions")
        turns = source_state.get("planning_turns")
        rounds = source_state.get("planning_rounds")
        if (
            not isinstance(evidence, list)
            or not all(isinstance(item, dict) for item in evidence)
            or not isinstance(turns, list)
            or not all(isinstance(item, dict) for item in turns)
            or not isinstance(rounds, list)
            or not all(isinstance(item, dict) for item in rounds)
        ):
            raise RuntimeStateError("planning reuse source planning records are invalid")
        _validate_planning_evidence_records(evidence)
        _validate_planning_turns(turns)
        _validate_planning_rounds(rounds)
        if not rounds or rounds[-1].get("status") != "approved":
            raise RuntimeStateError("planning reuse source has no approved final round")
        completed_roles = {
            turn.get("role")
            for turn in turns
            if turn.get("status") == "completed"
        }
        if not PLANNING_AGENT_ROLES.issubset(completed_roles):
            raise RuntimeStateError(
                "planning reuse source lacks completed author and reviewer turns"
            )
        context_record = source_state.get("reasoning_context_pack")
        final_round = rounds[-1]
        if (
            not isinstance(context_record, dict)
            or final_round.get("context_pack_path")
            != context_record.get("snapshot_path")
            or final_round.get("context_pack_sha256") != context_record.get("sha256")
        ):
            raise RuntimeStateError(
                "planning reuse source context pack binding is incomplete"
            )

    def _planning_reuse_source_artifacts(
        self, source_state: Mapping[str, object]
    ) -> tuple[Path, str, Path, Mapping[str, object]]:
        nested = source_state.get("planning_reuse")
        if isinstance(nested, dict):
            review = nested
            return (
                Path(str(nested.get("approved_plan_path"))).resolve(),
                _require_sha256(
                    nested.get("approved_plan_sha256"), "approved_plan_sha256"
                ),
                Path(str(nested.get("review_report_path"))).resolve(),
                review,
            )
        rounds = source_state.get("planning_rounds")
        if not isinstance(rounds, list) or not rounds or not isinstance(rounds[-1], dict):
            raise RuntimeStateError("planning reuse source has no approved planning record")
        review = rounds[-1]
        if review.get("status") != "approved":
            raise RuntimeStateError("planning reuse source planning record is not approved")
        return (
            Path(str(review.get("approved_plan_path"))).resolve(),
            _require_sha256(review.get("plan_sha256"), "plan_sha256"),
            Path(str(review.get("review_report_path"))).resolve(),
            review,
        )

    def _planning_reuse_handoff_payload(self) -> dict[str, object]:
        if self._planning_reuse is None:
            raise RuntimeStateError("planning reuse record is unavailable")
        return {
            "schema": "aegis.planning_handoff.v2",
            "run_id": self.run_id,
            "parent_run_id": self._planning_reuse["parent_run_id"],
            "approved_plan_path": self._planning_reuse["approved_plan_path"],
            "approved_plan_sha256": self._planning_reuse["approved_plan_sha256"],
            "review_report_path": self._planning_reuse["review_report_path"],
            "review_report_sha256": self._planning_reuse["review_report_sha256"],
            "engineering_documents_sha256": self._planning_reuse[
                "engineering_documents_sha256"
            ],
            "context_pack_path": self._planning_reuse["context_pack_path"],
            "context_pack_sha256": self._planning_reuse["context_pack_sha256"],
            "score": self._planning_reuse["score"],
            "error_count": self._planning_reuse["error_count"],
            "warning_count": self._planning_reuse["warning_count"],
            "verdict": self._planning_reuse["verdict"],
        }

    def _validate_planning_reuse(self) -> None:
        record = self._planning_reuse
        if record is None:
            raise RuntimeStateError("completed reused planning stage has no reuse record")
        if record.get("schema") != "aegis.planning_reuse.v1":
            raise RuntimeStateError("planning reuse record has an unsupported schema")
        if record.get("engineering_documents_sha256") != (
            self._engineering_input_manifest or {}
        ).get("documents_sha256"):
            raise FrozenInputMutationError(
                "planning reuse engineering inputs no longer match"
            )
        approved_path, handoff_path = self._expected_planning_handoff_paths()
        fixed_paths = {
            "approved_plan_path": approved_path,
            "review_report_path": (
                self.artifact_path / "planning-reuse" / "SOURCE_TEST_PLAN_REVIEW.md"
            ).resolve(),
            "source_run_state_snapshot_path": (
                self.artifact_path / "planning-reuse" / "SOURCE_RUN_STATE.json"
            ).resolve(),
            "handoff_path": handoff_path,
        }
        for field, expected in fixed_paths.items():
            value = record.get(field)
            if not isinstance(value, str) or Path(value).resolve() != expected:
                raise FrozenInputMutationError(f"planning reuse {field} changed")
        checks = (
            (approved_path, "approved_plan_sha256", "reused approved test plan"),
            (
                fixed_paths["review_report_path"],
                "review_report_sha256",
                "reused planning review report",
            ),
            (
                fixed_paths["source_run_state_snapshot_path"],
                "source_run_state_snapshot_sha256",
                "reused source run state",
            ),
            (
                Path(str(record.get("context_pack_path"))).resolve(),
                "context_pack_sha256",
                "reasoning context pack",
            ),
        )
        for path, hash_field, label in checks:
            actual = hashlib.sha256(_read_required_file(path, label)).hexdigest()
            if actual != _require_sha256(record.get(hash_field), hash_field):
                raise FrozenInputMutationError(f"{label} changed after planning reuse")
        if not _planning_review_is_accepted(record):
            raise RuntimeStateError("reused planning review does not satisfy approval rules")
        try:
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise FrozenInputMutationError("reused planning handoff is unreadable") from error
        if handoff != self._planning_reuse_handoff_payload():
            raise FrozenInputMutationError("reused planning handoff changed")

    def prepare_planning_author(
        self, context_pack_path: str | Path
    ) -> dict[str, object]:
        if self._seal is None:
            raise RuntimeStateError("planning handoff requires a verified project seal")
        supplied_path = Path(context_pack_path).resolve()
        if self._reasoning_context_pack is None:
            self._snapshot_reasoning_context_pack(supplied_path)
            self._write_state("ready")
        assert self._reasoning_context_pack is not None
        permitted_paths = {
            Path(str(self._reasoning_context_pack["source_path"])).resolve(),
            Path(str(self._reasoning_context_pack["snapshot_path"])).resolve(),
        }
        if supplied_path not in permitted_paths:
            raise RuntimeStateError(
                "planning context source changed after the run snapshot was created"
            )
        self._validate_reasoning_context_snapshot()
        context_path = Path(
            str(self._reasoning_context_pack["snapshot_path"])
        ).resolve()
        context_sha256 = str(self._reasoning_context_pack["sha256"])
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
            self.run_state_path.parent / "artifacts" / "graph" / "A" / round_id
        )
        record: dict[str, object] = {
            "round_id": round_id,
            "status": "allocating",
            "project_seal": self._seal.expected_seal,
            "context_pack_path": str(context_path),
            "context_pack_sha256": context_sha256,
            "engineering_input_manifest": self._engineering_input_control(),
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
            "semantic_issues": None,
            "prior_issue_assessments": [],
            "repeated_unresolved_issue_ids": [],
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
            "engineering_input_manifest": self._engineering_input_control(),
            "plan_path": record["plan_path"],
            "reviewed_plan_sha256": record["plan_sha256"],
            "review_report_path": record["review_report_path"],
            "acceptance_threshold": PLANNING_REVIEW_THRESHOLD,
            "prior_semantic_issues": (
                self._planning_rounds[-2].get("semantic_issues", [])
                if len(self._planning_rounds) > 1
                and self._planning_rounds[-2].get("status") == "rejected"
                else []
            ),
            "instructions": (
                "Review only plan_path at reviewed_plan_sha256. Write the complete "
                "review to review_report_path. Return reviewed_plan_sha256, score, "
                "error_count, warning_count, verdict, semantic_issues, and one "
                "evidence-backed prior_issue_assessment for every prior semantic "
                "issue. Do not modify the plan or any prior round."
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
        semantic_issues = _validate_semantic_issues(
            node_output.get("semantic_issues", [])
        )
        if accepted_candidate := (
            verdict == "PASS" and score >= PLANNING_REVIEW_THRESHOLD and error_count == 0
        ):
            if semantic_issues:
                raise RuntimeStateError(
                    "an accepted planning review cannot contain semantic issues"
                )
        elif not semantic_issues:
            raise RuntimeStateError(
                "a rejected planning review must contain at least one semantic issue"
            )
        prior_round = self._planning_rounds[-2] if len(self._planning_rounds) > 1 else None
        prior_issues = {
            str(issue["semantic_issue_id"]): issue
            for issue in (
                prior_round.get("semantic_issues", [])
                if isinstance(prior_round, dict)
                and prior_round.get("status") == "rejected"
                else []
            )
            if isinstance(issue, dict)
        }
        assessments = _validate_prior_issue_assessments(
            node_output.get("prior_issue_assessments", []),
            prior_issue_ids=set(prior_issues),
            current_issue_ids={
                str(issue["semantic_issue_id"]) for issue in semantic_issues
            },
        )
        repeated_issue_ids: list[str] = []
        for issue in semantic_issues:
            predecessor_ids = issue.get("predecessor_issue_ids", [])
            assert isinstance(predecessor_ids, list)
            unknown = [
                issue_id for issue_id in predecessor_ids if issue_id not in prior_issues
            ]
            if unknown:
                raise RuntimeStateError(
                    "semantic issue predecessor does not identify a prior unresolved issue: "
                    + ", ".join(unknown)
                )
        for assessment in assessments:
            prior_issue_id = str(assessment["prior_semantic_issue_id"])
            current_ids = assessment["current_semantic_issue_ids"]
            assert isinstance(current_ids, list)
            if assessment["disposition"] == "REPEATED_UNRESOLVED":
                for current_id in current_ids:
                    current_issue = next(
                        issue
                        for issue in semantic_issues
                        if issue["semantic_issue_id"] == current_id
                    )
                    if prior_issue_id not in current_issue.get(
                        "predecessor_issue_ids", []
                    ):
                        raise RuntimeStateError(
                            "semantic mapping receipt and issue predecessor links differ"
                        )
                    repeated_issue_ids.append(str(current_id))
        report_path = Path(str(record["review_report_path"]))
        report_bytes = _read_required_file(report_path, "planning review report")
        accepted = accepted_candidate
        record.update(
            status="publishing" if accepted else "rejected",
            review_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
            reviewed_plan_sha256=reviewed_plan_sha256,
            score=score,
            error_count=error_count,
            warning_count=warning_count,
            verdict=verdict,
            semantic_issues=semantic_issues,
            prior_issue_assessments=assessments,
            repeated_unresolved_issue_ids=sorted(set(repeated_issue_ids)),
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
            "engineering_input_manifest": self._engineering_input_control(),
            "plan_path": record["plan_path"],
            "previous_review_report_path": (
                previous["review_report_path"] if previous is not None else None
            ),
            "previous_review_report_sha256": (
                previous["review_report_sha256"] if previous is not None else None
            ),
            "previous_semantic_issues": (
                previous.get("semantic_issues", []) if previous is not None else []
            ),
            "repeated_unresolved_issue_ids": (
                previous.get("repeated_unresolved_issue_ids", [])
                if previous is not None
                else []
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
        self._validate_reasoning_context_snapshot()
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
        if self._planning_reuse is not None:
            if self._planning_rounds:
                raise RuntimeStateError(
                    "reused planning stage cannot also contain local planning rounds"
                )
            self._validate_planning_reuse()
            return
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
            "engineering_input_manifest": self._engineering_input_control(),
            "approved_plan_path": str(approved_path),
            "approved_plan_sha256": record["plan_sha256"],
            "reviewed_plan_sha256": record["reviewed_plan_sha256"],
            "review_report_path": record["review_report_path"],
            "review_report_sha256": record["review_report_sha256"],
            "score": record["score"],
            "error_count": record["error_count"],
            "warning_count": record["warning_count"],
            "verdict": record["verdict"],
            "semantic_issues": record["semantic_issues"],
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

    def _validate_persisted_planning_evidence_cache(self) -> None:
        for entry in self._evidence_sessions:
            if entry.get("node") != "planning":
                continue
            _validate_planning_evidence_record(entry)
            raw_status = entry.get("verification_status")
            application_status = entry.get("application_verification_status")
            if (
                raw_status == "VALID_COMPLETE"
                and application_status == "VALID_COMPLETE"
            ):
                continue
            if raw_status == "UNVERIFIED" and application_status is None:
                continue
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

    def _capture_frozen_runtime_manifest(
        self, *, git_command: str | None = None
    ) -> None:
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable")
        try:
            resolved = resolve_runtime_behavior_scope(
                self.project_root, self._seal.project_id
            )
        except RuntimeBehaviorScopeError as error:
            raise RuntimeStateError(
                f"cannot capture frozen runtime manifest: {error}"
            ) from error
        captured = {
            "schema": "aegis.frozen_runtime_manifest.v1",
            "scope_policy_sha256": resolved.policy_sha256,
            "resolved_manifest_sha256": resolved.manifest_sha256,
            "runtime_authority_id": resolved.runtime_authority_id,
            "scope_controls": [
                {
                    **_file_control_descriptor(self.project_root / relative_path),
                    "file_identity": _file_identity(
                        self.project_root / relative_path
                    ),
                }
                for relative_path in (
                    SCOPE_POLICY_RELATIVE_PATH,
                    SCOPE_DECISION_RELATIVE_PATH,
                    SCOPE_REVIEW_RELATIVE_PATH,
                    SCOPE_USER_STATEMENT_RELATIVE_PATH,
                )
            ],
            "entries": [
                {
                    "path": str((self.project_root / entry.path).resolve()),
                    "logical_path": entry.path,
                    "size": entry.size,
                    "sha256": entry.sha256,
                    "file_identity": _file_identity(
                        self.project_root / entry.path
                    ),
                }
                for entry in resolved.entries
            ],
            "external_runtime": self._capture_external_runtime_identity(
                git_command=git_command
            ),
        }
        prior = self._frozen_runtime_manifest
        if prior is not None and prior != captured:
            raise FrozenInputMutationError(
                "frozen runtime manifest changed during recovery"
            )
        self._frozen_runtime_manifest = captured

    def _capture_external_runtime_identity(
        self, *, git_command: str | None = None
    ) -> dict[str, object] | None:
        if not isinstance(self.relay_client, TraceRelayClient):
            return None
        try:
            codex_command = default_app_server_command()[0]
            selected_git_command = (
                git_command or shutil.which("git.exe") or shutil.which("git")
            )
            if selected_git_command is None:
                raise RuntimeIdentityError("Git executable is unavailable")
            return capture_production_runtime_identity(
                self.project_root,
                codex_command=codex_command,
                tracerelay_command=self.relay_client.command,
                git_command=selected_git_command,
            )
        except (RuntimeIdentityError, OSError) as error:
            raise RuntimeStateError(
                f"cannot freeze production runtime identity: {error}"
            ) from error

    def _frozen_watch_descriptors(self) -> dict[str, dict[str, object]]:
        descriptors: dict[str, dict[str, object]] = {}

        def add(
            path_value: object,
            size_value: object,
            sha_value: object,
            source: str,
        ) -> None:
            if not isinstance(path_value, (str, Path)):
                return
            path = Path(path_value).resolve()
            descriptors[str(path).casefold()] = {
                "path": str(path),
                "source": source,
                "expected_size": (
                    size_value
                    if isinstance(size_value, int) and not isinstance(size_value, bool)
                    else None
                ),
                "expected_sha256": sha_value if isinstance(sha_value, str) else None,
            }

        runtime = self._frozen_runtime_manifest or {}
        entries = runtime.get("entries", [])
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    add(
                        entry.get("path"),
                        entry.get("size"),
                        entry.get("sha256"),
                        "runtime_scope",
                    )
        scope_controls = runtime.get("scope_controls", [])
        if isinstance(scope_controls, list):
            for control in scope_controls:
                if isinstance(control, dict):
                    add(
                        control.get("path"),
                        control.get("size"),
                        control.get("sha256"),
                        "runtime_scope_control",
                    )
        external_runtime = runtime.get("external_runtime")
        if isinstance(external_runtime, dict):
            external_files = external_runtime.get("files", [])
            if isinstance(external_files, list):
                for external in external_files:
                    if isinstance(external, dict):
                        add(
                            external.get("path"),
                            external.get("size"),
                            external.get("sha256"),
                            str(external.get("source", "external_runtime")),
                        )
        engineering = self._engineering_input_manifest or {}
        snapshot_manifest = engineering.get("snapshot_path")
        snapshot_sha = engineering.get("snapshot_sha256")
        snapshot_size = None
        if isinstance(snapshot_manifest, str) and Path(snapshot_manifest).is_file():
            snapshot_size = Path(snapshot_manifest).stat().st_size
        add(
            self._engineering_input_source_path,
            snapshot_size,
            snapshot_sha,
            "engineering_manifest_source",
        )
        add(
            snapshot_manifest,
            snapshot_size,
            snapshot_sha,
            "engineering_manifest_snapshot",
        )
        documents = engineering.get("documents", [])
        if isinstance(documents, list):
            for document in documents:
                if isinstance(document, dict):
                    add(
                        document.get("source_path"),
                        document.get("source_size"),
                        document.get("source_sha256"),
                        "engineering_document_source",
                    )
                    add(
                        document.get("snapshot_path"),
                        document.get("snapshot_size"),
                        document.get("snapshot_sha256"),
                        "engineering_document_snapshot",
                    )
        context = self._reasoning_context_pack or {}
        for field, source in (
            ("source_path", "reasoning_context_source"),
            ("snapshot_path", "reasoning_context_snapshot"),
            (
                "coordinator_ledger_snapshot_path",
                "reasoning_ledger_coordinator_snapshot",
            ),
        ):
            if field == "coordinator_ledger_snapshot_path":
                add(
                    context.get(field),
                    context.get("coordinator_ledger_snapshot_size"),
                    context.get("coordinator_ledger_snapshot_sha256"),
                    source,
                )
            else:
                add(
                    context.get(field),
                    context.get("size"),
                    context.get("sha256"),
                    source,
                )
        for round_record in self._planning_rounds:
            for path_field, sha_field, source in (
                ("plan_path", "plan_sha256", "test_plan"),
                ("review_report_path", "review_report_sha256", "planning_review"),
            ):
                path_value = round_record.get(path_field)
                size = None
                if isinstance(path_value, str) and Path(path_value).is_file():
                    size = Path(path_value).stat().st_size
                add(path_value, size, round_record.get(sha_field), source)
        for descriptor in self._active_test_input_descriptors:
            add(
                descriptor.get("path"),
                descriptor.get("size"),
                descriptor.get("sha256"),
                str(descriptor.get("source", "test_execution_input")),
            )
        return descriptors

    def _start_frozen_input_watchers(self) -> list[FrozenInputWatcher]:
        descriptors = self._frozen_watch_descriptors()
        roots: list[Path] = [self.project_root]
        if not self.artifact_path.is_relative_to(self.project_root):
            roots.append(self.artifact_path)
        external_runtime = (self._frozen_runtime_manifest or {}).get(
            "external_runtime"
        )
        if isinstance(external_runtime, dict):
            watched_roots = external_runtime.get("watched_roots", [])
            if isinstance(watched_roots, list):
                roots.extend(
                    Path(value).resolve()
                    for value in watched_roots
                    if isinstance(value, str)
                )
        for descriptor in descriptors.values():
            path = Path(str(descriptor["path"]))
            if any(path.is_relative_to(root) for root in roots):
                continue
            roots.append(path.parent)
        unique: dict[str, Path] = {}
        for root in roots:
            if root.is_dir():
                unique.setdefault(str(root.resolve()).casefold(), root.resolve())
        watchers: list[FrozenInputWatcher] = []
        try:
            for root in unique.values():
                watcher = FrozenInputWatcher(root)
                watcher.start()
                watchers.append(watcher)
        except BaseException:
            for watcher in reversed(watchers):
                watcher.stop()
            raise
        return watchers

    @staticmethod
    def _stop_frozen_input_watchers(
        watchers: Sequence[FrozenInputWatcher],
    ) -> tuple[FileSystemEvent, ...]:
        events: list[FileSystemEvent] = []
        for watcher in reversed(watchers):
            events.extend(watcher.stop())
        return tuple(events)

    @staticmethod
    def _current_frozen_input_watch_events(
        watchers: Sequence[FrozenInputWatcher],
    ) -> tuple[FileSystemEvent, ...]:
        events: list[FileSystemEvent] = []
        for watcher in watchers:
            events.extend(watcher.events())
        return tuple(events)

    def _watcher_mutation_error(
        self, events: Sequence[FileSystemEvent]
    ) -> FrozenInputMutationError | None:
        descriptors = self._frozen_watch_descriptors()
        relevant: dict[str, dict[str, object]] = {}
        policy_path = (self.project_root / SCOPE_POLICY_RELATIVE_PATH).resolve()
        external_runtime = (self._frozen_runtime_manifest or {}).get(
            "external_runtime"
        )
        external_roots = (
            [
                Path(value).resolve()
                for value in external_runtime.get("watched_roots", [])
                if isinstance(value, str)
            ]
            if isinstance(external_runtime, dict)
            and isinstance(external_runtime.get("watched_roots"), list)
            else []
        )
        for event in events:
            path = event.path.resolve()
            folded = str(path).casefold()
            is_relevant = folded in descriptors or folded == str(policy_path).casefold()
            if not is_relevant and any(
                path.is_relative_to(root) for root in external_roots
            ):
                is_relevant = True
            if not is_relevant and path.is_relative_to(self.project_root):
                logical_path = path.relative_to(self.project_root).as_posix()
                try:
                    is_relevant = (
                        self._seal is not None
                        and runtime_behavior_path_is_selected(
                            self.project_root,
                            self._seal.project_id,
                            logical_path,
                        )
                    )
                except (RuntimeBehaviorScopeError, ValueError):
                    is_relevant = folded == str(policy_path).casefold()
            if not is_relevant:
                continue
            change = relevant.setdefault(
                folded,
                {
                    **descriptors.get(
                        folded,
                        {
                            "path": str(path),
                            "source": "runtime_scope",
                            "expected_size": None,
                            "expected_sha256": None,
                        },
                    ),
                    "observed_actions": [],
                },
            )
            actions = change["observed_actions"]
            assert isinstance(actions, list)
            if event.action not in actions:
                actions.append(event.action)
        if not relevant:
            return None
        changes: list[dict[str, object]] = []
        for change in relevant.values():
            changes.append(
                {
                    **change,
                    **_actual_file_descriptor(Path(str(change["path"]))),
                }
            )
        event_payload = {
            "schema": "aegis.frozen_input_mutation_event.v1",
            "observed_at_utc": _utc_now_text(),
            "responsible_node": self._current_node,
            "coordinator_pid": os.getpid(),
            "attribution_status": "UNATTRIBUTED",
            "tracerelay_session_ids": sorted(
                {
                    str(entry["session_id"])
                    for entry in self._evidence_sessions
                    if isinstance(entry.get("session_id"), str)
                }
            ),
            "reason": "a frozen input received a filesystem change event during node execution",
            "changes": changes,
        }
        return FrozenInputMutationError(
            "frozen project inputs changed during A-F; the run is terminated and "
            "requires the user to provide a reason",
            mutation_event=event_payload,
        )

    def _enrich_mutation_error(
        self, error: FrozenInputMutationError
    ) -> FrozenInputMutationError:
        if error.mutation_event is not None:
            return error
        expected: dict[str, dict[str, object]] = {}

        def add_expected(
            path_value: object,
            size_value: object,
            sha_value: object,
            source: str,
            file_identity: object = None,
        ) -> None:
            if (
                not isinstance(path_value, str)
                or not isinstance(size_value, int)
                or isinstance(size_value, bool)
                or not isinstance(sha_value, str)
            ):
                return
            path = Path(path_value).resolve()
            expected[str(path).casefold()] = {
                "path": str(path),
                "source": source,
                "expected_size": size_value,
                "expected_sha256": sha_value,
                "expected_file_identity": file_identity,
            }

        runtime_manifest = self._frozen_runtime_manifest or {}
        runtime_entries = runtime_manifest.get("entries", [])
        if isinstance(runtime_entries, list):
            for entry in runtime_entries:
                if isinstance(entry, dict):
                    add_expected(
                        entry.get("path"),
                        entry.get("size"),
                        entry.get("sha256"),
                        "runtime_scope",
                        entry.get("file_identity"),
                    )
        scope_controls = runtime_manifest.get("scope_controls", [])
        if isinstance(scope_controls, list):
            for control in scope_controls:
                if isinstance(control, dict):
                    add_expected(
                        control.get("path"),
                        control.get("size"),
                        control.get("sha256"),
                        "runtime_scope_control",
                        control.get("file_identity"),
                    )
        external_runtime = runtime_manifest.get("external_runtime")
        if isinstance(external_runtime, dict):
            external_files = external_runtime.get("files", [])
            if isinstance(external_files, list):
                for external in external_files:
                    if isinstance(external, dict):
                        add_expected(
                            external.get("path"),
                            external.get("size"),
                            external.get("sha256"),
                            str(external.get("source", "external_runtime")),
                            external.get("file_identity"),
                        )
        engineering = self._engineering_input_manifest or {}
        source_manifest = self._engineering_input_source_path
        if source_manifest is not None:
            snapshot_path = engineering.get("snapshot_path")
            if isinstance(snapshot_path, str) and Path(snapshot_path).is_file():
                snapshot_bytes = Path(snapshot_path).read_bytes()
                add_expected(
                    str(source_manifest),
                    len(snapshot_bytes),
                    hashlib.sha256(snapshot_bytes).hexdigest(),
                    "engineering_manifest_source",
                )
        documents = engineering.get("documents", [])
        if isinstance(documents, list):
            for document in documents:
                if not isinstance(document, dict):
                    continue
                add_expected(
                    document.get("source_path"),
                    document.get("source_size"),
                    document.get("source_sha256"),
                    "engineering_document_source",
                )
                add_expected(
                    document.get("snapshot_path"),
                    document.get("snapshot_size"),
                    document.get("snapshot_sha256"),
                    "engineering_document_snapshot",
                )
        context = self._reasoning_context_pack or {}
        context_sha = context.get("sha256")
        context_size = context.get("size")
        for field, source in (
            ("source_path", "reasoning_context_source"),
            ("snapshot_path", "reasoning_context_snapshot"),
        ):
            add_expected(context.get(field), context_size, context_sha, source)
        add_expected(
            context.get("coordinator_ledger_snapshot_path"),
            context.get("coordinator_ledger_snapshot_size"),
            context.get("coordinator_ledger_snapshot_sha256"),
            "reasoning_ledger_coordinator_snapshot",
        )
        for round_record in self._planning_rounds:
            for path_field, sha_field, source in (
                ("plan_path", "plan_sha256", "approved_test_plan"),
                ("review_report_path", "review_report_sha256", "planning_review"),
            ):
                path_value = round_record.get(path_field)
                sha_value = round_record.get(sha_field)
                if isinstance(path_value, str) and isinstance(sha_value, str):
                    path = Path(path_value)
                    size = path.stat().st_size if path.is_file() else 0
                    add_expected(path_value, size, sha_value, source)

        changes: list[dict[str, object]] = []
        for descriptor in expected.values():
            path = Path(str(descriptor["path"]))
            actual = _actual_file_descriptor(path)
            if (
                actual.get("actual_size") != descriptor["expected_size"]
                or actual.get("actual_sha256") != descriptor["expected_sha256"]
            ):
                changes.append({**descriptor, **actual})

        if self._seal is not None:
            try:
                current = resolve_runtime_behavior_scope(
                    self.project_root, self._seal.project_id
                )
                current_paths = {
                    str((self.project_root / entry.path).resolve()).casefold(): entry
                    for entry in current.entries
                }
                for folded_path, entry in current_paths.items():
                    if folded_path in expected:
                        continue
                    changes.append(
                        {
                            "path": str(
                                (self.project_root / entry.path).resolve()
                            ),
                            "source": "runtime_scope",
                            "expected_size": None,
                            "expected_sha256": None,
                            "expected_file_identity": None,
                            "actual_state": "unexpected",
                            "actual_size": entry.size,
                            "actual_sha256": entry.sha256,
                            "actual_file_identity": _file_identity(
                                self.project_root / entry.path
                            ),
                        }
                    )
            except RuntimeBehaviorScopeError:
                pass
        session_ids = sorted(
            {
                str(entry["session_id"])
                for entry in self._evidence_sessions
                if isinstance(entry.get("session_id"), str)
            }
        )
        event = {
            "schema": "aegis.frozen_input_mutation_event.v1",
            "observed_at_utc": _utc_now_text(),
            "responsible_node": self._current_node,
            "coordinator_pid": os.getpid(),
            "attribution_status": "UNATTRIBUTED",
            "tracerelay_session_ids": session_ids,
            "reason": str(error),
            "changes": changes,
        }
        return FrozenInputMutationError(str(error), mutation_event=event)

    def _validate_frozen_project_inputs(self) -> None:
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable before node execution")
        try:
            current = verify_expected_project_seal(self.project_root)
        except BaseException as error:
            raise FrozenInputMutationError(
                "frozen project runtime inputs changed during A-F; "
                "the run is terminated and requires the user to provide a reason"
            ) from error
        if (
            current.expected_seal != self._seal.expected_seal
            or current.sequence != self._seal.sequence
            or current.scope_policy_sha256 != self._seal.scope_policy_sha256
            or current.resolved_manifest_sha256
            != self._seal.resolved_manifest_sha256
        ):
            raise FrozenInputMutationError(
                "frozen project runtime inputs changed during A-F; "
                "the run is terminated and requires the user to provide a reason"
            )
        expected_external = (self._frozen_runtime_manifest or {}).get(
            "external_runtime"
        )
        try:
            current_external = self._capture_external_runtime_identity()
        except RuntimeStateError as error:
            raise FrozenInputMutationError(
                "production runtime dependencies became unverifiable during A-F"
            ) from error
        if current_external != expected_external:
            raise FrozenInputMutationError(
                "production runtime dependencies or effective environment changed "
                "during A-F; the run is terminated and requires the user to provide a reason"
            )
        self._validate_engineering_inputs()
        if self._reasoning_context_pack is not None:
            self._validate_reasoning_context_snapshot()
        if self._planning_stage_status == "completed":
            try:
                self._validate_completed_planning_stage()
            except BaseException as error:
                raise FrozenInputMutationError(
                    "frozen planning inputs changed during A-F; "
                    "the run is terminated and requires the user to provide a reason"
                ) from error

    def _seal_test_evidence_manifest(
        self, attempt: dict[str, object]
    ) -> None:
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable for test evidence")
        attempt_id = str(attempt["attempt_id"])
        snapshot_path = (
            self.artifact_path / "evidence-manifests" / f"{attempt_id}.json"
        ).resolve()
        if attempt.get("status") == "completed":
            self._validate_test_evidence_snapshot(attempt)
            return
        receipt = self._execution_turn_for_job(str(attempt["job_id"]))
        if receipt is None or receipt.get("status") != "completed":
            raise RuntimeStateError(
                "C cannot bind test evidence before its App Server turn completes"
            )
        session_ids = receipt.get("evidence_session_ids")
        if not isinstance(session_ids, list):
            raise RuntimeStateError("C has invalid TraceRelay evidence session IDs")
        current_path = (self.artifact_path / "test_evidence_manifest.json").resolve()
        request_path = (self.artifact_path / TEST_EXECUTION_REQUEST_NAME).resolve()
        request_snapshot_path = (
            self.artifact_path
            / "evidence-manifests"
            / f"{attempt_id}.request.json"
        ).resolve()
        approved_path, _handoff_path = self._expected_planning_handoff_paths()
        approved_sha256 = hashlib.sha256(
            _read_required_file(approved_path, "approved test plan")
        ).hexdigest()
        try:
            request = validate_test_execution_request(
                request_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                project_id_hex=self._seal.project_id.hex(),
                workflow_run_id=self.run_id,
                attempt_id=attempt_id,
                approved_test_plan_sha256=approved_sha256,
                approved_test_plan_path=approved_path,
            )
        except TestExecutionRequestError as error:
            raise RuntimeStateError(
                f"C produced an invalid test execution request: {error}"
            ) from error
        request_bytes = request.path.read_bytes()
        if request_snapshot_path.exists():
            if request_snapshot_path.read_bytes() != request_bytes:
                raise FrozenInputMutationError(
                    "immutable test execution request snapshot changed"
                )
        else:
            _atomic_write_bytes(request_snapshot_path, request_bytes)
        attempt.update(
            test_execution_request_path=str(request_snapshot_path),
            test_execution_request_sha256=request.sha256,
            test_execution_policy_sha256=request.execution_policy_sha256,
            test_runner_status="executing",
        )
        self._write_state("running")
        self._execute_test_request(
            request.payload,
            request_sha256=request.sha256,
            execution_policy_sha256=request.execution_policy_sha256,
            session_ids=[str(item) for item in session_ids],
            manifest_path=current_path,
        )
        attempt["test_runner_status"] = "completed"
        try:
            validated = validate_test_evidence_manifest(
                current_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                project_id_hex=self._seal.project_id.hex(),
                workflow_run_id=self.run_id,
                attempt_id=attempt_id,
                allowed_tracerelay_session_ids=set(session_ids),
            )
        except TestEvidenceManifestError as error:
            raise RuntimeStateError(
                f"C produced invalid test evidence: {error}"
            ) from error
        manifest_bytes = current_path.read_bytes()
        if snapshot_path.exists():
            if snapshot_path.read_bytes() != manifest_bytes:
                raise FrozenInputMutationError(
                    "immutable test evidence manifest snapshot changed"
                )
        else:
            _atomic_write_bytes(snapshot_path, manifest_bytes)
        attempt.update(
            test_evidence_manifest_path=str(snapshot_path),
            test_evidence_manifest_sha256=validated.sha256,
            approved_test_plan_sha256=validated.approved_test_plan_sha256,
            test_execution_policy_sha256=validated.execution_policy_sha256,
            test_ids=list(validated.test_ids),
        )
        self._validate_test_evidence_snapshot(attempt)
        current_path.unlink()
        request_path.unlink()

    def _execute_test_request(
        self,
        request: Mapping[str, object],
        *,
        request_sha256: str,
        execution_policy_sha256: str,
        session_ids: list[str],
        manifest_path: Path,
    ) -> None:
        attempt_id = str(request["attempt_id"])
        evidence_root = (self.artifact_path / "evidence" / attempt_id).resolve()
        if manifest_path.exists():
            raise RuntimeStateError(
                "C must not create the Coordinator-owned test evidence manifest"
            )
        if evidence_root.exists():
            if not evidence_root.is_dir() or any(evidence_root.iterdir()):
                raise RuntimeStateError(
                    "Coordinator test evidence root contains untrusted pre-existing data"
                )
        else:
            evidence_root.mkdir(parents=True, exist_ok=False)
        approved_path, _handoff_path = self._expected_planning_handoff_paths()
        plan_descriptor = _file_control_descriptor(approved_path)
        tests = request["tests"]
        assert isinstance(tests, list)
        records: list[dict[str, object]] = []
        self._active_test_input_descriptors = []
        for test_value in tests:
            assert isinstance(test_value, dict)
            self._active_test_input_descriptors.append(
                {
                    "path": str(test_value["cwd"]),
                    "size": None,
                    "sha256": None,
                    "source": "test_execution_cwd",
                }
            )
            execution_descriptors = [
                ("test_execution_executable", test_value["executable"]),
                *(
                    ("test_execution_input", item)
                    for item in test_value["test_inputs"]
                ),
            ]
            for source, descriptor in execution_descriptors:
                assert isinstance(descriptor, dict)
                self._active_test_input_descriptors.append(
                    {**descriptor, "source": source}
                )
        watchers = self._start_frozen_input_watchers()
        primary: BaseException | None = None
        watch_events: tuple[FileSystemEvent, ...] = ()
        try:
            for index, test_value in enumerate(tests, start=1):
                assert isinstance(test_value, dict)
                test_root = evidence_root / f"test-{index:04d}"
                test_root.mkdir(parents=False, exist_ok=False)
                stdout_path = test_root / "stdout.bin"
                stderr_path = test_root / "stderr.bin"
                receipt_path = test_root / "execution_receipt.json"
                command = [str(part) for part in test_value["command"]]
                wrapper_command = [
                    str(Path(sys._base_executable).resolve()),
                    "-I",
                    "-S",
                    str(Path(__file__).with_name("windows_job_runner.py").resolve()),
                    "--active-process-limit",
                    "64",
                    "--job-memory-limit-bytes",
                    str(4 * 1024**3),
                    "--process-time-limit-100ns",
                    str(int(test_value["timeout_seconds"]) * 10_000_000),
                    "--",
                    *command,
                ]
                approved_environment = test_value["environment"]
                assert isinstance(approved_environment, dict)
                environment = {
                    str(key): str(value)
                    for key, value in approved_environment.items()
                }
                started = _utc_now_text()
                try:
                    with hold_test_execution_inputs(
                        test_value,
                        project_root=self.project_root,
                        artifact_root=self.artifact_path,
                    ):
                        process = subprocess.Popen(
                            wrapper_command,
                            cwd=str(test_value["cwd"]),
                            env=environment,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        timed_out = False
                        deadline = monotonic() + int(test_value["timeout_seconds"])
                        while True:
                            remaining = deadline - monotonic()
                            if remaining <= 0:
                                timed_out = True
                                process.kill()
                                stdout, stderr = process.communicate(timeout=30)
                                break
                            try:
                                stdout, stderr = process.communicate(
                                    timeout=min(remaining, 0.1)
                                )
                                break
                            except subprocess.TimeoutExpired:
                                mutation = self._watcher_mutation_error(
                                    self._current_frozen_input_watch_events(watchers)
                                )
                                if mutation is None:
                                    continue
                                process.kill()
                                process.communicate(timeout=30)
                                raise mutation
                except (OSError, TestExecutionRequestError) as error:
                    raise RuntimeStateError(
                        f"Coordinator could not start test {test_value['test_id']}: {error}"
                    ) from error
                finished = _utc_now_text()
                exit_code = 124 if timed_out else int(process.returncode)
                _write_bytes_exclusive(stdout_path, stdout)
                _write_bytes_exclusive(stderr_path, stderr)
                stdout_descriptor = _file_descriptor_allow_empty(stdout_path)
                stderr_descriptor = _file_descriptor_allow_empty(stderr_path)
                environment_fingerprint = {
                    "platform": platform.platform(),
                    "python": sys.version.splitlines()[0],
                    "base_executable": str(Path(sys._base_executable).resolve()),
                    "approved_environment_sha256": hashlib.sha256(
                        json.dumps(
                            approved_environment,
                            ensure_ascii=False,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                    "effective_environment_sha256": hashlib.sha256(
                        json.dumps(
                            environment,
                            ensure_ascii=False,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                    "environment_variable_names_sha256": hashlib.sha256(
                        json.dumps(
                            sorted(environment),
                            ensure_ascii=False,
                            allow_nan=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                }
                receipt_payload: dict[str, object] = {
                    "schema": "aegis.test_execution_receipt.v3",
                    "trusted_runner": "aegis.coordinator.windows_job.v1",
                    "request_sha256": request_sha256,
                    "execution_policy_sha256": execution_policy_sha256,
                    "test_id": test_value["test_id"],
                    "command": command,
                    "executable": dict(test_value["executable"]),
                    "cwd": str(Path(str(test_value["cwd"])).resolve()),
                    "environment": environment_fingerprint,
                    "started_at_utc": started,
                    "finished_at_utc": finished,
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "runner_pid": process.pid,
                    "coordinator_pid": os.getpid(),
                    "test_inputs": [dict(item) for item in test_value["test_inputs"]],
                    "stdout": stdout_descriptor,
                    "stderr": stderr_descriptor,
                }
                _write_bytes_exclusive(
                    receipt_path, _canonical_json_bytes(receipt_payload)
                )
                receipt_descriptor = _file_control_descriptor(receipt_path)
                records.append(
                    {
                        "test_id": test_value["test_id"],
                        "requirement_ids": list(test_value["requirement_ids"]),
                        "command": command,
                        "executable": receipt_payload["executable"],
                        "execution_policy_sha256": receipt_payload[
                            "execution_policy_sha256"
                        ],
                        "cwd": receipt_payload["cwd"],
                        "environment": environment_fingerprint,
                        "started_at_utc": started,
                        "finished_at_utc": finished,
                        "exit_code": exit_code,
                        "test_inputs": receipt_payload["test_inputs"],
                        "stdout": stdout_descriptor,
                        "stderr": stderr_descriptor,
                        "raw_results": [receipt_descriptor],
                        "tracerelay_session_ids": list(session_ids),
                        "execution_receipt": receipt_descriptor,
                    }
                )
        except BaseException as error:
            primary = error
        finally:
            try:
                watch_events = self._stop_frozen_input_watchers(watchers)
            except BaseException as watcher_error:
                if primary is None:
                    primary = watcher_error
                else:
                    primary.add_note(
                        f"frozen-input watcher cleanup also failed: {watcher_error}"
                    )
        mutation = self._watcher_mutation_error(watch_events)
        self._active_test_input_descriptors = []
        if mutation is not None:
            if primary is not None:
                mutation.add_note(f"test execution also failed: {primary}")
            raise mutation
        if primary is not None:
            raise primary
        manifest = {
            "schema": "aegis.test_evidence_manifest.v2",
            "project_id_hex": request["project_id_hex"],
            "workflow_run_id": request["workflow_run_id"],
            "attempt_id": attempt_id,
            "approved_test_plan": plan_descriptor,
            "created_at_utc": _utc_now_text(),
            "records": records,
        }
        _write_bytes_exclusive(manifest_path, _canonical_json_bytes(manifest))

    def _validate_test_evidence_snapshot(
        self, attempt: Mapping[str, object]
    ) -> None:
        if self._seal is None:
            raise RuntimeStateError("project seal is unavailable for test evidence")
        manifest_path = attempt.get("test_evidence_manifest_path")
        attempt_id = attempt.get("attempt_id")
        if not isinstance(manifest_path, str) or not isinstance(attempt_id, str):
            raise RuntimeStateError("completed C attempt has no evidence manifest")
        expected_manifest_path = (
            self.artifact_path / "evidence-manifests" / f"{attempt_id}.json"
        ).resolve()
        if Path(manifest_path).resolve() != expected_manifest_path:
            raise FrozenInputMutationError(
                "completed C attempt changed its evidence manifest path"
            )
        receipt = self._execution_turn_for_job(str(attempt.get("job_id")))
        session_ids = receipt.get("evidence_session_ids") if receipt else None
        if not isinstance(session_ids, list):
            raise RuntimeStateError("completed C attempt has no TraceRelay sessions")
        try:
            validated = validate_test_evidence_manifest(
                manifest_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                project_id_hex=self._seal.project_id.hex(),
                workflow_run_id=self.run_id,
                attempt_id=attempt_id,
                allowed_tracerelay_session_ids=set(session_ids),
                expected_manifest_path=expected_manifest_path,
            )
        except TestEvidenceManifestError as error:
            raise FrozenInputMutationError(
                f"sealed test evidence changed after C: {error}"
            ) from error
        if (
            validated.sha256 != attempt.get("test_evidence_manifest_sha256")
            or validated.approved_test_plan_sha256
            != attempt.get("approved_test_plan_sha256")
            or validated.execution_policy_sha256
            != attempt.get("test_execution_policy_sha256")
            or list(validated.test_ids) != attempt.get("test_ids")
        ):
            raise FrozenInputMutationError(
                "sealed test evidence metadata changed after C"
            )
        request_path = attempt.get("test_execution_request_path")
        request_sha256 = attempt.get("test_execution_request_sha256")
        if not isinstance(request_path, str):
            raise RuntimeStateError("completed C attempt has no test execution request")
        expected_request_path = (
            self.artifact_path
            / "evidence-manifests"
            / f"{attempt_id}.request.json"
        ).resolve()
        if Path(request_path).resolve() != expected_request_path:
            raise FrozenInputMutationError(
                "completed C attempt changed its test execution request path"
            )
        try:
            current_request_sha256 = hashlib.sha256(
                expected_request_path.read_bytes()
            ).hexdigest()
        except OSError as error:
            raise FrozenInputMutationError(
                "test execution request is missing after C"
            ) from error
        if current_request_sha256 != request_sha256:
            raise FrozenInputMutationError(
                "test execution request changed after C"
            )
        if attempt.get("test_runner_status") != "completed":
            raise RuntimeStateError("completed C attempt has no completed trusted runner")

    def _validate_completed_test_evidence_manifests(self) -> None:
        for attempt in self._execution_attempts:
            if attempt.get("node") == "C" and attempt.get("status") == "completed":
                self._validate_test_evidence_snapshot(attempt)

    def _seal_final_review_verdict(
        self,
        attempt: dict[str, object],
        state: Mapping[str, object],
    ) -> None:
        status = state.get("status")
        if not isinstance(status, bool):
            raise RuntimeStateError("F returned a non-boolean status")
        verdict_path = (self.artifact_path / "FINAL_REVIEW_VERDICT.json").resolve()
        try:
            validated = validate_final_review_verdict(
                verdict_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                workflow_run_id=self.run_id,
                expected_status=status,
            )
        except FinalReviewVerdictError as error:
            raise RuntimeStateError(f"F produced an invalid verdict: {error}") from error
        attempt.update(
            final_review_verdict_path=str(verdict_path),
            final_review_verdict_sha256=validated.sha256,
            final_review_verdict=validated.verdict,
            final_review_evidence_ids=list(validated.evidence_ids),
        )
        self._validate_final_review_verdict(attempt, expected_status=status)

    def _validate_final_review_verdict(
        self,
        attempt: Mapping[str, object],
        *,
        expected_status: bool,
    ) -> None:
        expected_path = (self.artifact_path / "FINAL_REVIEW_VERDICT.json").resolve()
        raw_path = attempt.get("final_review_verdict_path")
        if not isinstance(raw_path, str) or Path(raw_path).resolve() != expected_path:
            raise FrozenInputMutationError("F verdict path changed after final review")
        try:
            validated = validate_final_review_verdict(
                expected_path,
                project_root=self.project_root,
                artifact_root=self.artifact_path,
                workflow_run_id=self.run_id,
                expected_status=expected_status,
            )
        except FinalReviewVerdictError as error:
            raise FrozenInputMutationError(
                f"F verdict changed after final review: {error}"
            ) from error
        if (
            validated.sha256 != attempt.get("final_review_verdict_sha256")
            or validated.verdict != attempt.get("final_review_verdict")
            or list(validated.evidence_ids)
            != attempt.get("final_review_evidence_ids")
        ):
            raise FrozenInputMutationError("F verdict metadata changed after final review")

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
        registry = self._require_agent_registry()
        handle = None
        existing = self._execution_agents.get(role_key)
        if existing is None:
            registered = registry.active(role_key)
            runtime_profile = self._role_runtime_profiles.get(role_key)
            if (
                registered is not None
                and (
                    registered.get("developer_instructions_sha256")
                    != instructions_sha256
                    or registered.get("skill_bindings")
                    != self._role_skill_bindings.get(role_key, [])
                    or (
                        runtime_profile is not None
                        and (
                            registered.get("model") != runtime_profile["model"]
                            or registered.get("reasoning_effort")
                            != runtime_profile["reasoning_effort"]
                        )
                    )
                )
            ):
                registry.retire(
                    role_key,
                    reason="role contract changed",
                )
                registered = None
            if registered is not None:
                existing = {
                    "status": "ready",
                    "developer_instructions_sha256": instructions_sha256,
                    "codex_thread_id": registered["thread_id"],
                    "model": registered["model"],
                    "reasoning_effort": registered["reasoning_effort"],
                    "registry_agent_id": registered["agent_id"],
                }
                self._execution_agents[role_key] = existing
            else:
                allocation = registry.begin_allocation(
                    role_key,
                    developer_instructions_sha256=instructions_sha256,
                    skill_bindings=self._role_skill_bindings.get(role_key, []),
                )
                existing = {
                    "status": "allocating",
                    "developer_instructions_sha256": instructions_sha256,
                    "codex_thread_id": None,
                    "model": None,
                    "reasoning_effort": None,
                    "registry_agent_id": allocation["agent_id"],
                }
                self._execution_agents[role_key] = existing
                self._write_state("running")
                handle = client.start_thread(
                    ephemeral=False,
                    model=self._expected_role_model(role_key),
                    sandbox="danger-full-access",
                    approval_policy="never",
                    developer_instructions=developer_instructions,
                )
                self._validate_role_handle(role_key, handle)
                activated = registry.activate(
                    role_key,
                    agent_id=str(allocation["agent_id"]),
                    thread_id=handle.thread_id,
                    model=handle.model,
                    reasoning_effort=handle.reasoning_effort,
                )
                existing.update(
                    status="ready",
                    codex_thread_id=activated["thread_id"],
                    model=activated["model"],
                    reasoning_effort=activated["reasoning_effort"],
                )
        if existing.get("status") == "ready":
            thread_id = existing.get("codex_thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeStateError("saved execution agent has no Codex thread ID")
            if handle is None:
                handle = client.resume_thread(
                    thread_id,
                    sandbox="danger-full-access",
                    approval_policy="never",
                )
                self._validate_role_handle(role_key, handle)
                existing.update(
                    model=handle.model,
                    reasoning_effort=handle.reasoning_effort,
                )
        else:
            raise RuntimeStateError(
                "execution thread allocation outcome is unknown; refusing replacement"
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

    def _expected_role_model(self, role_key: str) -> str | None:
        profile = self._role_runtime_profiles.get(role_key)
        return profile.get("model") if profile is not None else None

    def _validate_role_handle(self, role_key: str, handle: object) -> None:
        profile = self._role_runtime_profiles.get(role_key)
        if profile is None:
            return
        actual_model = getattr(handle, "model", None)
        actual_effort = getattr(handle, "reasoning_effort", None)
        if actual_model != profile["model"]:
            raise RuntimeStateError(
                f"{role_key} App Server model does not match its runtime profile"
            )
        if actual_effort != profile["reasoning_effort"]:
            raise RuntimeStateError(
                f"{role_key} App Server reasoning effort does not match its runtime profile"
            )

    def _planning_runtime_profile(self) -> Mapping[str, str] | None:
        profiles = [
            self._role_runtime_profiles.get(role)
            for role in ("TEST_PLAN_AUTHOR", "TEST_PLAN_REVIEWER")
        ]
        if profiles == [None, None]:
            return None
        if profiles[0] is None or profiles[1] is None or profiles[0] != profiles[1]:
            raise RuntimeStateError(
                "planning roles sharing one App Server require one runtime profile"
            )
        return profiles[0]

    def _require_agent_registry(self) -> DynamicAgentRegistry:
        if self._agent_registry is None:
            raise RuntimeStateError("dynamic agent registry is unavailable before preflight")
        return self._agent_registry

    def _compose_instruction_receipt_protocol(
        self, role_key: str, developer_instructions: str
    ) -> str:
        if self._seal is None:
            raise RuntimeStateError(
                "project seal is unavailable for instruction receipt binding"
            )
        base_sha256 = hashlib.sha256(
            developer_instructions.encode("utf-8")
        ).hexdigest()
        bindings = self._role_skill_bindings.get(role_key, [])
        bindings_sha256 = hashlib.sha256(
            json.dumps(
                bindings,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        challenge = hashlib.sha256(
            (
                self._seal.project_id.hex()
                + "\0"
                + role_key
                + "\0"
                + base_sha256
                + "\0"
                + bindings_sha256
            ).encode("ascii")
        ).hexdigest()
        staging_path = (
            self.runtime_root
            / "project_state"
            / "instruction_receipts"
            / f"{role_key}.json"
        ).resolve()
        payload: dict[str, object] = {
            "schema": "aegis.gpt_instruction_receipt.v1",
            "role_key": role_key,
            "project_id_hex": self._seal.project_id.hex(),
            "base_developer_instructions_sha256": base_sha256,
            "skill_bindings_sha256": bindings_sha256,
            "challenge": challenge,
        }
        encoded = _canonical_json_bytes(payload)
        self._instruction_receipt_specs[role_key] = {
            "path": str(staging_path),
            "payload": payload,
            "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
        }
        protocol = (
            "# Aegis GPT instruction receipt\n\n"
            "Before every role task, atomically write the exact UTF-8 JSON below "
            f"to `{staging_path}`. This receipt is mandatory and must be written "
            "before reading task artifacts or producing the role result. Do not "
            "derive it from the user message.\n\n"
            "```json\n"
            + encoded.decode("utf-8").rstrip("\n")
            + "\n```"
        )
        return developer_instructions.rstrip() + "\n\n" + protocol

    def _expected_instruction_receipt_path(self, role_key: str, job_id: str) -> Path:
        name = hashlib.sha256(
            (role_key + "\0" + job_id).encode("utf-8")
        ).hexdigest()
        return (self.artifact_path / "instruction-receipts" / f"{name}.json").resolve()

    def _validate_instruction_receipt_snapshot(
        self, turn_receipt: Mapping[str, object]
    ) -> None:
        if turn_receipt.get("status") != "completed":
            return
        if self._seal is None:
            raise RuntimeStateError(
                "project seal is unavailable for GPT instruction receipt validation"
            )
        role_key = turn_receipt.get("role")
        job_id = turn_receipt.get("job_id")
        snapshot_value = turn_receipt.get("instruction_receipt_path")
        if (
            not isinstance(role_key, str)
            or not role_key
            or not isinstance(job_id, str)
            or not job_id
            or not isinstance(snapshot_value, str)
        ):
            raise RuntimeStateError(
                "completed turn has invalid GPT instruction receipt metadata"
            )
        expected_path = self._expected_instruction_receipt_path(role_key, job_id)
        if Path(snapshot_value).resolve() != expected_path:
            raise RuntimeStateError("GPT instruction receipt snapshot path changed")
        expected_sha256 = _require_sha256(
            turn_receipt.get("instruction_receipt_sha256"),
            "instruction_receipt_sha256",
        )
        stored_challenge = _require_sha256(
            turn_receipt.get("instruction_receipt_challenge"),
            "instruction_receipt_challenge",
        )
        try:
            encoded, _identity = read_regular_file(
                expected_path,
                allowed_root=self.artifact_path,
                label="GPT instruction receipt snapshot",
                max_bytes=64 * 1024,
            )
        except PathSecurityError as error:
            raise RuntimeStateError(
                f"cannot validate GPT instruction receipt snapshot: {error}"
            ) from error
        if hashlib.sha256(encoded).hexdigest() != expected_sha256:
            raise RuntimeStateError("GPT instruction receipt snapshot SHA-256 mismatch")
        try:
            payload = json.loads(encoded.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeStateError(
                "GPT instruction receipt snapshot is invalid JSON"
            ) from error
        if not isinstance(payload, dict) or _canonical_json_bytes(payload) != encoded:
            raise RuntimeStateError(
                "GPT instruction receipt snapshot is not canonical JSON"
            )
        if set(payload) != {
            "schema",
            "role_key",
            "project_id_hex",
            "base_developer_instructions_sha256",
            "skill_bindings_sha256",
            "challenge",
        }:
            raise RuntimeStateError("GPT instruction receipt fields changed")
        base_sha256 = _require_sha256(
            payload.get("base_developer_instructions_sha256"),
            "base_developer_instructions_sha256",
        )
        bindings_sha256 = _require_sha256(
            payload.get("skill_bindings_sha256"), "skill_bindings_sha256"
        )
        challenge = _require_sha256(payload.get("challenge"), "challenge")
        expected_bindings_sha256 = hashlib.sha256(
            json.dumps(
                self._role_skill_bindings.get(role_key, []),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        expected_challenge = hashlib.sha256(
            (
                self._seal.project_id.hex()
                + "\0"
                + role_key
                + "\0"
                + base_sha256
                + "\0"
                + bindings_sha256
            ).encode("ascii")
        ).hexdigest()
        if (
            payload.get("schema") != "aegis.gpt_instruction_receipt.v1"
            or payload.get("role_key") != role_key
            or payload.get("project_id_hex") != self._seal.project_id.hex()
            or bindings_sha256 != expected_bindings_sha256
            or challenge != expected_challenge
            or challenge != stored_challenge
        ):
            raise RuntimeStateError(
                "GPT instruction receipt does not match the persisted role contract"
            )

    def _validate_persisted_instruction_receipts(self) -> None:
        for turn_receipt in (*self._planning_turns, *self._execution_turns):
            self._validate_instruction_receipt_snapshot(turn_receipt)

    def _prepare_instruction_receipt(self, role_key: str) -> None:
        spec = self._instruction_receipt_specs.get(role_key)
        if spec is None:
            raise RuntimeStateError("role instruction receipt protocol is unavailable")
        path = Path(str(spec["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)

    def _seal_instruction_receipt(
        self,
        role_key: str,
        job_id: str,
        turn_receipt: dict[str, object],
    ) -> None:
        spec = self._instruction_receipt_specs.get(role_key)
        if spec is None:
            raise RuntimeStateError("role instruction receipt protocol is unavailable")
        staging_path = Path(str(spec["path"]))
        try:
            encoded = staging_path.read_bytes()
        except OSError as error:
            raise RuntimeStateError(
                f"{role_key} did not produce the mandatory GPT instruction receipt"
            ) from error
        expected = _canonical_json_bytes(spec["payload"])
        if encoded != expected:
            raise RuntimeStateError(
                f"{role_key} GPT instruction receipt does not match injected instructions"
            )
        snapshot_path = self._expected_instruction_receipt_path(role_key, job_id)
        if snapshot_path.exists():
            if snapshot_path.read_bytes() != encoded:
                raise FrozenInputMutationError(
                    "immutable GPT instruction receipt changed"
                )
        else:
            _atomic_write_bytes(snapshot_path, encoded)
        staging_path.unlink()
        turn_receipt.update(
            instruction_receipt_path=str(snapshot_path),
            instruction_receipt_sha256=hashlib.sha256(encoded).hexdigest(),
            instruction_receipt_challenge=(
                spec["payload"]["challenge"]
                if isinstance(spec["payload"], dict)
                else None
            ),
        )

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
        self._validate_instruction_receipt_snapshot(receipt)
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
            operation_id=(
                str(entry["registration_operation_id"])
                if isinstance(entry.get("registration_operation_id"), str)
                else None
            ),
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

    def _validate_execution_stage_complete(self, state: Mapping[str, Any]) -> None:
        self._validate_frozen_project_inputs()
        self._validate_completed_test_evidence_manifests()
        if any(
            agent.get("status") != "ready" for agent in self._execution_agents.values()
        ):
            raise RuntimeStateError("Aegis run has an unresolved C-F thread allocation")
        if any(
            attempt.get("status") != "completed" for attempt in self._execution_attempts
        ):
            raise RuntimeStateError("Aegis run has an incomplete C-F node attempt")
        turns_by_attempt = {
            turn.get("attempt_id"): turn for turn in self._execution_turns
        }
        for attempt in self._execution_attempts:
            receipt = turns_by_attempt.get(attempt.get("attempt_id"))
            if receipt is None or receipt.get("status") != "completed":
                raise RuntimeStateError(
                    "Aegis run has an incomplete C-F App Server turn"
                )
        terminal_node = state.get("current_node")
        if state.get("status") is True:
            expected_terminal_node = "F"
        elif state.get("status") is False and terminal_node in {"E", "F"}:
            expected_terminal_node = str(terminal_node)
        else:
            raise RuntimeStateError("Aegis run has no valid terminal graph state")
        if (
            terminal_node != expected_terminal_node
            or self._last_completed_node != expected_terminal_node
        ):
            if expected_terminal_node == "F":
                raise RuntimeStateError(
                    "Aegis run has not completed the terminal F node"
                )
            raise RuntimeStateError(
                f"Aegis run has not completed terminal node {expected_terminal_node}"
            )
        final_attempt = (
            self._execution_attempts[-1] if self._execution_attempts else None
        )
        if (
            final_attempt is None
            or final_attempt.get("node") != expected_terminal_node
            or final_attempt.get("status") != "completed"
            or final_attempt.get("output_sha256") != _state_sha256(state)
        ):
            raise RuntimeStateError(
                "Aegis terminal state does not match the completed terminal attempt"
            )
        if expected_terminal_node == "F":
            self._validate_final_review_verdict(
                final_attempt,
                expected_status=state.get("status") is True,
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
        command = configured_app_server_command(
            default_app_server_command(), self._planning_runtime_profile()
        )
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
            operation_id = self._begin_registration_intent(node="planning")
            try:
                process = self.relay_client.open_managed_process(
                    process_command,
                    upstream_port=self.upstream_port,
                    registration_operation_id=operation_id,
                    **popen_options,
                )
            except BaseException as error:
                try:
                    self._record_registered_process_start_failure(node="planning")
                except BaseException as persistence_error:
                    error.add_note(
                        "registered TraceRelay session persistence also failed: "
                        f"{persistence_error}"
                    )
                raise
            self._planning_process = process
            self._persist_registration_result(
                process.registration,
                None,
                node="planning",
            )
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
        registry = self._require_agent_registry()
        handle = None
        developer_instructions = self._compose_instruction_receipt_protocol(
            role_key, developer_instructions
        )
        instructions_sha256 = hashlib.sha256(
            developer_instructions.encode("utf-8")
        ).hexdigest()
        existing = self._planning_agents.get(role_key)
        if role_key in self._planning_ready_roles:
            if existing is None or not isinstance(existing.get("codex_thread_id"), str):
                raise RuntimeStateError("planning agent state is incomplete")
            return str(existing["codex_thread_id"])
        if existing is None:
            registered = registry.active(role_key)
            runtime_profile = self._role_runtime_profiles.get(role_key)
            if (
                registered is not None
                and (
                    registered.get("developer_instructions_sha256")
                    != instructions_sha256
                    or registered.get("skill_bindings")
                    != self._role_skill_bindings.get(role_key, [])
                    or (
                        runtime_profile is not None
                        and (
                            registered.get("model") != runtime_profile["model"]
                            or registered.get("reasoning_effort")
                            != runtime_profile["reasoning_effort"]
                        )
                    )
                )
            ):
                registry.retire(role_key, reason="role contract changed")
                registered = None
            if registered is not None:
                existing = {
                    "codex_thread_id": registered["thread_id"],
                    "model": registered["model"],
                    "reasoning_effort": registered["reasoning_effort"],
                    "developer_instructions_sha256": instructions_sha256,
                    "registry_agent_id": registered["agent_id"],
                    "status": "ready",
                }
                self._planning_agents[role_key] = existing
            else:
                allocation = registry.begin_allocation(
                    role_key,
                    developer_instructions_sha256=instructions_sha256,
                    skill_bindings=self._role_skill_bindings.get(role_key, []),
                )
                existing = {
                    "codex_thread_id": None,
                    "model": None,
                    "reasoning_effort": None,
                    "developer_instructions_sha256": instructions_sha256,
                    "registry_agent_id": allocation["agent_id"],
                    "status": "allocating",
                }
                self._planning_agents[role_key] = existing
                self._write_state("running")
                handle = self._planning_app_server.start_thread(
                    ephemeral=False,
                    model=self._expected_role_model(role_key),
                    sandbox="danger-full-access",
                    approval_policy="never",
                    developer_instructions=developer_instructions,
                )
                self._validate_role_handle(role_key, handle)
                activated = registry.activate(
                    role_key,
                    agent_id=str(allocation["agent_id"]),
                    thread_id=handle.thread_id,
                    model=handle.model,
                    reasoning_effort=handle.reasoning_effort,
                )
                existing.update(
                    codex_thread_id=activated["thread_id"],
                    model=activated["model"],
                    reasoning_effort=activated["reasoning_effort"],
                    status="ready",
                )
        if existing.get("status", "ready") != "ready":
            raise RuntimeStateError(
                "planning thread allocation outcome is unknown; refusing replacement"
            )
        if handle is None:
            thread_id = existing.get("codex_thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeStateError("saved planning agent has no Codex thread ID")
            handle = self._planning_app_server.resume_thread(
                thread_id,
                sandbox="danger-full-access",
                approval_policy="never",
            )
            self._validate_role_handle(role_key, handle)
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
        self._validate_instruction_receipt_snapshot(receipt)
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

    def _begin_registration_intent(
        self,
        *,
        node: str,
        receipt: Mapping[str, object] | None = None,
    ) -> str:
        if self._registration_intent is not None:
            raise RuntimeStateError("a TraceRelay registration intent is already active")
        if node == "planning":
            if receipt is not None:
                raise RuntimeStateError("planning registration cannot bind an execution turn")
            attempt_id: str | None = None
            job_id = f"{self.run_id}:planning-app-server"
        else:
            if node not in EXECUTION_NODE_ROLES or receipt is None:
                raise RuntimeStateError("execution registration intent has no turn binding")
            attempt_id = _required_string(receipt.get("attempt_id"), "attempt_id")
            job_id = _required_string(receipt.get("job_id"), "job_id")
            receipt_status = receipt.get("status")
            if receipt.get("node") != node or receipt_status not in {
                "preparing",
                "inProgress",
            }:
                raise RuntimeStateError(
                    "execution registration intent does not match a recoverable turn"
                )
            if (
                receipt_status == "preparing"
                and receipt.get("evidence_session_ids") != []
            ):
                raise RuntimeStateError(
                    "execution registration intent cannot replace existing evidence"
                )
        operation_id = uuid4().hex
        self._registration_intent = {
            "operation_id": operation_id,
            "run_id": self.run_id,
            "node": node,
            "attempt_id": attempt_id,
            "job_id": job_id,
            "upstream_port": self.upstream_port,
            "created_at_utc": _utc_now_text(),
        }
        self._write_state("running")
        return operation_id

    def _persist_registration_result(
        self,
        registration: TraceRelayRegistration,
        verification: Mapping[str, object] | None,
        *,
        node: str,
        receipt: dict[str, object] | None = None,
        application_verification_status: str | None = None,
        process_pid: int | None = None,
        process_creation_time_100ns: int | None = None,
    ) -> None:
        intent = self._registration_intent
        if intent is None:
            raise RuntimeStateError("TraceRelay registration result has no durable intent")
        operation_id = _required_string(intent.get("operation_id"), "operation_id")
        if (
            intent.get("node") != node
            or registration.operation_id != operation_id
            or registration.upstream_port != self.upstream_port
        ):
            raise RuntimeStateError("TraceRelay registration result changed durable identity")
        if node in EXECUTION_NODE_ROLES:
            if receipt is None:
                raise RuntimeStateError("execution registration result has no turn receipt")
            if (
                receipt.get("attempt_id") != intent.get("attempt_id")
                or receipt.get("job_id") != intent.get("job_id")
                or receipt.get("node") != node
            ):
                raise RuntimeStateError(
                    "execution registration result changed its turn binding"
                )
            session_ids = receipt.get("evidence_session_ids")
            if not isinstance(session_ids, list):
                raise RuntimeStateError(
                    "execution turn has invalid evidence session IDs"
                )
            if registration.session_id not in session_ids:
                session_ids.append(registration.session_id)
        elif receipt is not None:
            raise RuntimeStateError("planning registration cannot bind an execution receipt")
        self._record_evidence(
            registration,
            verification,
            node=node,
            application_verification_status=application_verification_status,
            process_pid=process_pid,
            process_creation_time_100ns=process_creation_time_100ns,
        )
        self._registration_intent = None
        self._write_state("running")

    def _reconcile_registration_intent(self) -> None:
        intent = self._registration_intent
        if intent is None:
            return
        operation_id = _required_string(intent.get("operation_id"), "operation_id")
        registration = self.relay_client.resolve_registration_operation(operation_id)
        if registration is None:
            raise RuntimeStateError(
                "TraceRelay registration outcome is unresolved; refusing a new session"
            )
        if (
            registration.operation_id != operation_id
            or registration.upstream_port != self.upstream_port
        ):
            raise RuntimeStateError("resolved TraceRelay registration changed identity")
        verification = self.relay_client.recover_uncheckpointed_registration(
            registration
        )
        node = _required_string(intent.get("node"), "node")
        receipt: dict[str, object] | None = None
        if node in EXECUTION_NODE_ROLES:
            receipt = next(
                (
                    candidate
                    for candidate in self._execution_turns
                    if candidate.get("attempt_id") == intent.get("attempt_id")
                    and candidate.get("job_id") == intent.get("job_id")
                    and candidate.get("node") == node
                ),
                None,
            )
            if receipt is None:
                raise RuntimeStateError(
                    "registration intent has no matching execution receipt"
                )
        self._persist_registration_result(
            registration,
            verification,
            node=node,
            receipt=receipt,
            application_verification_status="INVALID",
        )
        raise RuntimeStateError(
            "uncheckpointed TraceRelay registration invalidates this run"
        )

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
        registration_operation_id = registration.operation_id
        if registration_operation_id is None and prior is not None:
            saved_operation_id = prior.get("registration_operation_id")
            registration_operation_id = (
                saved_operation_id if isinstance(saved_operation_id, str) else None
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
            "registration_operation_id": registration_operation_id,
        }
        if resolved_node in EXECUTION_NODE_ROLES:
            _validate_execution_evidence_record(entry)
        for index, existing in enumerate(self._evidence_sessions):
            if existing.get("session_id") == registration.session_id:
                self._evidence_sessions[index] = entry
                return
        self._evidence_sessions.append(entry)

    def _record_registered_process_start_failure(
        self,
        *,
        node: str,
        receipt: dict[str, object] | None = None,
    ) -> None:
        registration = getattr(self.relay_client, "last_registration", None)
        if not isinstance(registration, TraceRelayRegistration):
            return
        verification = getattr(self.relay_client, "last_verification", None)
        self._persist_registration_result(
            registration,
            verification if isinstance(verification, Mapping) else None,
            node=node,
            receipt=receipt,
            application_verification_status="INVALID",
        )

    def complete(self, state: dict[str, Any]) -> None:
        self.finish_planning_stage()
        self._validate_execution_stage_complete(state)
        self._current_node = None
        self._last_state = dict(state)
        terminal_status = "completed" if state.get("status") is True else "terminated"
        self._write_state(terminal_status)
        self._release_project_lease()

    def fail(self, error: BaseException) -> None:
        try:
            self.finish_planning_stage()
        except BaseException as cleanup_error:
            error.add_note(f"planning stage cleanup also failed: {cleanup_error}")
        self._write_state("failed", error)
        self._release_project_lease()

    def _release_project_lease(self) -> None:
        if not self._project_lease_acquired or self._agent_registry is None:
            return
        self._agent_registry.release_project_lease(self.run_id)
        self._project_lease_acquired = False

    def _write_state(self, status: str, error: BaseException | None = None) -> None:
        if not self._state_writable or self._reservation_token is None:
            raise RuntimeStateError("run state has not been durably reserved")
        payload = self._build_state_payload(status, error)
        encoded = _canonical_json_bytes(payload)
        _update_run_reservation_state(
            self.runtime_root,
            self.artifact_path,
            self.run_id,
            self._reservation_token,
            status=status,
            encoded_state=encoded,
        )
        _atomic_write_bytes(self.run_state_path, encoded)
        if (
            status not in {"completed", "terminated", "failed"}
            and self._project_lease_acquired
            and self._agent_registry is not None
        ):
            self._agent_registry.heartbeat_project_lease(self.run_id)
        if status in {"completed", "terminated", "failed"}:
            self._release_project_lease()

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
            "runtime_root": str(self.runtime_root),
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
            "repeated_semantic_refusal_issue_ids": sorted(
                {
                    str(issue_id)
                    for planning_round in self._planning_rounds
                    for issue_id in planning_round.get(
                        "repeated_unresolved_issue_ids", []
                    )
                }
            ),
            "planning_stage_status": self._planning_stage_status,
            "engineering_input_manifest": (
                dict(self._engineering_input_manifest)
                if self._engineering_input_manifest is not None
                else None
            ),
            "reasoning_context_pack": (
                dict(self._reasoning_context_pack)
                if self._reasoning_context_pack is not None
                else None
            ),
            "frozen_runtime_manifest": (
                dict(self._frozen_runtime_manifest)
                if self._frozen_runtime_manifest is not None
                else None
            ),
            "planning_reuse": (
                dict(self._planning_reuse)
                if self._planning_reuse is not None
                else None
            ),
            "execution_agents": {
                role: dict(value) for role, value in self._execution_agents.items()
            },
            "execution_turns": [dict(item) for item in self._execution_turns],
            "execution_attempts": [dict(item) for item in self._execution_attempts],
            "role_skill_bindings": {
                role: [dict(binding) for binding in bindings]
                for role, bindings in self._role_skill_bindings.items()
            },
            "role_runtime_profiles": {
                role: dict(profile)
                for role, profile in self._role_runtime_profiles.items()
            },
            "remote_witness_required": self.require_remote_witness,
            "remote_witness": (
                dict(self._remote_witness)
                if self._remote_witness is not None
                else None
            ),
            "registration_intent": (
                dict(self._registration_intent)
                if self._registration_intent is not None
                else None
            ),
            "codex_cli_path": self._codex_cli_path,
            "codex_cli_version": self._codex_cli_version,
            "created_at_utc": self._created_at_utc,
            "updated_at_utc": _utc_now_text(),
        }
        payload.update(_workflow_outcome(status, self._last_state))
        if isinstance(error, FrozenInputMutationError):
            payload.update(
                workflow_state="TERMINATED",
                engineering_verdict="INVALIDATED",
                delivery_eligible=False,
                master_review_status="REQUIRES_USER_REASON",
                termination_reason_code="FROZEN_INPUT_MUTATION",
                responsible_node=self._current_node,
            )
            if error.mutation_event is not None:
                payload["mutation_event"] = dict(error.mutation_event)
        if self._seal is not None:
            payload.update(
                project_id_hex=self._seal.project_id.hex(),
                seal_sequence=self._seal.sequence,
                expected_seal=self._seal.expected_seal,
            )
        if error is not None:
            payload["error"] = {"type": type(error).__name__, "message": str(error)}
        return payload


def _workflow_outcome(
    status: str,
    graph_state: Mapping[str, object] | None,
) -> dict[str, object]:
    current_node = graph_state.get("current_node") if graph_state else None
    if status == "completed":
        return {
            "workflow_state": "SUCCEEDED",
            "engineering_verdict": "PASS",
            "delivery_eligible": True,
            "master_review_status": "NOT_REQUIRED",
        }
    if status == "terminated":
        return {
            "workflow_state": "TERMINATED",
            "engineering_verdict": "FAIL" if current_node == "F" else "INCOMPLETE",
            "delivery_eligible": False,
            "master_review_status": "PENDING" if current_node == "F" else "NOT_REQUIRED",
        }
    if status == "failed":
        return {
            "workflow_state": "FAILED",
            "engineering_verdict": "UNDETERMINED",
            "delivery_eligible": False,
            "master_review_status": "NOT_STARTED",
        }
    return {
        "workflow_state": "ACTIVE",
        "engineering_verdict": "PENDING",
        "delivery_eligible": False,
        "master_review_status": "NOT_STARTED",
    }


def active_runtime_coordinator() -> RuntimeCoordinator | None:
    return _ACTIVE_COORDINATOR.get()


def load_run_state(runtime_root: str | Path, run_id: str) -> dict[str, object]:
    if RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
        raise ValueError("run_id contains unsupported path characters")
    resolved_runtime_root = Path(runtime_root).resolve()
    path = resolved_runtime_root / "runs" / run_id / "RUN_STATE.json"
    payload, authoritative_bytes = _load_authoritative_run_state(
        resolved_runtime_root, run_id
    )
    if payload.get("schema") in {
        "aegis.run_state.v1",
        "aegis.run_state.v2",
        "aegis.run_state.v3",
        "aegis.run_state.v4",
        "aegis.run_state.v5",
        "aegis.run_state.v6",
        "aegis.run_state.v7",
        "aegis.run_state.v8",
        "aegis.run_state.v9",
    }:
        raise RuntimeStateError(
            "run state predates the v10 authoritative-state contract; "
            "start a new run"
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
    stored_artifact_path = payload.get("artifact_path")
    if not isinstance(stored_artifact_path, str) or not Path(
        stored_artifact_path
    ).is_absolute():
        raise RuntimeStateError("run state artifact path is invalid")
    expected_artifact_path = Path(stored_artifact_path).resolve()
    _validate_run_reservation(
        resolved_runtime_root,
        expected_artifact_path,
        run_id,
        reservation_token,
        state_payload=payload,
    )
    try:
        projected = path.read_bytes() if path.is_file() else None
        if projected != authoritative_bytes:
            _atomic_write_bytes(path, authoritative_bytes)
    except OSError as error:
        raise RuntimeStateError(
            f"cannot rebuild RUN_STATE.json projection: {path}: {error}"
        ) from error
    return payload


@contextmanager
def open_graph_checkpointer(runtime_root: str | Path) -> Iterator[SqliteSaver]:
    path = Path(runtime_root).resolve() / CHECKPOINT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        yield SqliteSaver(connection)
    finally:
        connection.close()


def _reserve_new_run(
    runtime_root: Path,
    artifact_path: Path,
    run_state_path: Path,
    run_id: str,
    reservation_token: str,
    state_payload: Mapping[str, object],
) -> None:
    database_path = runtime_root / CHECKPOINT_RELATIVE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.parent.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
    transaction_started = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True
        _ensure_reservation_table(connection)
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
        encoded_state = _canonical_json_bytes(state_payload)
        connection.execute(
            f"""
            INSERT INTO {RESERVATION_TABLE}
                (run_id, reservation_token, artifact_path, created_at_utc,
                 state_sha256, state_status, state_updated_at_utc, state_blob)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                reservation_token,
                str(artifact_path),
                str(state_payload["created_at_utc"]),
                hashlib.sha256(encoded_state).hexdigest(),
                str(state_payload["status"]),
                str(state_payload["updated_at_utc"]),
                encoded_state,
            ),
        )
        connection.execute("COMMIT")
        transaction_started = False
        _atomic_write_bytes(run_state_path, encoded_state)
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
    runtime_root: Path,
    artifact_path: Path,
    run_id: str,
    reservation_token: str,
    *,
    state_payload: Mapping[str, object] | None = None,
) -> None:
    database_path = runtime_root / CHECKPOINT_RELATIVE_PATH
    if not database_path.is_file():
        raise RuntimeStateError("run reservation database is missing")
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro", uri=True, timeout=30
        )
        try:
            columns = {
                str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({RESERVATION_TABLE})"
                ).fetchall()
            }
            required_columns = {"state_sha256", "state_status", "state_blob"}
            if not required_columns.issubset(columns):
                raise RuntimeStateError(
                    "run reservation predates state-digest binding"
                )
            row = connection.execute(
                f"""
                SELECT reservation_token, artifact_path, state_sha256, state_status,
                       state_blob
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
    (
        stored_token,
        stored_artifact_path,
        stored_state_sha256,
        stored_state_status,
        stored_state_blob,
    ) = row
    if stored_token != reservation_token:
        raise RuntimeStateError("run reservation does not match RUN_STATE.json")
    if (
        not isinstance(stored_artifact_path, str)
        or Path(stored_artifact_path).resolve() != artifact_path
    ):
        raise RuntimeStateError("run reservation artifact path does not match")
    if isinstance(stored_state_blob, memoryview):
        authoritative_state = stored_state_blob.tobytes()
    elif isinstance(stored_state_blob, (bytes, bytearray)):
        authoritative_state = bytes(stored_state_blob)
    else:
        authoritative_state = b""
    if not authoritative_state:
        raise RuntimeStateError("run reservation has no authoritative state blob")
    if state_payload is None:
        try:
            decoded_state = json.loads(
                authoritative_state.decode("utf-8", errors="strict")
            )
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeStateError("authoritative run state is invalid JSON") from error
        if not isinstance(decoded_state, dict):
            raise RuntimeStateError("authoritative run state is not an object")
        state_payload = decoded_state
        encoded_state = authoritative_state
    else:
        encoded_state = _canonical_json_bytes(state_payload)
        if encoded_state != authoritative_state:
            raise RuntimeStateError("provided run state differs from authoritative state")
    actual_state_sha256 = hashlib.sha256(encoded_state).hexdigest()
    if stored_state_sha256 != actual_state_sha256:
        raise RuntimeStateError("run state does not match its reservation digest")
    if stored_state_status != state_payload.get("status"):
        raise RuntimeStateError("run state status does not match its reservation")


def initialize_runtime_authority(
    runtime_root: str | Path,
    *,
    project_id_hex: str,
    runtime_authority_id: str,
) -> None:
    """One-time migration step executed before publishing the remote witness."""
    _prepare_runtime_authority(
        Path(runtime_root).resolve(),
        project_id_hex=project_id_hex,
        runtime_authority_id=runtime_authority_id,
        allow_initialize=True,
    )


def _prepare_runtime_authority(
    runtime_root: Path,
    *,
    project_id_hex: str,
    runtime_authority_id: str,
    allow_initialize: bool,
) -> None:
    if re.fullmatch(r"[0-9a-f]{32}", project_id_hex) is None:
        raise RuntimeStateError("runtime authority project identity is invalid")
    if re.fullmatch(r"[0-9a-f]{32}", runtime_authority_id) is None:
        raise RuntimeStateError("runtime authority identity is invalid")
    root = runtime_root.resolve()
    anchor_path = root / RUNTIME_AUTHORITY_RELATIVE_PATH
    database_path = root / CHECKPOINT_RELATIVE_PATH
    anchor_exists = anchor_path.is_file()
    database_exists = database_path.is_file()
    if anchor_exists != database_exists:
        raise RuntimeStateError(
            "runtime authority anchor/database pair is incomplete; deletion or partial initialization detected"
        )
    expected_anchor = {
        "schema": "aegis.runtime_authority_anchor.v1",
        "project_id_hex": project_id_hex,
        "runtime_authority_id": runtime_authority_id,
        "runtime_root": str(root),
    }
    if not anchor_exists:
        if not allow_initialize:
            raise RuntimeStateError(
                "runtime authority is not initialized; initialize it before publishing the remote witness"
            )
        anchor_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            require_no_reparse(
                root,
                anchor_path.parent,
                label="runtime authority directory",
            )
        except PathSecurityError as error:
            raise RuntimeStateError(str(error)) from error
        _atomic_write_bytes(anchor_path, _canonical_json_bytes(expected_anchor))
        try:
            connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
            try:
                connection.execute("BEGIN IMMEDIATE")
                _ensure_reservation_table(connection)
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {RUNTIME_AUTHORITY_TABLE} (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        project_id_hex TEXT NOT NULL,
                        runtime_authority_id TEXT NOT NULL UNIQUE
                    )
                    """
                )
                connection.execute(
                    f"INSERT INTO {RUNTIME_AUTHORITY_TABLE}(singleton, project_id_hex, runtime_authority_id) VALUES (1, ?, ?)",
                    (project_id_hex, runtime_authority_id),
                )
                connection.execute("COMMIT")
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise RuntimeStateError(
                f"cannot initialize runtime authority database: {error}"
            ) from error

    try:
        anchor_bytes, _identity = read_regular_file(
            anchor_path,
            allowed_root=root,
            label="runtime authority anchor",
            max_bytes=1024 * 1024,
        )
        anchor = json.loads(anchor_bytes.decode("utf-8", errors="strict"))
    except (PathSecurityError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeStateError(f"runtime authority anchor is invalid: {error}") from error
    if anchor != expected_anchor:
        raise RuntimeStateError("runtime authority anchor identity mismatch")
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro",
            uri=True,
            timeout=30,
        )
        try:
            row = connection.execute(
                f"SELECT project_id_hex, runtime_authority_id FROM {RUNTIME_AUTHORITY_TABLE} WHERE singleton = 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise RuntimeStateError(
            f"runtime authority database is missing or corrupt: {error}"
        ) from error
    if row != (project_id_hex, runtime_authority_id):
        raise RuntimeStateError("runtime authority database identity mismatch")


def _ensure_reservation_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RESERVATION_TABLE} (
            run_id TEXT PRIMARY KEY,
            reservation_token TEXT NOT NULL UNIQUE,
            artifact_path TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            state_sha256 TEXT,
            state_status TEXT,
            state_updated_at_utc TEXT,
            state_blob BLOB
        )
        """
    )
    columns = {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({RESERVATION_TABLE})"
        ).fetchall()
    }
    additions = {
        "state_sha256": "TEXT",
        "state_status": "TEXT",
        "state_updated_at_utc": "TEXT",
        "state_blob": "BLOB",
    }
    for column, declaration in additions.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {RESERVATION_TABLE} ADD COLUMN {column} {declaration}"
            )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ACCOUNTABILITY_TABLE} (
            project_id_hex TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            marker_json TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )


def _update_run_reservation_state(
    runtime_root: Path,
    artifact_path: Path,
    run_id: str,
    reservation_token: str,
    *,
    status: str,
    encoded_state: bytes,
) -> None:
    database_path = runtime_root / CHECKPOINT_RELATIVE_PATH
    connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
    transaction_started = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True
        _ensure_reservation_table(connection)
        row = connection.execute(
            f"""
            SELECT reservation_token, artifact_path
            FROM {RESERVATION_TABLE}
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeStateError("run reservation does not exist")
        if row[0] != reservation_token or Path(str(row[1])).resolve() != artifact_path:
            raise RuntimeStateError("run reservation identity changed")
        connection.execute(
            f"""
            UPDATE {RESERVATION_TABLE}
            SET state_sha256 = ?, state_status = ?, state_updated_at_utc = ?,
                state_blob = ?
            WHERE run_id = ? AND reservation_token = ?
            """,
            (
                hashlib.sha256(encoded_state).hexdigest(),
                status,
                _utc_now_text(),
                encoded_state,
                run_id,
                reservation_token,
            ),
        )
        try:
            state = json.loads(encoded_state.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeStateError("new authoritative run state is invalid JSON") from error
        if not isinstance(state, dict):
            raise RuntimeStateError("new authoritative run state is not an object")
        project_id_hex = state.get("project_id_hex")
        if isinstance(project_id_hex, str) and re.fullmatch(
            r"[0-9a-f]{32}", project_id_hex
        ):
            if state.get("master_review_status") == "REQUIRES_USER_REASON":
                marker = {
                    "schema": "aegis.project_accountability_marker.v1",
                    "project_id_hex": project_id_hex,
                    "run_id": run_id,
                    "termination_reason_code": state.get("termination_reason_code"),
                    "mutation_event": state.get("mutation_event"),
                }
                connection.execute(
                    f"""
                    INSERT INTO {ACCOUNTABILITY_TABLE}(
                        project_id_hex, run_id, marker_json, updated_at_utc
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(project_id_hex) DO UPDATE SET
                        run_id = excluded.run_id,
                        marker_json = excluded.marker_json,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (
                        project_id_hex,
                        run_id,
                        json.dumps(marker, ensure_ascii=False, sort_keys=True),
                        _utc_now_text(),
                    ),
                )
            elif state.get("master_review_status") == "USER_REASON_RECORDED":
                connection.execute(
                    f"DELETE FROM {ACCOUNTABILITY_TABLE} WHERE project_id_hex = ? AND run_id = ?",
                    (project_id_hex, run_id),
                )
        connection.execute("COMMIT")
        transaction_started = False
    except RuntimeStateError:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    except sqlite3.Error as error:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise RuntimeStateError(
            f"cannot update run reservation state digest: {error}"
        ) from error
    finally:
        connection.close()


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


def _load_authoritative_run_state(
    runtime_root: Path, run_id: str
) -> tuple[dict[str, object], bytes]:
    database_path = runtime_root / CHECKPOINT_RELATIVE_PATH
    if not database_path.is_file():
        raise RuntimeStateError("run reservation database is missing")
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro", uri=True, timeout=30
        )
        try:
            row = connection.execute(
                f"SELECT state_blob, state_sha256 FROM {RESERVATION_TABLE} WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise RuntimeStateError(f"cannot load authoritative run state: {error}") from error
    if row is None:
        raise RuntimeStateError("run reservation does not exist")
    raw_blob = row[0]
    if isinstance(raw_blob, memoryview):
        encoded = raw_blob.tobytes()
    elif isinstance(raw_blob, (bytes, bytearray)):
        encoded = bytes(raw_blob)
    else:
        raise RuntimeStateError("run reservation has no authoritative state blob")
    if not encoded or hashlib.sha256(encoded).hexdigest() != row[1]:
        raise RuntimeStateError("authoritative run state digest mismatch")
    try:
        payload = json.loads(encoded.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeStateError("authoritative run state is invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeStateError("authoritative run state is not an object")
    return payload, encoded


def _audit_run_reservation_catalog(
    runtime_root: Path,
    *,
    project_id_hex: str,
    project_root: Path,
    runtime_authority_id: str,
) -> list[str]:
    database_path = runtime_root / CHECKPOINT_RELATIVE_PATH
    if not database_path.exists():
        raise RuntimeStateError(
            "runtime authority database disappeared after authority verification"
        )
    try:
        connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_reservation_table(connection)
            authority = connection.execute(
                f"SELECT project_id_hex, runtime_authority_id FROM {RUNTIME_AUTHORITY_TABLE} WHERE singleton = 1"
            ).fetchone()
            if authority != (project_id_hex, runtime_authority_id):
                raise RuntimeStateError("runtime authority identity changed during audit")
            rows = connection.execute(
                f"""
                SELECT run_id, reservation_token, artifact_path, state_sha256,
                       state_status, state_blob
                FROM {RESERVATION_TABLE}
                ORDER BY run_id
                """
            ).fetchall()
            marker = connection.execute(
                f"SELECT run_id, marker_json FROM {ACCOUNTABILITY_TABLE} WHERE project_id_hex = ?",
                (project_id_hex,),
            ).fetchone()
            unresolved: set[str] = set()
            for row in rows:
                run_id, token, artifact_path, digest, stored_status, raw_blob = row
                if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
                    raise RuntimeStateError("run reservation catalog contains an invalid run ID")
                if not isinstance(token, str) or RESERVATION_TOKEN_PATTERN.fullmatch(token) is None:
                    raise RuntimeStateError(f"run reservation {run_id} has an invalid token")
                if isinstance(raw_blob, memoryview):
                    encoded = raw_blob.tobytes()
                elif isinstance(raw_blob, (bytes, bytearray)):
                    encoded = bytes(raw_blob)
                else:
                    raise RuntimeStateError(
                        f"run reservation {run_id} has no authoritative state blob"
                    )
                if not encoded or hashlib.sha256(encoded).hexdigest() != digest:
                    raise RuntimeStateError(
                        f"run reservation {run_id} authoritative digest mismatch"
                    )
                try:
                    state = json.loads(encoded.decode("utf-8", errors="strict"))
                except (UnicodeError, json.JSONDecodeError) as error:
                    raise RuntimeStateError(
                        f"run reservation {run_id} authoritative state is invalid"
                    ) from error
                if (
                    not isinstance(state, dict)
                    or state.get("run_id") != run_id
                    or state.get("reservation_token") != token
                    or state.get("status") != stored_status
                    or state.get("artifact_path") != artifact_path
                ):
                    raise RuntimeStateError(
                        f"run reservation {run_id} authoritative identity mismatch"
                    )
                same_project = state.get("project_id_hex") == project_id_hex
                if not same_project:
                    stored_root = state.get("project_root")
                    same_project = isinstance(stored_root, str) and (
                        Path(stored_root).resolve() == project_root
                    )
                if same_project and state.get("master_review_status") == "REQUIRES_USER_REASON":
                    unresolved.add(run_id)
            if marker is not None:
                marker_run_id, marker_json = marker
                try:
                    marker_payload = json.loads(marker_json)
                except (TypeError, json.JSONDecodeError) as error:
                    raise RuntimeStateError("project accountability marker is corrupt") from error
                if (
                    not isinstance(marker_payload, dict)
                    or marker_payload.get("project_id_hex") != project_id_hex
                    or marker_payload.get("run_id") != marker_run_id
                ):
                    raise RuntimeStateError("project accountability marker identity mismatch")
                unresolved.add(str(marker_run_id))
            connection.execute("COMMIT")
            return sorted(unresolved)
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
    except RuntimeStateError:
        raise
    except sqlite3.Error as error:
        raise RuntimeStateError(
            f"cannot audit authoritative run reservations: {error}"
        ) from error


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RuntimeStateError("run state node names must be strings or null")
    return value


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeStateError(f"{field_name} must be a non-empty string")
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


def _validate_planning_evidence_records(
    evidence: Sequence[Mapping[str, object]],
) -> None:
    for entry in evidence:
        if entry.get("node") == "planning":
            _validate_planning_evidence_record(entry)


def _validate_evidence_identity_and_status(
    entry: Mapping[str, object],
    *,
    evidence_kind: str,
) -> tuple[object, object, object]:
    session_id = entry.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeStateError(f"{evidence_kind} evidence has an invalid session ID")
    session_path = entry.get("session_path")
    if not isinstance(session_path, str) or not session_path:
        raise RuntimeStateError(f"{evidence_kind} evidence has an invalid session path")
    path = Path(session_path)
    if not path.is_absolute() or path.name != session_id:
        raise RuntimeStateError(
            f"{evidence_kind} evidence session path does not match its session ID"
        )
    registration_operation_id = entry.get("registration_operation_id")
    if (
        not isinstance(registration_operation_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", registration_operation_id) is None
    ):
        raise RuntimeStateError(
            f"{evidence_kind} evidence has an invalid registration operation ID"
        )
    raw_status = entry.get("verification_status")
    if not isinstance(raw_status, str) or not raw_status:
        raise RuntimeStateError(
            f"{evidence_kind} evidence has an invalid verification status"
        )
    application_status = entry.get("application_verification_status")
    if application_status not in {None, "VALID_COMPLETE", "INVALID"}:
        raise RuntimeStateError(
            f"{evidence_kind} evidence has an invalid application verification status"
        )
    final_hash = entry.get("final_hash")
    if final_hash is not None:
        _require_sha256(final_hash, "final_hash")
    if raw_status == "VALID_COMPLETE":
        _require_sha256(final_hash, "final_hash")
    if application_status == "VALID_COMPLETE" and raw_status != "VALID_COMPLETE":
        raise RuntimeStateError(
            f"{evidence_kind} evidence application status contradicts raw verification"
        )
    return raw_status, application_status, final_hash


def _validate_planning_evidence_record(entry: Mapping[str, object]) -> None:
    if entry.get("node") != "planning":
        raise RuntimeStateError("planning evidence has an invalid node")
    _validate_evidence_identity_and_status(entry, evidence_kind="planning")
    process_pid = entry.get("process_pid")
    creation_time = entry.get("process_creation_time_100ns")
    if (process_pid is None) != (creation_time is None):
        raise RuntimeStateError("planning evidence has a partial process identity")
    if process_pid is not None:
        if (
            isinstance(process_pid, bool)
            or not isinstance(process_pid, int)
            or process_pid <= 0
            or isinstance(creation_time, bool)
            or not isinstance(creation_time, int)
            or creation_time <= 0
        ):
            raise RuntimeStateError("planning evidence has an invalid process identity")


def _validate_execution_evidence_record(entry: Mapping[str, object]) -> None:
    node = entry.get("node")
    if node not in EXECUTION_NODE_ROLES:
        raise RuntimeStateError("execution evidence has an invalid node")
    _raw_status, application_status, _final_hash = (
        _validate_evidence_identity_and_status(entry, evidence_kind="execution")
    )
    process_pid = entry.get("process_pid")
    creation_time = entry.get("process_creation_time_100ns")
    if process_pid is None and creation_time is None:
        if application_status != "INVALID":
            raise RuntimeStateError(
                "execution evidence without process identity must be application-invalid"
            )
        return
    if (process_pid is None) != (creation_time is None):
        raise RuntimeStateError(
            "execution turn evidence has a partial App Server PID/creation time identity"
        )
    if (
        isinstance(process_pid, bool)
        or not isinstance(process_pid, int)
        or process_pid <= 0
    ):
        raise RuntimeStateError("execution turn evidence has no valid App Server PID")
    if (
        isinstance(creation_time, bool)
        or not isinstance(creation_time, int)
        or creation_time <= 0
    ):
        raise RuntimeStateError(
            "execution turn evidence has no valid App Server creation time"
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
            if node == "C":
                if not isinstance(
                    attempt.get("test_execution_request_path"), str
                ) or not attempt["test_execution_request_path"]:
                    raise RuntimeStateError(
                        "completed C attempt has no test execution request path"
                    )
                _require_sha256(
                    attempt.get("test_execution_request_sha256"),
                    "test_execution_request_sha256",
                )
                _require_sha256(
                    attempt.get("test_execution_policy_sha256"),
                    "test_execution_policy_sha256",
                )
                if attempt.get("test_runner_status") != "completed":
                    raise RuntimeStateError(
                        "completed C attempt has no completed trusted runner"
                    )
                if not isinstance(
                    attempt.get("test_evidence_manifest_path"), str
                ) or not attempt["test_evidence_manifest_path"]:
                    raise RuntimeStateError(
                        "completed C attempt has no test evidence manifest path"
                    )
                _require_sha256(
                    attempt.get("test_evidence_manifest_sha256"),
                    "test_evidence_manifest_sha256",
                )
                _require_sha256(
                    attempt.get("approved_test_plan_sha256"),
                    "approved_test_plan_sha256",
                )
                test_ids = attempt.get("test_ids")
                if (
                    not isinstance(test_ids, list)
                    or not test_ids
                    or not all(isinstance(item, str) and item for item in test_ids)
                    or len(set(test_ids)) != len(test_ids)
                ):
                    raise RuntimeStateError(
                        "completed C attempt has invalid bound test IDs"
                    )
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
            if not isinstance(receipt.get("instruction_receipt_path"), str):
                raise RuntimeStateError(
                    "completed execution turn has no GPT instruction receipt path"
                )
            _require_sha256(
                receipt.get("instruction_receipt_sha256"),
                "instruction_receipt_sha256",
            )
            _require_sha256(
                receipt.get("instruction_receipt_challenge"),
                "instruction_receipt_challenge",
            )
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


def _validate_registration_intent(
    intent: Mapping[str, object] | None,
    *,
    run_id: str,
    upstream_port: int,
    execution_turns: Sequence[Mapping[str, object]],
) -> None:
    if intent is None:
        return
    if set(intent) != {
        "operation_id",
        "run_id",
        "node",
        "attempt_id",
        "job_id",
        "upstream_port",
        "created_at_utc",
    }:
        raise RuntimeStateError("registration intent has an invalid field set")
    operation_id = intent.get("operation_id")
    if (
        not isinstance(operation_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", operation_id) is None
    ):
        raise RuntimeStateError("registration intent has an invalid operation ID")
    if intent.get("run_id") != run_id or intent.get("upstream_port") != upstream_port:
        raise RuntimeStateError("registration intent changed run identity")
    created_at = intent.get("created_at_utc")
    if not isinstance(created_at, str) or not created_at:
        raise RuntimeStateError("registration intent has no creation time")
    node = intent.get("node")
    if node == "planning":
        if intent.get("attempt_id") is not None:
            raise RuntimeStateError("planning registration intent has an attempt ID")
        if intent.get("job_id") != f"{run_id}:planning-app-server":
            raise RuntimeStateError("planning registration intent has an invalid job ID")
        return
    if node not in EXECUTION_NODE_ROLES:
        raise RuntimeStateError("registration intent has an invalid node")
    receipt = next(
        (
            candidate
            for candidate in execution_turns
            if candidate.get("attempt_id") == intent.get("attempt_id")
            and candidate.get("job_id") == intent.get("job_id")
            and candidate.get("node") == node
        ),
        None,
    )
    if receipt is None or receipt.get("status") not in {"preparing", "inProgress"}:
        raise RuntimeStateError(
            "registration intent does not match one recoverable execution turn"
        )
    if (
        receipt.get("status") == "preparing"
        and receipt.get("evidence_session_ids") != []
    ):
        raise RuntimeStateError(
            "registration intent preparing turn already has evidence"
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
            creation_time = entry.get("process_creation_time_100ns")
            if process_pid is None and creation_time is None:
                if entry.get("application_verification_status") != "INVALID":
                    raise RuntimeStateError(
                        "execution evidence without process identity is not invalid"
                    )
            elif (
                isinstance(process_pid, bool)
                or not isinstance(process_pid, int)
                or process_pid <= 0
                or isinstance(creation_time, bool)
                or not isinstance(creation_time, int)
                or creation_time <= 0
            ):
                raise RuntimeStateError(
                    "execution turn evidence has no valid App Server process identity"
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
            if not isinstance(receipt.get("instruction_receipt_path"), str):
                raise RuntimeStateError(
                    "completed planning turn has no GPT instruction receipt path"
                )
            _require_sha256(
                receipt.get("instruction_receipt_sha256"),
                "instruction_receipt_sha256",
            )
            _require_sha256(
                receipt.get("instruction_receipt_challenge"),
                "instruction_receipt_challenge",
            )


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
            semantic_issues = _validate_semantic_issues(
                record.get("semantic_issues", [])
            )
            prior_round = rounds[index - 2] if index > 1 else None
            prior_issue_ids = {
                str(issue["semantic_issue_id"])
                for issue in (
                    prior_round.get("semantic_issues", [])
                    if isinstance(prior_round, Mapping)
                    and prior_round.get("status") == "rejected"
                    else []
                )
                if isinstance(issue, dict)
            }
            _validate_prior_issue_assessments(
                record.get("prior_issue_assessments", []),
                prior_issue_ids=prior_issue_ids,
                current_issue_ids={
                    str(issue["semantic_issue_id"]) for issue in semantic_issues
                },
            )
            repeated = record.get("repeated_unresolved_issue_ids", [])
            if not isinstance(repeated, list) or not all(
                isinstance(issue_id, str) and issue_id for issue_id in repeated
            ):
                raise RuntimeStateError(
                    "prior planning round has invalid repeated semantic issue IDs"
                )
            accepted = _planning_review_is_accepted(record)
            if status == "rejected" and accepted:
                raise RuntimeStateError(
                    "prior rejected planning round satisfies approval rules"
                )
            if status in {"publishing", "approved"} and not accepted:
                raise RuntimeStateError(
                    "prior approved planning round violates approval rules"
                )
            if status in {"publishing", "approved"} and semantic_issues:
                raise RuntimeStateError(
                    "prior approved planning round contains semantic issues"
                )
            if status == "rejected" and not semantic_issues:
                raise RuntimeStateError(
                    "prior rejected planning round has no semantic issues"
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


def _validate_semantic_issues(value: object) -> list[dict[str, object]]:
    required_fields = {
        "semantic_issue_id",
        "premises",
        "inference",
        "conclusion",
        "missing_evidence",
        "alternative_explanations",
        "closure_conditions",
    }
    optional_fields = {"predecessor_issue_ids", "semantic_identity_sha256"}
    if not isinstance(value, list):
        raise RuntimeStateError("semantic_issues must be a list")
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, issue in enumerate(value):
        if (
            not isinstance(issue, dict)
            or not required_fields.issubset(issue)
            or not set(issue).issubset(required_fields | optional_fields)
        ):
            raise RuntimeStateError(f"semantic issue {index} has invalid fields")
        issue_id = issue["semantic_issue_id"]
        if not isinstance(issue_id, str) or not issue_id:
            raise RuntimeStateError(f"semantic issue {index} has an invalid ID")
        if issue_id in seen_ids:
            raise RuntimeStateError("semantic issue IDs must be unique within a review")
        seen_ids.add(issue_id)
        for field in ("inference", "conclusion"):
            if not isinstance(issue[field], str) or not issue[field]:
                raise RuntimeStateError(
                    f"semantic issue {index} has an invalid {field}"
                )
        for field in (
            "premises",
            "missing_evidence",
            "alternative_explanations",
            "closure_conditions",
        ):
            entries = issue[field]
            if (
                not isinstance(entries, list)
                or not all(isinstance(item, str) and item for item in entries)
                or field in {"premises", "closure_conditions"}
                and not entries
            ):
                raise RuntimeStateError(
                    f"semantic issue {index} has an invalid {field}"
                )
        predecessor_ids = issue.get("predecessor_issue_ids", [])
        if (
            not isinstance(predecessor_ids, list)
            or not all(isinstance(item, str) and item for item in predecessor_ids)
            or len(predecessor_ids) != len(set(predecessor_ids))
        ):
            raise RuntimeStateError(
                f"semantic issue {index} has invalid predecessor_issue_ids"
            )
        identity_body = {
            field: (
                sorted(_normalize_semantic_text(item) for item in issue[field])
                if isinstance(issue[field], list)
                else _normalize_semantic_text(str(issue[field]))
            )
            for field in sorted(required_fields - {"semantic_issue_id"})
        }
        computed_identity = hashlib.sha256(
            json.dumps(
                identity_body,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        supplied_identity = issue.get("semantic_identity_sha256")
        if supplied_identity is not None and supplied_identity != computed_identity:
            raise RuntimeStateError(
                f"semantic issue {index} identity does not match its logical units"
            )
        normalized_issue = {
            field: (
                list(issue[field]) if isinstance(issue[field], list) else issue[field]
            )
            for field in sorted(required_fields)
        }
        normalized_issue["predecessor_issue_ids"] = list(predecessor_ids)
        normalized_issue["semantic_identity_sha256"] = computed_identity
        normalized.append(normalized_issue)
    return normalized


def _validate_prior_issue_assessments(
    value: object,
    *,
    prior_issue_ids: set[str],
    current_issue_ids: set[str],
) -> list[dict[str, object]]:
    required_fields = {
        "prior_semantic_issue_id",
        "disposition",
        "current_semantic_issue_ids",
        "rationale",
        "evidence",
    }
    if not isinstance(value, list):
        raise RuntimeStateError("prior_issue_assessments must be a list")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, assessment in enumerate(value):
        if not isinstance(assessment, dict) or set(assessment) != required_fields:
            raise RuntimeStateError(
                f"prior issue assessment {index} has invalid fields"
            )
        prior_id = assessment["prior_semantic_issue_id"]
        if not isinstance(prior_id, str) or prior_id not in prior_issue_ids:
            raise RuntimeStateError(
                f"prior issue assessment {index} identifies an unknown issue"
            )
        if prior_id in seen:
            raise RuntimeStateError("prior issue assessment IDs must be unique")
        seen.add(prior_id)
        disposition = assessment["disposition"]
        if disposition not in {
            "REPEATED_UNRESOLVED",
            "RESOLVED",
            "SUPERSEDED",
        }:
            raise RuntimeStateError(
                f"prior issue assessment {index} has an invalid disposition"
            )
        linked = assessment["current_semantic_issue_ids"]
        if (
            not isinstance(linked, list)
            or len(linked) != len(set(linked))
            or not all(
                isinstance(issue_id, str) and issue_id in current_issue_ids
                for issue_id in linked
            )
        ):
            raise RuntimeStateError(
                f"prior issue assessment {index} has invalid current issue links"
            )
        if disposition == "REPEATED_UNRESOLVED" and not linked:
            raise RuntimeStateError(
                f"prior issue assessment {index} omits the repeated current issue"
            )
        if disposition != "REPEATED_UNRESOLVED" and linked:
            raise RuntimeStateError(
                f"prior issue assessment {index} links current issues despite closure"
            )
        rationale = assessment["rationale"]
        evidence = assessment["evidence"]
        if not isinstance(rationale, str) or not rationale.strip():
            raise RuntimeStateError(
                f"prior issue assessment {index} has no semantic rationale"
            )
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(item, str) and item.strip() for item in evidence)
        ):
            raise RuntimeStateError(
                f"prior issue assessment {index} has no evidence"
            )
        normalized.append(
            {
                "prior_semantic_issue_id": prior_id,
                "disposition": disposition,
                "current_semantic_issue_ids": list(linked),
                "rationale": rationale,
                "evidence": list(evidence),
            }
        )
    if seen != prior_issue_ids:
        missing = sorted(prior_issue_ids - seen)
        extra = sorted(seen - prior_issue_ids)
        raise RuntimeStateError(
            "GPT semantic mapping receipt does not classify every prior issue; "
            f"missing={missing}, extra={extra}"
        )
    return normalized


def _normalize_semantic_text(value: str) -> str:
    return " ".join(value.casefold().split())


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


def _file_control_descriptor(path: Path) -> dict[str, object]:
    content = _read_required_file(path, "execution control artifact")
    return {
        "path": str(path.resolve()),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _file_descriptor_allow_empty(path: Path) -> dict[str, object]:
    try:
        if not path.is_file():
            raise RuntimeStateError(f"evidence file is missing: {path}")
        content = path.read_bytes()
    except RuntimeStateError:
        raise
    except OSError as error:
        raise RuntimeStateError(f"cannot read evidence file: {path}: {error}") from error
    return {
        "path": str(path.resolve()),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _file_identity(path: Path) -> dict[str, int] | None:
    try:
        status = path.stat()
    except OSError:
        return None
    return {"device": int(status.st_dev), "inode": int(status.st_ino)}


def _actual_file_descriptor(path: Path) -> dict[str, object]:
    try:
        if not path.is_file():
            return {
                "actual_state": "missing",
                "actual_size": None,
                "actual_sha256": None,
                "actual_file_identity": None,
            }
        content = path.read_bytes()
    except OSError as error:
        return {
            "actual_state": "unreadable",
            "actual_size": None,
            "actual_sha256": None,
            "actual_file_identity": None,
            "read_error": f"{type(error).__name__}: {error}",
        }
    return {
        "actual_state": "present",
        "actual_size": len(content),
        "actual_sha256": hashlib.sha256(content).hexdigest(),
        "actual_file_identity": _file_identity(path),
    }


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
    encoded = _canonical_json_bytes(payload)
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


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    _write_bytes_exclusive(path, _canonical_json_bytes(payload))


def _write_bytes_exclusive(path: Path, encoded: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
