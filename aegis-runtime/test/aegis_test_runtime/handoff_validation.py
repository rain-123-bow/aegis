from __future__ import annotations

import json
import os
import platform
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TestHandoffValidationError(RuntimeError):
    """Raised when Phase 20A Test handoff validation fails before test execution."""


@dataclass(frozen=True)
class TestHandoffValidationRequest:
    run_id: str
    handoff_kind: str
    target: str
    status: str
    target_repo: Path
    base_branch: str
    integration_branch: str
    integration_commit: str
    changed_files: list[str]
    group_mapping: list[dict[str, Any]]
    test_command: list[str]

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, default_test_command: list[str] | None = None) -> "TestHandoffValidationRequest":
        if not isinstance(value, dict):
            raise TestHandoffValidationError("handoff package must be an object")
        test_command = value.get("test_command") or value.get("test_commands")
        if isinstance(test_command, str):
            test_command_list = shlex.split(test_command, posix=os.name != "nt")
        elif isinstance(test_command, list) and all(isinstance(item, str) for item in test_command):
            test_command_list = list(test_command)
        else:
            test_command_list = list(default_test_command or [sys.executable, "-m", "pytest", "-vv"])
        group_mapping = value.get("group_mapping", [])
        if not isinstance(group_mapping, list) or any(not isinstance(item, dict) for item in group_mapping):
            raise TestHandoffValidationError("group_mapping must be a list of objects")
        return cls(
            run_id=_require_string(value.get("run_id"), "run_id"),
            handoff_kind=_require_string(value.get("handoff_kind"), "handoff_kind"),
            target=_require_string(value.get("target"), "target"),
            status=_require_string(value.get("status"), "status"),
            target_repo=Path(_require_string(value.get("target_repo"), "target_repo")).resolve(),
            base_branch=_require_string(value.get("base_branch", "main"), "base_branch"),
            integration_branch=_require_string(value.get("integration_branch"), "integration_branch"),
            integration_commit=str(value.get("integration_commit", "")),
            changed_files=_ensure_string_list(value.get("changed_files", []), "changed_files"),
            group_mapping=[dict(item) for item in group_mapping],
            test_command=test_command_list,
        )


