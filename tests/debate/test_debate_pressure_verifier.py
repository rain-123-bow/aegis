from __future__ import annotations

from pathlib import Path

from scripts import debate_subgraph_v2_pressure_verify as pressure


def test_pressure_scenarios_cover_distinct_production_debate_topics(
    tmp_path: Path,
) -> None:
    scenarios = pressure.build_pressure_scenarios(tmp_path / "projects")
    scenario_ids = {scenario.scenario_id for scenario in scenarios}

    assert scenario_ids >= {
        "one_off_data_chart_tool_language_lock",
        "payment_callback_idempotency_strategy",
        "telemetry_ingest_low_latency_route",
        "plugin_extension_boundary_strategy",
        "report_export_one_off_route",
        "balanced_evidence_non_convergent",
        "duplicate_routes_not_required",
        "missing_test_measurement_before_route",
        "many_stance_scale_route",
    }


def test_single_pressure_scenario_records_behavior_monitoring(
    tmp_path: Path,
) -> None:
    writer = pressure.PressureEvidenceWriter(tmp_path / "evidence")
    scenario = next(
        item
        for item in pressure.build_pressure_scenarios(tmp_path / "projects")
        if item.scenario_id == "payment_callback_idempotency_strategy"
    )

    result = pressure.run_single_scenario(writer, scenario)

    assert result.status == "passed"
    assert result.metrics["output_status"] == "completed"
    assert result.metrics["leader_assessment"]["decision"]
    assert result.metrics["worker_turn_count"] >= 2
    assert result.metrics["worker_attack_count"] >= 1
    assert result.metrics["causal_candidate_node_count"] >= 1
    assert result.metrics["causal_db_candidate_rows"] >= 1
    assert result.metrics["global_truth_written"] is False


def test_pressure_summary_keeps_scope_limited_when_real_agent_behavior_not_run(
    tmp_path: Path,
) -> None:
    writer = pressure.PressureEvidenceWriter(tmp_path / "evidence")
    result = pressure.PressureCaseResult(
        name="sample_case",
        status="passed",
        summary="ok",
        artifact="artifact.json",
        metrics={},
    )

    summary = pressure.write_pressure_report(
        writer,
        results=[result],
        real_agent_behavior_executed=False,
    )

    assert summary["verdict"] == "accepted_with_scope_limits"
    assert summary["status"] == "scope_limited"
    assert summary["scope_limits"] == ["real_agent_behavior_acceptance_not_executed"]
