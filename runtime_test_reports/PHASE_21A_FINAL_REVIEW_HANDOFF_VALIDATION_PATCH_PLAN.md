# Phase 21A Final Review Handoff Validation Patch Plan

## Summary

```yaml
phase: 21A
acceptance_target: accepted_final_review_handoff_validation_closure
scope: final_review_handoff_validation_not_real_final_review_leader
input_source: Test Phase 20B final_review handoff package
output_route: final_review -> master
real_final_review_leader_created: false
final_review_worker_created: false
production_final_review_lifecycle_closure: false
global_causal_truth_mutation: false
```

## Patch contents

Added files:

- `aegis-master-kit/organization/departments/final_review/FINAL_REVIEW_21A_HANDOFF_VALIDATION_CONTRACT.md`
- `aegis-runtime/final_review/aegis_final_review_runtime/phase21a_handoff.py`
- `aegis-runtime/final_review/aegis_final_review_runtime/phase21a_cli.py`
- `aegis-runtime/final_review/tests/test_phase21a_final_review_handoff_validation.py`
- `runtime_test_reports/PHASE_21A_FINAL_REVIEW_HANDOFF_VALIDATION_PATCH_PLAN.md`

Patched files:

- `aegis-master-kit/organization/departments/final_review/MANIFEST.yaml`
- `aegis-runtime/final_review/pyproject.toml`

## Validation commands

From repository root on Windows PowerShell:

```powershell
py -3.13 -m venv .venv-final-review-phase21a
.\.venv-final-review-phase21a\Scripts\python.exe -m pip install -U pip
.\.venv-final-review-phase21a\Scripts\python.exe -m pip install -e ".\aegis-runtime\final_review[dev]"

.\.venv-final-review-phase21a\Scripts\python.exe -m pytest .\aegis-runtime\final_review\tests\test_phase21a_final_review_handoff_validation.py -vv
.\.venv-final-review-phase21a\Scripts\python.exe -m pytest .\aegis-runtime\final_review -vv

git diff --check
```

Optional CLI shape:

```powershell
.\.venv-final-review-phase21a\Scripts\python.exe -m aegis_final_review_runtime.phase21a_cli run `
  --handoff-package .\.aegis-phase20b-test-real-worker\outputs\final_review_handoff_package_phase20b.json `
  --output-dir .\.aegis-phase21a-final-review-handoff-validation\outputs
```

## Acceptance meaning

Phase 21A proves that Final Review can consume the Test Phase 20B handoff package and generate a valid Final Review recommendation for Master.

It does not prove real nested-Codex Final Review Leader creation. That is Phase 21B.
