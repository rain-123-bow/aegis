# Phase 12 Debate Causal-Chain Closure Report

## Scope

Phase 12 patches the Phase 11 Debate router-integrated demo so the final report contains an explicit `causal_chain`, not only a `causal_result` summary.

Phase 12 closes Debate causal-chain output at demo level. It is still not production closure.

## Files Modified

- `aegis-runtime/debate/aegis_debate_runtime/models.py`
- `aegis-runtime/debate/aegis_debate_runtime/leader.py`
- `aegis-runtime/debate/tests/test_router_integrated_debate_closure.py`
- `runtime_test_reports/PHASE_12_DEBATE_CAUSAL_CHAIN_CLOSURE_REPORT.md`

No router runtime, top-level Master topology, or `aegis-master-kit` contract files were modified.

## Exact Commands Run

```powershell
python -m venv .venv-debate-runtime
.\.venv-debate-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-debate-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-debate-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\debate[dev]"
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-runtime\debate
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_router_integrated_debate_closure.py -vv
.\.venv-debate-runtime\Scripts\python.exe -m aegis_debate_runtime.cli --request .\aegis-runtime\debate\examples\demo_request.json
git diff --check
git status --short
```

## Pytest Output

Full Debate runtime test output:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-runtime\debate
configfile: pyproject.toml
collected 12 items

aegis-runtime\debate\tests\test_debate_runtime_contract.py ...........   [ 91%]
aegis-runtime\debate\tests\test_router_integrated_debate_closure.py .    [100%]

============================= 12 passed in 0.10s ==============================
```

Full router-integrated closure test output:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\playm\Documents\self-git\aegis\.venv-debate-runtime\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-runtime\debate
configfile: pyproject.toml
collecting ... collected 1 item

aegis-runtime\debate\tests\test_router_integrated_debate_closure.py::test_master_debate_request_closes_through_router_and_persists_causal_candidate PASSED [100%]

============================== 1 passed in 0.08s ==============================
```

CLI demo result:

```text
Command exited with status 0.
The CLI output included final_report.causal_chain.
The package example request selected S1 because that example is a separate internal transport-model demo request.
```

## Data Model Change

`FinalReport` now has a first-class `causal_chain` field.

The model validates:

- `chain_id`
- `source_request_id`
- `decision_problem`
- `selected_stance_id`
- non-empty `nodes`
- non-empty `edges`
- non-empty `selected_path`
- `rejected_paths`
- `unresolved_questions`
- `invalidation_entrypoints`
- node endpoint integrity
- edge endpoint integrity
- rejected path references
- invalidation entrypoint references

The old `causal_result` remains a summary candidate, but it is not accepted as a causal chain.

## Causal Chain Summary For Required Demo Topic

Required topic:

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

Generated causal-chain summary:

```json
{
  "selected_stance_id": "S2",
  "node_count": 19,
  "edge_count": 27,
  "selected_path": [
    "premise.debate_topology_contract",
    "stance.S2",
    "selection.S2",
    "conclusion.S2.selected"
  ],
  "rejected_paths": [
    {
      "stance_id": "S1",
      "rejection_node_ids": ["rejection.S1"],
      "decisive_edge_ids": [
        "edge.premise.rejection.S1",
        "edge.rejection.S1.selection.S2"
      ]
    },
    {
      "stance_id": "S3",
      "rejection_node_ids": ["rejection.S3"],
      "decisive_edge_ids": [
        "edge.premise.rejection.S3",
        "edge.rejection.S3.selection.S2"
      ]
    }
  ]
}
```

## Proof: S1 Rejection

S1 rejection is represented by node:

```json
{
  "id": "rejection.S1",
  "type": "alternative_rejection",
  "stance_id": "S1",
  "statement": "Reject S1: Use full-mesh asynchronous worker chat.",
  "why": "Full-mesh worker chat is rejected because it causes message explosion, hidden side channels, ordering ambiguity, and weak Leader control. Violates the leader-mediated topology boundary required by the Debate Department contract."
}
```

Key supporting edge:

