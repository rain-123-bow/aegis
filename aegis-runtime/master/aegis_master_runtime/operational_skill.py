from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SKILL_ID = "MASTER_OPERATIONAL_WORKFLOW_SKILL"
SKILL_VERSION = "v0.3"
PHASE = "phase24a_master_operational_workflow_skill_enforcement"
ALLOWED_MODELS = {"gpt-5.5", "gpt-5.4"}
PRIMARY_MODEL = "gpt-5.5"
FALLBACK_MODEL = "gpt-5.4"
ALLOWED_BUDGETS = {"high", "extra_high"}
VALID_INTAKE_CLASSIFICATIONS = {
    "question_only",
    "new_task_request",
    "task_update",
    "task_scope_change",
    "developer_decision",
    "commit_intent",
    "delivery_intent",
    "stable_fact_or_constraint",
    "causal_claim",
    "correction_or_amendment",
    "evidence_submission",
    "resource_or_policy_issue",
    "tooling_runtime_issue",
}
VALID_TASK_BOUNDARY_DECISIONS = {
    "create",
    "bind",
    "aggregate",
    "split",
    "planning_only",
    "reject",
    "defer",
    "question_only",
}
VALID_DEPARTMENTS = {None, "debate", "execution", "test", "final_review"}
VALID_TIMEOUT_STATES = {
    "none",
    "launcher_timeout",
    "child_thread_alive",
    "child_completed_late",
    "result_recovered",
    "child_failed",
    "proof_missing_after_final_deadline",
}


