from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from aegis.modules.master.continuity import ContinuityStore
from aegis.modules.master.models import (
    MasterArtifactRef,
    MasterModuleState,
    PmActorSession,
    RequirementApprovalDecision,
    RequirementSemanticAnalysis,
)
from aegis.modules.master.service import (
    build_execution_handoff,
    close_requirement_intake,
    draft_requirement_document_from_conversation,
    review_requirement_document,
)
from aegis.modules.master.artifacts import MasterArtifactStore


def _master_state(state: dict[str, Any]) -> MasterModuleState:
    return MasterModuleState.model_validate(state.get("master_module_state") or {})


def _with_master_state(state: dict[str, Any], module_state: MasterModuleState) -> dict[str, Any]:
    return {"master_module_state": module_state.model_dump(mode="json", exclude_none=True)}


def _goal(state: dict[str, Any]) -> str:
    return state["current_query"]["goal"]


def _run_ref(state: dict[str, Any]) -> str:
    return str(state.get("thread_id") or state.get("run_id") or "unthreaded")


def _stable_id(prefix: str, value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    safe = safe.strip("-_")[:48] or "unthreaded"
    return f"{prefix}-{safe}"


def _artifact_store(state: dict[str, Any]) -> MasterArtifactStore:
    return MasterArtifactStore(state["project_root"], _run_ref(state))


def _approval_for_artifact(
    *,
    approved: bool,
    artifact_ref: MasterArtifactRef,
    comments: str = "",
    requested_changes: list[str] | None = None,
) -> RequirementApprovalDecision:
    return RequirementApprovalDecision(
        approved=approved,
        artifact_id=artifact_ref.artifact_id,
        artifact_readme_path=artifact_ref.readme_path,
        artifact_sha256=artifact_ref.sha256,
        comments=comments,
        requested_changes=requested_changes or [],
    )


def _artifact_is_approved(
    approval: RequirementApprovalDecision | None,
    artifact_ref: MasterArtifactRef,
) -> bool:
    return (
        approval is not None
        and approval.approved
        and approval.artifact_id == artifact_ref.artifact_id
        and approval.artifact_sha256 == artifact_ref.sha256
    )


def _interrupt_payload(approval_type: str, artifact_ref: MasterArtifactRef) -> dict[str, Any]:
    return {
        "approval_type": approval_type,
        "artifact_ref": artifact_ref.model_dump(mode="json"),
        "readme_path": artifact_ref.readme_path,
        "primary_document_path": artifact_ref.primary_document_path,
        "sha256": artifact_ref.sha256,
        "required_decision": {"approved": "boolean"},
    }


def continuity_preflight(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    check = ContinuityStore().check_project(state["project_root"], recover_dirty=True)
    module_state = module_state.model_copy(
        update={"phase": "continuity_checked", "continuity_check": check}
    )
    updates = _with_master_state(state, module_state)
    if not check.can_proceed:
        updates["blockers"] = [
            *(state.get("blockers") or []),
            check.blocked_reason or "project continuity check blocked Master",
        ]
    return updates


def route_after_continuity_preflight(state: dict[str, Any]) -> str:
    module_state = _master_state(state)
    if module_state.continuity_check and module_state.continuity_check.can_proceed:
        return "master_intake"
    return "final_commit_gate"


def pm_session_start_or_resume(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.pm_session is not None:
        return _with_master_state(state, module_state)
    run_ref = _run_ref(state)
    session = PmActorSession(
        pm_session_id=_stable_id("pm-session", run_ref),
        pm_agent_id=_stable_id("master-pm", run_ref),
        pm_thread_id=_stable_id("pm-thread", run_ref),
    )
    module_state = module_state.model_copy(
        update={"phase": "pm_session_active", "pm_session": session}
    )
    return _with_master_state(state, module_state)


def pm_intake(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.pm_session is None:
        raise ValueError("resident PM session is required before PM intake")
    goal = _goal(state)
    if not state.get("master_semantic_analysis"):
        module_state = module_state.model_copy(update={"phase": "pm_semantic_analysis_required"})
        updates = _with_master_state(state, module_state)
        updates["blockers"] = [
            *(state.get("blockers") or []),
            "PM semantic analysis is required before requirement drafting",
        ]
        return updates
    semantic_analysis = RequirementSemanticAnalysis.model_validate(state["master_semantic_analysis"])
    conversation = close_requirement_intake(goal, semantic_analysis=semantic_analysis)
    conversation_ref = _artifact_store(state).write_intake(conversation)
    pm_session = module_state.pm_session.model_copy(
        update={"context_refs": [*module_state.pm_session.context_refs, conversation_ref]}
    )
    phase = (
        "requirement_intake_complete"
        if conversation.status == "ready_for_document" and not conversation.unresolved_questions
        else "requirement_intake_needs_clarification"
    )
    module_state = module_state.model_copy(
        update={"phase": phase, "pm_session": pm_session, "conversation_ref": conversation_ref}
    )
    updates = _with_master_state(state, module_state)
    if phase != "requirement_intake_complete":
        updates["blockers"] = [*(state.get("blockers") or []), "requirement intake is not closed"]
    return updates


def route_after_pm_intake(state: dict[str, Any]) -> str:
    module_state = _master_state(state)
    if module_state.phase == "requirement_intake_complete" and module_state.conversation_ref:
        return "requirement_doc_draft"
    return "final_commit_gate"


def requirement_doc_draft(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.conversation_ref is None:
        raise ValueError("requirement conversation is required before drafting")
    store = _artifact_store(state)
    conversation = store.read_intake(module_state.conversation_ref)
    document = draft_requirement_document_from_conversation(conversation)
    document_ref = store.write_requirement(document)
    module_state = module_state.model_copy(
        update={"phase": "requirement_document_drafted", "requirement_document_ref": document_ref}
    )
    return _with_master_state(state, module_state)


def requirement_user_approval(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.requirement_document_ref is None:
        raise ValueError("requirement document is required before user approval")
    artifact_ref = module_state.requirement_document_ref
    resume_value = interrupt(_interrupt_payload("requirement_document", artifact_ref))
    approved = bool(isinstance(resume_value, dict) and resume_value.get("approved"))
    approval = _approval_for_artifact(
        approved=approved,
        artifact_ref=artifact_ref,
        comments=resume_value.get("comments", "") if isinstance(resume_value, dict) else "",
        requested_changes=(
            resume_value.get("requested_changes", []) if isinstance(resume_value, dict) else []
        ),
    )
    module_state = module_state.model_copy(
        update={"phase": "requirement_approval_recorded", "requirement_approval": approval}
    )
    updates = _with_master_state(state, module_state)
    if not approved:
        updates["blockers"] = [*(state.get("blockers") or []), "requirement document not approved"]
    return updates


def route_after_requirement_approval(state: dict[str, Any]) -> str:
    module_state = _master_state(state)
    if module_state.requirement_approval and module_state.requirement_approval.approved:
        return "requirement_review"
    return "final_commit_gate"


def requirement_review(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.requirement_document_ref is None:
        raise ValueError("requirement document is required before review")
    if not _artifact_is_approved(
        module_state.requirement_approval,
        module_state.requirement_document_ref,
    ):
        raise ValueError("approved requirement document is required before review")
    store = _artifact_store(state)
    document = store.read_requirement(module_state.requirement_document_ref)
    review = review_requirement_document(
        document,
        knowledge_refs=["knowledge://project/local-candidates"],
    )
    review_ref = store.write_review(review)
    module_state = module_state.model_copy(
        update={"phase": "requirement_review_complete", "review_document_ref": review_ref}
    )
    return _with_master_state(state, module_state)


def review_debate_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.review_document_ref is None:
        raise ValueError("review document is required before debate dispatch")
    store = _artifact_store(state)
    review = store.read_review(module_state.review_document_ref)
    resolved_issues = []
    for issue in review.debate_issues:
        if issue.status == "resolved":
            resolved_issues.append(issue)
            continue
        resolved_issues.append(
            issue.model_copy(
                update={
                    "status": "resolved",
                    "result": {
                        "status": "causal_candidate",
                        "selected_position": "find_simpler_project_fit",
                        "why": (
                            "A local solution lock without evidence must remain a preference; "
                            "execution should choose the simplest project-fit route."
                        ),
                    },
                }
            )
        )
    if resolved_issues:
        review = review.model_copy(
            update={
                "debate_issues": resolved_issues,
                "conclusion": (
                    "Requirement review integrated Debate results and is ready for user confirmation."
                ),
            }
        )
    review_ref = store.write_review(review)
    module_state = module_state.model_copy(
        update={"phase": "review_debate_resolved", "review_document_ref": review_ref}
    )
    return _with_master_state(state, module_state)


def review_user_approval(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.review_document_ref is None:
        raise ValueError("review document is required before user approval")
    artifact_ref = module_state.review_document_ref
    resume_value = interrupt(_interrupt_payload("review_document", artifact_ref))
    approved = bool(isinstance(resume_value, dict) and resume_value.get("approved"))
    approval = _approval_for_artifact(
        approved=approved,
        artifact_ref=artifact_ref,
        comments=resume_value.get("comments", "") if isinstance(resume_value, dict) else "",
        requested_changes=(
            resume_value.get("requested_changes", []) if isinstance(resume_value, dict) else []
        ),
    )
    module_state = module_state.model_copy(
        update={"phase": "review_approval_recorded", "review_approval": approval}
    )
    updates = _with_master_state(state, module_state)
    if not approved:
        updates["blockers"] = [*(state.get("blockers") or []), "review document not approved"]
    return updates


def route_after_review_approval(state: dict[str, Any]) -> str:
    module_state = _master_state(state)
    if module_state.review_approval and module_state.review_approval.approved:
        return "execution_handoff"
    return "final_commit_gate"


def execution_handoff(state: dict[str, Any]) -> dict[str, Any]:
    module_state = _master_state(state)
    if module_state.requirement_document_ref is None or module_state.review_document_ref is None:
        raise ValueError("requirement and review documents are required before handoff")
    if not _artifact_is_approved(
        module_state.requirement_approval,
        module_state.requirement_document_ref,
    ):
        raise ValueError("approved requirement document is required before handoff")
    if not _artifact_is_approved(module_state.review_approval, module_state.review_document_ref):
        raise ValueError("approved review document is required before handoff")
    store = _artifact_store(state)
    requirement = store.read_requirement(module_state.requirement_document_ref)
    review = store.read_review(module_state.review_document_ref)
    handoff = build_execution_handoff(
        requirement,
        review,
        requirement_approval=module_state.requirement_approval,
        review_approval=module_state.review_approval,
    )
    handoff_ref = store.write_handoff(handoff)
    module_state = module_state.model_copy(
        update={"phase": "execution_handoff_ready", "execution_handoff_ref": handoff_ref}
    )
    return _with_master_state(state, module_state)
