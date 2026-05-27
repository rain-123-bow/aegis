# Phase 28A Test Real-Run Monitoring Hardening Acceptance Report

## Verdict

`accepted_test_real_run_monitoring_hardening`

Phase 28A is accepted at local demo/runtime validation level.

## Scope

Phase 28A hardens Test Department real-run monitoring after observed run feedback:

- command-route environment/tool preflight is required before execution;
- unavailable tooling must be blocked or superseded, not used as candidate failure evidence;
- Worker creation/proof/output/supervision `thread_id` continuity is enforced;
- launcher timeout is separated from Worker failure;
- invalid BlueZ diagnostic tooling is excluded from candidate failure evidence;
- BLE reachability without business write/notify proof can only produce a scope-limited result;
- production lifecycle, remote operation, and global causal-truth boundaries remain false.

This phase validates real-run monitoring hardening only. It does not claim production Test lifecycle closure, production CI closure, durable environment provisioning, production BLE business tooling, remote branch governance, release authority, production sign-off, or global causal truth merge.

## Repository State

- Repository: `C:\Users\playm\Documents\self-git\aegis`
- Branch: `v0.1.1-alpha-skill`
- Base commit before patch: `cf35a8f5621961b780ecba4384692e730597f7cd`
- Patch source used: `C:\Users\playm\Documents\AAA\aegis_phase28a_test_real_run_monitoring_hardening_patch_v0_4\aegis_phase28a_test_real_run_monitoring_hardening_patch_v0_4`
- Zip source check: `C:\Users\playm\Downloads\aegis_phase28a_test_real_run_monitoring_hardening_patch_v0_4.zip` was not present, so the local v0.4 patch directory was used.

## Files Added

```text
aegis-master-kit/organization/departments/test/TEST_REAL_RUN_MONITORING_HARDENING_CONTRACT.md
aegis-runtime/test/aegis_test_runtime/monitoring_hardening.py
aegis-runtime/test/tests/test_phase28a_test_real_run_monitoring_hardening.py
runtime_test_reports/PHASE_28A_TEST_REAL_RUN_MONITORING_HARDENING_PATCH_PLAN.md
runtime_test_reports/PHASE_28A_TEST_REAL_RUN_MONITORING_HARDENING_ACCEPTANCE_REPORT.md
```

## Files Modified

```text
README.md
aegis-master-kit/organization/departments/test/MANIFEST.yaml
aegis-master-kit/organization/departments/test/README.md
aegis-runtime/test/aegis_test_runtime/__init__.py
aegis-runtime/test/pyproject.toml
```

## Validation Plan Fixes

The validation plan at `C:\Users\playm\Downloads\PHASE_28A_TEST_REAL_RUN_MONITORING_HARDENING_VALIDATION_PLAN.md` was corrected before execution:

- replaced invalid PowerShell `py -3.13 - <<'PY'` heredoc syntax with `@' ... '@ | py -3.13 -`;
- replaced `py_compile` package checks with AST parsing so validation does not generate `__pycache__`;
- wrote smoke JSON with explicit UTF-8 without BOM;
- used `git status --short --untracked-files=all` for boundary checks;
- added fallback from missing zip package to the local v0.4 patch directory.

## Package Validation

Commands and results:

```powershell
Get-ChildItem -Recurse -File $dst
# package files present

py -3.13 - <<fixed inline package metadata/SHA256/LF/syntax checks>>
# generated artifact audit passed
# PATCH_MANIFEST metadata check passed
# SHA256SUMS passed
# LF audit passed
# syntax parse passed
# apply-script marker audit passed
```

Dry run:

```text
DRY RUN phase28a_test_real_run_monitoring_hardening
  file: aegis-master-kit/organization/departments/test/TEST_REAL_RUN_MONITORING_HARDENING_CONTRACT.md
  file: aegis-runtime/test/aegis_test_runtime/monitoring_hardening.py
  file: aegis-runtime/test/tests/test_phase28a_test_real_run_monitoring_hardening.py
  file: runtime_test_reports/PHASE_28A_TEST_REAL_RUN_MONITORING_HARDENING_PATCH_PLAN.md
```

Apply:

```text
APPLIED phase28a_test_real_run_monitoring_hardening
  file: aegis-master-kit/organization/departments/test/TEST_REAL_RUN_MONITORING_HARDENING_CONTRACT.md
  file: aegis-runtime/test/aegis_test_runtime/monitoring_hardening.py
  file: aegis-runtime/test/tests/test_phase28a_test_real_run_monitoring_hardening.py
  file: runtime_test_reports/PHASE_28A_TEST_REAL_RUN_MONITORING_HARDENING_PATCH_PLAN.md
BASE_COMMIT=cf35a8f5621961b780ecba4384692e730597f7cd
```

