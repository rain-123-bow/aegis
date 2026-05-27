# Phase 28A Test Real-Run Monitoring Hardening Patch Plan

## Verdict target

`accepted_test_real_run_monitoring_hardening`

## Scope

Phase 28A addresses defects observed in real Test Department run `T20260526-002` under the v0.2.1 test workflow:

1. Test route assumed unavailable tooling (`ninja`).
2. Worker proof/output used mismatched `thread_id`.
3. Launcher timeout had to be separated from Worker failure.
4. BLE validation proved reachability but not business write/notify.
5. Invalid BlueZ diagnostic command had to be excluded from product-failure evidence.

## Files added

```text
aegis-master-kit/organization/departments/test/TEST_REAL_RUN_MONITORING_HARDENING_CONTRACT.md
aegis-runtime/test/aegis_test_runtime/monitoring_hardening.py
aegis-runtime/test/tests/test_phase28a_test_real_run_monitoring_hardening.py
runtime_test_reports/PHASE_28A_TEST_REAL_RUN_MONITORING_HARDENING_PATCH_PLAN.md
```

## Files modified

```text
README.md
aegis-master-kit/organization/departments/test/README.md
aegis-master-kit/organization/departments/test/MANIFEST.yaml
aegis-runtime/test/aegis_test_runtime/__init__.py
aegis-runtime/test/pyproject.toml
```

## Validation commands

```powershell
py -3.13 -m venv .venv-test-monitoring-phase28a
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pip install -U pip
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-monitoring-phase28a\Scripts\python.exe -m compileall .\aegis-runtime\test\aegis_test_runtime
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_phase28a_test_real_run_monitoring_hardening.py -vv
.\.venv-test-monitoring-phase28a\Scripts\python.exe -m pytest .\aegis-runtime\test -vv
git diff --check
```

## Acceptance boundaries

No router/topology/model-policy/business-code mutation; no production Test lifecycle closure; no production CI closure; no remote push/PR/merge/release; no global causal truth merge.
