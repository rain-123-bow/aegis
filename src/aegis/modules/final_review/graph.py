"""LangGraph builder and deterministic Final Review Subgraph v2 runtime."""

import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aegis.modules.execution.models import ExecutionOutputPackage
from aegis.modules.final_review.artifacts import FinalReviewArtifactWriter, sha256_file, sha256_path
from aegis.modules.final_review.models import (
    ArtifactRef,
    CausalRefAssessment,
    CodeSurfaceConsistency,
    EvidenceReviewMatrix,
    FinalReviewBoundaryFlags,
    FinalReviewContextPackage,
    FinalReviewDecisionTrace,
    FinalReviewInputPackage,
    FinalReviewInputValidation,
    FinalReviewOutputPackage,
    FinalReviewProhibitedActionAttempt,
    FinalReviewProjectBinding,
    FinalReviewRunManifest,
    FinalReviewStateBoundaryResult,
    REQUIRED_THREAT_CHECKLIST_IDS,
    RequirementAlignmentItem,
    ReviewFinding,
    ThreatChecklistItem,
    ThreatChecklistMatrix,
)
from aegis.modules.final_review.path_io import (
    iter_files,
    path_exists,
    read_text,
    require_under_root,
)
from aegis.modules.test.models import ArtifactSchemaValidationResult, StateBoundaryResult, TestOutputPackage


class FinalReviewGraphState(TypedDict, total=False):
    input_package: dict[str, Any]
    binding: dict[str, Any]
    input_validation: dict[str, Any]
    input_validation_ref: dict[str, Any]
    context_package: dict[str, Any]
    context_resolution_ref: dict[str, Any]
    causal_assessments: list[dict[str, Any]]
    code_surface_consistency: dict[str, Any]
    code_surface_consistency_ref: dict[str, Any]
    code_surface_manifest_ref: dict[str, Any]
    requirement_alignment_ref: dict[str, Any]
    threat_findings: list[dict[str, Any]]
    threat_findings_ref: dict[str, Any]
    threat_checklist_matrix: dict[str, Any]
    threat_checklist_matrix_ref: dict[str, Any]
    code_quality_findings_ref: dict[str, Any]
    requirement_alignment: list[dict[str, Any]]
    evidence_review: dict[str, Any]
    evidence_review_ref: dict[str, Any]
    causal_consistency_ref: dict[str, Any]
    decision_trace: dict[str, Any]
    decision_trace_ref: dict[str, Any]
    final_review_report_ref: dict[str, Any]
    decision_ref: dict[str, Any]
    next_route_ref: dict[str, Any]
    run_manifest_ref: dict[str, Any]
    evidence_index_ref: dict[str, Any]
    artifact_hashes_ref: dict[str, Any]
    artifact_schema_validation_ref: dict[str, Any]
    state_boundary_results_ref: dict[str, Any]
    tool_audit_ref: dict[str, Any]
    output_package: dict[str, Any]
    scope_limits: list[str]


def build_final_review_subgraph():
    """Build the standalone deterministic Final Review Subgraph."""

    builder = StateGraph(FinalReviewGraphState)
    builder.add_node("input_validation", _input_validation_node)
    builder.add_node("context_resolution", _context_resolution_node)
    builder.add_node("code_surface_index", _code_surface_index_node)
    builder.add_node("requirement_alignment_review", _requirement_alignment_node)
    builder.add_node("threat_review", _threat_review_node)
    builder.add_node("code_quality_review", _code_quality_review_node)
    builder.add_node("evidence_review", _evidence_review_node)
    builder.add_node("causal_consistency_review", _causal_consistency_node)
    builder.add_node("decision_synthesis", _decision_synthesis_node)
    builder.add_node("closeout_package", _closeout_node)
    builder.add_edge(START, "input_validation")
    builder.add_conditional_edges(
        "input_validation",
        _route_after_input_validation,
        {"continue": "context_resolution", "blocked": "decision_synthesis"},
    )
    builder.add_edge("context_resolution", "code_surface_index")
    builder.add_edge("code_surface_index", "requirement_alignment_review")
    builder.add_edge("requirement_alignment_review", "threat_review")
    builder.add_edge("threat_review", "code_quality_review")
    builder.add_edge("code_quality_review", "evidence_review")
    builder.add_edge("evidence_review", "causal_consistency_review")
    builder.add_edge("causal_consistency_review", "decision_synthesis")
    builder.add_edge("decision_synthesis", "closeout_package")
    builder.add_edge("closeout_package", END)
    return builder.compile()


def _route_after_input_validation(state: FinalReviewGraphState) -> str:
    validation = FinalReviewInputValidation.model_validate(state["input_validation"])
    return "continue" if validation.status == "accepted" else "blocked"


def run_deterministic_final_review_subgraph(
    package: FinalReviewInputPackage,
) -> FinalReviewOutputPackage:
    """Run Final Review Subgraph and return its terminal output package."""

    result = build_final_review_subgraph().invoke({"input_package": package.model_dump(mode="json")})
    return FinalReviewOutputPackage.model_validate(result["output_package"])


def _input_validation_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package = FinalReviewInputPackage.model_validate(state["input_package"])
    binding = _bind_project(package)
    writer = FinalReviewArtifactWriter(binding)
    _write_artifact_readmes(writer)
    input_fingerprint_ref = _write_input_fingerprint(writer, package)
    validation = _validate_inputs(package)
    input_ref = writer.write_json(
        writer.artifact_dir("input") / "input_validation.json",
        validation,
        "input_validation",
    )
    return {
        "binding": binding.model_dump(mode="json"),
        "input_validation": validation.model_dump(mode="json"),
        "input_validation_ref": input_ref.model_dump(mode="json"),
        "input_fingerprint_ref": input_fingerprint_ref.model_dump(mode="json"),
    }


def _context_resolution_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package, _binding, writer = _runtime_parts(state)
    knowledge_payload = _read_json(package.knowledge_context_path) if package.knowledge_context_path else {}
    causal_payload = _read_json(package.causal_context_path) if package.causal_context_path else {}
    assessments = [_causal_assessment(item) for item in causal_payload.get("causal_refs", [])]
    knowledge_availability = knowledge_payload.get(
        "store_availability",
        "not_requested" if package.knowledge_context_path is None else "available",
    )
    causal_availability = causal_payload.get(
        "store_availability",
        "not_requested" if package.causal_context_path is None else "available",
    )
    missing_items = [
        *_list_payload(knowledge_payload.get("missing_context_items")),
        *_list_payload(causal_payload.get("missing_context_items")),
    ]
    degraded = bool(knowledge_payload.get("degraded_recall")) or bool(causal_payload.get("degraded_recall"))
    context = FinalReviewContextPackage(
        knowledge_refs=[str(item) for item in _list_payload(knowledge_payload.get("knowledge_refs"))],
        causal_active_refs=[
            item.causal_ref for item in assessments if item.status in {"active", "admitted"}
        ],
        causal_candidate_refs=[item.causal_ref for item in assessments if item.status == "candidate"],
        rejected_refs=[],
        missing_context_items=missing_items,
        degraded_recall=degraded,
        store_availability={"knowledge": knowledge_availability, "causal": causal_availability},
        requirement_context_sufficient=bool(
            knowledge_payload.get("requirement_context_sufficient", True)
        ),
        threat_context_sufficient=bool(
            knowledge_payload.get("threat_context_sufficient", True)
        ),
        causal_context_sufficient=bool(
            causal_payload.get("causal_context_sufficient", True)
        ),
    )
    context_dir = writer.artifact_dir("context")
    context_ref = writer.write_json(context_dir / "context_resolution_report.json", context, "context")
    writer.write_json(context_dir / "knowledge_context.json", knowledge_payload, "knowledge_context")
    writer.write_json(context_dir / "causal_context.json", causal_payload, "causal_context")
    writer.write_json(context_dir / "causal_ref_assessments.json", assessments, "causal_assessments")
    writer.write_text(
        context_dir / "context_resolution_report.md",
        "# Context Resolution\n\nKnowledge and causal context were resolved as bounded refs.\n",
        "context_report",
    )
    return {
        "context_package": context.model_dump(mode="json"),
        "context_resolution_ref": context_ref.model_dump(mode="json"),
        "causal_assessments": [item.model_dump(mode="json") for item in assessments],
    }


