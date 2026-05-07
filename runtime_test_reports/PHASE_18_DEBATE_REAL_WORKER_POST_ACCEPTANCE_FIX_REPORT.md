# Phase 18 Debate Real Worker Post-Acceptance Fix Report

Generated UTC: `2026-05-07T02:13:21.763802+00:00`

## Summary

Two post-acceptance engineering issues were fixed without changing frozen Debate semantics:

1. `audit-proofs` no longer double-prepends `proof_dir` when `expected_worker_proofs.json` contains a relative `proof_path` that already points under the proof directory.
2. `package-mailbucket` now copies existing worker proof files byte-for-byte into the mailbucket package when proof file paths are provided.

Phase 18 `accepted_real_debate_worker_closure` remains valid.

## Files Changed

- `aegis-runtime/debate/aegis_debate_runtime/real_nested_codex.py`
- `aegis-runtime/debate/aegis_debate_runtime/mailbucket_package.py`
- `aegis-runtime/debate/aegis_debate_runtime/real_worker_cli.py`
- `aegis-runtime/debate/tests/test_debate_real_nested_codex_worker_proof_audit.py`
- `aegis-runtime/debate/tests/test_debate_causal_state_and_mailbucket_package.py`
- `runtime_test_reports/PHASE_18_DEBATE_REAL_WORKER_POST_ACCEPTANCE_FIX_REPORT.md`
- `.aegis-phase18-post-acceptance-fix/`

## Fix 1: Proof Path Resolution

Implementation:

- Added `_resolve_expected_proof_path(...)` in `real_nested_codex.py`.
- Missing or empty `proof_path` resolves to `proof_dir / <worker_id>_proof.json`.
- Absolute `proof_path` is used as-is.
- Relative paths already resolving inside `proof_dir` are used as provided.
- Simple relative filenames still resolve under `proof_dir`.
- `_assert_proof(...)` was not weakened.

Regression result:

- Original Phase 18 `expected_worker_proofs.json` now audits successfully without converting paths to absolute.
- Audit status: `passed`
- Audited workers: `3`

## Fix 2: Byte-Identical Mailbucket Proof Copies

Implementation:

- Added `worker_proof_paths` support to `write_debate_result_mailbucket_package(...)`.
- `real_worker_cli.py package-mailbucket` now passes proof file paths instead of parsed proof dictionaries.
- Existing dict-based `worker_proofs` support remains for unit/demo callers.
- Passing both `worker_proofs` and `worker_proof_paths` fails fast.
- Source and destination proof hashes are checked after copy.

Hash result:

- all_byte_identical: `true`

| source proof | package proof | source sha256 | package sha256 | byte identical |
| --- | --- | --- | --- | --- |
| `.aegis-phase18-debate-test/worker_proofs/debate_worker__phase18-debate-run-001__S1_STRICT_REAL_WORKER_ACCEPTANCE_proof.json` | `.aegis-phase18-debate-test/mailbucket/phase18_debate_result_to_master/worker_proofs/debate_worker__phase18-debate-run-001__S1_STRICT_REAL_WORKER_ACCEPTANCE_proof.json` | `7300e5d0fdf8297bbec196b0722a503c9bd5c18e7b9af2ff079b320880913442` | `7300e5d0fdf8297bbec196b0722a503c9bd5c18e7b9af2ff079b320880913442` | `true` |
| `.aegis-phase18-debate-test/worker_proofs/debate_worker__phase18-debate-run-001__S2_HYBRID_FALLBACK_FOR_VELOCITY_proof.json` | `.aegis-phase18-debate-test/mailbucket/phase18_debate_result_to_master/worker_proofs/debate_worker__phase18-debate-run-001__S2_HYBRID_FALLBACK_FOR_VELOCITY_proof.json` | `a5f00d3735afe2e3751d70413931204be118934a81220712bbb89f3a77e7c7df` | `a5f00d3735afe2e3751d70413931204be118934a81220712bbb89f3a77e7c7df` | `true` |
| `.aegis-phase18-debate-test/worker_proofs/debate_worker__phase18-debate-run-001__S3_DEFER_REAL_WORKER_ACCEPTANCE_proof.json` | `.aegis-phase18-debate-test/mailbucket/phase18_debate_result_to_master/worker_proofs/debate_worker__phase18-debate-run-001__S3_DEFER_REAL_WORKER_ACCEPTANCE_proof.json` | `af9ab818c0a982d67c744a3d4d3e31a33dff07eba64c8a00b817dd0c5ce2fd6b` | `af9ab818c0a982d67c744a3d4d3e31a33dff07eba64c8a00b817dd0c5ce2fd6b` | `true` |

## Commands Run

