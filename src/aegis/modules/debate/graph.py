"""LangGraph builder and deterministic DebateSubgraph runtime."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from aegis.models import utc_now
from aegis.modules.debate.admission import (
    admit_stances,
    analyze_stance_relations,
    validate_hard_constraints,
)
from aegis.modules.debate.artifacts import DebateArtifactWriter
from aegis.modules.debate.candidate_writer import (
    CausalCandidateWriteError,
    build_update_candidate,
    write_causal_store_candidate,
)
from aegis.modules.debate.context import build_context_bundle
from aegis.modules.debate.errors import DebateErrorCode, DebateRuntimeError
from aegis.modules.debate.leader import (
    assess_leader_round,
    select_leader_candidate_stance,
)
from aegis.modules.debate.merge import build_causal_candidate_nodes
from aegis.modules.debate.models import (
    ConvergenceSignals,
    DebateContextBundle,
    DebateErrorRecord,
    DebateInputPackage,
    DebateOutputPackage,
    DebateRunManifest,
    DebateRuntimeConfig,
    DebateStatus,
    HardConstraintValidation,
    LeaderDecision,
    LeaderRoundAssessment,
    ProjectStoreBinding,
    StanceAdmissionRecord,
    StanceAdmissionStatus,
    StanceRelationKind,
    StanceRelationRecord,
    WorkerAttack,
    WorkerCausalChainDelta,
    WorkerProtocolViolation,
    WorkerSelfAudit,
    WorkerTurnPacket,
)
from aegis.modules.debate.store_binding import bind_project_stores
from aegis.modules.debate.worker import detect_worker_protocol_violations


_DEBATE_LOCK_GUARD = Lock()
_DEBATE_RUN_LOCKS: dict[str, Lock] = {}


class DebateGraphState(TypedDict, total=False):
    """JSON-safe state accepted by the standalone DebateSubgraph."""

    input_package: dict[str, Any]
    config: dict[str, Any]
    package: dict[str, Any]
    runtime_config: dict[str, Any]
    debate_id: str
    binding: dict[str, Any]
    manifest: dict[str, Any]
    context: dict[str, Any]
    constraint_validations: list[dict[str, Any]]
    admissions: list[dict[str, Any]]
    admitted_ids: list[str]
    relations: list[dict[str, Any]]
    contested_relations: list[dict[str, Any]]
    packets: list[dict[str, Any]]
    violations: list[dict[str, Any]]
    leader_assessment: dict[str, Any]
    stable_selected_rounds: int
    output_package: dict[str, Any]


def build_debate_subgraph(checkpointer: SqliteSaver | None = None):
    """Build the standalone DebateSubgraph with explicit workflow stages."""

    builder = StateGraph(DebateGraphState)
    builder.add_node("initialize_run", _initialize_run_node)
    builder.add_node("build_context", _build_context_node)
    builder.add_node("admit_stances", _admit_stances_node)
    builder.add_node("run_worker_rounds", _run_worker_rounds_node)
    builder.add_node("write_candidate", _write_candidate_node)
    builder.add_edge(START, "initialize_run")
    builder.add_edge("initialize_run", "build_context")
    builder.add_edge("build_context", "admit_stances")
    builder.add_edge("admit_stances", "run_worker_rounds")
    builder.add_edge("run_worker_rounds", "write_candidate")
    builder.add_edge("write_candidate", END)
    return builder.compile(checkpointer=checkpointer)


def run_deterministic_debate(
    package: DebateInputPackage,
    config: DebateRuntimeConfig | None = None,
) -> DebateOutputPackage:
    """Run deterministic DebateSubgraph closure for CI and local validation."""

    runtime_config = config or DebateRuntimeConfig()
    input_hash = _input_hash(package)
    debate_id = _debate_id(package, input_hash)
    with _debate_run_lock(debate_id):
        state = build_debate_subgraph().invoke(
            {
                "input_package": package.model_dump(mode="json"),
                "config": runtime_config.model_dump(mode="json"),
            }
        )
    return DebateOutputPackage.model_validate(state["output_package"])


class DebateRuntime:
    """Checkpointed standalone DebateSubgraph runtime."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        runtime_dir = self.project_root / ".aegis" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            runtime_dir / "debate_checkpoints.sqlite3",
            check_same_thread=False,
        )
        self.checkpointer = SqliteSaver(self._conn)
        if hasattr(self.checkpointer, "setup"):
            self.checkpointer.setup()
        self.graph = build_debate_subgraph(checkpointer=self.checkpointer)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DebateRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def run(
        self,
        package: DebateInputPackage,
        config: DebateRuntimeConfig | None = None,
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        actual_thread_id = thread_id or f"debate-thread-{uuid4().hex[:12]}"
        runtime_config = config or DebateRuntimeConfig()
        graph_config = {"configurable": {"thread_id": actual_thread_id}}
        state = {
            "input_package": package.model_dump(mode="json"),
            "config": runtime_config.model_dump(mode="json"),
        }
        result = self.graph.invoke(state, config=graph_config)
        return {
            "thread_id": actual_thread_id,
            "result": DebateOutputPackage.model_validate(
                result["output_package"]
            ),
        }

    def resume(self, thread_id: str) -> dict[str, Any]:
        snapshot = self.inspect(thread_id)
        output = snapshot["values"].get("output_package")
        if output is None:
            raise DebateRuntimeError(
                DebateErrorCode.LEADER_DECISION_INVALID,
                "debate checkpoint has no completed output package",
                context={"thread_id": thread_id, "next": snapshot["next"]},
            )
        return {
            "thread_id": thread_id,
            "result": DebateOutputPackage.model_validate(output),
        }

    def inspect(self, thread_id: str) -> dict[str, Any]:
        graph_config = {"configurable": {"thread_id": thread_id}}
        snapshot = self.graph.get_state(graph_config)
        return {
            "thread_id": thread_id,
            "values": snapshot.values,
            "next": snapshot.next,
            "metadata": snapshot.metadata,
        }


def _initialize_run_node(state: DebateGraphState) -> DebateGraphState:
    package = DebateInputPackage.model_validate(state["input_package"])
    config = DebateRuntimeConfig.model_validate(state.get("config", {}))
    input_hash = _input_hash(package)
    debate_id = _debate_id(package, input_hash)
    binding = bind_project_stores(
        project_root=package.project_root,
        debate_id=debate_id,
    )
    writer = DebateArtifactWriter(binding, config)
    input_ref = writer.write_json(writer.artifact_path("input_package.json"), package)
    manifest = DebateRunManifest(
        debate_id=debate_id,
        request_id=package.request_id,
        artifact_root=binding.debate_candidate_root,
        input_hash=input_hash,
        input_package_ref=str(input_ref),
    )
    _write_manifest(writer, manifest)
    return {
        "package": package.model_dump(mode="json"),
        "runtime_config": config.model_dump(mode="json"),
        "debate_id": debate_id,
        "binding": binding.model_dump(mode="json"),
        "manifest": manifest.model_dump(mode="json"),
    }


def _build_context_node(state: DebateGraphState) -> DebateGraphState:
    if "output_package" in state:
        return {}
    package, config, binding, writer, manifest = _runtime_parts(state)
    context = build_context_bundle(package, binding, config)
    context_ref = writer.write_json(writer.artifact_path("context_bundle.json"), context)
    manifest.context_bundle_ref = str(context_ref)
    manifest.context_bundle_hash = _hash_json(context.model_dump(mode="json"))
    gate = _context_gate(context)
    if gate is not None:
        status, code, message, gate_context = gate
        output = _status_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            status=status,
            code=code,
            message=message,
            context=gate_context,
        )
        return _state_with_output(output, manifest)
    return {
        "context": context.model_dump(mode="json"),
        "manifest": _manifest_dict(manifest),
    }


