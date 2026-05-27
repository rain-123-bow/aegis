from __future__ import annotations
from aegis_test_runtime.monitoring_hardening import validate_real_run_monitoring_package

def _valid_package() -> dict:
    return {
        "run_id": "T20260526-002",
        "test_routes": [
            {"route_id": "R1-build-static-protocol-v1", "commands": ["ninja -C build"], "route_result": "blocked", "blocker_kind": "environment", "superseded_by": "R1-build-static-protocol-v2", "candidate_failure_evidence_used": False, "environment_preflight": {"required_tools": ["ninja"], "available_tools": ["make"], "missing_tools": ["ninja"]}},
            {"route_id": "R1-build-static-protocol-v2", "commands": ["make -C build"], "route_result": "passed", "environment_preflight": {"required_tools": ["make"], "available_tools": ["make"], "missing_tools": []}},
            {"route_id": "R2-runtime-ble", "commands": ["bluetoothctl connect AA:BB:CC:DD:EE:FF"], "route_result": "passed", "environment_preflight": {"required_tools": ["bluetoothctl"], "available_tools": ["bluetoothctl"], "missing_tools": []}},
        ],
        "worker_creation_records": [{"route_id": "R2-runtime-ble", "thread_id": "thread-good"}],
        "worker_supervision_records": [{"route_id": "R2-runtime-ble", "thread_id": "thread-good", "launcher_status": "launcher_timeout", "child_status": "result_recovered", "recovery_attempted": True, "duplicate_worker_created_for_same_route": False}],
        "worker_proofs": [{"route_id": "R2-runtime-ble", "thread_id": "thread-good"}],
        "worker_outputs": [{"route_id": "R2-runtime-ble", "thread_id": "thread-good"}],
        "invalid_tooling_records": [{"command": "bluetoothctl list-attributes ADDRESS", "reason": "not valid in observed BlueZ main-menu context", "excluded_from_candidate_failure": True}],
        "business_validation": {"business_write_notify_required": True, "business_write_notify_proven": False, "missing_business_scope": ["deterministic business write payload", "expected notification or read response", "end-to-end business command transaction"], "covered_scope": ["advertisement_visibility", "service_discovery"]},
        "final_test_result": {"result": "passed_with_scope_limit", "next_route": "final_review", "known_limits": ["deterministic business write payload", "expected notification or read response", "end-to-end business command transaction"], "uncovered_scope": ["deterministic business write payload", "expected notification or read response", "end-to-end business command transaction"], "failure_signatures": [], "evidence_refs": ["test_result.yaml"]},
        "boundaries": {"production_test_lifecycle_closure_claimed": False, "global_causal_truth_merge_performed": False},
    }
def _assert_rejected(package: dict, marker: str) -> None:
    result = validate_real_run_monitoring_package(package)
    assert result.status == "rejected"
    assert any(marker in item["field"] or marker in item["reason"] for item in result.violations), result.to_dict()
def test_valid_real_run_monitoring_package_is_accepted() -> None:
    result = validate_real_run_monitoring_package(_valid_package()); assert result.status == "validated"; assert result.decision == "accepted_test_real_run_monitoring_hardening"
def test_command_route_without_preflight_rejects() -> None:
    package = _valid_package(); package["test_routes"][1].pop("environment_preflight"); _assert_rejected(package, "environment_preflight")
def test_missing_tool_must_block_or_be_superseded() -> None:
    package = _valid_package(); package["test_routes"][0].pop("superseded_by"); package["test_routes"][0]["route_result"] = "failed"; _assert_rejected(package, "route_result")
def test_missing_tool_must_not_be_candidate_failure_evidence() -> None:
    package = _valid_package(); package["test_routes"][0]["candidate_failure_evidence_used"] = True; _assert_rejected(package, "candidate_failure_evidence_used")
def test_thread_mismatch_rejects_without_correction_report() -> None:
    package = _valid_package(); package["worker_outputs"][0]["thread_id"] = "thread-bad"; _assert_rejected(package, "worker_thread_identity")
