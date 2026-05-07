# Adjudication and Causal Output Rules

## 1. Purpose

This document defines how the Debate Leader converts adversarial worker outputs into a final causal report.

The report must reduce future understanding cost for Master, Execution, or any later agent that lacks original session context.

## 2. Adjudication is not voting

The Leader must not select a stance merely because more workers supported it.

The Leader selects based on causal strength.

Primary criteria:

- evidence quality;
- assumption validity;
- scope precision;
- contract consistency;
- explanatory power;
- implementation feasibility;
- risk if wrong;
- cost and reversibility;
- invalidation clarity;
- downstream action impact.

## 3. Allowed adjudication outcomes

```text
accept_one
accept_multiple_by_scope
need_more_evidence
reject_debate_no_valid_position
stop_and_request_test
stop_and_escalate_to_master
```

## 4. Decision Label Boundary Rules

### request_more_context

Admission-stage only.

Use before worker creation when the incoming request lacks enough decision target, scope, constraints, or evidence references to derive at least two defensible stances.

It is not a final adjudication result after a completed debate.

### need_more_evidence

Final adjudication result.

Use when debate cannot produce a reliable causal result because evidence is missing or contradictory, but the missing evidence is not yet reducible to a concrete Test Department measurement request.

The next action may be Master, Execution, or none depending on who owns context/evidence acquisition.

### stop_and_request_test

Final adjudication result.

Use when continued debate cannot resolve the conflict and the decisive missing evidence is measurable by a concrete test, benchmark, experiment, log capture, or validation plan.

The final report must include `required_measurements` or `test_request`.

`next_action.target` must be `test`.

### stop_and_escalate_to_master

Final adjudication result.

Use when the remaining issue affects top-level governance, route authority, causal merge authority, project direction, responsibility ownership, or another Master-owned decision boundary that the Debate Department cannot decide by itself.

The final report must include the issue being escalated, the competing positions, why Debate cannot decide it locally, and what Master must decide.

`next_action.target` must be `master`.

### escalated

Not a final adjudication decision label.

Use only as a delivery or handoff status after a `stop_and_escalate_to_master` decision has been returned to Master.

It must not replace `stop_and_escalate_to_master` in `decision`, because it does not explain why escalation was required.


## 4.1 Equipoise handling

If multiple positions remain causally balanced after admissible debate pressure, the Leader must not choose arbitrarily.

The Leader must preserve all balanced positions with their valid scopes, risks, assumptions, and transition conditions.

The final report must include:

```yaml
developer_decision_required: true
developer_decision_reason: causal_equipoise|project_direction_choice|value_tradeoff_not_resolvable_by_evidence
balanced_positions:
  - stance_id: ...
    claim: ...
    valid_scope: ...
    risk_if_wrong: ...
    why_not_resolved_by_debate: ...
```

This is a Master handoff condition. Master must not hide the equipoise or collapse it into a fake single winner.

## 4.2 Adjudicator priority state

The final report must include the Leader's adjudicator causal state with route priority and expand priority.

Route priority answers whether a fact entered the current adjudication. Expand priority answers how deeply the fact was unfolded.

The purpose is to prevent long-debate semantic compression from erasing why the Leader stopped, selected, rejected, scoped, or escalated.

## 5. Selected position requirement

If selecting one position, the Leader must explain:

- the selected claim;
- why it best fits the request;
- what evidence supports it;
- what assumptions it requires;
- what scope it applies to;
- what would invalidate it;
- why it is stronger than alternatives.

## 6. Rejected position requirement

For every rejected stance, the Leader must record:

- stance id;
- original claim;
- best argument for that stance;
- decisive weakness;
- failed assumption, evidence gap, contract conflict, risk, cost, or scope issue;
- whether it is fully rejected or only deferred;
- condition under which it could be reopened.

No serious alternative may disappear silently.

## 7. Scoped position requirement

If multiple positions are valid under different conditions, the Leader must record:

```yaml
position: ...
valid_scope: ...
invalid_scope: ...
transition_condition: ...
action_when_condition_holds: ...
```

## 8. Invalidation conditions

Every final causal result must list conditions that would require re-evaluation.

Examples:

- hardware platform changes;
- performance budget changes;
- interface contract changes;
- evidence/log data contradicts the selected claim;
- customer constraint changes;
- safety risk classification changes;
- implementation cost changes;
- newly discovered dependency invalidates assumptions.

## 9. Causal result shape

Final causal output must contain:

```yaml
causal_result:
  statement: ...
  why: ...
  evidence:
    - type: ...
      ref: ...
      relevance: ...
  scope: ...
  assumptions:
    - ...
  depends_on:
    - ...
  invalidates:
    - ...
  supersedes:
    - ...
  rejected_alternatives:
    - stance_id: ...
      why_rejected: ...
      decisive_failure: ...
      reopen_if: ...
  scoped_alternatives:
    - stance_id: ...
      valid_scope: ...
      invalid_scope: ...
  risk_if_wrong: ...
  invalidation_conditions:
    - ...
  next_action:
    target: master|execution|test|final_review|none
    recommendation: ...
  required_measurements:
    - ...
  test_request:
    target: test
    plan_ref: ...
    why_needed: ...
  escalation:
    target: master
    issue: ...
    why_debate_cannot_decide: ...
  confidence: high|medium|low
  status: causal_candidate|needs_evidence|rejected|scoped
```

`required_measurements` or `test_request` is required when `decision` is `stop_and_request_test`.

`escalation` is required when `decision` is `stop_and_escalate_to_master`.


## 9.1 Complete Debate causal package

A completed Debate run must emit a complete Debate causal package suitable for router mailbucket delivery to Master.

The package must contain:

```text
README.md
final_report.json
adjudicator_causal_state.json
worker_states/<worker_id>.json
worker_proofs/<worker_id>_proof.json
transcript_digest.json
evidence_manifest.json
```

The router must not interpret these files. It only carries the route envelope and mailbucket path. Master reads the package and decides whether to merge, request tests, escalate to developer, or reject.

## 10. No bare conclusion rule

The Leader must never emit only:

```text
Choose A.
```

It must emit:

```text
Choose A because [...], under [...], supported by [...].
Reject B because [...].
Reject C because [...].
Reopen if [...].
```

## 11. Boundary to global causal merge

A Debate Department final report is a high-value causal candidate.

It is not automatically global causal truth unless the active governance configuration grants that authority.

By default, Master remains responsible for global causal merge.
