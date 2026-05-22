from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PHASE = "phase26a_execution_role_operational_skills"
LEADER_SKILL_ID = "EXECUTION_LEADER_OPERATIONAL_SKILL"
FRONT_SKILL_ID = "EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL"
BACK_SKILL_ID = "EXECUTION_BACK_AGENT_OPERATIONAL_SKILL"
SKILL_VERSION = "v0.3"

ALLOWED_REVIEW_DECISIONS = {
    "accept",
    "reject",
    "request_changes",
    "request_more_evidence",
    "scope_violation",
    "contract_violation",
}

FORBIDDEN_TRUE_FIELDS = (
    "remote_push_performed",
    "pull_request_created",
    "remote_merge_performed",
    "release_performed",
    "deployment_performed",
    "external_signoff_performed",
    "global_causal_truth_merge_performed",
    "production_store_write_performed",
)

FORBIDDEN_OUTPUT_TRUE_FIELDS = FORBIDDEN_TRUE_FIELDS + (
    "global_causal_truth_claimed",
)


class ExecutionOperationalSkillError(ValueError):
    """Raised when Phase 26A Execution skill validation input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == []


def _require_true(value: Any, field: str, violations: list[dict[str, Any]], reason: str) -> None:
    if value is not True:
        violations.append(_violation(field, reason))


def _require_false(value: Any, field: str, violations: list[dict[str, Any]], reason: str) -> None:
    if value is not False:
        violations.append(_violation(field, reason))


@dataclass(frozen=True)
class ExecutionSkillValidationResult:
    execution_skill_validation_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    leader_skill_ref: dict[str, str]
    front_skill_ref: dict[str, str]
    back_skill_ref: dict[str, str]
    group_count: int = 0
    front_output_count: int = 0
    back_review_count: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)
    leader_skill_installed: bool = False
    child_creation_proofs_verified: bool = False
    group_branch_proofs_verified: bool = False
    front_outputs_verified: bool = False
    back_reviews_verified: bool = False
    integration_verified: bool = False
    test_handoff_verified: bool = False
    remote_push_performed: bool = False
    pull_request_created: bool = False
    remote_merge_performed: bool = False
    release_performed: bool = False
    deployment_performed: bool = False
    external_signoff_performed: bool = False
    global_causal_truth_merge_performed: bool = False
    production_store_write_performed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_skill_validation_result_id": self.execution_skill_validation_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "leader_skill_ref": dict(self.leader_skill_ref),
            "front_skill_ref": dict(self.front_skill_ref),
            "back_skill_ref": dict(self.back_skill_ref),
            "group_count": self.group_count,
            "front_output_count": self.front_output_count,
            "back_review_count": self.back_review_count,
            "violations": list(self.violations),
            "leader_skill_installed": self.leader_skill_installed,
            "child_creation_proofs_verified": self.child_creation_proofs_verified,
            "group_branch_proofs_verified": self.group_branch_proofs_verified,
            "front_outputs_verified": self.front_outputs_verified,
            "back_reviews_verified": self.back_reviews_verified,
            "integration_verified": self.integration_verified,
            "test_handoff_verified": self.test_handoff_verified,
            "remote_push_performed": self.remote_push_performed,
            "pull_request_created": self.pull_request_created,
            "remote_merge_performed": self.remote_merge_performed,
            "release_performed": self.release_performed,
            "deployment_performed": self.deployment_performed,
            "external_signoff_performed": self.external_signoff_performed,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "production_store_write_performed": self.production_store_write_performed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExecutionOperationalSkillError(f"file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ExecutionOperationalSkillError(f"file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExecutionOperationalSkillError("file must contain a JSON object")
    return payload


def validate_execution_skill_run_file(
    run_path: str | Path,
    *,
    leader_skill_path: str | Path | None = None,
    front_skill_path: str | Path | None = None,
    back_skill_path: str | Path | None = None,
) -> ExecutionSkillValidationResult:
    return validate_execution_skill_run(
        load_json_object(run_path),
        leader_skill_path=leader_skill_path,
        front_skill_path=front_skill_path,
        back_skill_path=back_skill_path,
    )


def validate_execution_skill_run(
    run: dict[str, Any],
    *,
    leader_skill_path: str | Path | None = None,
    front_skill_path: str | Path | None = None,
    back_skill_path: str | Path | None = None,
) -> ExecutionSkillValidationResult:
    if not isinstance(run, dict):
        raise ExecutionOperationalSkillError("run must be a JSON object")

    violations: list[dict[str, Any]] = []

    if leader_skill_path is not None:
        _check_skill_file(leader_skill_path, skill_id=LEADER_SKILL_ID, field="leader_skill_file", violations=violations)
    if front_skill_path is not None:
        _check_skill_file(front_skill_path, skill_id=FRONT_SKILL_ID, field="front_skill_file", violations=violations)
    if back_skill_path is not None:
        _check_skill_file(back_skill_path, skill_id=BACK_SKILL_ID, field="back_skill_file", violations=violations)

    leader_ref = _ref(run.get("skill_ref"))
    if not _is_skill_ref(leader_ref, LEADER_SKILL_ID):
        violations.append(_violation("skill_ref", "Execution Leader run must reference EXECUTION_LEADER_OPERATIONAL_SKILL v0.3."))

    policy_auth = run.get("model_policy_authority")
    if policy_auth != "MODEL_REASONING_BUDGET_POLICY.yaml":
        violations.append(_violation("model_policy_authority", "Root MODEL_REASONING_BUDGET_POLICY.yaml must be the model-policy authority."))

    request = _ref(run.get("execution_request"))
    for key in ("request_id", "task_id", "aegis_work_branch", "scope"):
        if _is_missing(request.get(key)):
            violations.append(_violation(f"execution_request.{key}", "Execution request missing required field."))

    contract_check = _ref(run.get("contract_first_check"))
    if contract_check.get("frozen_contract_required") is True and contract_check.get("frozen_contract_present") is not True:
        violations.append(_violation("contract_first_check.frozen_contract_present", "Required frozen contract is missing."))

    split = _ref(run.get("split_decision"))
    if split.get("valid") is not True and split.get("single_group_justified") is not True:
        violations.append(_violation("split_decision", "Split must be valid or single-group execution must be justified."))
    invalid_patterns = split.get("invalid_split_patterns_present") or []
    if invalid_patterns:
        violations.append(_violation("split_decision.invalid_split_patterns_present", "Invalid split pattern(s) present: " + ", ".join(map(str, invalid_patterns))))

    groups = _as_dict_list(run.get("groups", []), "groups", violations)
    if not groups:
        violations.append(_violation("groups", "Execution run requires at least one group."))
    group_ids = [str(item.get("group_id", "")) for item in groups if item.get("group_id")]
    for group in groups:
        for key in ("group_id", "subtask_id", "responsibility_scope"):
            if _is_missing(group.get(key)):
                violations.append(_violation(f"groups.{key}", "Group missing required field."))

    branch_proofs = _as_dict_list(run.get("group_branch_proofs", []), "group_branch_proofs", violations)
    branch_by_group: dict[str, dict[str, Any]] = {}
    for proof in branch_proofs:
        group_id = str(proof.get("group_id", ""))
        if not group_id:
            violations.append(_violation("group_branch_proofs.group_id", "Group branch proof missing group_id."))
            continue
        branch_by_group[group_id] = proof
        _check_group_branch_proof(proof, violations)
    for group_id in group_ids:
        if group_id not in branch_by_group:
            violations.append(_violation("group_branch_proofs", f"Missing group branch proof for {group_id}."))

    child_proofs = _as_dict_list(run.get("child_agent_creation_proofs", []), "child_agent_creation_proofs", violations)
    child_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for proof in child_proofs:
        role = str(proof.get("role_id", ""))
        group_id = str(proof.get("group_id", ""))
        child_by_key[(role, group_id)] = proof
        _check_child_agent_creation_proof(proof, violations)
    for group_id in group_ids:
        if ("execution_front_agent", group_id) not in child_by_key:
            violations.append(_violation("child_agent_creation_proofs", f"Missing Front creation proof for {group_id}."))
        if ("execution_back_agent", group_id) not in child_by_key:
            violations.append(_violation("child_agent_creation_proofs", f"Missing Back creation proof for {group_id}."))

    front_outputs = _as_dict_list(run.get("front_outputs", []), "front_outputs", violations)
    front_by_group: dict[str, dict[str, Any]] = {}
    for output in front_outputs:
        group_id = str(output.get("group_id", ""))
        front_by_group[group_id] = output
        _check_front_output(output, child_by_key=child_by_key, branch_by_group=branch_by_group, violations=violations)
    for group_id in group_ids:
        if group_id not in front_by_group:
            violations.append(_violation("front_outputs", f"Missing Front output for {group_id}."))

    back_reviews = _as_dict_list(run.get("back_reviews", []), "back_reviews", violations)
    back_by_group: dict[str, dict[str, Any]] = {}
    for review in back_reviews:
        group_id = str(review.get("group_id", ""))
        back_by_group[group_id] = review
        _check_back_review(
            review,
            child_by_key=child_by_key,
            branch_by_group=branch_by_group,
            front_by_group=front_by_group,
            violations=violations,
        )
    for group_id in group_ids:
        if group_id not in back_by_group:
            violations.append(_violation("back_reviews", f"Missing Back review for {group_id}."))
        elif back_by_group[group_id].get("review_decision") != "accept":
            violations.append(_violation("back_reviews.review_decision", f"Group {group_id} is not accepted by Back review."))

    integration = _ref(run.get("leader_integration"))
    if groups:
        if integration.get("created_by") != "execution_leader":
            violations.append(_violation("leader_integration.created_by", "Leader integration branch must be created by execution_leader."))
        if integration.get("derives_from_base_commit") is not True:
            violations.append(_violation("leader_integration.derives_from_base_commit", "Integration branch must derive from base_commit."))
        accepted = integration.get("accepted_group_branches") or []
        if not isinstance(accepted, list) or len(accepted) < len(groups):
            violations.append(_violation("leader_integration.accepted_group_branches", "Integration must include all accepted group branches."))

    conflicts = _as_dict_list(run.get("integration_conflicts", []), "integration_conflicts", violations)
    for conflict in conflicts:
        if _is_missing(conflict.get("classification")) or _is_missing(conflict.get("default_action")):
            violations.append(_violation("integration_conflicts", "Integration conflict requires classification and default_action."))
        if conflict.get("silently_hidden") is True:
            violations.append(_violation("integration_conflicts.silently_hidden", "Integration conflicts must not be silently hidden."))

    handoff = _ref(run.get("test_handoff_package"))
    if groups:
        if _is_missing(handoff.get("integration_branch")) or handoff.get("integration_branch") != integration.get("integration_branch"):
            violations.append(_violation("test_handoff_package.integration_branch", "Test handoff must target the Leader integration branch."))
        if handoff.get("no_remote_push") is not True or handoff.get("no_pr_created") is not True or handoff.get("no_release") is not True:
            violations.append(_violation("test_handoff_package.boundary", "Test handoff must preserve no remote push / PR / release boundary."))

    causal = _ref(run.get("execution_causal_handoff"))
    if groups:
        for key in ("statement", "why", "evidence", "scope", "assumptions", "status"):
            if key not in causal or _is_missing(causal.get(key)):
                violations.append(_violation(f"execution_causal_handoff.{key}", "Execution causal handoff missing required field."))
        if causal.get("status") not in {"causal_candidate", None}:
            violations.append(_violation("execution_causal_handoff.status", "Execution handoff status must remain causal_candidate."))

    boundaries = _ref(run.get("boundaries"))
    for field in FORBIDDEN_TRUE_FIELDS:
        if run.get(field) is True or handoff.get(field) is True or causal.get(field) is True or boundaries.get(field) is True:
            violations.append(_violation(field, f"{field} must remain false."))

    status = "validated" if not violations else "rejected"
    return ExecutionSkillValidationResult(
        execution_skill_validation_result_id=f"execution-skill-{uuid4().hex}",
        phase=PHASE,
        status=status,
        decision="accepted_execution_role_skill_enforcement" if status == "validated" else "rejected",
        reason="Validated Execution Leader/Front/Back role-bound operational skill enforcement." if status == "validated" else "Execution role-bound skill validation failed.",
        leader_skill_ref={"skill_id": LEADER_SKILL_ID, "skill_version": SKILL_VERSION},
        front_skill_ref={"skill_id": FRONT_SKILL_ID, "skill_version": SKILL_VERSION},
        back_skill_ref={"skill_id": BACK_SKILL_ID, "skill_version": SKILL_VERSION},
        group_count=len(groups),
        front_output_count=len(front_outputs),
        back_review_count=len(back_reviews),
        violations=violations,
        leader_skill_installed=_is_skill_ref(leader_ref, LEADER_SKILL_ID),
        child_creation_proofs_verified=not any(v["field"].startswith("child_agent_creation_proofs") for v in violations),
        group_branch_proofs_verified=not any(v["field"].startswith("group_branch_proofs") for v in violations),
        front_outputs_verified=not any(v["field"].startswith("front_outputs") for v in violations),
        back_reviews_verified=not any(v["field"].startswith("back_reviews") for v in violations),
        integration_verified=not any(v["field"].startswith("leader_integration") or v["field"].startswith("integration_conflicts") for v in violations),
        test_handoff_verified=not any(v["field"].startswith("test_handoff_package") for v in violations),
    )


def _check_group_branch_proof(proof: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    for key in ("group_id", "subtask_id", "workspace_path", "repository_url", "aegis_work_branch", "base_commit", "group_work_branch", "branch_created_by", "allowed_paths", "local_success_criteria"):
        if key not in proof or _is_missing(proof.get(key)):
            violations.append(_violation(f"group_branch_proofs.{key}", "Group branch proof missing required field."))
    if proof.get("branch_created_by") != "execution_leader":
        violations.append(_violation("group_branch_proofs.branch_created_by", "Group branch must be created by execution_leader."))
    if proof.get("branch_derives_from_base_commit") is not True:
        violations.append(_violation("group_branch_proofs.branch_derives_from_base_commit", "Group branch must derive from base_commit."))
    if proof.get("branch_is_orphan") is not False or proof.get("branch_is_unborn") is not False:
        violations.append(_violation("group_branch_proofs.branch_state", "Group branch must not be orphan or unborn."))


def _check_child_agent_creation_proof(proof: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    required_non_empty = (
        "created_by",
        "creation_mechanism",
        "agent_id",
        "role_id",
        "group_id",
        "subtask_id",
        "thread_id",
        "requested_model",
        "policy_model",
        "requested_reasoning_effort",
        "policy_reasoning_budget",
        "skill_id",
        "skill_version",
        "proof_statement",
        "created_at_utc",
        "proof_json_ref",
        "proof_sha256",
    )
    for key in required_non_empty:
        if key not in proof or _is_missing(proof.get(key)):
            violations.append(_violation(f"child_agent_creation_proofs.{key}", "Child agent creation proof missing required field."))

    # Fallback audit fields must be present even when fallback was not used.
    for key in ("fallback_used", "fallback_reason", "fallback_evidence_refs"):
        if key not in proof:
            violations.append(_violation(f"child_agent_creation_proofs.{key}", "Child agent creation proof missing fallback audit field."))

    if proof.get("fallback_used") not in {True, False}:
        violations.append(_violation("child_agent_creation_proofs.fallback_used", "fallback_used must be boolean."))
    if proof.get("fallback_used") is True:
        if _is_missing(proof.get("fallback_reason")):
            violations.append(_violation("child_agent_creation_proofs.fallback_reason", "fallback_reason is required when fallback_used=true."))
        if _is_missing(proof.get("fallback_evidence_refs")):
            violations.append(_violation("child_agent_creation_proofs.fallback_evidence_refs", "fallback_evidence_refs are required when fallback_used=true."))

    if proof.get("created_by") != "execution_leader":
        violations.append(_violation("child_agent_creation_proofs.created_by", "Child agent must be created by execution_leader."))
    role = proof.get("role_id")
    expected_skill = FRONT_SKILL_ID if role == "execution_front_agent" else BACK_SKILL_ID if role == "execution_back_agent" else None
    if expected_skill is None:
        violations.append(_violation("child_agent_creation_proofs.role_id", "Child role_id must be execution_front_agent or execution_back_agent."))
    elif proof.get("skill_id") != expected_skill or proof.get("skill_version") != SKILL_VERSION:
        violations.append(_violation("child_agent_creation_proofs.skill_ref", "Child creation proof skill id/version mismatch."))
    if proof.get("requested_model") != proof.get("policy_model"):
        violations.append(_violation("child_agent_creation_proofs.model", "Requested model must match policy model."))
    if proof.get("requested_reasoning_effort") != proof.get("policy_reasoning_budget"):
        violations.append(_violation("child_agent_creation_proofs.reasoning", "Requested reasoning must match policy budget."))

def _check_front_output(output: dict[str, Any], *, child_by_key: dict[tuple[str, str], dict[str, Any]], branch_by_group: dict[str, dict[str, Any]], violations: list[dict[str, Any]]) -> None:
    group_id = str(output.get("group_id", ""))
    proof = child_by_key.get(("execution_front_agent", group_id), {})
    branch = branch_by_group.get(group_id, {})
    if output.get("role_id") != "execution_front_agent":
        violations.append(_violation("front_outputs.role_id", "Front output role_id must be execution_front_agent."))
    if not _is_skill_ref(_ref(output.get("skill_ref")), FRONT_SKILL_ID):
        violations.append(_violation("front_outputs.skill_ref", "Front output must reference Front skill v0.3."))
    if output.get("skill_received") is not True or output.get("skill_applied") is not True:
        violations.append(_violation("front_outputs.skill_received", "Front output must prove skill receipt/application."))
    if _is_missing(output.get("thread_id")):
        violations.append(_violation("front_outputs.thread_id", "Final Front output requires non-empty thread_id."))
    elif proof and output.get("thread_id") != proof.get("thread_id"):
        violations.append(_violation("front_outputs.thread_id", "Front thread_id must match creation proof."))
    for key in ("group_workspace", "group_work_branch", "base_commit", "commit_sha", "branch_diff_ref", "group_branch_proof_ref", "implementation_summary", "touched_files", "local_test_evidence", "group_causal_fork"):
        if key not in output or _is_missing(output.get(key)):
            violations.append(_violation(f"front_outputs.{key}", "Front output missing required field."))
    if _is_missing(output.get("child_agent_creation_proof_ref")):
        violations.append(_violation("front_outputs.child_agent_creation_proof_ref", "Front output requires child_agent_creation_proof_ref."))
    if branch and output.get("group_work_branch") != branch.get("group_work_branch"):
        violations.append(_violation("front_outputs.group_work_branch", "Front output branch must match group branch proof."))
    if branch and output.get("base_commit") != branch.get("base_commit"):
        violations.append(_violation("front_outputs.base_commit", "Front output base_commit must match group branch proof."))
    if output.get("worked_on_aegis_work_branch") is True or output.get("self_approved") is True:
        violations.append(_violation("front_outputs.boundary", "Front must not work on baseline branch or self-approve."))
    if _ref(output.get("group_causal_fork")).get("status") != "causal_candidate":
        violations.append(_violation("front_outputs.group_causal_fork.status", "Front causal fork must remain causal_candidate."))
    _check_forbidden_true_fields(output, "front_outputs", violations)


def _check_back_review(
    review: dict[str, Any],
    *,
    child_by_key: dict[tuple[str, str], dict[str, Any]],
    branch_by_group: dict[str, dict[str, Any]],
    front_by_group: dict[str, dict[str, Any]],
    violations: list[dict[str, Any]],
) -> None:
    group_id = str(review.get("group_id", ""))
    proof = child_by_key.get(("execution_back_agent", group_id), {})
    branch = branch_by_group.get(group_id, {})
    front = front_by_group.get(group_id, {})
    if review.get("role_id") != "execution_back_agent":
        violations.append(_violation("back_reviews.role_id", "Back review role_id must be execution_back_agent."))
    if not _is_skill_ref(_ref(review.get("skill_ref")), BACK_SKILL_ID):
        violations.append(_violation("back_reviews.skill_ref", "Back review must reference Back skill v0.3."))
    if review.get("skill_received") is not True or review.get("skill_applied") is not True:
        violations.append(_violation("back_reviews.skill_received", "Back review must prove skill receipt/application."))
    if _is_missing(review.get("thread_id")):
        violations.append(_violation("back_reviews.thread_id", "Final Back review requires non-empty thread_id."))
    elif proof and review.get("thread_id") != proof.get("thread_id"):
        violations.append(_violation("back_reviews.thread_id", "Back thread_id must match creation proof."))

    required_non_empty = (
        "child_agent_creation_proof_ref",
        "audit_workspace",
        "reviewed_branch",
        "reviewed_commit_sha",
        "base_commit",
        "review_decision",
        "review_summary",
        "evidence_checked",
    )
    for key in required_non_empty:
        if key not in review or _is_missing(review.get(key)):
            violations.append(_violation(f"back_reviews.{key}", "Back review missing required field."))

    # These fields must exist, but empty lists are valid when there are no blockers or no residual risk notes.
    for key in ("blocking_objections", "risk_notes"):
        if key not in review:
            violations.append(_violation(f"back_reviews.{key}", "Back review missing required field."))

    required_true_fields = (
        "branch_proof_checked",
        "branch_diff_checked",
        "touched_files_checked",
        "local_test_evidence_checked",
        "contract_checked",
        "first_principles_checked",
        "scope_checked",
        "risk_checked",
    )
    for key in required_true_fields:
        _require_true(review.get(key), f"back_reviews.{key}", violations, f"Back review requires {key}=true.")

    if branch and review.get("reviewed_branch") != branch.get("group_work_branch"):
        violations.append(_violation("back_reviews.reviewed_branch", "Back must review real group_work_branch."))
    if front and review.get("reviewed_commit_sha") != front.get("commit_sha"):
        violations.append(_violation("back_reviews.reviewed_commit_sha", "Back reviewed_commit_sha must match Front commit_sha."))
    if front and front.get("branch_diff_ref") not in (review.get("evidence_checked") or []):
        violations.append(_violation("back_reviews.evidence_checked", "Back evidence_checked must include Front branch_diff_ref."))
    if branch and review.get("audit_workspace") == branch.get("workspace_path") and review.get("same_workspace_exception_used") is not True:
        violations.append(_violation("back_reviews.audit_workspace", "Back same-workspace review requires a recorded exception."))
    if review.get("branch_derives_from_base_commit") is not True:
        violations.append(_violation("back_reviews.branch_derives_from_base_commit", "Back must verify branch derives from base_commit."))
    if review.get("branch_is_orphan") is not False or review.get("branch_is_unborn") is not False:
        violations.append(_violation("back_reviews.branch_state", "Back must reject orphan/unborn branches."))
    if review.get("review_decision") not in ALLOWED_REVIEW_DECISIONS:
        violations.append(_violation("back_reviews.review_decision", "Back review decision is invalid."))
    if review.get("same_workspace_exception_used") is True:
        exception = _ref(review.get("same_workspace_exception"))
        for key in ("approved_by", "reason", "exception_record_ref"):
            if _is_missing(exception.get(key)):
                violations.append(_violation(f"back_reviews.same_workspace_exception.{key}", "Same-workspace exception missing required field."))
        if exception.get("approved_by") != "execution_leader" or exception.get("read_only_review_mode") is not True or exception.get("implementation_modified_by_back") is not False or exception.get("no_new_commit_by_back") is not True:
            violations.append(_violation("back_reviews.same_workspace_exception", "Same-workspace exception is not audit-safe."))
    if review.get("implementation_modified_by_back") is True or review.get("no_new_commit_by_back") is not True:
        violations.append(_violation("back_reviews.implementation_modified_by_back", "Back must not modify implementation or create commits by default."))
    _check_forbidden_true_fields(review, "back_reviews", violations)


def _check_forbidden_true_fields(payload: dict[str, Any], prefix: str, violations: list[dict[str, Any]]) -> None:
    for field in FORBIDDEN_OUTPUT_TRUE_FIELDS:
        if payload.get(field) is True:
            violations.append(_violation(f"{prefix}.{field}", f"{field} must remain false."))

def _check_skill_file(path: str | Path, *, skill_id: str, field: str, violations: list[dict[str, Any]]) -> None:
    p = Path(path)
    if not p.is_file():
        violations.append(_violation(field, f"Skill file not found: {p}"))
        return
    text = p.read_text(encoding="utf-8")
    if f"skill_id: {skill_id}" not in text:
        violations.append(_violation(field, f"Skill file missing skill_id {skill_id}."))
    if f"skill_version: {SKILL_VERSION}" not in text:
        violations.append(_violation(field, f"Skill file missing skill_version {SKILL_VERSION}."))


def _is_skill_ref(ref: dict[str, Any], skill_id: str) -> bool:
    return ref.get("skill_id") == skill_id and ref.get("skill_version") == SKILL_VERSION


def _ref(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_dict_list(value: Any, field: str, violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        violations.append(_violation(field, f"{field} must be a list."))
        return []
    output = []
    for item in value:
        if isinstance(item, dict):
            output.append(dict(item))
        else:
            violations.append(_violation(field, f"{field} contains non-object item."))
    return output


def _violation(field: str, reason: str) -> dict[str, Any]:
    return {"field": field, "reason": reason}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Aegis Execution role operational skill enforcement.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate one Execution skill run JSON artifact.")
    validate.add_argument("--run", required=True)
    validate.add_argument("--leader-skill")
    validate.add_argument("--front-skill")
    validate.add_argument("--back-skill")
    validate.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "validate":
        result = validate_execution_skill_run_file(
            args.run,
            leader_skill_path=args.leader_skill,
            front_skill_path=args.front_skill,
            back_skill_path=args.back_skill,
        ).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
