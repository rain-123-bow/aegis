from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

LEADER_SKILL_ID = "DEBATE_LEADER_OPERATIONAL_SKILL"
LEADER_SKILL_VERSION = "v0.1"
WORKER_SKILL_ID = "DEBATE_WORKER_OPERATIONAL_SKILL"
WORKER_SKILL_VERSION = "v0.1"
PHASE = "phase25a_debate_role_operational_skills"

ALLOWED_ADMISSION_DECISIONS = {
    "accept_for_debate",
    "reject_no_debate_needed",
    "reject_insufficient_information",
    "reject_out_of_scope",
    "request_more_context",
}

ALLOWED_ADJUDICATION_DECISIONS = {
    "accept_one",
    "accept_multiple_by_scope",
    "need_more_evidence",
    "reject_debate_no_valid_position",
    "stop_and_request_test",
    "stop_and_escalate_to_master",
}

REQUIRED_PACKAGE_FILES = {
    "README.md",
    "final_report.json",
    "adjudicator_causal_state.json",
    "transcript_digest.json",
    "evidence_manifest.json",
}

FORBIDDEN_TRUE_FIELDS = (
    "global_causal_truth_merge_performed",
    "production_store_write_performed",
    "remote_push_performed",
    "pull_request_created",
    "remote_merge_performed",
    "release_performed",
)


