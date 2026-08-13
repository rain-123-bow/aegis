from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from project_seal_store import ProjectSealStoreError, verify_expected_project_seal


DECISION_SCHEMA = "aegis.semantic_decoy_decision.v1"
MANIFEST_SCHEMA = "aegis.semantic_decoy_manifest.v1"
REQUIREMENT_BINDING_SCHEMA = "aegis.semantic_decoy_requirement_binding.v1"
REVIEW_RECEIPT_SCHEMA = "aegis.semantic_decoy_review_receipt.v1"

_DECISION_FILENAME = "SEMANTIC_DECOY_DECISION.json"
_REQUIREMENT_HEADING = "## 17. Code Obfuscation and Semantic Decoy Decision"
_REQUIREMENT_FENCE = "```semantic-decoy-decision-binding"
_REVIEWS_REQUIRED_REASON = "independent semantic decoy reviews are required"

_DECISION_FIELDS = {
    "schema",
    "task_id",
    "phase",
    "enabled",
    "decision_source",
    "response_summary",
    "asked_at_utc",
    "answered_at_utc",
}
_REQUIREMENT_BINDING_FIELDS = {
    "schema",
    "task_id",
    "enabled",
    "decision_source",
    "decision_path",
    "decision_sha256",
}
_MANIFEST_FIELDS = {
    "schema",
    "task_id",
    "decision_sha256",
    "requirement_document_sha256",
    "context_pack_sha256",
    "project_seal",
    "frozen_at_utc",
    "entries",
}
_ENTRY_FIELDS = {
    "decoy_id",
    "classification",
    "code_anchors",
    "predicate",
    "true_semantics",
    "surface_semantics",
    "constraint_item_ids",
    "invalidation_conditions",
}
_REVIEW_RECEIPT_FIELDS = {
    "schema",
    "stage",
    "reviewer_role",
    "reviewer_identity",
    "reviewed_artifact_name",
    "reviewed_artifact_sha256",
    "task_id",
    "frozen_at_utc",
    "reviewed_at_utc",
    "manifest_sha256",
    "decision_sha256",
    "requirement_document_sha256",
    "context_pack_sha256",
    "project_seal",
    "verdict",
    "entries",
}
_REVIEW_ENTRY_FIELDS = {"decoy_id", "predicate", "constraints", "verdict"}
_CONSTRAINT_BINDING_FIELDS = {
    "item_id",
    "version",
    "evidence_path",
    "evidence_sha256",
}
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_PROJECT_SEAL = re.compile(r"ASC1:[0-9a-f]{64}")


class SemanticDecoyContractError(ValueError):
    pass


class DecoyClassification(str, Enum):
    REAL = "REAL"
    DECOY_UNREACHABLE = "DECOY_UNREACHABLE"
    UNKNOWN_STALE = "UNKNOWN-STALE"


@dataclass(frozen=True, slots=True)
class SemanticDecoyDecision:
    task_id: str
    enabled: bool
    decision_source: str
    response_summary: str
    asked_at_utc: str
    answered_at_utc: str


@dataclass(frozen=True, slots=True)
class SemanticDecoyEntryEvaluation:
    decoy_id: str
    declared_classification: DecoyClassification
    structural_classification: DecoyClassification
    effective_classification: DecoyClassification
    internal_logic_test_required: bool
    perimeter_tests_required: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticDecoyEvaluation:
    policy_enabled: bool
    entries: tuple[SemanticDecoyEntryEvaluation, ...]
    structurally_eligible_decoy_ids: tuple[str, ...]
    all_declared_decoys_structurally_valid: bool
    authorization_complete: bool
    reviewer_identities: tuple[str, ...]
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReviewReceipt:
    stage: str
    reviewer_identity: str
    reasons: tuple[str, ...]


