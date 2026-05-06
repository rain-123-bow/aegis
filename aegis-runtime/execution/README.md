# Aegis Execution Runtime Demo

This package is the demo/runtime implementation for the Execution Department contract.

It is **not** production execution infrastructure.

It demonstrates:

- Master -> Execution request intake;
- contract-first admission;
- direct plan selection versus Debate / Test-measurement routing;
- objective subtask split validation;
- one Execution Group per independent subtask;
- Front Agent implementation;
- Back Agent review with real blocking authority;
- group branch/workspace records;
- Leader-owned integration branch;
- implementation candidate handoff to Test;
- evidence-backed Test failure mapping to the original group;
- group rework, reintegration, and success feedback;
- group release after Test success while preserving responsibility records;
- final `execution_causal_chain` as a `causal_candidate`, not global causal truth.

## Boundary

`aegis-master-kit/organization/departments/execution/` defines the contracts.

`aegis-runtime/execution/` executes a deterministic demo of those contracts.

This runtime does not:

- push to remote;
- merge to main;
- release;
- create PRs;
- mutate Archive / Knowledge / Causal stores;
- perform production branch protection;
- run real nested-Codex process orchestration.

## Local validation

From repository root:

```powershell
py -3.13 -m venv .venv-execution-runtime
.\.venv-execution-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-execution-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-execution-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\execution[dev]"

.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution
.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution\tests\test_router_integrated_execution_closure.py -vv
.\.venv-execution-runtime\Scripts\python.exe -m aegis_execution_runtime.cli --request .\aegis-runtime\execution\examples\demo_request.json
```
