from __future__ import annotations

from aegis.modules.execution.models import ArtifactRef, RealAgentValidationResult
from aegis.modules.execution.validators import validate_real_agent_behavior


def artifact_ref(kind: str = "test") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{kind}-artifact",
        artifact_type=kind,
        path=f"/tmp/{kind}",
        readme_path=f"/tmp/{kind}/README.md",
        sha256="0" * 64,
        created_by_node="unit_test",
    )


def test_real_agent_validator_rejects_missing_review_baseline() -> None:
    result = validate_real_agent_behavior(
        thread_id="thread-1",
        execution_planned_before_implementation=True,
        review_baseline_before_review=False,
        unapproved_implementation_blocked=True,
        truth_write_attempt_blocked=True,
        no_default_front_back_group=True,
        remote_publish_interrupted=True,
        checked_artifacts=[artifact_ref("behavior")],
    )

    assert isinstance(result, RealAgentValidationResult)
    assert result.status == "failed"
    assert result.policy_violations
    assert result.policy_violations[0].violation_type == "scorecard_inconsistent"


def test_real_agent_validator_handles_missing_artifact_evidence() -> None:
    result = validate_real_agent_behavior(
        thread_id="thread-no-evidence",
        execution_planned_before_implementation=True,
        review_baseline_before_review=True,
        unapproved_implementation_blocked=True,
        truth_write_attempt_blocked=True,
        no_default_front_back_group=True,
        remote_publish_interrupted=True,
        checked_artifacts=[],
    )

    assert result.status == "failed"
    assert result.policy_violations
    assert result.policy_violations[0].violation_type == "scorecard_inconsistent"
