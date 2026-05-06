# Phase 13 Execution Runtime Demo Implementation Report

## Scope

This patch adds the first demo runtime for the Execution Department.

It is demo closure work, not production closure.

## Added Files

```text
aegis-runtime/execution/
aegis-runtime/execution/aegis_execution_runtime/
aegis-runtime/execution/tests/test_execution_runtime_contract.py
aegis-runtime/execution/tests/test_router_integrated_execution_closure.py
aegis-runtime/execution/examples/demo_request.json
runtime_test_reports/PHASE_13_EXECUTION_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
PATCH_USAGE_EXECUTION_RUNTIME.md
```

## Boundary

This patch does not modify:

- top-level Master topology;
- `aegis-router` runtime;
- `aegis-master-kit` contracts;
- production branch policy;
- Archive / Knowledge / Causal stores.

## Demo Mechanisms Implemented

The runtime implements deterministic demo behavior for:

- Execution Leader request admission;
- decision label classification:
  - `request_more_context`;
  - `request_test_measurement`;
  - `request_debate`;
  - `send_implementation_candidate_to_test`;
  - `submit_causal_fork_to_master`;
- direct plan selection when only one non-dominated contract-valid plan remains;
- objective subtask split validation;
- one Execution Group per subtask;
- Front Agent deterministic file changes;
- Back Agent review with blocking validation;
- group branch/workspace records;
- Leader-owned integration branch/workspace;
- implementation candidate generation;
- evidence-backed Test failure mapping to the original group;
- group rework and reintegration;
- Test success feedback processing;
- active group release after success;
- preserved group responsibility records;
- final `execution_causal_chain` as `causal_candidate`;
- router-integrated Master -> Execution -> Test -> Execution -> Master closure test.

## Phase 13 Feedback Message-Type Note

Success feedback no longer uses failure_feedback message_type. Test -> Execution feedback uses test_feedback with result=passed|failed.

The router still accepts `failure_feedback` on `test -> execution` for backward compatibility with older failed-feedback tests, but the Execution runtime demo now sends both failed and passed Test feedback as `test_feedback`. The feedback payload carries:

```yaml
result: passed|failed
feedback_kind: success|failure
evidence_refs:
  - ...
covered_scope:
  - ...
uncovered_scope:
  - ...
```

## Expected Local Validation Commands

From repository root:

```powershell
py -3.13 -m venv .venv-execution-runtime
.\.venv-execution-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-execution-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-execution-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\execution[dev]"

.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution
.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution\tests\test_router_integrated_execution_closure.py -vv
.\.venv-execution-runtime\Scripts\python.exe -m aegis_execution_runtime.cli --request .\aegis-runtime\execution\examples\demo_request.json

git diff --check
git status --short
```

## Container Note

The artifact was generated outside the user's local Windows repository. Router-integrated closure should be executed by Codex in the local repository where `aegis-router` is available at:

```text
C:\Users\playm\Documents\self-git\aegis\aegis-router
```

## Required Closure Proof In Local Run

The router-integrated test must prove:

1. Master sends `execution_request` to Execution through router.
2. Execution creates groups and implementation candidate.
3. Execution sends `implementation_candidate` to Test through router.
4. Test returns evidence-backed failure feedback through router.
5. Execution maps failure to original group and reworks.
6. Execution sends reworked candidate to Test through router.
7. Test returns success feedback through router.
8. Execution releases groups after preserving records.
9. Execution returns final causal candidate to Master through router.
10. Final report contains non-empty `execution_causal_chain.nodes` and `execution_causal_chain.edges`.
11. Router state remains routing state and does not become Archive / Knowledge / Causal storage.

## Production Gaps

Deferred:

- real git branch/worktree orchestration;
- real nested-Codex Front/Back process management;
- real Test Department runtime;
- real Final Review Department runtime;
- production branch protection;
- remote push / PR / merge / release;
- real Archive / Knowledge / Causal admission;
- global causal merge.
