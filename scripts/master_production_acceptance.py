from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aegis.graph import AegisRuntime  # noqa: E402


ScenarioKind = Literal["real_pm_allow", "real_pm_block", "bad_pm_review_block"]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name: str
    kind: ScenarioKind
    request: str
    expected_handoff_allowed: bool
    expected_stage: Literal["execution_completed", "pm_blocked", "review_blocked"]
    monitor_expectation: str
    injected_pm: dict[str, Any] | None = None


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="P1",
        name="existing-react-project-is-executable",
        kind="real_pm_allow",
        expected_handoff_allowed=True,
        expected_stage="execution_completed",
        monitor_expectation=(
            "Existing React project, endpoint, route, empty/loading/error states, wrapper path, "
            "and formatting are specified. PM should not block. Review should allow handoff."
        ),
        request=(
            "Existing project knowledge K-FRONTEND-001: the current frontend is React. "
            "Add route /sales-trend to the existing React frontend. Read /api/sales/monthly, "
            "whose response is an array of {month: YYYY-MM, amount: decimal}. Render one line chart "
            "sorted by month ascending. Show 'No sales data' for an empty array, "
            "'Loading sales trend' while loading, and 'Unable to load sales trend' on request failure. "
            "Use x-axis label Month, y-axis label Amount, and format amount as a plain decimal "
            "with two digits. Do not add a new chart dependency; use the existing chart wrapper at "
            "src/components/charts/LineChart.tsx."
        ),
    ),
    Scenario(
        scenario_id="P2",
        name="unsupported-cpp-remains-preference",
        kind="real_pm_allow",
        expected_handoff_allowed=True,
        expected_stage="execution_completed",
        monitor_expectation=(
            "C++ is requested without evidence. PM and Review must keep it as a preference, "
            "while allowing the closed mean/median utility requirement to proceed."
        ),
        request=(
            "Build a one-time local data utility. Input file is C:\\tmp\\stats.csv with a header row "
            "and numeric column value. Data row numbers start at 2. Output file is C:\\tmp\\stats.json. "
            "The output JSON schema is {mean:number|null, median:number|null, count_valid:int, "
            "invalid_rows:[{row:int,value:string,reason:string}]}. Missing or nonnumeric values in "
            "the value column must be reported with row numbers and excluded from mean and median. "
            "If no valid numeric values exist, mean and median must be null. I require C++, but I have "
            "no external reason, platform requirement, customer evidence, or existing project constraint."
        ),
    ),
    Scenario(
        scenario_id="P3",
        name="under-specified-latency-blocks-at-pm",
        kind="real_pm_block",
        expected_handoff_allowed=False,
        expected_stage="pm_blocked",
        monitor_expectation=(
            "The latency goal is material but not executable because record schema, aggregation, "
            "latency statistic, platform, and measurement method are absent. C++ must not become hard."
        ),
        request=(
            "Build a high-frequency binary record processor with end-to-end latency below 1ms. "
            "Input records are fixed binary records and output is aggregated results. Must use C++ "
            "because latency is low. Record schema, aggregation semantics, latency statistic, platform, "
            "measurement method, workload, and data rate are not provided."
        ),
    ),
    Scenario(
        scenario_id="P4",
        name="review-blocks-bad-pm-hard-lock",
        kind="bad_pm_review_block",
        expected_handoff_allowed=False,
        expected_stage="review_blocked",
        monitor_expectation=(
            "This is a defense-in-depth gate. The PM package is intentionally bad: it admits C++ as "
            "hard without evidence. Real Review must reject handoff and runtime must not execute."
        ),
        request=(
            "Build a one-time CSV statistics tool. Input C:\\tmp\\stats.csv has numeric column value. "
            "Output C:\\tmp\\stats.json must contain mean and median. The user says C++ is mandatory "
            "because it looks professional, but no valid evidence is supplied."
        ),
        injected_pm={
            "purpose": "Compute mean and median for a local CSV file.",
            "technical_path_requests": [
                {
                    "request": "Use C++",
                    "hard_constraint_admitted": True,
                    "basis": "User says C++ looks professional.",
                }
            ],
            "deliverable_requests": [
                "Read C:\\tmp\\stats.csv",
                "Write C:\\tmp\\stats.json",
                "Compute mean and median",
            ],
            "hard_constraints": [
                "Input path is C:\\tmp\\stats.csv.",
                "Output path is C:\\tmp\\stats.json.",
                "Output must contain mean and median.",
            ],
            "preferences": [],
            "unresolved_questions": [],
            "status": "ready_for_document",
            "self_audit": {
                "user_pressure_rejected_as_evidence": False,
                "purpose_separated_from_technical_path": True,
            },
        },
    ),
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def run_command(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def codex_thread_id(events_file: Path) -> str | None:
    if not events_file.exists():
        return None
    for line in events_file.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            return str(thread_id) if thread_id else None
    return None


def make_project(output_dir: Path, scenario_id: str, run_id: str) -> Path:
    project = output_dir / f"project_{scenario_id}_{run_id}"
    remote = output_dir / f"remote_{scenario_id}_{run_id}.git"
    for path in (project, remote):
        if path.exists():
            shutil.rmtree(path)
    run_command(["git", "init", "--bare", str(remote)])
    run_command(["git", "clone", str(remote), str(project)])
    run_command(["git", "config", "user.email", "aegis@example.invalid"], cwd=project)
    run_command(["git", "config", "user.name", "Aegis Production Acceptance"], cwd=project)
    (project / "README.md").write_text(
        "# Aegis Production Acceptance Project\n",
        encoding="utf-8",
        newline="\n",
    )
    run_command(["git", "add", "README.md"], cwd=project)
    run_command(["git", "commit", "-m", "initial"], cwd=project)
    run_command(["git", "push", "origin", "HEAD"], cwd=project)
    return project


def find_codex_cmd(explicit: str | None) -> Path:
    candidates = [
        Path(explicit) if explicit else None,
        Path(os.environ.get("AEGIS_CODEX_CMD", "")) if os.environ.get("AEGIS_CODEX_CMD") else None,
        Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise RuntimeError("Codex CLI command not found. Pass --codex-cmd or set AEGIS_CODEX_CMD.")


def parse_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def run_codex_json(
    *,
    codex_cmd: Path,
    prompt: str,
    final_file: Path,
    events_file: Path,
    model: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any] | None, str]:
    completed = subprocess.run(
        [
            str(codex_cmd),
            "exec",
            "-m",
            model,
            "-s",
            "read-only",
            "-c",
            "approval_policy=never",
            "-C",
            str(REPO_ROOT),
            "--output-last-message",
            str(final_file),
            "--json",
        ],
        cwd=REPO_ROOT,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    events_file.write_text(
        (completed.stdout or "") + (completed.stderr or ""),
        encoding="utf-8",
        newline="\n",
    )
    raw = final_file.read_text(encoding="utf-8") if final_file.exists() else ""
    parsed = parse_json_file(final_file)
    return parsed, raw


def pm_prompt(scenario: Scenario) -> str:
    return f"""You are the Aegis Master Project Manager intake agent.
Read this local contract first: src/aegis/modules/master/PM_INTAKE_SEMANTIC_CONTRACT.md.
Analyze exactly one request semantically. Do not use keyword matching or technology-name rules.
Only put blocking requirement-closure questions in unresolved_questions. Do not block on execution-time repository inspection details, ordinary implementation details, or details safely covered by explicit assumptions.

User request:
{scenario.request}

Return strict JSON only with:
purpose, deliverable_requests, technical_path_requests, hard_constraints, preferences, unresolved_questions, status, self_audit.
self_audit must include boolean user_pressure_rejected_as_evidence and purpose_separated_from_technical_path.
"""


def review_prompt(
    *,
    scenario: Scenario,
    pm_output: dict[str, Any],
    requirement_payload: str,
) -> str:
    return f"""You are the Aegis Master Requirement Review agent.
Read this local contract first: src/aegis/modules/master/REQUIREMENT_REVIEW_SEMANTIC_CONTRACT.md.
Review exactly one requirement package with semantic/contextual judgment and first principles.
Do not use keyword matching. PM output is not truth.

Production acceptance expectation:
{scenario.monitor_expectation}

Original request:
{scenario.request}

PM output JSON:
{json.dumps(pm_output, ensure_ascii=False)}

Runtime requirement document JSON:
{requirement_payload}

Return strict JSON only with:
independent_review_performed, pm_output_treated_as_truth, keyword_matching_used,
handoff_allowed, findings, accepted_hard_constraints, rejected_or_preference_constraints,
final_decision, self_audit.
"""


def semantic_payload(pm_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": pm_output.get("purpose") or "",
        "technical_path_requests": pm_output.get("technical_path_requests") or [],
        "deliverable_requests": pm_output.get("deliverable_requests") or [],
        "hard_constraints": pm_output.get("hard_constraints") or [],
        "preferences": pm_output.get("preferences") or [],
        "unresolved_questions": pm_output.get("unresolved_questions") or [],
        "status": pm_output.get("status") or "ready_for_document",
    }


def get_interrupt_value(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    value = interrupts[0].value
    return value if isinstance(value, dict) else None


def validate_pm_output(scenario: Scenario, pm_output: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(pm_output, dict):
        return ["PM output is not valid JSON object"]
    audit = pm_output.get("self_audit") or {}
    if audit.get("purpose_separated_from_technical_path") is not True:
        errors.append("PM did not self-audit purpose/technical-path separation")
    if scenario.kind != "bad_pm_review_block":
        if audit.get("user_pressure_rejected_as_evidence") is not True:
            errors.append("PM did not reject user pressure as evidence")
    if scenario.kind == "real_pm_allow" and pm_output.get("unresolved_questions"):
        errors.append("PM produced blocking unresolved questions for an executable scenario")
    if scenario.kind == "real_pm_block" and not pm_output.get("unresolved_questions"):
        errors.append("PM did not identify blocking unresolved questions")
    return errors


def validate_review_output(review_output: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(review_output, dict):
        return ["Review output is not valid JSON object"]
    if review_output.get("independent_review_performed") is not True:
        errors.append("Review did not report independent review")
    if review_output.get("pm_output_treated_as_truth") is not False:
        errors.append("Review treated PM output as truth or omitted the negative assertion")
    if review_output.get("keyword_matching_used") is not False:
        errors.append("Review used keyword matching or omitted the negative assertion")
    if not isinstance(review_output.get("handoff_allowed"), bool):
        errors.append("Review did not return boolean handoff_allowed")
    return errors


def run_scenario(
    *,
    scenario: Scenario,
    output_dir: Path,
    run_id: str,
    codex_cmd: Path,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    project = make_project(output_dir, scenario.scenario_id, run_id)
    thread_id = f"prod-{scenario.scenario_id}-{run_id[:15]}"

    if scenario.injected_pm is not None:
        pm_output = scenario.injected_pm
        pm_raw = json.dumps(pm_output, ensure_ascii=False, indent=2)
        pm_final_file = output_dir / f"{scenario.scenario_id}_pm_injected.json"
        pm_events_file = output_dir / f"{scenario.scenario_id}_pm_injected.events"
        pm_final_file.write_text(pm_raw, encoding="utf-8", newline="\n")
        pm_events_file.write_text("injected bad PM package for defense-in-depth test\n", encoding="utf-8")
    else:
        pm_final_file = output_dir / f"{scenario.scenario_id}_pm_final.json"
        pm_events_file = output_dir / f"{scenario.scenario_id}_pm_events.jsonl"
        pm_output, pm_raw = run_codex_json(
            codex_cmd=codex_cmd,
            prompt=pm_prompt(scenario),
            final_file=pm_final_file,
            events_file=pm_events_file,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    pm_errors = validate_pm_output(scenario, pm_output)
    if pm_errors and scenario.kind != "bad_pm_review_block":
        return {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "status": "pm_validation_failed",
            "pass": False,
            "pm_errors": pm_errors,
            "pm_output_file": str(pm_final_file),
            "pm_events_file": str(pm_events_file),
            "pm_thread_id": codex_thread_id(pm_events_file),
        }

    with AegisRuntime(project) as runtime:
        first = runtime.run(
            scenario.request,
            thread_id=thread_id,
            master_semantic_analysis=semantic_payload(pm_output or {}),
        )
        first_result = first["result"]
        first_interrupt = get_interrupt_value(first_result)

        if scenario.expected_stage == "pm_blocked":
            blocked = first_interrupt is None and (first_result.get("blockers") or [])
            return {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "status": "pm_blocked" if blocked else "pm_block_expected_but_not_observed",
                "pass": bool(blocked),
                "pm_output_file": str(pm_final_file),
                "pm_events_file": str(pm_events_file),
                "pm_thread_id": codex_thread_id(pm_events_file),
                "thread_id": thread_id,
                "expected_handoff_allowed": scenario.expected_handoff_allowed,
                "runtime_phase": (first_result.get("master_module_state") or {}).get("phase"),
                "blockers": first_result.get("blockers") or [],
                "execution_status": (first_result.get("execution_state") or {}).get("status"),
            }

        if first_interrupt is None:
            return {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "status": "missing_requirement_interrupt",
                "pass": False,
                "pm_output_file": str(pm_final_file),
                "pm_events_file": str(pm_events_file),
                "pm_thread_id": codex_thread_id(pm_events_file),
                "thread_id": thread_id,
                "runtime_result": first_result,
            }

        requirement_ref = first_interrupt["artifact_ref"]
        requirement_path = Path(requirement_ref["machine_data_path"])
        requirement_payload = requirement_path.read_text(encoding="utf-8")

        review_final_file = output_dir / f"{scenario.scenario_id}_review_final.json"
        review_events_file = output_dir / f"{scenario.scenario_id}_review_events.jsonl"
        review_output, review_raw = run_codex_json(
            codex_cmd=codex_cmd,
            prompt=review_prompt(
                scenario=scenario,
                pm_output=pm_output or {},
                requirement_payload=requirement_payload,
            ),
            final_file=review_final_file,
            events_file=review_events_file,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        review_errors = validate_review_output(review_output)
        if review_errors:
            return {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "status": "review_validation_failed",
                "pass": False,
                "review_errors": review_errors,
                "pm_output_file": str(pm_final_file),
                "review_output_file": str(review_final_file),
                "pm_thread_id": codex_thread_id(pm_events_file),
                "review_thread_id": codex_thread_id(review_events_file),
                "thread_id": thread_id,
            }

        second = runtime.resume(
            thread_id,
            {
                "approved": True,
                "comments": "user approved requirement document for production acceptance",
            },
        )
        second_result = second["result"]
        review_interrupt = get_interrupt_value(second_result)
        if review_interrupt is None:
            return {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "status": "missing_review_interrupt",
                "pass": False,
                "thread_id": thread_id,
                "review_output_file": str(review_final_file),
                "review_thread_id": codex_thread_id(review_events_file),
                "runtime_result": second_result,
            }

        handoff_allowed = review_output.get("handoff_allowed") is True
        final = runtime.resume(
            thread_id,
            {
                "approved": handoff_allowed,
                "comments": (
                    "handoff allowed by real Review agent"
                    if handoff_allowed
                    else "handoff blocked by real Review agent"
                ),
            },
        )

    final_result = final["result"]
    module_state = final_result.get("master_module_state") or {}
    execution_state = final_result.get("execution_state") or {}
    closeout = final_result.get("closeout") or {}
    blockers = final_result.get("blockers") or []

    if scenario.expected_stage == "execution_completed":
        stage_ok = execution_state.get("status") == "completed" and closeout.get("status") == "closed"
    elif scenario.expected_stage == "review_blocked":
        stage_ok = (
            handoff_allowed is False
            and execution_state.get("status") == "not_started"
            and bool(blockers)
            and module_state.get("phase") == "review_approval_recorded"
        )
    else:
        stage_ok = False

    expected_handoff_ok = handoff_allowed == scenario.expected_handoff_allowed
    return {
        "scenario_id": scenario.scenario_id,
        "name": scenario.name,
        "status": "completed",
        "pass": bool(stage_ok and expected_handoff_ok),
        "thread_id": thread_id,
        "review_handoff_allowed": handoff_allowed,
        "expected_handoff_allowed": scenario.expected_handoff_allowed,
        "runtime_phase": module_state.get("phase"),
        "execution_status": execution_state.get("status"),
        "closeout_status": closeout.get("status"),
        "blockers": blockers,
        "pm_output_file": str(pm_final_file),
        "pm_events_file": str(pm_events_file),
        "pm_thread_id": codex_thread_id(pm_events_file),
        "review_output_file": str(review_final_file),
        "review_events_file": str(review_events_file),
        "review_thread_id": codex_thread_id(review_events_file),
        "requirement_file": str(requirement_path),
        "artifact_hashes": {
            "pm": sha256_file(pm_final_file),
            "review": sha256_file(review_final_file),
            "requirement": sha256_file(requirement_path),
        },
        "review_final_decision": review_output.get("final_decision"),
    }


def write_report(
    *,
    output_dir: Path,
    results: list[dict[str, Any]],
    model: str,
    codex_cmd: Path,
) -> Path:
    report = output_dir / "MASTER_PRODUCTION_ACCEPTANCE_REPORT.md"
    passed_count = sum(1 for result in results if result.get("pass") is True)
    lines = [
        "# Master Production Acceptance Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Repository: `{REPO_ROOT}`",
        f"Codex command: `{codex_cmd}`",
        f"Agent model requested: `{model}`",
        "",
        "## Acceptance Standard",
        "",
        "- Real PM agent output must be produced by Codex CLI unless the scenario explicitly injects a bad PM package for defense testing.",
        "- Real Review agent output must be produced by Codex CLI for every post-PM handoff decision.",
        "- Runtime may enter Execution only when real Review returns `handoff_allowed=true`.",
        "- PM blocking must prevent requirement approval, Review, and Execution.",
        "- Review blocking must prevent Execution.",
        "- Deterministic runtime closure alone is not accepted as evidence.",
        "",
        "## Summary",
        "",
        f"- Passed scenarios: {passed_count}/{len(results)}",
        f"- Overall decision: {'pass' if passed_count == len(results) else 'fail'}",
        "",
        "## Scenario Matrix",
        "",
        "| scenario | status | expected handoff | review handoff | phase | execution | closeout | pass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            "| {scenario} | {status} | {expected} | {actual} | {phase} | {execution} | {closeout} | {passed} |".format(
                scenario=f"{result.get('scenario_id')} {result.get('name')}",
                status=result.get("status"),
                expected=result.get("expected_handoff_allowed"),
                actual=result.get("review_handoff_allowed"),
                phase=result.get("runtime_phase"),
                execution=result.get("execution_status"),
                closeout=result.get("closeout_status"),
                passed=result.get("pass"),
            )
        )
    lines.extend(["", "## Evidence Files", ""])
    for result in results:
        lines.append(f"### {result.get('scenario_id')} {result.get('name')}")
        for key in (
            "pm_output_file",
            "pm_events_file",
            "pm_thread_id",
            "review_output_file",
            "review_events_file",
            "review_thread_id",
            "requirement_file",
        ):
            if result.get(key):
                lines.append(f"- {key}: `{result[key]}`")
        if result.get("artifact_hashes"):
            lines.append(f"- artifact_hashes: `{json.dumps(result['artifact_hashes'], sort_keys=True)}`")
        if result.get("blockers"):
            lines.append(f"- blockers: `{json.dumps(result['blockers'], ensure_ascii=False)}`")
        if result.get("review_final_decision") is not None:
            lines.append(
                f"- review_final_decision: `{json.dumps(result['review_final_decision'], ensure_ascii=False)}`"
            )
        if result.get("pm_errors"):
            lines.append(f"- pm_errors: `{json.dumps(result['pm_errors'], ensure_ascii=False)}`")
        if result.get("review_errors"):
            lines.append(f"- review_errors: `{json.dumps(result['review_errors'], ensure_ascii=False)}`")
        lines.append("")
    lines.extend(
        [
            "## Boundary",
            "",
            "This acceptance validates the current Master module gate at local-git-project scope.",
            "It does not certify production Execution implementation quality, remote deployment, PR creation, or release behavior.",
            "No remote push, PR, merge, release, deployment, or production sign-off was performed.",
            "",
        ]
    )
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Master production-grade acceptance.")
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "Downloads" / "aegis_master_production_acceptance"),
    )
    parser.add_argument("--codex-cmd", default=None)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--timeout-seconds", type=int, default=420)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(output_dir / "local-app-data")
    codex_cmd = find_codex_cmd(args.codex_cmd)
    run_id = utc_stamp()

    results = [
        run_scenario(
            scenario=scenario,
            output_dir=output_dir,
            run_id=run_id,
            codex_cmd=codex_cmd,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        for scenario in SCENARIOS
    ]
    results_file = output_dir / "master_production_acceptance_results.json"
    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    report = write_report(output_dir=output_dir, results=results, model=args.model, codex_cmd=codex_cmd)
    print(report)
    return 0 if all(result.get("pass") is True for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
