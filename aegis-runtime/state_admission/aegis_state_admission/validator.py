from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

Decision = Literal[
    "accept_archive_candidate",
    "accept_knowledge_candidate",
    "stage_causal_candidate",
    "reject_wrong_store",
    "reject_insufficient_evidence",
    "reject_direct_global_write",
    "reject_local_only_causal",
    "needs_more_evidence",
    "needs_debate",
    "needs_master_structural_admission_review",
]
TargetStore = Literal["archive", "knowledge", "causal", "none"]
CandidateType = Literal["archive", "knowledge", "causal", "unknown"]

_ALLOWED_CAUSAL_SOURCES = {
    "master_unique_conclusion",
    "debate_leader_adjudication",
    "execution_leader_directional_reasoning",
}
_LOCAL_ONLY_CAUSAL_SOURCES = {
    "debate_worker_local",
    "ordinary_execution_detail",
    "test_route_evidence_only",
}
_DIRECT_GLOBAL_WRITE_FIELDS = (
    "global_causal_truth_mutation",
    "direct_global_write",
    "write_global_truth",
    "canonical_store_mutation",
)
_CAUSAL_TEXT_MARKERS = (
    " because ",
    " therefore ",
    " thus ",
    " hence ",
    " so ",
    "导致",
    "因此",
    "所以",
    "因为",
)


