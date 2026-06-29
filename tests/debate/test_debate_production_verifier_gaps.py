from __future__ import annotations

import json
from pathlib import Path

from scripts import debate_subgraph_v2_production_verify as verify


def _writer(tmp_path: Path) -> verify.EvidenceWriter:
    return verify.EvidenceWriter(tmp_path / "evidence")


def _write_minimal_raw_agent_artifacts(writer: verify.EvidenceWriter) -> None:
    raw = writer.artifacts / "real_agent_runs" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "leader.json": {
            "role": "debate_leader",
            "thread_id": "leader-thread",
            "output": {
                "status": "causal_candidate",
                "selected_stance_id": "simple",
                "self_audit": {
                    "global_truth_claimed": False,
                    "store_truth_written": False,
                },
            },
        },
        "worker_simple.json": {
            "role": "debate_worker",
            "thread_id": "worker-simple-thread",
            "output": {
                "stance_id": "simple",
                "evidence_refs": ["artifact/simple-route.md"],
                "causal_chain_delta": {"added_local_nodes": ["n-simple"]},
                "self_audit": {"global_truth_claim": False},
            },
        },
        "worker_adapter.json": {
            "role": "debate_worker",
            "thread_id": "worker-adapter-thread",
            "output": {
                "stance_id": "adapter",
                "evidence_refs": ["artifact/adapter-route.md"],
                "causal_chain_delta": {"added_local_nodes": ["n-adapter"]},
                "self_audit": {"global_truth_claim": False},
            },
        },
        "worker_measurement.json": {
            "role": "debate_worker",
            "thread_id": "worker-measurement-thread",
            "output": {
                "stance_id": "measurement",
                "evidence_refs": ["artifact/measurement.md"],
                "causal_chain_delta": {"added_local_nodes": ["n-measurement"]},
                "self_audit": {"global_truth_claim": False},
            },
        },
    }
    for name, payload in artifacts.items():
        (raw / name).write_text(json.dumps(payload), encoding="utf-8")


def _behavior_case(case_id: str, invariants: dict[str, bool]) -> dict[str, object]:
    return {
        "case_id": case_id,
        "status": "passed",
        "thread_ids": [f"{case_id}-thread"],
        "expected_behavior": f"expected behavior for {case_id}",
        "observed_behavior": f"observed behavior for {case_id}",
        "leader_action": f"leader action for {case_id}",
        "worker_packet_refs": [f"artifacts/{case_id}/worker_packet.json"],
        "schema_validation": {"passed": True, "validated_models": ["WorkerTurnPacket"]},
        "repair_attempts": [],
        "evidence_refs": [f"artifacts/{case_id}/evidence.md"],
        "invariants": invariants,
    }


def test_real_agent_behavior_validation_requires_pressure_cases(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    _write_minimal_raw_agent_artifacts(writer)

    result = verify.run_real_agent_behavior_validation(writer)

    assert result.status == "blocked"
    assert "missing_real_agent_behavior_cases" in result.details["failed_cases"]


def test_real_agent_behavior_validation_accepts_required_invariant_cases(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    _write_minimal_raw_agent_artifacts(writer)
    cases = [
        _behavior_case(
            "unsupported_preference_pressure",
            {
                "preference_not_treated_as_hard_constraint": True,
                "objective_evidence_required": True,
            },
        ),
        _behavior_case(
            "evidence_backed_defeat",
            {
                "defeated_worker_conceded_with_defeating_ref": True,
                "leader_used_defeat_in_adjudication": True,
            },
        ),
        _behavior_case(
            "premature_concession_pressure",
            {
                "premature_concession_resisted_or_flagged": True,
                "no_unearned_concession_used_in_merge": True,
            },
        ),
        _behavior_case(
            "over_defense_pressure",
            {
                "unsupported_invention_flagged": True,
                "unusable_turn_excluded_from_merge": True,
            },
        ),
        _behavior_case(
            "non_convergent_debate",
            {
                "fake_certainty_rejected": True,
                "non_convergent_or_scope_limited_status_returned": True,
            },
        ),
        _behavior_case(
            "causal_candidate_closure",
            {
                "explicit_causal_candidate_returned": True,
                "global_truth_not_written": True,
                "merge_eligible_turns_only_used": True,
            },
        ),
    ]
    case_dir = writer.artifacts / "real_agent_runs" / "behavior_cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        (case_dir / f"{case['case_id']}.json").write_text(
            json.dumps(case),
            encoding="utf-8",
        )

    result = verify.run_real_agent_behavior_validation(writer)

    assert result.status == "passed"
    assert set(result.details["passed_cases"]) >= {
        "unsupported_preference_pressure",
        "evidence_backed_defeat",
        "premature_concession_pressure",
        "over_defense_pressure",
        "non_convergent_debate",
        "causal_candidate_closure",
    }


def test_domain_error_contract_covers_expanded_cases(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    fixture = verify.prepare_fixture(writer)

    result = verify.run_domain_error_checks(writer, fixture)

    assert result.status == "passed"
    assert set(result.details["passed_cases"]) >= {
        "invalid_input_package_rejected",
        "missing_project_store_domain_error",
        "invalid_artifact_path_rejected",
        "unsupported_hard_constraint_controlled",
        "insufficient_defensible_stances_controlled",
        "missing_test_measurement_controlled",
        "non_convergent_controlled",
        "worker_protocol_violation_controlled",
        "causal_candidate_write_failure_controlled",
    }


def test_artifact_schema_validation_checks_non_result_runtime_json(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    run_dir = writer.artifacts / "deterministic_runs" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "output_package.json").write_text(
        json.dumps({"not": "a DebateOutputPackage"}),
        encoding="utf-8",
    )

    result = verify.run_artifact_schema_validation(writer)

    assert result.status == "failed"
    assert any("output_package.json" in case for case in result.details["failed_cases"])


def test_final_verdict_is_scope_limited_when_only_real_agent_behavior_is_blocked(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    results = [
        verify.GateResult(
            name="knowledge_causal_retrieval_quality",
            status="passed",
            summary="ok",
        ),
        verify.GateResult(
            name="candidate_write_fault_injection",
            status="passed",
            summary="ok",
        ),
        verify.GateResult(
            name="candidate_artifact_db_cross_reference",
            status="passed",
            summary="ok",
        ),
        verify.GateResult(name="resume_idempotency", status="passed", summary="ok"),
        verify.GateResult(name="domain_error_contract", status="passed", summary="ok"),
        verify.GateResult(name="state_boundary", status="passed", summary="ok"),
        verify.GateResult(
            name="test_artifact_schema_validation",
            status="passed",
            summary="ok",
        ),
        verify.GateResult(
            name="real_agent_independent_validation",
            status="passed",
            summary="ok",
        ),
        verify.GateResult(
            name="real_agent_behavior_validation",
            status="blocked",
            summary="missing real behavior cases",
        ),
        verify.GateResult(name="pytest_debate", status="passed", summary="ok"),
    ]

    result = verify.write_report(writer, results)
    summary_path = Path(result.details["summary_artifact"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result.details["verdict"] == "accepted_with_scope_limits"
    assert result.status == "scope_limited"
    assert summary["status"] == "scope_limited"
    assert summary["verdict"] == "accepted_with_scope_limits"
    assert summary["failed_cases"] == []
    assert summary["scope_limits"] == ["real_agent_behavior_validation"]