- `.\.venv-debate-real-worker\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py -vv`
- `.\.venv-debate-real-worker\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py -vv`
- `.\.venv-debate-real-worker\Scripts\python.exe -m pytest .\aegis-runtime\debate -vv`
- `.\.venv-debate-real-worker\Scripts\python.exe -m aegis_debate_runtime.real_worker_cli audit-proofs --expected .\.aegis-phase18-debate-test\expected_worker_proofs.json --proof-dir .\.aegis-phase18-debate-test\worker_proofs --output .\.aegis-phase18-post-acceptance-fix\relative_expected_audit_summary.json`
- `.\.venv-debate-real-worker\Scripts\python.exe -m aegis_debate_runtime.real_worker_cli package-mailbucket --final-report .\.aegis-phase18-debate-test\final_report.json --adjudicator-state .\.aegis-phase18-debate-test\adjudicator_causal_state.json --worker-states .\.aegis-phase18-debate-test\worker_states --worker-proofs .\.aegis-phase18-debate-test\worker_proofs --output-dir .\.aegis-phase18-debate-test\mailbucket\phase18_debate_result_to_master`
- `git diff --check`
- `git status --short`

## Exact Test Outputs

### Proof Audit Targeted Tests

```text
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\playm\Documents\self-git\aegis\.venv-debate-real-worker\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-runtime\debate
configfile: pyproject.toml
collecting ... collected 5 items

aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_fails_when_proof_is_missing PASSED [ 20%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_complete_proof PASSED [ 40%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_relative_proof_path_inside_proof_dir_without_double_prefix PASSED [ 60%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_simple_relative_proof_file_name_under_proof_dir PASSED [ 80%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_absolute_proof_path PASSED [100%]

============================== 5 passed in 0.05s ==============================
```

### Mailbucket Targeted Tests

```text
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\playm\Documents\self-git\aegis\.venv-debate-real-worker\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-runtime\debate
configfile: pyproject.toml
collecting ... collected 3 items

aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py::test_worker_and_adjudicator_causal_state_shapes_are_serializable PASSED [ 33%]
aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py::test_mailbucket_package_contains_required_causal_files PASSED [ 66%]
aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py::test_mailbucket_package_copies_existing_worker_proof_bytes_identically PASSED [100%]

============================== 3 passed in 0.04s ==============================
```

### Full Debate Runtime Tests

```text
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\playm\Documents\self-git\aegis\.venv-debate-real-worker\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-runtime\debate
configfile: pyproject.toml
collecting ... collected 23 items

aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py::test_worker_and_adjudicator_causal_state_shapes_are_serializable PASSED [  4%]
aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py::test_mailbucket_package_contains_required_causal_files PASSED [  8%]
aegis-runtime\debate\tests\test_debate_causal_state_and_mailbucket_package.py::test_mailbucket_package_copies_existing_worker_proof_bytes_identically PASSED [ 13%]
aegis-runtime\debate\tests\test_debate_policy_real_worker_contract.py::test_model_policy_defines_debate_worker_as_gpt_5_5_high PASSED [ 17%]
aegis-runtime\debate\tests\test_debate_policy_real_worker_contract.py::test_debate_contract_preserves_two_layer_shape_and_no_extra_roles PASSED [ 21%]
aegis-runtime\debate\tests\test_debate_policy_real_worker_contract.py::test_debate_worker_contract_requires_local_causal_state_priority PASSED [ 26%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_fails_when_proof_is_missing PASSED [ 30%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_complete_proof PASSED [ 34%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_relative_proof_path_inside_proof_dir_without_double_prefix PASSED [ 39%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_simple_relative_proof_file_name_under_proof_dir PASSED [ 43%]
aegis-runtime\debate\tests\test_debate_real_nested_codex_worker_proof_audit.py::test_strict_real_worker_proof_audit_accepts_absolute_proof_path PASSED [ 47%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_rejects_single_stance_before_worker_creation PASSED [ 52%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_request_more_context_before_worker_creation PASSED [ 56%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_creates_one_worker_per_valid_stance_and_releases_all PASSED [ 60%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_round_robin_broadcast_gives_all_workers_same_transcript_state PASSED [ 65%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_worker_direct_peer_message_is_forbidden PASSED [ 69%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_malicious_worker_cannot_switch_stance_silently PASSED [ 73%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_final_report_contains_causal_structure_and_rejected_alternatives PASSED [ 78%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_stop_and_request_test_label_has_test_target_and_measurements PASSED [ 82%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_stop_and_escalate_to_master_label_has_master_target PASSED [ 86%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_accept_multiple_by_scope_keeps_scoped_positions PASSED [ 91%]
aegis-runtime\debate\tests\test_debate_runtime_contract.py::test_runtime_does_not_claim_global_causal_truth_or_top_level_worker_routes PASSED [ 95%]
aegis-runtime\debate\tests\test_router_integrated_debate_closure.py::test_master_debate_request_closes_through_router_and_persists_causal_candidate PASSED [100%]

============================= 23 passed in 0.14s ==============================
```

