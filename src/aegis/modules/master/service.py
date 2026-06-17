from __future__ import annotations

from aegis.modules.master.models import (
    ConstraintSource,
    DebateIssue,
    ExecutionHandoffPackage,
    MasterGateError,
    RequirementApprovalDecision,
    RequirementConversation,
    RequirementConstraint,
    RequirementDocument,
    RequirementReviewDocument,
    RequirementReviewFinding,
    RequirementSemanticAnalysis,
)


_HARD_SOURCES: set[ConstraintSource] = {
    "explicit_requirement",
    "project_knowledge",
    "customer_written_evidence",
    "regulatory",
    "platform",
    "hard_cost",
    "first_principle",
}

def _is_solution_lock(constraint: RequirementConstraint) -> bool:
    return constraint.text.lower().startswith("requested implementation path:")


def _constraint_text_and_evidence_refs(
    text: str,
    fallback_evidence_refs: list[str],
) -> tuple[str, list[str]]:
    parts = [part.strip() for part in text.split(";")]
    evidence_refs: list[str] = []
    kept_parts: list[str] = []
    for part in parts:
        if part.lower().startswith("evidence_ref:"):
            refs = part.split(":", 1)[1]
            evidence_refs.extend(ref.strip() for ref in refs.split(",") if ref.strip())
        else:
            kept_parts.append(part)
    return "; ".join(kept_parts).strip(), evidence_refs or fallback_evidence_refs


def close_requirement_intake(
    raw_user_input: str,
    semantic_analysis: RequirementSemanticAnalysis | None = None,
) -> RequirementConversation:
    if semantic_analysis is None:
        semantic_analysis = RequirementSemanticAnalysis(
            purpose="",
            unresolved_questions=[
                "Semantic PM analysis is required before drafting a requirement document."
            ],
            status="clarifying",
        )
    technical_paths = list(dict.fromkeys(semantic_analysis.technical_path_requests))
    constraints = [
        RequirementConstraint(
            text=f"Requested implementation path: {path}",
            source="user",
            evidence_refs=[],
        )
        for path in technical_paths
    ]
    constraints.extend(
        RequirementConstraint(
            text=f"Deliverable request: {deliverable}",
            source="explicit_requirement",
            evidence_refs=["user_request://explicit-deliverable"],
        )
        for deliverable in dict.fromkeys(semantic_analysis.deliverable_requests)
    )
    for constraint in dict.fromkeys(semantic_analysis.hard_constraints):
        text, evidence_refs = _constraint_text_and_evidence_refs(
            constraint,
            ["user_request://explicit-constraint"],
        )
        constraints.append(
            RequirementConstraint(
                text=text,
                source="explicit_requirement",
                evidence_refs=evidence_refs,
            )
        )
    return RequirementConversation(
        goal=raw_user_input,
        purpose=semantic_analysis.purpose,
        technical_path_requests=technical_paths,
        deliverable_requests=list(dict.fromkeys(semantic_analysis.deliverable_requests)),
        user_messages=[raw_user_input],
        raw_constraints=constraints,
        unresolved_questions=list(semantic_analysis.unresolved_questions),
        status=semantic_analysis.status,
    )


def _admit_constraint(constraint: RequirementConstraint) -> RequirementConstraint:
    if constraint.source == "user" and not constraint.evidence_refs:
        return constraint.model_copy(
            update={
                "admission": "preference",
                "hard_constraint": False,
                "reason": "insufficient evidence for user-stated solution lock",
            }
        )
    if constraint.source == "customer_written_evidence" and not constraint.evidence_refs:
        return constraint.model_copy(
            update={
                "admission": "rejected",
                "hard_constraint": False,
                "reason": "customer constraint requires written evidence reference",
            }
        )
    if constraint.source in _HARD_SOURCES:
        return constraint.model_copy(
            update={
                "admission": "hard_constraint",
                "hard_constraint": True,
                "reason": "admitted by project fact, external evidence, or first-principles boundary",
            }
        )
    return constraint.model_copy(
        update={
            "admission": "preference",
            "hard_constraint": False,
            "reason": "not admitted as hard project constraint",
        }
    )


