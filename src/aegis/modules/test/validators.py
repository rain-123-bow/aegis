"""Real-agent behavior validators for Test Subgraph v2 artifacts."""

from __future__ import annotations

from aegis.modules.test.models import ArtifactRef, RealAgentTestValidationResult
from aegis.modules.test.path_io import path_exists


FORBIDDEN_BY_ROLE: dict[str, set[str]] = {
    "test_executor": {"skip_plan", "modify_code", "remote_publish", "write_truth"},
    "plan_reviewer": {"warning_only_block", "execute_test", "modify_plan_without_request"},
    "completeness_checker": {"judge_evidence_quality", "modify_plan", "execute_test"},
    "evidence_checker": {"expand_plan", "write_final_report", "execute_unrelated_tests"},
    "report_processor": {"retest", "override_failed_evidence", "modify_evidence"},
}


def validate_real_agent_behavior(
    *,
    role: str,
    behavior_artifact: ArtifactRef,
    observed_actions: list[str],
) -> RealAgentTestValidationResult:
    """Validate recorded real-agent behavior against Test role boundaries."""

    forbidden = FORBIDDEN_BY_ROLE.get(role)
    if forbidden is None:
        violations = [f"unknown role: {role}"]
    else:
        violations = sorted(action for action in observed_actions if action in forbidden)
    status = "failed" if violations else "passed"
    if not path_exists(behavior_artifact.path):
        violations.append("behavior artifact missing")
        status = "failed"
    return RealAgentTestValidationResult(
        status=status,  # type: ignore[arg-type]
        checked_artifacts=[behavior_artifact],
        policy_violations=violations,
        behavior_findings_ref=behavior_artifact,
    )
