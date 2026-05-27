from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PHASE = "phase28a_test_real_run_monitoring_hardening"
ALLOWED_FINAL_RESULTS = {"passed", "passed_with_scope_limit", "failed", "inconclusive", "blocked", "request_more_context"}
INVALID_BLUETOOTHCTL_ATTRIBUTE_PATTERNS = ("bluetoothctl list-attributes address", "bluetoothctl list-attributes <address>")

class MonitoringHardeningError(ValueError):
    pass

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class MonitoringHardeningValidationResult:
    validation_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    route_count: int = 0
    checked_rule_count: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    environment_preflight_verified: bool = False
    thread_identity_verified: bool = False
    launcher_timeout_boundary_verified: bool = False
    invalid_tooling_exclusion_verified: bool = False
    scope_limited_result_verified: bool = False
    production_test_lifecycle_closure_claimed: bool = False
    global_causal_truth_merge_performed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_result_id": self.validation_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "route_count": self.route_count,
            "checked_rule_count": self.checked_rule_count,
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "environment_preflight_verified": self.environment_preflight_verified,
            "thread_identity_verified": self.thread_identity_verified,
            "launcher_timeout_boundary_verified": self.launcher_timeout_boundary_verified,
            "invalid_tooling_exclusion_verified": self.invalid_tooling_exclusion_verified,
            "scope_limited_result_verified": self.scope_limited_result_verified,
            "production_test_lifecycle_closure_claimed": self.production_test_lifecycle_closure_claimed,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "created_at": self.created_at,
        }

