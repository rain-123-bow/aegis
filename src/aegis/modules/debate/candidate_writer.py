"""Causal-store candidate writing for DebateSubgraph."""

from __future__ import annotations

from pathlib import Path
import re

from aegis.modules.debate.models import (
    CausalCandidateNode,
    CausalCandidateWriteResult,
    CausalStoreUpdateCandidate,
    DebateInputPackage,
    ProjectStoreBinding,
)
from aegis.stores.causal.models import CausalDependencyGroup, CausalNodeDraft
from aegis.stores.causal.models import CausalStoreError
from aegis.stores.causal.store import CausalStore


class CausalCandidateWriteError(RuntimeError):
    """Raised when Debate causal candidate persistence is not trustworthy."""

    def __init__(self, result: CausalCandidateWriteResult) -> None:
        super().__init__("causal candidate write failed")
        self.result = result


def build_update_candidate(
    *,
    package: DebateInputPackage,
    debate_id: str,
    selected_stance_id: str,
    rejected_stance_ids: list[str],
    nodes: list[CausalCandidateNode],
    reused_node_ids: list[int] | None = None,
) -> CausalStoreUpdateCandidate:
    """Build the machine-readable causal-store update candidate."""

    return CausalStoreUpdateCandidate(
        candidate_id=f"{debate_id}-causal-candidate",
        request_id=package.request_id,
        debate_id=debate_id,
        selected_stance_id=selected_stance_id,
        nodes=nodes,
        reused_node_ids=reused_node_ids or [],
        rejected_alternatives=rejected_stance_ids,
    )


def write_causal_store_candidate(
    *,
    binding: ProjectStoreBinding,
    artifact_ref: str,
    candidate: CausalStoreUpdateCandidate,
) -> CausalCandidateWriteResult:
    """Write Debate causal candidates to the project-local Causal Store."""

    store = CausalStore(Path(binding.causal_store_root) / "causal.sqlite3")
    existing: list[int] = []
    skipped: list[str] = []
    errors: list[dict[str, object]] = []

    unresolved = _unresolved_local_dependency_errors(candidate.nodes)
    if unresolved:
        result = CausalCandidateWriteResult(
            candidate_id=candidate.candidate_id,
            artifact_ref=artifact_ref,
            write_status="failed",
            inserted_node_ids=[],
            existing_node_ids=[],
            skipped_node_refs=[],
            errors=unresolved,
        )
        raise CausalCandidateWriteError(result)

    drafts = [
        _to_causal_node_draft(candidate, node, artifact_ref)
        for node in candidate.nodes
    ]
    existing_ids = store.existing_candidate_node_ids(drafts)
    if existing_ids and all(node_id is not None for node_id in existing_ids):
        return CausalCandidateWriteResult(
            candidate_id=candidate.candidate_id,
            artifact_ref=artifact_ref,
            write_status="already_exists",
            inserted_node_ids=[],
            existing_node_ids=sorted({int(node_id) for node_id in existing_ids if node_id is not None}),
            skipped_node_refs=[node.local_node_ref for node in candidate.nodes],
            errors=[],
        )
    if any(node_id is not None for node_id in existing_ids):
        result = CausalCandidateWriteResult(
            candidate_id=candidate.candidate_id,
            artifact_ref=artifact_ref,
            write_status="failed",
            inserted_node_ids=[],
            existing_node_ids=sorted({int(node_id) for node_id in existing_ids if node_id is not None}),
            skipped_node_refs=[],
            errors=[
                {
                    "node_ref": None,
                    "code": "PARTIAL_DUPLICATE_PACKAGE",
                    "message": (
                        "causal candidate package partially overlaps existing "
                        "active candidate nodes and cannot be written safely"
                    ),
                }
            ],
        )
        raise CausalCandidateWriteError(result)
    try:
        inserted = store.put_candidates(drafts)
        status = "written" if inserted else "failed"
    except CausalStoreError as exc:
        existing_ids = store.existing_candidate_node_ids(drafts)
        if existing_ids and all(node_id is not None for node_id in existing_ids):
            return CausalCandidateWriteResult(
                candidate_id=candidate.candidate_id,
                artifact_ref=artifact_ref,
                write_status="already_exists",
                inserted_node_ids=[],
                existing_node_ids=sorted({int(node_id) for node_id in existing_ids if node_id is not None}),
                skipped_node_refs=[node.local_node_ref for node in candidate.nodes],
                errors=[],
            )
        existing_node_id = _existing_node_id_from_error(exc)
        if existing_node_id is not None:
            existing.append(existing_node_id)
        if exc.code in {"DUPLICATE_NODE", "NEAR_DUPLICATE_REVIEW_REQUIRED"} and len(drafts) == 1:
            skipped.append(candidate.nodes[0].local_node_ref)
            errors.append(
                {
                    "node_ref": candidate.nodes[0].local_node_ref,
                    "code": exc.code,
                    "message": exc.message,
                    "existing_node_id": existing_node_id,
                }
            )
            inserted = []
            status = "already_exists"
        else:
            errors.append(
                {
                    "node_ref": None,
                    "code": exc.code,
                    "message": exc.message,
                    "existing_node_id": existing_node_id,
                }
            )
            inserted = []
            status = "failed"
    except Exception as exc:  # noqa: BLE001
        errors.append(
            {
                "node_ref": None,
                "code": "UNEXPECTED_WRITE_ERROR",
                "message": str(exc),
            }
        )
        inserted = []
        status = "failed"

    result = CausalCandidateWriteResult(
        candidate_id=candidate.candidate_id,
        artifact_ref=artifact_ref,
        write_status=status,
        inserted_node_ids=inserted,
        existing_node_ids=sorted(set(existing)),
        skipped_node_refs=skipped,
        errors=errors,
    )
    if status in {"failed", "partial_failed"}:
        raise CausalCandidateWriteError(result)
    return result


