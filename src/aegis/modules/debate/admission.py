"""Admission and relation checks for DebateSubgraph."""

from __future__ import annotations

import re

from aegis.modules.debate.models import (
    ConstraintStatus,
    DebateContextBundle,
    DebateInputPackage,
    HardConstraintValidation,
    StanceAdmissionRecord,
    StanceAdmissionStatus,
    StanceRelationKind,
    StanceRelationRecord,
)


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_NEGATION_TERMS = {
    "against",
    "ban",
    "banned",
    "blocks",
    "cannot",
    "contraindicated",
    "disallow",
    "disallowed",
    "forbid",
    "forbidden",
    "forbids",
    "incompatible",
    "not",
    "reject",
    "rejected",
    "rejects",
    "unsupported",
}
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "by",
    "for",
    "has",
    "have",
    "is",
    "mandatory",
    "must",
    "of",
    "or",
    "rule",
    "required",
    "requires",
    "require",
    "route",
    "should",
    "the",
    "to",
    "use",
}


def validate_hard_constraints(
    package: DebateInputPackage,
    context: DebateContextBundle,
) -> list[HardConstraintValidation]:
    """Validate claimed hard constraints against objective evidence refs."""

    evidence = _evidence_index(context)
    validations: list[HardConstraintValidation] = []
    for constraint in package.hard_constraints:
        matched = evidence.get(constraint.evidence_ref or "")
        if matched and _statement_supported_by_evidence(
            constraint.statement,
            matched.text,
            minimum_overlap=2,
        ):
            validations.append(
                HardConstraintValidation(
                    constraint_id=constraint.constraint_id,
                    status=ConstraintStatus.VERIFIED,
                    reason=(
                        "Hard constraint evidence exists and materially "
                        "corresponds to the constraint statement."
                    ),
                    evidence_refs=[matched.ref],
                    matched_knowledge_refs=matched.knowledge_refs,
                    matched_causal_refs=matched.causal_refs,
                    matched_artifact_refs=matched.artifact_refs,
                )
            )
            continue
        validations.append(
            HardConstraintValidation(
                constraint_id=constraint.constraint_id,
                status=ConstraintStatus.UNSUPPORTED,
                reason=(
                    "Claimed hard constraint lacks project fact, written "
                    "evidence, platform rule, or first-principles necessity."
                ),
                evidence_refs=[],
            )
        )
    return validations


def admit_stances(
    package: DebateInputPackage,
    context: DebateContextBundle,
    hard_constraint_validations: list[HardConstraintValidation],
) -> list[StanceAdmissionRecord]:
    """Admit stances that have objective or first-principles support."""

    _ = hard_constraint_validations
    evidence = _evidence_index(context)
    records: list[StanceAdmissionRecord] = []
    for position in package.candidate_positions:
        supporting_refs: list[str] = []
        position_text = f"{position.statement} {position.summary}"
        for entry in evidence.values():
            if _statement_supported_by_evidence(
                position_text,
                entry.text,
                minimum_overlap=1,
            ):
                supporting_refs.append(entry.ref)
        supporting_refs = sorted(set(supporting_refs))
        if supporting_refs:
            records.append(
                StanceAdmissionRecord(
                    stance_id=position.stance_id,
                    status=StanceAdmissionStatus.ADMITTED,
                    reason="Stance has objective artifact or store context support.",
                    supporting_refs=supporting_refs,
                )
            )
            continue
        records.append(
            StanceAdmissionRecord(
                stance_id=position.stance_id,
                status=StanceAdmissionStatus.REJECTED,
                reason=(
                    "Stance lacks evidence, project knowledge, causal context, "
                    "or explicit first-principles necessity."
                ),
                supporting_refs=[],
            )
        )
    return records


def analyze_stance_relations(
    package: DebateInputPackage,
    admission_records: list[StanceAdmissionRecord],
    context: DebateContextBundle,
) -> list[StanceRelationRecord]:
    """Classify relations between admitted stances."""

    _ = context
    admitted = {
        record.stance_id
        for record in admission_records
        if record.status == StanceAdmissionStatus.ADMITTED
    }
    positions = [
        position
        for position in package.candidate_positions
        if position.stance_id in admitted
    ]
    relations: list[StanceRelationRecord] = []
    for index, left in enumerate(positions):
        for right in positions[index + 1 :]:
            if _normalized(left.statement) == _normalized(right.statement):
                relations.append(
                    StanceRelationRecord(
                        left_stance_id=left.stance_id,
                        right_stance_id=right.stance_id,
                        relation=StanceRelationKind.DUPLICATE,
                        reason="The two stances make the same material claim.",
                    )
                )
            else:
                relations.append(
                    StanceRelationRecord(
                        left_stance_id=left.stance_id,
                        right_stance_id=right.stance_id,
                        relation=StanceRelationKind.MUTUALLY_EXCLUSIVE,
                        reason=(
                            "The stances propose different selectable routes "
                            "for the same decision problem."
                        ),
                    )
                )
    return relations


class _ContextText:
    def __init__(self, tokens: set[str], refs: list[str]) -> None:
        self.tokens = tokens
        self.refs = refs


class _EvidenceEntry:
    def __init__(
        self,
        *,
        ref: str,
        text: str,
        knowledge_refs: list[str] | None = None,
        causal_refs: list[int] | None = None,
        artifact_refs: list[str] | None = None,
    ) -> None:
        self.ref = ref
        self.text = text
        self.knowledge_refs = knowledge_refs or []
        self.causal_refs = causal_refs or []
        self.artifact_refs = artifact_refs or []


