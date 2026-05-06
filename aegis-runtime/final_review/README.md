# Aegis Final Review Runtime Demo

This package is the demo/runtime implementation for the Final Review Department contract.

It is **not** production Final Review infrastructure.

It demonstrates:

- Test -> Final Review final package intake;
- resource-policy gate with `blocked_resource_policy` highest precedence;
- single-Leader whole-chain consistency review;
- object consistency between final code, implementation candidate, and tested candidate;
- Test/Execution/Debate reference completeness checks;
- strict `accept_for_master` no-limits semantics;
- scoped acceptance when `known_limits` or `blocked_scope` constrain the accepted scope;
- non-accept decisions for Execution, Test, missing evidence, and governance blockers;
- full `final_review_result` shape;
- Final Review -> Master router-integrated handoff;
- no internal Final Review workers.

## Boundary

`aegis-master-kit/organization/departments/final_review/` defines the contracts.

`aegis-runtime/final_review/` executes a deterministic demo of those contracts.

This runtime does not:

- call real external models;
- create root model/reasoning-budget policy files;
- create internal workers;
- modify implementation code;
- run tests;
- assign Execution rework;
- route directly to Execution or Test;
- push, merge, release, or deploy;
- mutate global causal truth.

## Local validation

From repository root:

```powershell
py -3.13 -m venv .venv-final-review-runtime
.\.venv-final-review-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-final-review-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-final-review-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\final_review[dev]"

.\.venv-final-review-runtime\Scripts\python.exe -m pytest .\aegis-runtime\final_review
.\.venv-final-review-runtime\Scripts\python.exe -m pytest .\aegis-runtime\final_review\tests\test_router_integrated_final_review_closure.py -vv
.\.venv-final-review-runtime\Scripts\python.exe -m aegis_final_review_runtime.cli --request .\aegis-runtime\final_review\examples\demo_request_accept.json
.\.venv-final-review-runtime\Scripts\python.exe -m aegis_final_review_runtime.cli --request .\aegis-runtime\final_review\examples\demo_request_blocked_resource.json
```