def _to_causal_node_draft(
    candidate: CausalStoreUpdateCandidate,
    node: CausalCandidateNode,
    artifact_ref: str,
) -> CausalNodeDraft:
    groups = [
        CausalDependencyGroup(
            group_id=group.group_id,
            causal_dependencies=[
                int(value)
                for value in group.causal_dependencies
            ],
            knowledge_refs=group.knowledge_refs,
            evidence_refs=group.evidence_refs,
            scope=group.scope,
            conditions=group.conditions,
            assumptions=group.assumptions,
            confidence=group.confidence,
            invalidation_conditions=group.invalidation_conditions,
        )
        for group in node.dependency_groups
    ]
    return CausalNodeDraft(
        content=node.statement,
        semantic_summary=node.semantic_summary,
        semantic_keys=node.semantic_keys,
        source_module="debate",
        source_run_id=candidate.debate_id,
        source_artifact_ref=artifact_ref,
        root_kind="design_decision",
        node_refs=[],
        dependency_groups=groups,
    )


def _unresolved_local_dependency_errors(
    nodes: list[CausalCandidateNode],
) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    local_refs = {node.local_node_ref for node in nodes}
    for node in nodes:
        for group in node.dependency_groups:
            for value in group.causal_dependencies:
                if str(value).isdigit():
                    continue
                code = (
                    "UNSUPPORTED_LOCAL_DEPENDENCY"
                    if value in local_refs
                    else "UNRESOLVED_LOCAL_DEPENDENCY"
                )
                errors.append(
                    {
                        "node_ref": node.local_node_ref,
                        "code": code,
                        "message": (
                            "Debate candidate package writes are atomic; "
                            "local causal dependency refs must be resolved "
                            f"before persistence: {value}"
                        ),
                    }
                )
    return errors


def _existing_node_id_from_error(exc: CausalStoreError) -> int | None:
    if "node_id" in exc.context:
        value = exc.context["node_id"]
        return int(value) if str(value).isdigit() else None
    match = re.search(r"node\s+(\d+)", exc.message)
    return int(match.group(1)) if match else None
