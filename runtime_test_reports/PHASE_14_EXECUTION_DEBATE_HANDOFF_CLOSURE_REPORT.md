# Phase 14 Execution Debate Handoff Closure Report

## Scope

This phase closes Execution-to-Debate handoff at demo level. It does not implement real nested-Codex agent orchestration.

Modified scope was limited to:

- `aegis-runtime/execution/`
- `runtime_test_reports/`

No `aegis-master-kit/`, `aegis-router/`, or top-level topology changes were made for Phase 14.

## Files Added or Modified

- Added `aegis-runtime/execution/tests/test_execution_debate_handoff_closure.py`
- Modified `aegis-runtime/execution/aegis_execution_runtime/models.py`
- Modified `aegis-runtime/execution/aegis_execution_runtime/leader.py`
- Added `runtime_test_reports/PHASE_14_EXECUTION_DEBATE_HANDOFF_CLOSURE_REPORT.md`

## Runtime Behavior Added

Execution runtime now has a demo-level `continue_after_debate()` path.

The path:

1. Accepts the original Execution request.
2. Accepts a Debate adjudication result payload.
3. Requires `selected_plan_id`, `decision`, `why_selected`, `causal_chain`, and `status == causal_candidate`.
4. Binds the Debate result into `ExecutionRunState.debate_reference`.
5. Continues execution using the Debate-selected plan.
6. Creates normal Execution Groups after adjudication.
7. Adds a Debate adjudication node and edge into the final `execution_causal_chain`.

## Commands Run

```powershell
.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution
.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution\tests\test_execution_debate_handoff_closure.py -vv
git diff --check
git status --short
```

## Pytest Output

Full Execution runtime suite:

```text
collected 7 items

aegis-runtime\execution\tests\test_execution_debate_handoff_closure.py . [ 14%]
aegis-runtime\execution\tests\test_execution_runtime_contract.py .....   [ 85%]
aegis-runtime\execution\tests\test_router_integrated_execution_closure.py . [100%]

7 passed in 0.28s
```

Focused Phase 14 test:

```text
aegis-runtime\execution\tests\test_execution_debate_handoff_closure.py::test_execution_requests_debate_binds_adjudication_and_returns_master_candidate PASSED [100%]

1 passed in 0.07s
```

## Router Flow Proof

Execution -> Debate was used with:

- sender: `execution`
- receiver: `debate`
- message_type: `adjudication_request`

Debate -> Execution was used with:

- sender: `debate`
- receiver: `execution`
- message_type: `adjudication_result`

The test also asserts that a direct Master -> internal execution group route is not introduced.

## Debate Selection

The deterministic simulated Debate result selected:

- `selected_plan_id`: `PLAN_B`
- selected route: structured adapter implementation
- reason: better extension boundary while remaining contract-valid

`PLAN_A` remains scoped as acceptable only where extension is not material.

## Execution Binding

Execution binds the Debate result as:

```json
{
  "used": true,
  "selected_plan_id": "PLAN_B",
  "causal_chain_ref": "debate-chain-phase14-plan-b",
  "status": "causal_candidate"
}
```

The binding is present in:

- `ExecutionRunState.debate_reference`
- `integration_candidate.debate_reference`
- `execution_causal_chain.debate_reference`

Execution does not re-litigate the Debate result. It uses the returned `selected_plan_id` to choose the implementation route and continue normal group creation.

## Final Causal Chain Excerpt

The final Execution causal chain includes this Debate support node:

```json
{
  "id": "debate_adjudication.PLAN_B",
  "type": "debate_adjudication",
  "statement": "Debate adjudicated PLAN_B for Execution route selection.",
  "evidence_refs": ["debate-chain-phase14-plan-b"]
}
```

And this support edge:

```json
{
  "from": "debate_adjudication.PLAN_B",
  "to": "plan.PLAN_B",
  "relation": "supports"
}
```

## Master Return

Execution returns the final report to Master through the top-level `execution -> master` route.

The router carries only a route envelope. The final report is in mailbucket content and includes:

- `decision == submit_causal_fork_to_master`
- `execution_causal_chain.status == causal_candidate`
- `execution_causal_chain.debate_reference.used == true`

Router state was checked to avoid becoming an Archive, Knowledge, Causal, global Causal, or causal store.

## Boundary Statement

This phase closes Execution-to-Debate handoff at demo level. It does not implement real nested-Codex agent orchestration.