def run_test_handoff_validation(
    handoff_package: dict[str, Any] | TestHandoffValidationRequest,
    *,
    output_dir: str | Path,
    default_test_command: list[str] | None = None,
) -> dict[str, Any]:
    request = handoff_package if isinstance(handoff_package, TestHandoffValidationRequest) else TestHandoffValidationRequest.from_mapping(handoff_package, default_test_command=default_test_command)
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    _validate_handoff(request)
    _assert_git_repo(request.target_repo)
    _assert_clean_worktree(request.target_repo)

    before_branch = _git_stdout(request.target_repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    _git(request.target_repo, ["checkout", request.integration_branch])
    checked_out_commit = _git_stdout(request.target_repo, ["rev-parse", "HEAD"])
    if request.integration_commit and checked_out_commit != request.integration_commit:
        raise TestHandoffValidationError(f"integration commit mismatch: checked out {checked_out_commit}, expected {request.integration_commit}")

    changed_files = _git_stdout(request.target_repo, ["diff", "--name-only", f"{request.base_branch}..{request.integration_branch}"]).splitlines()
    missing_expected_changes = sorted(set(request.changed_files) - set(changed_files))

    test_command = _resolve_command_for_cwd(request.test_command, request.target_repo)
    command_result = subprocess.run(test_command, cwd=request.target_repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    (output_root / "command_stdout.txt").write_text(command_result.stdout, encoding="utf-8")
    (output_root / "command_stderr.txt").write_text(command_result.stderr, encoding="utf-8")

    result_label = "passed" if command_result.returncode == 0 and not missing_expected_changes else "failed"
    status = "accepted_test_handoff_validation_closure" if result_label == "passed" else "test_handoff_validation_failed"
    next_route = "final_review" if result_label == "passed" else "execution"

    reproducibility_set = {
        "run_id": request.run_id,
        "target_repo": str(request.target_repo),
        "base_branch": request.base_branch,
        "integration_branch": request.integration_branch,
        "integration_commit": checked_out_commit,
        "previous_branch": before_branch,
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": str(request.target_repo),
        "test_command": test_command,
        "environment": {"PYTHONPATH": os.environ.get("PYTHONPATH", "")},
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    artifact_manifest = {
        "artifacts": [
            {"path": "test_handoff_validation_report.json", "type": "test_report"},
            {"path": "final_test_result.json", "type": "final_test_result"},
            {"path": "reproducibility_set.json", "type": "reproducibility_set"},
            {"path": "artifact_manifest.json", "type": "artifact_manifest"},
            {"path": "command_stdout.txt", "type": "stdout"},
            {"path": "command_stderr.txt", "type": "stderr"},
        ]
    }
    final_result = {
        "run_id": request.run_id,
        "result": result_label,
        "status": "scoped_test_conclusion",
        "feedback_kind": "success" if result_label == "passed" else "failure",
        "next_route": next_route,
        "final_code_ref": checked_out_commit,
        "implementation_candidate_ref": request.integration_branch,
        "integration_branch": request.integration_branch,
        "integration_commit": checked_out_commit,
        "changed_files": changed_files,
        "covered_scope": sorted(set(changed_files) & set(request.changed_files)),
        "uncovered_scope": missing_expected_changes,
        "evidence_refs": ["command_stdout.txt", "reproducibility_set.json", "artifact_manifest.json"],
        "test_data_refs": ["test_handoff_validation_report.json", "final_test_result.json"],
        "known_limits": [
            "Phase 20A validates Test Leader handoff validation and local test evidence only.",
            "No real Test Worker Codex agent was created in this phase.",
            "No remote push, PR, merge, release, production sign-off, or global causal merge was performed.",
        ],
        "causal_status": "causal_candidate",
    }
    report = {
        "run_id": request.run_id,
        "status": status,
        "phase_boundary": "test_handoff_validation_not_real_test_worker_closure",
        "handoff_kind": request.handoff_kind,
        "target_repo": str(request.target_repo),
        "base_branch": request.base_branch,
        "integration_branch": request.integration_branch,
        "integration_commit": checked_out_commit,
        "expected_integration_commit": request.integration_commit,
        "changed_files": changed_files,
        "expected_changed_files": request.changed_files,
        "missing_expected_changes": missing_expected_changes,
        "group_mapping": request.group_mapping,
        "command": {"command": test_command, "exit_code": command_result.returncode, "stdout_path": "command_stdout.txt", "stderr_path": "command_stderr.txt"},
        "test_result": result_label,
        "next_route": next_route,
        "reproducibility_set": reproducibility_set,
        "artifact_manifest": artifact_manifest,
        "boundaries": {
            "real_test_worker_codex_agents": False,
            "source_code_modified_by_test": False,
            "remote_push": False,
            "pull_request": False,
            "remote_merge": False,
            "release": False,
            "production_sign_off": False,
            "global_causal_truth": False,
        },
    }
    _write_json(output_root / "test_handoff_validation_report.json", report)
    _write_json(output_root / "final_test_result.json", final_result)
    _write_json(output_root / "reproducibility_set.json", reproducibility_set)
    _write_json(output_root / "artifact_manifest.json", artifact_manifest)
    (output_root / "README.md").write_text(
        "# Test Phase 20A Handoff Validation Package\n\n"
        f"run_id: `{report['run_id']}`\n\nstatus: `{report['status']}`\n\n"
        f"test_result: `{report['test_result']}`\n\n"
        f"integration_branch: `{report['integration_branch']}`\n\n"
        f"integration_commit: `{report['integration_commit']}`\n\n"
        "Boundary: this package validates Test handoff against a local sandbox integration branch. "
        "It does not prove real Test Worker Codex agent closure or production CI closure.\n",
        encoding="utf-8",
    )
    return report


def _validate_handoff(request: TestHandoffValidationRequest) -> None:
    if request.handoff_kind not in {"execution_real_front_back_candidate", "execution_git_topology_candidate"}:
        raise TestHandoffValidationError(f"unsupported handoff_kind: {request.handoff_kind}")
    if request.target != "test":
        raise TestHandoffValidationError("handoff target must be test")
    if request.status != "ready_for_test_department":
        raise TestHandoffValidationError("handoff status must be ready_for_test_department")
    if not request.changed_files:
        raise TestHandoffValidationError("handoff changed_files must not be empty")
    if not request.group_mapping:
        raise TestHandoffValidationError("handoff group_mapping must not be empty")
    for path in request.changed_files:
        _assert_safe_repo_path(path)


def _assert_git_repo(repo: Path) -> None:
    if not repo.is_dir():
        raise TestHandoffValidationError(f"target repo does not exist: {repo}")
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise TestHandoffValidationError(f"target repo is not a git repository: {repo}\n{result.stderr}")


def _assert_clean_worktree(repo: Path) -> None:
    status = _git_stdout(repo, ["status", "--porcelain"])
    if status:
        raise TestHandoffValidationError(f"target repo must be clean before Test handoff validation:\n{status}")


def _git(repo: Path, args: list[str]) -> None:
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise TestHandoffValidationError(f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}")


def _git_stdout(repo: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise TestHandoffValidationError(f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}")
    return result.stdout.strip()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_command_for_cwd(command: list[str], cwd: Path) -> list[str]:
    if not command:
        raise TestHandoffValidationError("test command must not be empty")
    executable = Path(command[0])
    if not executable.is_absolute() and executable.parent != Path("."):
        candidate = (cwd / executable).resolve()
        if candidate.exists():
            return [str(candidate), *command[1:]]
    return list(command)


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TestHandoffValidationError(f"{name} must be a non-empty string")
    return value


def _ensure_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise TestHandoffValidationError(f"{name} must be a list of non-empty strings")
    return list(value)


def _assert_safe_repo_path(path: str) -> None:
    parts = Path(path).parts
    if path.startswith("/") or ".." in parts:
        raise TestHandoffValidationError(f"path must be repository-relative and safe: {path}")