def _admit_stances_node(state: DebateGraphState) -> DebateGraphState:
    if "output_package" in state:
        return {}
    package, _config, _binding, writer, manifest = _runtime_parts(state)
    context = DebateContextBundle.model_validate(state["context"])
    validations = validate_hard_constraints(package, context)
    writer.write_json(
        writer.artifact_path("hard_constraint_validations.json"),
        validations,
    )
    unsupported = [
        validation
        for validation in validations
        if validation.status.value == "unsupported"
    ]
    if unsupported:
        output = _blocked_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.UNSUPPORTED_HARD_CONSTRAINT,
            message="One or more claimed hard constraints lack objective support.",
            context={"constraint_ids": [item.constraint_id for item in unsupported]},
        )
        return _state_with_output(output, manifest)

    normalized_statements = {
        _normalize_material_text(position.statement)
        for position in package.candidate_positions
    }
    if len(package.candidate_positions) >= 2 and len(normalized_statements) == 1:
        output = _debate_not_required_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.INSUFFICIENT_CONTESTED_STANCES,
            message="Candidate stances are materially duplicate.",
            context={
                "candidate_stance_ids": [
                    position.stance_id
                    for position in package.candidate_positions
                ]
            },
        )
        return _state_with_output(output, manifest)

    admissions = admit_stances(package, context, validations)
    admissions_ref = writer.write_json(
        writer.artifact_path("stance_admissions.json"),
        admissions,
    )
    manifest.stance_admissions_ref = str(admissions_ref)
    manifest.stance_admissions_hash = _hash_json(
        [record.model_dump(mode="json") for record in admissions]
    )
    admitted_ids = [
        record.stance_id
        for record in admissions
        if record.status == StanceAdmissionStatus.ADMITTED
    ]
    if len(admitted_ids) < 2:
        output = _debate_not_required_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.INSUFFICIENT_DEFENSIBLE_STANCES,
            message="Fewer than two defensible stances were admitted.",
            context={"admitted_stance_ids": admitted_ids},
        )
        return _state_with_output(output, manifest)

    relations = analyze_stance_relations(package, admissions, context)
    relations_ref = writer.write_json(
        writer.artifact_path("stance_relations.json"),
        relations,
    )
    manifest.stance_relations_ref = str(relations_ref)
    contested = [
        relation
        for relation in relations
        if relation.relation == StanceRelationKind.MUTUALLY_EXCLUSIVE
    ]
    if not contested:
        output = _debate_not_required_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.INSUFFICIENT_CONTESTED_STANCES,
            message="Admitted stances do not contain a material conflict.",
            context={"admitted_stance_ids": admitted_ids},
        )
        return _state_with_output(output, manifest)
    return {
        "constraint_validations": [
            item.model_dump(mode="json") for item in validations
        ],
        "admissions": [item.model_dump(mode="json") for item in admissions],
        "admitted_ids": admitted_ids,
        "relations": [item.model_dump(mode="json") for item in relations],
        "contested_relations": [item.model_dump(mode="json") for item in contested],
        "manifest": _manifest_dict(manifest),
    }