### Relative Expected Audit CLI Smoke

```text
{
  "audited_count": 3,
  "status": "passed",
  "workers": [
    {
      "proof_path": ".aegis-phase18-debate-test\\worker_proofs\\debate_worker__phase18-debate-run-001__S1_STRICT_REAL_WORKER_ACCEPTANCE_proof.json",
      "sha256": "7300e5d0fdf8297bbec196b0722a503c9bd5c18e7b9af2ff079b320880913442",
      "stance_id": "S1_STRICT_REAL_WORKER_ACCEPTANCE",
      "worker_id": "debate_worker__phase18-debate-run-001__S1_STRICT_REAL_WORKER_ACCEPTANCE"
    },
    {
      "proof_path": ".aegis-phase18-debate-test\\worker_proofs\\debate_worker__phase18-debate-run-001__S2_HYBRID_FALLBACK_FOR_VELOCITY_proof.json",
      "sha256": "a5f00d3735afe2e3751d70413931204be118934a81220712bbb89f3a77e7c7df",
      "stance_id": "S2_HYBRID_FALLBACK_FOR_VELOCITY",
      "worker_id": "debate_worker__phase18-debate-run-001__S2_HYBRID_FALLBACK_FOR_VELOCITY"
    },
    {
      "proof_path": ".aegis-phase18-debate-test\\worker_proofs\\debate_worker__phase18-debate-run-001__S3_DEFER_REAL_WORKER_ACCEPTANCE_proof.json",
      "sha256": "af9ab818c0a982d67c744a3d4d3e31a33dff07eba64c8a00b817dd0c5ce2fd6b",
      "stance_id": "S3_DEFER_REAL_WORKER_ACCEPTANCE",
      "worker_id": "debate_worker__phase18-debate-run-001__S3_DEFER_REAL_WORKER_ACCEPTANCE"
    }
  ]
}
```

### Package Mailbucket Byte Copy CLI Smoke

```text
{
  "decision": "accept_one",
  "developer_decision_required": false,
  "package_dir": ".aegis-phase18-debate-test\\mailbucket\\phase18_debate_result_to_master",
  "run_id": "phase18-debate-run-001",
  "worker_proof_count": 3,
  "worker_state_count": 3
}
```

## Git Hygiene

### git diff --check

```text
(no output)
```

### git status --short

```text
 M MODEL_REASONING_BUDGET_POLICY.yaml
 M aegis-master-kit/organization/departments/debate/ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md
 M aegis-master-kit/organization/departments/debate/DEBATE_DEPARTMENT_CONTRACT.md
 M aegis-master-kit/organization/departments/debate/DEBATE_LEADER_CONTRACT.md
 M aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CONTRACT.md
 M aegis-master-kit/organization/departments/debate/MANIFEST.yaml
 M aegis-master-kit/organization/departments/debate/README.md
 M aegis-runtime/debate/aegis_debate_runtime/__init__.py
 M aegis-runtime/debate/pyproject.toml
?? .aegis-phase18-debate-test/
?? .aegis-phase18-post-acceptance-fix/
?? aegis-master-kit/organization/departments/debate/DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md
?? aegis-master-kit/organization/departments/debate/DEBATE_RESULT_MAILBUCKET_PACKAGE_CONTRACT.md
?? aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md
?? aegis-runtime/debate/aegis_debate_runtime/causal_state.py
?? aegis-runtime/debate/aegis_debate_runtime/mailbucket_package.py
?? aegis-runtime/debate/aegis_debate_runtime/real_nested_codex.py
?? aegis-runtime/debate/aegis_debate_runtime/real_worker_cli.py
?? aegis-runtime/debate/tests/test_debate_causal_state_and_mailbucket_package.py
?? aegis-runtime/debate/tests/test_debate_policy_real_worker_contract.py
?? aegis-runtime/debate/tests/test_debate_real_nested_codex_worker_proof_audit.py
?? runtime_test_reports/PHASE_18_DEBATE_REAL_NESTED_CODEX_FULL_ACCEPTANCE_REPORT.md
?? runtime_test_reports/PHASE_18_DEBATE_REAL_NESTED_CODEX_WORKER_PATCH_PLAN.md
?? runtime_test_reports/PHASE_18_DEBATE_REAL_WORKER_POST_ACCEPTANCE_FIX_REPORT.md
```

## Boundaries

- No frozen Debate contract semantics were changed.
- Debate Department remains `Debate Leader + stance-bound Debate Workers`.
- Debate Leader remains `gpt-5.5 / high`.
- Debate Worker remains `gpt-5.5 / high`.
- No medium Debate Worker profile, fallback acceptance, extra Debate roles, or Master-created Debate Workers were added.
- No production nested-Codex lifecycle closure is claimed.
- No Archive / Knowledge / Causal global truth mutation is claimed.
- No push, merge, PR, release, or commit was performed.

