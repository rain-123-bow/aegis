from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

Decision = Literal[
    "stage_canonical_merge_candidate",
    "stage_scope_limited_merge_candidate",
    "stage_supersession_candidate",
    "stage_invalidation_candidate",
    "reject_candidate",
    "needs_more_evidence",
    "needs_debate",
    "developer_decision_required",
    "reject_direct_merge_or_store_write",
]

_ALLOWED_SOURCE_ORIGINS = {
    "master_unique_conclusion",
    "debate_leader_adjudication",
    "execution_leader_directional_reasoning",
}

_DIRECT_WRITE_FIELDS = (
    "canonical_global_merge_performed",
    "canonical_global_merge_allowed",
    "global_causal_truth_mutation",
    "production_store_write_performed",
    "causal_store_write_performed",
    "store_write_performed",
    "direct_global_write",
    "write_global_truth",
    "write_causal_store",
    "active_global_truth",
)
_HIGH_CONFIDENCE_TYPES = {
    "statistical",
    "deterministic_proof",
    "contract_proven",
    "test_evidence_backed",
    "static_analysis_backed",
}
_NON_DECISIVE_CONFIDENCE_TYPES = {
    "heuristic",
    "qualitative",
    "unknown",
}


class CausalReviewError(ValueError):
    """Raised when Phase 22B Causal Review input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CausalReviewDecision:
    review_decision_id: str
    phase: str
    decision: Decision
    why: str
    candidate_id: str
    candidate_statement: str
    source_origin: str
    accepted_status: str
    required_next_step: str
    scope: str
    assumptions: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    knowledge_context_used: list[str] = field(default_factory=list)
    causal_context_used: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    invalidates: list[str] = field(default_factory=list)
    master_confidence: dict[str, Any] = field(default_factory=dict)
    developer_decision_required: bool = False
    developer_decision_package: dict[str, Any] | None = None
    archive_event_candidate_required: bool = False
    archive_event_candidate: dict[str, Any] | None = None
    canonical_global_merge_performed: bool = False
    production_store_write_performed: bool = False
    causal_store_write_performed: bool = False
    master_owned_review: bool = True
    developer_owns_decisive_responsibility: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_decision_id": self.review_decision_id,
            "phase": self.phase,
            "decision": self.decision,
            "why": self.why,
            "candidate_id": self.candidate_id,
            "candidate_statement": self.candidate_statement,
            "source_origin": self.source_origin,
            "accepted_status": self.accepted_status,
            "required_next_step": self.required_next_step,
            "scope": self.scope,
            "assumptions": list(self.assumptions),
            "evidence_refs": list(self.evidence_refs),
            "knowledge_context_used": list(self.knowledge_context_used),
            "causal_context_used": list(self.causal_context_used),
            "conflicts": list(self.conflicts),
            "supersedes": list(self.supersedes),
            "invalidates": list(self.invalidates),
            "master_confidence": dict(self.master_confidence),
            "developer_decision_required": self.developer_decision_required,
            "developer_decision_package": self.developer_decision_package,
            "archive_event_candidate_required": self.archive_event_candidate_required,
            "archive_event_candidate": self.archive_event_candidate,
            "canonical_global_merge_performed": self.canonical_global_merge_performed,
            "production_store_write_performed": self.production_store_write_performed,
            "causal_store_write_performed": self.causal_store_write_performed,
            "master_owned_review": self.master_owned_review,
            "developer_owns_decisive_responsibility": self.developer_owns_decisive_responsibility,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CausalReviewError(f"review request file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CausalReviewError(f"review request file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CausalReviewError("review request file must contain a JSON object")
    return payload


def validate_review_file(path: str | Path) -> CausalReviewDecision:
    return validate_review_request(load_json_object(path))


def validate_review_request(request: dict[str, Any]) -> CausalReviewDecision:
    if not isinstance(request, dict):
        raise CausalReviewError("review request must be a JSON object")

    candidate = _candidate(request)
    source_origin = str(candidate.get("source_origin", ""))

    if _has_direct_write_attempt(request) or _has_direct_write_attempt(candidate):
        return _decision(
            decision="reject_direct_merge_or_store_write",
            candidate=candidate,
            why="Phase 22B rejects direct canonical/global merge and production store write attempts.",
            accepted_status="rejected",
            required_next_step="resubmit_as_review_artifact_without_store_mutation",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    if candidate.get("accepted_status") != "causal_candidate":
        return _decision(
            decision="reject_candidate",
            candidate=candidate,
            why="Phase 22B accepts only Phase 22A staged causal_candidate input.",
            accepted_status="rejected",
            required_next_step="run_phase22a_structural_admission_first",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    if source_origin not in _ALLOWED_SOURCE_ORIGINS:
        return _decision(
            decision="reject_candidate",
            candidate=candidate,
            why="Causal candidate has unsupported source origin for Master causal review.",
            accepted_status="rejected",
            required_next_step="provide_allowed_source_origin_or_route_to_debate",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    missing = _missing_required(candidate)
    if missing:
        return _decision(
            decision="needs_more_evidence",
            candidate=candidate,
            why=f"Causal candidate missing required field(s): {', '.join(missing)}",
            accepted_status="needs_more_evidence",
            required_next_step="complete_causal_candidate_structure_before_review",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    context_problem = _context_problem(request)
    if context_problem:
        return _decision(
            decision="needs_more_evidence",
            candidate=candidate,
            why=context_problem,
            accepted_status="needs_more_evidence",
            required_next_step="load_relevant_knowledge_and_causal_context_or_justify_absence",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    if request.get("multiple_plausible_paths") is True or candidate.get("multiple_plausible_paths") is True:
        return _decision(
            decision="needs_debate",
            candidate=candidate,
            why="Multiple plausible project-direction paths remain; Master must route to Debate instead of staging canonical merge candidate.",
            accepted_status="needs_debate",
            required_next_step="route_to_debate_for_adversarial_adjudication",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    conflicts = _conflicts(request, candidate)
    alternatives = _alternatives(request)

    if conflicts:
        if alternatives:
            return _developer_decision(
                candidate=candidate,
                request=request,
                why="Candidate conflicts with existing active/tentative causal state and no statistically decisive conclusion is available.",
                conflicts=conflicts,
            )
        return _decision(
            decision="needs_debate",
            candidate=candidate,
            why="Candidate conflicts with existing causal state and lacks a complete developer-decision alternative package.",
            accepted_status="needs_debate",
            required_next_step="route_to_debate_or_prepare_developer_decision_package",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            conflicts=conflicts,
            master_confidence=_confidence(request),
        )

    if _scope_overclaim(candidate):
        scope_limit = candidate.get("proposed_scope_limit") or request.get("proposed_scope_limit")
        if not scope_limit:
            return _decision(
                decision="reject_candidate",
                candidate=candidate,
                why="Candidate scope overclaims production/global validity and provides no narrowed scope.",
                accepted_status="rejected",
                required_next_step="resubmit_with_valid_scope_or_evidence",
                knowledge_context_used=_knowledge_refs(request),
                causal_context_used=_causal_refs(request),
                master_confidence=_confidence(request),
            )
        if not _has_high_confidence_support(request):
            return _developer_decision(
                candidate=candidate,
                request=request,
                why="Scope-limited acceptance affects project direction but lacks high-confidence support.",
                conflicts=[],
            )
        return _decision(
            decision="stage_scope_limited_merge_candidate",
            candidate=candidate,
            why="Candidate is eligible only under a narrowed scope and may proceed as a scope-limited merge candidate.",
            accepted_status="scope_limited_merge_candidate",
            required_next_step="phase22c_causal_store_persistence_after_developer_or_policy_authorization",
            scope=str(scope_limit),
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    supersedes = _as_string_list(candidate.get("supersedes", []))
    invalidates = _as_string_list(candidate.get("invalidates", []))
    if supersedes and not _all_refs_exist(supersedes, _causal_context(request)):
        return _decision(
            decision="needs_more_evidence",
            candidate=candidate,
            why="Candidate declares supersedes references that are not present in loaded causal context.",
            accepted_status="needs_more_evidence",
            required_next_step="load_referenced_causal_facts_before_supersession_review",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            supersedes=supersedes,
            master_confidence=_confidence(request),
        )
    if invalidates and not _all_refs_exist(invalidates, _causal_context(request)):
        return _decision(
            decision="needs_more_evidence",
            candidate=candidate,
            why="Candidate declares invalidates references that are not present in loaded causal context.",
            accepted_status="needs_more_evidence",
            required_next_step="load_referenced_causal_facts_before_invalidation_review",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            invalidates=invalidates,
            master_confidence=_confidence(request),
        )

    if not _has_high_confidence_support(request):
        if alternatives:
            return _developer_decision(
                candidate=candidate,
                request=request,
                why="Master lacks high-confidence support for a project-direction causal decision.",
                conflicts=[],
            )
        return _decision(
            decision="needs_more_evidence",
            candidate=candidate,
            why="Project-direction causal review requires high-confidence support or a complete developer-decision alternative package.",
            accepted_status="needs_more_evidence",
            required_next_step="provide_high_confidence_support_or_developer_decision_package",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            master_confidence=_confidence(request),
        )

    if supersedes:
        return _decision(
            decision="stage_supersession_candidate",
            candidate=candidate,
            why="Candidate may supersede existing causal fact(s) in a later persistence phase; no store write is performed now.",
            accepted_status="supersession_candidate",
            required_next_step="phase22c_causal_store_persistence",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            supersedes=supersedes,
            master_confidence=_confidence(request),
        )
    if invalidates:
        return _decision(
            decision="stage_invalidation_candidate",
            candidate=candidate,
            why="Candidate may invalidate existing causal fact(s) in a later persistence phase; no store write is performed now.",
            accepted_status="invalidation_candidate",
            required_next_step="phase22c_causal_store_persistence",
            knowledge_context_used=_knowledge_refs(request),
            causal_context_used=_causal_refs(request),
            invalidates=invalidates,
            master_confidence=_confidence(request),
        )

    return _decision(
        decision="stage_canonical_merge_candidate",
        candidate=candidate,
        why="Master review considered Knowledge and existing Causal context, found no unresolved conflict, and has high-confidence support; this stages a merge candidate only.",
        accepted_status="canonical_merge_candidate",
        required_next_step="phase22c_causal_store_persistence",
        knowledge_context_used=_knowledge_refs(request),
        causal_context_used=_causal_refs(request),
        master_confidence=_confidence(request),
    )


def _developer_decision(*, candidate: dict[str, Any], request: dict[str, Any], why: str, conflicts: list[str]) -> CausalReviewDecision:
    alternatives = _alternatives(request)
    package = {
        "candidate": candidate,
        "alternatives": alternatives,
        "knowledge_context_used": _knowledge_refs(request),
        "causal_context_used": _causal_refs(request),
        "conflicts": conflicts,
        "master_confidence": _confidence(request),
        "master_recommendation": request.get("master_recommendation"),
        "reason_master_cannot_own_decisive_conclusion": why,
        "probability_claim_boundary": "statistical probabilities require data; deterministic/contract/test/static-analysis confidence require evidence refs; heuristic estimates must remain labeled as heuristic",
    }
    archive_candidate = {
        "candidate_type": "archive",
        "event_type": "developer_decision_required",
        "actor": "master",
        "scope": _scope(candidate),
        "artifact_refs": _evidence_refs(candidate),
        "responsibility_boundary": "developer owns the decisive conclusion under unresolved uncertainty",
        "review_candidate_id": _candidate_id(candidate),
    }
    return _decision(
        decision="developer_decision_required",
        candidate=candidate,
        why=why,
        accepted_status="pending_developer_decision",
        required_next_step="developer_review_and_archive_record_before_any_canonical_merge",
        knowledge_context_used=_knowledge_refs(request),
        causal_context_used=_causal_refs(request),
        conflicts=conflicts,
        master_confidence=_confidence(request),
        developer_decision_required=True,
        developer_decision_package=package,
        archive_event_candidate_required=True,
        archive_event_candidate=archive_candidate,
        developer_owns_decisive_responsibility=True,
    )


def _decision(
    *,
    decision: Decision,
    candidate: dict[str, Any],
    why: str,
    accepted_status: str,
    required_next_step: str,
    knowledge_context_used: list[str],
    causal_context_used: list[str],
    master_confidence: dict[str, Any],
    scope: str | None = None,
    conflicts: list[str] | None = None,
    supersedes: list[str] | None = None,
    invalidates: list[str] | None = None,
    developer_decision_required: bool = False,
    developer_decision_package: dict[str, Any] | None = None,
    archive_event_candidate_required: bool = False,
    archive_event_candidate: dict[str, Any] | None = None,
    developer_owns_decisive_responsibility: bool = False,
) -> CausalReviewDecision:
    return CausalReviewDecision(
        review_decision_id=f"causal-review-{uuid4().hex}",
        phase="phase22b_master_causal_review",
        decision=decision,
        why=why,
        candidate_id=_candidate_id(candidate),
        candidate_statement=_statement(candidate),
        source_origin=str(candidate.get("source_origin", "")),
        accepted_status=accepted_status,
        required_next_step=required_next_step,
        scope=scope if scope is not None else _scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        knowledge_context_used=knowledge_context_used,
        causal_context_used=causal_context_used,
        conflicts=list(conflicts or []),
        supersedes=list(supersedes or _as_string_list(candidate.get("supersedes", []))),
        invalidates=list(invalidates or _as_string_list(candidate.get("invalidates", []))),
        master_confidence=master_confidence,
        developer_decision_required=developer_decision_required,
        developer_decision_package=developer_decision_package,
        archive_event_candidate_required=archive_event_candidate_required,
        archive_event_candidate=archive_event_candidate,
        developer_owns_decisive_responsibility=developer_owns_decisive_responsibility,
    )


def _candidate(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("causal_candidate") or request.get("candidate")
    if not isinstance(value, dict):
        raise CausalReviewError("review request requires causal_candidate object")
    return value


def _candidate_id(candidate: dict[str, Any]) -> str:
    for key in ("candidate_id", "id", "statement_id"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return f"candidate-{uuid4().hex}"


def _statement(candidate: dict[str, Any]) -> str:
    value = candidate.get("statement")
    return value if isinstance(value, str) else ""


def _scope(candidate: dict[str, Any]) -> str:
    value = candidate.get("scope")
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, str) and value:
        return value
    return "unspecified"


def _assumptions(candidate: dict[str, Any]) -> list[str]:
    return _as_string_list(candidate.get("assumptions", []))


def _evidence_refs(candidate: dict[str, Any]) -> list[str]:
    evidence = candidate.get("evidence") or candidate.get("evidence_refs") or []
    if isinstance(evidence, str):
        return [evidence] if evidence else []
    if not isinstance(evidence, list):
        raise CausalReviewError("evidence must be a list or string when present")
    refs: list[str] = []
    for item in evidence:
        if isinstance(item, str) and item:
            refs.append(item)
        elif isinstance(item, dict):
            ref = item.get("ref") or item.get("path") or item.get("id")
            if isinstance(ref, str) and ref:
                refs.append(ref)
        else:
            raise CausalReviewError("evidence list entries must be strings or objects with ref/path/id")
    return refs


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CausalReviewError("expected list of non-empty strings")
    return list(value)


def _missing_required(candidate: dict[str, Any]) -> list[str]:
    missing = [field for field in ("statement", "why", "scope", "source_origin") if not isinstance(candidate.get(field), str) or not candidate.get(field)]
    if not _evidence_refs(candidate):
        missing.append("evidence")
    if not _assumptions(candidate):
        missing.append("assumptions")
    return missing


def _knowledge_context(request: dict[str, Any]) -> list[dict[str, Any]]:
    value = request.get("knowledge_context", [])
    if not isinstance(value, list):
        raise CausalReviewError("knowledge_context must be a list")
    if any(not isinstance(item, dict) for item in value):
        raise CausalReviewError("knowledge_context entries must be objects")
    return list(value)


def _causal_context(request: dict[str, Any]) -> list[dict[str, Any]]:
    value = request.get("causal_context", [])
    if not isinstance(value, list):
        raise CausalReviewError("causal_context must be a list")
    if any(not isinstance(item, dict) for item in value):
        raise CausalReviewError("causal_context entries must be objects")
    return list(value)


def _knowledge_refs(request: dict[str, Any]) -> list[str]:
    return [_context_id(item, prefix="K") for item in _knowledge_context(request)]


def _causal_refs(request: dict[str, Any]) -> list[str]:
    return [_context_id(item, prefix="F") for item in _causal_context(request)]


def _context_id(item: dict[str, Any], *, prefix: str) -> str:
    for key in ("id", "ref", "statement_id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return f"{prefix}:anonymous"


def _context_problem(request: dict[str, Any]) -> str | None:
    if not _knowledge_context(request) and not request.get("knowledge_context_absence_reason"):
        return "Master causal review requires relevant Knowledge context or explicit absence reason."
    if not _causal_context(request) and not request.get("causal_context_absence_reason"):
        return "Master causal review requires relevant existing Causal context or explicit absence reason."
    return None


def _confidence(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("master_confidence") or {}
    if not isinstance(value, dict):
        raise CausalReviewError("master_confidence must be an object when present")
    threshold = _threshold(request)
    evidence_refs = value.get("evidence_refs", [])
    if isinstance(evidence_refs, str):
        evidence_refs = [evidence_refs]
    if not isinstance(evidence_refs, list) or any(not isinstance(item, str) or not item for item in evidence_refs):
        raise CausalReviewError("master_confidence.evidence_refs must be a list of non-empty strings when present")
    return {
        "type": str(value.get("type", "unknown")),
        "value": value.get("value"),
        "threshold": threshold,
        "evidence_refs": list(evidence_refs),
    }


def _threshold(request: dict[str, Any]) -> float:
    policy = request.get("review_policy") or {}
    if not isinstance(policy, dict):
        raise CausalReviewError("review_policy must be an object when present")
    return float(policy.get("statistical_confidence_threshold", 0.95))


def _has_high_confidence_support(request: dict[str, Any]) -> bool:
    confidence = _confidence(request)
    confidence_type = confidence["type"]

    if confidence_type == "statistical":
        value = confidence["value"]
        if not isinstance(value, (int, float)):
            return False
        return float(value) >= float(confidence["threshold"]) and bool(confidence["evidence_refs"])

    if confidence_type in {"deterministic_proof", "contract_proven", "test_evidence_backed", "static_analysis_backed"}:
        if not confidence["evidence_refs"]:
            return False
        value = confidence["value"]
        if isinstance(value, bool):
            return value is True
        if isinstance(value, str):
            return value in {"high", "passed", "proven", "verified", "satisfied"}
        return value is not None

    return False


def _alternatives(request: dict[str, Any]) -> list[dict[str, Any]]:
    value = request.get("alternatives", [])
    if not isinstance(value, list):
        raise CausalReviewError("alternatives must be a list when present")
    alternatives: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise CausalReviewError("alternatives entries must be objects")
        alternatives.append(dict(item))
    return alternatives


def _conflicts(request: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    conflicts = _as_string_list(candidate.get("conflicts_with", []))
    for fact in _causal_context(request):
        if fact.get("conflicts_with_candidate") is True or fact.get("relation_to_candidate") == "conflict":
            conflicts.append(_context_id(fact, prefix="F"))
    return sorted(set(conflicts))


def _scope_overclaim(candidate: dict[str, Any]) -> bool:
    if candidate.get("scope_overclaim") is True or candidate.get("production_overclaim") is True:
        return True
    scope = _scope(candidate).lower()
    markers = ("all projects", "global", "production", "universal", "always")
    return any(marker in scope for marker in markers)


def _all_refs_exist(refs: list[str], context: list[dict[str, Any]]) -> bool:
    context_ids = {_context_id(item, prefix="F") for item in context}
    return set(refs).issubset(context_ids)


def _has_direct_write_attempt(value: dict[str, Any]) -> bool:
    for field in _DIRECT_WRITE_FIELDS:
        if value.get(field) is True:
            return True
    status = str(value.get("status", ""))
    return status in {"active_global_truth", "global_truth", "sealed_global_causal", "merged_to_global_truth"}