def parse_semantic_decoy_decision(
    value: Mapping[str, Any],
) -> SemanticDecoyDecision:
    if not isinstance(value, Mapping) or set(value) != _DECISION_FIELDS:
        raise SemanticDecoyContractError(
            "semantic decoy decision has an invalid field set"
        )
    if value["schema"] != DECISION_SCHEMA:
        raise SemanticDecoyContractError(
            "semantic decoy decision has an unsupported schema"
        )
    task_id = _require_text(value["task_id"], "task_id")
    if value["phase"] != "pre_requirement_draft":
        raise SemanticDecoyContractError(
            "semantic decoy decision was not made before requirement drafting"
        )
    enabled = value["enabled"]
    if type(enabled) is not bool:
        raise SemanticDecoyContractError("semantic decoy enabled must be boolean")
    decision_source = _require_text(value["decision_source"], "decision_source")
    valid_sources = (
        {"developer_explicit_confirmation"}
        if enabled
        else {"developer_explicit_decline", "default_disabled"}
    )
    if decision_source not in valid_sources:
        raise SemanticDecoyContractError(
            "semantic decoy enablement requires explicit developer confirmation"
        )
    response_summary = _require_text(
        value["response_summary"], "response_summary"
    )
    asked_text, asked = _require_utc(value["asked_at_utc"], "asked_at_utc")
    answered_text, answered = _require_utc(
        value["answered_at_utc"], "answered_at_utc"
    )
    if answered < asked:
        raise SemanticDecoyContractError(
            "semantic decoy answer precedes the question"
        )
    return SemanticDecoyDecision(
        task_id=task_id,
        enabled=enabled,
        decision_source=decision_source,
        response_summary=response_summary,
        asked_at_utc=asked_text,
        answered_at_utc=answered_text,
    )


def _inspect_semantic_decoy_artifacts(
    manifest_bytes: bytes,
    *,
    decision_bytes: bytes,
    requirement_document_bytes: bytes,
    context_pack_bytes: bytes,
    verified_project_seal: str,
) -> SemanticDecoyEvaluation:
    """Inspect structure only; this function never grants an internal-test exemption."""

    for value, label in (
        (manifest_bytes, "semantic decoy manifest"),
        (decision_bytes, "semantic decoy decision"),
        (requirement_document_bytes, "requirement document"),
        (context_pack_bytes, "reasoning context pack"),
    ):
        if not isinstance(value, bytes):
            raise SemanticDecoyContractError(f"{label} must be bytes")
    manifest = _parse_json_object(manifest_bytes, "semantic decoy manifest")
    decision = parse_semantic_decoy_decision(
        _parse_json_object(decision_bytes, "semantic decoy decision")
    )
    requirement_binding = _parse_requirement_binding(
        requirement_document_bytes,
        decision=decision,
        decision_sha256=hashlib.sha256(decision_bytes).hexdigest(),
    )
    context_pack = _parse_json_object(
        context_pack_bytes,
        "reasoning context pack",
    )
    return _inspect_structure(
        manifest,
        decision=decision,
        requirement_binding=requirement_binding,
        decision_sha256=hashlib.sha256(decision_bytes).hexdigest(),
        requirement_document_sha256=hashlib.sha256(
            requirement_document_bytes
        ).hexdigest(),
        context_pack_sha256=hashlib.sha256(context_pack_bytes).hexdigest(),
        verified_project_seal=verified_project_seal,
        context_pack=context_pack,
    )


