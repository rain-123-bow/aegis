from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


TaskType = Literal["design", "implementation", "test", "review", "debug", "analysis"]
TaskBoundaryDecision = Literal["create", "bind", "split", "planning_only", "reject"]
RouteGrade = Literal["A", "B", "C", "D", "E", "F"]
ExpandGrade = Literal["A", "B", "C", "D"]
ExecutionStatus = Literal["not_started", "running", "blocked", "completed"]
TestResultStatus = Literal["passed", "passed_with_scope_limit", "failed", "blocked", "inconclusive"]
FinalReviewDecision = Literal[
    "accept_for_master",
    "accept_with_scope_limit",
    "request_test_expansion",
    "reject_to_execution",
    "request_more_evidence",
    "governance_blocker",
    "blocked_resource_policy",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CurrentQuery(StrictModel):
    query: str
    task_type: TaskType = "implementation"
    goal: str
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class TaskBoundary(StrictModel):
    decision: TaskBoundaryDecision
    task_ids: list[str] = Field(default_factory=list)
    commit_cardinality: Literal["one_task_one_commit"] = "one_task_one_commit"
    reason: str = ""


class SelectedFact(StrictModel):
    fact_id: str
    route_grade: RouteGrade
    expand_grade: ExpandGrade
    reason: str


class RouteExpandPlan(StrictModel):
    selected_facts: list[SelectedFact] = Field(default_factory=list)


class DebateRequestState(StrictModel):
    debate_required: bool = False
    requested_by: Literal["master", "execution_actor"] | None = None
    trigger_kind: list[str] = Field(default_factory=list)
    candidate_positions: list[str] = Field(default_factory=list)
    resume_target: Literal["master_review", "execution_resume"] | None = None


class DebateResult(StrictModel):
    decision: Literal["selected", "need_more_evidence"] = "selected"
    selected_position: str
    why: str
    status: Literal["causal_candidate"] = "causal_candidate"
    causal_package: dict[str, Any]


class ExecutionState(StrictModel):
    status: ExecutionStatus = "not_started"
    implementation_artifact_ref: str | None = None
    discovered_debate_need: bool = False
    rework_applied: bool = False
    blocked_reason: str | None = None
    adjudication_applied: bool = False


class TestRouteSpec(StrictModel):
    __test__: ClassVar[bool] = False

    route_id: str
    description: str
    superstep: str = "default"
    expected_result: TestResultStatus = "passed"


class TestGraphSpec(StrictModel):
    __test__: ClassVar[bool] = False

    spec_id: str = Field(default_factory=lambda: f"test-spec-{uuid4().hex[:8]}")
    routes: list[TestRouteSpec]
    integration_required: bool = False


class TestRouteResult(StrictModel):
    route_id: str
    superstep: str
    result: TestResultStatus
    evidence_ref: str


class TestFinalResult(StrictModel):
    result: TestResultStatus
    route_results: list[TestRouteResult]
    barrier_summary: str


class TestState(StrictModel):
    test_graph_spec_ref: str | None = None
    test_graph_spec: TestGraphSpec | None = None
    current_superstep: str | None = None
    route_results: list[TestRouteResult] = Field(default_factory=list)
    final_test_result: TestFinalResult | None = None
    run_count: int = 0


class FinalReviewResult(StrictModel):
    decision: FinalReviewDecision
    target: Literal["master"] = "master"
    why: str
    whole_chain_review: dict[str, Any] = Field(default_factory=dict)
    known_limits: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    global_causal_truth_merge_performed: bool = False
    workers_created: bool = False
    tests_run: bool = False
    code_modified: bool = False


class StoreCandidate(StrictModel):
    store: Literal["knowledge", "causal"]
    candidate_id: str = Field(default_factory=lambda: f"candidate-{uuid4().hex[:8]}")
    kind: str
    payload: dict[str, Any]
    artifact_ref: str | None = None
    created_at: str = Field(default_factory=utc_now)


class CommitGate(StrictModel):
    commit_candidate_requested: bool = False
    exactly_one_task_per_commit: bool = True
    developer_authorization_required: bool = True
    remote_push_performed: bool = False
    pr_created: bool = False
    remote_merge_performed: bool = False
    release_performed: bool = False


class DeveloperInterruptRecord(StrictModel):
    request_id: str
    reason: str
    decision: dict[str, Any] | None = None
    resolved: bool = False


class AegisGraphState(StrictModel):
    run_id: str = Field(default_factory=lambda: f"run-{uuid4().hex[:12]}")
    thread_id: str | None = None
    project_id: str
    project_root: str
    current_query: CurrentQuery
    master_semantic_analysis: dict[str, Any] | None = None
    master_module_state: dict[str, Any] = Field(default_factory=dict)
    task_boundary: TaskBoundary | None = None
    route_expand_plan: RouteExpandPlan = Field(default_factory=RouteExpandPlan)
    debate_request_state: DebateRequestState = Field(default_factory=DebateRequestState)
    debate_result: DebateResult | None = None
    execution_state: ExecutionState = Field(default_factory=ExecutionState)
    test_state: TestState = Field(default_factory=TestState)
    final_review_result: FinalReviewResult | None = None
    tool_intent_audits: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_candidates: list[StoreCandidate] = Field(default_factory=list)
    causal_candidates: list[StoreCandidate] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    developer_interrupts: list[DeveloperInterruptRecord] = Field(default_factory=list)
    commit_gate: CommitGate | None = None
    pending_tool_request: dict[str, Any] | None = None
    closeout: dict[str, Any] | None = None

    @field_validator("project_root")
    @classmethod
    def project_root_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_root is required")
        return str(Path(value))

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def new_initial_state(
    project_root: str,
    goal: str,
    task_type: TaskType = "implementation",
    thread_id: str | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    query = CurrentQuery(
        query=goal,
        task_type=task_type,
        goal=goal,
        constraints=["single_project_default"],
        success_criteria=["langgraph_minimum_closure"],
    )
    state = AegisGraphState(
        thread_id=thread_id,
        project_id=root.name or "aegis-project",
        project_root=str(root),
        current_query=query,
    )
    return state.as_dict()
