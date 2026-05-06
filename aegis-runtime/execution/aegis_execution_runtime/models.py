from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

DecisionLabel = Literal[
    "request_more_context",
    "request_test_measurement",
    "request_debate",
    "send_implementation_candidate_to_test",
    "request_failure_evidence",
    "triage_required",
    "resolve_internal_review_dispute",
    "governance_blocker_to_master",
    "submit_causal_fork_to_master",
    "map_to_group",
    "map_to_integration_owner",
    "rework_required",
    "release_groups",
    "accept",
]

ReviewDecision = Literal["accept", "reject", "request_changes", "request_more_evidence", "scope_violation", "contract_violation"]
GroupStatus = Literal[
    "CREATED",
    "IMPLEMENTING",
    "MODULE_TESTING",
    "INTERNAL_REVIEW",
    "READY_FOR_LEADER",
    "INTEGRATED",
    "UNDER_TEST",
    "REWORK_REQUIRED",
    "REWORKING",
    "REINTEGRATED",
    "ACCEPTED",
    "RELEASED",
]

CausalNodeType = Literal[
    "premise",
    "plan",
    "debate_adjudication",
    "split",
    "group_implementation",
    "back_review",
    "integration",
    "test_feedback",
    "rework",
    "risk",
    "invalidation_condition",
    "conclusion",
]

CausalRelation = Literal[
    "supports",
    "depends_on",
    "validates",
    "rejects",
    "maps_to",
    "requires_rework",
    "resolves",
    "narrows_scope",
    "creates_risk",
    "reopens_if",
]


