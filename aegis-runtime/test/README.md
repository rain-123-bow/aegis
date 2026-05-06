# Aegis Test Runtime Demo

This package is the demo/runtime implementation for the Test Department contract.

It is **not** production testing infrastructure.

It demonstrates:

- Execution -> Test candidate intake;
- contract-first admission;
- deterministic test plan generation;
- route split with one Test Worker per accepted route;
- route-level evidence production;
- strict result classification by evidence state;
- proven failure with ambiguous owner remains `failed`;
- missing/unstable evidence becomes `inconclusive` or `blocked`;
- governance/policy bypass becomes `blocked` with `blocker_kind: governance`;
- failed/inconclusive/ordinary blocked feedback routes to Execution Leader;
- passed/scoped-pass/final-governance blocked material routes to Final Review;
- minimal reproducibility set and artifact manifest retention;
- final Test result remains evidence/scoped conclusion, not global causal truth.

## Boundary

`aegis-master-kit/organization/departments/test/` defines the contracts.

`aegis-runtime/test/` executes a deterministic demo of those contracts.

This runtime does not:

- modify implementation code;
- assign Execution Group rework;
- create real Test worker processes;
- run real CI;
- perform real git branch checkout;
- send Test output directly to Master;
- mutate Archive / Knowledge / Causal stores;
- claim production Test closure.

## Local validation

From repository root:

```powershell
py -3.13 -m venv .venv-test-runtime
.\.venv-test-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test
.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_router_integrated_test_closure.py -vv
.\.venv-test-runtime\Scripts\python.exe -m aegis_test_runtime.cli --request .\aegis-runtime\test\examples\demo_request_pass.json
```
