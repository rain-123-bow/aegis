# Phase 20B Test Real Worker Patch Plan

## Scope

This patch moves Test Department from Phase 20A handoff validation toward strict real nested-Codex Test Worker acceptance.

It does not claim production Test lifecycle closure.

## Frozen decisions

```text
Test Leader = gpt-5.5 / high
Test Worker = gpt-5.5 / high
```

Forbidden in this phase:

- medium Test Worker;
- silent downgrade;
- fallback from real Test Worker to deterministic/in-process output in acceptance;
- Master-created Test Workers;
- source code modification by Test;
- remote push;
- PR creation;
- production merge;
- release;
- global causal truth merge.

## Key semantics

1. Master sees only the Test Leader.
2. Test Leader creates one Test Worker per accepted validation route.
3. Test Workers are request-scoped and route-bound.
4. Missing proof is failure, not skip.
5. Missing output is failure, not skip.
6. Output status must be `test_worker_report_candidate`.
7. Output causal status must be `scoped_evidence_candidate`.
8. Phase 20B reuses the sandbox integration-branch boundary introduced by Phase 20A.

## Production boundary

Not included:

- persistent Test Worker lifecycle;
- production CI;
- environment provisioning;
- external artifact backend;
- remote branch governance;
- release;
- global causal merge.


## v0.2 Safety Notes

- The stdio MCP client command parser is Windows-aware.
- The create-real path is a tool bridge only; true acceptance requires real Test Worker proof/output written by actual nested-Codex/Codex CLI workers.
- Tests are audit/tooling tests, not real worker creation tests.
