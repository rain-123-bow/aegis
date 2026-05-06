from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    BlockerKind,
    FinalTestReport,
    OwnerHint,
    TestPlan,
    TestRequest,
    TestRoute,
    TestWorkerReport,
)


class TestLeader:
    __test__ = False
    """Deterministic demo Test Leader.

    This runtime uses in-process deterministic workers and a file snapshot supplied
    by the request. It proves the Test Department contract at demo level, not
    production CI, git checkout, or nested-Codex worker orchestration.
    """

    def __init__(self, private_root: str | Path | None = None):
        self.private_root = Path(private_root or ".aegis-test-runtime").resolve()
        self.private_root.mkdir(parents=True, exist_ok=True)

    def run(self, request_payload: dict[str, Any]) -> FinalTestReport:
        request = TestRequest.from_dict(request_payload)
        run_id = f"test-run-{uuid4().hex}"
        run_root = self.private_root / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        self._write_json(run_root / "test_request.json", request.to_dict())

        missing = request.missing_context()
        if missing:
            return self._early_report(
                run_id=run_id,
                run_root=run_root,
                request=request,
                result="request_more_context",
                feedback_kind="missing_context",
                blocker_kind="handoff",
                blocker_scope=", ".join(missing),
                required_next_action="Execution Leader must provide missing Test handoff context.",
                why=f"Missing required Test handoff context: {', '.join(missing)}",
            )

        governance_blocker = self._governance_blocker(request)
        if governance_blocker is not None:
            return self._early_report(
                run_id=run_id,
                run_root=run_root,
                request=request,
                result="blocked",
                feedback_kind="governance_blocker",
                blocker_kind="governance",
                blocker_scope=governance_blocker,
                required_next_action=(
                    "Final Review must inspect governance blocker."
                    if request.governance_review_required
                    else "Execution Leader must remove or correct governance-violating requested action."
                ),
                why="Requested validation or candidate action would bypass governance or policy.",
                next_route="final_review" if request.governance_review_required else "execution",
                requires_governance_review=request.governance_review_required,
            )

        plan = self._make_plan(run_id=run_id, request=request)
        plan_path = run_root / "test_plan.json"
        self._write_json(plan_path, plan.to_dict())

        route_reports: list[TestWorkerReport] = []
        for route in plan.routes:
            route_reports.append(self._run_worker(run_id=run_id, request=request, route=route, run_root=run_root))

        report = self._aggregate(
            run_id=run_id,
            run_root=run_root,
            request=request,
            plan=plan,
            plan_path=plan_path,
            route_reports=route_reports,
        )
        self._write_json(run_root / "final_test_report.json", report.to_dict())
        return report

    def _governance_blocker(self, request: TestRequest) -> str | None:
        forbidden = set(request.forbidden_actions)
        for action in request.requested_actions:
            if action in forbidden:
                return action
            lowered = action.lower()
            if any(term in lowered for term in ("bypass", "force merge", "release", "remote push", "main merge")):
                return action
        return None

    def _make_plan(self, *, run_id: str, request: TestRequest) -> TestPlan:
        if request.route_specs:
            routes = request.route_specs
        else:
            routes = self._generate_default_routes(request)
        if not routes:
            routes = [
                TestRoute(
                    route_id="route.changed_files_exist",
                    route_type="inspection",
                    mandatory=True,
                    scope=list(request.changed_files),
                    method="file_snapshot_inspection",
                    required_files=list(request.changed_files),
                    inspection_steps=["Verify every changed file exists in the candidate snapshot."],
                    evidence_requirements=["worker report", "file snapshot"],
                )
            ]
        route_ids = {route.route_id for route in routes}
        if len(route_ids) != len(routes):
            raise ValueError("duplicate route_id in Test plan")
        mandatory = [route.route_id for route in routes if route.mandatory]
        optional = [route.route_id for route in routes if not route.mandatory]
        return TestPlan(
            plan_id=f"{run_id}-plan",
            request_id=request.request_id,
            objective=request.objective,
            validation_scope=list(request.changed_files),
            mandatory_routes=mandatory,
            optional_routes=optional,
            routes=routes,
            route_independence=[
                "Routes are read-only over the candidate file snapshot.",
                "Each route writes its own artifact folder under Test Leader private runtime root.",
                "No route is allowed to modify implementation code.",
            ],
            artifact_plan=["test_plan.json", "route report JSON files", "reproducibility_set.json", "artifact_manifest.json"],
        )

    def _generate_default_routes(self, request: TestRequest) -> list[TestRoute]:
        routes: list[TestRoute] = []
        for path in request.changed_files:
            route_id = f"route.{self._slug(path)}"
            inspection_steps = [f"Verify {path} exists in the candidate snapshot."]
            expected_patterns: dict[str, str] = {}
            lower_text = " ".join(request.success_criteria + request.expected_test_focus + request.known_risks).lower()
            if ("final summary" in lower_text or "summary" in lower_text) and any(
                token in path.lower() for token in ("fixture", "output", "result")
            ):
                expected_patterns[path] = "final summary"
                inspection_steps.append(f"Verify {path} contains the required final summary marker.")
            routes.append(
                TestRoute(
                    route_id=route_id,
                    route_type="inspection",
                    mandatory=True,
                    scope=[path],
                    method="file_snapshot_inspection",
                    required_files=[path],
                    expected_patterns=expected_patterns,
                    commands=[f"inspect {path}"],
                    inspection_steps=inspection_steps,
                    evidence_requirements=["worker report", "file snapshot"],
                    failure_owner_files=[path],
                )
            )
        return routes

    def _run_worker(
        self,
        *,
        run_id: str,
        request: TestRequest,
        route: TestRoute,
        run_root: Path,
    ) -> TestWorkerReport:
        worker_id = f"{run_id}__{route.route_id}__worker"
        route_root = run_root / "routes" / self._slug(route.route_id)
        route_root.mkdir(parents=True, exist_ok=True)

        commands_run: list[dict[str, Any]] = []
        logs: list[str] = []
        artifacts: list[str] = []
        observations: list[str] = []
        failure_signatures: list[str] = []
        covered_scope: list[str] = []
        uncovered_scope: list[str] = []
        blocker_kind: BlockerKind | None = None
        blocker_scope = ""

        if route.simulate_result == "blocked":
            blocker_kind = route.blocker_kind or "unknown"
            blocker_scope = route.blocker_scope or ", ".join(route.scope)
            observations.append(f"Route blocked by {blocker_kind}: {blocker_scope}")
            result = "blocked"
        elif route.simulate_result == "inconclusive":
            observations.append("Route evidence is intentionally inconclusive in this deterministic fixture.")
            result = "inconclusive"
        else:
            result = "passed"
            for path in route.required_files:
                command = {"command": f"inspect {path}", "exit_code": 0}
                if path not in request.candidate_files:
                    command["exit_code"] = 1
                    result = "failed"
                    failure_signatures.append(f"missing_required_file:{path}")
                    observations.append(f"{path} is missing from candidate snapshot.")
                    uncovered_scope.append(path)
                else:
                    observations.append(f"{path} exists in candidate snapshot.")
                    covered_scope.append(path)
                commands_run.append(command)

            for path, pattern in route.expected_patterns.items():
                command = {"command": f"contains {path} {pattern!r}", "exit_code": 0}
                content = request.candidate_files.get(path, "")
                if path not in request.candidate_files:
                    command["exit_code"] = 1
                    result = "failed"
                    failure_signatures.append(f"missing_required_file:{path}")
                    observations.append(f"{path} is missing and cannot satisfy pattern {pattern!r}.")
                    if path not in uncovered_scope:
                        uncovered_scope.append(path)
                elif pattern not in content:
                    command["exit_code"] = 1
                    result = "failed"
                    failure_signatures.append(f"missing_pattern:{path}:{pattern}")
                    observations.append(f"{path} does not contain required pattern {pattern!r}.")
                    if path not in covered_scope:
                        covered_scope.append(path)
                else:
                    observations.append(f"{path} contains required pattern {pattern!r}.")
                    if path not in covered_scope:
                        covered_scope.append(path)
                commands_run.append(command)

            if route.simulate_result == "failed":
                result = "failed"
                failure_signatures.append("simulated_failure")
                observations.append("Route was configured to simulate candidate failure.")

        owner_hint = self._owner_hint(request=request, route=route, result=result)

        stdout_path = route_root / "stdout.txt"
        stderr_path = route_root / "stderr.txt"
        stdout_path.write_text("\n".join(observations) + "\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        logs.extend([str(stdout_path), str(stderr_path)])

        snapshot_path = route_root / "candidate_snapshot.json"
        snapshot = {path: request.candidate_files.get(path, None) for path in route.required_files or route.scope}
        self._write_json(snapshot_path, snapshot)
        artifacts.append(str(snapshot_path))

        evidence_refs = [str(stdout_path), str(snapshot_path)]
        test_data_refs = [str(route_root / "worker_report.json")]

        if result == "failed" and not failure_signatures:
            result = "inconclusive"
            observations.append("Downgraded to inconclusive because failed result lacked a failure signature.")

        report = TestWorkerReport(
            route_id=route.route_id,
            worker_id=worker_id,
            route_scope=list(route.scope),
            commands_run=commands_run,
            inspection_steps_run=list(route.inspection_steps),
            logs=logs,
            artifacts=artifacts,
            environment={
                "runtime": "deterministic-demo",
                "execution_mode": "in_process_worker",
                "candidate_source": "request.candidate_files snapshot",
            },
            covered_scope=sorted(set(covered_scope)),
            uncovered_scope=sorted(set(uncovered_scope)),
            observations=observations,
            route_result=result,  # type: ignore[arg-type]
            failure_signatures=sorted(set(failure_signatures)),
            evidence_refs=evidence_refs,
            test_data_refs=test_data_refs,
            owner_hint=owner_hint,
            blocker_kind=blocker_kind,
            blocker_scope=blocker_scope,
            why=self._route_why(result=result, blocker_kind=blocker_kind),
            assumptions=["candidate_files snapshot represents the integrated candidate for this demo runtime"],
            material_conditions=[request.final_code_ref, request.implementation_candidate_ref],
        )
        self._write_json(route_root / "worker_report.json", report.to_dict())
        return report

    def _aggregate(
        self,
        *,
        run_id: str,
        run_root: Path,
        request: TestRequest,
        plan: TestPlan,
        plan_path: Path,
        route_reports: list[TestWorkerReport],
    ) -> FinalTestReport:
        route_dicts = [report.to_dict() for report in route_reports]
        covered = sorted({scope for report in route_reports for scope in report.covered_scope})
        uncovered = sorted(set(request.uncovered_scope_override) | {scope for report in route_reports for scope in report.uncovered_scope})
        evidence_refs = sorted({ref for report in route_reports for ref in report.evidence_refs})
        test_data_refs = sorted({ref for report in route_reports for ref in report.test_data_refs})
        failure_signatures = sorted({sig for report in route_reports for sig in report.failure_signatures})

        mandatory_by_id = set(plan.mandatory_routes)
        mandatory_reports = [report for report in route_reports if report.route_id in mandatory_by_id]

        result = "passed"
        feedback_kind = "success"
        next_route = "final_review"
        blocker_kind: BlockerKind | None = None
        blocker_scope = ""
        requires_governance_review = False
        required_next_action = "Final Review should inspect final code and Test evidence."
        owner_hint = OwnerHint(owner_type="none")

        blocked_reports = [report for report in mandatory_reports if report.route_result == "blocked"]
        failed_reports = [report for report in mandatory_reports if report.route_result == "failed"]
        inconclusive_reports = [report for report in mandatory_reports if report.route_result == "inconclusive"]

        if blocked_reports:
            result = "blocked"
            feedback_kind = "blocked"
            first = blocked_reports[0]
            blocker_kind = first.blocker_kind or "unknown"
            blocker_scope = first.blocker_scope or ", ".join(first.route_scope)
            requires_governance_review = blocker_kind == "governance"
            next_route = "final_review" if requires_governance_review and request.governance_review_required else "execution"
            if requires_governance_review:
                feedback_kind = "governance_blocker"
                required_next_action = (
                    "Final Review must inspect governance blocker."
                    if next_route == "final_review"
                    else "Execution Leader must remove governance-violating candidate action."
                )
            else:
                required_next_action = "Execution Leader must address blocked Test prerequisite or candidate handoff."
        elif failed_reports:
            result = "failed"
            feedback_kind = "failure"
            next_route = "execution"
            owner_hint = self._aggregate_owner_hint(failed_reports)
            required_next_action = "Execution Leader must triage Test evidence and assign rework."
        elif inconclusive_reports:
            result = "inconclusive"
            feedback_kind = "inconclusive"
            next_route = "execution"
            owner_hint = OwnerHint(owner_type="none")
            required_next_action = "Execution Leader and Test Leader must produce stronger evidence before pass/fail."
        elif uncovered:
            result = "passed_with_scope_limit"
            feedback_kind = "success"
            next_route = "final_review"
            required_next_action = "Final Review must decide whether explicit uncovered scope is acceptable."
        else:
            result = "passed"
            feedback_kind = "success"
            next_route = "final_review"

        reproducibility_path = run_root / "reproducibility_set.json"
        artifact_manifest_path = run_root / "artifact_manifest.json"
        self._write_json(
            reproducibility_path,
            {
                "request_id": request.request_id,
                "test_plan_ref": str(plan_path),
                "routes": [route.to_dict() for route in plan.routes],
                "commands": [command for report in route_reports for command in report.commands_run],
                "environment": {
                    "runtime": "deterministic-demo",
                    "candidate_source": "request.candidate_files snapshot",
                },
                "input_refs": {
                    "base_branch": request.base_branch,
                    "integration_branch": request.integration_branch,
                    "implementation_candidate_ref": request.implementation_candidate_ref,
                    "final_code_ref": request.final_code_ref,
                },
                "expected_results": request.success_criteria,
                "actual_result_summary": result,
                "evidence_refs": evidence_refs,
                "artifact_manifest_ref": str(artifact_manifest_path),
            },
        )
        self._write_json(
            artifact_manifest_path,
            {
                "run_id": run_id,
                "artifacts": sorted(set(evidence_refs + test_data_refs + [str(plan_path), str(reproducibility_path)])),
                "cleanup_policy": "Raw artifacts may be pruned only after final report, manifest, and reproducibility set exist.",
            },
        )

        decision = "send_result_to_final_review" if next_route == "final_review" else "send_feedback_to_execution"
        return FinalTestReport(
            run_id=run_id,
            request_id=request.request_id,
            result=result,  # type: ignore[arg-type]
            feedback_kind=feedback_kind,  # type: ignore[arg-type]
            next_route=next_route,  # type: ignore[arg-type]
            decision=decision,
            final_code_ref=request.final_code_ref,
            implementation_candidate_ref=request.implementation_candidate_ref,
            test_plan_ref=str(plan_path),
            route_reports=route_dicts,
            test_data_refs=test_data_refs,
            evidence_refs=evidence_refs,
            coverage_summary={"covered_scope": covered, "uncovered_scope": uncovered},
            covered_scope=covered,
            uncovered_scope=uncovered,
            failure_signatures=failure_signatures,
            owner_hint=owner_hint,
            blocker_kind=blocker_kind,
            blocker_scope=blocker_scope,
            requires_governance_review=requires_governance_review,
            required_next_action=required_next_action,
            known_limits=uncovered,
            assumptions=["deterministic demo validates supplied candidate snapshot, not real git checkout"],
            material_conditions=[request.base_branch, request.integration_branch, request.final_code_ref],
            reproducibility_set_ref=str(reproducibility_path),
            artifact_manifest_ref=str(artifact_manifest_path),
            artifact_paths={
                "test_request": str(run_root / "test_request.json"),
                "test_plan": str(plan_path),
                "reproducibility_set": str(reproducibility_path),
                "artifact_manifest": str(artifact_manifest_path),
                "final_report": str(run_root / "final_test_report.json"),
            },
        )

    def _early_report(
        self,
        *,
        run_id: str,
        run_root: Path,
        request: TestRequest,
        result: str,
        feedback_kind: str,
        blocker_kind: BlockerKind | None,
        blocker_scope: str,
        required_next_action: str,
        why: str,
        next_route: str = "execution",
        requires_governance_review: bool = False,
    ) -> FinalTestReport:
        reproducibility_path = run_root / "reproducibility_set.json"
        artifact_manifest_path = run_root / "artifact_manifest.json"
        self._write_json(
            reproducibility_path,
            {
                "request_id": request.request_id,
                "input_refs": {
                    "base_branch": request.base_branch,
                    "integration_branch": request.integration_branch,
                    "implementation_candidate_ref": request.implementation_candidate_ref,
                    "final_code_ref": request.final_code_ref,
                },
                "actual_result_summary": result,
                "why": why,
            },
        )
        self._write_json(
            artifact_manifest_path,
            {
                "run_id": run_id,
                "artifacts": [str(run_root / "test_request.json"), str(reproducibility_path)],
                "cleanup_policy": "Retain minimal reproducibility set for admission or blocker result.",
            },
        )
        report = FinalTestReport(
            run_id=run_id,
            request_id=request.request_id,
            result=result,  # type: ignore[arg-type]
            feedback_kind=feedback_kind,  # type: ignore[arg-type]
            next_route=next_route,  # type: ignore[arg-type]
            decision="send_result_to_final_review" if next_route == "final_review" else "send_feedback_to_execution",
            final_code_ref=request.final_code_ref,
            implementation_candidate_ref=request.implementation_candidate_ref,
            test_plan_ref="",
            route_reports=[],
            test_data_refs=[],
            evidence_refs=[str(run_root / "test_request.json")],
            coverage_summary={"covered_scope": [], "uncovered_scope": list(request.changed_files)},
            covered_scope=[],
            uncovered_scope=list(request.changed_files),
            failure_signatures=[],
            owner_hint=OwnerHint(owner_type="none"),
            blocker_kind=blocker_kind,
            blocker_scope=blocker_scope,
            requires_governance_review=requires_governance_review,
            required_next_action=required_next_action,
            known_limits=list(request.changed_files),
            assumptions=["admission or blocker result occurred before route execution"],
            material_conditions=[request.base_branch, request.integration_branch, request.final_code_ref],
            reproducibility_set_ref=str(reproducibility_path),
            artifact_manifest_ref=str(artifact_manifest_path),
            artifact_paths={
                "test_request": str(run_root / "test_request.json"),
                "reproducibility_set": str(reproducibility_path),
                "artifact_manifest": str(artifact_manifest_path),
                "final_report": str(run_root / "final_test_report.json"),
            },
        )
        self._write_json(run_root / "final_test_report.json", report.to_dict())
        return report

    def _owner_hint(self, *, request: TestRequest, route: TestRoute, result: str) -> OwnerHint:
        if result != "failed":
            return OwnerHint(owner_type="none")
        owner_files = route.failure_owner_files or route.required_files or list(route.expected_patterns)
        owners = {request.ownership_map.get(path, "") for path in owner_files}
        owners.discard("")
        if len(owners) == 1:
            owner = next(iter(owners))
            if owner == "integration":
                return OwnerHint(owner_type="integration")
            return OwnerHint(owner_type="group", owner_id=owner)
        return OwnerHint(owner_type="ambiguous")

    def _aggregate_owner_hint(self, failed_reports: list[TestWorkerReport]) -> OwnerHint:
        hints = [report.owner_hint for report in failed_reports]
        typed = {(hint.owner_type, hint.owner_id) for hint in hints}
        if len(typed) == 1:
            return hints[0]
        return OwnerHint(owner_type="ambiguous")

    def _route_why(self, *, result: str, blocker_kind: BlockerKind | None) -> str:
        if result == "passed":
            return "Assigned route checks passed and assigned scope was covered."
        if result == "failed":
            return "Evidence proves the candidate violated an assigned mandatory route expectation."
        if result == "blocked":
            return f"Route could not proceed because blocker_kind={blocker_kind or 'unknown'}."
        return "Route evidence is insufficient to prove pass or fail."

    def _slug(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "item"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
