# Phase 15 Test Runtime Demo Implementation Report

## Scope

This patch adds the first deterministic demo runtime for the Test Department.

It is demo closure work, not production closure.

## Added Files

```text
aegis-runtime/test/
runtime_test_reports/PHASE_15_TEST_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
PATCH_USAGE_TEST_RUNTIME.md
```

## Boundary

This patch does not modify:

- `aegis-router/`;
- `aegis-runtime/debate/`;
- `aegis-runtime/execution/`;
- `aegis-master-kit/organization/topologies/`;
- `aegis-master-kit/organization/departments/test/`.

It does not add a `test -> master` route.

## Demo Mechanisms Implemented

The runtime implements deterministic demo behavior for:

- Test Leader request admission;
- Test plan generation;
- one Test Worker per accepted route;
- worker route evidence production;
- final result aggregation by evidence state;
- failed feedback to Execution Leader;
- passed result handoff to Final Review;
- proven failure with ambiguous owner remaining `failed`;
- missing/unstable evidence becoming `inconclusive` or `blocked`;
- governance blocker becoming `blocked` with `blocker_kind: governance`;
- minimal reproducibility set retention;
- artifact manifest retention;
- final Test result as evidence/scoped conclusion, not global causal truth.

## Expected Local Validation Commands

From repository root:

```powershell
py -3.13 -m venv .venv-test-runtime
.\.venv-test-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test
.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_router_integrated_test_closure.py -vv
.\.venv-test-runtime\Scripts\python.exe -m aegis_test_runtime.cli --request .\aegis-runtime\test\examples\demo_request_pass.json

git diff --check
git status --short
```

## Required Closure Proof In Local Run

The router-integrated test must prove:

1. Execution sends an `implementation_candidate` to Test through router.
2. Test Leader receives the request through the router/mailbucket path.
3. Test Leader designs routes and produces worker evidence.
4. Failed candidate result routes to Execution Leader with `test_feedback`.
5. Passed candidate result routes to Final Review with `test_result`.
6. Test output does not route directly to Master.
7. Test output remains evidence/scoped conclusion and does not mutate global causal truth.
8. Router state remains routing state and does not become Archive / Knowledge / Causal storage.

## Production Gaps

Deferred:

- real git checkout / branch validation;
- real CI command execution;
- real nested-Codex Test Worker processes;
- real environment provisioning;
- real artifact retention backend;
- real Final Review runtime;
- real Archive / Knowledge / Causal admission;
- global causal merge.
