# Phase 15 Test Runtime Demo Local Verification Report

## Scope

Local verification of the Test Department deterministic demo runtime.

This verification applies the local Test runtime demo patch, then validates demo-level behavior only. It does not claim production Test closure.

## Commands Run

Working directory:

```text
C:\Users\playm\Documents\self-git\aegis
```

Commands:

```powershell
git diff --check
git status --short

py -3.13 -m venv .venv-test-runtime
.\.venv-test-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_test_runtime_contract.py -vv
.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_router_integrated_test_closure.py -vv
.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test -vv

.\.venv-test-runtime\Scripts\python.exe -m aegis_test_runtime.cli --request .\aegis-runtime\test\examples\demo_request_pass.json
.\.venv-test-runtime\Scripts\python.exe -m aegis_test_runtime.cli --request .\aegis-runtime\test\examples\demo_request_failure.json
```

## Results

- git diff --check: pass
- contract tests: pass, `6 passed in 0.07s`
- router-integrated closure test: pass, `1 passed in 0.16s`
- full Test runtime suite: pass, `7 passed in 0.12s`
- CLI pass demo: pass
- CLI failure demo: pass

CLI pass demo returned:

```json
{
  "feedback_kind": "success",
  "next_route": "final_review",
  "result": "passed"
}
```

CLI failure demo returned:

```json
{
  "feedback_kind": "failure",
  "next_route": "execution",
  "result": "failed"
}
```

## Closure Proof

- Execution -> Test route verified: yes
- Test -> Execution failed feedback verified: yes
- Test -> Final Review passed result verified: yes
- Test -> Master direct route avoided: yes
- reproducibility set retained: yes
- artifact manifest retained: yes
- Test result remains evidence/scoped conclusion: yes
- Router state remains routing state: yes

## Boundary

- no production Test closure claimed
- no top-level topology changed
- no router changed
- no test -> master route added
- no global causal truth mutation
- no cache files committed

## Notes

The local verification used Python 3.13.13 in `.venv-test-runtime`.

The runtime is deterministic demo infrastructure. It uses request-provided candidate snapshots and in-process route workers; it does not perform production git checkout, real CI, real environment provisioning, or nested-Codex Test Worker orchestration.
