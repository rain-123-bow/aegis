"""Project-store grounded context retrieval for DebateSubgraph."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from aegis.modules.debate.models import (
    ArtifactContextRef,
    CausalContextRef,
    DebateContextBundle,
    DebateInputPackage,
    DebateRuntimeConfig,
    DegradedRecallWarning,
    KnowledgeContextRef,
    MeasurementNeed,
    ProjectStoreBinding,
    RejectedCausalRef,
    RejectedArtifactRef,
    RejectedKnowledgeRef,
    RetrievalAudit,
)
from aegis.stores.causal.models import CausalQuery, ExpandContextRequest
from aegis.stores.causal.store import CausalStore
from aegis.stores.knowledge.models import KnowledgeQueryContext
from aegis.stores.knowledge.store import KnowledgeStore


def build_context_bundle(
    package: DebateInputPackage,
    binding: ProjectStoreBinding,
    config: DebateRuntimeConfig,
) -> DebateContextBundle:
    """Build Debate context from project-local Knowledge and Causal stores."""

    knowledge_refs: list[KnowledgeContextRef] = []
    rejected_knowledge_refs: list[RejectedKnowledgeRef] = []
    causal_refs: list[CausalContextRef] = []
    artifact_refs: list[ArtifactContextRef] = []
    rejected_causal_refs: list[RejectedCausalRef] = []
    rejected_artifact_refs: list[RejectedArtifactRef] = []
    missing_measurements: list[MeasurementNeed] = []
    warnings: list[DegradedRecallWarning] = []

    artifact_refs, rejected_artifact_refs = _validated_artifact_refs(
        package,
        binding,
        config,
    )

    knowledge_db = Path(binding.knowledge_store_root) / "knowledge.sqlite3"
    knowledge_store = KnowledgeStore(knowledge_db)
    knowledge_result = knowledge_store.query(_knowledge_query(package))
    knowledge_facts = _ranked_limited_items(
        [
        *knowledge_result.mandatory_facts,
        *knowledge_result.supplemental_facts,
        ],
        query_text=_query_text(package),
        text_getter=_knowledge_fact_text,
        limit=config.max_knowledge_context_refs,
    )
    for fact in knowledge_facts:
        evidence_ref = fact.evidence_refs[0].ref_id if fact.evidence_refs else ""
        knowledge_refs.append(
            KnowledgeContextRef(
                knowledge_id=fact.knowledge_id,
                statement=fact.semantic_summary,
                subject=fact.subject_id,
                object=fact.object,
                object_ref=str(fact.object),
                predicate=fact.predicate,
                scope=str(fact.fact_validity_scope),
                evidence_ref=evidence_ref,
                evidence_refs=[ref.ref_id for ref in fact.evidence_refs],
                applicability_reason="KnowledgeStore applicability query matched debate input.",
                confidence="high",
            )
        )
    for rejected in knowledge_result.rejected_facts:
        rejected_knowledge_refs.append(
            RejectedKnowledgeRef(
                ref=f"knowledge:{rejected.knowledge_id}",
                reason=rejected.reason,
            )
        )
    for need in knowledge_result.missing_knowledge_needs:
        missing_measurements.append(
            MeasurementNeed(
                need_id=need.need_id,
                question=need.why_needed,
                blocking_level=(
                    "blocking"
                    if need.blocking_level != "advisory"
                    else "non_blocking"
                ),
                suggested_owner=(
                    "test"
                    if need.blocking_level == "request_test_measurement"
                    else "master"
                ),
            )
        )
    for warning in knowledge_result.degraded_recall_warnings:
        warnings.append(
            DegradedRecallWarning(
                warning_id=warning.code,
                message=warning.message,
            )
        )

    causal_db = Path(binding.causal_store_root) / "causal.sqlite3"
    causal_store = CausalStore(causal_db)
    causal_query = causal_store.search_nodes(
        CausalQuery(
            query=_query_text(package),
            mode="admitted_only",
            include_rejected=True,
            limit=20,
        )
    )
    causal_nodes = _ranked_limited_items(
        causal_query.nodes,
        query_text=_query_text(package),
        text_getter=_causal_node_text,
        limit=config.max_causal_context_refs,
    )
    for node in causal_nodes:
        causal_refs.append(
            CausalContextRef(
                node_id=node.node_id,
                content=node.content,
                semantic_summary=node.semantic_summary,
                evidence_refs=[
                    ref_id
                    for group in node.dependency_groups
                    for ref_id in group.evidence_refs
                ],
                confidence="medium",
            )
        )
    for rejected in causal_query.rejected_nodes:
        rejected_causal_refs.append(
            RejectedCausalRef(
                ref=f"causal:{rejected.node_id}",
                reason=rejected.reason,
            )
        )
    for warning in causal_query.warnings:
        warnings.append(
            DegradedRecallWarning(
                warning_id=warning.code,
                message=warning.message,
            )
        )

    explicit_node_ids = [
        int(ref)
        for ref in package.causal_query_refs
        if str(ref).strip().isdigit()
    ]
    if explicit_node_ids:
        expanded = causal_store.expand_context(
            ExpandContextRequest(
                node_ids=explicit_node_ids,
                depth=2,
                mode="admitted_only",
            )
        )
        known_causal_ids = {ref.node_id for ref in causal_refs if ref.node_id is not None}
        for node_id in expanded.selected_nodes:
            if node_id in known_causal_ids:
                continue
            if len(causal_refs) >= config.max_causal_context_refs:
                break
            node = causal_store.get_node(node_id)
            causal_refs.append(_causal_ref_from_node(node))
            known_causal_ids.add(node_id)
        for rejected in expanded.rejected_nodes:
            rejected_causal_refs.append(
                RejectedCausalRef(
                    ref=f"causal:{rejected.node_id}",
                    reason=rejected.reason,
                )
            )

    degraded = bool(warnings or causal_query.degraded_recall)
    return DebateContextBundle(
        debate_id=None,
        knowledge_refs=knowledge_refs,
        rejected_knowledge_refs=rejected_knowledge_refs,
        causal_refs=causal_refs,
        artifact_refs=artifact_refs,
        rejected_causal_refs=rejected_causal_refs,
        rejected_artifact_refs=rejected_artifact_refs,
        missing_measurements=missing_measurements,
        degraded_recall_warnings=warnings,
        retrieval_audit=RetrievalAudit(
            knowledge_query_refs=package.knowledge_query_refs,
            causal_query_refs=package.causal_query_refs,
            admitted_knowledge_count=len(knowledge_refs),
            admitted_causal_count=len(causal_refs),
            degraded_recall=degraded,
        ),
    )


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _ranked_limited_items(
    items: list[Any],
    *,
    query_text: str,
    text_getter,
    limit: int,
) -> list[Any]:
    query_tokens = _tokens(query_text)

    def rank(item: Any) -> tuple[int, int, str]:
        item_text = text_getter(item)
        item_tokens = _tokens(item_text)
        exact_phrase_bonus = 1 if query_text and query_text.lower() in item_text.lower() else 0
        stable_id = str(getattr(item, "knowledge_id", getattr(item, "node_id", "")))
        return (len(query_tokens & item_tokens), exact_phrase_bonus, stable_id)

    ranked = sorted(items, key=rank, reverse=True)
    return ranked[:limit]


def _knowledge_fact_text(fact: Any) -> str:
    return " ".join(
        str(part)
        for part in (
            getattr(fact, "semantic_summary", ""),
            getattr(fact, "subject_id", ""),
            getattr(fact, "predicate", ""),
            getattr(fact, "object", ""),
            " ".join(getattr(fact, "semantic_keys", []) or []),
        )
        if part
    )


def _causal_node_text(node: Any) -> str:
    return " ".join(
        str(part)
        for part in (
            getattr(node, "content", ""),
            getattr(node, "semantic_summary", ""),
            " ".join(getattr(node, "semantic_keys", []) or []),
        )
        if part
    )


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        if len(token) > 2:
            tokens.add(token)
        if any("\u3400" <= char <= "\ufaff" for char in token):
            for size in (2, 3):
                if len(token) >= size:
                    tokens.update(
                        token[index : index + size]
                        for index in range(len(token) - size + 1)
                    )
    return tokens


def _knowledge_query(package: DebateInputPackage) -> KnowledgeQueryContext:
    return KnowledgeQueryContext(
        project_id=Path(package.project_root).name,
        task_intents=["implementation", "debate"],
        lifecycle_phase="debate",
        affected_entities=[
            package.decision_problem,
            *(position.statement for position in package.candidate_positions),
        ],
        operations=["choose implementation route", package.decision_problem],
        qualities=[
            *(position.summary for position in package.candidate_positions),
        ],
        conditions=package.source_artifact_refs,
        query_terms=_query_terms(package),
        mode="active",
    )


def _query_text(package: DebateInputPackage) -> str:
    return " ".join(_query_terms(package))


def _query_terms(package: DebateInputPackage) -> list[str]:
    terms = [package.decision_problem, *package.knowledge_query_refs]
    for position in package.candidate_positions:
        terms.extend([position.stance_id, position.statement, position.summary])
        terms.extend(position.source_artifact_refs)
    return [term for term in terms if str(term).strip()]


def _causal_ref_from_node(node) -> CausalContextRef:  # noqa: ANN001
    return CausalContextRef(
        node_id=node.node_id,
        content=node.content,
        semantic_summary=node.semantic_summary,
        evidence_refs=[
            ref_id
            for group in node.dependency_groups
            for ref_id in group.evidence_refs
        ],
        confidence="medium",
    )


def _validated_artifact_refs(
    package: DebateInputPackage,
    binding: ProjectStoreBinding,
    config: DebateRuntimeConfig,
) -> tuple[list[ArtifactContextRef], list[RejectedArtifactRef]]:
    verified: list[ArtifactContextRef] = []
    rejected: list[RejectedArtifactRef] = []
    seen: set[str] = set()
    for raw_ref in _input_artifact_refs(package):
        if raw_ref in seen:
            continue
        seen.add(raw_ref)
        resolved = _resolve_project_artifact(raw_ref, binding)
        if resolved is None:
            rejected.append(
                RejectedArtifactRef(
                    ref=raw_ref,
                    reason=(
                        "artifact ref must resolve to an existing non-code file "
                        "inside project_root"
                    ),
                )
            )
            continue
        verified.append(
            ArtifactContextRef(
                input_ref=raw_ref,
                resolved_ref=str(resolved),
                scope="project_artifact",
                content_preview=_read_artifact_preview(resolved, config.max_artifact_bytes),
            )
        )
    return verified, rejected


def _input_artifact_refs(package: DebateInputPackage) -> list[str]:
    refs = [str(ref) for ref in package.source_artifact_refs]
    for position in package.candidate_positions:
        refs.extend(str(ref) for ref in position.source_artifact_refs)
    return [ref for ref in refs if ref.strip()]


def _resolve_project_artifact(ref: str, binding: ProjectStoreBinding) -> Path | None:
    project_root = Path(binding.project_root).resolve()
    code_root = Path(binding.code_root).resolve()
    raw_path = Path(ref)
    candidate = raw_path if raw_path.is_absolute() else project_root / raw_path
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_file():
        return None
    if not _is_relative_to(resolved, project_root):
        return None
    if resolved == code_root or _is_relative_to(resolved, code_root):
        return None
    return resolved


def _read_artifact_preview(path: Path, max_bytes: int) -> str:
    byte_limit = min(max_bytes, 32_000)
    try:
        data = path.read_bytes()[:byte_limit]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