def load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MonitoringHardeningError(f"file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise MonitoringHardeningError(f"file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MonitoringHardeningError(f"file must contain a JSON object: {p}")
    return payload

def validate_real_run_monitoring_package_file(path: str | Path) -> MonitoringHardeningValidationResult:
    return validate_real_run_monitoring_package(load_json_object(path))

def validate_real_run_monitoring_package(package: dict[str, Any]) -> MonitoringHardeningValidationResult:
    if not isinstance(package, dict):
        raise MonitoringHardeningError("package must be a JSON object")
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checked = 0
    checked += validate_test_environment_preflight(package, violations=violations, warnings=warnings)
    checked += validate_test_artifact_consistency(package, violations=violations, warnings=warnings)
    checked += validate_invalid_tooling_exclusion(package, violations=violations, warnings=warnings)
    checked += validate_scope_limited_result(package, violations=violations, warnings=warnings)
    checked += _check_boundary_flags(package, violations)
    routes = _routes(package)
    status = "validated" if not violations else "rejected"
    return MonitoringHardeningValidationResult(
        validation_result_id=f"phase28a-monitoring-{uuid4().hex}",
        phase=PHASE,
        status=status,
        decision="accepted_test_real_run_monitoring_hardening" if status == "validated" else "rejected",
        reason="Validated real-run Test monitoring hardening rules." if status == "validated" else "Real-run Test monitoring hardening validation failed.",
        route_count=len(routes),
        checked_rule_count=checked,
        violations=violations,
        warnings=warnings,
        environment_preflight_verified=not any(v["field"].startswith("test_routes") or v["field"].startswith("environment_preflight") for v in violations),
        thread_identity_verified=not any("thread_id" in v["field"] or v["field"].startswith("worker_") for v in violations),
        launcher_timeout_boundary_verified=not any("launcher_timeout" in v["field"] for v in violations),
        invalid_tooling_exclusion_verified=not any("invalid_tooling" in v["field"] or "tooling" in v["field"] for v in violations),
        scope_limited_result_verified=not any(v["field"].startswith("final_test_result") or v["field"].startswith("business_validation") for v in violations),
        production_test_lifecycle_closure_claimed=bool(package.get("production_test_lifecycle_closure_claimed", False)),
        global_causal_truth_merge_performed=bool(package.get("global_causal_truth_merge_performed", False)),
    )

def validate_test_environment_preflight(package: dict[str, Any], *, violations=None, warnings=None) -> int:
    violations = violations if violations is not None else []
    warnings = warnings if warnings is not None else []
    checked = 0
    for index, route in enumerate(_routes(package)):
        checked += 1
        route_id = str(route.get("route_id") or f"route[{index}]")
        commands = _string_list(route.get("commands", []))
        command_tools = [_first_token(command) for command in commands if _first_token(command)]
        preflight = _ref(route.get("environment_preflight"))
        superseded_by = route.get("superseded_by")
        route_result = route.get("route_result") or route.get("result")
        if command_tools and not preflight:
            violations.append(_violation(f"test_routes.{route_id}.environment_preflight", "command routes require environment_preflight before route execution."))
            continue
        if preflight:
            required_tools = _string_list(preflight.get("required_tools", []))
            available_tools = set(_string_list(preflight.get("available_tools", [])))
            missing_tools = set(_string_list(preflight.get("missing_tools", [])))
            if not required_tools and command_tools:
                warnings.append(_warning(f"test_routes.{route_id}.environment_preflight.required_tools", "environment_preflight should list command tools explicitly."))
            for tool in required_tools:
                if tool not in available_tools and tool not in missing_tools:
                    violations.append(_violation(f"test_routes.{route_id}.environment_preflight.missing_tools", f"required tool {tool} must be recorded as available or missing."))
            if missing_tools:
                if not superseded_by and not (route_result == "blocked" and route.get("blocker_kind") in {"environment", "dependency"}):
                    violations.append(_violation(f"test_routes.{route_id}.route_result", "route with missing required tools must be blocked/environment or explicitly superseded."))
                if route.get("candidate_failure_evidence_used") is True:
                    violations.append(_violation(f"test_routes.{route_id}.candidate_failure_evidence_used", "missing environment tools must not be used as candidate failure evidence."))
    return checked

def validate_test_artifact_consistency(package: dict[str, Any], *, violations=None, warnings=None) -> int:
    violations = violations if violations is not None else []
    warnings = warnings if warnings is not None else []
    checked = 0
    creation_by_route = _by_route(package.get("worker_creation_records") or package.get("worker_creation_requests") or [])
    proof_by_route = _by_route(package.get("worker_proofs") or [])
    output_by_route = _by_route(package.get("worker_outputs") or [])
    supervision_by_route = _by_route(package.get("worker_supervision_records") or [])
    superseded_outputs = _by_route(package.get("superseded_worker_outputs") or [])
    correction_reports = _by_route(package.get("thread_id_correction_reports") or package.get("correction_reports") or [])
    all_routes = sorted(set(creation_by_route) | set(proof_by_route) | set(output_by_route) | set(supervision_by_route))
    for route_id in all_routes:
        checked += 1
        creation = creation_by_route.get(route_id, {})
        proof = proof_by_route.get(route_id, {})
        output = output_by_route.get(route_id, {})
        supervision = supervision_by_route.get(route_id, {})
        creation_thread = creation.get("thread_id")
        proof_thread = proof.get("thread_id")
        output_thread = output.get("thread_id")
        supervision_thread = supervision.get("thread_id")
        for name, value in (("creation", creation_thread), ("proof", proof_thread), ("output", output_thread), ("supervision", supervision_thread)):
            if (name == "supervision" and not supervision) or (name == "creation" and not creation):
                continue
            if _missing(value):
                violations.append(_violation(f"worker_{name}.{route_id}.thread_id", f"{name} record requires non-empty thread_id."))
        expected_threads = {value for value in (creation_thread, proof_thread, output_thread, supervision_thread) if not _missing(value)}
        if len(expected_threads) > 1:
            correction = correction_reports.get(route_id, {})
            if not correction:
                violations.append(_violation(f"worker_thread_identity.{route_id}", "creation/proof/output/supervision thread_id mismatch requires an explicit correction report."))
            else:
                if correction.get("status") not in {"corrected", "superseded_wrong_output", "accepted_correction"}:
                    violations.append(_violation(f"thread_id_correction_reports.{route_id}.status", "thread_id correction report must mark the mismatch corrected or superseded."))
                if _missing(correction.get("sha256")):
                    violations.append(_violation(f"thread_id_correction_reports.{route_id}.sha256", "thread_id correction report requires sha256 evidence."))
                if correction.get("valid_thread_id") not in expected_threads:
                    violations.append(_violation(f"thread_id_correction_reports.{route_id}.valid_thread_id", "correction valid_thread_id must match one of the observed thread ids."))
                if not superseded_outputs.get(route_id):
                    warnings.append(_warning(f"superseded_worker_outputs.{route_id}", "thread mismatch was corrected, but no superseded output record was provided."))
        if supervision:
            if supervision.get("launcher_status") == "launcher_timeout":
                if supervision.get("worker_failed") is True or supervision.get("child_status") in {"failed", "worker_failed"}:
                    violations.append(_violation(f"worker_supervision_records.{route_id}.launcher_timeout", "launcher_timeout with captured thread_id must not be treated as worker failure."))
                if supervision.get("recovery_attempted") is not True:
                    violations.append(_violation(f"worker_supervision_records.{route_id}.recovery_attempted", "launcher_timeout must trigger recovery before final failure."))
                if supervision.get("duplicate_worker_created_for_same_route") is True:
                    violations.append(_violation(f"worker_supervision_records.{route_id}.duplicate_worker_created_for_same_route", "do not create duplicate workers solely because launcher timeout occurred."))
    return checked

def validate_invalid_tooling_exclusion(package: dict[str, Any], *, violations=None, warnings=None) -> int:
    violations = violations if violations is not None else []
    checked = 0
    invalid_records = _as_dict_list(package.get("invalid_tooling_records") or package.get("tooling_limitations") or [])
    final_result = _ref(package.get("final_test_result") or package.get("final_report"))
    failure_signatures = " ".join(_string_list(final_result.get("failure_signatures", []))).lower()
    evidence_refs = " ".join(_string_list(final_result.get("evidence_refs", []))).lower()
    for record in invalid_records:
        checked += 1
        command = str(record.get("command", "")).lower()
        excluded = record.get("excluded_from_candidate_failure") is True
        if any(pattern in command for pattern in INVALID_BLUETOOTHCTL_ATTRIBUTE_PATTERNS):
            if not excluded:
                violations.append(_violation("invalid_tooling_records.excluded_from_candidate_failure", "invalid bluetoothctl list-attributes ADDRESS command must be excluded from candidate-failure evidence."))
            if final_result.get("result") == "failed" and ("list-attributes" in failure_signatures or "list-attributes" in evidence_refs):
                violations.append(_violation("final_test_result.failure_signatures", "invalid BlueZ command failure must not be used as product failure evidence."))
    return checked

def validate_scope_limited_result(package: dict[str, Any], *, violations=None, warnings=None) -> int:
    violations = violations if violations is not None else []
    checked = 1
    final_result = _ref(package.get("final_test_result") or package.get("final_report"))
    result = final_result.get("result")
    if result not in ALLOWED_FINAL_RESULTS:
        violations.append(_violation("final_test_result.result", "final result label is invalid."))
        return checked
    business = _ref(package.get("business_validation") or package.get("ble_business_validation"))
    requires_business = business.get("business_write_notify_required") is True or business.get("business_transaction_required") is True
    proven = business.get("business_write_notify_proven") is True or business.get("end_to_end_business_transaction_proven") is True
    missing = _string_list(business.get("missing_business_scope", []))
    if requires_business and not proven:
        if result == "passed":
            violations.append(_violation("final_test_result.result", "full passed is forbidden when required BLE business write/notify is not proven."))
        if result == "passed_with_scope_limit":
            known_limits = _string_list(final_result.get("known_limits", []))
            uncovered_scope = _string_list(final_result.get("uncovered_scope", []))
            if not known_limits or not uncovered_scope:
                violations.append(_violation("final_test_result.known_limits", "passed_with_scope_limit requires explicit known_limits and uncovered_scope."))
            joined_uncovered_scope = " ".join(uncovered_scope).lower()
            if missing and not all(item.lower() in joined_uncovered_scope for item in missing):
                violations.append(_violation("final_test_result.uncovered_scope", "missing BLE business scope must be preserved in uncovered_scope."))
        elif result not in {"blocked", "inconclusive", "passed_with_scope_limit"}:
            violations.append(_violation("final_test_result.result", "missing required BLE business proof must be blocked, inconclusive, or passed_with_scope_limit with explicit limits."))
    return checked

def _check_boundary_flags(package: dict[str, Any], violations: list[dict[str, Any]]) -> int:
    checked = 1
    final_result = _ref(package.get("final_test_result") or package.get("final_report"))
    boundaries = _ref(package.get("boundaries"))
    for source, prefix in ((package, "package"), (final_result, "final_test_result"), (boundaries, "boundaries")):
        for field in ("production_test_lifecycle_closure_claimed", "production_ci_closure_claimed", "remote_branch_governance_closure_claimed", "remote_push_performed", "pull_request_created", "remote_merge_performed", "release_performed", "deployment_performed", "external_signoff_performed", "production_store_write_performed", "global_causal_truth_merge_performed"):
            if source.get(field) is True:
                violations.append(_violation(f"{prefix}.{field}", f"{field} must remain false in Phase 28A."))
    return checked

def _routes(package: dict[str, Any]) -> list[dict[str, Any]]:
    routes = package.get("test_routes") or package.get("routes") or _ref(package.get("test_plan")).get("routes") or []
    return _as_dict_list(routes)
def _by_route(value: Any) -> dict[str, dict[str, Any]]:
    return {str(item.get("route_id")): item for item in _as_dict_list(value) if item.get("route_id")}
def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    return [] if value is None or not isinstance(value, list) else [dict(item) for item in value if isinstance(item, dict)]
def _ref(value: Any) -> dict[str, Any]: return dict(value) if isinstance(value, dict) else {}
def _string_list(value: Any) -> list[str]:
    if value is None: return []
    if isinstance(value, str): return [value] if value else []
    if isinstance(value, list): return [str(item) for item in value if item is not None and str(item) != ""]
    return []
def _missing(value: Any) -> bool: return value is None or value == "" or value == []
def _first_token(command: str) -> str:
    command = command.strip(); return command.split()[0] if command else ""
def _violation(field: str, reason: str) -> dict[str, Any]: return {"field": field, "reason": reason}
def _warning(field: str, reason: str) -> dict[str, Any]: return {"field": field, "reason": reason}

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Aegis Test real-run monitoring hardening artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate one real-run monitoring package JSON artifact.")
    validate.add_argument("--package", required=True, help="Path to monitoring package JSON.")
    validate.add_argument("--output", help="Optional output path for validation result JSON.")
    return parser

def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "validate":
        result = validate_real_run_monitoring_package_file(args.package).to_dict()
        if args.output:
            output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)); return
    raise SystemExit(f"unknown command: {args.command}")
if __name__ == "__main__": main()
