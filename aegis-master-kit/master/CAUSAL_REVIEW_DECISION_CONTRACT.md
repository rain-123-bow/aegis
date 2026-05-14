# Causal Review Decision Contract

## 1. Purpose

This contract defines the output shape for Phase 22B Master Causal Review.

The decision is not a store write, not a production seal, and not a canonical/global causal truth merge.

## 2. Required fields

```yaml
review_decision_id: string
phase: phase22b_master_causal_review
decision: stage_canonical_merge_candidate|stage_scope_limited_merge_candidate|stage_supersession_candidate|stage_invalidation_candidate|reject_candidate|needs_more_evidence|needs_debate|developer_decision_required|reject_direct_merge_or_store_write
why: string
candidate_id: string
candidate_statement: string
source_origin: master_unique_conclusion|debate_leader_adjudication|execution_leader_directional_reasoning
accepted_status: canonical_merge_candidate|scope_limited_merge_candidate|supersession_candidate|invalidation_candidate|rejected|needs_more_evidence|needs_debate|pending_developer_decision
required_next_step: string
scope: string
assumptions:
  - string
evidence_refs:
  - string
knowledge_context_used:
  - string
causal_context_used:
  - string
conflicts:
  - string
supersedes:
  - string
invalidates:
  - string
master_confidence:
  type: statistical|deterministic_proof|contract_proven|test_evidence_backed|static_analysis_backed|heuristic|qualitative|unknown
  value: number|string|bool|null
  threshold: number|null
  evidence_refs:
    - string
developer_decision_required: bool
developer_decision_package: object|null
archive_event_candidate_required: bool
archive_event_candidate: object|null
canonical_global_merge_performed: false
production_store_write_performed: false
causal_store_write_performed: false
master_owned_review: true
developer_owns_decisive_responsibility: bool
```

## 3. Decision semantics

### `stage_canonical_merge_candidate`

The candidate passed Phase 22B review and may proceed to a later persistence/merge phase.

It does not mean:

```text
canonical/global causal truth has been written
production Causal Store was mutated
Developer has delegated final real-world responsibility
```

### `stage_scope_limited_merge_candidate`

The candidate is acceptable only under narrowed scope.

The decision must provide the narrowed scope and why the original scope was too broad.

### `stage_supersession_candidate`

The candidate is eligible to supersede one or more existing causal facts in a later persistence/merge phase.

The decision must name the superseded fact IDs.

### `stage_invalidation_candidate`

The candidate is eligible to invalidate one or more existing causal facts in a later persistence/merge phase.

The decision must name the invalidated fact IDs.

### `developer_decision_required`

Master cannot claim a high-confidence supported conclusion for a project-direction decision.

The output must include the complete developer decision package and an Archive event candidate.

### `reject_direct_merge_or_store_write`

Any input attempting canonical/global merge, direct Causal Store write, production store mutation, or active truth write is rejected.

## 4. Confidence semantics

Statistical confidence requires evidence-backed data and a numeric threshold. It must not be fabricated from ordinary reasoning confidence.

Deterministic proof, contract-proven conclusions, test-evidence-backed conclusions, and static-analysis-backed conclusions may satisfy the high-confidence gate when explicit evidence references are present.

Heuristic, qualitative, or unknown confidence may be reported, but cannot satisfy the decisive high-confidence acceptance gate.

The decision output must preserve the confidence type so downstream review can distinguish statistical probability from non-statistical engineering certainty.

## 5. Mandatory false fields

Every Phase 22B decision must preserve:

```yaml
canonical_global_merge_performed: false
production_store_write_performed: false
causal_store_write_performed: false
```

## 6. Developer responsibility rule

If `developer_decision_required` is true:

```yaml
developer_owns_decisive_responsibility: true
archive_event_candidate_required: true
```

Master may recommend, but must not hide uncertainty or take decisive real-world responsibility.

## 7. Archive rule for escalation

The Archive event candidate is required only as a candidate. Phase 22B does not write Archive.

It records the responsibility interaction, not the truth of the selected conclusion.