class DebateOperationalSkillError(ValueError):
    """Raised when Phase 25A Debate skill validation input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == []


@dataclass(frozen=True)
class DebateSkillValidationResult:
    debate_skill_validation_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    leader_skill_ref: dict[str, str]
    worker_skill_ref: dict[str, str]
    stance_count: int = 0
    worker_creation_count: int = 0
    worker_output_count: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)
    leader_skill_installed: bool = False
    worker_skill_installation_verified: bool = False
    worker_skill_outputs_verified: bool = False
    adjudicator_causal_state_verified: bool = False
    causal_package_verified: bool = False
    global_causal_truth_merge_performed: bool = False
    production_store_write_performed: bool = False
    remote_push_performed: bool = False
    pull_request_created: bool = False
    remote_merge_performed: bool = False
    release_performed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "debate_skill_validation_result_id": self.debate_skill_validation_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "leader_skill_ref": dict(self.leader_skill_ref),
            "worker_skill_ref": dict(self.worker_skill_ref),
            "stance_count": self.stance_count,
            "worker_creation_count": self.worker_creation_count,
            "worker_output_count": self.worker_output_count,
            "violations": list(self.violations),
            "leader_skill_installed": self.leader_skill_installed,
            "worker_skill_installation_verified": self.worker_skill_installation_verified,
            "worker_skill_outputs_verified": self.worker_skill_outputs_verified,
            "adjudicator_causal_state_verified": self.adjudicator_causal_state_verified,
            "causal_package_verified": self.causal_package_verified,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "production_store_write_performed": self.production_store_write_performed,
            "remote_push_performed": self.remote_push_performed,
            "pull_request_created": self.pull_request_created,
            "remote_merge_performed": self.remote_merge_performed,
            "release_performed": self.release_performed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DebateOperationalSkillError(f"file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise DebateOperationalSkillError(f"file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DebateOperationalSkillError("file must contain a JSON object")
    return payload


def validate_debate_skill_run_file(
    run_path: str | Path,
    *,
    leader_skill_path: str | Path | None = None,
    worker_skill_path: str | Path | None = None,
) -> DebateSkillValidationResult:
    return validate_debate_skill_run(
        load_json_object(run_path),
        leader_skill_path=leader_skill_path,
        worker_skill_path=worker_skill_path,
    )


def validate_debate_skill_run(
    run: dict[str, Any],
    *,
    leader_skill_path: str | Path | None = None,
    worker_skill_path: str | Path | None = None,
) -> DebateSkillValidationResult:
    if not isinstance(run, dict):
        raise DebateOperationalSkillError("run must be a JSON object")

    violations: list[dict[str, Any]] = []

    if leader_skill_path is not None:
        _check_skill_file(leader_skill_path, skill_id=LEADER_SKILL_ID, skill_version=LEADER_SKILL_VERSION, field="leader_skill_file", violations=violations)
    if worker_skill_path is not None:
        _check_skill_file(worker_skill_path, skill_id=WORKER_SKILL_ID, skill_version=WORKER_SKILL_VERSION, field="worker_skill_file", violations=violations)

    leader_ref = _ref(run.get("skill_ref"))
    if not _is_skill_ref(leader_ref, LEADER_SKILL_ID, LEADER_SKILL_VERSION):
        violations.append(_violation("skill_ref", "Debate Leader run must reference DEBATE_LEADER_OPERATIONAL_SKILL v0.1."))

    admission = run.get("admission") if isinstance(run.get("admission"), dict) else {}
    admission_decision = str(admission.get("decision", ""))
    if admission_decision not in ALLOWED_ADMISSION_DECISIONS:
        violations.append(_violation("admission.decision", "Admission decision is missing or invalid."))

    stances = _as_dict_list(run.get("stances", []), "stances", violations)
    stance_ids = [str(item.get("stance_id", "")) for item in stances if item.get("stance_id")]
    duplicate_stance_ids = sorted({sid for sid in stance_ids if stance_ids.count(sid) > 1})
    for sid in duplicate_stance_ids:
        violations.append(_violation("stances", f"Duplicate stance_id: {sid}"))

    if admission_decision == "accept_for_debate" and len(stances) < 2:
        violations.append(_violation("stances", "Accepted Debate runs require at least two valid stances."))
    if admission_decision != "accept_for_debate" and run.get("worker_creation_requests"):
        violations.append(_violation("worker_creation_requests", "Rejected or context-request Debate runs must not create Workers."))

    for item in stances:
        for key in ("stance_id", "claim", "scope", "assumptions"):
            if not item.get(key):
                violations.append(_violation(f"stances.{item.get('stance_id', '<missing>')}.{key}", "Stance packet missing required field."))

    worker_creations = _as_dict_list(run.get("worker_creation_requests", []), "worker_creation_requests", violations)
    worker_outputs = _as_dict_list(run.get("worker_outputs", []), "worker_outputs", violations)

    creation_by_stance: dict[str, dict[str, Any]] = {}
    for creation in worker_creations:
        stance_id = str(creation.get("stance_id", ""))
        if not stance_id:
            violations.append(_violation("worker_creation_requests.stance_id", "Worker creation request missing stance_id."))
            continue
        if stance_id in creation_by_stance:
            violations.append(_violation("worker_creation_requests", f"More than one Worker creation request for stance {stance_id}."))
        creation_by_stance[stance_id] = creation
        if stance_id not in stance_ids:
            violations.append(_violation("worker_creation_requests.stance_id", f"Worker creation references unknown stance {stance_id}."))
        if not _is_skill_ref(_ref(creation.get("worker_skill_ref")), WORKER_SKILL_ID, WORKER_SKILL_VERSION):
            violations.append(_violation("worker_creation_requests.worker_skill_ref", f"Worker creation for stance {stance_id} lacks DEBATE_WORKER_OPERATIONAL_SKILL v0.1."))
        if creation.get("role_id") not in {None, "debate_worker"}:
            violations.append(_violation("worker_creation_requests.role_id", "Worker creation role_id must be debate_worker."))
        if creation.get("stance_bound") is False or creation.get("one_stance_only") is False:
            violations.append(_violation("worker_creation_requests.stance_bound", "Worker creation must be stance-bound and one-stance-only."))

    if admission_decision == "accept_for_debate":
        for stance_id in stance_ids:
            if stance_id not in creation_by_stance:
                violations.append(_violation("worker_creation_requests", f"Missing Worker creation for stance {stance_id}."))

    output_by_stance: dict[str, dict[str, Any]] = {}
    for output in worker_outputs:
        stance_id = str(output.get("stance_id", ""))
        if not stance_id:
            violations.append(_violation("worker_outputs.stance_id", "Worker output missing stance_id."))
            continue
        output_by_stance[stance_id] = output
        _check_worker_output(output, stance_ids=stance_ids, violations=violations)

    if admission_decision == "accept_for_debate":
        for stance_id in stance_ids:
            if stance_id not in output_by_stance:
                violations.append(_violation("worker_outputs", f"Missing Worker output for stance {stance_id}."))

    adjudicator = run.get("adjudicator_causal_state")
    adjudicator_verified = isinstance(adjudicator, dict)
    if admission_decision == "accept_for_debate" and not adjudicator_verified:
        violations.append(_violation("adjudicator_causal_state", "Accepted Debate run requires adjudicator causal state."))
    if isinstance(adjudicator, dict):
        for key in ("candidate_positions", "route_priority", "expand_priority", "stop_reason", "developer_decision_required"):
            if key not in adjudicator:
                violations.append(_violation(f"adjudicator_causal_state.{key}", "Adjudicator causal state missing required field."))

    final_report = run.get("final_report") if isinstance(run.get("final_report"), dict) else {}
    decision = str(final_report.get("adjudication_decision") or final_report.get("decision") or "")
    if admission_decision == "accept_for_debate" and decision not in ALLOWED_ADJUDICATION_DECISIONS:
        violations.append(_violation("final_report.adjudication_decision", "Final adjudication decision is missing or invalid."))

    if isinstance(adjudicator, dict) and adjudicator.get("developer_decision_required") is True:
        if final_report.get("developer_decision_required") is not True:
            violations.append(_violation("final_report.developer_decision_required", "Causal equipoise/developer decision must be preserved in final report."))
        if not final_report.get("balanced_positions"):
            violations.append(_violation("final_report.balanced_positions", "Developer decision required must preserve balanced positions."))

    causal_result = final_report.get("causal_result")
    if admission_decision == "accept_for_debate" and not isinstance(causal_result, dict):
        violations.append(_violation("final_report.causal_result", "Final report must include causal_result."))
    if isinstance(causal_result, dict):
        for key in ("statement", "why", "evidence", "scope", "assumptions", "next_action", "status"):
            if key not in causal_result or _is_missing(causal_result.get(key)):
                violations.append(_violation(f"final_report.causal_result.{key}", "Causal result missing required field."))

    causal_chain = final_report.get("causal_chain")
    if admission_decision == "accept_for_debate" and not isinstance(causal_chain, dict):
        violations.append(_violation("final_report.causal_chain", "Final report must include causal_chain; causal_result alone is insufficient."))
    if isinstance(causal_chain, dict):
        _check_causal_chain(causal_chain, violations)

    package_manifest = run.get("causal_package") or run.get("package_manifest") or {}
    package_files = set(_string_list(package_manifest.get("files", []))) if isinstance(package_manifest, dict) else set()
    causal_package_verified = False
    if admission_decision == "accept_for_debate":
        missing_files = sorted(REQUIRED_PACKAGE_FILES - package_files)
        if missing_files:
            violations.append(_violation("causal_package.files", "Causal package missing required file(s): " + ", ".join(missing_files)))
        has_worker_state = any(item.startswith("worker_states/") for item in package_files)
        has_worker_proof = any(item.startswith("worker_proofs/") for item in package_files)
        if not has_worker_state:
            violations.append(_violation("causal_package.files", "Causal package must include worker_states/<worker_id>.json."))
        if not has_worker_proof:
            violations.append(_violation("causal_package.files", "Causal package must include worker_proofs/<worker_id>_proof.json."))
        causal_package_verified = not missing_files and has_worker_state and has_worker_proof

    cleanup = run.get("cleanup") if isinstance(run.get("cleanup"), dict) else {}
    if admission_decision == "accept_for_debate" and cleanup.get("temporary_workers_released_or_marked_for_cleanup") is not True:
        violations.append(_violation("cleanup.temporary_workers_released_or_marked_for_cleanup", "Temporary Workers must be released or marked for cleanup."))

    boundaries = run.get("boundaries") if isinstance(run.get("boundaries"), dict) else {}
    for field in FORBIDDEN_TRUE_FIELDS:
        if run.get(field) is True or final_report.get(field) is True or boundaries.get(field) is True:
            violations.append(_violation(field, f"{field} must remain false."))

    status = "validated" if not violations else "rejected"
    return DebateSkillValidationResult(
        debate_skill_validation_result_id=f"debate-skill-{uuid4().hex}",
        phase=PHASE,
        status=status,
        decision="accepted_debate_role_skill_enforcement" if status == "validated" else "rejected",
        reason="Validated Debate Leader/Worker role-bound operational skill enforcement." if status == "validated" else "Debate role-bound skill validation failed.",
        leader_skill_ref={"skill_id": LEADER_SKILL_ID, "skill_version": LEADER_SKILL_VERSION},
        worker_skill_ref={"skill_id": WORKER_SKILL_ID, "skill_version": WORKER_SKILL_VERSION},
        stance_count=len(stances),
        worker_creation_count=len(worker_creations),
        worker_output_count=len(worker_outputs),
        violations=violations,
        leader_skill_installed=_is_skill_ref(leader_ref, LEADER_SKILL_ID, LEADER_SKILL_VERSION),
        worker_skill_installation_verified=not any(v["field"].startswith("worker_creation_requests") for v in violations),
        worker_skill_outputs_verified=not any(v["field"].startswith("worker_outputs") for v in violations),
        adjudicator_causal_state_verified=adjudicator_verified and not any(v["field"].startswith("adjudicator_causal_state") for v in violations),
        causal_package_verified=causal_package_verified,
        global_causal_truth_merge_performed=False,
        production_store_write_performed=False,
        remote_push_performed=False,
        pull_request_created=False,
        remote_merge_performed=False,
        release_performed=False,
    )



def _check_causal_chain(causal_chain: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    required_fields = (
        "chain_id",
        "source_request_id",
        "decision_problem",
        "selected_stance_id",
        "nodes",
        "edges",
        "selected_path",
        "rejected_paths",
        "unresolved_questions",
        "invalidation_entrypoints",
    )
    for key in required_fields:
        if key not in causal_chain:
            violations.append(_violation(f"final_report.causal_chain.{key}", "Causal chain missing required field."))

    for key in ("chain_id", "source_request_id", "decision_problem", "selected_stance_id", "nodes", "edges", "selected_path"):
        if key in causal_chain and _is_missing(causal_chain.get(key)):
            violations.append(_violation(f"final_report.causal_chain.{key}", "Causal chain required field must not be empty."))

    nodes = causal_chain.get("nodes")
    edges = causal_chain.get("edges")
    if isinstance(nodes, list):
        node_ids: set[str] = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                violations.append(_violation(f"final_report.causal_chain.nodes[{index}]", "Causal chain node must be an object."))
                continue
            for key in ("id", "type", "statement", "why", "evidence_refs", "assumptions", "scope", "confidence"):
                if key not in node or _is_missing(node.get(key)):
                    violations.append(_violation(f"final_report.causal_chain.nodes[{index}].{key}", "Causal chain node missing required field."))
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                if node_id in node_ids:
                    violations.append(_violation(f"final_report.causal_chain.nodes[{index}].id", f"Duplicate causal_chain node id: {node_id}"))
                node_ids.add(node_id)
    else:
        node_ids = set()

    if isinstance(edges, list):
        edge_ids: set[str] = set()
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                violations.append(_violation(f"final_report.causal_chain.edges[{index}]", "Causal chain edge must be an object."))
                continue
            for key in ("id", "from", "to", "relation", "why"):
                if key not in edge or _is_missing(edge.get(key)):
                    violations.append(_violation(f"final_report.causal_chain.edges[{index}].{key}", "Causal chain edge missing required field."))
            edge_id = edge.get("id")
            if isinstance(edge_id, str) and edge_id:
                if edge_id in edge_ids:
                    violations.append(_violation(f"final_report.causal_chain.edges[{index}].id", f"Duplicate causal_chain edge id: {edge_id}"))
                edge_ids.add(edge_id)
            if node_ids:
                if edge.get("from") not in node_ids:
                    violations.append(_violation(f"final_report.causal_chain.edges[{index}].from", "Causal chain edge source must reference an existing node."))
                if edge.get("to") not in node_ids:
                    violations.append(_violation(f"final_report.causal_chain.edges[{index}].to", "Causal chain edge target must reference an existing node."))
    else:
        edge_ids = set()

    selected_path = causal_chain.get("selected_path")
    if isinstance(selected_path, list) and node_ids:
        for node_id in selected_path:
            if node_id not in node_ids:
                violations.append(_violation("final_report.causal_chain.selected_path", f"selected_path references missing node: {node_id}"))

    rejected_paths = causal_chain.get("rejected_paths")
    if isinstance(rejected_paths, list):
        for index, path in enumerate(rejected_paths):
            if not isinstance(path, dict):
                violations.append(_violation(f"final_report.causal_chain.rejected_paths[{index}]", "Rejected path must be an object."))
                continue
            if not path.get("stance_id"):
                violations.append(_violation(f"final_report.causal_chain.rejected_paths[{index}].stance_id", "Rejected path requires stance_id."))
            for node_id in _string_list(path.get("rejection_node_ids", [])):
                if node_ids and node_id not in node_ids:
                    violations.append(_violation(f"final_report.causal_chain.rejected_paths[{index}].rejection_node_ids", f"Rejected path references missing node: {node_id}"))
            for edge_id in _string_list(path.get("decisive_edge_ids", [])):
                if edge_ids and edge_id not in edge_ids:
                    violations.append(_violation(f"final_report.causal_chain.rejected_paths[{index}].decisive_edge_ids", f"Rejected path references missing edge: {edge_id}"))

    entrypoints = causal_chain.get("invalidation_entrypoints")
    if isinstance(entrypoints, list):
        for index, entrypoint in enumerate(entrypoints):
            if not isinstance(entrypoint, dict):
                violations.append(_violation(f"final_report.causal_chain.invalidation_entrypoints[{index}]", "Invalidation entrypoint must be an object."))
                continue
            condition_node_id = entrypoint.get("condition_node_id")
            if node_ids and condition_node_id not in node_ids:
                violations.append(_violation(f"final_report.causal_chain.invalidation_entrypoints[{index}].condition_node_id", "Invalidation entrypoint must reference an existing node."))
            for node_id in _string_list(entrypoint.get("reopens_node_ids", [])):
                if node_ids and node_id not in node_ids:
                    violations.append(_violation(f"final_report.causal_chain.invalidation_entrypoints[{index}].reopens_node_ids", f"Invalidation entrypoint references missing node: {node_id}"))

def _check_worker_output(output: dict[str, Any], *, stance_ids: list[str], violations: list[dict[str, Any]]) -> None:
    stance_id = str(output.get("stance_id", ""))
    if stance_id not in stance_ids:
        violations.append(_violation("worker_outputs.stance_id", f"Worker output references unknown stance {stance_id}."))
    if not _is_skill_ref(_ref(output.get("skill_ref")), WORKER_SKILL_ID, WORKER_SKILL_VERSION):
        violations.append(_violation("worker_outputs.skill_ref", f"Worker output for stance {stance_id} lacks DEBATE_WORKER_OPERATIONAL_SKILL v0.1."))
    if output.get("skill_received") is not True or output.get("skill_applied") is not True:
        violations.append(_violation("worker_outputs.skill_received", "Worker output must prove skill_received=true and skill_applied=true."))
    if output.get("stance_binding_verified") is not True or output.get("exactly_one_stance") is not True:
        violations.append(_violation("worker_outputs.stance_binding", "Worker output must verify exactly one stance binding."))
    if output.get("final_adjudication_attempted") is not False:
        violations.append(_violation("worker_outputs.final_adjudication_attempted", "Worker must not attempt final adjudication."))
    if output.get("global_truth_claimed") is not False:
        violations.append(_violation("worker_outputs.global_truth_claimed", "Worker must not claim global truth."))
    if output.get("persistent_identity_requested") is True:
        violations.append(_violation("worker_outputs.persistent_identity_requested", "Worker must not request persistent identity by default."))

    state = output.get("worker_local_causal_state")
    if not isinstance(state, dict):
        violations.append(_violation("worker_outputs.worker_local_causal_state", "Worker output must include worker_local_causal_state."))
        return
    for key in ("stance_id", "claim", "why", "evidence", "scope", "assumptions", "route_priority", "expand_priority", "status"):
        if key not in state or _is_missing(state.get(key)):
            violations.append(_violation(f"worker_outputs.worker_local_causal_state.{key}", "Worker local causal state missing required field."))
    if state.get("stance_id") != stance_id:
        violations.append(_violation("worker_outputs.worker_local_causal_state.stance_id", "Worker local causal state stance_id must match output stance_id."))


def _check_skill_file(path: str | Path, *, skill_id: str, skill_version: str, field: str, violations: list[dict[str, Any]]) -> None:
    p = Path(path)
    if not p.is_file():
        violations.append(_violation(field, f"Skill file not found: {p}"))
        return
    text = p.read_text(encoding="utf-8")
    if f"skill_id: {skill_id}" not in text:
        violations.append(_violation(field, f"Skill file missing skill_id {skill_id}."))
    if f"skill_version: {skill_version}" not in text:
        violations.append(_violation(field, f"Skill file missing skill_version {skill_version}."))


def _is_skill_ref(ref: dict[str, Any], skill_id: str, skill_version: str) -> bool:
    return ref.get("skill_id") == skill_id and ref.get("skill_version") == skill_version


def _ref(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_dict_list(value: Any, field: str, violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        violations.append(_violation(field, f"{field} must be a list."))
        return []
    output = []
    for item in value:
        if isinstance(item, dict):
            output.append(dict(item))
        else:
            violations.append(_violation(field, f"{field} contains a non-object item."))
    return output


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _violation(field: str, reason: str) -> dict[str, Any]:
    return {"field": field, "reason": reason}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Aegis Debate Leader/Worker operational skill enforcement.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate one Debate skill run JSON artifact.")
    validate.add_argument("--run", required=True, help="Path to Debate skill run JSON.")
    validate.add_argument("--leader-skill", help="Optional path to DEBATE_LEADER_OPERATIONAL_SKILL.md.")
    validate.add_argument("--worker-skill", help="Optional path to DEBATE_WORKER_OPERATIONAL_SKILL.md.")
    validate.add_argument("--output", help="Optional output path for validation result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "validate":
        result = validate_debate_skill_run_file(
            args.run,
            leader_skill_path=args.leader_skill,
            worker_skill_path=args.worker_skill,
        ).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