```json
{
  "id": "edge.rejection.S1.selection.S2",
  "from": "rejection.S1",
  "to": "selection.S2",
  "relation": "supports_selection",
  "why": "Rejecting S1 narrows the decision to the stance that preserves the required debate mechanism."
}
```

## Proof: S3 Rejection

S3 rejection is represented by node:

```json
{
  "id": "rejection.S3",
  "type": "alternative_rejection",
  "stance_id": "S3",
  "statement": "Reject S3: Use independent workers with final synthesis only.",
  "why": "Independent workers with final synthesis only are rejected because workers cannot see each other's arguments, so adversarial pressure is lost. Does not provide the shared transcript needed for attacks, answers, concessions, and scope refinement."
}
```

Key supporting edge:

```json
{
  "id": "edge.rejection.S3.selection.S2",
  "from": "rejection.S3",
  "to": "selection.S2",
  "relation": "supports_selection",
  "why": "Rejecting S3 narrows the decision to the stance that preserves the required debate mechanism."
}
```

## Proof: S2 Selection

S2 selection is represented by node:

```json
{
  "id": "selection.S2",
  "type": "selection_reason",
  "stance_id": "S2",
  "statement": "Select S2: Use leader-mediated round-robin broadcast.",
  "why": "The selected stance preserves Leader-controlled turn order, canonical transcript, shared worker view, adversarial pressure, and avoids direct worker-to-worker side channels."
}
```

The topology premise supports S2 selection:

```json
{
  "id": "edge.premise.selection.S2",
  "from": "premise.debate_topology_contract",
  "to": "selection.S2",
  "relation": "supports_selection",
  "why": "The selected stance satisfies the leader-mediated topology premise."
}
```

## Proof: Invalidation Conditions

Invalidation entrypoints are explicit:

```json
[
  {
    "condition_node_id": "invalidation.S1.0",
    "reopens_node_ids": ["rejection.S1"]
  },
  {
    "condition_node_id": "invalidation.S2.0",
    "reopens_node_ids": ["conclusion.S2.selected"]
  },
  {
    "condition_node_id": "invalidation.S2.1",
    "reopens_node_ids": ["conclusion.S2.selected"]
  },
  {
    "condition_node_id": "invalidation.S3.0",
    "reopens_node_ids": ["rejection.S3"]
  }
]
```

The test asserts `reopens_if` edges from invalidation nodes to at least one rejected alternative or selected conclusion.

## Proof: Returned To Master Through Router

The router-integrated test now asserts:

- `final_report["causal_chain"]` exists before submission.
- Debate writes the final report, including `causal_chain`, as `final_report.json`.
- Debate sends only a small route envelope through `debate -> master`.
- Master receives the route envelope through router.
- The returned mailbucket attachment contains `causal_chain`.
- The returned `causal_chain.chain_id` matches the Leader-produced chain.

This proves the causal chain is returned to Master through the router/mailbucket path without making the router parse causal truth.

## Proof: Persistence After Cleanup

The router-integrated test unregisters:

- `debate_worker_S1`
- `debate_worker_S2`
- `debate_worker_S3`
- `debate_leader`

Then it asserts:

- the internal request-scoped debate domain has no active agents;
- the private final report artifact still exists;
- the mailbucket `final_report.json` attachment still exists;
- the persisted private report still contains the same `causal_chain.chain_id`;
- persisted `causal_chain.nodes` and `causal_chain.edges` remain non-empty.

## Proof: Router State Is Not A Causal Store

The test still asserts serialized router state does not contain:

- `archive`
- `knowledge`
- `causal`
- `global_causal`
- `causal_store`

The causal chain lives in the returned final report artifact. Router state remains routing state.

## Boundary

- Raw transcript alone does not satisfy the test.
- `causal_result` summary alone does not satisfy the test.
- `causal_chain` is a demo-level causal candidate output, not a global Causal Store mutation.
- No production crypto or production security was added.
- No top-level Master topology was modified.
- No `aegis-router` runtime code was modified.
- No push, merge, release, or PR was performed.

Phase 12 closes Debate causal-chain output at demo level. It is still not production closure.
