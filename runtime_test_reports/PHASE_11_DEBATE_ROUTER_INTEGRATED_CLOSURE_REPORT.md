# Phase 11 Debate Router-Integrated Closure Report

## Scope

This phase applied the Debate runtime demo package and added a router-integrated closure test for the Debate Department.

This is demo closure, not production closure.

## Environment

- Repository: `C:\Users\playm\Documents\self-git\aegis`
- Router package: `C:\Users\playm\Documents\self-git\aegis\aegis-router`
- Branch: `v0.1.0-alpha`
- Python requested first: `py -3.12`
- Python 3.12 result: unavailable on this machine
- Python actually used: `Python 3.13.13`
- Virtual environment used: `C:\Users\playm\Documents\self-git\aegis\.venv-debate-runtime`

## Files Added Or Modified

Added:

- `PATCH_USAGE.md`
- `aegis-runtime/debate/`
- `aegis-runtime/debate/tests/test_router_integrated_debate_closure.py`
- `runtime_test_reports/PHASE_10_DEBATE_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_11_DEBATE_ROUTER_INTEGRATED_CLOSURE_REPORT.md`

Modified:

- `README.md`
- `aegis-runtime/debate/README.md`
- `aegis-runtime/debate/aegis_debate_runtime/cli.py`
- `aegis-runtime/debate/aegis_debate_runtime/leader.py`
- `aegis-runtime/debate/aegis_debate_runtime/models.py`
- `aegis-runtime/debate/tests/test_debate_runtime_contract.py`

Pre-existing untracked package content now included in this commit scope:

- `aegis-master-kit/organization/departments/debate/`

## Commands Run

```powershell
python -m venv .venv-debate-runtime
.\.venv-debate-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-debate-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-debate-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\debate[dev]"
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-router
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-runtime\debate
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_router_integrated_debate_closure.py -vv
.\.venv-debate-runtime\Scripts\python.exe -m aegis_debate_runtime.cli --request .\aegis-runtime\debate\examples\demo_request.json
git diff --check
git status --short
```

## Test Results

Router tests:

```text
collected 142 items
142 passed in 4.85s
```

Debate runtime tests:

```text
collected 12 items
12 passed in 0.09s
```

Router-integrated closure test:

```text
test_router_integrated_debate_closure.py::test_master_debate_request_closes_through_router_and_persists_causal_candidate PASSED
1 passed in 0.08s
```

CLI demo:

```text
Command exited with status 0.
Output included run_id, selected_stance, decision, and final_report_path.
The package example selected stance S1 for its separate transport-model demo request.
```

## Required Demo Topic Result

The router-integrated closure test used this Master-created topic:

```text
Choose the internal Debate Worker communication model for demo runtime:
S1 = full-mesh asynchronous worker chat
S2 = leader-mediated round-robin broadcast
S3 = independent workers with final synthesis only
```

Final selected stance:

```text
S2
```

Decision:

```text
accept_one
```

Why S2 was selected:

- S2 preserves Leader control of speaking order.
- S2 keeps a canonical transcript.
- S2 allows workers to see the same transcript before their turns.
- S2 permits adversarial pressure without uncontrolled worker-to-worker channels.
- S2 matches the Debate Department leader-mediated round-robin boundary.

Why S1 was rejected:

- Full-mesh worker chat causes message explosion.
- It creates hidden side channels.
- It creates ordering ambiguity.
- It weakens Leader control.

Why S3 was rejected:

- Independent workers cannot see each other's arguments during the run.
- Adversarial pressure is lost.
- Final synthesis alone does not provide shared attack, answer, concession, and scope-refinement pressure.

## Router Closure Proof

The test proves:

- Router domain `top_level_master_domain` was created.
- Top-level agents `master`, `debate`, and `execution` were registered.
- Master submitted `debate_request` to Debate through the allowed `master -> debate` route.
- Debate received the request through the router.
- Debate Leader admitted the request after deriving three defensible stances.
- Debate Leader created a request-scoped internal debate domain.
- Internal agents `debate_leader`, `debate_worker_S1`, `debate_worker_S2`, and `debate_worker_S3` were registered.
- Internal routes were leader-mediated only:
  - `debate_leader -> debate_worker_S1`
  - `debate_leader -> debate_worker_S2`
  - `debate_leader -> debate_worker_S3`
  - `debate_worker_S1 -> debate_leader`
  - `debate_worker_S2 -> debate_leader`
  - `debate_worker_S3 -> debate_leader`
- Worker peer-to-peer sends were rejected:
  - `debate_worker_S1 -> debate_worker_S2`
  - `debate_worker_S2 -> debate_worker_S3`
  - `debate_worker_S3 -> debate_worker_S1`
- Worker bypass attempts to `master` and `execution` were rejected.
- Debate result returned through the allowed `debate -> master` route.
- Master received and acknowledged the result message.

## Causal Candidate Proof

The final report is marked as:

```text
causal_candidate
```

It is not global causal truth.

The test asserts the final causal report includes:

- `why`
- `evidence`
- `assumptions`
- `material_conditions`
- `scope`
- `risk_if_wrong`
- `invalidation_conditions`
- `rejected_alternatives`

The result message submitted through router carries only a small route envelope. The final causal report is persisted as mailbucket attachment content and as a private final report artifact. The router does not parse the report as truth.

## Cleanup Proof

The test proves cleanup by:

- unregistering `debate_worker_S1`
- unregistering `debate_worker_S2`
- unregistering `debate_worker_S3`
- unregistering `debate_leader`
- checking that the internal request-scoped domain snapshot has no active agents left

The final causal report survives cleanup:

- private final report file remains present
- mailbucket `final_report.json` attachment remains present
- persisted report still contains selected stance `S2`

## Router State Boundary Proof

The test asserts serialized router state does not contain these store names:

- `archive`
- `knowledge`
- `causal`
- `global_causal`
- `causal_store`

This proves the demo does not mutate Archive, Knowledge, Causal, Global Causal, or any causal store through router state.

## Hygiene

`git diff --check` result:

```text
passed with no whitespace errors
```

Generated artifacts removed before commit scope:

- `aegis-runtime/debate/aegis_debate_runtime.egg-info`
- `aegis-runtime/debate/.pytest_cache`
- `aegis-runtime/debate/aegis_debate_runtime/__pycache__`
- `aegis-runtime/debate/tests/__pycache__`

Final hygiene before local commit:

- `.venv-debate-runtime` was removed.
- no `__pycache__` or `.pytest_cache` directories remained in the repository tree.
- `git diff --check` passed with no output.
- `git status --short` showed only source, documentation, contract, runtime demo, and runtime report changes.

## Boundary Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- Runtime code was not moved into `aegis-master-kit`.
- Debate Workers were not added to the top-level Master route table.
- Top-level Master topology was not modified.
- This is demo closure, not production closure.
