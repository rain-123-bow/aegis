from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aegis_test_runtime.handoff_validation import TestHandoffValidationError, run_test_handoff_validation


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _make_sandbox(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "sandbox"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "aegis@example.invalid")
    _git(repo, "config", "user.name", "Aegis Test")
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_base.py").write_text("def test_base():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    _git(repo, "checkout", "-B", "aegis/phase20a/integration", "main")
    (repo / "tests" / "test_phase20a.py").write_text("def test_phase20a():\n    assert 2 == 2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "integration candidate")
    integration = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")
    return repo, integration


def _handoff(repo: Path, integration: str) -> dict:
    return {
        "handoff_kind": "execution_real_front_back_candidate",
        "target": "test",
        "status": "ready_for_test_department",
        "run_id": "phase20a-test",
        "target_repo": str(repo),
        "base_branch": "main",
        "integration_branch": "aegis/phase20a/integration",
        "integration_commit": integration,
        "changed_files": ["tests/test_phase20a.py"],
        "group_mapping": [{"group_id": "G1", "branch_name": "aegis/G1", "touched_files": ["tests/test_phase20a.py"]}],
    }


def test_phase20a_validates_handoff_checkout_runs_pytest_and_writes_package(tmp_path: Path):
    repo, integration = _make_sandbox(tmp_path)
    output_dir = tmp_path / "out"
    report = run_test_handoff_validation(_handoff(repo, integration), output_dir=output_dir, default_test_command=[sys.executable, "-m", "pytest", "-q"])
    assert report["status"] == "accepted_test_handoff_validation_closure"
    assert report["test_result"] == "passed"
    assert report["integration_commit"] == integration
    assert (output_dir / "test_handoff_validation_report.json").is_file()
    assert (output_dir / "final_test_result.json").is_file()
    assert (output_dir / "reproducibility_set.json").is_file()
    assert (output_dir / "artifact_manifest.json").is_file()
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "aegis/phase20a/integration"


def test_phase20a_rejects_dirty_target_repo_before_checkout(tmp_path: Path):
    repo, integration = _make_sandbox(tmp_path)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(TestHandoffValidationError, match="clean"):
        run_test_handoff_validation(_handoff(repo, integration), output_dir=tmp_path / "out", default_test_command=[sys.executable, "-m", "pytest", "-q"])


def test_phase20a_rejects_invalid_handoff_target(tmp_path: Path):
    repo, integration = _make_sandbox(tmp_path)
    handoff = _handoff(repo, integration)
    handoff["target"] = "master"
    with pytest.raises(TestHandoffValidationError, match="target"):
        run_test_handoff_validation(handoff, output_dir=tmp_path / "out", default_test_command=[sys.executable, "-m", "pytest", "-q"])


def test_phase20a_failed_pytest_returns_failed_result_not_exception(tmp_path: Path):
    repo, integration = _make_sandbox(tmp_path)
    _git(repo, "checkout", "aegis/phase20a/integration")
    (repo / "tests" / "test_fail.py").write_text("def test_fail():\n    assert False\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "failing integration candidate")
    integration = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")
    report = run_test_handoff_validation(_handoff(repo, integration), output_dir=tmp_path / "out", default_test_command=[sys.executable, "-m", "pytest", "-q"])
    assert report["status"] == "test_handoff_validation_failed"
    assert report["test_result"] == "failed"
    assert report["boundaries"]["remote_push"] is False
    assert report["boundaries"]["global_causal_truth"] is False
