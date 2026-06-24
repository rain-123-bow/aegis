"""Production-like pressure verification for DebateSubgraph v2.

The script stresses deterministic DebateSubgraph runtime behavior across
multiple project-like debate topics. It does not replace real-agent behavioral
acceptance; the final verdict remains scope-limited unless that separate
acceptance evidence is supplied by a real-agent run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from aegis.modules.debate import (
    CandidatePosition,
    DebateInputPackage,
    DebateOutputPackage,
    DebateRuntimeConfig,
    HardConstraint,
    LeaderRoundAssessment,
    WorkerTurnPacket,
    run_deterministic_debate,
)
from aegis.stores.causal.models import (
    AdmissionTransaction,
    CausalDependencyGroup,
    CausalNodeDraft,
)
from aegis.stores.causal.store import CausalStore
from aegis.stores.knowledge.models import (
    AdmissionRequest,
    ApplicabilityProfile,
    EvidencePointer,
    EvidenceRef,
    KnowledgeFactDraft,
    NeedRule,
)
from aegis.stores.knowledge.store import KnowledgeStore


REPO_ROOT = Path(__file__).resolve().parents[1]
Status = Literal["passed", "failed", "blocked", "scope_limited"]


@dataclass(frozen=True)
class PressureScenario:
    scenario_id: str
    title: str
    expected_statuses: set[str]
    package: DebateInputPackage
    config: DebateRuntimeConfig = field(default_factory=lambda: DebateRuntimeConfig(max_rounds=3))


@dataclass
class PressureCaseResult:
    name: str
    status: Status
    summary: str
    artifact: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class PressureEvidenceWriter:
    def __init__(self, root: Path):
        self.root = root
        self.artifacts = root / "artifacts"
        self.reports = root / "reports"
        self.logs = root / "logs"
        self.projects = root / "projects"
        for path in [
            self.artifacts,
            self.artifacts / "scenario_runs",
            self.artifacts / "concurrency",
            self.artifacts / "aggregate",
            self.reports,
            self.logs,
            self.projects,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def write_json(self, relative_path: str, payload: object) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def write_text(self, relative_path: str, payload: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument("--repeat-count", type=int, default=12)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    evidence_root = args.evidence_root or (
        REPO_ROOT / "module_test_reports" / f"debate_v2_pressure_{timestamp}"
    )
    writer = PressureEvidenceWriter(evidence_root)
    results: list[PressureCaseResult] = []
    scenarios = build_pressure_scenarios(writer.projects)
    start = time.perf_counter()
    for scenario in scenarios:
        results.append(run_single_scenario(writer, scenario))
    results.append(run_repeated_idempotency_pressure(writer, scenarios, args.repeat_count))
    results.append(run_concurrent_duplicate_pressure(writer, args.concurrency))
    results.append(run_retrieval_scale_pressure(writer))
    results.append(run_artifact_scale_pressure(writer))
    results.append(run_db_integrity_check(writer))
    elapsed = time.perf_counter() - start
    summary = write_pressure_report(
        writer,
        results=results,
        real_agent_behavior_executed=False,
        extra={"elapsed_seconds": elapsed},
    )
    print(f"evidence_root={writer.root}")
    print(f"final_verdict={summary['verdict']}")
    return 0 if summary["status"] in {"passed", "scope_limited"} else 1


def build_pressure_scenarios(projects_root: Path) -> list[PressureScenario]:
    projects_root.mkdir(parents=True, exist_ok=True)
    return [
        one_off_data_chart_tool_language_lock(projects_root),
        payment_callback_idempotency_strategy(projects_root),
        telemetry_ingest_low_latency_route(projects_root),
        plugin_extension_boundary_strategy(projects_root),
        report_export_one_off_route(projects_root),
        balanced_evidence_non_convergent(projects_root),
        duplicate_routes_not_required(projects_root),
        missing_test_measurement_before_route(projects_root),
        many_stance_scale_route(projects_root),
    ]


def run_single_scenario(
    writer: PressureEvidenceWriter,
    scenario: PressureScenario,
) -> PressureCaseResult:
    started = time.perf_counter()
    failed: list[str] = []
    output = run_deterministic_debate(scenario.package, scenario.config)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if output.status.value not in scenario.expected_statuses:
        failed.append(f"unexpected_status_{output.status.value}")
    metrics = collect_behavior_metrics(scenario, output)
    if metrics["code_root_polluted"]:
        failed.append("code_root_polluted")
    if metrics["global_truth_written"]:
        failed.append("global_truth_written")
    if output.status.value == "completed":
        if metrics["worker_turn_count"] <= 0:
            failed.append("missing_worker_turns")
        if metrics["leader_assessment"] is None:
            failed.append("missing_leader_assessment")
        if metrics["causal_candidate_node_count"] <= 0:
            failed.append("missing_causal_candidate_nodes")
        if metrics["causal_db_candidate_rows"] <= 0:
            failed.append("missing_causal_db_candidate_rows")
        if metrics["candidate_rows_all_candidate"] is not True:
            failed.append("candidate_rows_not_candidate_status")
    metrics["elapsed_ms"] = elapsed_ms
    artifact = writer.write_json(
        f"artifacts/scenario_runs/{scenario.scenario_id}_result.json",
        {
            "scenario_id": scenario.scenario_id,
            "title": scenario.title,
            "status": "passed" if not failed else "failed",
            "failed_cases": failed,
            "output_package": output.model_dump(mode="json"),
            "metrics": metrics,
        },
    )
    copy_run_artifacts(output, writer.artifacts / "scenario_runs" / scenario.scenario_id)
    return PressureCaseResult(
        name=scenario.scenario_id,
        status="passed" if not failed else "failed",
        summary=f"{scenario.title}: {output.status.value}",
        artifact=rel(artifact),
        metrics=metrics,
    )


def collect_behavior_metrics(
    scenario: PressureScenario,
    output: DebateOutputPackage,
) -> dict[str, Any]:
    artifact_root = Path(output.artifact_root)
    leader = read_model(artifact_root / "leader_assessment.json", LeaderRoundAssessment)
    worker_turns = read_model_list(artifact_root / "worker_turns.json", WorkerTurnPacket)
    violations = read_json(artifact_root / "worker_violations.json", default=[])
    causal_candidate = read_json(artifact_root / "causal_candidate.json", default={})
    write_result = read_json(artifact_root / "causal_write_result.json", default={})
    db_rows = causal_rows_by_id(
        scenario.package.project_root,
        [int(item) for item in write_result.get("inserted_node_ids", [])],
    )
    return {
        "output_status": output.status.value,
        "selected_stance_id": output.selected_stance_id,
        "rejected_stance_ids": output.rejected_stance_ids,
        "artifact_root": str(artifact_root),
        "leader_assessment": leader.model_dump(mode="json") if leader else None,
        "worker_turn_count": len(worker_turns),
        "worker_attack_count": sum(len(turn.attacks) for turn in worker_turns),
        "worker_concession_count": sum(len(turn.concessions) for turn in worker_turns),
        "worker_evidence_ref_count": sum(len(turn.evidence_refs) for turn in worker_turns),
        "worker_violation_count": len(violations) if isinstance(violations, list) else 0,
        "worker_violation_types": sorted(
            {
                str(item.get("violation_type"))
                for item in violations
                if isinstance(item, dict) and item.get("violation_type")
            }
        ),
        "causal_candidate_node_count": len(causal_candidate.get("proposed_nodes", []))
        if isinstance(causal_candidate, dict)
        else 0,
        "causal_db_candidate_rows": len(db_rows),
        "candidate_rows_all_candidate": all(row["status"] == "candidate" for row in db_rows.values())
        if db_rows
        else None,
        "causal_write_status": write_result.get("write_status")
        if isinstance(write_result, dict)
        else None,
        "global_truth_written": any(row["status"] == "admitted" for row in db_rows.values()),
        "code_root_polluted": code_root_has_unexpected_files(scenario.package.project_root),
        "db_integrity": sqlite_integrity(scenario.package.project_root / "causal" / "causal.sqlite3"),
    }


def run_repeated_idempotency_pressure(
    writer: PressureEvidenceWriter,
    scenarios: list[PressureScenario],
    repeat_count: int,
) -> PressureCaseResult:
    records: list[dict[str, Any]] = []
    failed: list[str] = []
    durations: list[float] = []
    for scenario in scenarios:
        before = count_causal_nodes(scenario.package.project_root)
        statuses: list[str] = []
        for _ in range(repeat_count):
            started = time.perf_counter()
            output = run_deterministic_debate(scenario.package, scenario.config)
            durations.append((time.perf_counter() - started) * 1000)
            statuses.append(output.status.value)
        after = count_causal_nodes(scenario.package.project_root)
        allowed_growth = 0 if statuses[-1] != "completed" else 0
        if after - before > allowed_growth:
            failed.append(f"{scenario.scenario_id}_candidate_count_grew_{before}_to_{after}")
        records.append(
            {
                "scenario_id": scenario.scenario_id,
                "before_nodes": before,
                "after_nodes": after,
                "statuses": statuses,
            }
        )
    artifact = writer.write_json(
        "artifacts/aggregate/repeated_idempotency_pressure_results.json",
        {
            "status": "passed" if not failed else "failed",
            "repeat_count": repeat_count,
            "failed_cases": failed,
            "records": records,
            "duration_ms": duration_summary(durations),
        },
    )
    return PressureCaseResult(
        name="repeated_idempotency_pressure",
        status="passed" if not failed else "failed",
        summary=f"{repeat_count} repeated runs per scenario checked for duplicate growth.",
        artifact=rel(artifact),
        metrics={"failed_cases": failed, "duration_ms": duration_summary(durations)},
    )


def run_concurrent_duplicate_pressure(
    writer: PressureEvidenceWriter,
    concurrency: int,
) -> PressureCaseResult:
    scenario = payment_callback_idempotency_strategy(writer.projects / "concurrent_duplicate")
    before = count_causal_nodes(scenario.package.project_root)
    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(run_deterministic_debate, scenario.package, scenario.config)
            for _ in range(concurrency)
        ]
        for future in as_completed(futures):
            try:
                output = future.result()
                records.append(
                    {
                        "status": output.status.value,
                        "artifact_root": output.artifact_root,
                        "selected_stance_id": output.selected_stance_id,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                records.append({"exception": type(exc).__name__, "message": str(exc)})
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    after = count_causal_nodes(scenario.package.project_root)
    exceptions = [record for record in records if "exception" in record]
    if exceptions:
        failed.append("raw_exception_leak")
    if after - before > 3:
        failed.append(f"duplicate_candidate_rows_excessive_{before}_to_{after}")
    integrity = sqlite_integrity(scenario.package.project_root / "causal" / "causal.sqlite3")
    if integrity["integrity_check"] != "ok":
        failed.append("sqlite_integrity_failed")
    artifact = writer.write_json(
        "artifacts/concurrency/concurrent_duplicate_pressure_results.json",
        {
            "status": "passed" if not failed else "failed",
            "concurrency": concurrency,
            "before_nodes": before,
            "after_nodes": after,
            "failed_cases": failed,
            "records": records,
            "elapsed_ms": elapsed_ms,
            "integrity": integrity,
        },
    )
    return PressureCaseResult(
        name="concurrent_duplicate_pressure",
        status="passed" if not failed else "failed",
        summary=f"{concurrency} concurrent duplicate Debate runs checked.",
        artifact=rel(artifact),
        metrics={
            "failed_cases": failed,
            "before_nodes": before,
            "after_nodes": after,
            "elapsed_ms": elapsed_ms,
            "integrity": integrity,
        },
    )


def run_retrieval_scale_pressure(writer: PressureEvidenceWriter) -> PressureCaseResult:
    root = make_project(writer.projects / "retrieval_scale")
    seed_many_knowledge(root, count=1200)
    seed_many_causal(root, count=600)
    package = make_package(
        root=root,
        request_id="req-retrieval-scale",
        decision_problem="Choose data export route under large project-local stores",
        positions=[
            ("streaming_export", "Use streaming export", "Streaming export avoids memory spikes.", ["streaming-route.md"]),
            ("batch_export", "Use batch export", "Batch export is simpler for one-off use.", ["batch-route.md"]),
        ],
        knowledge_queries=["streaming export memory pressure", "batch export"],
        causal_queries=["streaming export"],
    )
    started = time.perf_counter()
    output = run_deterministic_debate(package, DebateRuntimeConfig(max_rounds=3))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    context = read_json(Path(output.artifact_root) / "context_bundle.json", default={})
    knowledge_count = len(context.get("knowledge_refs", [])) if isinstance(context, dict) else 0
    causal_count = len(context.get("causal_refs", [])) if isinstance(context, dict) else 0
    context_bytes = len(json.dumps(context, sort_keys=True).encode("utf-8"))
    failed: list[str] = []
    if knowledge_count > 50 or causal_count > 50:
        failed.append("retrieval_ref_limit_exceeded")
    if context_bytes > 256 * 1024:
        failed.append("retrieval_package_too_large")
    if output.status.value not in {"completed", "need_measurement", "non_convergent"}:
        failed.append(f"unexpected_status_{output.status.value}")
    artifact = writer.write_json(
        "artifacts/aggregate/retrieval_scale_pressure_results.json",
        {
            "status": "passed" if not failed else "failed",
            "failed_cases": failed,
            "output_status": output.status.value,
            "elapsed_ms": elapsed_ms,
            "knowledge_ref_count": knowledge_count,
            "causal_ref_count": causal_count,
            "context_bytes": context_bytes,
        },
    )
    return PressureCaseResult(
        name="retrieval_scale_pressure",
        status="passed" if not failed else "failed",
        summary="Large Knowledge/Causal store retrieval stayed bounded.",
        artifact=rel(artifact),
        metrics={
            "failed_cases": failed,
            "elapsed_ms": elapsed_ms,
            "knowledge_ref_count": knowledge_count,
            "causal_ref_count": causal_count,
            "context_bytes": context_bytes,
        },
    )


def run_artifact_scale_pressure(writer: PressureEvidenceWriter) -> PressureCaseResult:
    scenario = many_stance_scale_route(writer.projects / "artifact_scale")
    config = DebateRuntimeConfig(max_rounds=8, stable_selected_stance_round_threshold=6)
    started = time.perf_counter()
    output = run_deterministic_debate(scenario.package, config)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    root = Path(output.artifact_root)
    files = [path for path in root.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)
    failed: list[str] = []
    if any(scenario.package.project_root / "code" in path.parents for path in files):
        failed.append("artifact_under_code_root")
    if output.status.value not in {"completed", "non_convergent", "scope_limited"}:
        failed.append(f"unexpected_status_{output.status.value}")
    artifact = writer.write_json(
        "artifacts/aggregate/artifact_scale_pressure_results.json",
        {
            "status": "passed" if not failed else "failed",
            "failed_cases": failed,
            "output_status": output.status.value,
            "artifact_file_count": len(files),
            "artifact_total_bytes": total_bytes,
            "elapsed_ms": elapsed_ms,
        },
    )
    return PressureCaseResult(
        name="artifact_scale_pressure",
        status="passed" if not failed else "failed",
        summary="Larger stance/round artifact set stayed inside Debate candidate root.",
        artifact=rel(artifact),
        metrics={
            "failed_cases": failed,
            "output_status": output.status.value,
            "artifact_file_count": len(files),
            "artifact_total_bytes": total_bytes,
            "elapsed_ms": elapsed_ms,
        },
    )


def run_db_integrity_check(writer: PressureEvidenceWriter) -> PressureCaseResult:
    checks: dict[str, Any] = {}
    failed: list[str] = []
    for db in writer.projects.rglob("causal.sqlite3"):
        result = sqlite_integrity(db)
        checks[str(db)] = result
        if result["integrity_check"] != "ok" or result["foreign_key_violations"]:
            failed.append(str(db))
    artifact = writer.write_json(
        "artifacts/aggregate/db_integrity_results.json",
        {
            "status": "passed" if not failed else "failed",
            "failed_cases": failed,
            "checks": checks,
        },
    )
    return PressureCaseResult(
        name="db_integrity",
        status="passed" if not failed else "failed",
        summary="SQLite integrity and foreign key checks completed.",
        artifact=rel(artifact),
        metrics={"failed_cases": failed, "db_count": len(checks)},
    )


def write_pressure_report(
    writer: PressureEvidenceWriter,
    *,
    results: list[PressureCaseResult],
    real_agent_behavior_executed: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed = [result for result in results if result.status == "failed"]
    blocked = [result for result in results if result.status == "blocked"]
    scope_limits = [] if real_agent_behavior_executed else ["real_agent_behavior_acceptance_not_executed"]
    if failed:
        verdict = "rejected"
        status: Status = "failed"
    elif blocked:
        verdict = "blocked"
        status = "blocked"
    elif scope_limits:
        verdict = "accepted_with_scope_limits"
        status = "scope_limited"
    else:
        verdict = "accepted"
        status = "passed"
    rows = "\n".join(
        f"| {result.name} | {result.status} | {result.summary} | {result.artifact or ''} |"
        for result in results
    )
    report = f"""# DebateSubgraph v2 Pressure Verification Report

