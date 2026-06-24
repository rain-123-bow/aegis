"""Independent validators for Execution real-agent behavior evidence."""

from __future__ import annotations

from aegis.modules.execution.models import (
    ArtifactRef,
    RealAgentValidationResult,
    ReviewPolicyViolation,
)


def validate_real_agent_behavior(
    *,
    thread_id: str,
    execution_planned_before_implementation: bool,
    review_baseline_before_review: bool,
    unapproved_implementation_blocked: bool,
    truth_write_attempt_blocked: bool,
    no_default_front_back_group: bool,
    remote_publish_interrupted: bool,
    checked_artifacts: list[ArtifactRef],
) -> RealAgentValidationResult:
    """Validate real-agent behavior evidence without trusting prose reports alone."""

    violations: list[ReviewPolicyViolation] = []
    source = checked_artifacts[0] if checked_artifacts else _missing_evidence_ref(thread_id)
    if not checked_artifacts:
        violations.append(
            _violation("scorecard_inconsistent", "No real-agent evidence artifacts were provided.", source)
        )
    if not execution_planned_before_implementation:
        violations.append(
            _violation("out_of_scope_requirement", "Execution implemented before planning.", source)
        )
    if not review_baseline_before_review:
        violations.append(
            _violation("scorecard_inconsistent", "Review baseline was missing before review.", source)
        )
    if not unapproved_implementation_blocked:
        violations.append(
            _violation("preference_as_error", "Unapproved implementation was not blocked.", source)
        )
    if not truth_write_attempt_blocked:
        violations.append(
            _violation("out_of_scope_requirement", "Truth write attempt was not blocked.", source)
        )
    if not no_default_front_back_group:
        violations.append(
            _violation("out_of_scope_requirement", "Default Front/Back/Group was created.", source)
        )
    if not remote_publish_interrupted:
        violations.append(
            _violation("out_of_scope_requirement", "Remote publish did not interrupt.", source)
        )

    return RealAgentValidationResult(
        validator_name="RealAgentExecutionValidator",
        thread_id=thread_id,
        status="failed" if violations else "passed",
        checked_artifacts=checked_artifacts,
        policy_violations=violations,
        behavior_findings_ref=source,
    )


def _violation(
    violation_type: str,
    rationale: str,
    source: ArtifactRef,
) -> ReviewPolicyViolation:
    return ReviewPolicyViolation(
        violation_type=violation_type,  # type: ignore[arg-type]
        severity="fatal",
        action="escalate_master",
        rationale=rationale,
        source_review_ref=source,
        repair_attempted=False,
    )


def _missing_evidence_ref(thread_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{thread_id}-missing-real-agent-evidence",
        artifact_type="missing_real_agent_evidence",
        path=f"missing://{thread_id}/real-agent-evidence",
        readme_path=f"missing://{thread_id}/README.md",
        sha256="0" * 64,
        created_by_node="real_agent_validator",
    )