def test_thread_mismatch_accepts_with_correction_report() -> None:
    package = _valid_package(); package["worker_outputs"][0]["thread_id"] = "thread-old"; package["superseded_worker_outputs"] = [{"route_id": "R2-runtime-ble", "thread_id": "thread-old", "status": "superseded"}]; package["thread_id_correction_reports"] = [{"route_id": "R2-runtime-ble", "status": "corrected", "valid_thread_id": "thread-good", "sha256": "abc123"}]; assert validate_real_run_monitoring_package(package).status == "validated"
def test_thread_correction_requires_sha256() -> None:
    package = _valid_package(); package["worker_outputs"][0]["thread_id"] = "thread-old"; package["thread_id_correction_reports"] = [{"route_id": "R2-runtime-ble", "status": "corrected", "valid_thread_id": "thread-good"}]; _assert_rejected(package, "sha256")
def test_launcher_timeout_must_not_be_worker_failure() -> None:
    package = _valid_package(); package["worker_supervision_records"][0]["child_status"] = "failed"; _assert_rejected(package, "launcher_timeout")
def test_launcher_timeout_requires_recovery_attempt() -> None:
    package = _valid_package(); package["worker_supervision_records"][0]["recovery_attempted"] = False; _assert_rejected(package, "recovery_attempted")
def test_launcher_timeout_must_not_duplicate_worker() -> None:
    package = _valid_package(); package["worker_supervision_records"][0]["duplicate_worker_created_for_same_route"] = True; _assert_rejected(package, "duplicate")
def test_invalid_bluez_command_must_be_excluded_from_candidate_failure() -> None:
    package = _valid_package(); package["invalid_tooling_records"][0]["excluded_from_candidate_failure"] = False; _assert_rejected(package, "excluded_from_candidate_failure")
def test_invalid_bluez_command_cannot_support_failed_result() -> None:
    package = _valid_package(); package["final_test_result"]["result"] = "failed"; package["final_test_result"]["failure_signatures"] = ["bluetoothctl list-attributes ADDRESS failed"]; _assert_rejected(package, "failure_signatures")
def test_missing_business_write_notify_forbids_full_pass() -> None:
    package = _valid_package(); package["final_test_result"]["result"] = "passed"; package["final_test_result"]["known_limits"] = []; package["final_test_result"]["uncovered_scope"] = []; _assert_rejected(package, "full passed")
def test_scope_limited_result_requires_known_limits() -> None:
    package = _valid_package(); package["final_test_result"]["known_limits"] = []; _assert_rejected(package, "known_limits")
def test_scope_limited_result_must_preserve_missing_business_scope() -> None:
    package = _valid_package(); package["final_test_result"]["uncovered_scope"] = ["some other limit"]; _assert_rejected(package, "uncovered_scope")
def test_business_not_required_allows_pass() -> None:
    package = _valid_package(); package["business_validation"]["business_write_notify_required"] = False; package["final_test_result"]["result"] = "passed"; package["final_test_result"]["known_limits"] = []; package["final_test_result"]["uncovered_scope"] = []; assert validate_real_run_monitoring_package(package).status == "validated"
def test_business_transaction_proven_allows_full_pass() -> None:
    package = _valid_package(); package["business_validation"]["business_write_notify_proven"] = True; package["business_validation"]["end_to_end_business_transaction_proven"] = True; package["final_test_result"]["result"] = "passed"; package["final_test_result"]["known_limits"] = []; package["final_test_result"]["uncovered_scope"] = []; assert validate_real_run_monitoring_package(package).status == "validated"
def test_production_closure_claim_rejects() -> None:
    package = _valid_package(); package["production_test_lifecycle_closure_claimed"] = True; _assert_rejected(package, "production_test_lifecycle_closure_claimed")
def test_global_causal_truth_merge_rejects() -> None:
    package = _valid_package(); package["global_causal_truth_merge_performed"] = True; _assert_rejected(package, "global_causal_truth_merge_performed")

def test_remote_push_boundary_rejects() -> None:
    package = _valid_package(); package["boundaries"]["remote_push_performed"] = True
    _assert_rejected(package, "remote_push_performed")
