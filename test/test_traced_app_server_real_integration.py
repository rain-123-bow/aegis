from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "test"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aegis_runtime  # noqa: E402
from aegis_runtime import (  # noqa: E402
    RuntimeCoordinator,
    TraceRelayClient,
    resolve_tracerelay_command,
)
from aegis_test_support import (  # noqa: E402
    initialize_test_git_repository,
    write_test_engineering_input_manifest,
    write_test_execution_request,
    write_test_reasoning_context_pack,
    write_test_runtime_scope_policy,
)
from engineering_input_manifest import validate_engineering_input_manifest  # noqa: E402
from main import (  # noqa: E402
    complete_reviewer_model_output,
    execution_output_schema,
    execution_reviewer_output_schema,
    planning_review_output_schema,
    require_control_envelope_unchanged,
    validate_reviewer_envelope,
)
from project_seal_store import record_project_seal  # noqa: E402
from reviewer_contract import (  # noqa: E402
    FINAL_REVIEWER as REVIEW_CONTRACT_FINAL_REVIEWER,
    TEST_RESULT_REVIEWER as REVIEW_CONTRACT_TEST_RESULT_REVIEWER,
    coordinator_review_stage,
)
from tracerelay_client import (  # noqa: E402
    _windows_job_name,
    _windows_process_creation_time_100ns,
)
from windows_job_runner import _freeze_named_job_members  # noqa: E402


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

REVIEW_NODE_SCHEMA = planning_review_output_schema()

CONTROL_PLANE_REPORT_SCHEMA = "aegis.app_server_control_acceptance.v7"

AEGIS_SOURCE_BINDINGS = tuple(
    path.relative_to(PROJECT_ROOT).as_posix()
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py"))
)

TRACERELAY_SOURCE_BINDINGS = (
    "third_party/TraceRelay/src/tracerelay/cli.py",
    "third_party/TraceRelay/src/tracerelay/config.py",
    "third_party/TraceRelay/src/tracerelay/service.py",
    "third_party/TraceRelay/src/tracerelay/session.py",
    "third_party/TraceRelay/src/tracerelay/verify.py",
)

REQUIRED_REGISTRATION_CRASH_MODES = (
    "after_register_before_popen",
    "after_popen_before_identity_checkpoint",
)


def _write_production_runtime_fixture(project: Path) -> None:
    shutil.copy2(
        PROJECT_ROOT / "requirements-runtime.txt",
        project / "requirements-runtime.txt",
    )
    tracerelay_target = project / "third_party" / "TraceRelay"
    tracerelay_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PROJECT_ROOT / "third_party" / "TraceRelay", tracerelay_target)


