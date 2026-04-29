# PHASE 10 Debate Runtime Demo Implementation Report

## Decision

DEBATE_RUNTIME_DEMO_PATCH_READY

This patch adds a demo-level executable runtime for the Debate Department contract.

## Scope

Implemented:

- request admission;
- stance validation;
- one temporary worker per valid stance;
- leader-mediated round-robin broadcast;
- canonical transcript digest;
- worker stance-binding enforcement;
- no worker peer-to-peer channel;
- Leader adjudication labels;
- worker/topology cleanup;
- persistent causal final report;
- causal candidate status rather than global causal truth.

Not implemented:

- production security hardening;
- real nested-codex process orchestration as a required dependency;
- remote trust;
- key lifecycle and rotation;
- global Causal Store mutation;
- Master-level causal merge;
- production-quality reasoning intelligence.

## Files Added

```text
aegis-runtime/debate/README.md
aegis-runtime/debate/pyproject.toml
aegis-runtime/debate/aegis_debate_runtime/__init__.py
aegis-runtime/debate/aegis_debate_runtime/models.py
aegis-runtime/debate/aegis_debate_runtime/adapters.py
aegis-runtime/debate/aegis_debate_runtime/topology.py
aegis-runtime/debate/aegis_debate_runtime/leader.py
aegis-runtime/debate/aegis_debate_runtime/cli.py
aegis-runtime/debate/examples/demo_request.json
aegis-runtime/debate/tests/test_debate_runtime_contract.py
runtime_test_reports/PHASE_10_DEBATE_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
PATCH_USAGE.md
```

## Contract Alignment

The runtime preserves these Debate Department invariants:

```text
Debate Leader is the only external boundary.
Workers are request-scoped and stance-bound.
Workers are created only after valid stance admission.
Internal topology is leader-mediated round-robin broadcast.
Worker direct peer messaging is forbidden.
Leader adjudicates; workers do not own final results.
Final output preserves causal structure rather than a bare conclusion.
Temporary resources are released after final report generation.
Debate output is a causal candidate, not automatic global causal truth.
```

## Decision Label Boundary

The runtime keeps the important label distinctions:

- `request_more_context`: admission-stage only, before workers are created.
- `rejected_no_debate_needed`: admission-stage rejection when fewer than two valid stances exist.
- `stop_and_request_test`: final result when measurable evidence is required; next target is `test`.
- `stop_and_escalate_to_master`: final result when governance/top-level authority is affected; next target is `master`.
- `accept_multiple_by_scope`: final result when multiple stances are valid under distinct scopes.
- `accept_one`: final result when one stance is selected and alternatives are explicitly rejected.

## Demo Validation Command

```bash
cd aegis-runtime/debate
python -m pytest
```

## Demo Run Command

```bash
cd aegis-runtime/debate
python -m aegis_debate_runtime.cli --request examples/demo_request.json
```

## Future Runtime Work

Future phases may replace the deterministic in-process demo workers with real nested-codex worker processes by implementing the provided worker factory interface.

The runtime already contains a subprocess adapter extension point, but the demo contract tests intentionally use in-process workers to validate behavior without depending on a local Codex binary.
