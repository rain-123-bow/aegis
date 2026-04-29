# Apply Aegis Debate Runtime Demo Patch v0.1

## Target repository root

Unzip this package at the repository root.

It will add:

```text
aegis-runtime/debate/
runtime_test_reports/PHASE_10_DEBATE_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
```

## Scope

This patch implements the **demo runtime** for the Debate Department contract.

It does not implement production hardening, remote trust, certificate chains, key rotation, or real global Causal Store merge.

## Intended validation command

From repository root:

```bash
cd aegis-runtime/debate
python -m pytest
```

## Runtime demo command

From repository root:

```bash
cd aegis-runtime/debate
python -m aegis_debate_runtime.cli --request examples/demo_request.json
```

## Boundary

The contract package remains under:

```text
aegis-master-kit/organization/departments/debate/
```

The executable demo runtime is intentionally outside `aegis-master-kit` because `aegis-master-kit` defines organization semantics, not runtime process management.
