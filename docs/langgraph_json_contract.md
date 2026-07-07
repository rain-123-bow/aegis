# LangGraph JSON Contract

## Authority order

```text
GRAPH_GATE_RESULT.json
GRAPH_STATE_SNAPSHOT.json
reviewer/master closure JSON
reviewer blocker JSON
reviewer result JSON
author/executor claim JSON
human Markdown summaries
```

`README.md` is not part of the control plane.

## Control files

```text
AUTHOR_PATCH_CLAIM.json
TEST_PLAN_REVIEW_RESULT.json
TEST_PLAN_REVIEW_BLOCKERS.json
TEST_PLAN_BLOCKER_CLOSURE.json
TEST_EXECUTION_CLAIM.json
TEST_RESULT_REVIEW_RESULT.json
TEST_RESULT_REVIEW_BLOCKERS.json
TEST_RESULT_BLOCKER_CLOSURE.json
GRAPH_GATE_RESULT.json
GRAPH_STATE_SNAPSHOT.json
```

## Graph gate rules

```text
non-pure node JSON response -> fail closed
review score < 90 -> fail
open_blockers.length > 0 -> fail
effective score for open P0 blocker -> 0
status=true + open_blockers -> status ignored
previous open blockers + missing closure JSON -> hard fail
required_files without content diff -> no re-review
same blocker repeated -> author_constraints tightened
5 test-plan author review/gate failures -> END, developer intervention required
```

## Reviewer result JSON

```json
{
  "status": false,
  "score": 80,
  "open_blockers": [
    {
      "blocker_id": "REQ-FUNC-025-P0",
      "severity": "P0",
      "finding": "TP-011 only covers SHM lifecycle and does not prove eventfd/poll blocking wakeup or absence of continuous SHM polling.",
      "required_files": ["TEST_PLAN.md", "TRACEABILITY_MATRIX.md", "TEST_CASE_INDEX.md"],
      "required_change": "Add dedicated P0 test proving eventfd/poll blocking wakeup and no busy-loop SHM polling.",
      "forbidden_substitute": ["SHM slot lifecycle only", "traceability mapping only"],
      "evidence_atoms": ["eventfd/poll wakeup", "no continuous SHM polling", "no busy loop while waiting"]
    }
  ]
}
```

## Reviewer blocker JSON

```json
{
  "open_blockers": [
    {
      "blocker_id": "REQ-FUNC-025-P0",
      "severity": "P0",
      "finding": "Concrete unresolved failure.",
      "required_files": ["TEST_PLAN.md"],
      "required_change": "Concrete file-level requirement.",
      "forbidden_substitute": ["old near-match explanation"],
      "evidence_atoms": ["required evidence atom"]
    }
  ]
}
```

## Author patch claim JSON

```json
{
  "resolution_type": "patch",
  "blocker_claims": [
    {
      "blocker_id": "REQ-FUNC-025-P0",
      "modified_files": ["TEST_PLAN.md", "TRACEABILITY_MATRIX.md", "TEST_CASE_INDEX.md"],
      "new_or_modified_test_ids": ["TP-P0-025-EVENTFD-POLL"],
      "evidence_contract": ["eventfd/poll wakeup", "no continuous SHM polling", "no busy loop while waiting"],
      "why_old_tests_are_insufficient": "TP-011 covers SHM lifecycle only and does not prove the reviewer-required blocking wakeup evidence."
    }
  ]
}
```

Forbidden `resolution_type` values:

```text
argument_only
reinterpretation
traceability_only
reuse_old_tp
documentation_only
```

## Closure JSON

```json
{
  "closed_blocker_ids": ["REQ-FUNC-025-P0"],
  "closure_evidence": [
    {
      "blocker_id": "REQ-FUNC-025-P0",
      "verified_files": ["TEST_PLAN.md", "TRACEABILITY_MATRIX.md", "TEST_CASE_INDEX.md"],
      "verified_test_ids": ["TP-P0-025-EVENTFD-POLL"],
      "verified_evidence_contract": ["eventfd/poll wakeup", "no continuous SHM polling", "no busy loop while waiting"]
    }
  ]
}
```

Only reviewer/master nodes may write closure JSON.

## Gate output JSON

```json
{
  "time": "ISO-8601",
  "node": "B",
  "route": "A",
  "status": false,
  "violations": [],
  "raw_status": true,
  "review_score": 80,
  "effective_score": 0,
  "open_blockers": [],
  "same_blocker_counts": {},
  "test_plan_author_review_failures": 1,
  "test_plan_author_gate_failures": 0,
  "stop_reason": null
}
```

## Role boundaries

`TEST_PLAN_AUTHOR` can modify files and write `AUTHOR_PATCH_CLAIM.json`.

`TEST_PLAN_AUTHOR` cannot close blockers, reinterpret blockers, downgrade P0 blockers, or claim pass while `open_blockers` is non-empty.

`TEST_PLAN_REVIEWER` can write `TEST_PLAN_REVIEW_RESULT.json`, `TEST_PLAN_REVIEW_BLOCKERS.json`, and `TEST_PLAN_BLOCKER_CLOSURE.json`.

`TEST_PLAN_REVIEWER` cannot pass with open blockers, pass below score threshold, or fail without actionable machine-readable blockers.
