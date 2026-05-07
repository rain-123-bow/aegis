from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aegis_debate_runtime.causal_state import AdjudicatorCausalState, WorkerLocalCausalState
from aegis_debate_runtime.mailbucket_package import validate_debate_result_mailbucket_package, write_debate_result_mailbucket_package


def test_worker_and_adjudicator_causal_state_shapes_are_serializable():
    stance = {
        "stance_id": "S1",
        "claim": "Use leader-mediated round-robin.",
        "why": "It preserves turn control and avoids uncontrolled group chat.",
        "scope": "Debate Department internal runtime.",
        "assumptions": ["Leader controls the debate topology."],
        "evidence": [{"type": "contract", "ref": "INTERNAL_TOPOLOGY_CONTRACT.md", "relevance": "topology rule"}],
        "risk_if_wrong": "Workers may drift into full-mesh chat.",
        "invalidation_conditions": ["A later contract permits full-mesh debate."],
    }

    worker_state = WorkerLocalCausalState.from_stance(run_id="run-1", worker_id="worker-S1", stance=stance)
    worker_payload = worker_state.to_dict()

    assert worker_payload["stance_id"] == "S1"
    assert worker_payload["route_priority"]
    assert worker_payload["expand_priority"]

    adjudicator_state = AdjudicatorCausalState.initial(
        run_id="run-1",
        decision_target="Select Debate topology.",
        current_question="Which topology should the Debate Department use?",
        stances=[stance],
    )
    adjudicator_payload = adjudicator_state.to_dict()

    assert adjudicator_payload["route_priority"]
    assert adjudicator_payload["expand_priority"]


def test_mailbucket_package_contains_required_causal_files(tmp_path: Path):
    final_report = {
        "run_id": "run-1",
        "decision": "accept_one",
        "causal_result": {
            "statement": "Use leader-mediated round-robin.",
            "evidence": [{"type": "contract", "ref": "INTERNAL_TOPOLOGY_CONTRACT.md", "relevance": "topology rule"}],
        },
        "transcript_digest": [{"turn_id": "t1", "stance_id": "S1", "claim": "Use leader-mediated round-robin."}],
    }
    adjudicator_state = {
        "run_id": "run-1",
        "route_priority": [{"id": "stance_set", "route_grade": "A", "reason": "core"}],
        "expand_priority": [{"id": "selected", "expand_grade": "A", "reason": "final"}],
    }
    worker_state = {
        "run_id": "run-1",
        "worker_id": "worker-S1",
        "stance_id": "S1",
        "claim": "Use leader-mediated round-robin.",
        "why": "It prevents uncontrolled group chat.",
        "evidence": [],
        "route_priority": [{"id": "claim", "route_grade": "A", "reason": "core"}],
        "expand_priority": [{"id": "claim", "expand_grade": "A", "reason": "core"}],
    }
    worker_proof = {
        "agent_id": "worker-S1",
        "worker_id": "worker-S1",
        "stance_id": "S1",
        "role_id": "debate_worker",
    }

    summary = write_debate_result_mailbucket_package(
        output_dir=tmp_path,
        final_report=final_report,
        adjudicator_causal_state=adjudicator_state,
        worker_states=[worker_state],
        worker_proofs=[worker_proof],
    )

    assert summary["worker_state_count"] == 1
    assert summary["worker_proof_count"] == 1
    validate_debate_result_mailbucket_package(tmp_path, require_worker_proofs=True)
    assert (tmp_path / "README.md").is_file()
    assert (tmp_path / "final_report.json").is_file()
    assert (tmp_path / "adjudicator_causal_state.json").is_file()
    assert list((tmp_path / "worker_states").glob("*.json"))
    assert list((tmp_path / "worker_proofs").glob("*_proof.json"))


def test_mailbucket_package_copies_existing_worker_proof_bytes_identically(tmp_path: Path):
    final_report = {
        "run_id": "run-1",
        "decision": "accept_one",
        "causal_result": {"statement": "Use leader-mediated round-robin."},
    }
    adjudicator_state = {
        "run_id": "run-1",
        "route_priority": [{"id": "stance_set", "route_grade": "A", "reason": "core"}],
        "expand_priority": [{"id": "selected", "expand_grade": "A", "reason": "final"}],
    }
    worker_state = {
        "run_id": "run-1",
        "worker_id": "worker-S1",
        "stance_id": "S1",
        "claim": "Use leader-mediated round-robin.",
        "why": "It prevents uncontrolled group chat.",
        "evidence": [],
        "route_priority": [{"id": "claim", "route_grade": "A", "reason": "core"}],
        "expand_priority": [{"id": "claim", "expand_grade": "A", "reason": "core"}],
    }
    source_proof_path = tmp_path / "worker-S1_proof.json"
    source_proof_path.write_bytes(b'{"z":2,"a":1,"worker_id":"worker-S1","stance_id":"S1"}\n')
    package_dir = tmp_path / "package"

    summary = write_debate_result_mailbucket_package(
        output_dir=package_dir,
        final_report=final_report,
        adjudicator_causal_state=adjudicator_state,
        worker_states=[worker_state],
        worker_proof_paths=[source_proof_path],
    )

    package_proof_path = package_dir / "worker_proofs" / source_proof_path.name
    source_hash = hashlib.sha256(source_proof_path.read_bytes()).hexdigest()
    package_hash = hashlib.sha256(package_proof_path.read_bytes()).hexdigest()

    assert summary["worker_proof_count"] == 1
    assert package_hash == source_hash
