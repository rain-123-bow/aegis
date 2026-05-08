from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ExecutionGitTopologyError(RuntimeError):
    """Raised when Phase 19A git topology validation fails."""


@dataclass(frozen=True)
class FileMutation:
    path: str
    content: str = ""
    change_type: str = "modify"
    why_changed: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FileMutation":
        if not isinstance(value, dict):
            raise ExecutionGitTopologyError("file change must be an object")
        path = value.get("path")
        if not isinstance(path, str) or not path:
            raise ExecutionGitTopologyError("file change requires non-empty path")
        change_type = str(value.get("change_type", "modify"))
        if change_type not in {"add", "modify", "delete"}:
            raise ExecutionGitTopologyError("file change_type must be add, modify, or delete")
        _assert_safe_repo_path(path)
        return cls(
            path=path,
            content=str(value.get("content", "")),
            change_type=change_type,
            why_changed=str(value.get("why_changed", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content": self.content,
            "change_type": self.change_type,
            "why_changed": self.why_changed,
        }


@dataclass(frozen=True)
class GroupBranchRequest:
    group_id: str
    subtask_id: str
    branch_name: str
    responsibility: str
    local_success_criteria: list[str]
    file_changes: list[FileMutation]
    local_test_commands: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "GroupBranchRequest":
        if not isinstance(value, dict):
            raise ExecutionGitTopologyError("group entry must be an object")
        group_id = _require_string(value.get("group_id"), "group_id")
        subtask_id = _require_string(value.get("subtask_id"), "subtask_id")
        branch_name = _require_string(value.get("branch_name"), "branch_name")
        responsibility = _require_string(value.get("responsibility"), "responsibility")
        criteria = _ensure_string_list(value.get("local_success_criteria", []), "local_success_criteria")
        if not criteria:
            raise ExecutionGitTopologyError(f"group {group_id} requires local_success_criteria")
        changes = [FileMutation.from_mapping(item) for item in value.get("file_changes", [])]
        if not changes:
            raise ExecutionGitTopologyError(f"group {group_id} requires file_changes")
        return cls(
            group_id=group_id,
            subtask_id=subtask_id,
            branch_name=branch_name,
            responsibility=responsibility,
            local_success_criteria=criteria,
            file_changes=changes,
            local_test_commands=_ensure_string_list(value.get("local_test_commands", []), "local_test_commands"),
        )

    def touched_files(self) -> list[str]:
        return [item.path for item in self.file_changes]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "subtask_id": self.subtask_id,
            "branch_name": self.branch_name,
            "responsibility": self.responsibility,
            "local_success_criteria": list(self.local_success_criteria),
            "file_changes": [item.to_dict() for item in self.file_changes],
            "local_test_commands": list(self.local_test_commands),
        }


@dataclass(frozen=True)
class ExecutionGitTopologyRequest:
    run_id: str
    target_repo: Path
    base_branch: str
    integration_branch: str
    groups: list[GroupBranchRequest]
    objective: str = ""
    test_handoff_target: str = "test"

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ExecutionGitTopologyRequest":
        if not isinstance(value, dict):
            raise ExecutionGitTopologyError("request must be an object")
        run_id = _require_string(value.get("run_id"), "run_id")
        target_repo = Path(_require_string(value.get("target_repo"), "target_repo")).resolve()
        groups = [GroupBranchRequest.from_mapping(item) for item in value.get("groups", [])]
        if not groups:
            raise ExecutionGitTopologyError("request requires at least one group")
        return cls(
            run_id=run_id,
            target_repo=target_repo,
            base_branch=_require_string(value.get("base_branch", "main"), "base_branch"),
            integration_branch=_require_string(value.get("integration_branch"), "integration_branch"),
            groups=groups,
            objective=str(value.get("objective", "")),
            test_handoff_target=str(value.get("test_handoff_target", "test")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_repo": str(self.target_repo),
            "base_branch": self.base_branch,
            "integration_branch": self.integration_branch,
            "objective": self.objective,
            "test_handoff_target": self.test_handoff_target,
            "groups": [item.to_dict() for item in self.groups],
        }


def run_execution_git_topology_closure(
    request_data: dict[str, Any] | ExecutionGitTopologyRequest,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run Phase 19A local git topology closure.

    This function performs real local git branch and merge operations. It does
    not push, open PRs, release, or claim real Front/Back Codex agent closure.
    """

    request = request_data if isinstance(request_data, ExecutionGitTopologyRequest) else ExecutionGitTopologyRequest.from_mapping(request_data)
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    _validate_request(request)
    _assert_git_repo(request.target_repo)
    _assert_clean_worktree(request.target_repo)

    _git(request.target_repo, ["checkout", request.base_branch])
    base_commit = _git_stdout(request.target_repo, ["rev-parse", "HEAD"])

    group_records: list[dict[str, Any]] = []
    for group in request.groups:
        record = _run_group_branch(request=request, group=group, base_commit=base_commit)
        group_records.append(record)

    integration_record = _run_integration_branch(request=request, base_commit=base_commit, group_records=group_records)
    package = _make_test_handoff_package(
        request=request,
        base_commit=base_commit,
        group_records=group_records,
        integration_record=integration_record,
    )
    report = {
        "run_id": request.run_id,
        "status": "accepted_execution_git_topology_closure",
        "objective": request.objective,
        "target_repo": str(request.target_repo),
        "base_branch": request.base_branch,
        "base_commit": base_commit,
        "integration_branch": request.integration_branch,
        "integration_commit": integration_record["integration_commit"],
        "group_records": group_records,
        "test_handoff_package": package,
        "causal_candidate": {
            "statement": "Execution Leader produced a local git integration candidate for Test handoff.",
            "why": (
                "Every accepted independent group produced a real local group branch from the same base commit, "
                "and the Execution Leader integrated those branches into a Leader-owned integration branch."
            ),
            "evidence": [
                {"type": "git", "ref": record["commit_sha"], "relevance": f"group {record['group_id']} branch commit"}
                for record in group_records
            ]
            + [
                {
                    "type": "git",
                    "ref": integration_record["integration_commit"],
                    "relevance": "Leader-owned integration branch commit",
                }
            ],
            "scope": "Phase 19A local git topology closure only",
            "assumptions": [
                "Group file ownership was validated before branch creation.",
                "The target repository was clean before the run.",
                "No remote push, PR, merge, release, or production sign-off was performed.",
            ],
            "invalidation_conditions": [
                "A later check finds unreported merge conflicts.",
                "A group branch is found to include files outside its declared responsibility.",
                "The integration branch is pushed or merged without developer authorization.",
            ],
            "status": "causal_candidate",
        },
        "boundaries": {
            "real_front_back_codex_agents": False,
            "remote_push": False,
            "pull_request": False,
            "production_merge": False,
            "release": False,
            "global_causal_truth": False,
        },
    }

    _write_outputs(output_root=output_root, report=report, package=package, group_records=group_records)
    return report


def _run_group_branch(*, request: ExecutionGitTopologyRequest, group: GroupBranchRequest, base_commit: str) -> dict[str, Any]:
    repo = request.target_repo
    _git(repo, ["checkout", "-B", group.branch_name, base_commit])

    for change in group.file_changes:
        _apply_file_mutation(repo, change)

    if not _git_stdout(repo, ["status", "--porcelain"]):
        raise ExecutionGitTopologyError(f"group {group.group_id} produced no git changes")

    local_test_results = [_run_local_test(repo, command) for command in group.local_test_commands]

    _git(repo, ["add", "-A"])
    _git(repo, ["commit", "-m", f"execution group {group.group_id}: {group.subtask_id}"])
    commit_sha = _git_stdout(repo, ["rev-parse", "HEAD"])
    diff_files = _git_stdout(repo, ["diff", "--name-only", f"{base_commit}..{commit_sha}"]).splitlines()

    return {
        "group_id": group.group_id,
        "subtask_id": group.subtask_id,
        "branch_name": group.branch_name,
        "commit_sha": commit_sha,
        "responsibility": group.responsibility,
        "touched_files": diff_files,
        "declared_files": group.touched_files(),
        "local_success_criteria": list(group.local_success_criteria),
        "local_test_results": local_test_results,
        "status": "GROUP_BRANCH_READY_FOR_LEADER_INTEGRATION",
        "phase_boundary": "deterministic topology closure; not real Front/Back Codex agent work",
    }


def _run_integration_branch(*, request: ExecutionGitTopologyRequest, base_commit: str, group_records: list[dict[str, Any]]) -> dict[str, Any]:
    repo = request.target_repo
    _git(repo, ["checkout", "-B", request.integration_branch, base_commit])
    merge_records: list[dict[str, Any]] = []
    for record in group_records:
        branch = record["branch_name"]
        result = _run_git(repo, ["merge", "--no-ff", "--no-edit", branch])
        if result.returncode != 0:
            raise ExecutionGitTopologyError(
                "Leader integration merge failed. Conflict must be attributed; silent patching is forbidden. "
                f"branch={branch}\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        merge_records.append({"group_id": record["group_id"], "branch_name": branch})
    integration_commit = _git_stdout(repo, ["rev-parse", "HEAD"])
    changed_files = _git_stdout(repo, ["diff", "--name-only", f"{base_commit}..{integration_commit}"]).splitlines()
    return {
        "integration_branch": request.integration_branch,
        "integration_commit": integration_commit,
        "changed_files": changed_files,
        "merge_records": merge_records,
        "status": "INTEGRATION_BRANCH_READY_FOR_TEST_HANDOFF",
    }


def _make_test_handoff_package(*, request: ExecutionGitTopologyRequest, base_commit: str, group_records: list[dict[str, Any]], integration_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "handoff_kind": "execution_git_topology_candidate",
        "target": request.test_handoff_target,
        "run_id": request.run_id,
        "target_repo": str(request.target_repo),
        "base_branch": request.base_branch,
        "base_commit": base_commit,
        "integration_branch": integration_record["integration_branch"],
        "integration_commit": integration_record["integration_commit"],
        "changed_files": list(integration_record["changed_files"]),
        "group_mapping": [
            {
                "group_id": item["group_id"],
                "subtask_id": item["subtask_id"],
                "branch_name": item["branch_name"],
                "commit_sha": item["commit_sha"],
                "touched_files": list(item["touched_files"]),
            }
            for item in group_records
        ],
        "known_limits": [
            "Phase 19A validates local git topology only.",
            "Front/Back agents are deterministic or deferred in this phase.",
            "No remote push, PR, merge, release, or production sign-off was performed.",
        ],
        "status": "ready_for_test_department",
    }


def _write_outputs(*, output_root: Path, report: dict[str, Any], package: dict[str, Any], group_records: list[dict[str, Any]]) -> None:
    group_dir = output_root / "group_records"
    group_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "execution_git_topology_report.json", report)
    _write_json(output_root / "test_handoff_package.json", package)
    for item in group_records:
        _write_json(group_dir / f"{_safe_name(item['group_id'])}.json", item)
    (output_root / "README.md").write_text(
        "# Execution Phase 19A Git Topology Package\n\n"
        f"run_id: `{report['run_id']}`\n\n"
        f"status: `{report['status']}`\n\n"
        f"integration_branch: `{report['integration_branch']}`\n\n"
        "This package is a Test handoff candidate generated by Execution Leader.\n\n"
        "Boundary: Phase 19A validates local git branch/workspace/integration topology only. "
        "It does not prove real Front/Back Codex agent execution and does not perform remote push, PR, merge, or release.\n",
        encoding="utf-8",
    )


def _apply_file_mutation(repo: Path, change: FileMutation) -> None:
    target = (repo / change.path).resolve()
    if not _is_relative_to(target, repo.resolve()):
        raise ExecutionGitTopologyError(f"file mutation escapes repository: {change.path}")
    if change.change_type == "delete":
        if target.exists():
            target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(change.content, encoding="utf-8", newline="\n")


def _run_local_test(repo: Path, command: str) -> dict[str, Any]:
    result = subprocess.run(command, cwd=repo, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    payload = {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "passed": result.returncode == 0}
    if result.returncode != 0:
        raise ExecutionGitTopologyError(f"group local test failed: {command}\n{result.stdout}\n{result.stderr}")
    return payload


def _validate_request(request: ExecutionGitTopologyRequest) -> None:
    seen_group_ids: set[str] = set()
    seen_branches: set[str] = set()
    file_owner: dict[str, str] = {}
    for group in request.groups:
        if group.group_id in seen_group_ids:
            raise ExecutionGitTopologyError(f"duplicate group_id: {group.group_id}")
        seen_group_ids.add(group.group_id)
        if group.branch_name in seen_branches:
            raise ExecutionGitTopologyError(f"duplicate group branch: {group.branch_name}")
        seen_branches.add(group.branch_name)
        if group.branch_name == request.integration_branch:
            raise ExecutionGitTopologyError("group branch must not equal integration branch")
        for path in group.touched_files():
            owner = file_owner.get(path)
            if owner is not None:
                raise ExecutionGitTopologyError(f"invalid split: file {path} is owned by both {owner} and {group.group_id}")
            file_owner[path] = group.group_id


def _assert_git_repo(repo: Path) -> None:
    if not repo.is_dir():
        raise ExecutionGitTopologyError(f"target repository directory does not exist: {repo}")
    result = _run_git(repo, ["rev-parse", "--is-inside-work-tree"])
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise ExecutionGitTopologyError(f"target repository is not a git worktree: {repo}")


def _assert_clean_worktree(repo: Path) -> None:
    status = _git_stdout(repo, ["status", "--porcelain"])
    if status:
        raise ExecutionGitTopologyError(f"target repository worktree must be clean before Phase 19A run:\n{status}")


def _git(repo: Path, args: list[str]) -> None:
    result = _run_git(repo, args)
    if result.returncode != 0:
        raise ExecutionGitTopologyError(f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}")


def _git_stdout(repo: Path, args: list[str]) -> str:
    result = _run_git(repo, args)
    if result.returncode != 0:
        raise ExecutionGitTopologyError(f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}")
    return result.stdout.strip()


def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionGitTopologyError(f"{name} must be a non-empty string")
    return value


def _ensure_string_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ExecutionGitTopologyError(f"{name} must be a list of non-empty strings")
    return list(value)


def _assert_safe_repo_path(value: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ExecutionGitTopologyError(f"path must be repository-relative and safe: {value}")


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)