## Scope

Production-like deterministic DebateSubgraph pressure verification across
multiple local project debate topics. This does not execute real-agent
behavioral acceptance.

## Verdict

`{verdict}`

## Evidence Root

```text
{writer.root}
```

## Result Matrix

| Case | Status | Summary | Artifact |
| --- | --- | --- | --- |
{rows}

## Failed Cases

{format_results(failed)}

## Blocked Cases

{format_results(blocked)}

## Scope Limits

{format_scope_limits(scope_limits)}
"""
    report_path = writer.reports / "DEBATE_SUBGRAPH_V2_PRESSURE_VERIFICATION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    summary = {
        "status": status,
        "verdict": verdict,
        "scope_limits": scope_limits,
        "passed_cases": [result.name for result in results if result.status == "passed"],
        "failed_cases": [result.name for result in failed],
        "blocked_cases": [result.name for result in blocked],
        "report_ref": rel(report_path),
        "results": [result.__dict__ for result in results],
    }
    if extra:
        summary.update(extra)
    writer.write_json("artifacts/aggregate/final_pressure_summary.json", summary)
    return summary


def one_off_data_chart_tool_language_lock(root: Path) -> PressureScenario:
    project = make_project(root / "one_off_data_chart_tool_language_lock")
    package = make_package(
        root=project,
        request_id="req-chart-language-lock",
        decision_problem="Choose implementation route for a one-off local data chart tool",
        positions=[
            ("cpp_required", "Use C++ because requester prefers it", "Requester preference for C++.", ["cpp-preference.md"]),
            ("python_script", "Use Python script", "Python has lower implementation overhead for chart generation.", ["python-chart.md"]),
        ],
        hard_constraints=[
            HardConstraint(
                constraint_id="hc-cpp-preference",
                statement="C++ is mandatory because requester prefers it.",
                source="user",
                evidence_ref="archive/cpp-preference.md",
            )
        ],
    )
    return PressureScenario(
        scenario_id="one_off_data_chart_tool_language_lock",
        title="Reject unsupported user language lock for one-off chart tool",
        expected_statuses={"blocked"},
        package=package,
        config=DebateRuntimeConfig(max_rounds=2),
    )


def payment_callback_idempotency_strategy(root: Path) -> PressureScenario:
    project = make_project(root / "payment_callback_idempotency_strategy")
    package = make_package(
        root=project,
        request_id="req-payment-idempotency",
        decision_problem="Choose payment callback idempotency strategy",
        positions=[
            ("direct_update", "Use direct database update", "Direct update is simplest.", ["direct-update.md"]),
            ("transactional_outbox", "Use transactional outbox", "Outbox preserves retry safety and auditability.", ["outbox.md", "outbox-risk.md"]),
            ("cache_dedupe", "Use cache dedupe only", "Cache dedupe reduces write overhead.", ["cache-dedupe.md"]),
        ],
        knowledge_queries=["payment callback retry idempotency audit"],
        causal_queries=["retry safety idempotency"],
    )
    seed_prior_context(
        project,
        knowledge=[
            ("Payment providers may retry callbacks.", "knowledge/payment-retry", ["payment", "retry", "idempotency"]),
            ("Financial callback handling must preserve auditability.", "knowledge/payment-audit", ["payment", "audit"]),
        ],
        causal=[
            ("Retry safety supports transactional outbox for payment callback processing.", "causal/payment-outbox"),
        ],
    )
    return PressureScenario(
        scenario_id="payment_callback_idempotency_strategy",
        title="Payment callback idempotency strategy",
        expected_statuses={"completed"},
        package=package,
    )


def telemetry_ingest_low_latency_route(root: Path) -> PressureScenario:
    project = make_project(root / "telemetry_ingest_low_latency_route")
    package = make_package(
        root=project,
        request_id="req-telemetry-low-latency",
        decision_problem="Choose telemetry ingest route for low latency sensor stream",
        positions=[
            ("cpp_ring_buffer", "Use C++ ring buffer ingest", "C++ ring buffer minimizes latency.", ["cpp-ring-buffer.md", "latency-budget.md"]),
            ("go_worker_pool", "Use Go worker pool ingest", "Go worker pool improves operational simplicity.", ["go-worker.md"]),
            ("rust_bounded_channel", "Use Rust bounded channel ingest", "Rust bounded channels balance safety and latency.", ["rust-channel.md"]),
        ],
        knowledge_queries=["sensor ingest latency safety"],
        causal_queries=["low latency bounded channel"],
    )
    seed_prior_context(
        project,
        knowledge=[
            ("Telemetry route has sub-10ms p95 latency budget.", "knowledge/latency-budget", ["latency", "telemetry"]),
            ("Memory safety is material for long-running ingest services.", "knowledge/memory-safety", ["memory", "safety"]),
        ],
        causal=[
            ("Bounded queues reduce overload collapse risk in telemetry ingest.", "causal/bounded-queues"),
        ],
    )
    return PressureScenario(
        scenario_id="telemetry_ingest_low_latency_route",
        title="Telemetry ingest low-latency implementation route",
        expected_statuses={"completed"},
        package=package,
    )


def plugin_extension_boundary_strategy(root: Path) -> PressureScenario:
    project = make_project(root / "plugin_extension_boundary_strategy")
    package = make_package(
        root=project,
        request_id="req-plugin-boundary",
        decision_problem="Choose plugin extension boundary strategy",
        positions=[
            ("direct_internal_api", "Use direct internal API", "Direct API is easiest to implement.", ["direct-api.md"]),
            ("adapter_boundary", "Use adapter boundary", "Adapter boundary isolates plugin contracts.", ["adapter-boundary.md", "contract-risk.md"]),
            ("event_bus", "Use event bus", "Event bus decouples plugin producers and consumers.", ["event-bus.md"]),
        ],
        knowledge_queries=["plugin contract boundary decoupling"],
        causal_queries=["extension boundary adapter"],
    )
    seed_prior_context(
        project,
        knowledge=[
            ("Plugin APIs are expected to evolve independently.", "knowledge/plugin-evolution", ["plugin", "boundary"]),
            ("Event bus adds ordering and observability complexity.", "knowledge/event-bus-risk", ["event", "bus", "ordering"]),
        ],
        causal=[
            ("Explicit adapter boundaries reduce plugin coupling when contracts evolve independently.", "causal/plugin-adapter"),
        ],
    )
    return PressureScenario(
        scenario_id="plugin_extension_boundary_strategy",
        title="Plugin extension boundary route",
        expected_statuses={"completed"},
        package=package,
    )


def report_export_one_off_route(root: Path) -> PressureScenario:
    project = make_project(root / "report_export_one_off_route")
    package = make_package(
        root=project,
        request_id="req-report-export",
        decision_problem="Choose one-off report export route",
        positions=[
            ("quick_script", "Use a quick local script", "Local script minimizes overhead.", ["quick-script.md", "one-off.md"]),
            ("web_dashboard", "Build a web dashboard", "Dashboard improves reuse if repeated.", ["dashboard.md"]),
            ("desktop_app", "Build a desktop app", "Desktop app supports non-technical users.", ["desktop.md"]),
        ],
        knowledge_queries=["one-off report export local script"],
        causal_queries=["scope simplicity"],
    )
    seed_prior_context(
        project,
        knowledge=[
            ("This report export is one-off and local.", "knowledge/one-off-local", ["one-off", "local"]),
        ],
        causal=[
            ("One-off local scope increases the value of the smallest reliable implementation path.", "causal/one-off-smallest"),
        ],
    )
    return PressureScenario(
        scenario_id="report_export_one_off_route",
        title="One-off report export implementation route",
        expected_statuses={"completed"},
        package=package,
    )


def balanced_evidence_non_convergent(root: Path) -> PressureScenario:
    project = make_project(root / "balanced_evidence_non_convergent")
    package = make_package(
        root=project,
        request_id="req-balanced-evidence",
        decision_problem="Choose balanced evidence route where no stance should fake certainty",
        positions=[
            ("route_a", "Use route A", "Route A has local complexity benefits.", ["route-a.md"]),
            ("route_b", "Use route B", "Route B has lifecycle benefits.", ["route-b.md"]),
        ],
    )
    return PressureScenario(
        scenario_id="balanced_evidence_non_convergent",
        title="Balanced evidence non-convergent debate",
        expected_statuses={"non_convergent"},
        package=package,
        config=DebateRuntimeConfig(max_rounds=1, stable_selected_stance_round_threshold=3),
    )


def duplicate_routes_not_required(root: Path) -> PressureScenario:
    project = make_project(root / "duplicate_routes_not_required")
    package = make_package(
        root=project,
        request_id="req-duplicate-routes",
        decision_problem="Detect duplicate routes that do not need debate",
        positions=[
            ("route_a", "Use route A", "Route A.", ["route-a.md"]),
            ("route_a_duplicate", "Use route A", "Route A duplicate.", ["route-a.md"]),
        ],
    )
    return PressureScenario(
        scenario_id="duplicate_routes_not_required",
        title="Duplicate route is not a debate",
        expected_statuses={"debate_not_required"},
        package=package,
    )


def missing_test_measurement_before_route(root: Path) -> PressureScenario:
    project = make_project(root / "missing_test_measurement_before_route")
    store = KnowledgeStore(project / "knowledge" / "knowledge.sqlite3")
    store.register_need_rule(
        NeedRule(
            rule_id="need-benchmark-before-route",
            required_dimension="benchmark_result",
            trigger_operations=["choose implementation route"],
            required_subject_kinds=["project"],
            acceptable_sources=["test"],
            default_blocking_level="request_test_measurement",
            rationale="A benchmark result is required before route adjudication.",
        )
    )
    package = make_package(
        root=project,
        request_id="req-missing-measurement",
        decision_problem="Choose implementation route when benchmark evidence is decisive",
        positions=[
            ("route_fast", "Use fast route", "Fast route may reduce latency.", ["fast-route.md"]),
            ("route_safe", "Use safe route", "Safe route may reduce failure risk.", ["safe-route.md"]),
        ],
    )
    return PressureScenario(
        scenario_id="missing_test_measurement_before_route",
        title="Missing Test measurement blocks route adjudication",
        expected_statuses={"need_measurement"},
        package=package,
    )


def many_stance_scale_route(root: Path) -> PressureScenario:
    project = make_project(root / "many_stance_scale_route")
    positions = [
        ("route_simple", "Use simple local route", "Simple local route minimizes overhead.", ["simple.md", "simple-extra.md"]),
        ("route_adapter", "Use adapter route", "Adapter route improves extension boundary.", ["adapter.md"]),
        ("route_queue", "Use queue route", "Queue route absorbs burst pressure.", ["queue.md"]),
        ("route_cache", "Use cache route", "Cache route improves repeated lookup latency.", ["cache.md"]),
        ("route_batch", "Use batch route", "Batch route improves throughput for offline jobs.", ["batch.md"]),
    ]
    package = make_package(
        root=project,
        request_id="req-many-stance-scale",
        decision_problem="Choose route among several valid implementation paths",
        positions=positions,
        knowledge_queries=["implementation route scale pressure"],
        causal_queries=["route selection pressure"],
    )
    seed_prior_context(
        project,
        knowledge=[
            ("Local scope favors simple route unless burst pressure or extension boundary is proven.", "knowledge/many-simple", ["simple", "route"]),
            ("Burst pressure can justify queue route.", "knowledge/many-queue", ["queue", "burst"]),
        ],
        causal=[
            ("A larger option set increases the need for explicit rejection reasons.", "causal/many-options"),
        ],
    )
    return PressureScenario(
        scenario_id="many_stance_scale_route",
        title="Many-stance route selection scale pressure",
        expected_statuses={"completed"},
        package=package,
        config=DebateRuntimeConfig(max_rounds=5, max_workers=6),
    )


def make_project(root: Path) -> Path:
    if root.exists():
        shutil.rmtree(root)
    for folder in ("code", "archive", "knowledge", "causal"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root


def make_package(
    *,
    root: Path,
    request_id: str,
    decision_problem: str,
    positions: list[tuple[str, str, str, list[str]]],
    hard_constraints: list[HardConstraint] | None = None,
    knowledge_queries: list[str] | None = None,
    causal_queries: list[str] | None = None,
) -> DebateInputPackage:
    refs: dict[str, str] = {}
    for _stance_id, statement, summary, file_names in positions:
        for file_name in file_names:
            path = root / "archive" / file_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Verified evidence: {statement}. {summary}", encoding="utf-8")
            refs[file_name] = str(path.resolve())
    return DebateInputPackage(
        request_id=request_id,
        source_module="execution",
        project_root=root,
        decision_problem=decision_problem,
        decision_scope="single local project",
        required_outcome="choose_one",
        knowledge_query_refs=knowledge_queries or [],
        causal_query_refs=causal_queries or [],
        source_artifact_refs=list(refs.values()),
        candidate_positions=[
            CandidatePosition(
                stance_id=stance_id,
                statement=statement,
                summary=summary,
                source_artifact_refs=[refs[name] for name in file_names],
            )
            for stance_id, statement, summary, file_names in positions
        ],
        hard_constraints=hard_constraints or [],
    )


def seed_prior_context(
    root: Path,
    *,
    knowledge: list[tuple[str, str, list[str]]],
    causal: list[tuple[str, str]],
) -> None:
    knowledge_store = KnowledgeStore(root / "knowledge" / "knowledge.sqlite3")
    for summary, evidence_id, semantic_keys in knowledge:
        fact_id = knowledge_store.put_candidate(
            KnowledgeFactDraft(
                fact_kind="platform",
                subject_kind="project",
                subject_id=root.name,
                predicate="constrains",
                object_kind="scalar",
                object=summary,
                fact_validity_scope={"project": root.name},
                semantic_summary=summary,
                semantic_keys=semantic_keys,
                source_module="knowledge_review",
                source_artifact_ref=evidence_id,
                evidence_refs=[
                    EvidenceRef(
                        ref_type="artifact",
                        ref_id=evidence_id,
                        verifier="knowledge_review",
                        verification_method="pressure_fixture_seed",
                    )
                ],
                applicability_profile=ApplicabilityProfile(
                    applicability_scope={"project": root.name},
                    affected_entities=["implementation route"],
                    affected_operations=["choose implementation route"],
                    task_intents=["implementation", "debate"],
                    lifecycle_phases=["debate"],
                    must_consider_when=["implementation route"],
                    priority="high",
                ),
                no_known_invalidation=True,
            )
        )
        knowledge_store.admit_fact(
            AdmissionRequest(
                knowledge_id=fact_id,
                admitted_by_module="knowledge_review",
                admission_method="knowledge_review",
                rationale="Pressure fixture admission.",
                evidence_refs=[EvidencePointer(ref_type="artifact", ref_id=evidence_id)],
            )
        )
    causal_store = CausalStore(root / "causal" / "causal.sqlite3")
    admitted_ids: list[int] = []
    previous: int | None = None
    for statement, evidence_id in causal:
        groups = []
        if previous is not None:
            groups.append(
                CausalDependencyGroup(
                    causal_dependencies=[previous],
                    evidence_refs=[evidence_id],
                    scope="single local project",
                )
            )
        node_id = causal_store.put_candidate(
            CausalNodeDraft(
                content=statement,
                semantic_summary=statement,
                semantic_keys=[token for token in statement.lower().split()[:8]],
                source_module="causal_review",
                source_artifact_ref=evidence_id,
                root_kind="design_decision",
                dependency_groups=groups,
                node_refs=[("artifact", evidence_id)],
            )
        )
        admitted_ids.append(node_id)
        previous = node_id
    if admitted_ids:
        causal_store.admit_nodes(
            AdmissionTransaction(
                node_ids=admitted_ids,
                admitted_by_module="causal_review",
                rationale="Pressure fixture causal admission.",
                evidence_ref="pressure/causal-seed",
            )
        )


def seed_many_knowledge(root: Path, *, count: int) -> None:
    store = KnowledgeStore(root / "knowledge" / "knowledge.sqlite3")
    for index in range(count):
        term = "streaming export" if index % 17 == 0 else f"noise-{index}"
        evidence_ref = f"knowledge/scale-{index}"
        fact_id = store.put_candidate(
            KnowledgeFactDraft(
                fact_kind="platform",
                subject_kind="project",
                subject_id=root.name,
                predicate="constrains",
                object_kind="scalar",
                object=f"{term} knowledge fact {index}",
                fact_validity_scope={"project": root.name},
                semantic_summary=f"{term} knowledge fact {index}",
                semantic_keys=term.split() + [str(index)],
                source_module="knowledge_review",
                source_artifact_ref=evidence_ref,
                evidence_refs=[
                    EvidenceRef(
                        ref_type="artifact",
                        ref_id=evidence_ref,
                        verifier="knowledge_review",
                        verification_method="pressure_fixture_seed",
                    )
                ],
                applicability_profile=ApplicabilityProfile(
                    applicability_scope={"project": root.name},
                    affected_entities=["implementation route"],
                    affected_operations=["choose implementation route"],
                    task_intents=["debate"],
                    lifecycle_phases=["debate"],
                    must_consider_when=["implementation route"],
                ),
                no_known_invalidation=True,
            )
        )
        store.admit_fact(
            AdmissionRequest(
                knowledge_id=fact_id,
                admitted_by_module="knowledge_review",
                admission_method="knowledge_review",
                rationale="Pressure scale admission.",
                evidence_refs=[EvidencePointer(ref_type="artifact", ref_id=evidence_ref)],
            )
        )


def seed_many_causal(root: Path, *, count: int) -> None:
    store = CausalStore(root / "causal" / "causal.sqlite3")
    ids: list[int] = []
    for index in range(count):
        text = (
            f"Streaming export causal node {index}"
            if index % 19 == 0
            else f"Unrelated causal node {index}"
        )
        ids.append(
            store.put_candidate(
                CausalNodeDraft(
                    content=text,
                    semantic_summary=text,
                    semantic_keys=text.lower().split(),
                    source_module="causal_review",
                    source_artifact_ref=f"causal/scale-{index}",
                    root_kind="design_decision",
                    node_refs=[("artifact", f"causal/scale-{index}")],
                )
            )
        )
    if ids:
        store.admit_nodes(
            AdmissionTransaction(
                node_ids=ids,
                admitted_by_module="causal_review",
                rationale="Pressure scale causal admission.",
                evidence_ref="causal/scale-admission",
            )
        )


def read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_model(path: Path, model: type) -> Any | None:
    if not path.exists():
        return None
    return model.model_validate(read_json(path, default={}))


def read_model_list(path: Path, model: type) -> list[Any]:
    payload = read_json(path, default=[])
    if not isinstance(payload, list):
        return []
    return [model.model_validate(item) for item in payload]


def copy_run_artifacts(output: DebateOutputPackage, destination: Path) -> None:
    root = Path(output.artifact_root)
    if root.exists():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(root, destination)


def causal_rows_by_id(project_root: Path, node_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not node_ids:
        return {}
    db = project_root / "causal" / "causal.sqlite3"
    placeholders = ",".join("?" for _ in node_ids)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT node_id, status, source_module, source_artifact_ref FROM causal_nodes "
            f"WHERE node_id IN ({placeholders})",
            tuple(node_ids),
        ).fetchall()
    return {int(row["node_id"]): dict(row) for row in rows}


def count_causal_nodes(project_root: Path) -> int:
    db = project_root / "causal" / "causal.sqlite3"
    if not db.exists():
        return 0
    with sqlite3.connect(db) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='causal_nodes'"
        ).fetchone()
        if not table:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0])


def sqlite_integrity(db: Path) -> dict[str, Any]:
    if not db.exists():
        return {"integrity_check": "missing", "foreign_key_violations": []}
    with sqlite3.connect(db) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [list(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]
    return {"integrity_check": integrity, "foreign_key_violations": foreign_keys}


def code_root_has_unexpected_files(project_root: Path) -> bool:
    code_root = project_root / "code"
    return any(path.is_file() for path in code_root.rglob("*"))


def duration_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    sorted_values = sorted(values)
    p95_index = min(len(sorted_values) - 1, int(len(sorted_values) * 0.95))
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(sorted_values[p95_index], 3),
        "max": round(max(values), 3),
    }


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def format_results(results: list[PressureCaseResult]) -> str:
    if not results:
        return "None."
    return "\n".join(f"- `{result.name}`: {result.summary}" for result in results)


def format_scope_limits(scope_limits: list[str]) -> str:
    if not scope_limits:
        return "None."
    return "\n".join(f"- `{item}`" for item in scope_limits)


if __name__ == "__main__":
    raise SystemExit(main())