def _code_surface_index_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package, binding, writer = _runtime_parts(state)
    execution = _read_execution_output(package)
    current_manifest = _current_code_manifest(binding.code_root)
    current_manifest_ref = writer.write_json(
        writer.artifact_dir("code_surface") / "code_surface_manifest.json",
        current_manifest,
        "code_surface_manifest",
    )
    if execution.implementation_changeset_ref is None:
        consistency = CodeSurfaceConsistency(
            execution_changed_files_ref=None,
            test_code_diff_ref=None,
            final_review_current_manifest_ref=current_manifest_ref,
            changed_file_hashes_match_execution=False,
            changed_file_hashes_match_test=False,
            unexpected_current_changes=[],
            missing_expected_changes=[],
            symlink_or_path_escape_detected=False,
            comparison_mode="not_applicable",
            status="not_applicable",
        )
        consistency_ref = writer.write_json(
            writer.artifact_dir("code_surface") / "code_surface_consistency.json",
            consistency,
            "code_surface_consistency",
        )
        writer.write_json(writer.artifact_dir("code_surface") / "changed_files.json", [], "changed_files")
        writer.write_json(writer.artifact_dir("code_surface") / "review_targets.json", [], "review_targets")
        writer.write_text(
            writer.artifact_dir("code_surface") / "code_surface_report.md",
            "# Code Surface\n\nstatus: `not_applicable`\n",
            "code_surface_report",
        )
        return {
            "code_surface_consistency": consistency.model_dump(mode="json"),
            "code_surface_consistency_ref": consistency_ref.model_dump(mode="json"),
            "code_surface_manifest_ref": current_manifest_ref.model_dump(mode="json"),
        }
    execution_changeset_ref = _convert_ref(execution.implementation_changeset_ref)
    changeset = _read_json(execution.implementation_changeset_ref.path)
    mismatches: list[str] = []
    missing: list[str] = []
    test_mismatches: list[str] = []
    unexpected: list[str] = []
    escape = False
    current_hashes = {str(item["path"]): str(item["sha256"]) for item in current_manifest["files"]}
    for item in changeset.get("changed_files", []):
        relative = item.get("path", "")
        try:
            current_path = require_under_root(binding.code_root / relative, binding.code_root, label="changed file")
        except ValueError:
            escape = True
            continue
        expected_hash = item.get("sha256_after")
        if not path_exists(current_path):
            missing.append(relative)
            continue
        actual_hash = sha256_file(current_path)
        if expected_hash and actual_hash != expected_hash:
            mismatches.append(relative)
    comparison_mode, expected_hashes = _expected_code_manifest_hashes(changeset)
    if expected_hashes:
        if comparison_mode == "full_manifest":
            unexpected = sorted(set(current_hashes) - set(expected_hashes))
        for relative, expected_hash in sorted(expected_hashes.items()):
            actual_hash = current_hashes.get(relative)
            if actual_hash is None:
                if relative not in missing:
                    missing.append(relative)
                continue
            if expected_hash and actual_hash != expected_hash and relative not in mismatches:
                mismatches.append(relative)
    test_changeset = _test_changeset_payload(package)
    for item in test_changeset.get("changed_files", []):
        relative = item.get("path", "")
        try:
            current_path = require_under_root(binding.code_root / relative, binding.code_root, label="test changed file")
        except ValueError:
            escape = True
            continue
        if not path_exists(current_path):
            test_mismatches.append(relative)
            continue
        expected_hash = item.get("sha256_after")
        if expected_hash and sha256_file(current_path) != expected_hash:
            test_mismatches.append(relative)
    if test_changeset.get("status") == "blocked":
        test_mismatches.append("test_run_changeset_blocked")
    consistency = CodeSurfaceConsistency(
        execution_changed_files_ref=execution_changeset_ref,
        test_code_diff_ref=_test_changeset_ref(package),
        final_review_current_manifest_ref=current_manifest_ref,
        changed_file_hashes_match_execution=not mismatches and not missing,
        changed_file_hashes_match_test=not test_mismatches,
        unexpected_current_changes=unexpected,
        missing_expected_changes=missing,
        symlink_or_path_escape_detected=escape,
        comparison_mode=comparison_mode,
        status="mismatch" if mismatches or missing or unexpected or test_mismatches or escape else "consistent",
    )
    consistency_ref = writer.write_json(
        writer.artifact_dir("code_surface") / "code_surface_consistency.json",
        consistency,
        "code_surface_consistency",
    )
    writer.write_json(
        writer.artifact_dir("code_surface") / "changed_files.json",
        changeset.get("changed_files", []),
        "changed_files",
    )
    writer.write_json(
        writer.artifact_dir("code_surface") / "review_targets.json",
        [item.get("path") for item in changeset.get("changed_files", [])],
        "review_targets",
    )
    writer.write_text(
        writer.artifact_dir("code_surface") / "code_surface_report.md",
        f"# Code Surface\n\nstatus: `{consistency.status}`\n",
        "code_surface_report",
    )
    return {
        "code_surface_consistency": consistency.model_dump(mode="json"),
        "code_surface_consistency_ref": consistency_ref.model_dump(mode="json"),
        "code_surface_manifest_ref": current_manifest_ref.model_dump(mode="json"),
    }


def _requirement_alignment_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package, _binding, writer = _runtime_parts(state)
    requirements_payload = _read_json(package.requirement_package_dir / "requirements.json")
    mapping_payload = _execution_requirement_mapping_payload(package)
    mapping_by_id = {
        str(item.get("requirement_id")): item
        for item in _list_payload(mapping_payload.get("requirements"))
        if item.get("requirement_id")
    }
    items: list[RequirementAlignmentItem] = []
    for requirement in _list_payload(requirements_payload.get("requirements")):
        requirement_id = str(requirement.get("requirement_id", "")).strip()
        if not requirement_id:
            continue
        mapping = mapping_by_id.get(requirement_id)
        status = "not_testable_from_available_evidence"
        evidence_refs: list[str] = []
        if mapping:
            status = str(mapping.get("status", status))
            evidence_refs = [str(item) for item in _list_payload(mapping.get("evidence_refs"))]
        items.append(
            RequirementAlignmentItem(
                requirement_id=requirement_id,
                status=status,  # type: ignore[arg-type]
                evidence_refs=evidence_refs,
            )
        )
    if not items:
        items = [
            RequirementAlignmentItem(
                requirement_id="UNKNOWN",
                status="not_testable_from_available_evidence",
                evidence_refs=[],
            )
        ]
    ref = writer.write_json(
        writer.artifact_dir("requirement_alignment") / "requirement_alignment_matrix.json",
        items,
        "requirement_alignment",
    )
    writer.write_text(
        writer.artifact_dir("requirement_alignment") / "requirement_alignment_report.md",
        "# Requirement Alignment\n\nDeterministic requirement mapping review completed.\n",
        "requirement_alignment_report",
    )
    return {
        "requirement_alignment": [item.model_dump(mode="json") for item in items],
        "requirement_alignment_ref": ref.model_dump(mode="json"),
    }


def _threat_review_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package, binding, writer = _runtime_parts(state)
    execution = _read_execution_output(package)
    changeset = (
        _read_json(execution.implementation_changeset_ref.path)
        if execution.implementation_changeset_ref is not None
        else {}
    )
    findings: list[ReviewFinding] = []
    reviewed_paths: list[str] = []
    threat_hits: dict[str, bool] = {checklist_id: False for checklist_id in REQUIRED_THREAT_CHECKLIST_IDS}
    for item in changeset.get("changed_files", []):
        relative = item.get("path", "")
        path = require_under_root(binding.code_root / relative, binding.code_root, label="review target")
        if not path_exists(path):
            continue
        reviewed_paths.append(str(path))
        content = read_text(path)
        file_hits = _detect_threat_surfaces(content)
        for checklist_id, hit in file_hits.items():
            threat_hits[checklist_id] = threat_hits[checklist_id] or hit
        for checklist_id, hit in file_hits.items():
            if hit:
                findings.append(_threat_finding(checklist_id, relative))
    checklist_items = _threat_checklist_items(threat_hits, reviewed_paths)
    matrix = ThreatChecklistMatrix(
        items=checklist_items,
        all_items_answered=True,
        unknown_security_relevant_items=[],
    )
    threat_dir = writer.artifact_dir("threat_review")
    matrix_ref = writer.write_json(
        threat_dir / "threat_checklist_matrix.json",
        matrix,
        "threat_checklist_matrix",
    )
    findings_ref = writer.write_json(
        threat_dir / "threat_findings.json",
        findings,
        "threat_findings",
    )
    writer.write_text(
        threat_dir / "threat_review_report.md",
        f"# Threat Review\n\ncritical_findings: `{len(findings)}`\n",
        "threat_review_report",
    )
    return {
        "threat_findings": [item.model_dump(mode="json") for item in findings],
        "threat_findings_ref": findings_ref.model_dump(mode="json"),
        "threat_checklist_matrix": matrix.model_dump(mode="json"),
        "threat_checklist_matrix_ref": matrix_ref.model_dump(mode="json"),
    }


