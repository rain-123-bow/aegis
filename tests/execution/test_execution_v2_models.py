from __future__ import annotations

import pytest

from aegis.modules.execution.models import (
    ArtifactRef,
    ExecutionBoundaryFlags,
    ExecutionOutputPackage,
    ReviewIssue,
    ReviewScorecard,
)


def artifact_ref(kind: str = "test") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{kind}-artifact",
        artifact_type=kind,
        path=f"/tmp/{kind}",
        readme_path=f"/tmp/{kind}/README.md",
        sha256="0" * 64,
        created_by_node="unit_test",
    )


def test_scorecard_approved_requires_no_errors() -> None:
    with pytest.raises(ValueError, match="approved scorecards require score >= 95"):
        ReviewScorecard(
            decision="approved",
            score=94,
            dimensions={"requirements": 94},
            error_count=0,
            warning_count=0,
            suggestion_count=0,
            blocking_issues=[],
            non_blocking_issues=[],
            baseline_ref=artifact_ref("baseline"),
            review_artifact_ref=artifact_ref("review"),
        )

    with pytest.raises(ValueError, match="approved scorecards require error_count == 0"):
        ReviewScorecard(
            decision="approved",
            score=98,
            dimensions={"requirements": 98},
            error_count=1,
            warning_count=0,
            suggestion_count=0,
            blocking_issues=[
                ReviewIssue(
                    issue_id="err-1",
                    severity="error",
                    requirement_refs=["REQ-1"],
                    evidence_refs=["E-1"],
                    explanation="Plan violates a hard requirement.",
                    required_change="Fix the hard requirement mapping.",
                    blocking=True,
                )
            ],
            non_blocking_issues=[],
            baseline_ref=artifact_ref("baseline"),
            review_artifact_ref=artifact_ref("review"),
        )


def test_warning_only_score_95_must_approve() -> None:
    with pytest.raises(ValueError, match="warning-only reviews with score >= 95 must approve"):
        ReviewScorecard(
            decision="changes_required",
            score=96,
            dimensions={"requirements": 96},
            error_count=0,
            warning_count=1,
            suggestion_count=0,
            blocking_issues=[],
            non_blocking_issues=[
                ReviewIssue(
                    issue_id="warn-1",
                    severity="warning",
                    requirement_refs=["REQ-1"],
                    evidence_refs=["E-1"],
                    explanation="A non-blocking simplification exists.",
                    required_change=None,
                    blocking=False,
                )
            ],
            baseline_ref=artifact_ref("baseline"),
            review_artifact_ref=artifact_ref("review"),
        )


def test_blocking_issue_must_be_error() -> None:
    with pytest.raises(ValueError, match="blocking issues must have severity=error"):
        ReviewScorecard(
            decision="changes_required",
            score=90,
            dimensions={"requirements": 90},
            error_count=0,
            warning_count=1,
            suggestion_count=0,
            blocking_issues=[
                ReviewIssue(
                    issue_id="warn-1",
                    severity="warning",
                    requirement_refs=["REQ-1"],
                    evidence_refs=["E-1"],
                    explanation="Warning cannot block.",
                    required_change="Do not block on warning.",
                    blocking=True,
                )
            ],
            non_blocking_issues=[],
            baseline_ref=artifact_ref("baseline"),
            review_artifact_ref=artifact_ref("review"),
        )


def test_execution_output_package_forbids_truth_and_remote_publish() -> None:
    with pytest.raises(ValueError, match="ExecutionOutputPackage boundary flags must remain false"):
        ExecutionOutputPackage(
            run_id="run-1",
            status="completed",
            phase="completed",
            master_handoff_ref=artifact_ref("handoff"),
            input_validation_ref=artifact_ref("input-validation"),
            implementation_artifact_ref=artifact_ref("implementation"),
            implementation_changeset_ref=artifact_ref("changeset"),
            simple_test_evidence_ref=artifact_ref("tests"),
            boundary=ExecutionBoundaryFlags(wrote_causal_truth=True),
            next_stage="test_subgraph",
            evidence_index_ref=artifact_ref("evidence-index"),
        )


def test_completed_output_requires_implementation_and_test_refs() -> None:
    with pytest.raises(ValueError, match="completed output requires implementation_artifact_ref"):
        ExecutionOutputPackage(
            run_id="run-1",
            status="completed",
            phase="completed",
            master_handoff_ref=artifact_ref("handoff"),
            input_validation_ref=artifact_ref("input-validation"),
            boundary=ExecutionBoundaryFlags(),
            next_stage="test_subgraph",
            evidence_index_ref=artifact_ref("evidence-index"),
        )
