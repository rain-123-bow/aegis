# Flat Node Graph

## Current LangGraph runtime

The current runtime graph is the A-F test workflow in `src/main.py`.

```text
START
  -> A TEST_PLAN_AUTHOR
  -> B TEST_PLAN_REVIEWER
       pass -> C TEST_EXECUTOR
       fail -> A TEST_PLAN_AUTHOR
       hard fail -> END
  -> D TEST_RESULT_REVIEWER
       pass -> E TEST_REPORT_WRITER
       fail -> C TEST_EXECUTOR
       hard fail -> END
  -> F FINAL_REVIEWER
  -> END
```

The earlier Project Manager / Requirement Designer / Execution Designer roles remain logical upstream concepts. They are not LangGraph nodes in this runtime because Codex App and LangGraph cannot reliably coordinate arbitrary process-external agents at every step.

## Machine contract

The graph is JSON-first.

`README.md` is human navigation only. It is not a control plane, not a blocker closure file, and not a substitute for evidence.

Authoritative contract: [`langgraph_json_contract.md`](./langgraph_json_contract.md).

## Route authority

Agents may report `status` in their final JSON response, but routing is decided by the graph gate.

The graph gate uses:

```text
strict JSON response
JSON control files
open_blockers
review score
blocker closure files
required file diffs
retry budget
```

The graph gate writes:

```text
GRAPH_GATE_RESULT.json
GRAPH_STATE_SNAPSHOT.json
```

## Pass rule

A reviewer pass requires:

```text
status == true
score >= 90
open_blockers.length == 0
previous open blockers closed by reviewer closure file
```

Any open P0 blocker forces:

```text
effective_score = 0
status = false
```

`status=true` from an author or executor does not override open blockers.

## Test-plan failure budget

The test-plan author may be returned by the reviewer at most 5 consecutive times.

On the 5th failed test-plan review:

```text
gate_route = END
status = false
stop_reason = developer intervention required
```

## Producer authority boundary

The test-plan author can:

```text
modify files
write AUTHOR_PATCH_CLAIM.json
map blocker -> modified files -> test IDs -> evidence contract
send patch back to review
```

The test-plan author cannot:

```text
reinterpret reviewer blockers
downgrade P0 blockers
close blockers
claim pass while blockers remain open
use traceability-only mapping as evidence
reuse old tests when reviewer forbids it
```

## Reviewer authority boundary

The reviewer can:

```text
write review result JSON
write blocker JSON
write blocker closure JSON
approve only when no blockers remain
```

The reviewer cannot:

```text
fail without actionable blockers
pass with open blockers
pass below score threshold
close blockers without explicit closure IDs
```