def _run_worker_rounds_node(state: DebateGraphState) -> DebateGraphState:
    if "output_package" in state:
        return {}
    package, config, _binding, writer, manifest = _runtime_parts(state)
    admissions = [
        StanceAdmissionRecord.model_validate(item)
        for item in state["admissions"]
    ]
    validations = [
        HardConstraintValidation.model_validate(item)
        for item in state["constraint_validations"]
    ]
    contested = [
        StanceRelationRecord.model_validate(item)
        for item in state["contested_relations"]
    ]
    admitted_ids = state["admitted_ids"]
    packets: list[WorkerTurnPacket] = []
    violations: list[WorkerProtocolViolation] = []
    assessment: LeaderRoundAssessment | None = None
    stable_selected_rounds = 0
    previous_selected: str | None = None

    for round_index in range(1, config.max_rounds + 1):
        round_packets = _build_worker_packets(
            package,
            admitted_ids,
            round_index=round_index,
            previous_selected_stance_id=previous_selected,
        )
        packets.extend(round_packets)
        round_violations = [
            violation
            for packet in round_packets
            for violation in detect_worker_protocol_violations(packet)
        ]
        violations.extend(round_violations)
        selected = select_leader_candidate_stance(
            active_stance_ids=admitted_ids,
            packets=round_packets,
            admission_records=admissions,
            hard_constraint_validations=validations,
        )
        if selected is not None and selected == previous_selected:
            stable_selected_rounds += 1
        else:
            previous_selected = selected
            stable_selected_rounds = 1 if selected is not None else 0
        dominated = [
            stance_id
            for stance_id in admitted_ids
            if selected is not None and stance_id != selected
        ]
        stable_enough = (
            selected is not None
            and stable_selected_rounds >= config.stable_selected_stance_round_threshold
        )
        assessment = assess_leader_round(
            round_index=round_index,
            active_stance_ids=[selected, *dominated] if selected else admitted_ids,
            dominated_stances=dominated if stable_enough else [],
            violations=round_violations,
            signals=ConvergenceSignals(
                undefeated_stance_count=1 if stable_enough else len(admitted_ids),
                unresolved_conflict_count=0 if stable_enough else len(contested),
                new_material_argument_count=0 if stable_enough else len(round_packets),
                decisive_constraint_count=1 if stable_enough else 0,
                stable_selected_stance_rounds=stable_selected_rounds,
                worker_protocol_violation_count=len(round_violations),
            ),
        )
        if assessment.decision == LeaderDecision.STOP_CONVERGED:
            break
        if assessment.decision == LeaderDecision.REQUEST_WORKER_REPAIR:
            if round_index <= config.max_worker_repair_attempts:
                continue
            break
        if assessment.decision == LeaderDecision.ABORT_PROTOCOL_VIOLATION:
            break

    if assessment is None:
        output = _blocked_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.LEADER_DECISION_INVALID,
            message="Leader did not assess any debate round.",
            context={},
        )
        return _state_with_output(output, manifest)

    worker_turns_ref = writer.write_json(writer.artifact_path("worker_turns.json"), packets)
    writer.write_json(writer.artifact_path("worker_violations.json"), violations)
    assessment_ref = writer.write_json(
        writer.artifact_path("leader_assessment.json"),
        assessment,
    )
    manifest.worker_turns_ref = str(worker_turns_ref)
    manifest.leader_assessment_ref = str(assessment_ref)

    if assessment.selected_stance_id is None:
        if assessment.decision == LeaderDecision.CONTINUE_DEBATE:
            status = (
                DebateStatus.SCOPE_LIMITED
                if config.allow_scope_limited_verdict_on_max_rounds
                else DebateStatus.NON_CONVERGENT
            )
            output = _status_output(
                debate_id=state["debate_id"],
                package=package,
                writer=writer,
                manifest=manifest,
                status=status,
                code=DebateErrorCode.DEBATE_NON_CONVERGENT,
                message="Debate reached max_rounds without stable convergence.",
                context={
                    "max_rounds": config.max_rounds,
                    "stable_selected_stance_rounds": stable_selected_rounds,
                    "required_stable_rounds": config.stable_selected_stance_round_threshold,
                },
            )
            return _state_with_output(output, manifest)
        output = _blocked_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.LEADER_DECISION_INVALID,
            message="Leader did not produce a selected stance.",
            context={"decision": assessment.decision.value},
        )
        return _state_with_output(output, manifest)

    return {
        "packets": [item.model_dump(mode="json") for item in packets],
        "violations": [item.model_dump(mode="json") for item in violations],
        "leader_assessment": assessment.model_dump(mode="json"),
        "stable_selected_rounds": stable_selected_rounds,
        "manifest": _manifest_dict(manifest),
    }


