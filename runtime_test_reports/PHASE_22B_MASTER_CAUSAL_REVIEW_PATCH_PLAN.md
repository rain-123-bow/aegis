# Phase 22B Master Causal Review Patch Plan

## Scope

Phase 22B adds Master-owned high-budget causal review governance for staged Phase 22A Causal candidates.

It validates:

```text
staged causal_candidate
  + relevant Knowledge context
  + relevant existing Causal context
  + current constraints
  + confidence / uncertainty state
  -> causal_review_decision
```

## Not in scope

Phase 22B does not:

- write the production Causal Store
- perform canonical/global causal truth merge
- write Archive / Knowledge / Causal stores
- create a separate causal-review department
- create a long-lived Causal Review Agent
- add router topology
- take decisive real-world responsibility away from Developer

## Files added

```text
aegis-master-kit/master/MASTER_CAUSAL_REVIEW_GOVERNANCE_POLICY.md
aegis-master-kit/master/CAUSAL_REVIEW_DECISION_CONTRACT.md
aegis-runtime/causal_review/
runtime_test_reports/PHASE_22B_MASTER_CAUSAL_REVIEW_PATCH_PLAN.md
```

## Runtime validation

The deterministic runtime validates mechanical boundaries:

- staged candidate requirement
- Knowledge context requirement
- Causal context requirement or explicit absence reason
- high-confidence support gate
- conflict handling
- developer decision escalation
- Archive event candidate requirement for developer decision
- supersede / invalidate reference checks
- direct merge / store write rejection

Phase 22B deliberately separates statistical probability from deterministic, contract-proven, test-evidence-backed, and static-analysis-backed engineering confidence.

Heuristic / qualitative confidence cannot satisfy the decisive acceptance gate, but statistical evidence is not the only valid high-confidence source.

Expected runtime test count after the confidence semantics fix:

```text
22 passed
```

## Acceptance label

```text
accepted_master_causal_review_boundary
```

## Deferred

Actual causal persistence and canonical store update are deferred to Phase 22C.