def _context_text(context: DebateContextBundle) -> _ContextText:
    texts: list[str] = []
    refs: list[str] = []
    for knowledge_ref in context.knowledge_refs:
        texts.extend(
            [
                knowledge_ref.statement,
                knowledge_ref.object_ref or "",
                knowledge_ref.predicate or "",
                knowledge_ref.scope,
            ]
        )
        refs.append(knowledge_ref.evidence_ref)
        if knowledge_ref.knowledge_id is not None:
            refs.append(f"knowledge:{knowledge_ref.knowledge_id}")
    for causal_ref in context.causal_refs:
        texts.extend([causal_ref.content, causal_ref.semantic_summary])
        refs.extend(causal_ref.evidence_refs)
        if causal_ref.node_id is not None:
            refs.append(f"causal:{causal_ref.node_id}")
    for artifact_ref in context.artifact_refs:
        texts.extend([artifact_ref.input_ref, artifact_ref.content_preview])
        refs.append(artifact_ref.resolved_ref)
    return _ContextText(tokens=_tokens(" ".join(texts)), refs=sorted(set(refs)))


def _evidence_index(context: DebateContextBundle) -> dict[str, _EvidenceEntry]:
    index: dict[str, _EvidenceEntry] = {}
    for knowledge_ref in context.knowledge_refs:
        text = " ".join(
            [
                knowledge_ref.statement,
                knowledge_ref.subject or "",
                knowledge_ref.predicate or "",
                knowledge_ref.object_ref or knowledge_ref.object or "",
                knowledge_ref.scope,
            ]
        )
        refs = [knowledge_ref.evidence_ref, *knowledge_ref.evidence_refs]
        for ref in refs:
            if not ref:
                continue
            index[ref] = _EvidenceEntry(
                ref=ref,
                text=text,
                knowledge_refs=[
                    f"knowledge:{knowledge_ref.knowledge_id}"
                    if knowledge_ref.knowledge_id is not None
                    else ref
                ],
            )
    for causal_ref in context.causal_refs:
        text = " ".join([causal_ref.content, causal_ref.semantic_summary])
        if causal_ref.node_id is not None:
            index[f"causal:{causal_ref.node_id}"] = _EvidenceEntry(
                ref=f"causal:{causal_ref.node_id}",
                text=text,
                causal_refs=[causal_ref.node_id],
            )
        for ref in causal_ref.evidence_refs:
            index[ref] = _EvidenceEntry(
                ref=ref,
                text=text,
                causal_refs=[causal_ref.node_id] if causal_ref.node_id is not None else [],
            )
    for artifact_ref in context.artifact_refs:
        text = " ".join([artifact_ref.input_ref, artifact_ref.content_preview])
        for ref in (artifact_ref.input_ref, artifact_ref.resolved_ref):
            index[ref] = _EvidenceEntry(
                ref=ref,
                text=text,
                artifact_refs=[artifact_ref.resolved_ref],
            )
    return index


def _verified_artifact_ref_map(context: DebateContextBundle) -> dict[str, str]:
    refs: dict[str, str] = {}
    for artifact_ref in context.artifact_refs:
        refs[artifact_ref.input_ref] = artifact_ref.resolved_ref
        refs[artifact_ref.resolved_ref] = artifact_ref.resolved_ref
    return refs


def _statement_supported_by_evidence(
    statement: str,
    evidence_text: str,
    *,
    minimum_overlap: int = 2,
) -> bool:
    statement_tokens = _material_tokens(statement)
    evidence_tokens = _material_tokens(evidence_text)
    if not statement_tokens or not evidence_tokens:
        return False
    overlap = statement_tokens & evidence_tokens
    if not overlap:
        return False
    if _has_opposing_polarity(statement, evidence_text, overlap):
        return False
    required_overlap = 1 if len(statement_tokens) <= 2 else minimum_overlap
    return len(overlap) >= required_overlap


def _token_sequence(text: str) -> list[str]:
    base_tokens: list[str] = []
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        base_tokens.append(token)
        tokens.append(token)
        if any("\u3400" <= char <= "\ufaff" for char in token):
            for size in (2, 3):
                if len(token) >= size:
                    tokens.extend(
                        token[index : index + size]
                        for index in range(len(token) - size + 1)
                    )
    for index, token in enumerate(base_tokens[:-1]):
        if token in {"option", "plan", "route", "stance"}:
            tokens.append(f"{token}_{base_tokens[index + 1]}")
    return tokens


def _tokens(text: str) -> set[str]:
    return set(_token_sequence(text))


def _material_tokens(text: str) -> set[str]:
    return {
        token
        for token in _tokens(text)
        if len(token) > 2 and token not in _STOPWORDS
    }


def _has_opposing_polarity(
    statement: str,
    evidence_text: str,
    overlap: set[str],
) -> bool:
    statement_negated = _negated_material_tokens(statement, overlap)
    evidence_negated = _negated_material_tokens(evidence_text, overlap)
    return statement_negated != evidence_negated


def _negated_material_tokens(text: str, target_tokens: set[str]) -> set[str]:
    sequence = _token_sequence(text)
    negated: set[str] = set()
    for index, token in enumerate(sequence):
        if token not in target_tokens:
            continue
        start = max(0, index - 4)
        end = min(len(sequence), index + 5)
        window = set(sequence[start:end])
        if window & _NEGATION_TERMS:
            negated.add(token)
    return negated


def _normalized(text: str) -> str:
    return " ".join(sorted(_tokens(text)))