def draft_requirement_document(
    goal: str,
    raw_constraints: list[RequirementConstraint] | None = None,
) -> RequirementDocument:
    constraints = [_admit_constraint(constraint) for constraint in raw_constraints or []]
    subjective = [
        constraint.text for constraint in constraints if constraint.admission in {"preference", "rejected"}
    ]
    return RequirementDocument(
        goal=goal,
        objective=goal.strip(),
        constraints=constraints,
        success_criteria=[
            "implementation result is objectively verifiable",
            "accepted hard constraints are traceable to evidence or first principles",
        ],
        assumptions=["single local git project scope"],
        excluded_subjective_preferences=subjective,
    )


def draft_requirement_document_from_conversation(
    conversation: RequirementConversation,
) -> RequirementDocument:
    return draft_requirement_document(
        goal=conversation.purpose,
        raw_constraints=conversation.raw_constraints,
    )


def review_requirement_document(
    document: RequirementDocument,
    knowledge_refs: list[str],
) -> RequirementReviewDocument:
    findings: list[RequirementReviewFinding] = []
    debate_issues: list[DebateIssue] = []
    for constraint in document.constraints:
        if constraint.admission == "preference" and _is_solution_lock(constraint):
            issue = DebateIssue(
                question=f"Should the requirement force this local solution: {constraint.text}",
                why=(
                    "The requested local solution lock has multiple implementation routes "
                    "and lacks enough evidence to be admitted as a hard constraint."
                ),
                candidate_positions=["honor_as_preference_only", "find_simpler_project_fit"],
            )
            debate_issues.append(issue)
            findings.append(
                RequirementReviewFinding(
                    requirement_item=constraint.text,
                    decision="reject_as_hard_constraint",
                    why="User preference cannot override project integrity without evidence.",
                    evidence_refs=knowledge_refs,
                    first_principles=[
                        "constraints must be necessary",
                        "implementation choices need evidence when alternatives exist",
                    ],
                    debate_issue_id=issue.issue_id,
                )
            )
        elif constraint.admission == "rejected":
            findings.append(
                RequirementReviewFinding(
                    requirement_item=constraint.text,
                    decision="request_more_evidence",
                    why=constraint.reason,
                    evidence_refs=constraint.evidence_refs,
                )
            )
        else:
            findings.append(
                RequirementReviewFinding(
                    requirement_item=constraint.text or document.objective,
                    decision="accept",
                    why="Requirement item is compatible with current evidence boundary.",
                    evidence_refs=[*knowledge_refs, *constraint.evidence_refs],
                    first_principles=["project integrity over user preference"],
                )
            )
    if not findings:
        findings.append(
            RequirementReviewFinding(
                requirement_item=document.objective,
                decision="accept",
                why="Objective is bounded to a single local git project.",
                evidence_refs=knowledge_refs,
                first_principles=["project scope must be explicit before execution"],
            )
        )
    conclusion = (
        "Requirement review is complete with debate issues pending."
        if debate_issues
        else "Requirement review is complete and ready for user confirmation."
    )
    return RequirementReviewDocument(
        requirement_document_id=document.document_id,
        findings=findings,
        debate_issues=debate_issues,
        conclusion=conclusion,
    )


def _require_approved(
    approval: RequirementApprovalDecision | None,
    document_name: str,
) -> None:
    if approval is None or not approval.approved:
        raise MasterGateError(f"{document_name} is not approved")


def build_execution_handoff(
    requirement: RequirementDocument,
    review: RequirementReviewDocument,
    requirement_approval: RequirementApprovalDecision | None,
    review_approval: RequirementApprovalDecision | None,
) -> ExecutionHandoffPackage:
    _require_approved(requirement_approval, "requirement document")
    _require_approved(review_approval, "review document")
    accepted = [item.text for item in requirement.constraints if item.admission == "hard_constraint"]
    rejected = [
        item.text for item in requirement.constraints if item.admission in {"preference", "rejected"}
    ]
    evidence_refs: list[str] = []
    risks: list[str] = []
    for finding in review.findings:
        evidence_refs.extend(finding.evidence_refs)
        if finding.decision != "accept":
            risks.append(finding.why)
    return ExecutionHandoffPackage(
        requirement_document_id=requirement.document_id,
        review_document_id=review.document_id,
        accepted_constraints=accepted,
        rejected_constraints=rejected,
        risks=risks,
        open_limits=[issue.question for issue in review.debate_issues if issue.status == "pending"],
        evidence_refs=sorted(set(evidence_refs)),
    )
