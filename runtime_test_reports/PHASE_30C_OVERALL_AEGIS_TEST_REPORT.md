# Phase 30C Overall Aegis Test Report

## Scope

This report records an overall local validation run for the current Aegis repository state after the Phase 30A governance hardening and Phase 30B nested-codex behavioral attestation changes.

This is a regression and demo/runtime verification pass. It does not claim production closure.

## Repository

- Repository path: `C:\Users\playm\Documents\self-git\aegis`
- Branch tested: `v0.1.1-alpha-skill`
- Remote tracking branch: `origin/v0.1.1-alpha-skill`
- Push/merge/PR: not performed

## Environment

- Temporary venv: `C:\Users\playm\AppData\Local\Temp\aegis-overall-test-20260602`
- Python: `3.13.13`
- pytest: `9.0.3`
- Installation command:

```powershell
pip install -e ".\aegis-router[dev]" -e ".\aegis-runtime\master[dev]" -e ".\aegis-runtime\debate[dev]" -e ".\aegis-runtime\execution[dev]" -e ".\aegis-runtime\test[dev]" -e ".\aegis-runtime\final_review[dev]" -e ".\aegis-runtime\state_admission[dev]" -e ".\aegis-runtime\causal_review[dev]" -e ".\aegis-runtime\causal_store[dev]" -e ".\aegis-runtime\archive_store[dev]" -e ".\aegis-runtime\knowledge_store[dev]" -e ".\aegis-runtime\three_store_linkage[dev]"
```

## Per-Package Pytest Matrix

| Package | Result |
| --- | --- |
| `aegis-router` | `144 passed in 4.98s` |
| `aegis-runtime/master` | `41 passed in 0.36s` |
| `aegis-runtime/debate` | `43 passed in 0.36s` |
| `aegis-runtime/execution` | `42 passed in 2.47s` |
| `aegis-runtime/test` | `71 passed, 1 warning in 3.84s` |
| `aegis-runtime/final_review` | `38 passed in 0.19s` |
| `aegis-runtime/state_admission` | `13 passed in 0.04s` |
| `aegis-runtime/causal_review` | `22 passed in 0.05s` |
| `aegis-runtime/causal_store` | `14 passed in 0.14s` |
| `aegis-runtime/archive_store` | `17 passed in 0.30s` |
| `aegis-runtime/knowledge_store` | `21 passed in 0.14s` |
| `aegis-runtime/three_store_linkage` | `22 passed in 0.27s` |

Per-package total: `477 passed`, `0 failed`.

## Combined Pytest Run

Command:

```powershell
python -m pytest .\aegis-router .\aegis-runtime\master .\aegis-runtime\debate .\aegis-runtime\execution .\aegis-runtime\test .\aegis-runtime\final_review .\aegis-runtime\state_admission .\aegis-runtime\causal_review .\aegis-runtime\causal_store .\aegis-runtime\archive_store .\aegis-runtime\knowledge_store .\aegis-runtime\three_store_linkage -q
```

Result:

```text
488 passed, 6 warnings in 18.55s
```

Warnings observed:

- `PytestUnknownMarkWarning` for unregistered `pytest.mark.router` when running the combined suite from repository root.
- `PytestCollectionWarning` because `TestHandoffValidationError` is a runtime exception class whose name starts with `Test` and has an `__init__` constructor.

These warnings did not fail the suite, but they are test-hygiene issues.

## Standalone Router Acceptance

Command:

```powershell
python .\aegis-router\scripts\acceptance_router_contract.py
```

Result:

```json
{
  "passed": 11,
  "failed": 0
}
```

Verified checks:

- positive same-domain route with ack
- cross-domain send rejected
- unregistered send rejected
- unregistered receive rejected
- inactive send rejected
- non-target ack rejected
- cross-domain parent registration rejected
- no-ack message reaches terminal completed state
- heartbeat does not reactivate inactive agent
- heartbeat rejects unregistered agent
- malformed MCP call returns controlled `InvalidRequestError`

## CLI Smoke Tests

| Runtime | Command target | Result |
| --- | --- | --- |
| Debate | `aegis-runtime\debate\examples\demo_request.json` | passed; produced `decision=accept_one`, `selected_stance=S1` |
| Execution | `aegis-runtime\execution\examples\demo_request.json` | passed; produced `decision=submit_causal_fork_to_master`, `final_status=test_passed` |
| Test pass path | `aegis-runtime\test\examples\demo_request_pass.json` | passed; produced `result=passed`, `feedback_kind=success`, `next_route=final_review` |
| Test failure path | `aegis-runtime\test\examples\demo_request_failure.json` | passed; produced `result=failed`, `feedback_kind=failure`, `next_route=execution` |
| Final Review accept path | `aegis-runtime\final_review\examples\demo_request_accept.json` | passed; produced `decision=accept_for_master` |
| Final Review resource-blocked path | `aegis-runtime\final_review\examples\demo_request_blocked_resource.json` | passed; produced `decision=blocked_resource_policy` |
| Final Review scope-limit path | `aegis-runtime\final_review\examples\demo_request_scope_limit.json` | passed; produced `decision=accept_for_master_with_scope_limit` |

Runtime-generated folders from CLI smoke tests were removed after validation:

- `.aegis-execution-runtime`
- `.aegis-test-runtime`
- `.aegis-final-review-runtime`

## Overall Behavior Assessment

The current Aegis local runtime stack is healthy at demo/runtime regression level:

- Router contract behavior remains intact.
- Top-level route, envelope, mailbucket, governance hook, and double-crypto tests remain passing through the router suite.
- Master runtime policy/bootstrap tests pass after Phase 30A/30B changes.
- Debate, Execution, Test, and Final Review demo runtimes pass their package tests and CLI smoke paths.
- State admission, causal review, causal store, archive store, knowledge store, and three-store linkage packages all pass local tests.

Current closure remains demo/runtime and contract-level closure, not production closure.

## Remaining Issues

1. The root-level combined pytest command emits `pytest.mark.router` unknown-marker warnings.
   - Recommended fix: register the `router` marker in a root-level pytest configuration or avoid root-level combined runs without package configs.

2. `TestHandoffValidationError` is collected as a candidate test class by pytest naming rules.
   - Recommended fix: rename the exception class or set `__test__ = False` on the class.

3. Nested-codex actual resolved model and reasoning budget still depend on behavioral attestation where the tool does not expose authoritative resolved runtime metadata.
   - This is a known evidence boundary, not a failed runtime test.

## Boundary Confirmation

- No push was performed.
- No merge was performed.
- No PR was created.
- No production closure is claimed.
- No router runtime behavior was changed during this overall test.
- No Archive, Knowledge, or Causal store mutation was introduced by the router.
