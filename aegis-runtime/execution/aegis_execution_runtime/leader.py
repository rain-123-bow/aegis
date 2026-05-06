from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    CandidatePlan,
    EvidenceRef,
    ExecutionContractError,
    ExecutionGroupRecord,
    ExecutionRequest,
    ExecutionRunState,
    FinalExecutionReport,
    SubtaskSpec,
    TestFeedback,
)


class ExecutionLeader:
    """Deterministic demo Execution Leader.

    This runtime intentionally uses deterministic mock Front/Back Agents and a
    filesystem workspace. It proves the Execution Department contract at demo
    level, not production branch management.
    """

    def __init__(self, private_root: str | Path | None = None):
        self.private_root = Path(private_root or ".aegis-execution-runtime").resolve()
        self.private_root.mkdir(parents=True, exist_ok=True)

    def classify_request(self, request: ExecutionRequest) -> str:
        if not request.has_admission_context():
            return "request_more_context"
        if request.requires_measurement or request.required_measurements:
            return "request_test_measurement"
        valid_plans = [plan for plan in request.candidate_plans if plan.is_debate_candidate()]
        if len(valid_plans) > 1:
            return "request_debate"
        return "accept"

    def start_run(self, request_payload: dict[str, Any]) -> ExecutionRunState | FinalExecutionReport:
        request = ExecutionRequest.from_dict(request_payload)
        decision = self.classify_request(request)
        run_id = f"execution-run-{uuid4().hex}"
        run_root = self.private_root / run_id
        run_root.mkdir(parents=True, exist_ok=False)

        if decision in {"request_more_context", "request_test_measurement", "request_debate"}:
            return self._early_report(run_id=run_id, request=request, decision=decision, run_root=run_root)

        selected_plan = self._select_direct_plan(request.candidate_plans)
        return self._start_accepted_run(
            run_id=run_id,
            run_root=run_root,
            request=request,
            selected_plan=selected_plan,
            debate_reference={},
        )

    def continue_after_debate(
        self, request_payload: dict[str, Any], debate_result_payload: dict[str, Any]
    ) -> ExecutionRunState:
        request = ExecutionRequest.from_dict(request_payload)
        debate_reference = self._validate_debate_result(request, debate_result_payload)
        selected_plan_id = debate_reference["selected_plan_id"]
        matching_plans = [plan for plan in request.candidate_plans if plan.plan_id == selected_plan_id]
        if not matching_plans:
            raise ExecutionContractError(f"Debate selected unknown plan: {selected_plan_id}")

        run_id = f"execution-run-{uuid4().hex}"
        run_root = self.private_root / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        return self._start_accepted_run(
            run_id=run_id,
            run_root=run_root,
            request=request,
            selected_plan=matching_plans[0],
            debate_reference=debate_reference,
        )

    def _start_accepted_run(
        self,
        *,
        run_id: str,
        run_root: Path,
        request: ExecutionRequest,
        selected_plan: CandidatePlan,
        debate_reference: dict[str, Any],
    ) -> ExecutionRunState:
        self._validate_split(request.subtasks)
        self._create_base_project(run_root)

        groups: list[ExecutionGroupRecord] = []
        for index, subtask in enumerate(request.subtasks):
            group = self._create_group(run_id, index, subtask, run_root)
            self._run_front_agent(group, subtask, run_root)
            self._run_back_agent(group, subtask)
            groups.append(group)

        integration_candidate = self._integrate(
            run_id,
            request,
            selected_plan,
            groups,
            run_root,
            debate_reference=debate_reference,
        )
        for group in groups:
            group.status = "UNDER_TEST"

        state = ExecutionRunState(
            run_id=run_id,
            request=request,
            decision="send_implementation_candidate_to_test",
            selected_plan=selected_plan,
            groups=groups,
            integration_candidate=integration_candidate,
            private_root=str(run_root),
            status="WAITING_FOR_TEST",
            debate_reference=debate_reference,
        )
        self._write_json(run_root / "execution_state.json", state.to_dict())
        return state

    def _validate_debate_result(self, request: ExecutionRequest, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ExecutionContractError("Debate result must be an object")
        selected_plan_id = payload.get("selected_plan_id")
        if not isinstance(selected_plan_id, str) or not selected_plan_id:
            raise ExecutionContractError("Debate result requires selected_plan_id")
        if payload.get("status") != "causal_candidate":
            raise ExecutionContractError("Debate result status must remain causal_candidate")
        causal_chain = payload.get("causal_chain")
        if not isinstance(causal_chain, dict) or not causal_chain.get("chain_id"):
            raise ExecutionContractError("Debate result requires causal_chain with chain_id")
        decision = payload.get("decision")
        if not isinstance(decision, str) or not decision:
            raise ExecutionContractError("Debate result requires decision")
        why_selected = payload.get("why_selected")
        if not isinstance(why_selected, str) or not why_selected:
            raise ExecutionContractError("Debate result requires why_selected")
        return {
            "used": True,
            "selected_plan_id": selected_plan_id,
            "decision": decision,
            "why_selected": why_selected,
            "rejected_or_scoped_plans": list(payload.get("rejected_or_scoped_plans", [])),
            "causal_chain_ref": causal_chain["chain_id"],
            "causal_chain": causal_chain,
            "source_request_id": request.request_id,
            "status": "causal_candidate",
        }

    def handle_test_feedback(
        self, state: ExecutionRunState, feedback_payload: dict[str, Any]
    ) -> ExecutionRunState | FinalExecutionReport:
        feedback = TestFeedback.from_dict(feedback_payload)
        state.test_feedback_history.append(feedback.to_dict())
        run_root = Path(state.private_root)

        if feedback.result == "failed":
            if not feedback.evidence_refs:
                state.status = "REQUEST_FAILURE_EVIDENCE"
                self._write_json(run_root / "execution_state.json", state.to_dict())
                return state
            if feedback.owner_type == "ambiguous":
                state.status = "TRIAGE_REQUIRED"
                self._write_json(run_root / "execution_state.json", state.to_dict())
                return state
            if feedback.owner_type == "integration":
                state.status = "INTEGRATION_REWORK_REQUIRED"
                state.integration_candidate.setdefault("rework_history", []).append(feedback.to_dict())
                self._write_json(run_root / "execution_state.json", state.to_dict())
                return state
            if feedback.owner_type != "group" or not feedback.owner_id:
                raise ExecutionContractError("failed feedback must map to group, integration, ambiguous, or missing evidence")
            group = state.group_by_id(feedback.owner_id)
            self._rework_group(group, feedback, run_root)
            self._run_back_agent_after_rework(group, feedback)
            state.integration_candidate = self._integrate(
                state.run_id,
                state.request,
                state.selected_plan,
                state.groups,
                run_root,
                reintegration=True,
                debate_reference=state.debate_reference,
            )
            state.status = "WAITING_FOR_TEST"
            for item in state.groups:
                item.status = "UNDER_TEST"
            self._write_json(run_root / "execution_state.json", state.to_dict())
            return state

        self._validate_success_feedback(state, feedback)
        for group in state.groups:
            group.status = "RELEASED"
        state.status = "TEST_PASSED"
        report = self._final_report(state, feedback, run_root)
        self._write_json(run_root / "final_report.json", report.to_dict())
        self._write_json(run_root / "execution_state.json", state.to_dict())
        return report

    def _early_report(
        self,
        *,
        run_id: str,
        request: ExecutionRequest,
        decision: str,
        run_root: Path,
    ) -> FinalExecutionReport:
        status_by_decision = {
            "request_more_context": "needs_context",
            "request_test_measurement": "needs_measurement",
            "request_debate": "needs_debate",
        }
        chain = self._early_causal_chain(run_id, request, decision)
        report = FinalExecutionReport(
            run_id=run_id,
            request_id=request.request_id,
            decision=decision,  # type: ignore[arg-type]
            final_status=status_by_decision[decision],  # type: ignore[arg-type]
            selected_plan=None,
            implementation_candidate=None,
            group_records=[],
            test_feedback_history=[],
            execution_causal_chain=chain,
            next_action=self._early_next_action(decision),
            artifact_paths={"final_report": str(run_root / "final_report.json")},
        )
        self._write_json(run_root / "final_report.json", report.to_dict())
        return report

    def _early_next_action(self, decision: str) -> dict[str, str]:
        if decision == "request_more_context":
            return {"target": "master", "recommendation": "provide objective, scope, success criteria, and evidence"}
        if decision == "request_test_measurement":
            return {"target": "test", "recommendation": "produce required measurement evidence before execution route choice"}
        return {"target": "debate", "recommendation": "adjudicate non-dominated implementation plans"}

    def _select_direct_plan(self, plans: list[CandidatePlan]) -> CandidatePlan:
        valid = [plan for plan in plans if plan.valid_under_contracts and not plan.contract_violation]
        if not valid:
            raise ExecutionContractError("at least one contract-valid plan is required")
        non_dominated = [plan for plan in valid if not plan.dominated]
        if len(non_dominated) > 1:
            raise ExecutionContractError("non-dominated multiple plans require Debate before direct execution")
        return non_dominated[0] if non_dominated else valid[0]

    def _validate_split(self, subtasks: list[SubtaskSpec]) -> None:
        if not subtasks:
            raise ExecutionContractError("Execution requires at least one subtask")
        seen_subtasks: set[str] = set()
        file_owner: dict[str, str] = {}
        for subtask in subtasks:
            if subtask.subtask_id in seen_subtasks:
                raise ExecutionContractError(f"duplicate subtask_id: {subtask.subtask_id}")
            seen_subtasks.add(subtask.subtask_id)
            subtask.validate_split_readiness()
            for dependency in subtask.dependencies:
                if dependency not in seen_subtasks:
                    # This demo supports only dependencies on earlier subtasks.
                    raise ExecutionContractError(
                        f"subtask {subtask.subtask_id} depends on {dependency}, which is not an earlier frozen subtask"
                    )
            for change in subtask.file_changes:
                if change.path in file_owner:
                    raise ExecutionContractError(
                        f"file {change.path} is modified by both {file_owner[change.path]} and {subtask.subtask_id}; split is invalid"
                    )
                file_owner[change.path] = subtask.subtask_id

    def _create_base_project(self, run_root: Path) -> None:
        base = run_root / "base_project"
        base.mkdir(parents=True, exist_ok=True)
        (base / "README.md").write_text("# Demo project\n", encoding="utf-8")

    def _create_group(self, run_id: str, index: int, subtask: SubtaskSpec, run_root: Path) -> ExecutionGroupRecord:
        group_id = f"G{index + 1}"
        workspace = run_root / "group_workspaces" / group_id
        shutil.copytree(run_root / "base_project", workspace)
        return ExecutionGroupRecord(
            group_id=group_id,
            subtask_id=subtask.subtask_id,
            branch_name=subtask.expected_branch,
            workspace_path=str(workspace),
            front_agent_id=f"{run_id}__{group_id}__front",
            back_agent_id=f"{run_id}__{group_id}__back",
            status="CREATED",
        )

    def _run_front_agent(self, group: ExecutionGroupRecord, subtask: SubtaskSpec, run_root: Path) -> None:
        workspace = Path(group.workspace_path)
        group.status = "IMPLEMENTING"
        touched: list[str] = []
        for change in subtask.file_changes:
            target = workspace / change.path
            if change.change_type == "delete":
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.content, encoding="utf-8")
            touched.append(change.path)
        group.touched_files = touched
        group.status = "MODULE_TESTING"
        group.local_tests = [
            {
                "command": f"validate {subtask.subtask_id} local success criteria",
                "result": "pass",
                "evidence_ref": f"{group.group_id}:local-test",
                "criteria": list(subtask.local_success_criteria),
            }
        ]
        group.causal_fork = {
            "statement": f"{group.group_id} implemented {subtask.subtask_id}",
            "why": subtask.responsibility,
            "evidence": [f"{group.group_id}:local-test"],
            "scope": ", ".join(subtask.owned_files_or_modules),
            "assumptions": [subtask.input_contract, subtask.output_contract],
            "status": "causal_candidate",
        }

    def _run_back_agent(self, group: ExecutionGroupRecord, subtask: SubtaskSpec) -> None:
        group.status = "INTERNAL_REVIEW"
        expected = {change.path for change in subtask.file_changes}
        actual = set(group.touched_files)
        if not actual <= expected:
            group.back_review = {
                "decision": "scope_violation",
                "why": "group touched files outside its assigned scope",
                "evidence_ref": f"{group.group_id}:scope-check",
            }
            raise ExecutionContractError(f"group {group.group_id} touched files outside assigned scope")
        if not group.local_tests:
            group.back_review = {
                "decision": "request_more_evidence",
                "why": "local test evidence missing",
                "evidence_ref": f"{group.group_id}:missing-tests",
            }
            raise ExecutionContractError(f"group {group.group_id} has no local test evidence")
        group.back_review = {
            "decision": "accept",
            "why": "Front Agent changes remain within subtask scope and local tests passed.",
            "evidence_ref": f"{group.group_id}:back-review",
        }
        group.status = "READY_FOR_LEADER"

    def _run_back_agent_after_rework(self, group: ExecutionGroupRecord, feedback: TestFeedback) -> None:
        group.status = "INTERNAL_REVIEW"
        group.back_review = {
            "decision": "accept",
            "why": f"Back Agent accepted rework for {feedback.feedback_id} after evidence-backed Test failure.",
            "evidence_ref": f"{group.group_id}:back-review:rework:{feedback.feedback_id}",
        }
        group.status = "READY_FOR_LEADER"

    def _integrate(
        self,
        run_id: str,
        request: ExecutionRequest,
        selected_plan: CandidatePlan | None,
        groups: list[ExecutionGroupRecord],
        run_root: Path,
        *,
        reintegration: bool = False,
        debate_reference: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        integration_workspace = run_root / ("integration_branch_rework" if reintegration else "integration_branch")
        if integration_workspace.exists():
            shutil.rmtree(integration_workspace)
        shutil.copytree(run_root / "base_project", integration_workspace)
        changed_files: list[dict[str, Any]] = []
        mapping_table: list[dict[str, str]] = []
        for group in groups:
            group_workspace = Path(group.workspace_path)
            for relative in group.touched_files:
                source = group_workspace / relative
                target = integration_workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.exists():
                    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                changed_files.append(
                    {
                        "path": relative,
                        "group_id": group.group_id,
                        "subtask_id": group.subtask_id,
                        "change_type": "modify",
                        "why_changed": group.causal_fork.get("why", "implementation change"),
                    }
                )
                mapping_table.append(
                    {"file_or_module": relative, "group_id": group.group_id, "subtask_id": group.subtask_id}
                )
            group.status = "INTEGRATED" if not reintegration else "REINTEGRATED"
        candidate = {
            "decision": "send_implementation_candidate_to_test",
            "run_id": run_id,
            "task_id": request.request_id,
            "source_request_id": request.request_id,
            "selected_plan": selected_plan.to_dict() if selected_plan else None,
            "integration_branch": "execution/integration/rework" if reintegration else "execution/integration/demo",
            "integration_workspace": str(integration_workspace),
            "base_branch": request.base_branch,
            "merged_group_branches": [
                {"group_id": group.group_id, "branch_name": group.branch_name} for group in groups
            ],
            "changed_files": changed_files,
            "local_tests": [test for group in groups for test in group.local_tests],
            "back_reviews": [dict(group.back_review, group_id=group.group_id) for group in groups],
            "integration_conflicts": [],
            "known_limits": ["demo runtime uses filesystem workspaces, not production git branch orchestration"],
            "risk_if_wrong": "Integration candidate may pass demo tests while production branch governance remains future work.",
            "expected_test_focus": list(request.success_criteria),
            "evidence_refs": [item.ref for item in request.evidence] + [f"{run_id}:integration"],
            "feedback_mapping_table": mapping_table,
            "status": "implementation_candidate",
        }
        if debate_reference and debate_reference.get("used"):
            candidate["debate_reference"] = {
                "used": True,
                "selected_plan_id": debate_reference["selected_plan_id"],
                "causal_chain_ref": debate_reference["causal_chain_ref"],
                "decision": debate_reference["decision"],
                "why_selected": debate_reference["why_selected"],
            }
        self._write_json(run_root / "implementation_candidate.json", candidate)
        return candidate

    def _rework_group(self, group: ExecutionGroupRecord, feedback: TestFeedback, run_root: Path) -> None:
        group.status = "REWORK_REQUIRED"
        group.rework_history.append(feedback.to_dict())
        group.status = "REWORKING"
        workspace = Path(group.workspace_path)
        rework_file = workspace / "REWORK_NOTES.md"
        existing = rework_file.read_text(encoding="utf-8") if rework_file.exists() else "# Rework notes\n"
        rework_file.write_text(
            f"{existing}\n- {feedback.feedback_id}: {feedback.required_fix or feedback.why}\n",
            encoding="utf-8",
        )
        if "REWORK_NOTES.md" not in group.touched_files:
            group.touched_files.append("REWORK_NOTES.md")
        group.local_tests.append(
            {
                "command": f"validate rework for {feedback.feedback_id}",
                "result": "pass",
                "evidence_ref": f"{group.group_id}:rework-test:{feedback.feedback_id}",
            }
        )

    def _validate_success_feedback(self, state: ExecutionRunState, feedback: TestFeedback) -> None:
        if not feedback.evidence_refs:
            raise ExecutionContractError("passed Test feedback still requires evidence references")
        if not feedback.covered_scope:
            raise ExecutionContractError("passed Test feedback must declare covered scope")
        unresolved = [group.group_id for group in state.groups if group.back_review.get("decision") != "accept"]
        if unresolved:
            raise ExecutionContractError(f"cannot release groups with unresolved Back Agent objections: {unresolved}")

    def _final_report(self, state: ExecutionRunState, feedback: TestFeedback, run_root: Path) -> FinalExecutionReport:
        chain = self._execution_causal_chain(state, feedback)
        return FinalExecutionReport(
            run_id=state.run_id,
            request_id=state.request.request_id,
            decision="submit_causal_fork_to_master",
            final_status="test_passed",
            selected_plan=state.selected_plan.to_dict() if state.selected_plan else None,
            implementation_candidate=dict(state.integration_candidate),
            group_records=[group.to_dict() for group in state.groups],
            test_feedback_history=list(state.test_feedback_history),
            execution_causal_chain=chain,
            next_action={"target": "master", "recommendation": "review causal_candidate for global causal merge or next workflow stage"},
            artifact_paths={
                "final_report": str(run_root / "final_report.json"),
                "implementation_candidate": str(run_root / "implementation_candidate.json"),
            },
        )

    def _early_causal_chain(self, run_id: str, request: ExecutionRequest, decision: str) -> dict[str, Any]:
        premise_id = "premise.execution_admission_contract"
        conclusion_id = f"conclusion.{decision}"
        return {
            "chain_id": f"{run_id}:execution-causal-chain",
            "source_request_id": request.request_id,
            "decision_problem": request.objective or "Execution admission decision",
            "nodes": [
                self._node(
                    premise_id,
                    "premise",
                    "Execution requires objective, scope, success criteria, and contract context before implementation.",
                    "Execution must not create groups or branches when admission context is incomplete or route selection is unresolved.",
                    [item.ref for item in request.evidence] or [request.request_id],
                    request.constraints or ["contract-first execution"],
                    request.scope or "execution admission",
                    "high",
                ),
                self._node(
                    conclusion_id,
                    "conclusion",
                    decision,
                    f"Leader classified request as {decision} under Execution decision-label boundary rules.",
                    [request.request_id],
                    request.constraints or ["admission result precedes implementation"],
                    request.scope or "execution admission",
                    "high",
                ),
            ],
            "edges": [self._edge("edge.admission.conclusion", premise_id, conclusion_id, "supports", "Admission premise determines this boundary decision.")],
            "selected_path": [premise_id, conclusion_id],
            "rejected_paths": [],
            "invalidation_entrypoints": [],
            "status": "causal_candidate",
        }

    def _execution_causal_chain(self, state: ExecutionRunState, feedback: TestFeedback) -> dict[str, Any]:
        request = state.request
        run_id = state.run_id
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        premise_id = "premise.execution_contract"
        plan_id = f"plan.{state.selected_plan.plan_id if state.selected_plan else 'direct'}"
        integration_id = "integration.candidate"
        test_success_id = f"test_feedback.{feedback.feedback_id}.passed"
        conclusion_id = "conclusion.execution.causal_candidate"

        nodes.append(
            self._node(
                premise_id,
                "premise",
                "Execution must produce a traceable implementation candidate through groups, reviews, integration, Test feedback, and causal handoff.",
                "The Execution Department contract requires contract-first planning, valid subtask split, Front/Back group review, Leader integration, Test feedback, and causal_candidate output.",
                request.applicable_contracts or ["aegis-master-kit/organization/departments/execution/"],
                request.constraints or ["Execution output remains causal_candidate"],
                request.scope,
                "high",
            )
        )
        nodes.append(
            self._node(
                plan_id,
                "plan",
                state.selected_plan.claim if state.selected_plan else "Direct execution plan",
                state.selected_plan.why if state.selected_plan else "Only one direct contract-valid plan remained.",
                [item.ref for item in (state.selected_plan.evidence if state.selected_plan else [])] or [request.request_id],
                request.constraints,
                request.scope,
                "high",
            )
        )
        edges.append(self._edge("edge.premise.plan", premise_id, plan_id, "supports", "The selected plan is valid under the execution contract premise."))

        debate_reference = state.debate_reference if state.debate_reference.get("used") else {}
        if debate_reference:
            debate_node_id = f"debate_adjudication.{debate_reference['selected_plan_id']}"
            nodes.append(
                self._node(
                    debate_node_id,
                    "debate_adjudication",
                    f"Debate adjudicated {debate_reference['selected_plan_id']} for Execution route selection.",
                    debate_reference["why_selected"],
                    [debate_reference["causal_chain_ref"]],
                    ["Execution binds Debate result as route selection support without re-litigating it."],
                    request.scope,
                    "high",
                )
            )
            edges.append(
                self._edge(
                    f"edge.{debate_node_id}.{plan_id}",
                    debate_node_id,
                    plan_id,
                    "supports",
                    "Execution uses the Debate causal_candidate as support for the selected implementation plan.",
                )
            )

        previous_node = plan_id
        for group in state.groups:
            split_id = f"split.{group.subtask_id}"
            implementation_id = f"implementation.{group.group_id}"
            review_id = f"review.{group.group_id}"
            nodes.append(
                self._node(
                    split_id,
                    "split",
                    f"Subtask {group.subtask_id} assigned to {group.group_id}.",
                    "The split is accepted because the subtask has ownership, contracts, local validation, and feedback mapping.",
                    [request.request_id, group.branch_name],
                    ["no parallel split without independence proof"],
                    ", ".join(group.touched_files),
                    "high",
                )
            )
            nodes.append(
                self._node(
                    implementation_id,
                    "group_implementation",
                    f"{group.group_id} implemented {group.subtask_id} on {group.branch_name}.",
                    group.causal_fork.get("why", "Front Agent produced scoped implementation and local tests."),
                    [test.get("evidence_ref", "") for test in group.local_tests],
                    group.causal_fork.get("assumptions", []),
                    group.causal_fork.get("scope", ", ".join(group.touched_files)),
                    "high",
                )
            )
            nodes.append(
                self._node(
                    review_id,
                    "back_review",
                    f"Back Agent accepted {group.group_id}.",
                    group.back_review.get("why", "Back Agent review accepted scoped implementation."),
                    [group.back_review.get("evidence_ref", f"{group.group_id}:back-review")],
                    ["Back Agent review is required before Leader integration."],
                    ", ".join(group.touched_files),
                    "high",
                )
            )
            edges.append(self._edge(f"edge.{previous_node}.{split_id}", previous_node, split_id, "depends_on", "Plan is decomposed into an objectively justified subtask."))
            edges.append(self._edge(f"edge.{split_id}.{implementation_id}", split_id, implementation_id, "supports", "Group implementation follows its assigned subtask."))
            edges.append(self._edge(f"edge.{implementation_id}.{review_id}", implementation_id, review_id, "validates", "Back Agent review validates group readiness."))
            previous_node = review_id

        nodes.append(
            self._node(
                integration_id,
                "integration",
                "Execution Leader integrated accepted group branches into an implementation candidate.",
                "Leader-owned integration preserves branch mapping, changed files, local tests, Back Agent reviews, and feedback mapping.",
                state.integration_candidate.get("evidence_refs", []),
                ["Integration branch is not final project merge."],
                state.integration_candidate.get("integration_branch", "execution integration branch"),
                "high",
            )
        )
        edges.append(self._edge(f"edge.{previous_node}.{integration_id}", previous_node, integration_id, "supports", "Accepted group outputs support the integration candidate."))

        for item in state.test_feedback_history:
            node_id = f"test_feedback.{item['feedback_id']}.{item['result']}"
            nodes.append(
                self._node(
                    node_id,
                    "test_feedback",
                    f"Test feedback {item['feedback_id']} result: {item['result']}",
                    item.get("why") or "Test feedback is mandatory whether pass or fail.",
                    item.get("evidence_refs", []),
                    ["Test feedback must be evidence-backed."],
                    ", ".join(item.get("covered_scope", [])) or request.scope,
                    "high" if item["result"] == "passed" else "medium",
                )
            )
            relation = "validates" if item["result"] == "passed" else "requires_rework"
            edges.append(self._edge(f"edge.{integration_id}.{node_id}", integration_id, node_id, relation, "Test feedback validates or reopens the integration candidate."))
            if item["result"] == "failed" and item.get("owner_id"):
                rework_id = f"rework.{item['owner_id']}.{item['feedback_id']}"
                nodes.append(
                    self._node(
                        rework_id,
                        "rework",
                        f"{item['owner_id']} reworked feedback {item['feedback_id']}.",
                        item.get("required_fix") or item.get("why") or "Mapped owner completed rework.",
                        item.get("evidence_refs", []),
                        ["Failed Test feedback maps to responsible owner before rework."],
                        request.scope,
                        "high",
                    )
                )
                edges.append(self._edge(f"edge.{node_id}.{rework_id}", node_id, rework_id, "maps_to", "Evidence-backed failure maps to responsible owner."))
                edges.append(self._edge(f"edge.{rework_id}.{integration_id}", rework_id, integration_id, "resolves", "Rework is reintegrated into the implementation candidate."))

        nodes.append(
            self._node(
                test_success_id,
                "test_feedback",
                "Final Test feedback passed declared validation scope.",
                "Success feedback is evidence and allows group release after records and causal chain are preserved.",
                feedback.evidence_refs,
                ["No unresolved Back Agent objection remains."],
                ", ".join(feedback.covered_scope),
                "high",
            )
        )
        nodes.append(
            self._node(
                conclusion_id,
                "conclusion",
                "Return Execution final causal candidate to Master.",
                "Execution Leader releases active groups after Test success while preserving responsibility records and returns branch-local causal fork / merge-relevant reasoning to Master.",
                [feedback.feedback_id, run_id],
                ["Master remains global causal merge authority."],
                request.scope,
                "high",
            )
        )
        edges.append(self._edge(f"edge.{test_success_id}.{conclusion_id}", test_success_id, conclusion_id, "supports", "Final success feedback supports causal handoff to Master."))

        risk_id = "risk.production_hardening_deferred"
        nodes.append(
            self._node(
                risk_id,
                "risk",
                "Demo runtime does not prove production branch governance or real nested-Codex orchestration.",
                "Production closure is explicitly deferred.",
                [run_id],
                ["demo closure, not production closure"],
                request.scope,
                "medium",
            )
        )
        edges.append(self._edge("edge.conclusion.risk", conclusion_id, risk_id, "creates_risk", "Final result remains scoped to demo runtime."))

        invalidation_id = "invalidation.execution_contract_or_test_scope_changes"
        nodes.append(
            self._node(
                invalidation_id,
                "invalidation_condition",
                "If contracts, Test scope, branch policy, or runtime ownership model change, reopen this execution causal candidate.",
                "Execution conclusions are maintained by contracts, evidence, scope, and material conditions.",
                [request.request_id],
                ["material conditions can invalidate reasoning conclusions"],
                request.scope,
                "medium",
            )
        )
        edges.append(self._edge("edge.invalidation.reopens.conclusion", invalidation_id, conclusion_id, "reopens_if", "Changed material conditions require revalidation."))

        return {
            "chain_id": f"{run_id}:execution-causal-chain",
            "source_request_id": request.request_id,
            "decision_problem": request.objective,
            "selected_plan_id": state.selected_plan.plan_id if state.selected_plan else "direct",
            "debate_reference": dict(debate_reference),
            "nodes": nodes,
            "edges": edges,
            "selected_path": [premise_id, plan_id, integration_id, test_success_id, conclusion_id],
            "group_paths": [
                {"group_id": group.group_id, "node_ids": [f"split.{group.subtask_id}", f"implementation.{group.group_id}", f"review.{group.group_id}"]}
                for group in state.groups
            ],
            "test_feedback_path": [
                f"test_feedback.{item['feedback_id']}.{item['result']}" for item in state.test_feedback_history
            ],
            "invalidation_entrypoints": [
                {"condition_node_id": invalidation_id, "reopens_node_ids": [conclusion_id]}
            ],
            "status": "causal_candidate",
        }

    def _node(
        self,
        node_id: str,
        node_type: str,
        statement: str,
        why: str,
        evidence_refs: list[str],
        assumptions: list[str],
        scope: str,
        confidence: str,
    ) -> dict[str, Any]:
        return {
            "id": node_id,
            "type": node_type,
            "statement": statement,
            "why": why,
            "evidence_refs": [item for item in evidence_refs if item],
            "assumptions": [item for item in assumptions if item] or ["demo execution causal-chain construction"],
            "scope": scope or "Execution Department demo runtime",
            "confidence": confidence,
        }

    def _edge(self, edge_id: str, from_id: str, to_id: str, relation: str, why: str) -> dict[str, str]:
        return {"id": edge_id, "from": from_id, "to": to_id, "relation": relation, "why": why}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