def evaluate_semantic_decoy_files(
    manifest_path: str | Path,
    *,
    requirement_document_path: str | Path,
    context_pack_path: str | Path,
    implementation_plan_path: str | Path,
    implementation_review_path: str | Path,
    approved_test_plan_path: str | Path,
    test_review_path: str | Path,
    project_root: str | Path,
) -> SemanticDecoyEvaluation:
    """Evaluate exact artifacts against the verified project Seal and two reviews."""

    root = Path(project_root).resolve()
    try:
        verified_seal = verify_expected_project_seal(root).expected_seal
    except ProjectSealStoreError as error:
        raise SemanticDecoyContractError(
            f"cannot verify current project Seal: {error}"
        ) from error

    manifest_file = Path(manifest_path)
    requirement_path = Path(requirement_document_path)
    context_file = Path(context_pack_path)
    implementation_plan_file = Path(implementation_plan_path)
    implementation_review_file = Path(implementation_review_path)
    test_plan_file = Path(approved_test_plan_path)
    test_review_file = Path(test_review_path)
    expected_names = (
        (manifest_file, "SEMANTIC_DECOY_MANIFEST.json", "manifest"),
        (requirement_path, "REQUIREMENT_DESIGN_FINAL.md", "requirement document"),
        (implementation_plan_file, "IMPLEMENTATION_PLAN_FINAL.md", "implementation plan"),
        (
            implementation_review_file,
            "SEMANTIC_DECOY_IMPLEMENTATION_REVIEW.json",
            "implementation review",
        ),
        (test_plan_file, "APPROVED_TEST_PLAN.md", "approved test plan"),
        (test_review_file, "SEMANTIC_DECOY_TEST_REVIEW.json", "test review"),
    )
    for path, expected_name, label in expected_names:
        if path.name != expected_name:
            raise SemanticDecoyContractError(
                f"{label} must use canonical filename {expected_name}"
            )
    decision_path = requirement_path.parent / _DECISION_FILENAME
    manifest_bytes = _read_required_bytes(manifest_file, "semantic decoy manifest")
    decision_bytes = _read_required_bytes(decision_path, "semantic decoy decision")
    requirement_bytes = _read_required_bytes(requirement_path, "requirement document")
    context_bytes = _read_required_bytes(context_file, "reasoning context pack")
    implementation_plan_bytes = _read_required_bytes(
        implementation_plan_file,
        "implementation plan",
    )
    implementation_review_bytes = _read_required_bytes(
        implementation_review_file,
        "implementation-plan semantic decoy review",
    )
    test_plan_bytes = _read_required_bytes(
        test_plan_file,
        "approved test plan",
    )
    test_review_bytes = _read_required_bytes(
        test_review_file,
        "test-plan semantic decoy review",
    )

    structural = _inspect_semantic_decoy_artifacts(
        manifest_bytes,
        decision_bytes=decision_bytes,
        requirement_document_bytes=requirement_bytes,
        context_pack_bytes=context_bytes,
        verified_project_seal=verified_seal,
    )
    manifest = _parse_json_object(manifest_bytes, "semantic decoy manifest")
    context_pack = _parse_json_object(context_bytes, "reasoning context pack")
    ledger_items = _index_context_items(context_pack)
    expected_entries, evidence_reasons = _expected_review_entries(
        manifest,
        ledger_items=ledger_items,
        project_root=root,
    )
    common = {
        "task_id": manifest["task_id"],
        "frozen_at_utc": manifest["frozen_at_utc"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        "requirement_document_sha256": hashlib.sha256(
            requirement_bytes
        ).hexdigest(),
        "context_pack_sha256": hashlib.sha256(context_bytes).hexdigest(),
        "project_seal": verified_seal,
        "entries": expected_entries,
    }
    implementation_receipt = _validate_review_receipt(
        implementation_review_bytes,
        stage="implementation_plan",
        reviewer_role="implementation_plan_reviewer",
        reviewed_artifact_name="IMPLEMENTATION_PLAN_FINAL.md",
        reviewed_artifact_bytes=implementation_plan_bytes,
        common=common,
    )
    test_receipt = _validate_review_receipt(
        test_review_bytes,
        stage="test_plan",
        reviewer_role="test_plan_reviewer",
        reviewed_artifact_name="APPROVED_TEST_PLAN.md",
        reviewed_artifact_bytes=test_plan_bytes,
        common=common,
    )

    review_reasons = [*evidence_reasons]
    review_reasons.extend(implementation_receipt.reasons)
    review_reasons.extend(test_receipt.reasons)
    if implementation_receipt.reviewer_identity == test_receipt.reviewer_identity:
        review_reasons.append("semantic decoy reviewers are not independent")
    review_reasons = list(dict.fromkeys(review_reasons))

    declared_decoys = {
        entry.decoy_id
        for entry in structural.entries
        if entry.declared_classification is DecoyClassification.DECOY_UNREACHABLE
    }
    structural_ids = set(structural.structurally_eligible_decoy_ids)
    can_authorize = (
        structural.all_declared_decoys_structurally_valid
        and declared_decoys == structural_ids
        and not review_reasons
    )
    entries: list[SemanticDecoyEntryEvaluation] = []
    for entry in structural.entries:
        if (
            can_authorize
            and entry.declared_classification
            is DecoyClassification.DECOY_UNREACHABLE
        ):
            entries.append(
                replace(
                    entry,
                    effective_classification=DecoyClassification.DECOY_UNREACHABLE,
                    internal_logic_test_required=False,
                    reasons=(),
                )
            )
        elif entry.declared_classification is DecoyClassification.DECOY_UNREACHABLE:
            entries.append(
                replace(
                    entry,
                    effective_classification=DecoyClassification.UNKNOWN_STALE,
                    internal_logic_test_required=True,
                    reasons=tuple(
                        dict.fromkeys((*entry.reasons, *review_reasons))
                    ),
                )
            )
        else:
            entries.append(entry)

    all_reasons = [
        reason
        for reason in structural.blocking_reasons
        if reason != _REVIEWS_REQUIRED_REASON
    ]
    all_reasons.extend(review_reasons)
    if declared_decoys and not can_authorize:
        all_reasons.append("independent semantic decoy authorization is incomplete")
    unique_reasons = tuple(dict.fromkeys(all_reasons))
    authorization_complete = (
        not unique_reasons and (not declared_decoys or can_authorize)
    )
    return SemanticDecoyEvaluation(
        policy_enabled=structural.policy_enabled,
        entries=tuple(entries),
        structurally_eligible_decoy_ids=structural.structurally_eligible_decoy_ids,
        all_declared_decoys_structurally_valid=(
            structural.all_declared_decoys_structurally_valid
        ),
        authorization_complete=authorization_complete,
        reviewer_identities=(
            implementation_receipt.reviewer_identity,
            test_receipt.reviewer_identity,
        ),
        blocking_reasons=unique_reasons,
    )


def _inspect_structure(
    manifest: Mapping[str, Any],
    *,
    decision: SemanticDecoyDecision,
    requirement_binding: Mapping[str, Any],
    decision_sha256: str,
    requirement_document_sha256: str,
    context_pack_sha256: str,
    verified_project_seal: str,
    context_pack: Mapping[str, Any],
) -> SemanticDecoyEvaluation:
    if not isinstance(manifest, Mapping) or set(manifest) != _MANIFEST_FIELDS:
        raise SemanticDecoyContractError(
            "semantic decoy manifest has an invalid field set"
        )
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise SemanticDecoyContractError(
            "semantic decoy manifest has an unsupported schema"
        )
    task_id = _require_text(manifest["task_id"], "manifest task_id")
    recorded_decision_sha = _require_sha256(
        manifest["decision_sha256"], "decision_sha256"
    )
    recorded_requirement_sha = _require_sha256(
        manifest["requirement_document_sha256"],
        "requirement_document_sha256",
    )
    recorded_context_sha = _require_sha256(
        manifest["context_pack_sha256"],
        "context_pack_sha256",
    )
    recorded_seal = _require_project_seal(manifest["project_seal"])
    actual_decision_sha = _require_sha256(
        decision_sha256,
        "actual decision_sha256",
    )
    actual_requirement_sha = _require_sha256(
        requirement_document_sha256,
        "actual requirement_document_sha256",
    )
    actual_context_sha = _require_sha256(
        context_pack_sha256,
        "actual context_pack_sha256",
    )
    actual_seal = _require_project_seal(verified_project_seal)
    _require_utc(manifest["frozen_at_utc"], "frozen_at_utc")
    raw_entries = manifest["entries"]
    if not isinstance(raw_entries, list):
        raise SemanticDecoyContractError("semantic decoy entries must be a list")

    global_reasons: list[str] = []
    if task_id != decision.task_id:
        global_reasons.append("manifest task does not match the decision task")
    if requirement_binding["task_id"] != task_id:
        global_reasons.append("requirement binding task does not match manifest")
    if recorded_decision_sha != actual_decision_sha:
        global_reasons.append("semantic decoy decision SHA-256 mismatch")
    if recorded_requirement_sha != actual_requirement_sha:
        global_reasons.append("requirement document SHA-256 mismatch")
    if recorded_context_sha != actual_context_sha:
        global_reasons.append("reasoning context pack SHA-256 mismatch")
    if recorded_seal != actual_seal:
        global_reasons.append("project Seal mismatch")
    if context_pack.get("task_id") != task_id:
        global_reasons.append("reasoning context pack task does not match manifest")
    context_metadata = context_pack.get("metadata")
    if (
        not isinstance(context_metadata, Mapping)
        or context_metadata.get("project_seal") != actual_seal
    ):
        global_reasons.append(
            "reasoning context pack is not bound to the current project Seal"
        )
    warnings = context_pack.get("warnings", [])
    if not isinstance(warnings, list):
        raise SemanticDecoyContractError(
            "reasoning context pack warnings must be a list"
        )
    if warnings:
        global_reasons.append("reasoning context pack contains warnings")

    ledger_items = _index_context_items(context_pack)
    active_refutes = _active_refute_item_ids(context_pack)
    entries: list[SemanticDecoyEntryEvaluation] = []
    seen_ids: set[str] = set()
    structural_blocking = list(global_reasons)
    for raw_entry in raw_entries:
        parsed = _parse_manifest_entry(raw_entry)
        decoy_id = parsed["decoy_id"]
        if decoy_id in seen_ids:
            raise SemanticDecoyContractError(
                f"duplicate semantic decoy id: {decoy_id}"
            )
        seen_ids.add(decoy_id)
        entry = _inspect_entry(
            parsed,
            policy_enabled=decision.enabled,
            global_reasons=global_reasons,
            ledger_items=ledger_items,
            active_refutes=active_refutes,
        )
        entries.append(entry)
        structural_blocking.extend(
            f"{decoy_id}: {reason}" for reason in entry.reasons
        )

    eligible = tuple(
        entry.decoy_id
        for entry in entries
        if entry.structural_classification
        is DecoyClassification.DECOY_UNREACHABLE
    )
    declared_decoys = tuple(
        entry.decoy_id
        for entry in entries
        if entry.declared_classification
        is DecoyClassification.DECOY_UNREACHABLE
    )
    unique_blocking = tuple(dict.fromkeys(structural_blocking))
    return SemanticDecoyEvaluation(
        policy_enabled=decision.enabled,
        entries=tuple(entries),
        structurally_eligible_decoy_ids=eligible,
        all_declared_decoys_structurally_valid=(
            set(eligible) == set(declared_decoys) and not unique_blocking
        ),
        authorization_complete=not declared_decoys and not unique_blocking,
        reviewer_identities=(),
        blocking_reasons=(
            unique_blocking
            if not declared_decoys
            else tuple(
                dict.fromkeys(
                    (*unique_blocking, _REVIEWS_REQUIRED_REASON)
                )
            )
        ),
    )


def _parse_requirement_binding(
    requirement_bytes: bytes,
    *,
    decision: SemanticDecoyDecision,
    decision_sha256: str,
) -> Mapping[str, Any]:
    try:
        text = requirement_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SemanticDecoyContractError(
            "requirement document is not valid UTF-8"
        ) from error
    lines = text.splitlines()
    heading_indexes = [
        index for index, line in enumerate(lines) if line == _REQUIREMENT_HEADING
    ]
    if len(heading_indexes) != 1:
        raise SemanticDecoyContractError(
            "requirement document must contain exactly one semantic decoy section"
        )
    start = heading_indexes[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    section = lines[start:end]
    fence_indexes = [
        index for index, line in enumerate(section) if line == _REQUIREMENT_FENCE
    ]
    if len(fence_indexes) != 1:
        raise SemanticDecoyContractError(
            "requirement semantic decoy section must contain one binding block"
        )
    fence_start = fence_indexes[0]
    closing_indexes = [
        index
        for index in range(fence_start + 1, len(section))
        if section[index] == "```"
    ]
    if len(closing_indexes) != 1:
        raise SemanticDecoyContractError(
            "requirement semantic decoy binding block is not unique or closed"
        )
    binding_bytes = "\n".join(
        section[fence_start + 1 : closing_indexes[0]]
    ).encode("utf-8")
    binding = _parse_json_object(binding_bytes, "requirement semantic decoy binding")
    if set(binding) != _REQUIREMENT_BINDING_FIELDS:
        raise SemanticDecoyContractError(
            "requirement semantic decoy binding has an invalid field set"
        )
    if binding["schema"] != REQUIREMENT_BINDING_SCHEMA:
        raise SemanticDecoyContractError(
            "requirement semantic decoy binding has an unsupported schema"
        )
    if binding["task_id"] != decision.task_id:
        raise SemanticDecoyContractError(
            "requirement semantic decoy task conflicts with decision"
        )
    if type(binding["enabled"]) is not bool or binding["enabled"] != decision.enabled:
        raise SemanticDecoyContractError(
            "requirement semantic decoy enablement conflicts with decision"
        )
    if binding["decision_source"] != decision.decision_source:
        raise SemanticDecoyContractError(
            "requirement semantic decoy source conflicts with decision"
        )
    if binding["decision_path"] != _DECISION_FILENAME:
        raise SemanticDecoyContractError(
            "requirement semantic decoy decision path is not canonical"
        )
    if _require_sha256(
        binding["decision_sha256"],
        "requirement decision_sha256",
    ) != _require_sha256(decision_sha256, "actual decision_sha256"):
        raise SemanticDecoyContractError(
            "requirement semantic decoy decision SHA-256 mismatch"
        )
    return binding


def _parse_manifest_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ENTRY_FIELDS:
        raise SemanticDecoyContractError(
            "semantic decoy entry has an invalid field set"
        )
    try:
        classification = DecoyClassification(value["classification"])
    except (TypeError, ValueError) as error:
        raise SemanticDecoyContractError(
            "semantic decoy entry has an invalid classification"
        ) from error
    parsed = {
        "decoy_id": _require_text(value["decoy_id"], "decoy_id"),
        "classification": classification,
        "code_anchors": _require_text_list(value["code_anchors"], "code_anchors"),
        "predicate": _require_text(value["predicate"], "predicate"),
        "true_semantics": _require_text(value["true_semantics"], "true_semantics"),
        "surface_semantics": _require_text_list(
            value["surface_semantics"],
            "surface_semantics",
            allow_empty=True,
        ),
        "constraint_item_ids": _require_text_list(
            value["constraint_item_ids"],
            "constraint_item_ids",
            allow_empty=True,
        ),
        "invalidation_conditions": _require_text_list(
            value["invalidation_conditions"],
            "invalidation_conditions",
            allow_empty=True,
        ),
    }
    if classification is DecoyClassification.DECOY_UNREACHABLE:
        for field in (
            "surface_semantics",
            "constraint_item_ids",
            "invalidation_conditions",
        ):
            if not parsed[field]:
                raise SemanticDecoyContractError(
                    f"DECOY_UNREACHABLE requires {field}"
                )
    return parsed


def _inspect_entry(
    entry: Mapping[str, Any],
    *,
    policy_enabled: bool,
    global_reasons: Sequence[str],
    ledger_items: Mapping[str, Sequence[Mapping[str, Any]]],
    active_refutes: set[str],
) -> SemanticDecoyEntryEvaluation:
    declared = entry["classification"]
    assert isinstance(declared, DecoyClassification)
    if declared is DecoyClassification.REAL:
        return SemanticDecoyEntryEvaluation(
            decoy_id=entry["decoy_id"],
            declared_classification=declared,
            structural_classification=DecoyClassification.REAL,
            effective_classification=DecoyClassification.REAL,
            internal_logic_test_required=True,
            perimeter_tests_required=False,
            reasons=(),
        )

    reasons = list(global_reasons)
    if declared is DecoyClassification.UNKNOWN_STALE:
        reasons.append("entry is explicitly UNKNOWN-STALE")
    if not policy_enabled:
        reasons.append("semantic decoy policy is disabled")
    if declared is DecoyClassification.DECOY_UNREACHABLE:
        for item_id in entry["constraint_item_ids"]:
            candidates = ledger_items.get(item_id, ())
            if len(candidates) != 1:
                reasons.append(f"constraint item {item_id} is missing or ambiguous")
                continue
            item = candidates[0]
            if item.get("status") != "active":
                reasons.append(f"constraint item {item_id} is not active")
            if item.get("type") not in {"fact", "rule"}:
                reasons.append(f"constraint item {item_id} is not a fact or rule")
            evidence_path = item.get("evidence_path")
            if not isinstance(evidence_path, str) or not evidence_path.strip():
                reasons.append(f"constraint item {item_id} has no evidence path")
            version = item.get("version")
            if type(version) is not int or version < 1:
                reasons.append(f"constraint item {item_id} has no valid version")
            if item_id in active_refutes:
                reasons.append(f"constraint item {item_id} has an active refute")

    structural = (
        DecoyClassification.DECOY_UNREACHABLE
        if declared is DecoyClassification.DECOY_UNREACHABLE and not reasons
        else DecoyClassification.UNKNOWN_STALE
    )
    return SemanticDecoyEntryEvaluation(
        decoy_id=entry["decoy_id"],
        declared_classification=declared,
        structural_classification=structural,
        effective_classification=DecoyClassification.UNKNOWN_STALE,
        internal_logic_test_required=True,
        perimeter_tests_required=True,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _validate_review_receipt(
    receipt_bytes: bytes,
    *,
    stage: str,
    reviewer_role: str,
    reviewed_artifact_name: str,
    reviewed_artifact_bytes: bytes,
    common: Mapping[str, Any],
) -> _ReviewReceipt:
    value = _parse_json_object(receipt_bytes, f"{stage} semantic decoy review")
    if set(value) != _REVIEW_RECEIPT_FIELDS:
        raise SemanticDecoyContractError(
            f"{stage} semantic decoy review has an invalid field set"
        )
    if value["schema"] != REVIEW_RECEIPT_SCHEMA:
        raise SemanticDecoyContractError(
            f"{stage} semantic decoy review has an unsupported schema"
        )
    identity = _require_text(value["reviewer_identity"], "reviewer_identity")
    reasons: list[str] = []
    expected_scalars = {
        "stage": stage,
        "reviewer_role": reviewer_role,
        "reviewed_artifact_name": reviewed_artifact_name,
        "reviewed_artifact_sha256": hashlib.sha256(
            reviewed_artifact_bytes
        ).hexdigest(),
        "task_id": common["task_id"],
        "frozen_at_utc": common["frozen_at_utc"],
        "manifest_sha256": common["manifest_sha256"],
        "decision_sha256": common["decision_sha256"],
        "requirement_document_sha256": common["requirement_document_sha256"],
        "context_pack_sha256": common["context_pack_sha256"],
        "project_seal": common["project_seal"],
        "verdict": "PASS",
    }
    for field, expected in expected_scalars.items():
        if value[field] != expected:
            reasons.append(f"{stage} review {field} mismatch")
    frozen_text, frozen = _require_utc(value["frozen_at_utc"], "frozen_at_utc")
    reviewed_text, reviewed = _require_utc(
        value["reviewed_at_utc"],
        "reviewed_at_utc",
    )
    del frozen_text, reviewed_text
    if reviewed < frozen:
        reasons.append(f"{stage} review predates the frozen evidence")
    raw_entries = value["entries"]
    if not isinstance(raw_entries, list):
        raise SemanticDecoyContractError(f"{stage} review entries must be a list")
    parsed_entries = [_parse_review_entry(item, stage=stage) for item in raw_entries]
    if parsed_entries != common["entries"]:
        reasons.append(f"{stage} review decoy evidence mismatch")
    return _ReviewReceipt(
        stage=stage,
        reviewer_identity=identity,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _parse_review_entry(value: Any, *, stage: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REVIEW_ENTRY_FIELDS:
        raise SemanticDecoyContractError(
            f"{stage} review entry has an invalid field set"
        )
    constraints = value["constraints"]
    if not isinstance(constraints, list):
        raise SemanticDecoyContractError(
            f"{stage} review constraints must be a list"
        )
    parsed_constraints: list[dict[str, Any]] = []
    for constraint in constraints:
        if (
            not isinstance(constraint, Mapping)
            or set(constraint) != _CONSTRAINT_BINDING_FIELDS
        ):
            raise SemanticDecoyContractError(
                f"{stage} review constraint has an invalid field set"
            )
        version = constraint["version"]
        if type(version) is not int or version < 1:
            raise SemanticDecoyContractError(
                f"{stage} review constraint version must be a positive integer"
            )
        parsed_constraints.append(
            {
                "item_id": _require_text(constraint["item_id"], "item_id"),
                "version": version,
                "evidence_path": _require_relative_path(
                    constraint["evidence_path"],
                    "evidence_path",
                ),
                "evidence_sha256": _require_sha256(
                    constraint["evidence_sha256"],
                    "evidence_sha256",
                ),
            }
        )
    return {
        "decoy_id": _require_text(value["decoy_id"], "decoy_id"),
        "predicate": _require_text(value["predicate"], "predicate"),
        "constraints": parsed_constraints,
        "verdict": value["verdict"],
    }


def _expected_review_entries(
    manifest: Mapping[str, Any],
    *,
    ledger_items: Mapping[str, Sequence[Mapping[str, Any]]],
    project_root: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    expected: list[dict[str, Any]] = []
    reasons: list[str] = []
    raw_entries = manifest.get("entries", [])
    if not isinstance(raw_entries, list):
        raise SemanticDecoyContractError("semantic decoy entries must be a list")
    for raw_entry in raw_entries:
        entry = _parse_manifest_entry(raw_entry)
        if entry["classification"] is not DecoyClassification.DECOY_UNREACHABLE:
            continue
        constraints: list[dict[str, Any]] = []
        for item_id in entry["constraint_item_ids"]:
            candidates = ledger_items.get(item_id, ())
            if len(candidates) != 1:
                reasons.append(f"constraint item {item_id} is missing or ambiguous")
                continue
            item = candidates[0]
            version = item.get("version")
            evidence_path_value = item.get("evidence_path")
            if type(version) is not int or version < 1:
                reasons.append(f"constraint item {item_id} has no valid version")
                continue
            try:
                evidence_path = _require_relative_path(
                    evidence_path_value,
                    "evidence_path",
                )
                evidence_file = _resolve_project_relative(project_root, evidence_path)
                evidence_sha = _sha256_file(evidence_file)
            except SemanticDecoyContractError as error:
                reasons.append(f"constraint item {item_id}: {error}")
                continue
            constraints.append(
                {
                    "item_id": item_id,
                    "version": version,
                    "evidence_path": evidence_path,
                    "evidence_sha256": evidence_sha,
                }
            )
        expected.append(
            {
                "decoy_id": entry["decoy_id"],
                "predicate": entry["predicate"],
                "constraints": constraints,
                "verdict": "PASS",
            }
        )
    return expected, reasons


def _index_context_items(
    context_pack: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    if not isinstance(context_pack, Mapping):
        raise SemanticDecoyContractError("reasoning context pack must be an object")
    result: dict[str, list[Mapping[str, Any]]] = {}
    for section in ("items", "cause_items"):
        rows = context_pack.get(section, [])
        if not isinstance(rows, list):
            raise SemanticDecoyContractError(
                f"reasoning context pack {section} must be a list"
            )
        for row in rows:
            if not isinstance(row, Mapping):
                raise SemanticDecoyContractError(
                    f"reasoning context pack {section} contains a non-object"
                )
            item_id = row.get("id")
            if isinstance(item_id, str) and item_id:
                candidates = result.setdefault(item_id, [])
                if not any(dict(candidate) == dict(row) for candidate in candidates):
                    candidates.append(row)
    return result


def _active_refute_item_ids(context_pack: Mapping[str, Any]) -> set[str]:
    rows = context_pack.get("edges", [])
    if not isinstance(rows, list):
        raise SemanticDecoyContractError(
            "reasoning context pack edges must be a list"
        )
    result: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise SemanticDecoyContractError(
                "reasoning context pack edges contains a non-object"
            )
        if row.get("relation") == "refutes" and row.get("status") == "active":
            for field in ("from_id", "to_id"):
                item_id = row.get(field)
                if isinstance(item_id, str) and item_id:
                    result.add(item_id)
    return result


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticDecoyContractError(f"{field} must be non-empty text")
    return value


def _require_text_list(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise SemanticDecoyContractError(
            f"{field} must be a list of non-empty strings"
        )
    if len(set(value)) != len(value):
        raise SemanticDecoyContractError(f"{field} must not contain duplicates")
    return tuple(value)


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise SemanticDecoyContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _require_project_seal(value: Any) -> str:
    if not isinstance(value, str) or _PROJECT_SEAL.fullmatch(value) is None:
        raise SemanticDecoyContractError(
            "project_seal must use canonical ASC1 form"
        )
    return value


def _require_utc(value: Any, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SemanticDecoyContractError(f"{field} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise SemanticDecoyContractError(
            f"{field} must be a valid UTC timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise SemanticDecoyContractError(f"{field} must be a UTC timestamp")
    return value, parsed


def _require_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticDecoyContractError(f"{field} must be a relative path")
    normalized = value.replace("\\", "/")
    if normalized.startswith(("/", "~")) or (
        len(normalized) >= 2 and normalized[1] == ":"
    ):
        raise SemanticDecoyContractError(f"{field} must be a relative path")
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise SemanticDecoyContractError(f"{field} must be normalized")
    return str(path)


def _resolve_project_relative(project_root: Path, relative_path: str) -> Path:
    path = project_root.joinpath(*PurePosixPath(relative_path).parts).resolve()
    if not path.is_relative_to(project_root):
        raise SemanticDecoyContractError("evidence path escapes project root")
    if not path.is_file():
        raise SemanticDecoyContractError(f"evidence file is missing: {relative_path}")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SemanticDecoyContractError(f"cannot read evidence file: {path}") from error
    return digest.hexdigest()


def _read_required_bytes(path: str | Path, label: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise SemanticDecoyContractError(f"cannot read {label}: {error}") from error


def _parse_json_object(data: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SemanticDecoyContractError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise SemanticDecoyContractError(f"{label} must contain a JSON object")
    return value


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SemanticDecoyContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
