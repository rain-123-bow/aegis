from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aegis.modules.master import (
    ContinuityStore,
    MasterGateError,
    RequirementApprovalDecision,
    RequirementConstraint,
    RequirementSemanticAnalysis,
    build_execution_handoff,
    close_requirement_intake,
    draft_requirement_document,
    draft_requirement_document_from_conversation,
    review_requirement_document,
)


def _run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_project_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    project = tmp_path / "project"
    _run_git(tmp_path, "init", "--bare", str(remote))
    _run_git(tmp_path, "clone", str(remote), str(project))
    _run_git(project, "config", "user.email", "aegis@example.invalid")
    _run_git(project, "config", "user.name", "Aegis Test")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    _run_git(project, "add", "README.md")
    _run_git(project, "commit", "-m", "initial")
    _run_git(project, "push", "origin", "HEAD")
    return project, remote


def test_master_schema_downgrades_unsubstantiated_solution_lock_to_preference():
    document = draft_requirement_document(
        goal="Implement a local report generator.",
        raw_constraints=[
            RequirementConstraint(
                text="Must use framework X.",
                source="user",
                evidence_refs=[],
            )
        ],
    )

    constraint = document.constraints[0]
    assert constraint.admission == "preference"
    assert constraint.hard_constraint is False
    assert "insufficient evidence" in constraint.reason


def test_pm_intake_splits_purpose_from_technical_path_lock():
    conversation = close_requirement_intake(
        "一个一次性用到根据数据画表格，我要求用 C++ 实现",
        semantic_analysis=RequirementSemanticAnalysis(
            purpose="根据用户提供的数据生成一次性表格交付物",
            technical_path_requests=["C++"],
            deliverable_requests=["table artifact"],
        ),
    )

    assert "C++" not in conversation.purpose
    assert "C++" in conversation.technical_path_requests
    assert conversation.deliverable_requests
    assert conversation.raw_constraints

    document = draft_requirement_document_from_conversation(conversation)

    assert "C++" not in document.objective
    assert "表格" in document.objective or "table" in document.objective.lower()
    assert document.constraints[0].admission == "preference"
    assert document.constraints[0].hard_constraint is False
    assert "C++" in document.excluded_subjective_preferences[0]


def test_pm_semantic_analysis_accepts_structured_real_agent_list_items():
    analysis = RequirementSemanticAnalysis.model_validate(
        {
            "purpose": "Generate a PNG bar chart from Excel data.",
            "technical_path_requests": [
                {
                    "request": "Use Rust",
                    "hard_constraint_admitted": False,
                    "reason": "No project evidence proves Rust is necessary.",
                }
            ],
            "deliverable_requests": [
                {
                    "artifact": "PNG bar chart",
                    "input": "Excel file",
                    "required_columns": ["date", "amount"],
                }
            ],
            "unresolved_questions": [],
            "status": "ready_for_document",
        }
    )

    assert analysis.technical_path_requests == ["Use Rust"]
    assert analysis.deliverable_requests == [
        "PNG bar chart; input: Excel file; required_columns: date, amount"
    ]


def test_requirement_document_preserves_real_agent_functional_constraints():
    conversation = close_requirement_intake(
        "Read Excel and generate a PNG bar chart on Windows. Use Rust.",
        semantic_analysis=RequirementSemanticAnalysis.model_validate(
            {
                "purpose": "Generate a PNG bar chart from Excel data on Windows.",
                "technical_path_requests": [
                    {
                        "request": "Use Rust",
                        "hard_constraint_admitted": False,
                        "reason": "No evidence proves Rust is necessary.",
                    }
                ],
                "deliverable_requests": [
                    {
                        "artifact": "PNG bar chart",
                        "input": "Excel file",
                        "required_columns": ["date", "amount"],
                    }
                ],
                "hard_constraints": [
                    {
                        "constraint": "Must run locally on Windows.",
                        "admitted": True,
                        "basis": "Explicit platform/runtime boundary.",
                    }
                ],
                "unresolved_questions": [],
                "status": "ready_for_document",
            }
        ),
    )

    document = draft_requirement_document_from_conversation(conversation)
    constraints = {item.text: item for item in document.constraints}

    assert constraints["Requested implementation path: Use Rust"].admission == "preference"
    assert constraints["Deliverable request: PNG bar chart; input: Excel file; required_columns: date, amount"].admission == "hard_constraint"
    assert constraints["Must run locally on Windows."].admission == "hard_constraint"


def test_admitted_technical_path_is_not_reintroduced_as_preference():
    conversation = close_requirement_intake(
        "Add a page to the current React frontend.",
        semantic_analysis=RequirementSemanticAnalysis.model_validate(
            {
                "purpose": "Show monthly sales trends in the existing frontend.",
                "technical_path_requests": [
                    {
                        "request": "Continue using React.",
                        "hard_constraint_admitted": True,
                        "basis": "Existing React frontend integration boundary.",
                    }
                ],
                "deliverable_requests": ["Add a sales line chart page."],
                "hard_constraints": [],
                "unresolved_questions": [],
                "status": "ready_for_document",
            }
        ),
    )

    document = draft_requirement_document_from_conversation(conversation)

    assert "Continue using React." not in conversation.technical_path_requests
    assert not [
        item for item in document.constraints if item.text.startswith("Requested implementation path:")
    ]
    assert any(
        item.text == "Continue using React." and item.admission == "hard_constraint"
        for item in document.constraints
    )


