# Phase 21B Final Review Real Leader Patch Plan

## Scope

Phase 21B adds real Final Review Leader acceptance tooling after Phase 21A handoff validation.

It validates:

```text
Master
  -> real nested-Codex / Codex Final Review Leader
      -> proof file
      -> output file
      -> final_review_result recommendation
  -> Master recommendation boundary
```

## Added files

- `aegis-master-kit/organization/departments/final_review/FINAL_REVIEW_21B_REAL_LEADER_ACCEPTANCE_CONTRACT.md`
- `aegis-runtime/final_review/aegis_final_review_runtime/real_leader.py`
- `aegis-runtime/final_review/aegis_final_review_runtime/real_leader_cli.py`
- `aegis-runtime/final_review/tests/test_phase21b_final_review_real_leader_acceptance.py`
- `runtime_test_reports/PHASE_21B_FINAL_REVIEW_REAL_LEADER_PATCH_PLAN.md`

## Modified files

- `aegis-master-kit/organization/departments/final_review/MANIFEST.yaml`
- `aegis-runtime/final_review/pyproject.toml`
- `aegis-runtime/final_review/aegis_final_review_runtime/__init__.py`

## Explicit non-goals

- Do not create Final Review Workers.
- Do not change router topology.
- Do not modify implementation code.
- Do not perform remote push, PR creation, merge, release, production sign-off, or global causal truth mutation.
- Do not claim production Final Review lifecycle closure.

## Expected acceptance label

```text
accepted_real_final_review_leader_closure
```

## Forbidden labels

```text
accepted_final_review_worker_closure
production_final_review_lifecycle_closure
production_release_review_closure
global_causal_truth_closure
```