def _stop_test_runtime(tracerelay_command: Sequence[str]) -> None:
    def invoke(*arguments: str) -> tuple[int, dict[str, object]]:
        completed = subprocess.run(
            [*tracerelay_command, *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=30,
        )
        raw = completed.stdout.strip() or completed.stderr.strip()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(payload, dict):
            raise AssertionError("TraceRelay cleanup returned a non-object")
        return completed.returncode, payload

    _returncode, status = invoke("status")
    if status.get("state") == "NOT_RUNNING":
        return
    identity = status.get("runtime_identity")
    runtime_nonce = (
        identity.get("runtime_nonce") if isinstance(identity, dict) else None
    )
    if not isinstance(runtime_nonce, str) or not runtime_nonce:
        raise AssertionError("TraceRelay cleanup cannot prove the runtime nonce")
    returncode, stopped = invoke("stop", "--runtime-nonce", runtime_nonce)
    if returncode != 0 or stopped.get("ok") is not True:
        raise AssertionError(f"TraceRelay cleanup failed: {stopped}")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        _returncode, status = invoke("status")
        if status.get("state") == "NOT_RUNNING":
            return
        time.sleep(0.1)
    raise AssertionError("TraceRelay did not stop after acceptance cleanup")


def _write_synthetic_final_review_verdict(
    artifact_path: Path,
    *,
    workflow_run_id: str,
    status: bool,
) -> None:
    artifact_path.mkdir(parents=True, exist_ok=True)
    review_path = artifact_path / "FINAL_REVIEW.md"
    review_path.write_text("# Synthetic final review\n", encoding="utf-8")
    review_bytes = review_path.read_bytes()
    input_manifest_path = artifact_path / "FINAL_REVIEW_INPUT_MANIFEST.json"
    input_manifest_bytes = input_manifest_path.read_bytes()
    input_manifest = json.loads(input_manifest_bytes)
    evidence_index = [dict(item) for item in input_manifest["required_evidence"]]
    evidence_index.extend(
        [
            {
                "evidence_id": "final-review-input-manifest",
                "path": str(input_manifest_path.resolve()),
                "size": len(input_manifest_bytes),
                "sha256": hashlib.sha256(input_manifest_bytes).hexdigest(),
            },
            {
                "evidence_id": "final-review",
                "path": str(review_path.resolve()),
                "size": len(review_bytes),
                "sha256": hashlib.sha256(review_bytes).hexdigest(),
            },
        ]
    )
    (artifact_path / "FINAL_REVIEW_VERDICT.json").write_text(
        json.dumps(
            {
                "schema": "aegis.final_review_verdict.v1",
                "workflow_run_id": workflow_run_id,
                "verdict": "PASS" if status else "FAIL",
                "conclusion": "Crash recovery preserved the reviewed turn.",
                "reasons": ["The recovered response is bound to durable evidence."],
                "evidence_index": evidence_index,
            }
        ),
        encoding="utf-8",
    )


def _write_execution_crash_control_artifacts(
    coordinator: RuntimeCoordinator,
) -> dict[str, object]:
    artifact_path = coordinator.artifact_path
    artifact_path.mkdir(parents=True, exist_ok=True)
    if coordinator._engineering_input_manifest is None:
        coordinator._engineering_input_source_path = write_test_engineering_input_manifest(
            coordinator.project_root
        )
        coordinator._snapshot_engineering_inputs()
    if coordinator._reasoning_context_pack is None:
        assert coordinator._seal is not None
        assert coordinator._engineering_input_manifest is not None
        context_source = write_test_reasoning_context_pack(
            coordinator.project_root,
            artifact_path / "direct-f-context-source.json",
            project_id_hex=coordinator._seal.project_id.hex(),
            project_seal=coordinator._seal.expected_seal,
            engineering_documents_sha256=str(
                coordinator._engineering_input_manifest["documents_sha256"]
            ),
        )
        live_snapshot_path = (
            coordinator.project_root
            / ".aegis"
            / "reasoning_ledger"
            / "test-live-snapshot.json"
        )
        live_snapshot = json.loads(live_snapshot_path.read_text(encoding="utf-8"))
        with patch.object(
            aegis_runtime,
            "export_live_reasoning_ledger_snapshot",
            return_value=live_snapshot,
        ):
            coordinator._snapshot_reasoning_context_pack(context_source)
    else:
        live_snapshot_path = (
            coordinator.project_root
            / ".aegis"
            / "reasoning_ledger"
            / "test-live-snapshot.json"
        )
        live_snapshot = json.loads(live_snapshot_path.read_text(encoding="utf-8"))
    assert coordinator._reasoning_context_pack is not None
    assert coordinator._seal is not None
    context_path = Path(
        str(coordinator._reasoning_context_pack["snapshot_path"])
    ).resolve()
    round_id = "round-0001"
    round_directory = (
        coordinator.run_state_path.parent
        / "artifacts"
        / "graph"
        / "A"
        / round_id
    )
    plan_path = (round_directory / "TEST_PLAN.md").resolve()
    review_path = (round_directory / "TEST_PLAN_REVIEW.md").resolve()
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("# Crash acceptance test plan\n", encoding="utf-8")
    review_path.write_text("# Crash acceptance plan review\n", encoding="utf-8")
    plan_bytes = plan_path.read_bytes()
    review_bytes = review_path.read_bytes()
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    review_sha256 = hashlib.sha256(review_bytes).hexdigest()
    approved_path, handoff_path = coordinator._expected_planning_handoff_paths()
    approved_path.write_bytes(plan_bytes)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    review_result = {
        "artifact_path": str(coordinator.artifact_path),
        "reasoning_ledger_context_pack": str(context_path),
        "review_conclusion": "PASS",
        "finding_categories": [],
        "findings": [],
        "review_output_artifacts": [
            {
                "artifact_id": "test-plan-review",
                "path": str(review_path),
                "size": len(review_bytes),
                "sha256": review_sha256,
            }
        ],
    }
    planning_round: dict[str, object] = {
        "round_id": round_id,
        "status": "approved",
        "project_seal": coordinator._seal.expected_seal,
        "context_pack_path": str(context_path),
        "context_pack_sha256": coordinator._reasoning_context_pack["sha256"],
        "engineering_input_manifest": coordinator._engineering_input_control(),
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha256,
        "review_report_path": str(review_path),
        "review_report_sha256": review_sha256,
        "reviewed_plan_sha256": plan_sha256,
        "score": 100,
        "error_count": 0,
        "warning_count": 0,
        "verdict": "PASS",
        "review_conclusion": "PASS",
        "finding_categories": [],
        "findings": [],
        "review_result": review_result,
        "semantic_issues": [],
        "prior_issue_assessments": [],
        "repeated_unresolved_issue_ids": [],
        "created_at_utc": now,
        "frozen_at_utc": now,
        "reviewed_at_utc": now,
        "approved_plan_path": str(approved_path),
        "handoff_path": str(handoff_path),
    }
    handoff_path.write_text(
        json.dumps(
            coordinator._planning_handoff_payload(planning_round),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    approved_bytes = approved_path.read_bytes()
    handoff_bytes = handoff_path.read_bytes()
    planning_round.update(
        approved_plan_size=len(approved_bytes),
        approved_plan_sha256=hashlib.sha256(approved_bytes).hexdigest(),
        handoff_size=len(handoff_bytes),
        handoff_sha256=hashlib.sha256(handoff_bytes).hexdigest(),
    )
    coordinator._planning_rounds.append(planning_round)
    planning_session_id = f"planning-{uuid4().hex}"
    planning_session_path = (
        artifact_path / "synthetic-planning-evidence" / planning_session_id
    ).resolve()
    planning_session_path.mkdir(parents=True, exist_ok=False)
    coordinator._record_evidence(
        aegis_runtime.TraceRelayRegistration(
            session_id=planning_session_id,
            proxy_host="127.0.0.1",
            proxy_port=45_000,
            upstream_port=coordinator.upstream_port,
            session_path=planning_session_path,
            operation_id="ab" * 16,
        ),
        {"status": "VALID_COMPLETE", "final_hash": "cd" * 32},
        node="planning",
        application_verification_status="VALID_COMPLETE",
    )
    coordinator._planning_stage_status = "completed"
    coordinator._lock_run_wide_files(
        [plan_path, review_path, approved_path, handoff_path]
    )
    coordinator._write_state("running")
    with patch.object(
        aegis_runtime,
        "export_live_reasoning_ledger_snapshot",
        return_value=live_snapshot,
    ):
        coordinator._validate_completed_planning_stage()
    return live_snapshot


REGISTRATION_CRASH_CASE_FIELDS = frozenset(
    {
        "crash_mode",
        "worker_exit_code",
        "operation_id",
        "session_id",
        "session_path",
        "marker",
        "recovery_cli_commands",
        "verification",
        "application_verification_status",
        "final_run_status",
        "termination_reason_code",
        "persisted_process_pid",
        "persisted_process_creation_time_100ns",
        "observed_process_terminated",
        "observed_child_terminated",
        "observed_descendants_terminated",
        "frozen_job_members_terminated",
        "codex_cli_path",
        "codex_cli_version",
        "codex_cli_sha256",
    }
)
REGISTRATION_CRASH_VERIFICATION_FIELDS = frozenset(
    {
        "final_hash",
        "observed_bytes",
        "observed_connection_count",
        "record_count",
        "sent_error_bytes",
        "sent_success_bytes",
        "status",
        "unknown_bytes",
    }
)
REGISTRATION_CRASH_BYTE_DIRECTIONS = frozenset(
    {"client_to_upstream", "upstream_to_client"}
)
TRACERELAY_SESSION_ID_PATTERN = re.compile(
    r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z_[0-9a-f]{32}"
)


def _source_sha256(*relative_paths: str) -> dict[str, str]:
    return {
        relative_path: hashlib.sha256(
            (PROJECT_ROOT / relative_path).read_bytes()
        ).hexdigest()
        for relative_path in relative_paths
    }


class AcceptanceReportSourceBindingContractTests(unittest.TestCase):
    def test_control_plane_report_schema_is_v7(self) -> None:
        self.assertEqual(
            CONTROL_PLANE_REPORT_SCHEMA,
            "aegis.app_server_control_acceptance.v7",
        )

    def test_reports_bind_every_aegis_python_source(self) -> None:
        expected = tuple(
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in sorted((PROJECT_ROOT / "src").rglob("*.py"))
        )

        self.assertEqual(AEGIS_SOURCE_BINDINGS, expected)

    def test_control_plane_report_binds_current_codex_cli_bytes(self) -> None:
        captured = {
            "codex_cli_path": r"C:\\tools\\codex.cmd",
            "codex_cli_version": "codex-cli 0.test",
            "codex_cli_sha256": "ab" * 32,
        }
        state = {
            "codex_cli_path": captured["codex_cli_path"],
            "codex_cli_version": captured["codex_cli_version"],
        }

        with patch(
            f"{__name__}._validate_current_codex_cli_identity",
            return_value=captured,
        ):
            identity = _control_plane_codex_identity(state, captured)

        self.assertEqual(identity, captured)


def _capture_codex_cli_identity(command: str | Path) -> dict[str, str]:
    path = Path(command).resolve(strict=True)
    if not path.is_file():
        raise AssertionError("Codex CLI path is not a file")
    version = aegis_runtime.read_codex_cli_version(str(path))
    if not version.strip():
        raise AssertionError("Codex CLI version is empty")
    return {
        "codex_cli_path": str(path),
        "codex_cli_version": version,
        "codex_cli_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _validate_current_codex_cli_identity(
    identity: dict[str, object],
) -> dict[str, str]:
    if set(identity) != {
        "codex_cli_path",
        "codex_cli_version",
        "codex_cli_sha256",
    }:
        raise AssertionError("Codex CLI identity has an invalid field set")
    path_text = identity.get("codex_cli_path")
    version = identity.get("codex_cli_version")
    sha256 = identity.get("codex_cli_sha256")
    if (
        not isinstance(path_text, str)
        or not path_text.strip()
        or not isinstance(version, str)
        or not version.strip()
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise AssertionError("Codex CLI identity is invalid")
    current = _capture_codex_cli_identity(path_text)
    if current != identity:
        raise AssertionError("Codex CLI identity changed during acceptance")
    return current


def _control_plane_codex_identity(
    state: dict[str, object],
    captured_identity: dict[str, object],
) -> dict[str, str]:
    current = _validate_current_codex_cli_identity(captured_identity)
    if (
        state.get("codex_cli_path") != current["codex_cli_path"]
        or state.get("codex_cli_version") != current["codex_cli_version"]
    ):
        raise AssertionError("run state used a different Codex CLI identity")
    return current


def _collect_registration_crash_cases(
    run_case: Callable[[str], dict[str, object]],
) -> list[dict[str, object]]:
    """Run both required cases fail-fast; a failed case prevents publication."""
    return [run_case(crash_mode) for crash_mode in REQUIRED_REGISTRATION_CRASH_MODES]


def _validate_registration_crash_cases(
    cases: list[dict[str, object]],
) -> dict[str, str]:
    if len(cases) != len(REQUIRED_REGISTRATION_CRASH_MODES):
        raise AssertionError("registration crash report does not contain exactly two cases")
    modes = [case.get("crash_mode") for case in cases]
    if set(modes) != set(REQUIRED_REGISTRATION_CRASH_MODES) or len(set(modes)) != 2:
        raise AssertionError("registration crash report has an incomplete mode set")

    operation_ids: set[str] = set()
    session_ids: set[str] = set()
    codex_identities: set[tuple[str, str, str]] = set()
    for case in cases:
        if set(case) != REGISTRATION_CRASH_CASE_FIELDS:
            raise AssertionError("registration crash case has an invalid field set")
        crash_mode = case["crash_mode"]
        codex_identity = _validate_current_codex_cli_identity(
            {
                "codex_cli_path": case.get("codex_cli_path"),
                "codex_cli_version": case.get("codex_cli_version"),
                "codex_cli_sha256": case.get("codex_cli_sha256"),
            }
        )
        codex_identities.add(
            (
                codex_identity["codex_cli_path"],
                codex_identity["codex_cli_version"],
                codex_identity["codex_cli_sha256"],
            )
        )
        operation_id = case.get("operation_id")
        session_id = case.get("session_id")
        session_path = case.get("session_path")
        if case.get("worker_exit_code") != 91:
            raise AssertionError(f"registration crash worker did not exit 91: {crash_mode}")
        if (
            not isinstance(operation_id, str)
            or len(operation_id) != 32
            or any(character not in "0123456789abcdef" for character in operation_id)
            or operation_id in operation_ids
        ):
            raise AssertionError("registration crash operation identity is invalid")
        operation_ids.add(operation_id)
        if (
            not isinstance(session_id, str)
            or TRACERELAY_SESSION_ID_PATTERN.fullmatch(session_id) is None
            or session_id in session_ids
            or not isinstance(session_path, str)
            or not Path(session_path).is_absolute()
            or Path(session_path).name != session_id
        ):
            raise AssertionError("registration crash session identity is invalid")
        try:
            datetime.strptime(session_id.split("_", maxsplit=1)[0], "%Y%m%dT%H%M%S.%fZ")
        except ValueError as error:
            raise AssertionError(
                "registration crash session timestamp is invalid"
            ) from error
        session_ids.add(session_id)

        marker = case.get("marker")
        expected_popen = crash_mode == "after_popen_before_identity_checkpoint"
        expected_marker_fields = {"crash_mode", "popen_started"}
        if expected_popen:
            expected_marker_fields.update(
                {
                    "observed_process_pid",
                    "observed_process_creation_time_100ns",
                    "observed_process_active_before_crash",
                    "observed_child_pid",
                    "observed_child_creation_time_100ns",
                    "expected_child_image_path",
                    "observed_child_image_path",
                    "observed_child_active_before_crash",
                    "observed_descendant_processes",
                    "job_name",
                    "job_creation_frozen",
                    "frozen_job_member_processes",
                }
            )
        if (
            not isinstance(marker, dict)
            or set(marker) != expected_marker_fields
            or marker.get("crash_mode") != crash_mode
            or marker.get("popen_started") is not expected_popen
        ):
            raise AssertionError("registration crash marker does not match its mode")
        observed_process_pid = marker.get("observed_process_pid")
        observed_process_creation_time = marker.get(
            "observed_process_creation_time_100ns"
        )
        observed_child_pid = marker.get("observed_child_pid")
        observed_child_creation_time = marker.get(
            "observed_child_creation_time_100ns"
        )
        expected_child_image_path = marker.get("expected_child_image_path")
        observed_child_image_path = marker.get("observed_child_image_path")
        observed_descendants = marker.get("observed_descendant_processes")
        frozen_job_members = marker.get("frozen_job_member_processes")
        if expected_popen:
            if (
                isinstance(observed_process_pid, bool)
                or not isinstance(observed_process_pid, int)
                or observed_process_pid <= 0
                or isinstance(observed_process_creation_time, bool)
                or not isinstance(observed_process_creation_time, int)
                or observed_process_creation_time <= 0
                or marker.get("observed_process_active_before_crash") is not True
                or isinstance(observed_child_pid, bool)
                or not isinstance(observed_child_pid, int)
                or observed_child_pid <= 0
                or isinstance(observed_child_creation_time, bool)
                or not isinstance(observed_child_creation_time, int)
                or observed_child_creation_time <= 0
                or observed_child_creation_time <= observed_process_creation_time
                or not isinstance(expected_child_image_path, str)
                or not Path(expected_child_image_path).is_absolute()
                or not isinstance(observed_child_image_path, str)
                or not Path(observed_child_image_path).is_absolute()
                or not _same_windows_executable_path(
                    observed_child_image_path, expected_child_image_path
                )
                or marker.get("observed_child_active_before_crash") is not True
                or observed_child_pid == observed_process_pid
            ):
                raise AssertionError(
                    "Popen crash marker has no active runner/AppServer identity"
                )
            if not isinstance(observed_descendants, list) or not observed_descendants:
                raise AssertionError(
                    "Popen crash marker has no observed AppServer descendants"
                )
            descendant_pids: set[int] = set()
            app_server_bound = False
            for descendant in observed_descendants:
                if not isinstance(descendant, dict) or set(descendant) != {
                    "pid",
                    "parent_pid",
                    "creation_time_100ns",
                    "image_path",
                    "command_line",
                    "active_before_crash",
                }:
                    raise AssertionError(
                        "Popen crash marker has an invalid descendant identity"
                    )
                pid = descendant.get("pid")
                parent_pid = descendant.get("parent_pid")
                creation_time = descendant.get("creation_time_100ns")
                image_path = descendant.get("image_path")
                command_line = descendant.get("command_line")
                if (
                    isinstance(pid, bool)
                    or not isinstance(pid, int)
                    or pid <= 0
                    or pid in descendant_pids
                    or isinstance(parent_pid, bool)
                    or not isinstance(parent_pid, int)
                    or parent_pid <= 0
                    or isinstance(creation_time, bool)
                    or not isinstance(creation_time, int)
                    or creation_time <= observed_process_creation_time
                    or not isinstance(image_path, str)
                    or not Path(image_path).is_absolute()
                    or not isinstance(command_line, str)
                    or not command_line.strip()
                    or descendant.get("active_before_crash") is not True
                ):
                    raise AssertionError(
                        "Popen crash marker descendant identity is invalid"
                    )
                descendant_pids.add(pid)
                folded_command = command_line.casefold()
                if "app-server" in folded_command and "stdio://" in folded_command:
                    app_server_bound = True
            if not app_server_bound:
                raise AssertionError(
                    "Popen crash marker does not bind an AppServer command identity"
                )
            expected_job_name = _windows_job_name(operation_id)
            if (
                marker.get("job_name") != expected_job_name
                or marker.get("job_creation_frozen") is not True
                or not isinstance(frozen_job_members, list)
                or len(frozen_job_members) < 3
            ):
                raise AssertionError(
                    "Popen crash marker has no frozen authoritative Job membership"
                )
            frozen_member_pids: set[int] = set()
            for member in frozen_job_members:
                if not isinstance(member, dict) or set(member) != {
                    "pid",
                    "parent_pid",
                    "creation_time_100ns",
                    "image_path",
                    "command_line",
                    "active_before_crash",
                    "suspended_before_crash",
                }:
                    raise AssertionError("frozen Job member identity is invalid")
                member_pid = member.get("pid")
                member_parent = member.get("parent_pid")
                member_creation = member.get("creation_time_100ns")
                member_image = member.get("image_path")
                member_command = member.get("command_line")
                if (
                    isinstance(member_pid, bool)
                    or not isinstance(member_pid, int)
                    or member_pid <= 0
                    or member_pid in frozen_member_pids
                    or isinstance(member_parent, bool)
                    or not isinstance(member_parent, int)
                    or member_parent <= 0
                    or isinstance(member_creation, bool)
                    or not isinstance(member_creation, int)
                    or member_creation <= 0
                    or not isinstance(member_image, str)
                    or not Path(member_image).is_absolute()
                    or not isinstance(member_command, str)
                    or not member_command.strip()
                    or member.get("active_before_crash") is not True
                    or member.get("suspended_before_crash")
                    is not (member_pid != observed_process_pid)
                ):
                    raise AssertionError("frozen Job member identity is invalid")
                frozen_member_pids.add(member_pid)
            if frozen_member_pids != {
                int(observed_process_pid),
                int(observed_child_pid),
                *descendant_pids,
            }:
                raise AssertionError(
                    "frozen Job membership does not exactly cover the observed process tree"
                )
            if not any(
                "app-server" in str(member["command_line"]).casefold()
                and "stdio://" in str(member["command_line"]).casefold()
                for member in frozen_job_members
            ):
                raise AssertionError("frozen Job membership has no Codex AppServer")
            if not any(
                codex_identity["codex_cli_path"].casefold()
                in str(member["command_line"]).casefold()
                for member in frozen_job_members
            ):
                raise AssertionError(
                    "frozen Job membership is not bound to the recorded Codex CLI"
                )
            known_parents = {int(observed_child_pid), *descendant_pids}
            if any(
                int(descendant["parent_pid"]) not in known_parents
                for descendant in observed_descendants
            ):
                raise AssertionError(
                    "Popen crash marker descendant tree is disconnected"
                )
            parent_by_pid = {
                int(descendant["pid"]): int(descendant["parent_pid"])
                for descendant in observed_descendants
            }
            for descendant_pid in descendant_pids:
                cursor = descendant_pid
                visited: set[int] = set()
                while cursor != observed_child_pid:
                    if cursor in visited or cursor not in parent_by_pid:
                        raise AssertionError(
                            "Popen crash marker descendant tree has no path to the command shell"
                        )
                    visited.add(cursor)
                    cursor = parent_by_pid[cursor]
        elif any(
            value is not None
            for value in (
                observed_process_pid,
                observed_process_creation_time,
                observed_child_pid,
                observed_child_creation_time,
                expected_child_image_path,
                observed_child_image_path,
                observed_descendants,
                frozen_job_members,
            )
        ):
            raise AssertionError("pre-Popen crash marker contains a process identity")
        expected_terminated = True if expected_popen else None
        if (
            case.get("observed_process_terminated") is not expected_terminated
            or case.get("observed_child_terminated") is not expected_terminated
            or case.get("observed_descendants_terminated") is not expected_terminated
            or case.get("frozen_job_members_terminated") is not expected_terminated
        ):
            raise AssertionError(
                "registration crash left an observed runner/AppServer descendant alive"
            )

        expected_commands_already_idle = [
            ["resolve-registration", "--operation-id", operation_id],
            ["verify", session_path],
        ]
        recovery_commands = case.get("recovery_cli_commands")
        close_sequence_valid = False
        if isinstance(recovery_commands, list) and len(recovery_commands) == 3:
            close_command = recovery_commands[1]
            close_sequence_valid = (
                recovery_commands[0]
                == ["resolve-registration", "--operation-id", operation_id]
                and isinstance(close_command, list)
                and len(close_command) == 3
                and close_command[:2] == ["close", "--runtime-nonce"]
                and isinstance(close_command[2], str)
                and len(close_command[2]) == 32
                and all(
                    character in "0123456789abcdef"
                    for character in close_command[2]
                )
                and recovery_commands[2] == ["verify", session_path]
            )
        if recovery_commands != expected_commands_already_idle and not close_sequence_valid:
            raise AssertionError(
                "registration crash recovery command sequence is invalid: "
                f"{recovery_commands!r}"
            )
        verification = case.get("verification")
        if (
            not isinstance(verification, dict)
            or set(verification) != REGISTRATION_CRASH_VERIFICATION_FIELDS
            or verification.get("status") != "VALID_COMPLETE"
        ):
            raise AssertionError("registration crash journal is not VALID_COMPLETE")
        final_hash = verification.get("final_hash")
        if (
            not isinstance(final_hash, str)
            or len(final_hash) != 64
            or any(character not in "0123456789abcdef" for character in final_hash)
        ):
            raise AssertionError("registration crash journal has an invalid final hash")
        for count_field in ("observed_connection_count", "record_count"):
            count = verification.get(count_field)
            if type(count) is not int or count < 0:
                raise AssertionError(
                    f"registration crash journal has an invalid {count_field}"
                )
        byte_maps: dict[str, dict[str, int]] = {}
        for byte_field in (
            "observed_bytes",
            "sent_error_bytes",
            "sent_success_bytes",
            "unknown_bytes",
        ):
            byte_counts = verification.get(byte_field)
            if (
                not isinstance(byte_counts, dict)
                or set(byte_counts) != REGISTRATION_CRASH_BYTE_DIRECTIONS
                or any(type(value) is not int or value < 0 for value in byte_counts.values())
            ):
                raise AssertionError(
                    f"registration crash journal has invalid {byte_field}"
                )
            byte_maps[byte_field] = byte_counts
        for direction in REGISTRATION_CRASH_BYTE_DIRECTIONS:
            if byte_maps["observed_bytes"][direction] != sum(
                byte_maps[field][direction]
                for field in ("sent_success_bytes", "sent_error_bytes", "unknown_bytes")
            ):
                raise AssertionError(
                    "registration crash journal byte accounting is inconsistent"
                )
        if case.get("application_verification_status") != "INVALID":
            raise AssertionError("registration crash application verdict is not INVALID")
        if (
            case.get("final_run_status") != "terminated"
            or case.get("termination_reason_code") != "FREEZE_CONTINUITY_LOST"
        ):
            raise AssertionError(
                "registration crash run was not permanently continuity-terminated"
            )
        if (
            case["persisted_process_pid"] is not None
            or case["persisted_process_creation_time_100ns"] is not None
        ):
            raise AssertionError("registration crash report persisted an unverified identity")
    if len(codex_identities) != 1:
        raise AssertionError("registration crash cases used different Codex CLI identities")
    path, version, sha256 = codex_identities.pop()
    return {
        "codex_cli_path": path,
        "codex_cli_version": version,
        "codex_cli_sha256": sha256,
    }


def _publish_registration_crash_report(
    report_path: Path,
    *,
    cases: list[dict[str, object]],
    tracerelay_command: str | Path | Sequence[str],
) -> dict[str, object]:
    codex_identity = _validate_registration_crash_cases(cases)
    command = (
        resolve_tracerelay_command(tracerelay_command)
        if isinstance(tracerelay_command, (str, Path))
        else tuple(tracerelay_command)
    )
    python_path = Path(command[0]).resolve(strict=True)
    report: dict[str, object] = {
        "schema": "aegis.registration_crash_acceptance.v7",
        "verdict": "PASS",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cases": cases,
        "tracerelay_command": list(command),
        "tracerelay_python_sha256": hashlib.sha256(
            python_path.read_bytes()
        ).hexdigest(),
        **codex_identity,
        "source_sha256": _source_sha256(
            *AEGIS_SOURCE_BINDINGS,
            "test/test_traced_app_server_real_integration.py",
            *TRACERELAY_SOURCE_BINDINGS,
        ),
    }
    report_path = report_path.resolve()
    temporary_path = report_path.with_name(f".{report_path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, report_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return report


def _shared_worker_pycache(fallback: Path) -> Path:
    if sys.pycache_prefix is None:
        fallback.mkdir(parents=True)
        return fallback.resolve()
    shared = Path(sys.pycache_prefix).resolve()
    if not shared.is_dir() or any(shared.iterdir()):
        raise RuntimeError(
            "real acceptance pycache prefix must be an existing empty directory"
        )
    return shared


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
            command=config["tracerelay_command"],
            monitor_interval_seconds=0.05,
        ),
        start_node="C",
    )
    coordinator.preflight()
    live_snapshot = _write_execution_crash_control_artifacts(coordinator)

    def crash_after_turn_checkpoint(
        *_args: object, **_kwargs: object
    ) -> None:
        os._exit(91)

    def operation(node_state: dict[str, object]) -> dict[str, object]:
        response = coordinator.run_execution_agent(
            "TEST_EXECUTOR",
            str(config["prompt"]),
            output_schema=NODE_SCHEMA,
            developer_instructions=str(config["developer_instructions"]),
            timeout_seconds=300,
        )
        return {**node_state, "response": response, "current_node": "C"}

    with (
        patch.object(
            aegis_runtime,
            "export_live_reasoning_ledger_snapshot",
            return_value=live_snapshot,
        ),
        patch.object(
            aegis_runtime.AppServerClient,
            "wait_turn",
            crash_after_turn_checkpoint,
        ),
    ):
        coordinator.execute_node("C", operation, state)
    raise AssertionError("crash worker unexpectedly returned")


def _run_registration_crash_worker(config_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    crash_mode = str(config["crash_mode"])
    marker_path = Path(config["marker_path"])
    expected_child_image_path = Path(
        str(config["expected_child_image_path"])
    ).resolve()
    default_creation_time_reader = TraceRelayClient(
        command=config["tracerelay_command"]
    )._process_creation_time_reader
    coordinator: RuntimeCoordinator | None = None

    def crash_before_popen(*_args: object, **_kwargs: object) -> object:
        marker_path.write_text(
            json.dumps({"crash_mode": crash_mode, "popen_started": False}) + "\n",
            encoding="utf-8",
        )
        os._exit(91)

    def crash_before_creation_time_checkpoint(process_pid: int) -> int:
        if coordinator is None or coordinator._registration_intent is None:
            return default_creation_time_reader(process_pid)
        relay_client = coordinator.relay_client
        if process_pid in {
            relay_client._service_pid,
            relay_client._supervisor_pid,
        }:
            return default_creation_time_reader(process_pid)
        process_creation_time_100ns = default_creation_time_reader(process_pid)
        deadline = time.monotonic() + 10
        child_candidates: list[tuple[int, int, Path]] = []
        while time.monotonic() < deadline:
            child_candidates = []
            for pid in _windows_direct_child_pids(process_pid):
                if not _windows_process_is_running(pid):
                    continue
                child_creation_time = default_creation_time_reader(pid)
                if child_creation_time <= process_creation_time_100ns:
                    continue
                child_image_path = _windows_process_image_path(pid)
                if not _same_windows_executable_path(
                    child_image_path, expected_child_image_path
                ):
                    continue
                child_candidates.append(
                    (pid, child_creation_time, child_image_path)
                )
            if len(child_candidates) == 1:
                break
            if len(child_candidates) > 1:
                raise RuntimeError(
                    "multiple matching AppServer child identities were observed"
                )
            if not _windows_process_is_running(process_pid):
                raise RuntimeError(
                    "Windows Job runner exited before AppServer child startup"
                )
            time.sleep(0.02)
        if not child_candidates:
            raise RuntimeError("AppServer child did not start before crash injection")
        child_pid, child_creation_time_100ns, child_image_path = child_candidates[0]
        if (
            not _windows_process_identity_is_running(
                process_pid, process_creation_time_100ns
            )
            or not _windows_process_identity_is_running(
                child_pid, child_creation_time_100ns
            )
        ):
            raise RuntimeError(
                "managed process identity was not active before crash injection"
            )
        descendant_deadline = time.monotonic() + 10
        observed_descendants: list[dict[str, object]] = []
        while time.monotonic() < descendant_deadline:
            observed_descendants = []
            for descendant_pid, parent_pid in _windows_descendant_processes(
                child_pid
            ):
                if not _windows_process_is_running(descendant_pid):
                    continue
                descendant_creation_time = default_creation_time_reader(
                    descendant_pid
                )
                if descendant_creation_time <= process_creation_time_100ns:
                    continue
                descendant_image = _windows_process_image_path(descendant_pid)
                descendant_command = _windows_process_command_line(descendant_pid)
                if not _windows_process_identity_is_running(
                    descendant_pid, descendant_creation_time
                ):
                    continue
                observed_descendants.append(
                    {
                        "pid": descendant_pid,
                        "parent_pid": parent_pid,
                        "creation_time_100ns": descendant_creation_time,
                        "image_path": str(descendant_image),
                        "command_line": descendant_command,
                        "active_before_crash": True,
                    }
                )
            if any(
                "app-server" in str(item["command_line"]).casefold()
                and "stdio://" in str(item["command_line"]).casefold()
                for item in observed_descendants
            ):
                break
            if not _windows_process_identity_is_running(
                child_pid, child_creation_time_100ns
            ):
                raise RuntimeError(
                    "AppServer command shell exited before descendant attribution"
                )
            time.sleep(0.02)
        if not observed_descendants or not any(
            "app-server" in str(item["command_line"]).casefold()
            and "stdio://" in str(item["command_line"]).casefold()
            for item in observed_descendants
        ):
            raise RuntimeError(
                "real Codex AppServer descendant was not observed before crash injection"
            )
        operation_id = str(coordinator._registration_intent["operation_id"])
        job_name = _windows_job_name(operation_id)
        frozen_member_pids = _freeze_named_job_members(
            job_name, runner_pid=process_pid
        )
        if process_pid not in frozen_member_pids or child_pid not in frozen_member_pids:
            raise RuntimeError("frozen Job membership omitted the runner or command shell")
        parent_by_pid = _windows_process_parent_map()
        frozen_job_members: list[dict[str, object]] = []
        for member_pid in frozen_member_pids:
            member_creation_time = default_creation_time_reader(member_pid)
            if not _windows_process_identity_is_running(
                member_pid, member_creation_time
            ):
                raise RuntimeError("frozen Job member identity was not active")
            parent_pid = parent_by_pid.get(member_pid)
            if not isinstance(parent_pid, int) or parent_pid <= 0:
                raise RuntimeError("frozen Job member has no process parent identity")
            frozen_job_members.append(
                {
                    "pid": member_pid,
                    "parent_pid": parent_pid,
                    "creation_time_100ns": member_creation_time,
                    "image_path": str(_windows_process_image_path(member_pid)),
                    "command_line": _windows_process_command_line(member_pid),
                    "active_before_crash": True,
                    "suspended_before_crash": member_pid != process_pid,
                }
            )
        observed_descendants = [
            {
                key: value
                for key, value in member.items()
                if key != "suspended_before_crash"
            }
            for member in frozen_job_members
            if member["pid"] not in {process_pid, child_pid}
        ]
        if not observed_descendants or not any(
            "app-server" in str(item["command_line"]).casefold()
            and "stdio://" in str(item["command_line"]).casefold()
            for item in observed_descendants
        ):
            raise RuntimeError("frozen Job membership omitted the real Codex AppServer")
        marker_path.write_text(
            json.dumps(
                {
                    "crash_mode": crash_mode,
                    "popen_started": True,
                    "observed_process_pid": process_pid,
                    "observed_process_creation_time_100ns": (
                        process_creation_time_100ns
                    ),
                    "observed_process_active_before_crash": True,
                    "observed_child_pid": child_pid,
                    "observed_child_creation_time_100ns": (
                        child_creation_time_100ns
                    ),
                    "expected_child_image_path": str(expected_child_image_path),
                    "observed_child_image_path": str(child_image_path),
                    "observed_child_active_before_crash": True,
                    "observed_descendant_processes": observed_descendants,
                    "job_name": job_name,
                    "job_creation_frozen": True,
                    "frozen_job_member_processes": frozen_job_members,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        os._exit(91)

    relay_options: dict[str, object] = {}
    if crash_mode == "after_register_before_popen":
        relay_options["popen_factory"] = crash_before_popen
    elif crash_mode == "after_popen_before_identity_checkpoint":
        relay_options["process_creation_time_reader"] = (
            crash_before_creation_time_checkpoint
        )
    else:
        raise ValueError(f"unsupported registration crash mode: {crash_mode}")

    project = Path(config["project"])
    artifact_path = Path(config["artifact_path"])
    state = dict(config["state"])
    coordinator = RuntimeCoordinator(
        project_root=project,
        artifact_path=artifact_path,
        run_id=str(config["run_id"]),
        upstream_port=int(config["upstream_port"]),
        relay_client=TraceRelayClient(
            command=config["tracerelay_command"],
            monitor_interval_seconds=0.05,
            **relay_options,
        ),
        start_node="C",
    )
    coordinator.preflight()
    live_snapshot = _write_execution_crash_control_artifacts(coordinator)

    def operation(node_state: dict[str, object]) -> dict[str, object]:
        response = coordinator.run_execution_agent(
            "TEST_EXECUTOR",
            str(config["prompt"]),
            output_schema=NODE_SCHEMA,
            developer_instructions=str(config["developer_instructions"]),
            timeout_seconds=300,
        )
        return {**node_state, "response": response, "current_node": "C"}

    with patch.object(
        aegis_runtime,
        "export_live_reasoning_ledger_snapshot",
        return_value=live_snapshot,
    ):
        coordinator.execute_node("C", operation, state)
    raise AssertionError("registration crash worker unexpectedly returned")


def _windows_process_is_running(process_pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
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
        wait_result = int(kernel32.WaitForSingleObject(process, 0))
        if wait_result == wait_timeout:
            return True
        if wait_result == wait_object_0:
            return False
        raise OSError(
            ctypes.get_last_error(),
            f"WaitForSingleObject failed for PID {process_pid}: {wait_result}",
        )
    finally:
        kernel32.CloseHandle(process)


def _windows_process_identity_is_running(
    process_pid: int, creation_time_100ns: int
) -> bool:
    if not _windows_process_is_running(process_pid):
        return False
    try:
        return (
            _windows_process_creation_time_100ns(process_pid)
            == creation_time_100ns
        )
    except RuntimeError:
        if not _windows_process_is_running(process_pid):
            return False
        raise


def _windows_process_parent_map() -> dict[int, int]:
    import ctypes
    from ctypes import wintypes

    th32cs_snapprocess = 0x00000002
    max_path = 260

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * max_path),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        parents: dict[int, int] = {}
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            raise OSError(ctypes.get_last_error(), "Process32FirstW failed")
        while True:
            process_pid = int(entry.th32ProcessID)
            parent_pid = int(entry.th32ParentProcessID)
            if process_pid > 0 and parent_pid > 0:
                parents[process_pid] = parent_pid
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return parents
    finally:
        kernel32.CloseHandle(snapshot)


def _windows_direct_child_pids(parent_pid: int) -> list[int]:
    return sorted(
        process_pid
        for process_pid, observed_parent_pid in _windows_process_parent_map().items()
        if observed_parent_pid == parent_pid
    )


def _windows_descendant_processes(parent_pid: int) -> list[tuple[int, int]]:
    descendants: list[tuple[int, int]] = []
    pending = [parent_pid]
    seen = {parent_pid}
    while pending:
        current_parent = pending.pop(0)
        for child_pid in _windows_direct_child_pids(current_parent):
            if child_pid in seen:
                continue
            seen.add(child_pid)
            descendants.append((child_pid, current_parent))
            pending.append(child_pid)
    return descendants


def _windows_process_image_path(process_pid: int) -> Path:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process = kernel32.OpenProcess(
        process_query_limited_information, False, process_pid
    )
    if not process:
        raise OSError(
            ctypes.get_last_error(), f"cannot inspect process image PID {process_pid}"
        )
    try:
        capacity = wintypes.DWORD(32_768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(
            process, 0, buffer, ctypes.byref(capacity)
        ):
            raise OSError(
                ctypes.get_last_error(),
                f"QueryFullProcessImageNameW failed for PID {process_pid}",
            )
        return Path(buffer.value).resolve()
    finally:
        kernel32.CloseHandle(process)


def _windows_process_command_line(process_pid: int) -> str:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise RuntimeError("PowerShell is unavailable for process attribution")
    completed = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                # Hidden Windows PowerShell processes otherwise use the local
                # code page, while the reader below requires lossless UTF-8.
                "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
                "$process = Get-CimInstance Win32_Process -Filter "
                f"'ProcessId = {process_pid}'; "
                "if ($null -eq $process) { exit 3 }; "
                "[Console]::Out.Write($process.CommandLine)"
            ),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    command_line = completed.stdout.strip()
    if completed.returncode != 0 or not command_line:
        raise RuntimeError(
            f"cannot read command line for process PID {process_pid}: "
            f"exit={completed.returncode} stderr={completed.stderr.strip()}"
        )
    return command_line


def _expected_windows_child_image_path(command_executable: str | Path) -> Path:
    command_path = Path(command_executable)
    if command_path.suffix.casefold() in {".bat", ".cmd"}:
        command_shell = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
        if not command_shell:
            raise RuntimeError("Windows command shell executable is unavailable")
        return Path(command_shell).resolve()
    resolved = shutil.which(str(command_executable))
    return Path(resolved or command_executable).resolve()


def _same_windows_executable_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
        str(Path(right).resolve())
    )


@unittest.skipUnless(
    os.environ.get("RUN_TRACERELAY_REAL_ACCEPTANCE"),
    "set RUN_TRACERELAY_REAL_ACCEPTANCE=1 to run the traced App Server acceptance",
)
class TracedAppServerRealIntegrationTests(unittest.TestCase):
    def test_planning_and_per_turn_execution_control_planes(self) -> None:
        tracerelay_command = resolve_tracerelay_command(
            os.environ.get("TRACERELAY_PYTHON")
        )
        initial = subprocess.run(
            [*tracerelay_command, "status"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=15,
        )
        initial_raw = initial.stdout.strip() or initial.stderr.strip()
        initial_status = json.loads(initial_raw.decode("utf-8", errors="replace"))
        if initial_status.get("state") != "NOT_RUNNING":
            self.skipTest("TraceRelay is already running; ownership is ambiguous")
        codex_identity = _capture_codex_cli_identity(
            aegis_runtime.default_app_server_command()[0]
        )
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
        runtime_root = root / "runtime"
        artifact_path = runtime_root / "runs" / run_id / "artifacts"
        source = project / "src" / "acceptance_target.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("ACCEPTANCE_TARGET = True\n", encoding="utf-8")
        test_runner = project / "test" / "acceptance_test.py"
        test_runner.parent.mkdir(parents=True, exist_ok=True)
        test_runner.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(project.resolve())!r})\n"
            "from src.acceptance_target import ACCEPTANCE_TARGET\n"
            "print(ACCEPTANCE_TARGET)\n"
            "raise SystemExit(0 if ACCEPTANCE_TARGET is True else 1)\n",
            encoding="utf-8",
        )
        _write_production_runtime_fixture(project)
        engineering_manifest = write_test_engineering_input_manifest(project)
        write_test_runtime_scope_policy(project)
        head = initialize_test_git_repository(project, "pilot fixture")
        seal = record_project_seal(
            project,
            git_head_before_record=head,
            project_id=bytes(range(16)),
            seal_chain_id=bytes(range(16, 32)),
        )
        context_path = root / "inputs" / "REASONING_LEDGER_CONTEXT_PACK.json"
        engineering = validate_engineering_input_manifest(
            engineering_manifest,
            project_root=project,
            project_id_hex=bytes(range(16)).hex(),
        )
        write_test_reasoning_context_pack(
            project,
            context_path,
            project_id_hex=bytes(range(16)).hex(),
            project_seal=seal.expected_seal,
            engineering_documents_sha256=engineering.documents_sha256,
        )
        live_snapshot = json.loads(
            (
                project
                / ".aegis"
                / "reasoning_ledger"
                / "test-live-snapshot.json"
            ).read_text(encoding="utf-8")
        )
        ledger_patch = patch.object(
            aegis_runtime,
            "export_live_reasoning_ledger_snapshot",
            return_value=live_snapshot,
        )
        ledger_patch.start()
        self.addCleanup(ledger_patch.stop)
        expected = {
            "artifact_path": str(artifact_path),
            "reasoning_ledger_context_pack": str(context_path),
            "status": True,
        }
        executable = Path(sys._base_executable).resolve()
        source_bytes = source.read_bytes()
        executable_bytes = executable.read_bytes()
        test_runner_bytes = test_runner.read_bytes()
        execution_policy = {
            "schema": "aegis.test_execution_policy.v2",
            "tests": [
                {
                    "test_id": "T-001",
                    "requirement_ids": ["R-001"],
                    "command": [
                        str(executable),
                        "-B",
                        str(test_runner.resolve()),
                    ],
                    "cwd": str(project.resolve()),
                    "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
                    "timeout_seconds": 30,
                    "test_inputs": [
                        {
                            "path": str(source.resolve()),
                            "size": len(source_bytes),
                            "sha256": hashlib.sha256(source_bytes).hexdigest(),
                        },
                        {
                            "path": str(test_runner.resolve()),
                            "size": len(test_runner_bytes),
                            "sha256": hashlib.sha256(test_runner_bytes).hexdigest(),
                        }
                    ],
                    "executable": {
                        "path": str(executable),
                        "size": len(executable_bytes),
                        "sha256": hashlib.sha256(executable_bytes).hexdigest(),
                    },
                }
            ],
        }
        execution_policy_json = json.dumps(
            execution_policy, ensure_ascii=False, sort_keys=True
        )
        relay = TraceRelayClient(
            command=tracerelay_command,
            monitor_interval_seconds=0.05,
        )
        coordinator = RuntimeCoordinator(
            project_root=project,
            artifact_path=artifact_path,
            runtime_root=runtime_root,
            run_id=run_id,
            upstream_port=int(os.environ.get("TRACERELAY_UPSTREAM_PORT", "7899")),
            relay_client=relay,
            start_node="A",
            engineering_input_manifest_path=engineering_manifest,
        )
        owned = False
        try:
            coordinator.preflight()
            owned = True
            planning_instructions = {
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
            coordinator.prepare_planning_agents(planning_instructions)
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
                        "fixture fact is that src/acceptance_target.py contains exactly the one "
                        "side-effect-free line `ACCEPTANCE_TARGET = True`. In this fixture, "
                        "The authoritative test is the exact argv/cwd/environment policy below. "
                        "PASS requires completion within 30 seconds and exit code 0. Stdout "
                        "exactly one `True` line and empty stderr are expected evidence, not extra "
                        "pass gates. The plan must state cwd, argv, input, timeout, evidence paths, "
                        "and the complete pass/fail rule. It must embed the exact policy between "
                        "the two marker lines shown below so the Coordinator can execute it:\n"
                        "<!-- AEGIS_TEST_EXECUTION_POLICY_BEGIN -->\n"
                        f"{execution_policy_json}\n"
                        "<!-- AEGIS_TEST_EXECUTION_POLICY_END -->\n"
                        "These are the complete "
                        "authoritative synthetic requirements; do not add other witnesses or "
                        "constraints. Address every prior review item when present. Then return "
                        f"exactly this JSON object: {expected_json}\n"
                        f"CONTROL={json.dumps(author_control, ensure_ascii=False)}"
                    ),
                    output_schema=NODE_SCHEMA,
                    developer_instructions=planning_instructions[
                        "TEST_PLAN_AUTHOR"
                    ],
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
                        "verdict; model status does not control routing. Set artifact_path "
                        f"exactly to {artifact_path} and reasoning_ledger_context_pack exactly "
                        f"to {review_control['context_pack_path']}.\n"
                        f"CONTROL={json.dumps(review_control, ensure_ascii=False)}"
                    ),
                    output_schema=REVIEW_NODE_SCHEMA,
                    developer_instructions=planning_instructions[
                        "TEST_PLAN_REVIEWER"
                    ],
                    job_id=str(review_control["job_id"]),
                )
                reviewer_output = complete_reviewer_model_output(
                    json.loads(reviewer_raw)
                )
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
                    "Persistent synthetic test executor. Inspect only the Coordinator-provided "
                    "test execution request and any explicitly requested continuity file. Do "
                    "not execute tests or create Coordinator-owned evidence. Do not use "
                    "Aegis-specific skills. Return only schema-valid JSON."
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
            ) -> dict[str, object]:
                def operation(input_state: dict[str, object]) -> dict[str, object]:
                    if node == "C":
                        attempt = coordinator._active_execution_attempt
                        assert attempt is not None
                        assert coordinator._seal is not None
                        write_test_execution_request(
                            project,
                            artifact_path,
                            project_id_hex=coordinator._seal.project_id.hex(),
                            workflow_run_id=coordinator.run_id,
                            attempt_id=str(attempt["attempt_id"]),
                        )
                        control = coordinator.test_execution_control()
                    else:
                        control = coordinator.execution_node_control()
                    node_message = {
                        "artifact_path": input_state["artifact_path"],
                        "reasoning_ledger_context_pack": input_state[
                            "reasoning_ledger_context_pack"
                        ],
                    }
                    turn_prompt = (
                        prompt
                        + "\nNODE_MESSAGE="
                        + json.dumps(node_message, ensure_ascii=False)
                        + "\nCONTROL="
                        + json.dumps(control, ensure_ascii=False)
                    )
                    raw = coordinator.run_execution_agent(
                        role,
                        turn_prompt,
                        output_schema=(
                            execution_reviewer_output_schema(role)
                            if node in {"D", "F"}
                            else execution_output_schema()
                        ),
                        developer_instructions=execution_instructions[role],
                        timeout_seconds=1_800,
                    )
                    output = json.loads(raw)
                    if node in {"D", "F"}:
                        output = complete_reviewer_model_output(output)
                        validated = validate_reviewer_envelope(
                            role, input_state, output
                        )
                        contract_role = (
                            REVIEW_CONTRACT_TEST_RESULT_REVIEWER
                            if node == "D"
                            else REVIEW_CONTRACT_FINAL_REVIEWER
                        )
                        review_stage = coordinator_review_stage(
                            contract_role, validated
                        )
                        node_output = {
                            **validated,
                            "coordinator_review_stage": review_stage,
                            "status": (
                                review_stage == "TEST_REPORTING"
                                if node == "D"
                                else validated["review_conclusion"] == "PASS"
                            ),
                        }
                    else:
                        require_control_envelope_unchanged(
                            node, input_state, output
                        )
                        self.assertIs(output["status"], True)
                        node_output = output
                    return {**input_state, **node_output, "current_node": node}

                return coordinator.execute_node(node, operation, node_state)

            execution_state = {
                **expected,
                "reasoning_ledger_context_pack": str(
                    review_control["context_pack_path"]
                ),
            }
            first_c = execute_turn(
                "C",
                "TEST_EXECUTOR",
                (
                    "Read CONTROL.request_path without changing it. Do not execute its tests; "
                    "the Coordinator executes them after this turn. Return NODE_MESSAGE fields, "
                    "status=true, and output_artifacts containing exactly one descriptor with "
                    "artifact_id=test-execution-request, the exact absolute CONTROL.request_path, "
                    "and its actual positive byte size and lowercase SHA-256. Remember marker "
                    "C-PERSISTENT-THREAD for your next turn."
                ),
                execution_state,
            )
            first_d = execute_turn(
                "D",
                "TEST_RESULT_REVIEWER",
                (
                    "Audit every descriptor in CONTROL.test_evidence_manifests and the files "
                    "they bind. Write artifact_path/TEST_RESULT_REVIEW.md. For this first review "
                    "round deliberately request one retest: return review_conclusion=FAIL, "
                    "one EXECUTION_INCOMPLETE evidence-backed finding, "
                    "and review_output_artifacts containing exactly one test-result-review "
                    "descriptor for TEST_RESULT_REVIEW.md with its actual size and SHA-256. "
                    "The Coordinator derives finding categories. Preserve both NODE_MESSAGE "
                    "paths exactly."
                ),
                first_c,
            )
            self.assertIs(first_d["status"], False)
            second_c = execute_turn(
                "C",
                "TEST_EXECUTOR",
                (
                    "This is a second turn on your persistent role. Write only the marker you "
                    "were told to remember to artifact_path/THREAD_CONTINUITY.txt. Read the new "
                    "CONTROL.request_path without changing it and do not execute its tests. "
                    "Return NODE_MESSAGE fields, status=true, and output_artifacts containing "
                    "exactly one test-execution-request descriptor for CONTROL.request_path "
                    "with its actual positive byte size and lowercase SHA-256."
                ),
                first_d,
            )
            second_d = execute_turn(
                "D",
                "TEST_RESULT_REVIEWER",
                (
                    "This is the second review turn on your persistent role. Re-read "
                    "every manifest in CONTROL.test_evidence_manifests and its bound evidence. "
                    "Accept only when the authoritative test records stdout True and exit code "
                    "0. Overwrite artifact_path/TEST_RESULT_REVIEW.md with the complete accepted "
                    "review. Return review_conclusion=PASS, empty findings, "
                    "and exactly one test-result-review descriptor for the report with actual "
                    "size and SHA-256. Preserve both NODE_MESSAGE paths exactly."
                ),
                second_c,
            )
            self.assertIs(second_d["status"], True)
            reported = execute_turn(
                "E",
                "TEST_REPORT_WRITER",
                (
                    "Read every descriptor in CONTROL.test_evidence_manifests and its bound "
                    "evidence, then write artifact_path/TEST_REPORT.md. It must state stdout "
                    "True, exit code 0, and PASS. Return NODE_MESSAGE fields, status=true, and "
                    "output_artifacts containing exactly one test-report descriptor for "
                    "TEST_REPORT.md with its actual positive byte size and lowercase SHA-256."
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
                    "Independently audit project_root/src/acceptance_target.py, the reasoning "
                    "ledger context pack, artifact_path/TEST_REPORT.md, "
                    "and every Coordinator-owned test evidence manifest in CONTROL. Accept "
                    "only when code, reasoning facts, test evidence, "
                    "and report consistently bind stdout True and exit code 0 to PASS. Write "
                    "artifact_path/FINAL_REVIEW.md with verdict PASS, explicit reasons, and the "
                    f"exact report SHA-256 {report_sha256}. Also write "
                    "artifact_path/FINAL_REVIEW_VERDICT.json as a JSON object with exactly: "
                    f"schema=`aegis.final_review_verdict.v1`, workflow_run_id=`{run_id}`, "
                    "verdict=`PASS`, a non-empty conclusion, a non-empty reasons string array, "
                    "and a non-empty evidence_index. Every evidence_index item must contain "
                    "exactly evidence_id, absolute path, actual byte size, and actual lowercase "
                    "SHA-256. Read artifact_path/FINAL_REVIEW_INPUT_MANIFEST.json. Audit every "
                    "entry in its required_evidence array and copy every descriptor byte-for-byte "
                    "into evidence_index. Then add exact descriptors with evidence IDs "
                    "final-review-input-manifest and final-review for the input manifest and "
                    "FINAL_REVIEW.md. Compute those two descriptors only after both files are "
                    "durable. Omitting any Coordinator-required descriptor is a failure. Return "
                    "review_conclusion=PASS, empty findings, and "
                    "review_output_artifacts containing exactly final-review and "
                    "final-review-verdict descriptors for those two output files with actual "
                    "sizes and SHA-256 values. Preserve both NODE_MESSAGE paths exactly."
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
            response_root = (artifact_path / "responses").resolve()
            self.assertTrue(
                all(
                    Path(item["raw_response_path"])
                    .resolve()
                    .is_relative_to(response_root)
                    for item in [*state["planning_turns"], *execution_turns]
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
            final_input_path = artifact_path / "FINAL_REVIEW_INPUT_MANIFEST.json"
            final_input = json.loads(final_input_path.read_text(encoding="utf-8"))
            final_verdict = json.loads(
                (artifact_path / "FINAL_REVIEW_VERDICT.json").read_text(
                    encoding="utf-8"
                )
            )
            required_ids = {
                item["evidence_id"] for item in final_input["required_evidence"]
            } | {"final-review-input-manifest", "final-review"}
            verdict_ids = {
                item["evidence_id"] for item in final_verdict["evidence_index"]
            }
            self.assertTrue(required_ids.issubset(verdict_ids))
            self.assertTrue(
                any(item.startswith("project-runtime:") for item in required_ids)
            )
            self.assertIn("test-report", required_ids)
            self.assertIn("reasoning-context-pack", required_ids)
            self.assertTrue(
                any(item.startswith("test-evidence-manifest:") for item in required_ids)
            )
            self.assertEqual(
                len(
                    [
                        item
                        for item in required_ids
                        if item.startswith("planning-response:")
                    ]
                ),
                len(state["planning_turns"]),
            )
            self.assertEqual(
                len(
                    [
                        item
                        for item in required_ids
                        if item.startswith("planning-instruction-receipt:")
                    ]
                ),
                len(state["planning_turns"]),
            )
            self.assertTrue((artifact_path / "TEST_REPORT.md").read_bytes().strip())
            self.assertTrue((artifact_path / "FINAL_REVIEW.md").read_bytes().strip())

            report = {
                "schema": CONTROL_PLANE_REPORT_SCHEMA,
                "verdict": "PASS",
                "created_at_utc": stamp,
                "run_id": run_id,
                "runtime_root": str(runtime_root),
                "artifact_path": str(artifact_path),
                "run_state_path": str(coordinator.run_state_path),
                **_control_plane_codex_identity(state, codex_identity),
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
                "tracerelay_command": list(tracerelay_command),
                "tracerelay_python_sha256": hashlib.sha256(
                    Path(tracerelay_command[0]).read_bytes()
                ).hexdigest(),
                "source_sha256": _source_sha256(
                    *AEGIS_SOURCE_BINDINGS,
                    "test/test_traced_app_server_real_integration.py",
                    *TRACERELAY_SOURCE_BINDINGS,
                ),
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
                _stop_test_runtime(tracerelay_command)

    def test_hard_crash_cleans_exact_session_and_terminates_original_run(self) -> None:
        tracerelay_command = resolve_tracerelay_command(
            os.environ.get("TRACERELAY_PYTHON")
        )
        initial = subprocess.run(
            [*tracerelay_command, "status"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=15,
        )
        initial_raw = initial.stdout.strip() or initial.stderr.strip()
        initial_status = json.loads(initial_raw.decode("utf-8", errors="replace"))
        if initial_status.get("state") != "NOT_RUNNING":
            self.skipTest("TraceRelay is already running; ownership is ambiguous")
        codex_identity = _capture_codex_cli_identity(
            aegis_runtime.default_app_server_command()[0]
        )

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
        _write_production_runtime_fixture(project)
        write_test_runtime_scope_policy(project)
        head = initialize_test_git_repository(project, "crash fixture")
        record_project_seal(
            project,
            git_head_before_record=head,
            project_id=bytes(range(16)),
            seal_chain_id=bytes(range(16, 32)),
        )
        context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        artifact_path.mkdir(parents=True, exist_ok=True)
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
        worker_pycache = _shared_worker_pycache(root / "worker-pycache")
        # Initial status proved that no pre-existing runtime exists. Claim cleanup
        # responsibility before the crash worker starts so pre-checkpoint failures
        # cannot leak a relay and suppress the remaining acceptance cases.
        owned = True
        coordinator: RuntimeCoordinator | None = None
        try:
            crashed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-X",
                    f"pycache_prefix={worker_pycache}",
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
            state_path = artifact_path / "runs" / run_id / "RUN_STATE.json"
            interrupted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                interrupted["codex_cli_path"], codex_identity["codex_cli_path"]
            )
            self.assertEqual(
                interrupted["codex_cli_version"], codex_identity["codex_cli_version"]
            )
            _validate_current_codex_cli_identity(codex_identity)
            self.assertEqual(interrupted["execution_turns"][0]["status"], "inProgress")
            old_evidence = next(
                entry
                for entry in interrupted["evidence_sessions"]
                if entry["node"] == "C"
            )
            self.assertEqual(old_evidence["verification_status"], "UNVERIFIED")
            self.assertIsNone(old_evidence["application_verification_status"])
            self.assertGreater(old_evidence["process_creation_time_100ns"], 0)

            live_snapshot = json.loads(
                (
                    project
                    / ".aegis"
                    / "reasoning_ledger"
                    / "test-live-snapshot.json"
                ).read_text(encoding="utf-8")
            )
            ledger_patch = patch.object(
                aegis_runtime,
                "export_live_reasoning_ledger_snapshot",
                return_value=live_snapshot,
            )
            ledger_patch.start()
            self.addCleanup(ledger_patch.stop)
            recovery_commands: list[list[str]] = []

            def recording_cli_runner(
                command: list[str], timeout: float
            ) -> subprocess.CompletedProcess[str]:
                recovery_commands.append(command[len(tracerelay_command) :])
                return subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    check=False,
                    timeout=timeout,
                )

            relay = TraceRelayClient(
                command=tracerelay_command,
                cli_runner=recording_cli_runner,
                monitor_interval_seconds=0.05,
            )
            coordinator = RuntimeCoordinator(
                project_root=project,
                artifact_path=artifact_path,
                run_id=run_id,
                upstream_port=upstream_port,
                relay_client=relay,
                start_node="C",
                prior_state=interrupted,
            )
            with self.assertRaisesRegex(
                aegis_runtime.FreezeContinuityLostError,
                "cannot resume safely",
            ):
                coordinator.preflight()

            completed = json.loads(state_path.read_text(encoding="utf-8"))
            receipt = completed["execution_turns"][0]
            evidence = completed["evidence_sessions"]
            execution_evidence = [
                entry for entry in evidence if entry["node"] == "C"
            ]
            self.assertEqual(completed["status"], "terminated")
            self.assertEqual(
                completed["termination_reason_code"],
                "FREEZE_CONTINUITY_LOST",
            )
            self.assertEqual(receipt["status"], "inProgress")
            self.assertEqual(
                receipt["evidence_session_ids"],
                [old_evidence["session_id"]],
            )
            self.assertEqual(len(execution_evidence), 1)
            recovered_execution_evidence = execution_evidence[0]
            self.assertEqual(
                recovered_execution_evidence["verification_status"],
                "VALID_COMPLETE",
            )
            self.assertEqual(
                recovered_execution_evidence["application_verification_status"],
                "INVALID",
            )
            process_pids = [int(recovered_execution_evidence["process_pid"])]
            process_creation_times = [
                int(recovered_execution_evidence["process_creation_time_100ns"])
            ]
            self.assertFalse(_windows_process_is_running(process_pids[0]))
            invoked_commands = [command[0] for command in recovery_commands]
            self.assertNotIn("start", invoked_commands)
            self.assertNotIn("register", invoked_commands)
            self.assertIn("verify", invoked_commands)
            report = {
                "schema": "aegis.execution_crash_cleanup_acceptance.v4",
                "verdict": "PASS",
                "run_id": run_id,
                "worker_exit_code": crashed.returncode,
                "codex_thread_id": receipt["codex_thread_id"],
                "codex_turn_id": receipt["codex_turn_id"],
                "evidence_session_ids": receipt["evidence_session_ids"],
                "process_pids": process_pids,
                "process_creation_times_100ns": process_creation_times,
                "processes_terminated": True,
                "application_verification_status": "INVALID",
                "final_run_status": completed["status"],
                "termination_reason_code": completed["termination_reason_code"],
                "recovery_cli_commands": recovery_commands,
                "new_execution_session_started": False,
                "tracerelay_command": list(tracerelay_command),
                "tracerelay_python_sha256": hashlib.sha256(
                    Path(tracerelay_command[0]).read_bytes()
                ).hexdigest(),
                **codex_identity,
                "source_sha256": _source_sha256(
                    *AEGIS_SOURCE_BINDINGS,
                    "test/test_traced_app_server_real_integration.py",
                    *TRACERELAY_SOURCE_BINDINGS,
                ),
            }
            report_path = root / "CRASH_RECOVERY_REPORT.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"CRASH_RECOVERY_REPORT={report_path}")
        finally:
            if owned:
                _stop_test_runtime(tracerelay_command)

    def test_registration_intent_recovers_both_real_pre_checkpoint_crashes(
        self,
    ) -> None:
        tracerelay_command = resolve_tracerelay_command(
            os.environ.get("TRACERELAY_PYTHON")
        )

        def run_cli(*arguments: str) -> tuple[int, dict[str, object]]:
            completed = subprocess.run(
                [*tracerelay_command, *arguments],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=30,
            )
            raw = completed.stdout.strip() or completed.stderr.strip()
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            self.assertIsInstance(payload, dict)
            return completed.returncode, payload

        _returncode, initial_status = run_cli("status")
        if initial_status.get("state") != "NOT_RUNNING":
            self.skipTest("TraceRelay is already running; ownership is ambiguous")
        codex_identity = _capture_codex_cli_identity(
            aegis_runtime.default_app_server_command()[0]
        )

        short_id = uuid4().hex[:12]
        root = (
            Path(
                os.environ.get(
                    "AEGIS_APP_SERVER_ACCEPTANCE_ROOT", r"C:\code\aegis_artifacts"
                )
            )
            / "as_registration_crash"
            / short_id
        ).resolve()
        project = root / "project"
        source = project / "src" / "acceptance_target.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("ACCEPTANCE_TARGET = True\n", encoding="utf-8")
        _write_production_runtime_fixture(project)
        write_test_runtime_scope_policy(project)
        head = initialize_test_git_repository(project, "registration fixture")
        record_project_seal(
            project,
            git_head_before_record=head,
            project_id=bytes(range(16)),
            seal_chain_id=bytes(range(16, 32)),
        )
        upstream_port = int(os.environ.get("TRACERELAY_UPSTREAM_PORT", "7899"))
        def run_case(crash_mode: str) -> dict[str, object]:
            if crash_mode in REQUIRED_REGISTRATION_CRASH_MODES:
                run_id = f"registration-{crash_mode}-{short_id}"
                artifact_path = root / crash_mode / "artifacts"
                artifact_path.mkdir(parents=True, exist_ok=True)
                context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
                state = {
                    "artifact_path": str(artifact_path),
                    "reasoning_ledger_context_pack": str(context_path),
                    "status": True,
                }
                marker_path = root / crash_mode / "CRASH_MARKER.json"
                expected_child_image_path = _expected_windows_child_image_path(
                    aegis_runtime.default_app_server_command()[0]
                )
                config = {
                    "crash_mode": crash_mode,
                    "marker_path": str(marker_path),
                    "project": str(project),
                    "artifact_path": str(artifact_path),
                    "run_id": run_id,
                    "upstream_port": upstream_port,
                    "tracerelay_command": tracerelay_command,
                    "expected_child_image_path": str(expected_child_image_path),
                    "state": state,
                    "prompt": (
                        "Return exactly one JSON object matching the output schema. "
                        f"Preserve artifact_path as {artifact_path} and "
                        "reasoning_ledger_context_pack as "
                        f"{context_path}; set status to true. Do not use tools."
                    ),
                    "developer_instructions": (
                        "Return only schema-valid JSON for the registration crash "
                        "acceptance. Do not use Aegis-specific skills."
                    ),
                }
                config_path = root / crash_mode / "CRASH_WORKER_CONFIG.json"
                config_path.write_text(
                    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                worker_pycache = _shared_worker_pycache(
                    root / crash_mode / "worker-pycache"
                )

                try:
                    crashed = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            "-X",
                            f"pycache_prefix={worker_pycache}",
                            str(Path(__file__).resolve()),
                            "--registration-crash-worker",
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
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    self.assertEqual(marker["crash_mode"], crash_mode)
                    self.assertEqual(
                        marker["popen_started"],
                        crash_mode == "after_popen_before_identity_checkpoint",
                    )
                    observed_process_terminated: bool | None = None
                    observed_child_terminated: bool | None = None
                    observed_descendants_terminated: bool | None = None
                    frozen_job_members_terminated: bool | None = None
                    if marker["popen_started"]:
                        observed_process_pid = int(marker["observed_process_pid"])
                        observed_process_creation_time = int(
                            marker["observed_process_creation_time_100ns"]
                        )
                        observed_child_pid = int(marker["observed_child_pid"])
                        observed_child_creation_time = int(
                            marker["observed_child_creation_time_100ns"]
                        )
                        descendant_identities = [
                            (
                                int(item["pid"]),
                                int(item["creation_time_100ns"]),
                            )
                            for item in marker["observed_descendant_processes"]
                        ]
                        frozen_job_member_identities = [
                            (
                                int(item["pid"]),
                                int(item["creation_time_100ns"]),
                            )
                            for item in marker["frozen_job_member_processes"]
                        ]
                        self.assertIs(
                            marker["observed_process_active_before_crash"], True
                        )
                        self.assertIs(
                            marker["observed_child_active_before_crash"], True
                        )
                        deadline = time.monotonic() + 10
                        while (
                            (
                                _windows_process_identity_is_running(
                                    observed_process_pid,
                                    observed_process_creation_time,
                                )
                                or _windows_process_identity_is_running(
                                    observed_child_pid,
                                    observed_child_creation_time,
                                )
                                or any(
                                    _windows_process_identity_is_running(pid, created)
                                    for pid, created in descendant_identities
                                )
                                or any(
                                    _windows_process_identity_is_running(pid, created)
                                    for pid, created in frozen_job_member_identities
                                )
                            )
                            and time.monotonic() < deadline
                        ):
                            time.sleep(0.05)
                        observed_process_terminated = not (
                            _windows_process_identity_is_running(
                                observed_process_pid,
                                observed_process_creation_time,
                            )
                        )
                        observed_child_terminated = not (
                            _windows_process_identity_is_running(
                                observed_child_pid,
                                observed_child_creation_time,
                            )
                        )
                        observed_descendants_terminated = not any(
                            _windows_process_identity_is_running(pid, created)
                            for pid, created in descendant_identities
                        )
                        frozen_job_members_terminated = not any(
                            _windows_process_identity_is_running(pid, created)
                            for pid, created in frozen_job_member_identities
                        )
                        self.assertTrue(observed_process_terminated)
                        self.assertTrue(observed_child_terminated)
                        self.assertTrue(observed_descendants_terminated)
                        self.assertTrue(frozen_job_members_terminated)

                    state_path = (
                        artifact_path
                        / "runs"
                        / run_id
                        / "RUN_STATE.json"
                    )
                    interrupted = json.loads(state_path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        interrupted["codex_cli_path"],
                        codex_identity["codex_cli_path"],
                    )
                    self.assertEqual(
                        interrupted["codex_cli_version"],
                        codex_identity["codex_cli_version"],
                    )
                    _validate_current_codex_cli_identity(codex_identity)
                    intent = interrupted["registration_intent"]
                    receipt = interrupted["execution_turns"][0]
                    self.assertEqual(intent["run_id"], run_id)
                    self.assertEqual(intent["node"], "C")
                    self.assertEqual(intent["attempt_id"], receipt["attempt_id"])
                    self.assertEqual(intent["job_id"], receipt["job_id"])
                    self.assertEqual(receipt["status"], "preparing")
                    self.assertEqual(receipt["evidence_session_ids"], [])
                    self.assertEqual(
                        [
                            entry
                            for entry in interrupted["evidence_sessions"]
                            if entry["node"] == "C"
                        ],
                        [],
                    )

                    resolver = TraceRelayClient(
                        command=tracerelay_command,
                        monitor_interval_seconds=0.05,
                    )
                    registration = resolver.resolve_registration_operation(
                        intent["operation_id"]
                    )
                    self.assertIsNotNone(registration)
                    assert registration is not None
                    self.assertEqual(registration.operation_id, intent["operation_id"])
                    metadata = json.loads(
                        (registration.session_path / "session.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(metadata["operation_id"], intent["operation_id"])

                    recovery_commands: list[list[str]] = []

                    def recording_cli_runner(
                        command: list[str], timeout: float
                    ) -> subprocess.CompletedProcess[str]:
                        recovery_commands.append(
                            command[len(tracerelay_command) :]
                        )
                        return subprocess.run(
                            command,
                            stdin=subprocess.DEVNULL,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="strict",
                            check=False,
                            timeout=timeout,
                        )

                    live_snapshot = json.loads(
                        (
                            project
                            / ".aegis"
                            / "reasoning_ledger"
                            / "test-live-snapshot.json"
                        ).read_text(encoding="utf-8")
                    )
                    ledger_patch = patch.object(
                        aegis_runtime,
                        "export_live_reasoning_ledger_snapshot",
                        return_value=live_snapshot,
                    )
                    ledger_patch.start()
                    self.addCleanup(ledger_patch.stop)
                    recovery = RuntimeCoordinator(
                        project_root=project,
                        artifact_path=artifact_path,
                        run_id=run_id,
                        upstream_port=upstream_port,
                        relay_client=TraceRelayClient(
                            command=tracerelay_command,
                            cli_runner=recording_cli_runner,
                            monitor_interval_seconds=0.05,
                        ),
                        start_node="C",
                        prior_state=interrupted,
                    )
                    with self.assertRaisesRegex(
                        aegis_runtime.FreezeContinuityLostError,
                        "cannot resume safely",
                    ):
                        recovery.preflight()

                    invoked_commands = [command[0] for command in recovery_commands]
                    self.assertNotIn("start", invoked_commands)
                    self.assertNotIn("register", invoked_commands)
                    self.assertIn("resolve-registration", invoked_commands)
                    self.assertIn("verify", invoked_commands)

                    recovered = json.loads(state_path.read_text(encoding="utf-8"))
                    self.assertEqual(recovered["status"], "terminated")
                    self.assertEqual(
                        recovered["termination_reason_code"],
                        "FREEZE_CONTINUITY_LOST",
                    )
                    self.assertIsNone(recovered["registration_intent"])
                    recovered_receipt = recovered["execution_turns"][0]
                    recovered_evidence = [
                        entry
                        for entry in recovered["evidence_sessions"]
                        if entry["node"] == "C"
                    ]
                    self.assertEqual(
                        recovered_receipt["evidence_session_ids"],
                        [registration.session_id],
                    )
                    self.assertEqual(len(recovered_evidence), 1)
                    evidence = recovered_evidence[0]
                    self.assertEqual(evidence["session_id"], registration.session_id)
                    self.assertEqual(
                        evidence["registration_operation_id"], intent["operation_id"]
                    )
                    self.assertEqual(
                        evidence["application_verification_status"], "INVALID"
                    )
                    self.assertIsNone(evidence["process_pid"])
                    self.assertIsNone(evidence["process_creation_time_100ns"])
                    verification_returncode, verification = run_cli(
                        "verify", str(registration.session_path)
                    )
                    self.assertEqual(verification_returncode, 0)
                    self.assertEqual(verification["status"], "VALID_COMPLETE")

                    _returncode, recovered_status = run_cli("status")
                    self.assertEqual(recovered_status["state"], "IDLE")
                    return {
                        "crash_mode": crash_mode,
                        "worker_exit_code": crashed.returncode,
                        "operation_id": intent["operation_id"],
                        "session_id": registration.session_id,
                        "session_path": str(registration.session_path),
                        "marker": marker,
                        "recovery_cli_commands": recovery_commands,
                        "verification": verification,
                        "application_verification_status": "INVALID",
                        "final_run_status": recovered["status"],
                        "termination_reason_code": recovered[
                            "termination_reason_code"
                        ],
                        "persisted_process_pid": evidence["process_pid"],
                        "persisted_process_creation_time_100ns": evidence[
                            "process_creation_time_100ns"
                        ],
                        "observed_process_terminated": observed_process_terminated,
                        "observed_child_terminated": observed_child_terminated,
                        "observed_descendants_terminated": (
                            observed_descendants_terminated
                        ),
                        "frozen_job_members_terminated": (
                            frozen_job_members_terminated
                        ),
                        **codex_identity,
                    }
                finally:
                    _stop_test_runtime(tracerelay_command)
            raise AssertionError(f"unsupported registration crash mode: {crash_mode}")

        cases = _collect_registration_crash_cases(run_case)
        report_path = root / "REGISTRATION_CRASH_REPORT.json"
        _publish_registration_crash_report(
            report_path,
            cases=cases,
            tracerelay_command=tracerelay_command,
        )
        print(f"REGISTRATION_CRASH_REPORT={report_path}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--execution-crash-worker":
        _run_execution_crash_worker(Path(sys.argv[2]).resolve())
    elif len(sys.argv) == 3 and sys.argv[1] == "--registration-crash-worker":
        _run_registration_crash_worker(Path(sys.argv[2]).resolve())
    else:
        unittest.main()