class StateAdmissionError(ValueError):
    """Raised when candidate input is malformed for Phase 22A validation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AdmissionDecision:
    admission_decision_id: str
    phase: str
    target_store: TargetStore
    decision: Decision
    why: str
    candidate_id: str
    candidate_type: CandidateType
    accepted_status: str
    required_next_step: str
    scope: str
    assumptions: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    candidate_admission_only: bool = True
    canonical_global_merge_allowed: bool = False
    store_write_performed: bool = False
    master_owned_admission: bool = True
    ordinary_agent_direct_write_allowed: bool = False
    global_causal_truth_mutation: bool = False
    production_storage_mutation: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "admission_decision_id": self.admission_decision_id,
            "phase": self.phase,
            "target_store": self.target_store,
            "decision": self.decision,
            "why": self.why,
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "accepted_status": self.accepted_status,
            "required_next_step": self.required_next_step,
            "scope": self.scope,
            "assumptions": list(self.assumptions),
            "evidence_refs": list(self.evidence_refs),
            "candidate_admission_only": self.candidate_admission_only,
            "canonical_global_merge_allowed": self.canonical_global_merge_allowed,
            "store_write_performed": self.store_write_performed,
            "master_owned_admission": self.master_owned_admission,
            "ordinary_agent_direct_write_allowed": self.ordinary_agent_direct_write_allowed,
            "global_causal_truth_mutation": self.global_causal_truth_mutation,
            "production_storage_mutation": self.production_storage_mutation,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateAdmissionError(f"candidate file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateAdmissionError(f"candidate file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StateAdmissionError("candidate file must contain a JSON object")
    return payload


def validate_candidate_file(path: str | Path) -> AdmissionDecision:
    return validate_candidate(load_json_object(path))


def validate_candidate(candidate: dict[str, Any]) -> AdmissionDecision:
    if not isinstance(candidate, dict):
        raise StateAdmissionError("candidate must be a JSON object")

    candidate_type = _candidate_type(candidate)
    requested_store = _requested_store(candidate)
    candidate_id = _candidate_id(candidate)

    direct_global_write = _has_direct_global_write(candidate)
    if direct_global_write:
        return _decision(
            decision="reject_direct_global_write",
            target_store="none",
            candidate_type=candidate_type,
            candidate_id=candidate_id,
            why="Phase 22A admits candidates only and must reject direct global truth or production store mutation attempts.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="rejected",
            required_next_step="remove_direct_global_write_and_resubmit_as_candidate",
        )

    if requested_store == "archive" or candidate_type == "archive":
        return _validate_archive(candidate, candidate_id=candidate_id, candidate_type=candidate_type)
    if requested_store == "knowledge" or candidate_type == "knowledge":
        return _validate_knowledge(candidate, candidate_id=candidate_id, candidate_type=candidate_type)
    if requested_store == "causal" or candidate_type == "causal":
        return _validate_causal(candidate, candidate_id=candidate_id, candidate_type=candidate_type)

    return _decision(
        decision="reject_wrong_store",
        target_store="none",
        candidate_type="unknown",
        candidate_id=candidate_id,
        why="Candidate must explicitly target archive, knowledge, or causal admission.",
        scope=_scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        accepted_status="rejected",
        required_next_step="classify_candidate_store_before_resubmission",
    )


def _validate_archive(candidate: dict[str, Any], *, candidate_id: str, candidate_type: CandidateType) -> AdmissionDecision:
    if candidate_type not in {"archive", "unknown"}:
        return _wrong_store(candidate, candidate_id, candidate_type, "archive")
    if candidate.get("truth_status") in {"knowledge", "causal", "global_truth", "active_global_truth"}:
        return _decision(
            decision="reject_wrong_store",
            target_store="archive",
            candidate_type="archive",
            candidate_id=candidate_id,
            why="Archive records history and responsibility, but it must not claim Knowledge, Causal, or global truth status.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="rejected",
            required_next_step="remove_truth_claim_or_submit_to_knowledge_or_causal_admission",
        )
    missing = [field for field in ("task_id", "event_type", "actor", "occurred_at") if not _has_non_empty(candidate, field)]
    if missing:
        return _insufficient(candidate, candidate_id, "archive", f"Archive candidate missing required field(s): {', '.join(missing)}")
    if not _evidence_refs(candidate):
        return _insufficient(candidate, candidate_id, "archive", "Archive candidate requires at least one evidence or artifact reference.")
    return _decision(
        decision="accept_archive_candidate",
        target_store="archive",
        candidate_type="archive",
        candidate_id=candidate_id,
        why="Archive candidate records a task event/responsibility item and does not claim truth production.",
        scope=_scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        accepted_status="archive_candidate",
        required_next_step="master_record_archive_entry_or_stage_archive_update",
    )


def _validate_knowledge(candidate: dict[str, Any], *, candidate_id: str, candidate_type: CandidateType) -> AdmissionDecision:
    if candidate_type not in {"knowledge", "unknown"}:
        return _wrong_store(candidate, candidate_id, candidate_type, "knowledge")
    if _has_causal_shape(candidate):
        return _decision(
            decision="reject_wrong_store",
            target_store="knowledge",
            candidate_type="knowledge",
            candidate_id=candidate_id,
            why="Knowledge stores neutral facts and constraints; causal reasoning chains must go through Causal admission.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="rejected",
            required_next_step="route_to_causal_admission_if_causal_structure_is_intended",
        )
    missing = [field for field in ("statement", "scope", "version_context") if not _has_non_empty(candidate, field)]
    if missing:
        return _insufficient(candidate, candidate_id, "knowledge", f"Knowledge candidate missing required field(s): {', '.join(missing)}")
    if not _evidence_refs(candidate):
        return _insufficient(candidate, candidate_id, "knowledge", "Knowledge candidate requires source-backed evidence.")
    if candidate.get("claim_status") == "developer_asserted" and not candidate.get("master_verified"):
        return _decision(
            decision="needs_more_evidence",
            target_store="knowledge",
            candidate_type="knowledge",
            candidate_id=candidate_id,
            why="Developer assertions cannot become active Knowledge without Master verification and evidence review.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="needs_more_evidence",
            required_next_step="master_verify_claim_or_record_assertion_in_archive",
        )
    return _decision(
        decision="accept_knowledge_candidate",
        target_store="knowledge",
        candidate_type="knowledge",
        candidate_id=candidate_id,
        why="Knowledge candidate is a source-backed neutral fact or constraint without causal reasoning content.",
        scope=_scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        accepted_status="knowledge_candidate",
        required_next_step="master_review_and_stage_knowledge_update",
    )


def _validate_causal(candidate: dict[str, Any], *, candidate_id: str, candidate_type: CandidateType) -> AdmissionDecision:
    if candidate_type not in {"causal", "unknown"}:
        return _wrong_store(candidate, candidate_id, candidate_type, "causal")

    source_origin = str(candidate.get("source_origin", ""))
    if source_origin in _LOCAL_ONLY_CAUSAL_SOURCES:
        return _decision(
            decision="reject_local_only_causal",
            target_store="causal",
            candidate_type="causal",
            candidate_id=candidate_id,
            why="Local Debate Worker, ordinary implementation, or Test evidence-only reasoning is not directly admissible as project-level Causal state.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="rejected",
            required_next_step="submit_through_debate_leader_or_master_project_direction_review",
        )

    if candidate.get("requires_debate") is True or candidate.get("multiple_plausible_paths") is True:
        return _decision(
            decision="needs_debate",
            target_store="causal",
            candidate_type="causal",
            candidate_id=candidate_id,
            why="Causal proposal declares unresolved alternative paths, so Master must route to Debate instead of admitting a project-level causal candidate.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="needs_debate",
            required_next_step="route_to_debate_for_adjudicated_causal_chain",
        )

    if source_origin == "execution_leader_directional_reasoning" and candidate.get("implementation_path_unique") is not True:
        return _decision(
            decision="needs_debate",
            target_store="causal",
            candidate_type="causal",
            candidate_id=candidate_id,
            why="Execution Leader directional reasoning is admissible only when the implementation path is effectively unique; otherwise Debate is required.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="needs_debate",
            required_next_step="route_to_debate_or_provide_effective_uniqueness_evidence",
        )

    if source_origin not in _ALLOWED_CAUSAL_SOURCES:
        return _decision(
            decision="reject_insufficient_evidence",
            target_store="causal",
            candidate_type="causal",
            candidate_id=candidate_id,
            why="Causal candidate must declare an allowed project-level source origin: Master unique conclusion, Debate Leader adjudication, or Execution Leader directional reasoning under effective uniqueness.",
            scope=_scope(candidate),
            assumptions=_assumptions(candidate),
            evidence_refs=_evidence_refs(candidate),
            accepted_status="rejected",
            required_next_step="provide_allowed_source_origin_or_route_to_debate",
        )

    missing = [field for field in ("statement", "why", "scope") if not _has_non_empty(candidate, field)]
    if not _assumptions(candidate):
        missing.append("assumptions")
    if not _evidence_refs(candidate):
        missing.append("evidence")
    if missing:
        return _insufficient(candidate, candidate_id, "causal", f"Causal candidate missing required field(s): {', '.join(missing)}")

    if not str(candidate.get("why", "")).strip():
        return _insufficient(candidate, candidate_id, "causal", "Causal candidate cannot be a bare conclusion; why is required.")

    # For source_origin == debate_leader_adjudication, reaching this branch means
    # Master-owned structural admission review staged the result only as a
    # candidate. Debate Leader output is never automatically accepted and never
    # becomes global truth in Phase 22A.
    return _decision(
        decision="stage_causal_candidate",
        target_store="causal",
        candidate_type="causal",
        candidate_id=candidate_id,
        why=(
            "Master structural admission review staged this complete causal structure only as a Phase 22A Causal candidate. "
            "This is not canonical/global causal truth and not a production Causal Store write."
        ),
        scope=_scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        accepted_status="causal_candidate",
        required_next_step="future_high_budget_causal_review_before_global_merge",
    )


def _wrong_store(candidate: dict[str, Any], candidate_id: str, candidate_type: CandidateType, expected: TargetStore) -> AdmissionDecision:
    return _decision(
        decision="reject_wrong_store",
        target_store=expected,
        candidate_type=candidate_type,
        candidate_id=candidate_id,
        why=f"Candidate type {candidate_type} does not match requested {expected} store admission.",
        scope=_scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        accepted_status="rejected",
        required_next_step="resubmit_to_the_matching_store_admission_path",
    )


def _insufficient(candidate: dict[str, Any], candidate_id: str, target_store: TargetStore, why: str) -> AdmissionDecision:
    return _decision(
        decision="reject_insufficient_evidence",
        target_store=target_store,
        candidate_type=_candidate_type(candidate),
        candidate_id=candidate_id,
        why=why,
        scope=_scope(candidate),
        assumptions=_assumptions(candidate),
        evidence_refs=_evidence_refs(candidate),
        accepted_status="rejected",
        required_next_step="provide_required_fields_and_evidence_before_resubmission",
    )


def _decision(
    *,
    decision: Decision,
    target_store: TargetStore,
    candidate_type: CandidateType,
    candidate_id: str,
    why: str,
    scope: str,
    assumptions: list[str],
    evidence_refs: list[str],
    accepted_status: str,
    required_next_step: str,
) -> AdmissionDecision:
    return AdmissionDecision(
        admission_decision_id=f"admission-{uuid4().hex}",
        phase="phase22a_three_store_admission",
        target_store=target_store,
        decision=decision,
        why=why,
        candidate_id=candidate_id,
        candidate_type=candidate_type,
        accepted_status=accepted_status,
        required_next_step=required_next_step,
        scope=scope,
        assumptions=assumptions,
        evidence_refs=evidence_refs,
    )


def _candidate_type(candidate: dict[str, Any]) -> CandidateType:
    value = str(candidate.get("candidate_type") or candidate.get("store") or candidate.get("target_store") or "unknown")
    if value in {"archive", "archive_candidate"}:
        return "archive"
    if value in {"knowledge", "knowledge_candidate"}:
        return "knowledge"
    if value in {"causal", "causal_candidate"}:
        return "causal"
    return "unknown"


def _requested_store(candidate: dict[str, Any]) -> TargetStore:
    value = str(candidate.get("target_store") or candidate.get("store") or candidate.get("candidate_type") or "none")
    if "archive" in value:
        return "archive"
    if "knowledge" in value:
        return "knowledge"
    if "causal" in value:
        return "causal"
    return "none"


def _candidate_id(candidate: dict[str, Any]) -> str:
    for key in ("candidate_id", "id", "task_id", "statement_id"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return f"candidate-{uuid4().hex}"


def _scope(candidate: dict[str, Any]) -> str:
    value = candidate.get("scope", "")
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, str) and value:
        return value
    return "unspecified"


def _assumptions(candidate: dict[str, Any]) -> list[str]:
    value = candidate.get("assumptions")
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise StateAdmissionError("assumptions must be a list of non-empty strings when present")
    return list(value)


def _evidence_refs(candidate: dict[str, Any]) -> list[str]:
    evidence = candidate.get("evidence") or candidate.get("evidence_refs") or candidate.get("artifact_refs") or []
    if isinstance(evidence, str):
        return [evidence] if evidence else []
    if not isinstance(evidence, list):
        raise StateAdmissionError("evidence/evidence_refs/artifact_refs must be a list or string when present")
    refs: list[str] = []
    for item in evidence:
        if isinstance(item, str) and item:
            refs.append(item)
        elif isinstance(item, dict):
            ref = item.get("ref") or item.get("path") or item.get("id")
            if isinstance(ref, str) and ref:
                refs.append(ref)
        else:
            raise StateAdmissionError("evidence list entries must be strings or objects with ref/path/id")
    return refs


def _has_non_empty(candidate: dict[str, Any], field_name: str) -> bool:
    value = candidate.get(field_name)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _has_direct_global_write(candidate: dict[str, Any]) -> bool:
    for field_name in _DIRECT_GLOBAL_WRITE_FIELDS:
        if candidate.get(field_name) is True:
            return True
    status = str(candidate.get("status", ""))
    if status in {"active_global_truth", "global_truth", "sealed_global_causal"}:
        return True
    return False


def _has_causal_shape(candidate: dict[str, Any]) -> bool:
    if any(key in candidate for key in ("why", "depends_on", "invalidates", "supersedes", "causal_chain")):
        return True
    text = f" {candidate.get('statement', '')} ".lower()
    return any(marker in text for marker in _CAUSAL_TEXT_MARKERS)