def _code_quality_review_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    _package, _binding, writer = _runtime_parts(state)
    ref = writer.write_json(
        writer.artifact_dir("code_quality") / "code_quality_findings.json",
        [],
        "code_quality_findings",
    )
    writer.write_text(
        writer.artifact_dir("code_quality") / "code_quality_report.md",
        "# Code Quality\n\nNo deterministic blocker found.\n",
        "code_quality_report",
    )
    return {"code_quality_findings_ref": ref.model_dump(mode="json")}


def _evidence_review_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package, _binding, writer = _runtime_parts(state)
    test_output = _read_test_output(package)
    schema = ArtifactSchemaValidationResult.model_validate_json(
        read_text(test_output.artifact_schema_check_ref.path)
    )
    state_boundary = StateBoundaryResult.model_validate_json(
        read_text(test_output.state_boundary_results_ref.path)
    )
    evidence_index = _read_json(test_output.evidence_index_ref.path)
    matrix_status = evidence_index.get("evidence_matrix", {}).get("status", "complete")
    test_changeset = _test_changeset_payload(package)
    execution_records = _test_execution_records_payload(evidence_index)
    skipped_without_valid_reason = any(
        row.get("status") == "skipped" and not row.get("skip_reason") for row in execution_records
    )
    raw_overrode_structured = bool(evidence_index.get("raw_report_overrode_structured_evidence"))
    status = "accepted"
    blocker = None
    if test_output.status != "passed":
        status = "gap"
        blocker = "test_not_passed"
    elif schema.status != "passed":
        status = "gap"
        blocker = "test_artifact_schema_failed"
    elif state_boundary.status != "passed":
        status = "gap"
        blocker = "test_state_boundary_failed"
    elif matrix_status != "complete":
        status = "gap"
        blocker = "test_not_passed"
    elif test_changeset.get("status") == "blocked":
        status = "gap"
        blocker = "code_surface_mismatch"
    elif skipped_without_valid_reason or raw_overrode_structured:
        status = "gap"
        blocker = "test_not_passed"
    review = EvidenceReviewMatrix(
        test_output_status=test_output.status,
        artifact_schema_status=schema.status,
        state_boundary_status=state_boundary.status,
        evidence_matrix_status=matrix_status,
        raw_report_overrode_structured_evidence=raw_overrode_structured,
        status=status,  # type: ignore[arg-type]
        blocker=blocker,  # type: ignore[arg-type]
    )
    ref = writer.write_json(
        writer.artifact_dir("evidence_review") / "evidence_review_matrix.json",
        review,
        "evidence_review_matrix",
    )
    writer.write_text(
        writer.artifact_dir("evidence_review") / "evidence_review_report.md",
        f"# Evidence Review\n\nstatus: `{review.status}`\n",
        "evidence_review_report",
    )
    return {
        "evidence_review": review.model_dump(mode="json"),
        "evidence_review_ref": ref.model_dump(mode="json"),
    }


def _causal_consistency_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    _package, _binding, writer = _runtime_parts(state)
    assessments = [CausalRefAssessment.model_validate(item) for item in state["causal_assessments"]]
    ref = writer.write_json(
        writer.artifact_dir("causal_consistency") / "causal_ref_assessments.json",
        assessments,
        "causal_ref_assessments",
    )
    writer.write_json(
        writer.artifact_dir("causal_consistency") / "causal_consistency_matrix.json",
        {"active_conflict": _has_active_causal_conflict(assessments)},
        "causal_consistency_matrix",
    )
    writer.write_text(
        writer.artifact_dir("causal_consistency") / "causal_consistency_report.md",
        "# Causal Consistency\n\nCandidates are advisory only; active/admitted conflicts block.\n",
        "causal_consistency_report",
    )
    return {"causal_consistency_ref": ref.model_dump(mode="json")}


def _decision_synthesis_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    validation = FinalReviewInputValidation.model_validate(state["input_validation"])
    considered = [
        "input invalid / boundary violation",
        "Test output failed or inconsistent",
        "critical threat",
        "error threat",
        "hard requirement mismatch",
        "code surface mismatch",
        "active/admitted causal conflict",
        "material context insufficiency",
        "warning-only threat accepted with scope limits",
        "all hard gates pass",
    ]
    scope_limits: list[str] = []
    if validation.status == "blocked":
        trace = FinalReviewDecisionTrace(
            matched_rule="input invalid / boundary violation",
            considered_rules=considered,
            decision="governance_blocker",
            status="blocked",
            next_stage="master",
            blocker=validation.blocker,
        )
    else:
        code_surface = CodeSurfaceConsistency.model_validate(state["code_surface_consistency"])
        evidence = EvidenceReviewMatrix.model_validate(state["evidence_review"])
        findings = [ReviewFinding.model_validate(item) for item in state["threat_findings"]]
        causal = [CausalRefAssessment.model_validate(item) for item in state["causal_assessments"]]
        context = FinalReviewContextPackage.model_validate(state["context_package"])
        requirements = [
            RequirementAlignmentItem.model_validate(item)
            for item in state.get("requirement_alignment", [])
        ]
        if evidence.status != "accepted":
            trace = FinalReviewDecisionTrace(
                matched_rule="Test output failed or inconsistent",
                considered_rules=considered,
                decision="request_more_test_evidence",
                status="blocked",
                next_stage="test",
                blocker=evidence.blocker,
            )
        elif any(item.severity == "critical" for item in findings):
            trace = FinalReviewDecisionTrace(
                matched_rule="critical threat",
                considered_rules=considered,
                decision="reject_to_execution",
                status="rejected",
                next_stage="execution",
                blocker="critical_threat",
            )
        elif any(item.severity == "error" and item.blocks_closeout for item in findings):
            trace = FinalReviewDecisionTrace(
                matched_rule="error threat",
                considered_rules=considered,
                decision="reject_to_execution",
                status="rejected",
                next_stage="execution",
                blocker="critical_threat",
            )
        elif any(item.status == "not_satisfied" for item in requirements):
            trace = FinalReviewDecisionTrace(
                matched_rule="hard requirement mismatch",
                considered_rules=considered,
                decision="reject_to_execution",
                status="rejected",
                next_stage="execution",
                blocker="hard_requirement_mismatch",
            )
        elif code_surface.status != "consistent":
            trace = FinalReviewDecisionTrace(
                matched_rule="code surface mismatch",
                considered_rules=considered,
                decision="reject_to_execution",
                status="rejected",
                next_stage="execution",
                blocker="code_surface_mismatch",
            )
        elif _has_active_causal_conflict(causal):
            trace = FinalReviewDecisionTrace(
                matched_rule="active/admitted causal conflict",
                considered_rules=considered,
                decision="causal_conflict_detected",
                status="blocked",
                next_stage="master",
                blocker="active_causal_conflict",
            )
        elif _context_blocks_acceptance(context):
            trace = FinalReviewDecisionTrace(
                matched_rule="material context insufficiency",
                considered_rules=considered,
                decision="governance_blocker",
                status="blocked",
                next_stage="master",
                blocker="context_unavailable",
            )
        elif any(item.severity == "warning" for item in findings):
            scope_limits = [
                f"{item.finding_id}: {item.title}"
                for item in findings
                if item.severity == "warning"
            ]
            trace = FinalReviewDecisionTrace(
                matched_rule="warning-only threat accepted with scope limits",
                considered_rules=considered,
                decision="accept_with_scope_limits",
                status="accepted_with_scope_limits",
                next_stage="master_closeout",
            )
        else:
            trace = FinalReviewDecisionTrace(
                matched_rule="all hard gates pass",
                considered_rules=considered,
                decision="accept_for_master_closeout",
                status="accepted",
                next_stage="master_closeout",
            )
    _package, _binding, writer = _runtime_parts(state)
    ref = writer.write_json(
        writer.artifact_dir("decision") / "decision_precedence_trace.json",
        trace,
        "decision_precedence_trace",
    )
    decision_ref = writer.write_json(
        writer.artifact_dir("decision") / "final_review_decision.json",
        trace,
        "final_review_decision",
    )
    return {
        "decision_trace": trace.model_dump(mode="json"),
        "decision_trace_ref": ref.model_dump(mode="json"),
        "decision_ref": decision_ref.model_dump(mode="json"),
        "scope_limits": scope_limits,
    }


