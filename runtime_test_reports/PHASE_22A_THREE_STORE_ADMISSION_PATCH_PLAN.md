# Phase 22A Three-Store Admission Patch Plan

## Summary

Phase 22A introduces a Master-owned admission boundary for Archive / Knowledge / Causal candidates.

This phase does not add a fifth department and does not create a long-lived State Admission Agent.

## Boundary

```text
Department output / developer claim / Master observation
  -> Master-owned state admission validator
  -> admission_decision
```

## Added files

- `aegis-master-kit/master/THREE_STORE_ADMISSION_POLICY.md`
- `aegis-master-kit/master/STATE_ADMISSION_DECISION_CONTRACT.md`
- `aegis-runtime/state_admission/pyproject.toml`
- `aegis-runtime/state_admission/aegis_state_admission/__init__.py`
- `aegis-runtime/state_admission/aegis_state_admission/validator.py`
- `aegis-runtime/state_admission/aegis_state_admission/cli.py`
- `aegis-runtime/state_admission/tests/test_phase22a_three_store_admission.py`
- `runtime_test_reports/PHASE_22A_THREE_STORE_ADMISSION_PATCH_PLAN.md`

## Validation intent

The runtime validator proves:

- Archive can admit task history without producing truth.
- Knowledge can admit source-backed neutral facts and constraints.
- Knowledge rejects causal reasoning chains.
- Causal rejects bare conclusions.
- Debate Worker local causal state is rejected as project-level Causal.
- Debate Leader adjudicated causal chains can be admitted only as candidates.
- Execution Leader directional reasoning must route to Debate when the path is not effectively unique.
- Direct global causal truth writes are rejected.

Phase 22A deliberately uses `stage_causal_candidate` terminology to prevent confusing candidate-lane admission with global causal truth merge.

The patch validates two separate gates:

1. Phase 22A structural admission into the Causal candidate lane.
2. Future high-budget causal review / canonical merge, which is not implemented in Phase 22A.

## Non-claims

Phase 22A does not claim:

- production storage closure
- Archive / Knowledge / Causal production write closure
- global causal truth merge
- persistent state backend
- encryption / key lifecycle
- release / PR / merge governance
