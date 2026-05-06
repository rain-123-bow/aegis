# Final Review Result and Handoff Contract

## 1. Purpose

This contract defines how Final Review returns results to Master.

## Decision precedence

Final Review decisions must be selected in this order:

1. Resource policy unresolved or insufficient -> `blocked_resource_policy`.
2. Governance/policy/authority blocker -> `governance_blocker_to_master`.
3. Candidate object mismatch or Execution-owned defect -> `reject_to_execution_via_master`.
4. Test coverage/evidence route deficiency -> `request_test_expansion_via_master`.
5. Missing, stale, contradictory, or non-reproducible evidence without unique owner -> `request_more_evidence_via_master`.
6. All acceptance conditions hold with explicit limits -> `accept_for_master_with_scope_limit`.
7. All acceptance conditions hold with no limits -> `accept_for_master`.

Resource policy failure always stops the review before substantive acceptance or evidence routing.

## 2. Only valid output route

Final Review output route:

```text
final_review -> master
```

No other output route is valid in v0.1.

## 3. Message type

Preferred message type:

```text
final_review_result
```

## 4. Decision labels

Allowed decisions:

```text
accept_for_master
accept_for_master_with_scope_limit
reject_to_execution_via_master
request_test_expansion_via_master
request_more_evidence_via_master
governance_blocker_to_master
blocked_resource_policy
```

## 5. Decision semantics

### accept_for_master

Use only when all acceptance conditions hold and:

```yaml
known_limits: []
blocked_scope: []
missing_evidence: []
governance_blockers: []
resource_policy:
  status: satisfied
```

`accept_for_master` must not be used when any material known limit constrains the accepted scope.

Material conditions may be present, but they are not limiting known limits.

### accept_for_master_with_scope_limit

Use when the candidate is acceptable for Master review only under explicit limits.

This label requires:

```yaml
known_limits:
  - ...
# and/or
blocked_scope:
  - ...
```

The result must explain why the accepted scope remains reviewable despite the limits.

Do not use this label when a mandatory Test route failed, when evidence is contradictory, or when resource policy is missing.

### Other non-accept decisions

- `reject_to_execution_via_master`: implementation, integration, Execution evidence, or object consistency requires Execution action.
- `request_test_expansion_via_master`: Test evidence, coverage, route scope, reproducibility, or artifacts are insufficient.
- `request_more_evidence_via_master`: required evidence is missing, stale, contradictory, or not reproducible enough.
- `governance_blocker_to_master`: Master must decide policy, authority, topology, release, responsibility, or causal merge boundary.
- `blocked_resource_policy`: required Final Review model/resource policy cannot be resolved or satisfied.

## 6. Required output fields

```yaml
final_review_result_id: string
request_id: string
decision: accept_for_master|accept_for_master_with_scope_limit|reject_to_execution_via_master|request_test_expansion_via_master|request_more_evidence_via_master|governance_blocker_to_master|blocked_resource_policy
target: master
why: string
final_code_ref: string
implementation_candidate_ref: string
tested_candidate_ref: string
reviewed_refs:
  execution_final_report_ref: string
  execution_causal_chain_ref: string
  test_final_report_ref: string
  test_plan_ref: string
  test_route_report_refs:
    - string
  test_evidence_refs:
    - string
  reproducibility_set_ref: string
  artifact_manifest_ref: string
  debate_refs:
    - string
accepted_scope:
  - string
blocked_scope:
  - string
known_limits:
  - string
missing_evidence:
  - string
governance_blockers:
  - string
resource_policy:
  policy_ref: string
  required_profile: final_review_leader
  resolved_profile: string
  reasoning_budget: maximum|unknown
  fallback_used: false|true
  status: satisfied|missing|unavailable|insufficient|fallback_forbidden
causal_boundary: string
recommended_master_action: string
```

The YAML above is a minimum full result shape.

Any example Final Review result must include all required fields or explicitly state that it is a non-normative fragment.

Normative examples must not omit:

- `final_review_result_id`;
- `request_id`;
- `target`;
- `reviewed_refs`;
- `resource_policy`;
- `causal_boundary`;
- `recommended_master_action`.

## 7. Invalid outputs

Contract violations:

1. returning directly to Execution;
2. returning directly to Test;
3. saying the candidate is globally accepted truth;
4. hiding uncovered scope;
5. accepting when tested object and final object differ materially;
6. accepting when resource policy is missing or insufficient;
7. accepting without Test evidence;
8. accepting without final code reference;
9. performing push, merge, release, or deployment;
10. returning `accept_for_master` with non-empty `known_limits`;
11. returning `accept_for_master` with non-empty `blocked_scope`;
12. returning `accept_for_master` with non-empty `missing_evidence`;
13. returning any non-`blocked_resource_policy` decision when `resource_policy.status` is `missing`, `unavailable`, `insufficient`, or `fallback_forbidden`;
14. providing normative result examples that omit required fields.