def _closeout_node(state: FinalReviewGraphState) -> FinalReviewGraphState:
    package, binding, writer = _runtime_parts(state)
    trace = FinalReviewDecisionTrace.model_validate(state["decision_trace"])
    refs = _ensure_closeout_refs(state, writer)
    final_dir = writer.artifact_dir("final_report")
    final_report_ref = writer.write_text(
        final_dir / "final_review_report.md",
        _final_report_text(trace),
        "final_review_report",
    )
    next_route_ref = writer.write_json(
        final_dir / "next_route.json",
        {"next_stage": trace.next_stage, "decision": trace.decision},
        "next_route",
    )
    tool_audit_ref = _write_tool_audit(writer, state)
    state_boundary_ref = _write_state_boundary(state, writer, package)
    state_boundary = FinalReviewStateBoundaryResult.model_validate_json(read_text(state_boundary_ref.path))
    decision_trace_ref = ArtifactRef.model_validate(refs["decision_trace_ref"])
    decision_ref = ArtifactRef.model_validate(refs["decision_ref"])
    if state_boundary.status != "passed":
        trace = FinalReviewDecisionTrace(
            matched_rule="Final Review state boundary failed",
            considered_rules=[*trace.considered_rules, "Final Review terminal state boundary"],
            decision="governance_blocker",
            status="blocked",
            next_stage="master",
            blocker="schema_validation_failed",
        )
        final_report_ref = writer.write_text(
            final_dir / "final_review_report.md",
            _final_report_text(trace),
            "final_review_report",
        )
        next_route_ref = writer.write_json(
            final_dir / "next_route.json",
            {"next_stage": trace.next_stage, "decision": trace.decision},
            "next_route",
        )
        decision_trace_ref = writer.write_json(
            writer.artifact_dir("decision") / "decision_precedence_trace.json",
            trace,
            "decision_precedence_trace",
        )
        decision_ref = writer.write_json(
            writer.artifact_dir("decision") / "final_review_decision.json",
            trace,
            "final_review_decision",
        )
    artifact_schema_ref = writer.write_json(
        writer.artifact_dir("index") / "artifact_schema_validation_results.json",
        {"status": "pending"},
        "artifact_schema_validation",
    )
    artifact_hashes_ref = writer.write_json(
        writer.artifact_dir("index") / "artifact_hashes.json",
        [],
        "artifact_hashes",
    )
    final_output_hash_path = writer.artifact_dir("index") / "final_review_output_package.sha256"
    run_manifest = FinalReviewRunManifest(
        run_id=package.run_id,
        current_terminal_status=trace.status,
        decision=trace.decision,
        input_validation_hash=ArtifactRef.model_validate(state["input_validation_ref"]).sha256,
        input_fingerprint_sha256=_input_fingerprint_sha256(package),
        final_report_hash=final_report_ref.sha256,
        final_review_output_package_hash_path=str(final_output_hash_path),
    )
    run_manifest_ref = writer.write_json(
        writer.artifact_dir("index") / "run_manifest.json",
        run_manifest,
        "run_manifest",
    )
    evidence_index_ref = writer.write_json(
        writer.artifact_dir("index") / "evidence_index.json",
        _evidence_index_payload(state),
        "evidence_index",
    )
    output = FinalReviewOutputPackage(
        run_id=package.run_id,
        status=trace.status,
        decision=trace.decision,
        next_stage=trace.next_stage,
        final_review_run_dir=str(binding.final_review_artifact_root),
        input_validation_ref=ArtifactRef.model_validate(state["input_validation_ref"]),
        context_resolution_ref=ArtifactRef.model_validate(refs["context_resolution_ref"]),
        code_surface_manifest_ref=ArtifactRef.model_validate(refs["code_surface_manifest_ref"]),
        requirement_alignment_ref=ArtifactRef.model_validate(refs["requirement_alignment_ref"]),
        threat_findings_ref=ArtifactRef.model_validate(refs["threat_findings_ref"]),
        code_quality_findings_ref=ArtifactRef.model_validate(refs["code_quality_findings_ref"]),
        evidence_review_ref=ArtifactRef.model_validate(refs["evidence_review_ref"]),
        causal_consistency_ref=ArtifactRef.model_validate(refs["causal_consistency_ref"]),
        threat_checklist_matrix_ref=ArtifactRef.model_validate(refs["threat_checklist_matrix_ref"]),
        code_surface_consistency_ref=ArtifactRef.model_validate(refs["code_surface_consistency_ref"]),
        decision_precedence_trace_ref=decision_trace_ref,
        final_review_report_ref=final_report_ref,
        decision_ref=decision_ref,
        next_route_ref=next_route_ref,
        run_manifest_ref=run_manifest_ref,
        evidence_index_ref=evidence_index_ref,
        artifact_hashes_ref=artifact_hashes_ref,
        artifact_schema_validation_ref=artifact_schema_ref,
        state_boundary_results_ref=state_boundary_ref,
        tool_audit_ref=tool_audit_ref,
        boundary_flags=FinalReviewBoundaryFlags(),
        scope_limits=state.get("scope_limits", []) if trace.decision == "accept_with_scope_limits" else [],
        blocker=trace.blocker,
    )
    output_ref = writer.write_json(
        final_dir / "final_review_output_package.json",
        output,
        "final_review_output_package",
    )
    artifact_hashes_ref = _write_artifact_hashes(writer, binding.final_review_artifact_root)
    output = output.model_copy(update={"artifact_hashes_ref": artifact_hashes_ref})
    output_ref = writer.write_json(final_dir / "final_review_output_package.json", output, "final_review_output_package")
    artifact_schema_ref = writer.write_json(
        writer.artifact_dir("index") / "artifact_schema_validation_results.json",
        _closeout_schema_validation_payload(output, output_ref),
        "artifact_schema_validation",
    )
    output = output.model_copy(update={"artifact_schema_validation_ref": artifact_schema_ref})
    output_ref = writer.write_json(final_dir / "final_review_output_package.json", output, "final_review_output_package")
    writer.write_text(final_output_hash_path, sha256_file(output_ref.path) + "\n", "final_output_hash")
    _write_node_readme(writer, output_ref)
    return {"output_package": output.model_dump(mode="json")}


