# Phase 20A Test Handoff Validation Patch Plan

## Scope

This patch adds Test Department Phase 20A handoff validation support.

It validates that Test Leader can consume an Execution Phase 19B handoff package, checkout the sandbox integration branch, run local tests, and preserve reproducible evidence.

It does not claim real Test Worker Codex agent closure or production CI closure.

## Frozen decisions

```text
Phase 20A = Test handoff validation closure
Phase 20B = real Test Worker Codex agent closure, deferred
```

## Key semantics

1. Test receives a handoff package from Execution.
2. The handoff target must be `test`.
3. The handoff status must be `ready_for_test_department`.
4. Test checks out the sandbox integration branch locally.
5. Test runs the supplied local test command.
6. Test preserves command stdout/stderr, branch, commit, changed files, reproducibility set, artifact manifest, and scoped final test result.
7. Test does not modify code.
8. Test does not push, PR, remote merge, release, or claim global causal truth.

## Production boundary

Not included:

- real Test Worker Codex agent creation;
- production CI;
- environment provisioning;
- external artifact backend;
- remote branch governance;
- global causal merge.