def _write_candidate_node(state: DebateGraphState) -> DebateGraphState:
    if "output_package" in state:
        return {}
    package, _config, binding, writer, manifest = _runtime_parts(state)
    assessment = LeaderRoundAssessment.model_validate(state["leader_assessment"])
    packets = [
        WorkerTurnPacket.model_validate(item)
        for item in state["packets"]
    ]
    violations = [
        WorkerProtocolViolation.model_validate(item)
        for item in state["violations"]
    ]
    selected = assessment.selected_stance_id
    if selected is None:
        output = _blocked_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.LEADER_DECISION_INVALID,
            message="Leader did not produce a selected stance.",
            context={"decision": assessment.decision.value},
        )
        return _state_with_output(output, manifest)

    rejected = [stance_id for stance_id in state["admitted_ids"] if stance_id != selected]
    nodes = build_causal_candidate_nodes(
        debate_id=state["debate_id"],
        packets=packets,
        violations=violations,
    )
    candidate = build_update_candidate(
        package=package,
        debate_id=state["debate_id"],
        selected_stance_id=selected,
        rejected_stance_ids=rejected,
        nodes=nodes,
    )
    candidate_payload = _external_candidate_payload(candidate)
    candidate_ref = writer.write_json(
        writer.artifact_path("causal_candidate.json"),
        candidate_payload,
    )
    manifest.causal_candidate_ref = str(candidate_ref)
    manifest.causal_candidate_hash = _hash_json(candidate_payload)

    try:
        write_result = write_causal_store_candidate(
            binding=binding,
            artifact_ref=str(candidate_ref),
            candidate=candidate,
        )
    except CausalCandidateWriteError as exc:
        write_result_ref = writer.write_json(
            writer.artifact_path("causal_write_result.json"),
            exc.result,
        )
        manifest.causal_write_result_ref = str(write_result_ref)
        output = _blocked_output(
            debate_id=state["debate_id"],
            package=package,
            writer=writer,
            manifest=manifest,
            code=DebateErrorCode.CAUSAL_CANDIDATE_WRITE_FAILED,
            message="Causal candidate write failed; Debate cannot close.",
            context=exc.result.model_dump(mode="json"),
        )
        return _state_with_output(output, manifest)

    write_result_ref = writer.write_json(
        writer.artifact_path("causal_write_result.json"),
        write_result,
    )
    manifest.causal_write_result_ref = str(write_result_ref)
    final_report_ref = writer.write_json(
        writer.artifact_path("final_report.json"),
        {
            "decision_problem": package.decision_problem,
            "selected_stance_id": selected,
            "rejected_stance_ids": rejected,
            "causal_candidate_ref": str(candidate_ref),
            "causal_store_write": write_result.model_dump(mode="json"),
            "status": "causal_candidate",
        },
    )
    manifest.final_report_ref = str(final_report_ref)
    output = DebateOutputPackage(
        debate_id=state["debate_id"],
        request_id=package.request_id,
        status=DebateStatus.COMPLETED,
        decision_type=package.required_outcome,
        selected_stance_id=selected,
        rejected_stance_ids=rejected,
        review_summary=(
            "Debate closed with a causal_candidate. The selected stance is "
            f"{selected}; rejected stances are {', '.join(rejected) or 'none'}."
        ),
        causal_candidate_ref=str(candidate_ref),
        causal_store_candidate_id=candidate.candidate_id,
        final_report_ref=str(final_report_ref),
        manifest_ref=str(writer.artifact_path("manifest.json")),
        artifact_root=str(binding.debate_candidate_root),
    )
    output_ref = writer.write_json(writer.artifact_path("output_package.json"), output)
    manifest.output_package_ref = str(output_ref)
    manifest.run_status = DebateStatus.COMPLETED.value
    _write_manifest(writer, manifest)
    return _state_with_output(output, manifest)