def _validate_inputs(package: FinalReviewInputPackage) -> FinalReviewInputValidation:
    reasons: list[str] = []
    blocker = None
    requirement_valid = _has_readme(package.requirement_package_dir)
    if requirement_valid:
        requirement_index = package.requirement_package_dir / "requirements.json"
        if not path_exists(requirement_index):
            requirement_valid = False
            blocker = blocker or "missing_required_artifact"
            reasons.append("requirement package requirements.json missing")
        else:
            try:
                requirements_payload = _read_json(requirement_index)
                if not isinstance(requirements_payload.get("requirements"), list):
                    requirement_valid = False
                    blocker = blocker or "schema_validation_failed"
                    reasons.append("requirement package requirements.json lacks requirements list")
            except Exception as exc:  # noqa: BLE001 - validation must capture malformed input.
                requirement_valid = False
                blocker = blocker or "schema_validation_failed"
                reasons.append(f"requirement package requirements.json invalid: {exc}")
    review_valid = _has_readme(package.requirement_review_package_dir)
    code_root_valid = False
    try:
        require_under_root(package.code_root, package.project_root, label="code_root")
        code_root_valid = path_exists(package.code_root)
    except ValueError:
        blocker = "code_root_escape"
        reasons.append("code_root escapes project_root")
    execution_valid = False
    test_valid = False
    terminal_valid = False
    boundary_valid = True
    hashes_valid = True
    roots_valid = True
    allowed_artifact_roots = [package.project_root / ".aegis" / "artifacts"]
    try:
        execution = _read_execution_output(package)
        execution_valid = execution.status == "completed" and execution.next_stage == "test_subgraph"
        if execution.status != "completed":
            blocker = blocker or "execution_not_completed"
            reasons.append("ExecutionOutputPackage.status is not completed")
        elif execution.next_stage != "test_subgraph":
            blocker = blocker or "execution_wrong_next_stage"
            reasons.append("ExecutionOutputPackage.next_stage is not test_subgraph")
        boundary_valid = boundary_valid and not any(execution.boundary.model_dump().values())
        execution_refs = [
            execution.implementation_artifact_ref,
            execution.implementation_changeset_ref,
            execution.simple_test_evidence_ref,
            execution.execution_causal_candidate_ref,
            execution.evidence_index_ref,
        ]
        try:
            mapping_ref = _execution_requirement_mapping_ref(package)
            execution_refs.append(mapping_ref)
        except Exception as exc:  # noqa: BLE001
            hashes_valid = False
            roots_valid = False
            blocker = blocker or "missing_required_artifact"
            reasons.append(f"execution requirement mapping ref invalid: {exc}")
        hashes_valid = hashes_valid and _artifact_hashes_valid(execution_refs)
        roots_valid = roots_valid and _artifact_refs_under_allowed_roots(
            execution_refs,
            allowed_artifact_roots,
        )
    except Exception as exc:  # noqa: BLE001 - validation must capture malformed packages.
        blocker = blocker or "missing_required_artifact"
        reasons.append(f"execution output invalid: {exc}")
    try:
        test_output = _read_test_output(package)
        test_valid = test_output.status == "passed" and test_output.next_stage == "final_review"
        if test_output.status != "passed":
            blocker = blocker or "test_not_passed"
            reasons.append("TestOutputPackage.status is not passed")
        elif test_output.next_stage != "final_review":
            blocker = blocker or "test_wrong_next_stage"
            reasons.append("TestOutputPackage.next_stage is not final_review")
        boundary_valid = boundary_valid and not any(test_output.boundary.model_dump().values())
        test_refs = [
            test_output.input_validation_ref,
            test_output.approved_test_plan_ref,
            test_output.test_execution_manifest_ref,
            test_output.evidence_check_ref,
            test_output.artifact_schema_check_ref,
            test_output.final_test_report_ref,
            test_output.state_boundary_results_ref,
            test_output.evidence_index_ref,
        ]
        hashes_valid = hashes_valid and _artifact_hashes_valid(test_refs)
        roots_valid = roots_valid and _artifact_refs_under_allowed_roots(test_refs, allowed_artifact_roots)
    except Exception as exc:  # noqa: BLE001
        blocker = blocker or "missing_required_artifact"
        reasons.append(f"test output invalid: {exc}")
    if not requirement_valid and not any("requirement package" in reason for reason in reasons):
        blocker = blocker or "missing_required_artifact"
        reasons.append("requirement package README.md missing")
    if not review_valid:
        blocker = blocker or "missing_required_artifact"
        reasons.append("requirement review package README.md missing")
    if not boundary_valid:
        blocker = blocker or "boundary_flag_violation"
        reasons.append("Execution or Test boundary flags are invalid")
    if not hashes_valid:
        blocker = blocker or "artifact_hash_mismatch"
        reasons.append("artifact hash mismatch")
    if not roots_valid:
        blocker = blocker or "artifact_root_escape"
        reasons.append("artifact ref escapes allowed roots")
    terminal_valid = execution_valid and test_valid and boundary_valid and hashes_valid
    accepted = all(
        [
            requirement_valid,
            review_valid,
            execution_valid,
            test_valid,
            hashes_valid,
            boundary_valid,
            code_root_valid,
            roots_valid,
            terminal_valid,
        ]
    )
    return FinalReviewInputValidation(
        requirement_package_valid=requirement_valid,
        requirement_review_package_valid=review_valid,
        execution_output_valid=execution_valid,
        test_output_valid=test_valid,
        artifact_hashes_valid=hashes_valid,
        boundary_flags_valid=boundary_valid,
        code_root_valid=code_root_valid,
        allowed_artifact_roots_valid=roots_valid,
        terminal_consistency_valid=terminal_valid,
        status="accepted" if accepted else "blocked",
        blocker=None if accepted else blocker or "terminal_consistency_mismatch",
        reasons=reasons,
    )


def _bind_project(package: FinalReviewInputPackage) -> FinalReviewProjectBinding:
    base_artifact_root = (
        package.project_root
        / ".aegis"
        / "artifacts"
        / "final_review"
        / package.run_id
    )
    artifact_root = _select_run_artifact_root(base_artifact_root, _input_fingerprint_sha256(package))
    return FinalReviewProjectBinding(
        project_root=package.project_root,
        code_root=package.code_root,
        knowledge_store_root=str(package.project_root / "knowledge"),
        causal_store_root=str(package.project_root / "causal"),
        final_review_artifact_root=artifact_root,
    )


def _select_run_artifact_root(base_root: Path, input_fingerprint: str) -> Path:
    if not path_exists(base_root):
        return base_root
    if _run_root_matches_input(base_root, input_fingerprint):
        return base_root

    candidate = base_root.with_name(f"{base_root.name}-{input_fingerprint[:12]}")
    if not path_exists(candidate) or _run_root_matches_input(candidate, input_fingerprint):
        return candidate

    counter = 2
    while True:
        fallback = base_root.with_name(f"{base_root.name}-{input_fingerprint[:12]}-{counter}")
        if not path_exists(fallback) or _run_root_matches_input(fallback, input_fingerprint):
            return fallback
        counter += 1


def _run_root_matches_input(run_root: Path, input_fingerprint: str) -> bool:
    marker = run_root / "index" / "input_fingerprint.json"
    if not path_exists(marker):
        return False
    try:
        payload = json.loads(read_text(marker))
    except Exception:  # noqa: BLE001 - corrupt marker must not authorize overwrite.
        return False
    return payload.get("input_fingerprint_sha256") == input_fingerprint


def _write_input_fingerprint(
    writer: FinalReviewArtifactWriter,
    package: FinalReviewInputPackage,
) -> ArtifactRef:
    fingerprint = _input_fingerprint_sha256(package)
    return writer.write_json(
        writer.artifact_dir("index") / "input_fingerprint.json",
        {
            "run_id": package.run_id,
            "input_fingerprint_sha256": fingerprint,
            "rerun_policy": "reuse only when input_fingerprint_sha256 matches; otherwise choose a distinct run directory",
        },
        "input_fingerprint",
    )