## Runtime Validation Environment

```powershell
py -3.13 -m venv .venv-test-monitoring-phase28a
.\.venv-test-monitoring-phase28a\Scripts\python.exe --version
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pip install -U pip
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"
```

Result:

```text
Python 3.13.13
```

`aegis-router[dev]` was installed alongside `aegis-runtime/test[dev]` because the full Test runtime suite contains router-integrated tests.

## Test Results

Compile check:

```powershell
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m compileall .\aegis-runtime\test\aegis_test_runtime
```

Result:

```text
compileall passed
```

Targeted Phase 28A test:

```powershell
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_phase28a_test_real_run_monitoring_hardening.py -vv
```

Result:

```text
20 passed in 0.04s
```

Full Test runtime suite:

```powershell
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pytest .\aegis-runtime\test -vv
```

Result:

```text
71 passed, 1 warning in 3.69s
```

The warning is the pre-existing pytest collection warning for `TestHandoffValidationError` having a constructor. It is not introduced by Phase 28A.

## Runtime Fix During Validation

The first targeted run found one real validation defect:

```text
test_scope_limited_result_must_preserve_missing_business_scope FAILED
```

Cause:

`monitoring_hardening.py` accepted a `passed_with_scope_limit` result when missing BLE business scope appeared in `known_limits`, even if `uncovered_scope` omitted it.

Fix:

`passed_with_scope_limit` now requires every missing BLE business scope item to be preserved in `final_test_result.uncovered_scope`. `known_limits` alone is not enough.

After the fix:

```text
20 passed
71 passed, 1 warning
```

## CLI Smoke

Module-form CLI:

```powershell
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m aegis_test_runtime.monitoring_hardening validate --package .\.aegis-phase28a-monitoring-smoke\valid_monitoring_package.json --output .\.aegis-phase28a-monitoring-smoke\valid_monitoring_result.json
```

Result:

```json
{
  "decision": "accepted_test_real_run_monitoring_hardening",
  "environment_preflight_verified": true,
  "global_causal_truth_merge_performed": false,
  "invalid_tooling_exclusion_verified": true,
  "launcher_timeout_boundary_verified": true,
  "production_test_lifecycle_closure_claimed": false,
  "scope_limited_result_verified": true,
  "status": "validated",
  "thread_identity_verified": true,
  "violations": [],
  "warnings": []
}
```

The module-form command emitted Python's `runpy` warning because `aegis_test_runtime.__init__` exports `monitoring_hardening` symbols before the module is executed with `-m`. The console script below passed cleanly.

Console-script CLI:

```powershell
.\.venv-test-monitoring-phase28a\Scripts\aegis-test-monitoring-hardening.exe validate --package .\.aegis-phase28a-monitoring-smoke\valid_monitoring_package.json --output .\.aegis-phase28a-monitoring-smoke\valid_monitoring_result_console.json
```

Result:

```json
{
  "decision": "accepted_test_real_run_monitoring_hardening",
  "status": "validated",
  "violations": [],
  "warnings": []
}
```

## Negative Smoke Cases

Seven negative smoke cases were executed against mutations of the valid monitoring package:

| case | expected marker | result |
| --- | --- | --- |
| missing preflight | `environment_preflight` | rejected |
| missing tool used as candidate failure | `candidate_failure_evidence_used` | rejected |
| thread ID mismatch without correction | `worker_thread_identity` | rejected |
| launcher timeout marked as worker failure | `launcher_timeout` | rejected |
| invalid BlueZ tooling not excluded | `invalid_tooling_records.excluded_from_candidate_failure` | rejected |
| missing BLE business scope claims full pass | `full passed` | rejected |
| global truth boundary violation | `global_causal_truth_merge_performed` | rejected |

Result:

```text
negative smoke cases passed: 7
```

## Boundary Confirmation

- No router behavior was modified.
- No top-level topology was modified.
- No model policy was modified.
- No business code was modified.
- No remote push was performed.
- No PR was created.
- No merge was performed.
- No release was performed.
- No generated key or secret was added.
- No production Test lifecycle closure is claimed.
- No production CI closure is claimed.
- No global causal truth merge is claimed.

## Remaining Gaps

- Phase 28A remains a local deterministic monitoring hardening validator.
- Production Test lifecycle supervision is still deferred.
- Production CI and durable environment provisioning are still deferred.
- Production BLE business tooling remains outside this patch.
- Module-form CLI emits a `runpy` warning due package-level eager exports; the console-script entry point runs cleanly.