def test_structured_hard_constraint_preserves_evidence_refs():
    conversation = close_requirement_intake(
        "Customer email EVID-2026-0617 requires CSV export.",
        semantic_analysis=RequirementSemanticAnalysis.model_validate(
            {
                "purpose": "Implement report export.",
                "technical_path_requests": [],
                "deliverable_requests": ["Report export"],
                "hard_constraints": [
                    {
                        "constraint": "Export format must be CSV.",
                        "admitted": True,
                        "evidence_ref": "EVID-2026-0617",
                    }
                ],
                "unresolved_questions": [],
                "status": "ready_for_document",
            }
        ),
    )

    document = draft_requirement_document_from_conversation(conversation)

    csv_constraint = next(item for item in document.constraints if item.text.startswith("Export format"))
    assert csv_constraint.evidence_refs == ["EVID-2026-0617"]


def test_master_schema_accepts_written_customer_evidence_as_hard_constraint():
    document = draft_requirement_document(
        goal="Implement a local report generator.",
        raw_constraints=[
            RequirementConstraint(
                text="Must export CSV because the customer contract requires CSV import.",
                source="customer_written_evidence",
                evidence_refs=["contract://customer/import-requirements#csv"],
            )
        ],
    )

    constraint = document.constraints[0]
    assert constraint.admission == "hard_constraint"
    assert constraint.hard_constraint is True


def test_review_routes_weak_local_lock_to_debate_issue():
    conversation = close_requirement_intake(
        "Choose the storage implementation and use direct JSON files.",
        semantic_analysis=RequirementSemanticAnalysis(
            purpose="Choose and implement a storage mechanism for the local project.",
            technical_path_requests=["direct JSON files"],
            deliverable_requests=["storage implementation"],
        ),
    )
    document = draft_requirement_document_from_conversation(conversation)

    review = review_requirement_document(
        document,
        knowledge_refs=["knowledge://project/storage-boundaries"],
    )

    assert review.findings[0].decision == "reject_as_hard_constraint"
    assert review.debate_issues
    assert review.debate_issues[0].status == "pending"
    assert "multiple implementation routes" in review.debate_issues[0].why


def test_execution_handoff_requires_both_user_approvals():
    requirement = draft_requirement_document(goal="Implement a small local feature.")
    review = review_requirement_document(requirement, knowledge_refs=[])

    with pytest.raises(MasterGateError, match="requirement document is not approved"):
        build_execution_handoff(
            requirement,
            review,
            requirement_approval=None,
            review_approval=RequirementApprovalDecision(approved=True, approved_by="user"),
        )

    with pytest.raises(MasterGateError, match="review document is not approved"):
        build_execution_handoff(
            requirement,
            review,
            requirement_approval=RequirementApprovalDecision(approved=True, approved_by="user"),
            review_approval=None,
        )


def test_execution_handoff_contains_requirement_and_review_refs():
    requirement = draft_requirement_document(goal="Implement a small local feature.")
    review = review_requirement_document(requirement, knowledge_refs=[])

    handoff = build_execution_handoff(
        requirement,
        review,
        requirement_approval=RequirementApprovalDecision(approved=True, approved_by="user"),
        review_approval=RequirementApprovalDecision(approved=True, approved_by="user"),
    )

    assert handoff.status == "ready_for_execution"
    assert handoff.requirement_document_id == requirement.document_id
    assert handoff.review_document_id == review.document_id
    assert handoff.forbidden_actions == [
        "master_executes_code",
        "master_runs_tests",
        "master_merges_global_causal_truth",
    ]


def test_continuity_records_baseline_then_reports_clean(tmp_path, monkeypatch):
    project, _remote = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    store = ContinuityStore()
    first = store.check_project(project)
    second = store.check_project(project)

    assert first.status == "baseline_missing"
    assert first.can_proceed is True
    assert first.action_taken == "record_baseline"
    assert second.status == "clean"
    assert second.can_proceed is True


def test_continuity_blocks_git_project_without_remote(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    _run_git(project, "init")
    _run_git(project, "config", "user.email", "aegis@example.invalid")
    _run_git(project, "config", "user.name", "Aegis Test")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    _run_git(project, "add", "README.md")
    _run_git(project, "commit", "-m", "initial")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    result = ContinuityStore().check_project(project)

    assert result.status == "unknown_remote"
    assert result.can_proceed is False
    assert result.blocked_reason == "git remote origin is required for continuity recovery"


def test_continuity_dirty_project_can_be_quarantined_and_recloned(tmp_path, monkeypatch):
    project, remote = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    store = ContinuityStore()
    store.check_project(project)
    (project / "README.md").write_text("# Changed outside Aegis\n", encoding="utf-8")

    result = store.check_project(project, recover_dirty=True)

    assert result.status == "dirty"
    assert result.can_proceed is True
    assert result.action_taken == "quarantine_and_reclone"
    assert result.quarantine_path
    assert Path(result.quarantine_path).exists()
    assert _run_git(project, "config", "--get", "remote.origin.url") == str(remote)
    assert (project / "README.md").read_text(encoding="utf-8") == "# Demo\n"
