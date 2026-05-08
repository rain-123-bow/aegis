from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aegis_execution_runtime.git_topology import (
    ExecutionGitTopologyError,
    run_execution_git_topology_closure,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "sandbox"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "aegis@example.invalid")
    _git(repo, "config", "user.name", "Aegis Test")
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests" / "test_model.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial sandbox")
    _git(repo, "branch", "-M", "main")
    return repo


def test_phase19a_creates_group_branches_integration_branch_and_test_handoff(tmp_path: Path):
    repo = _make_repo(tmp_path)
    output_dir = tmp_path / "phase19a"
    request = {
        "run_id": "phase19a-test-run",
        "target_repo": str(repo),
        "base_branch": "main",
        "integration_branch": "aegis/phase19a/integration",
        "objective": "Validate local git topology closure.",
        "groups": [
            {
                "group_id": "G1",
                "subtask_id": "model-change",
                "branch_name": "aegis/phase19a/G1-model",
                "responsibility": "Update model constant.",
                "local_success_criteria": ["model file is updated"],
                "file_changes": [
                    {
                        "path": "src/model.py",
                        "content": "VALUE = 2\n",
                        "change_type": "modify",
                        "why_changed": "deterministic group change",
                    }
                ],
            },
            {
                "group_id": "G2",
                "subtask_id": "test-change",
                "branch_name": "aegis/phase19a/G2-test",
                "responsibility": "Add test evidence.",
                "local_success_criteria": ["test file is updated"],
                "file_changes": [
                    {
                        "path": "tests/test_model.py",
                        "content": "def test_value():\n    assert True\n\ndef test_extra():\n    assert 2 == 2\n",
                        "change_type": "modify",
                        "why_changed": "deterministic group test change",
                    }
                ],
            },
        ],
    }

    report = run_execution_git_topology_closure(request, output_dir=output_dir)

    assert report["status"] == "accepted_execution_git_topology_closure"
    assert report["integration_branch"] == "aegis/phase19a/integration"
    assert len(report["group_records"]) == 2
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "aegis/phase19a/integration"
    assert _git(repo, "rev-parse", "--verify", "aegis/phase19a/G1-model")
    assert _git(repo, "rev-parse", "--verify", "aegis/phase19a/G2-test")

    handoff = (output_dir / "test_handoff_package.json").read_text(encoding="utf-8")
    assert "execution_git_topology_candidate" in handoff
    assert "aegis/phase19a/integration" in handoff
    assert (output_dir / "group_records" / "G1.json").is_file()
    assert (output_dir / "group_records" / "G2.json").is_file()


def test_phase19a_rejects_duplicate_file_ownership_before_branching(tmp_path: Path):
    repo = _make_repo(tmp_path)
    request = {
        "run_id": "phase19a-duplicate",
        "target_repo": str(repo),
        "base_branch": "main",
        "integration_branch": "aegis/phase19a/integration",
        "groups": [
            {
                "group_id": "G1",
                "subtask_id": "one",
                "branch_name": "aegis/G1",
                "responsibility": "first owner",
                "local_success_criteria": ["changed"],
                "file_changes": [{"path": "src/model.py", "content": "VALUE = 2\n"}],
            },
            {
                "group_id": "G2",
                "subtask_id": "two",
                "branch_name": "aegis/G2",
                "responsibility": "second owner",
                "local_success_criteria": ["changed"],
                "file_changes": [{"path": "src/model.py", "content": "VALUE = 3\n"}],
            },
        ],
    }

    with pytest.raises(ExecutionGitTopologyError, match="invalid split"):
        run_execution_git_topology_closure(request, output_dir=tmp_path / "out")


def test_phase19a_rejects_dirty_target_repo(tmp_path: Path):
    repo = _make_repo(tmp_path)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    request = {
        "run_id": "phase19a-dirty",
        "target_repo": str(repo),
        "base_branch": "main",
        "integration_branch": "aegis/phase19a/integration",
        "groups": [
            {
                "group_id": "G1",
                "subtask_id": "one",
                "branch_name": "aegis/G1",
                "responsibility": "safe change",
                "local_success_criteria": ["changed"],
                "file_changes": [{"path": "src/model.py", "content": "VALUE = 2\n"}],
            }
        ],
    }

    with pytest.raises(ExecutionGitTopologyError, match="clean"):
        run_execution_git_topology_closure(request, output_dir=tmp_path / "out")