def _input_fingerprint_sha256(package: FinalReviewInputPackage) -> str:
    payload = {
        "run_id": package.run_id,
        "project_root": str(package.project_root.resolve()),
        "code_root": _path_fingerprint(package.code_root),
        "requirement_package_dir": _path_fingerprint(package.requirement_package_dir),
        "requirement_review_package_dir": _path_fingerprint(package.requirement_review_package_dir),
        "execution_output_package_path": _path_fingerprint(package.execution_output_package_path),
        "test_output_package_path": _path_fingerprint(package.test_output_package_path),
        "knowledge_context_path": _path_fingerprint(package.knowledge_context_path)
        if package.knowledge_context_path
        else None,
        "causal_context_path": _path_fingerprint(package.causal_context_path)
        if package.causal_context_path
        else None,
        "max_serialized_state_bytes": package.max_serialized_state_bytes,
        "prohibited_action_attempts": [
            attempt.model_dump(mode="json") for attempt in package.prohibited_action_attempts
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_fingerprint(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not path_exists(resolved):
        return {"path": str(resolved), "exists": False, "kind": "missing", "sha256": None}
    kind = "directory" if resolved.is_dir() else "file"
    return {
        "path": str(resolved),
        "exists": True,
        "kind": kind,
        "sha256": sha256_path(resolved) if kind == "directory" else sha256_file(resolved),
    }


def _runtime_parts(
    state: FinalReviewGraphState,
) -> tuple[FinalReviewInputPackage, FinalReviewProjectBinding, FinalReviewArtifactWriter]:
    package = FinalReviewInputPackage.model_validate(state["input_package"])
    binding_payload = state.get("binding")
    binding = (
        FinalReviewProjectBinding.model_validate(binding_payload)
        if binding_payload
        else _bind_project(package)
    )
    return package, binding, FinalReviewArtifactWriter(binding)


def _write_artifact_readmes(writer: FinalReviewArtifactWriter) -> None:
    root = writer.binding.final_review_artifact_root
    writer.write_text(
        root / "README.md",
        "Final Review run artifact root. Read input, context, code_surface, threat_review, "
        "evidence_review, causal_consistency, decision, final_report, then index.\n",
        "final_review_run_readme",
    )
    for name in [
        "input",
        "context",
        "code_surface",
        "requirement_alignment",
        "threat_review",
        "code_quality",
        "evidence_review",
        "causal_consistency",
        "decision",
        "final_report",
        "tool_audit",
        "index",
    ]:
        writer.write_text(
            writer.artifact_dir(name) / "README.md",
            f"Final Review {name} artifacts.\n",
            f"{name}_readme",
        )


def _read_execution_output(package: FinalReviewInputPackage) -> ExecutionOutputPackage:
    return ExecutionOutputPackage.model_validate_json(read_text(package.execution_output_package_path))


def _read_test_output(package: FinalReviewInputPackage) -> TestOutputPackage:
    return TestOutputPackage.model_validate_json(read_text(package.test_output_package_path))


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(read_text(path))


def _list_payload(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _has_readme(path: Path) -> bool:
    return path_exists(path / "README.md")


def _artifact_hashes_valid(refs: list[Any]) -> bool:
    for ref in refs:
        if ref is None:
            return False
        if not path_exists(ref.path):
            return False
        if sha256_path(ref.path) != ref.sha256:
            return False
    return True


def _artifact_refs_under_allowed_roots(refs: list[Any], allowed_roots: list[Path]) -> bool:
    for ref in refs:
        if ref is None:
            return False
        if not _path_under_any_root(ref.path, allowed_roots):
            return False
        if not _path_under_any_root(ref.readme_path, allowed_roots):
            return False
    return True


def _path_under_any_root(path: str | Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            require_under_root(path, root, label="artifact ref")
            return True
        except ValueError:
            continue
    return False


def _convert_ref(ref: Any) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=ref.artifact_id,
        artifact_type=ref.artifact_type,
        path=ref.path,
        readme_path=ref.readme_path,
        sha256=ref.sha256,
        created_by_node=ref.created_by_node,
        created_at_utc=ref.created_at_utc,
        round=ref.round,
    )


def _current_code_manifest(code_root: Path) -> dict[str, Any]:
    files = []
    for item in iter_files(code_root):
        files.append(
            {
                "path": item.relative_to(code_root).as_posix(),
                "sha256": sha256_file(item),
                "size_bytes": item.stat().st_size,
            }
        )
    return {"code_root": str(code_root), "files": files}


def _test_changeset_ref(package: FinalReviewInputPackage) -> ArtifactRef | None:
    test_output = _read_test_output(package)
    evidence_index = _read_json(test_output.evidence_index_ref.path)
    payload = evidence_index.get("test_run_changeset_ref") or evidence_index.get("changeset_ref")
    return ArtifactRef.model_validate(payload) if payload else None


def _test_changeset_payload(package: FinalReviewInputPackage) -> dict[str, Any]:
    ref = _test_changeset_ref(package)
    return _read_json(ref.path) if ref else {}


def _execution_requirement_mapping_ref(package: FinalReviewInputPackage) -> ArtifactRef:
    execution = _read_execution_output(package)
    if execution.evidence_index_ref is None:
        raise ValueError("execution output lacks evidence_index_ref")
    evidence_index = _read_json(execution.evidence_index_ref.path)
    payload = evidence_index.get("requirement_mapping_ref")
    if not payload:
        raise ValueError("execution evidence index lacks requirement_mapping_ref")
    return ArtifactRef.model_validate(payload)


def _execution_requirement_mapping_payload(package: FinalReviewInputPackage) -> dict[str, Any]:
    return _read_json(_execution_requirement_mapping_ref(package).path)


def _expected_code_manifest_hashes(changeset: dict[str, Any]) -> tuple[str, dict[str, str]]:
    manifest = changeset.get("code_manifest")
    if isinstance(manifest, dict) and isinstance(manifest.get("files"), list):
        return (
            "full_manifest",
            {
                str(item.get("path")): str(item.get("sha256", ""))
                for item in manifest["files"]
                if item.get("path")
            },
        )
    return (
        "changed_files_only",
        {
            str(item.get("path")): str(item.get("sha256_after", ""))
            for item in _list_payload(changeset.get("changed_files"))
            if item.get("path")
        },
    )


def _test_execution_records_payload(evidence_index: dict[str, Any]) -> list[dict[str, Any]]:
    payload = evidence_index.get("test_node_execution_records_ref")
    if not payload:
        return []
    ref = ArtifactRef.model_validate(payload)
    records: list[dict[str, Any]] = []
    for line in read_text(ref.path).splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def _has_critical_shell_threat(content: str) -> bool:
    dangerous_tokens = ["os.system(", "subprocess.", "shell=True", "eval(", "exec("]
    return any(token in content for token in dangerous_tokens)


def _detect_threat_surfaces(content: str) -> dict[str, bool]:
    return {
        "THREAT-001-shell-command-execution": _has_critical_shell_threat(content),
        "THREAT-002-path-input-handling": any(
            token in content for token in ["Path(", "open(", "read_text(", "write_text("]
        ),
        "THREAT-003-file-delete-move-overwrite-recursive-scan": any(
            token in content
            for token in ["unlink(", "rmdir(", "remove(", "shutil.rmtree", "shutil.move", "os.walk("]
        ),
        "THREAT-004-secret-read-or-logging": any(
            token.lower() in content.lower() for token in ["secret", "token", "password", "api_key"]
        ),
        "THREAT-005-network-or-remote-publication": any(
            token in content for token in ["requests.", "httpx.", "urllib.", "socket.", "git push"]
        ),
        "THREAT-006-truth-store-write": any(
            token in content for token in ["knowledge/", "causal/", "truth_written"]
        ),
        "THREAT-007-governance-bypass": any(
            token in content for token in ["skip_review", "bypass", "force=True"]
        ),
        "THREAT-008-unbounded-resource-or-concurrency": any(
            token in content for token in ["while True", "ThreadPoolExecutor", "ProcessPoolExecutor"]
        ),
        "THREAT-009-raw-report-trust": "raw_report" in content,
        "THREAT-010-unadmitted-dependency-or-platform-assumption": any(
            token in content for token in ["pip install", "npm install", "apt install", "platform.system("]
        ),
    }


def _threat_finding(checklist_id: str, reviewed_path: str) -> ReviewFinding:
    metadata = {
        "THREAT-001-shell-command-execution": (
            "critical",
            "Unsafe shell execution surface",
            "Changed code contains unbounded shell execution.",
            True,
        ),
        "THREAT-002-path-input-handling": (
            "warning",
            "Filesystem path handling requires bounded review scope",
            "Changed code handles filesystem paths; closeout may proceed only with explicit scope limits.",
            False,
        ),
        "THREAT-003-file-delete-move-overwrite-recursive-scan": (
            "critical",
            "Destructive filesystem operation surface",
            "Changed code can delete, move, overwrite, or recursively scan files.",
            True,
        ),
        "THREAT-004-secret-read-or-logging": (
            "critical",
            "Secret read or logging surface",
            "Changed code appears to read or log secret-like material.",
            True,
        ),
        "THREAT-005-network-or-remote-publication": (
            "critical",
            "Network or remote publication surface",
            "Changed code can communicate with remote systems or publish externally.",
            True,
        ),
        "THREAT-006-truth-store-write": (
            "critical",
            "Knowledge/Causal truth-store mutation surface",
            "Changed code appears able to write truth-store material directly.",
            True,
        ),
        "THREAT-007-governance-bypass": (
            "critical",
            "Governance bypass surface",
            "Changed code contains governance bypass indicators.",
            True,
        ),
        "THREAT-008-unbounded-resource-or-concurrency": (
            "error",
            "Unbounded resource or concurrency surface",
            "Changed code introduces potentially unbounded runtime behavior.",
            True,
        ),
        "THREAT-009-raw-report-trust": (
            "error",
            "Raw report trust surface",
            "Changed code may trust raw reports over structured evidence.",
            True,
        ),
        "THREAT-010-unadmitted-dependency-or-platform-assumption": (
            "warning",
            "Unadmitted dependency or platform assumption",
            "Changed code uses dependency or platform assumptions that require scope-limited closeout.",
            False,
        ),
    }
    severity, title, description, blocks = metadata[checklist_id]
    return ReviewFinding(
        finding_id=f"threat-{checklist_id.removeprefix('THREAT-').replace('_', '-').lower()}",
        category="threat",
        severity=severity,  # type: ignore[arg-type]
        title=title,
        description=f"{description} Reviewed path: {reviewed_path}.",
        affected_refs=[],
        evidence_refs=[],
        requirement_ids=[],
        recommendation="Return to Execution if blocking; otherwise preserve explicit Final Review scope limits.",
        recommended_next_owner="execution" if blocks else "none",
        blocks_closeout=blocks,
    )


def _threat_checklist_items(
    threat_hits: dict[str, bool],
    reviewed_paths: list[str],
) -> list[ThreatChecklistItem]:
    questions = {
        "THREAT-001-shell-command-execution": "Does changed code execute shell commands?",
        "THREAT-002-path-input-handling": "Does changed code handle filesystem paths?",
        "THREAT-003-file-delete-move-overwrite-recursive-scan": "Does changed code delete, move, overwrite, or recursively scan files?",
        "THREAT-004-secret-read-or-logging": "Does changed code read or log secrets?",
        "THREAT-005-network-or-remote-publication": "Does changed code perform network or remote publication?",
        "THREAT-006-truth-store-write": "Does changed code write Knowledge or Causal truth?",
        "THREAT-007-governance-bypass": "Does changed code bypass governance gates?",
        "THREAT-008-unbounded-resource-or-concurrency": "Does changed code introduce unbounded resources or concurrency?",
        "THREAT-009-raw-report-trust": "Does changed code trust raw reports over structured evidence?",
        "THREAT-010-unadmitted-dependency-or-platform-assumption": "Does changed code assume unadmitted dependencies or platforms?",
    }
    blocker_ids = {
        "THREAT-001-shell-command-execution",
        "THREAT-003-file-delete-move-overwrite-recursive-scan",
        "THREAT-004-secret-read-or-logging",
        "THREAT-005-network-or-remote-publication",
        "THREAT-006-truth-store-write",
        "THREAT-007-governance-bypass",
        "THREAT-008-unbounded-resource-or-concurrency",
        "THREAT-009-raw-report-trust",
    }
    return [
        ThreatChecklistItem(
            checklist_id=checklist_id,
            question=questions[checklist_id],
            status="yes" if threat_hits.get(checklist_id, False) else "no",
            reviewed_paths=reviewed_paths,
            finding_refs=[f"threat-{checklist_id.removeprefix('THREAT-').replace('_', '-').lower()}"]
            if threat_hits.get(checklist_id)
            else [],
            blocker=checklist_id in blocker_ids and threat_hits.get(checklist_id, False),
        )
        for checklist_id in REQUIRED_THREAT_CHECKLIST_IDS
    ]


def _causal_assessment(payload: dict[str, Any]) -> CausalRefAssessment:
    status = payload.get("status", "unknown")
    hard = status in {"active", "admitted"}
    return CausalRefAssessment(
        causal_ref=payload.get("causal_ref", "unknown"),
        status=status,
        usable_as_hard_constraint=hard,
        usable_as_advisory_context=status in {"candidate", "active", "admitted"},
        conflict_materiality=payload.get("conflict_materiality", "none"),
        assessment_reason=payload.get("assessment_reason", "No assessment reason provided."),
    )


def _has_active_causal_conflict(assessments: list[CausalRefAssessment]) -> bool:
    return any(
        item.status in {"active", "admitted"} and item.conflict_materiality in {"high", "blocker"}
        for item in assessments
    )


def _context_blocks_acceptance(context: FinalReviewContextPackage) -> bool:
    availability_failed = any(value in {"missing", "degraded"} for value in context.store_availability.values())
    material_missing = any(bool(item.get("material", True)) for item in context.missing_context_items)
    return (
        availability_failed
        or material_missing
        or context.degraded_recall
        or not context.requirement_context_sufficient
        or not context.threat_context_sufficient
        or not context.causal_context_sufficient
    )


def _write_tool_audit(writer: FinalReviewArtifactWriter, state: FinalReviewGraphState) -> ArtifactRef:
    package = FinalReviewInputPackage.model_validate(state["input_package"])
    audit_dir = writer.artifact_dir("tool_audit")
    read_paths = sorted(_audited_read_paths(state))
    writer.write_json(
        audit_dir / "tool_action_plan.json",
        [
            {
                "tool": "read_file",
                "intent": "final_review_evidence_read",
                "side_effect_level": "read_only",
                "path": path,
                "capability": "local_file_read",
                "risk_gate": "allow_read_only",
            }
            for path in read_paths
        ],
        "tool_action_plan",
    )
    writer.write_jsonl(
        audit_dir / "tool_execution_records.jsonl",
        [
            {
                "tool": "read_file",
                "status": "executed",
                "intent": "final_review_evidence_read",
                "side_effect_level": "read_only",
                "path": path,
                "capability": "local_file_read",
                "risk_gate": "allow_read_only",
                "result_sha256": sha256_file(path) if path_exists(path) else None,
            }
            for path in read_paths
        ],
        "tool_execution_records",
    )
    denied_actions = [_denied_action_record(attempt) for attempt in package.prohibited_action_attempts]
    return writer.write_json(audit_dir / "denied_actions.json", denied_actions, "denied_actions")


def _denied_action_record(attempt: FinalReviewProhibitedActionAttempt) -> dict[str, Any]:
    return {
        "attempted_action": attempt.attempted_action,
        "requested_tool": attempt.requested_tool,
        "reason": attempt.reason,
        "risk_class": attempt.risk_class,
        "denial_decision": "denied",
        "affected_artifact_refs": attempt.affected_artifact_refs,
        "side_effect_level": "forbidden",
        "policy": "final_review_read_only_governance_gate",
    }


def _audited_read_paths(state: FinalReviewGraphState) -> set[str]:
    package = FinalReviewInputPackage.model_validate(state["input_package"])
    paths = {
        str(package.requirement_package_dir / "requirements.json"),
        str(package.execution_output_package_path),
        str(package.test_output_package_path),
    }
    for optional in [package.knowledge_context_path, package.causal_context_path]:
        if optional is not None:
            paths.add(str(optional))
    for ref_payload in _evidence_index_payload(state).values():
        try:
            paths.add(ArtifactRef.model_validate(ref_payload).path)
        except Exception:  # noqa: BLE001 - audit should not fail closeout.
            continue
    return paths


def _ensure_closeout_refs(
    state: FinalReviewGraphState,
    writer: FinalReviewArtifactWriter,
) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    skipped_dir = writer.artifact_dir("skipped")
    defaults: dict[str, tuple[str, Any]] = {
        "context_resolution_ref": ("context_resolution_skipped.json", {"status": "skipped"}),
        "code_surface_manifest_ref": ("code_surface_manifest_skipped.json", {"status": "skipped"}),
        "requirement_alignment_ref": ("requirement_alignment_skipped.json", []),
        "threat_findings_ref": ("threat_findings_skipped.json", []),
        "code_quality_findings_ref": ("code_quality_findings_skipped.json", []),
        "evidence_review_ref": ("evidence_review_skipped.json", {"status": "skipped"}),
        "causal_consistency_ref": ("causal_consistency_skipped.json", {"status": "skipped"}),
        "threat_checklist_matrix_ref": (
            "threat_checklist_matrix_skipped.json",
            ThreatChecklistMatrix(
                items=[
                    ThreatChecklistItem(
                        checklist_id=checklist_id,
                        question="Skipped because input validation blocked Final Review.",
                        status="unknown",
                    )
                    for checklist_id in REQUIRED_THREAT_CHECKLIST_IDS
                ],
                all_items_answered=False,
                unknown_security_relevant_items=list(REQUIRED_THREAT_CHECKLIST_IDS),
            ),
        ),
        "code_surface_consistency_ref": ("code_surface_consistency_skipped.json", {"status": "skipped"}),
    }
    for key, (filename, payload) in defaults.items():
        if key in state:
            refs[key] = state[key]
            continue
        refs[key] = writer.write_json(skipped_dir / filename, payload, key.removesuffix("_ref")).model_dump(
            mode="json"
        )
    refs["decision_trace_ref"] = state["decision_trace_ref"]
    refs["decision_ref"] = state["decision_ref"]
    return refs


def _closeout_schema_validation_payload(
    output: FinalReviewOutputPackage,
    output_ref: ArtifactRef,
) -> dict[str, Any]:
    checks = [
        _schema_validation_check(
            "FinalReviewOutputPackage",
            output_ref,
            lambda text: FinalReviewOutputPackage.model_validate_json(text),
        ),
        _schema_validation_check(
            "FinalReviewDecisionTrace",
            output.decision_precedence_trace_ref,
            lambda text: FinalReviewDecisionTrace.model_validate_json(text),
        ),
        _schema_validation_check(
            "ThreatChecklistMatrix",
            output.threat_checklist_matrix_ref,
            lambda text: ThreatChecklistMatrix.model_validate_json(text),
        ),
        _schema_validation_check(
            "CodeSurfaceConsistency",
            output.code_surface_consistency_ref,
            lambda text: CodeSurfaceConsistency.model_validate_json(text),
        ),
        _schema_validation_check(
            "EvidenceReviewMatrix",
            output.evidence_review_ref,
            lambda text: EvidenceReviewMatrix.model_validate_json(text),
        ),
        _schema_validation_check(
            "FinalReviewRunManifest",
            output.run_manifest_ref,
            lambda text: FinalReviewRunManifest.model_validate_json(text),
        ),
        _schema_validation_check(
            "FinalReviewStateBoundaryResult",
            output.state_boundary_results_ref,
            lambda text: FinalReviewStateBoundaryResult.model_validate_json(text),
        ),
        _schema_validation_check(
            "next_route",
            output.next_route_ref,
            lambda text: _validate_next_route_payload(text, output),
        ),
        _schema_validation_check(
            "evidence_index",
            output.evidence_index_ref,
            lambda text: _validate_json_object(text, required_keys=["input_validation_ref", "decision_trace_ref"]),
        ),
        _schema_validation_check(
            "artifact_hashes",
            output.artifact_hashes_ref,
            _validate_artifact_hash_rows,
        ),
        _schema_validation_check(
            "tool_action_plan",
            Path(output.tool_audit_ref.path).parent / "tool_action_plan.json",
            lambda text: _validate_json_list(text, required_keys=["tool", "path", "intent", "side_effect_level"]),
        ),
        _schema_validation_check(
            "tool_execution_records",
            Path(output.tool_audit_ref.path).parent / "tool_execution_records.jsonl",
            _validate_tool_execution_records,
        ),
        _schema_validation_check(
            "denied_actions",
            output.tool_audit_ref,
            _validate_json_list,
        ),
        _schema_validation_check(
            "requirement_alignment",
            output.requirement_alignment_ref,
            lambda text: [RequirementAlignmentItem.model_validate(item) for item in json.loads(text)],
        ),
        _schema_validation_check(
            "threat_findings",
            output.threat_findings_ref,
            lambda text: [ReviewFinding.model_validate(item) for item in json.loads(text)],
        ),
        _schema_validation_check(
            "code_quality_findings",
            output.code_quality_findings_ref,
            lambda text: [ReviewFinding.model_validate(item) for item in json.loads(text)],
        ),
        _schema_validation_check(
            "context_resolution",
            output.context_resolution_ref,
            lambda text: FinalReviewContextPackage.model_validate_json(text),
        ),
        _schema_validation_check(
            "causal_ref_assessments",
            output.causal_consistency_ref,
            lambda text: [CausalRefAssessment.model_validate(item) for item in json.loads(text)],
        ),
    ]
    failures = [
        {
            "schema_name": item["schema_name"],
            "path": item["path"],
            "failure_reason": item["failure_reason"],
        }
        for item in checks
        if item["status"] != "passed"
    ]
    return {
        "status": "failed" if failures else "passed",
        "checked_artifacts": checks,
        "failures": failures,
        "self_reference_policy": {
            "final_review_output_package": "structurally validated before final self-reference hash write; final output sha256 is detached under index/final_review_output_package.sha256",
            "excluded_from_artifact_hash_manifest": [
                "index/artifact_hashes.json",
                "index/artifact_schema_validation_results.json",
                "index/final_review_output_package.sha256",
                "final_report/final_review_output_package.json",
            ],
        },
    }


def _schema_validation_check(
    schema_name: str,
    ref: ArtifactRef | Path,
    validator: Any,
) -> dict[str, Any]:
    path = ref.path if isinstance(ref, ArtifactRef) else str(ref)
    if not path_exists(path):
        return {
            "schema_name": schema_name,
            "path": path,
            "status": "failed",
            "failure_reason": "artifact path missing",
        }
    try:
        validator(read_text(path))
    except Exception as exc:  # noqa: BLE001 - schema validation must report all failures.
        return {
            "schema_name": schema_name,
            "path": path,
            "status": "failed",
            "failure_reason": str(exc),
        }
    return {
        "schema_name": schema_name,
        "path": path,
        "status": "passed",
        "failure_reason": None,
    }


def _validate_next_route_payload(text: str, output: FinalReviewOutputPackage) -> dict[str, Any]:
    payload = json.loads(text)
    if payload.get("next_stage") != output.next_stage or payload.get("decision") != output.decision:
        raise ValueError("next_route does not match terminal output")
    return payload


def _validate_json_object(text: str, *, required_keys: list[str] | None = None) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    for key in required_keys or []:
        if key not in payload:
            raise ValueError(f"missing required key: {key}")
    return payload


def _validate_json_list(text: str, *, required_keys: list[str] | None = None) -> list[Any]:
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("expected JSON list")
    for row in payload:
        if required_keys is None:
            continue
        if not isinstance(row, dict):
            raise ValueError("expected list rows to be JSON objects")
        for key in required_keys:
            if key not in row:
                raise ValueError(f"missing required key: {key}")
    return payload


def _validate_artifact_hash_rows(text: str) -> list[dict[str, Any]]:
    rows = _validate_json_list(text, required_keys=["path", "sha256", "size"])
    for row in rows:
        if row["path"] in {
            "index/artifact_hashes.json",
            "index/artifact_schema_validation_results.json",
            "index/final_review_output_package.sha256",
            "final_report/final_review_output_package.json",
        }:
            raise ValueError(f"self-mutating artifact must not be hashed: {row['path']}")
    return rows  # type: ignore[return-value]


def _validate_tool_execution_records(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for key in ["tool", "status", "side_effect_level", "path", "intent", "result_sha256"]:
            if key not in row:
                raise ValueError(f"missing required key: {key}")
        rows.append(row)
    if not rows:
        raise ValueError("tool execution records must not be empty")
    return rows


def _write_state_boundary(
    state: FinalReviewGraphState,
    writer: FinalReviewArtifactWriter,
    package: FinalReviewInputPackage,
) -> ArtifactRef:
    payload = json.dumps(_jsonable(state), ensure_ascii=True, sort_keys=True)
    result = FinalReviewStateBoundaryResult(
        serialized_state_size_bytes=len(payload.encode("utf-8")),
        max_serialized_state_bytes=package.max_serialized_state_bytes,
        long_text_fields_detected=[],
        artifact_refs_only=True,
        status="passed"
        if len(payload.encode("utf-8")) <= package.max_serialized_state_bytes
        else "failed",
    )
    return writer.write_json(
        writer.artifact_dir("index") / "state_boundary_results.json",
        result,
        "state_boundary_results",
    )


def _write_artifact_hashes(writer: FinalReviewArtifactWriter, root: Path) -> ArtifactRef:
    rows = [
        {
            "path": item.relative_to(root).as_posix(),
            "sha256": sha256_file(item),
            "size": item.stat().st_size,
        }
        for item in iter_files(root)
        if _include_in_hash_manifest(item, root)
    ]
    return writer.write_json(writer.artifact_dir("index") / "artifact_hashes.json", rows, "artifact_hashes")


def _include_in_hash_manifest(path: Path, root: Path) -> bool:
    if path.name.endswith(".tmp"):
        return False
    relative = path.relative_to(root).as_posix()
    return relative not in {
        "index/artifact_hashes.json",
        "index/artifact_schema_validation_results.json",
        "index/final_review_output_package.sha256",
        "final_report/final_review_output_package.json",
    }


def _evidence_index_payload(state: FinalReviewGraphState) -> dict[str, Any]:
    keys = [
        "input_validation_ref",
        "context_resolution_ref",
        "code_surface_manifest_ref",
        "code_surface_consistency_ref",
        "requirement_alignment_ref",
        "threat_findings_ref",
        "threat_checklist_matrix_ref",
        "code_quality_findings_ref",
        "evidence_review_ref",
        "causal_consistency_ref",
        "decision_trace_ref",
    ]
    return {key: state[key] for key in keys if key in state}


def _final_report_text(trace: FinalReviewDecisionTrace) -> str:
    return (
        "# Final Review Report\n\n"
        f"- status: `{trace.status}`\n"
        f"- decision: `{trace.decision}`\n"
        f"- next_stage: `{trace.next_stage}`\n"
        f"- matched_rule: `{trace.matched_rule}`\n\n"
        "This report is a gate decision only. It does not modify code, run tests, "
        "or admit Knowledge/Causal truth.\n"
    )


def _write_node_readme(writer: FinalReviewArtifactWriter, output_ref: ArtifactRef) -> None:
    writer.write_text(
        writer.binding.final_review_artifact_root / "README.md",
        "Final Review artifact root. Read final_report/final_review_report.md first, then "
        "final_report/final_review_output_package.json and final_report/next_route.json. "
        f"Output package: {output_ref.path}\n",
        "final_review_run_readme",
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