class MasterOperationalSkillError(ValueError):
    """Raised when Phase 24A Master operational skill input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MasterOperationalSkillValidationResult:
    validation_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    cycle_id: str
    skill_id: str | None
    skill_version: str | None
    checked_rule_count: int
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    required_archive_event_count: int = 0
    archive_event_candidate_count: int = 0
    knowledge_candidate_count: int = 0
    causal_candidate_count: int = 0
    production_master_autonomy_claimed: bool = False
    remote_push_performed: bool = False
    pr_created: bool = False
    remote_merge_performed: bool = False
    release_performed: bool = False
    global_causal_truth_merge_performed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_result_id": self.validation_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "cycle_id": self.cycle_id,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "checked_rule_count": self.checked_rule_count,
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "required_archive_event_count": self.required_archive_event_count,
            "archive_event_candidate_count": self.archive_event_candidate_count,
            "knowledge_candidate_count": self.knowledge_candidate_count,
            "causal_candidate_count": self.causal_candidate_count,
            "production_master_autonomy_claimed": self.production_master_autonomy_claimed,
            "remote_push_performed": self.remote_push_performed,
            "pr_created": self.pr_created,
            "remote_merge_performed": self.remote_merge_performed,
            "release_performed": self.release_performed,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MasterOperationalSkillError(f"Master cycle file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise MasterOperationalSkillError(f"Master cycle file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MasterOperationalSkillError("Master cycle file must contain a JSON object")
    return payload


def validate_master_operational_cycle_file(
    cycle_path: str | Path,
    *,
    skill_path: str | Path | None = None,
) -> MasterOperationalSkillValidationResult:
    return validate_master_operational_cycle(load_json_object(cycle_path), skill_path=skill_path)


def validate_master_operational_cycle(
    cycle: dict[str, Any],
    *,
    skill_path: str | Path | None = None,
) -> MasterOperationalSkillValidationResult:
    if not isinstance(cycle, dict):
        raise MasterOperationalSkillError("cycle must be a JSON object")

    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checked = 0

    skill_ref = _as_mapping(cycle.get("skill_ref"), "skill_ref", violations)
    skill_id = _string(skill_ref.get("skill_id")) if skill_ref else None
    skill_version = _string(skill_ref.get("skill_version")) if skill_ref else None
    cycle_id = _string(cycle.get("cycle_id")) or f"cycle-{uuid4().hex}"

    if skill_path is not None:
        checked += 1
        _check_skill_file(skill_path, violations)

    checked += 1
    if skill_id != SKILL_ID or skill_version != SKILL_VERSION:
        violations.append(_violation("skill_ref", "skill_ref must reference MASTER_OPERATIONAL_WORKFLOW_SKILL v0.3"))

    checked += 1
    if cycle.get("master_role_id") != "master":
        violations.append(_violation("master_role_id", "Master operational cycle must be owned by role_id=master"))

    checked += 1
    classification = _string(cycle.get("user_input_classification"))
    if classification not in VALID_INTAKE_CLASSIFICATIONS:
        violations.append(_violation("user_input_classification", "user input must be classified before Master responds"))

    task_boundary = _as_mapping(cycle.get("task_boundary"), "task_boundary", violations)
    checked += 1
    _check_task_boundary(cycle, task_boundary, violations, warnings)

    checked += 1
    _check_required_candidates(cycle, violations)

    checked += 1
    _check_model_policy_resolution(cycle.get("model_policy_resolution", []), violations)

    checked += 1
    _check_department_dispatch(cycle.get("department_dispatch", {}), violations)

    checked += 1
    _check_supervision(cycle.get("supervision", {}), violations)

    checked += 1
    _check_commit_gate(cycle.get("commit_gate", {}), cycle, violations)

    checked += 1
    _check_responsibility_boundary(cycle.get("responsibility_boundary", {}), violations)

    checked += 1
    _check_forbidden_global_flags(cycle, violations)

    archive_candidates = _as_list(cycle.get("archive_event_candidates", []))
    knowledge_candidates = _as_list(cycle.get("knowledge_candidates", []))
    causal_candidates = _as_list(cycle.get("causal_candidates", []))
    required_archive_events = 1 if cycle.get("requires_archive_event") is True else 0

    status = "validated" if not violations else "rejected"
    decision = "accepted_master_operational_workflow_skill_enforcement" if not violations else "rejected"
    reason = "Master operational cycle satisfies the role-bound skill gates." if not violations else "Master operational cycle violates the role-bound skill gates."

    commit_gate = cycle.get("commit_gate", {}) if isinstance(cycle.get("commit_gate", {}), dict) else {}
    return MasterOperationalSkillValidationResult(
        validation_result_id=f"master-skill-validation-{uuid4().hex}",
        phase=PHASE,
        status=status,
        decision=decision,
        reason=reason,
        cycle_id=cycle_id,
        skill_id=skill_id,
        skill_version=skill_version,
        checked_rule_count=checked,
        violations=violations,
        warnings=warnings,
        required_archive_event_count=required_archive_events,
        archive_event_candidate_count=len(archive_candidates),
        knowledge_candidate_count=len(knowledge_candidates),
        causal_candidate_count=len(causal_candidates),
        production_master_autonomy_claimed=bool(cycle.get("production_master_autonomy_claimed", False)),
        remote_push_performed=bool(commit_gate.get("remote_push_performed", False)),
        pr_created=bool(commit_gate.get("pr_created", False)),
        remote_merge_performed=bool(commit_gate.get("remote_merge_performed", False)),
        release_performed=bool(commit_gate.get("release_performed", False)),
        global_causal_truth_merge_performed=bool(cycle.get("global_causal_truth_merge_performed", False)),
    )


def _check_skill_file(skill_path: str | Path, violations: list[dict[str, Any]]) -> None:
    path = Path(skill_path)
    if not path.is_file():
        violations.append(_violation("skill_path", f"skill file does not exist: {path}"))
        return
    text = path.read_text(encoding="utf-8")
    required_markers = [
        "MASTER_OPERATIONAL_WORKFLOW_SKILL v0.3",
        "Every user message triggers Master Intake",
        "Task identity is commit-bound",
        "Reasoning budget must not downgrade",
        "Models below `gpt-5.4` are forbidden",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        violations.append(_violation("skill_path", f"skill file is missing marker(s): {', '.join(missing)}"))


def _check_task_boundary(cycle: dict[str, Any], task_boundary: dict[str, Any], violations: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    if not task_boundary:
        return
    decision = _string(task_boundary.get("decision"))
    if decision not in VALID_TASK_BOUNDARY_DECISIONS:
        violations.append(_violation("task_boundary.decision", "task boundary decision must be explicit"))
    if cycle.get("requires_task") is True and decision in {"question_only", "planning_only", "reject", "defer"}:
        violations.append(_violation("task_boundary.decision", "task-like input cannot remain question_only/planning_only/reject/defer without explicit no-execution boundary"))
    if task_boundary.get("existing_archived_tasks_merged") is True:
        violations.append(_violation("task_boundary.existing_archived_tasks_merged", "existing archived tasks must not be merged"))
    if task_boundary.get("aggregation_after_archive") is True:
        violations.append(_violation("task_boundary.aggregation_after_archive", "aggregation is allowed only before formal Archive task creation"))
    final_task_ids = _as_list(task_boundary.get("final_archive_task_ids", []))
    if decision in {"create", "bind", "aggregate", "split"} and not final_task_ids:
        violations.append(_violation("task_boundary.final_archive_task_ids", "final commit-bound Archive task IDs are required"))
    if decision == "aggregate" and len(final_task_ids) != 1:
        violations.append(_violation("task_boundary.final_archive_task_ids", "aggregation must produce exactly one final Archive task"))
    if decision == "split" and len(final_task_ids) < 2:
        violations.append(_violation("task_boundary.final_archive_task_ids", "split must produce multiple final Archive tasks / commits"))
    commit_candidate_count = int(task_boundary.get("commit_candidate_count", 0) or 0)
    if commit_candidate_count > 0 and commit_candidate_count != len(final_task_ids):
        warnings.append(_warning("task_boundary.commit_candidate_count", "commit candidate count should match final Archive task count unless this cycle is only a partial planning cycle"))


def _check_required_candidates(cycle: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    if cycle.get("requires_archive_event") is True and not _as_list(cycle.get("archive_event_candidates", [])):
        violations.append(_violation("archive_event_candidates", "task lifecycle effects require at least one Archive event candidate"))
    if cycle.get("requires_knowledge_candidate") is True and not _as_list(cycle.get("knowledge_candidates", [])):
        violations.append(_violation("knowledge_candidates", "stable reusable facts/constraints require Knowledge candidate consideration"))
    if cycle.get("requires_causal_candidate") is True and not _as_list(cycle.get("causal_candidates", [])):
        violations.append(_violation("causal_candidates", "reusable project-direction judgment requires Causal candidate consideration"))


def _check_model_policy_resolution(value: Any, violations: list[dict[str, Any]]) -> None:
    resolutions = _as_list(value)
    if not resolutions:
        violations.append(_violation("model_policy_resolution", "Master must record model/reasoning policy resolution"))
        return
    for idx, item in enumerate(resolutions):
        if not isinstance(item, dict):
            violations.append(_violation(f"model_policy_resolution[{idx}]", "model policy resolution entry must be an object"))
            continue
        resolved_model = _string(item.get("resolved_model"))
        requested_model = _string(item.get("requested_model"))
        resolved_budget = _string(item.get("resolved_reasoning_budget"))
        requested_budget = _string(item.get("requested_reasoning_budget"))
        policy_budget = _string(item.get("policy_reasoning_budget"))
        fallback_used = item.get("fallback_used") is True

        if not requested_model:
            violations.append(_violation(f"model_policy_resolution[{idx}].requested_model", "requested_model is required; provider-default fallback is forbidden"))
        if resolved_model not in ALLOWED_MODELS:
            violations.append(_violation(f"model_policy_resolution[{idx}].resolved_model", "resolved model must be gpt-5.5 or explicit gpt-5.4 fallback; models below gpt-5.4 are forbidden"))
        if requested_model and requested_model not in ALLOWED_MODELS:
            violations.append(_violation(f"model_policy_resolution[{idx}].requested_model", "requested model must be gpt-5.5 or gpt-5.4; models below gpt-5.4 are forbidden"))
        if resolved_budget not in ALLOWED_BUDGETS or requested_budget not in ALLOWED_BUDGETS or policy_budget not in ALLOWED_BUDGETS:
            violations.append(_violation(f"model_policy_resolution[{idx}].reasoning_budget", "reasoning budget must be high or extra_high for current Master skill roles"))
        if resolved_budget != policy_budget:
            violations.append(_violation(f"model_policy_resolution[{idx}].resolved_reasoning_budget", "reasoning budget downgrade or mismatch is forbidden"))
        if fallback_used:
            if not (requested_model == PRIMARY_MODEL and resolved_model == FALLBACK_MODEL):
                violations.append(_violation(f"model_policy_resolution[{idx}].fallback_used", "fallback is allowed only from gpt-5.5 to gpt-5.4"))
            if not _string(item.get("fallback_reason")) or not _as_list(item.get("fallback_evidence_refs", [])):
                violations.append(_violation(f"model_policy_resolution[{idx}].fallback_evidence_refs", "explicit fallback requires reason and evidence refs"))
        else:
            if requested_model and resolved_model and requested_model != resolved_model:
                violations.append(_violation(f"model_policy_resolution[{idx}].resolved_model", "model mismatch without explicit fallback is forbidden"))


def _check_department_dispatch(value: Any, violations: list[dict[str, Any]]) -> None:
    dispatch = value if isinstance(value, dict) else {}
    target = dispatch.get("target_department")
    if target not in VALID_DEPARTMENTS:
        violations.append(_violation("department_dispatch.target_department", "target_department must be debate, execution, test, final_review, or null"))
    if dispatch.get("master_created_internal_worker") is True:
        violations.append(_violation("department_dispatch.master_created_internal_worker", "Master must not directly create department-internal workers"))
    if dispatch.get("master_created_top_level_leader_only") is False and target is not None:
        violations.append(_violation("department_dispatch.master_created_top_level_leader_only", "Master may create/call only top-level department Leaders"))
    if dispatch.get("model_policy_checked") is False and target is not None:
        violations.append(_violation("department_dispatch.model_policy_checked", "department dispatch requires model policy check"))


def _check_supervision(value: Any, violations: list[dict[str, Any]]) -> None:
    supervision = value if isinstance(value, dict) else {}
    state = _string(supervision.get("nested_codex_timeout_state")) or "none"
    if state not in VALID_TIMEOUT_STATES:
        violations.append(_violation("supervision.nested_codex_timeout_state", "timeout state is invalid"))
    if state in {"launcher_timeout", "child_thread_alive", "child_completed_late", "result_recovered"}:
        if supervision.get("thread_id_recorded") is not True:
            violations.append(_violation("supervision.thread_id_recorded", "threadId must be recorded for launcher timeout recovery"))
    if state == "launcher_timeout" and supervision.get("recovery_attempted") is not True:
        violations.append(_violation("supervision.recovery_attempted", "launcher_timeout must trigger recovery/polling before final failure"))
    if supervision.get("launcher_timeout_treated_as_agent_failed") is True:
        violations.append(_violation("supervision.launcher_timeout_treated_as_agent_failed", "tools/call timeout must not be treated as child-agent failure"))


def _check_commit_gate(value: Any, cycle: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    gate = value if isinstance(value, dict) else {}
    if cycle.get("requires_commit_gate") is True or gate.get("commit_candidate_requested") is True:
        if gate.get("exactly_one_archive_task_per_commit") is not True:
            violations.append(_violation("commit_gate.exactly_one_archive_task_per_commit", "each commit candidate must bind exactly one final Archive task"))
        if gate.get("developer_authorization_required") is not True:
            violations.append(_violation("commit_gate.developer_authorization_required", "developer authorization is required for real critical actions"))
    for field_name in ("remote_push_performed", "pr_created", "remote_merge_performed", "release_performed"):
        if gate.get(field_name) is True:
            violations.append(_violation(f"commit_gate.{field_name}", "Master skill must not perform remote push, PR, merge, or release"))


def _check_responsibility_boundary(value: Any, violations: list[dict[str, Any]]) -> None:
    boundary = value if isinstance(value, dict) else {}
    for field_name in (
        "developer_retains_remote_push",
        "developer_retains_main_merge",
        "developer_retains_release",
        "developer_retains_external_signoff",
    ):
        if boundary.get(field_name) is not True:
            violations.append(_violation(f"responsibility_boundary.{field_name}", "developer must retain critical real-world responsibility actions"))


def _check_forbidden_global_flags(cycle: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    forbidden_true = (
        "production_master_autonomy_claimed",
        "global_causal_truth_merge_performed",
        "production_release_authority_claimed",
        "external_signoff_performed_by_master",
    )
    for field_name in forbidden_true:
        if cycle.get(field_name) is True:
            violations.append(_violation(field_name, "Phase 24A skill enforcement must not claim production autonomy, release authority, sign-off, or global causal merge"))


def _as_mapping(value: Any, field_name: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    violations.append(_violation(field_name, f"{field_name} must be an object"))
    return {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _violation(field: str, reason: str) -> dict[str, Any]:
    return {"field": field, "reason": reason}


def _warning(field: str, reason: str) -> dict[str, Any]:
    return {"field": field, "reason": reason}