class ExecutionContractError(ValueError):
    """Raised when the Execution runtime violates the department contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_string(value: Any, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ExecutionContractError(f"{name} must be a {'possibly empty ' if allow_empty else ''}string")
    return value


def _ensure_string_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ExecutionContractError(f"{name} must be a list of non-empty strings")
    return list(value)


@dataclass(frozen=True)
class EvidenceRef:
    type: str
    ref: str
    relevance: str = ""

    @classmethod
    def from_any(cls, value: Any) -> "EvidenceRef":
        if isinstance(value, str):
            return cls(type="reference", ref=value, relevance="provided by caller")
        if isinstance(value, dict):
            return cls(
                type=_ensure_string(value.get("type", "reference"), "evidence.type"),
                ref=_ensure_string(value.get("ref"), "evidence.ref"),
                relevance=_ensure_string(value.get("relevance", ""), "evidence.relevance", allow_empty=True),
            )
        raise ExecutionContractError("evidence entries must be strings or objects")

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "ref": self.ref, "relevance": self.relevance}


@dataclass(frozen=True)
class CandidatePlan:
    plan_id: str
    claim: str
    why: str
    valid_under_contracts: bool = True
    dominated: bool = False
    contract_violation: bool = False
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    risk_if_wrong: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int) -> "CandidatePlan":
        if not isinstance(value, dict):
            raise ExecutionContractError("candidate plan must be an object")
        return cls(
            plan_id=_ensure_string(value.get("plan_id") or f"P{index + 1}", "plan.plan_id"),
            claim=_ensure_string(value.get("claim"), "plan.claim"),
            why=_ensure_string(value.get("why"), "plan.why"),
            valid_under_contracts=bool(value.get("valid_under_contracts", True)),
            dominated=bool(value.get("dominated", False)),
            contract_violation=bool(value.get("contract_violation", False)),
            strengths=_ensure_string_list(value.get("strengths", []), "plan.strengths"),
            weaknesses=_ensure_string_list(value.get("weaknesses", []), "plan.weaknesses"),
            evidence=[EvidenceRef.from_any(item) for item in value.get("evidence", [])],
            risk_if_wrong=_ensure_string(value.get("risk_if_wrong", ""), "plan.risk_if_wrong", allow_empty=True),
        )

    def is_debate_candidate(self) -> bool:
        return self.valid_under_contracts and not self.contract_violation and not self.dominated

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "claim": self.claim,
            "why": self.why,
            "valid_under_contracts": self.valid_under_contracts,
            "dominated": self.dominated,
            "contract_violation": self.contract_violation,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "evidence": [item.to_dict() for item in self.evidence],
            "risk_if_wrong": self.risk_if_wrong,
        }


@dataclass(frozen=True)
class FileChangeSpec:
    path: str
    content: str
    change_type: Literal["add", "modify", "delete"] = "modify"
    why_changed: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FileChangeSpec":
        if not isinstance(value, dict):
            raise ExecutionContractError("file change must be an object")
        change_type = value.get("change_type", "modify")
        if change_type not in {"add", "modify", "delete"}:
            raise ExecutionContractError("file change_type must be add, modify, or delete")
        path = _ensure_string(value.get("path"), "file_change.path")
        if path.startswith("/") or ".." in Path(path).parts:
            raise ExecutionContractError("file_change.path must be repository-relative and safe")
        return cls(
            path=path,
            content=_ensure_string(value.get("content", ""), "file_change.content", allow_empty=True),
            change_type=change_type,
            why_changed=_ensure_string(value.get("why_changed", ""), "file_change.why_changed", allow_empty=True),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "content": self.content,
            "change_type": self.change_type,
            "why_changed": self.why_changed,
        }


@dataclass(frozen=True)
class SubtaskSpec:
    subtask_id: str
    responsibility: str
    owned_files_or_modules: list[str]
    input_contract: str
    output_contract: str
    dependencies: list[str]
    independence_reason: str
    local_success_criteria: list[str]
    expected_branch: str
    merge_risk: Literal["low", "medium", "high"]
    feedback_mapping_rule: str
    file_changes: list[FileChangeSpec]

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int) -> "SubtaskSpec":
        if not isinstance(value, dict):
            raise ExecutionContractError("subtask must be an object")
        merge_risk = value.get("merge_risk", "medium")
        if merge_risk not in {"low", "medium", "high"}:
            raise ExecutionContractError("subtask.merge_risk must be low, medium, or high")
        return cls(
            subtask_id=_ensure_string(value.get("subtask_id") or f"S{index + 1}", "subtask.subtask_id"),
            responsibility=_ensure_string(value.get("responsibility"), "subtask.responsibility"),
            owned_files_or_modules=_ensure_string_list(
                value.get("owned_files_or_modules", []), "subtask.owned_files_or_modules"
            ),
            input_contract=_ensure_string(value.get("input_contract"), "subtask.input_contract"),
            output_contract=_ensure_string(value.get("output_contract"), "subtask.output_contract"),
            dependencies=_ensure_string_list(value.get("dependencies", []), "subtask.dependencies"),
            independence_reason=_ensure_string(value.get("independence_reason"), "subtask.independence_reason"),
            local_success_criteria=_ensure_string_list(
                value.get("local_success_criteria", []), "subtask.local_success_criteria"
            ),
            expected_branch=_ensure_string(value.get("expected_branch"), "subtask.expected_branch"),
            merge_risk=merge_risk,
            feedback_mapping_rule=_ensure_string(value.get("feedback_mapping_rule"), "subtask.feedback_mapping_rule"),
            file_changes=[FileChangeSpec.from_dict(item) for item in value.get("file_changes", [])],
        )

    def validate_split_readiness(self) -> None:
        if not self.owned_files_or_modules:
            raise ExecutionContractError(f"subtask {self.subtask_id} has no owned files/modules")
        if not self.local_success_criteria:
            raise ExecutionContractError(f"subtask {self.subtask_id} has no local success criteria")
        if not self.file_changes:
            raise ExecutionContractError(f"subtask {self.subtask_id} has no deterministic demo file changes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "responsibility": self.responsibility,
            "owned_files_or_modules": list(self.owned_files_or_modules),
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "dependencies": list(self.dependencies),
            "independence_reason": self.independence_reason,
            "local_success_criteria": list(self.local_success_criteria),
            "expected_branch": self.expected_branch,
            "merge_risk": self.merge_risk,
            "feedback_mapping_rule": self.feedback_mapping_rule,
            "file_changes": [item.to_dict() for item in self.file_changes],
        }


@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    sender: str
    objective: str
    scope: str
    constraints: list[str]
    applicable_contracts: list[str]
    success_criteria: list[str]
    forbidden_actions: list[str]
    base_branch: str
    candidate_plans: list[CandidatePlan]
    subtasks: list[SubtaskSpec]
    evidence: list[EvidenceRef] = field(default_factory=list)
    requires_measurement: bool = False
    required_measurements: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExecutionRequest":
        if not isinstance(value, dict):
            raise ExecutionContractError("execution request must be an object")
        return cls(
            request_id=_ensure_string(value.get("request_id") or f"execution-run-{uuid4().hex}", "request.request_id"),
            sender=_ensure_string(value.get("sender", "unknown"), "request.sender"),
            objective=_ensure_string(value.get("objective", ""), "request.objective", allow_empty=True),
            scope=_ensure_string(value.get("scope", ""), "request.scope", allow_empty=True),
            constraints=_ensure_string_list(value.get("constraints", []), "request.constraints"),
            applicable_contracts=_ensure_string_list(value.get("applicable_contracts", []), "request.applicable_contracts"),
            success_criteria=_ensure_string_list(value.get("success_criteria", []), "request.success_criteria"),
            forbidden_actions=_ensure_string_list(value.get("forbidden_actions", []), "request.forbidden_actions"),
            base_branch=_ensure_string(value.get("base_branch", "v0.1.0-alpha"), "request.base_branch"),
            candidate_plans=[CandidatePlan.from_dict(item, idx) for idx, item in enumerate(value.get("candidate_plans", []))],
            subtasks=[SubtaskSpec.from_dict(item, idx) for idx, item in enumerate(value.get("subtasks", []))],
            evidence=[EvidenceRef.from_any(item) for item in value.get("evidence", [])],
            requires_measurement=bool(value.get("requires_measurement", False)),
            required_measurements=_ensure_string_list(value.get("required_measurements", []), "request.required_measurements"),
        )

    def has_admission_context(self) -> bool:
        return bool(self.objective and self.scope and self.success_criteria)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "sender": self.sender,
            "objective": self.objective,
            "scope": self.scope,
            "constraints": list(self.constraints),
            "applicable_contracts": list(self.applicable_contracts),
            "success_criteria": list(self.success_criteria),
            "forbidden_actions": list(self.forbidden_actions),
            "base_branch": self.base_branch,
            "candidate_plans": [item.to_dict() for item in self.candidate_plans],
            "subtasks": [item.to_dict() for item in self.subtasks],
            "evidence": [item.to_dict() for item in self.evidence],
            "requires_measurement": self.requires_measurement,
            "required_measurements": list(self.required_measurements),
        }


@dataclass
class ExecutionGroupRecord:
    group_id: str
    subtask_id: str
    branch_name: str
    workspace_path: str
    front_agent_id: str
    back_agent_id: str
    status: GroupStatus = "CREATED"
    touched_files: list[str] = field(default_factory=list)
    local_tests: list[dict[str, Any]] = field(default_factory=list)
    back_review: dict[str, Any] = field(default_factory=dict)
    causal_fork: dict[str, Any] = field(default_factory=dict)
    rework_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "subtask_id": self.subtask_id,
            "branch_name": self.branch_name,
            "workspace_path": self.workspace_path,
            "front_agent_id": self.front_agent_id,
            "back_agent_id": self.back_agent_id,
            "status": self.status,
            "touched_files": list(self.touched_files),
            "local_tests": list(self.local_tests),
            "back_review": dict(self.back_review),
            "causal_fork": dict(self.causal_fork),
            "rework_history": list(self.rework_history),
        }


@dataclass(frozen=True)
class TestFeedback:
    feedback_id: str
    result: Literal["passed", "failed"]
    feedback_kind: Literal["success", "failure"]
    evidence_refs: list[str]
    covered_scope: list[str]
    uncovered_scope: list[str] = field(default_factory=list)
    owner_type: Literal["group", "integration", "ambiguous", "missing_evidence", "none"] = "none"
    owner_id: str = ""
    required_fix: str = ""
    why: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TestFeedback":
        if not isinstance(value, dict):
            raise ExecutionContractError("test feedback must be an object")
        result = value.get("result")
        if result not in {"passed", "failed"}:
            raise ExecutionContractError("test feedback result must be passed or failed")
        feedback_kind = value.get("feedback_kind")
        if feedback_kind is None:
            feedback_kind = "success" if result == "passed" else "failure"
        if feedback_kind not in {"success", "failure"}:
            raise ExecutionContractError("test feedback feedback_kind must be success or failure")
        if (result == "passed" and feedback_kind != "success") or (result == "failed" and feedback_kind != "failure"):
            raise ExecutionContractError("test feedback feedback_kind must match result")
        owner_type = value.get("owner_type", "none")
        if owner_type not in {"group", "integration", "ambiguous", "missing_evidence", "none"}:
            raise ExecutionContractError("test feedback owner_type is invalid")
        return cls(
            feedback_id=_ensure_string(value.get("feedback_id") or f"test-feedback-{uuid4().hex}", "feedback.feedback_id"),
            result=result,
            feedback_kind=feedback_kind,
            evidence_refs=_ensure_string_list(value.get("evidence_refs", []), "feedback.evidence_refs"),
            covered_scope=_ensure_string_list(value.get("covered_scope", []), "feedback.covered_scope"),
            uncovered_scope=_ensure_string_list(value.get("uncovered_scope", []), "feedback.uncovered_scope"),
            owner_type=owner_type,
            owner_id=_ensure_string(value.get("owner_id", ""), "feedback.owner_id", allow_empty=True),
            required_fix=_ensure_string(value.get("required_fix", ""), "feedback.required_fix", allow_empty=True),
            why=_ensure_string(value.get("why", ""), "feedback.why", allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "result": self.result,
            "feedback_kind": self.feedback_kind,
            "evidence_refs": list(self.evidence_refs),
            "covered_scope": list(self.covered_scope),
            "uncovered_scope": list(self.uncovered_scope),
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "required_fix": self.required_fix,
            "why": self.why,
        }


@dataclass
class ExecutionRunState:
    run_id: str
    request: ExecutionRequest
    decision: DecisionLabel
    selected_plan: CandidatePlan | None
    groups: list[ExecutionGroupRecord]
    integration_candidate: dict[str, Any]
    private_root: str
    test_feedback_history: list[dict[str, Any]] = field(default_factory=list)
    status: str = "WAITING_FOR_TEST"
    debate_reference: dict[str, Any] = field(default_factory=dict)

    def group_by_id(self, group_id: str) -> ExecutionGroupRecord:
        for group in self.groups:
            if group.group_id == group_id:
                return group
        raise ExecutionContractError(f"unknown execution group: {group_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "request": self.request.to_dict(),
            "decision": self.decision,
            "selected_plan": self.selected_plan.to_dict() if self.selected_plan else None,
            "groups": [group.to_dict() for group in self.groups],
            "integration_candidate": dict(self.integration_candidate),
            "private_root": self.private_root,
            "test_feedback_history": list(self.test_feedback_history),
            "status": self.status,
            "debate_reference": dict(self.debate_reference),
        }


@dataclass(frozen=True)
class FinalExecutionReport:
    run_id: str
    request_id: str
    decision: DecisionLabel
    final_status: Literal["test_passed", "needs_rework", "blocked", "needs_context", "needs_debate", "needs_measurement"]
    selected_plan: dict[str, Any] | None
    implementation_candidate: dict[str, Any] | None
    group_records: list[dict[str, Any]]
    test_feedback_history: list[dict[str, Any]]
    execution_causal_chain: dict[str, Any]
    next_action: dict[str, str]
    artifact_paths: dict[str, str]
    created_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if self.decision == "submit_causal_fork_to_master" and self.final_status != "test_passed":
            raise ExecutionContractError("submit_causal_fork_to_master requires final_status == test_passed")
        if self.next_action.get("target") not in {"master", "test", "debate", "execution", "none"}:
            raise ExecutionContractError("final report next_action.target is invalid")
        chain = self.execution_causal_chain
        required = ["chain_id", "source_request_id", "decision_problem", "nodes", "edges", "selected_path", "invalidation_entrypoints", "status"]
        missing = [key for key in required if key not in chain]
        if missing:
            raise ExecutionContractError(f"execution_causal_chain missing field(s): {', '.join(missing)}")
        if chain.get("status") != "causal_candidate":
            raise ExecutionContractError("execution causal chain must remain causal_candidate")
        nodes = chain.get("nodes")
        edges = chain.get("edges")
        if not isinstance(nodes, list) or not nodes:
            raise ExecutionContractError("execution_causal_chain.nodes must be non-empty")
        if not isinstance(edges, list) or not edges:
            raise ExecutionContractError("execution_causal_chain.edges must be non-empty")
        node_ids = {node.get("id") for node in nodes if isinstance(node, dict)}
        for edge in edges:
            if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
                raise ExecutionContractError("execution_causal_chain edge endpoint must reference a node")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "decision": self.decision,
            "final_status": self.final_status,
            "selected_plan": self.selected_plan,
            "implementation_candidate": self.implementation_candidate,
            "group_records": list(self.group_records),
            "test_feedback_history": list(self.test_feedback_history),
            "execution_causal_chain": self.execution_causal_chain,
            "next_action": dict(self.next_action),
            "artifact_paths": dict(self.artifact_paths),
            "created_at": self.created_at,
        }