def _runtime_parts(
    state: DebateGraphState,
) -> tuple[
    DebateInputPackage,
    DebateRuntimeConfig,
    ProjectStoreBinding,
    DebateArtifactWriter,
    DebateRunManifest,
]:
    package = DebateInputPackage.model_validate(state["package"])
    config = DebateRuntimeConfig.model_validate(state["runtime_config"])
    binding = ProjectStoreBinding.model_validate(state["binding"])
    writer = DebateArtifactWriter(binding, config)
    manifest = DebateRunManifest.model_validate(state["manifest"])
    return package, config, binding, writer, manifest


def _state_with_output(
    output: DebateOutputPackage,
    manifest: DebateRunManifest,
) -> DebateGraphState:
    return {
        "output_package": output.model_dump(mode="json"),
        "manifest": _manifest_dict(manifest),
    }


def _manifest_dict(manifest: DebateRunManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json")


def _build_worker_packets(
    package: DebateInputPackage,
    admitted_ids: list[str],
    *,
    round_index: int,
    previous_selected_stance_id: str | None,
) -> list[WorkerTurnPacket]:
    positions = {
        position.stance_id: position for position in package.candidate_positions
    }
    packets: list[WorkerTurnPacket] = []
    for stance_id in admitted_ids:
        position = positions[stance_id]
        opponent_ids = [item for item in admitted_ids if item != stance_id]
        defense = position.summary
        concessions: list[dict[str, str]] = []
        if round_index > 1:
            defense = (
                f"{position.summary}; responds to round {round_index - 1} "
                "leader assessment and remaining attacks."
            )
        if (
            round_index > 1
            and previous_selected_stance_id is not None
            and stance_id != previous_selected_stance_id
        ):
            concessions.append(
                {
                    "target_ref": f"{stance_id}-selection-support",
                    "why_conceded": (
                        f"{previous_selected_stance_id} has stronger admitted "
                        "evidence in the current debate package."
                    ),
                    "defeating_ref": (
                        f"round-{round_index - 1}-{previous_selected_stance_id}"
                    ),
                }
            )
        attacks = [
            WorkerAttack(
                target_ref=opponent_id,
                claim=f"{stance_id} challenges {opponent_id}.",
                why=(
                    "The alternative introduces different trade-offs for the "
                    "same decision problem and must be justified by evidence."
                ),
                evidence_refs=position.source_artifact_refs,
            )
            for opponent_id in opponent_ids
            if round_index == 1 or stance_id == previous_selected_stance_id
        ]
        packets.append(
            WorkerTurnPacket(
                turn_id=f"round-{round_index}-{stance_id}",
                round_index=round_index,
                worker_id=f"worker-{stance_id}",
                stance_id=stance_id,
                observed_canonical_transcript_ref=(
                    f"canonical-transcript-round-{round_index}"
                ),
                defense=defense,
                attacks=attacks,
                concessions=concessions,
                chain_delta=WorkerCausalChainDelta(
                    added_local_nodes=[
                        {
                            "local_node_ref": f"{stance_id}-selection-support",
                            "statement": position.statement,
                            "semantic_summary": position.summary,
                            "semantic_keys": _semantic_keys(position.summary),
                            "evidence_refs": position.source_artifact_refs,
                            "conditions": [
                                "No stronger competing stance evidence exists."
                            ],
                            "scope": package.decision_problem,
                            "confidence": "medium",
                            "assumptions": [
                                "The cited project evidence remains valid.",
                                "The decision scope does not materially expand.",
                            ],
                            "invalidation_conditions": [
                                "New project evidence defeats this stance.",
                                "A rejected alternative gains decisive evidence.",
                            ],
                        }
                    ],
                    added_local_edges=[
                        {
                            "from": f"{stance_id}-selection-support",
                            "to": "debate-conclusion",
                            "relation": "supports_selection",
                        }
                    ],
                ),
                evidence_refs=position.source_artifact_refs,
                self_audit=WorkerSelfAudit(
                    unsupported_claims=[],
                    truth_status_claimed="local_argument_only",
                ),
            )
        )
    return packets


def _blocked_output(
    *,
    debate_id: str,
    package: DebateInputPackage,
    writer: DebateArtifactWriter,
    manifest: DebateRunManifest,
    code: DebateErrorCode,
    message: str,
    context: dict[str, object],
) -> DebateOutputPackage:
    return _status_output(
        debate_id=debate_id,
        package=package,
        writer=writer,
        manifest=manifest,
        status=DebateStatus.BLOCKED,
        code=code,
        message=message,
        context=context,
    )


def _status_output(
    *,
    debate_id: str,
    package: DebateInputPackage,
    writer: DebateArtifactWriter,
    manifest: DebateRunManifest,
    status: DebateStatus,
    code: DebateErrorCode,
    message: str,
    context: dict[str, object],
) -> DebateOutputPackage:
    output = DebateOutputPackage(
        debate_id=debate_id,
        request_id=package.request_id,
        status=status,
        review_summary=message,
        artifact_root=str(writer.binding.debate_candidate_root),
        manifest_ref=str(writer.artifact_path("manifest.json")),
        errors=[
            DebateErrorRecord(
                code=code.value,
                message=message,
                context=context,
            )
        ],
    )
    output_ref = writer.write_json(writer.artifact_path("output_package.json"), output)
    manifest.output_package_ref = str(output_ref)
    manifest.run_status = status.value
    _write_manifest(writer, manifest)
    return output


def _debate_not_required_output(
    *,
    debate_id: str,
    package: DebateInputPackage,
    writer: DebateArtifactWriter,
    manifest: DebateRunManifest,
    code: DebateErrorCode,
    message: str,
    context: dict[str, object],
) -> DebateOutputPackage:
    output = DebateOutputPackage(
        debate_id=debate_id,
        request_id=package.request_id,
        status=DebateStatus.DEBATE_NOT_REQUIRED,
        review_summary=message,
        artifact_root=str(writer.binding.debate_candidate_root),
        manifest_ref=str(writer.artifact_path("manifest.json")),
        errors=[
            DebateErrorRecord(
                code=code.value,
                message=message,
                context=context,
            )
        ],
    )
    output_ref = writer.write_json(writer.artifact_path("output_package.json"), output)
    manifest.output_package_ref = str(output_ref)
    manifest.run_status = DebateStatus.DEBATE_NOT_REQUIRED.value
    _write_manifest(writer, manifest)
    return output


def _debate_id(package: DebateInputPackage, input_hash: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", package.request_id).strip("-")
    return f"debate-{raw}-{input_hash[:12]}"


def _debate_run_lock(debate_id: str) -> Lock:
    with _DEBATE_LOCK_GUARD:
        lock = _DEBATE_RUN_LOCKS.get(debate_id)
        if lock is None:
            lock = Lock()
            _DEBATE_RUN_LOCKS[debate_id] = lock
        return lock


def _input_hash(package: DebateInputPackage) -> str:
    return _hash_json(package.model_dump(mode="json"))


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_manifest(
    writer: DebateArtifactWriter,
    manifest: DebateRunManifest,
):
    manifest.updated_at_utc = utc_now()
    return writer.write_json(writer.artifact_path("manifest.json"), manifest)


def _context_gate(
    context: DebateContextBundle,
) -> tuple[DebateStatus, DebateErrorCode, str, dict[str, object]] | None:
    blocking_needs = [
        need for need in context.missing_measurements if need.blocking_level == "blocking"
    ]
    test_needs = [
        need for need in blocking_needs if need.suggested_owner == "test"
    ]
    if test_needs:
        return (
            DebateStatus.NEED_MEASUREMENT,
            DebateErrorCode.MISSING_TEST_MEASUREMENT,
            "Debate requires concrete Test measurement before adjudication.",
            {
                "need_ids": [need.need_id for need in test_needs],
                "questions": [need.question for need in test_needs],
            },
        )
    if blocking_needs:
        return (
            DebateStatus.NEED_MORE_CONTEXT,
            DebateErrorCode.MISSING_REQUIRED_CONTEXT,
            "Debate requires missing project context before adjudication.",
            {
                "need_ids": [need.need_id for need in blocking_needs],
                "questions": [need.question for need in blocking_needs],
            },
        )
    if context.degraded_recall_warnings:
        return (
            DebateStatus.NEED_MORE_CONTEXT,
            DebateErrorCode.DEGRADED_CONTEXT_RECALL,
            "Debate context recall is degraded and cannot support a strong verdict.",
            {
                "warning_ids": [
                    warning.warning_id for warning in context.degraded_recall_warnings
                ],
                "messages": [
                    warning.message for warning in context.degraded_recall_warnings
                ],
            },
        )
    return None


def _normalize_material_text(text: str) -> str:
    return " ".join(sorted(re.findall(r"[A-Za-z0-9_]+", text.lower())))


def _external_candidate_payload(candidate) -> dict[str, object]:  # noqa: ANN001
    return {
        "source_module": "debate",
        "candidate_id": candidate.candidate_id,
        "request_id": candidate.request_id,
        "debate_id": candidate.debate_id,
        "selected_stance_id": candidate.selected_stance_id,
        "rejected_alternatives": candidate.rejected_alternatives,
        "status": candidate.status.value,
        "proposed_nodes": [
            node.model_dump(mode="json") for node in candidate.nodes
        ],
        "reused_node_ids": candidate.reused_node_ids,
    }


def _semantic_keys(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
    seen: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen[:12]
