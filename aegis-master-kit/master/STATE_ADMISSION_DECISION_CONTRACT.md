# State Admission Decision Contract

## 1. Purpose

This contract defines the minimal output shape of a Master-owned three-store admission decision.

The decision is not a database write, not a production seal, and not a global causal merge.

## 2. Required fields

```yaml
admission_decision_id: string
phase: phase22a_three_store_admission
target_store: archive|knowledge|causal|none
decision: accept_archive_candidate|accept_knowledge_candidate|stage_causal_candidate|reject_wrong_store|reject_insufficient_evidence|reject_direct_global_write|reject_local_only_causal|needs_more_evidence|needs_debate|needs_master_structural_admission_review
why: string
candidate_id: string
candidate_type: archive|knowledge|causal|unknown
accepted_status: archive_candidate|knowledge_candidate|causal_candidate|rejected|needs_debate|needs_more_evidence|needs_master_review
required_next_step: string
scope: string
assumptions:
  - string
evidence_refs:
  - string
candidate_admission_only: true
canonical_global_merge_allowed: false
store_write_performed: false
master_owned_admission: true
ordinary_agent_direct_write_allowed: false
global_causal_truth_mutation: false
production_storage_mutation: false
```

## 3. Causal candidate rule

`stage_causal_candidate` must not imply global truth.

It must include:

```yaml
accepted_status: causal_candidate
required_next_step: future_high_budget_causal_review_before_global_merge
candidate_admission_only: true
canonical_global_merge_allowed: false
store_write_performed: false
master_owned_admission: true
global_causal_truth_mutation: false
production_storage_mutation: false
```

## 4. Archive rule

Archive admission proves that an event or record is admissible to the task history ledger.

It must not claim that archived statements are Knowledge or Causal truth.

## 5. Knowledge rule

Knowledge admission accepts neutral, source-backed facts or constraints.

It must reject causal reasoning chains and design conclusions.

## 6. Causal source rule

Causal admission accepts only project-direction causal candidates from:

- Master unique conclusion
- Debate Leader adjudication
- Execution Leader directional reasoning under effective uniqueness

Debate Worker local causal state and ordinary implementation/test detail must not be admitted as project-level Causal.

## 7. Debate Leader adjudication rule

Debate Leader adjudicated causal output is not automatically accepted.

Master must perform Phase 22A structural admission review first.

If the causal structure is incomplete, overclaims production/global truth, lacks evidence/scope/assumptions/source origin, or contains unresolved alternatives, the decision must be rejected, needs_more_evidence, or needs_debate.

If structurally complete, the result may be staged only as `causal_candidate`.

Staging still does not perform canonical/global causal truth merge.
