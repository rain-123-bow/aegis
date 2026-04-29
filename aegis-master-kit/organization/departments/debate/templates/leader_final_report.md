# Debate Leader Final Report

## 1. Metadata

```yaml
debate_run_id: DEBATE-RUN-0000
request_id: REQ-0000
request_source: master|execution
decision: accept_one|accept_multiple_by_scope|need_more_evidence|rejected_no_valid_position|rejected_no_debate_needed|stop_and_request_test|stop_and_escalate_to_master
escalation_status: not_applicable|pending_handoff|handed_off
```

`request_more_context` is admission-stage only and must not be used as this final report decision.

`escalated` is not a final decision label. Use `decision: stop_and_escalate_to_master` and record handoff state in `escalation_status`.

## 2. Why Debate Was Needed

Explain why this request required adversarial reasoning instead of direct execution or simple lookup.

## 3. Stances Considered

| Stance | Claim | Final Status | Summary |
| --- | --- | --- | --- |
| S1 | ... | accepted/rejected/scoped/conceded/deferred | ... |
| S2 | ... | accepted/rejected/scoped/conceded/deferred | ... |

## 4. Adjudication Summary

### Selected / scoped outcome

State the chosen outcome.

### Why selected

Explain why the selected stance or scoped outcome has the strongest causal support.

### Why alternatives failed

For every serious alternative, explain the decisive weakness.

### Unresolved questions

List unresolved questions and why debate could not resolve them.

## 5. Causal Result for Master / Execution

```yaml
causal_result:
  statement: "..."
  why: "..."
  evidence:
    - type: code|log|experiment|document|conversation|observation
      ref: "..."
      relevance: "..."
  scope: "..."
  assumptions:
    - "..."
  material_conditions:
    - "..."
  depends_on:
    - "..."
  invalidates:
    - "..."
  supersedes:
    - "..."
  rejected_alternatives:
    - stance_id: S2
      why_rejected: "..."
      decisive_failure: "..."
      reopen_if: "..."
  scoped_alternatives:
    - stance_id: S3
      valid_scope: "..."
      invalid_scope: "..."
  risk_if_wrong: "..."
  invalidation_conditions:
    - "..."
  next_action:
    target: master|execution|test|final_review|none
    recommendation: "..."
  required_measurements:
    - "Required only when decision is stop_and_request_test."
  test_request:
    target: test
    plan_ref: "Required only when decision is stop_and_request_test."
    why_needed: "Why debate cannot resolve this without measurement."
  escalation:
    target: master
    issue: "Required only when decision is stop_and_escalate_to_master."
    why_debate_cannot_decide: "Why this is a Master-owned boundary."
  confidence: high|medium|low
  status: causal_candidate|needs_evidence|rejected|scoped
```

## 6. Transcript Digest

Summarize only the transcript parts needed to audit the causal result.

## 7. Cleanup Result

```yaml
cleanup_result:
  workers_released: true|false
  topology_released: true|false
  retained_artifacts:
    - final_report
    - stance_packets
    - transcript_digest
    - evidence_refs
  cleanup_notes: "..."
```
