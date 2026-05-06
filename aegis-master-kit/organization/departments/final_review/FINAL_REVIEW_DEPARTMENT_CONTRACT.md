# Final Review Department Contract

## 1. Definition

The Final Review Department is the final review gate before results return to Master.

It performs a single-subject, whole-chain review of:

- final code reference;
- implementation candidate reference;
- Execution final report and execution causal chain;
- Test final result, route reports, evidence, reproducibility set, and artifact manifest;
- Debate references and causal chains when Debate was used;
- known risks, known limits, uncovered scope, blockers, and material conditions;
- governance and responsibility boundaries.

## 2. Non-definition

The Final Review Department is not:

- a generic code review pool;
- a parallel reviewer swarm;
- a Test Department replacement;
- an Execution rework dispatcher;
- a code modification agent;
- a release authority;
- a remote push / merge / deployment executor;
- a global Causal Store merge authority.

## 3. Single-Leader rule

Final Review v0.1 has exactly one internal review subject:

```text
Final Review Leader
```

Internal Final Review Workers are forbidden.

The Leader may use a checklist, but the review must remain one continuous semantic integration process.

Reason:

```text
Final review requires uninterrupted whole-chain semantic integration.
Splitting review into worker fragments risks locally correct judgments with globally broken causality.
```

## 4. External boundary and route rule

The external department boundary is the Final Review Leader.

The valid communication routes are:

Current topology provides only:

```text
test -> final_review
final_review -> master
```

Final Review must not invent:

```text
final_review -> execution
final_review -> test
final_review -> debate
final_review -> archive
final_review -> causal
```

If Final Review recommends Execution rework, Test expansion, more evidence, governance decision, or causal merge rejection, it must return that recommendation to Master.

Master owns the next top-level route.

## 5. Review authority

Final Review owns:

- whole-chain consistency review;
- final candidate/evidence/package completeness review;
- object consistency review;
- scope and limit review;
- evidence sufficiency review;
- governance blocker detection;
- final recommendation to Master.

Final Review does not own:

- implementation changes;
- test execution;
- Execution Group assignment;
- branch merge;
- release;
- production deployment;
- global causal truth merge.

## 6. Required resource policy stance

Final Review must use the role profile assigned to `final_review_leader` by the root model and reasoning-budget policy when that policy exists.

This contract package does not create that root policy file.

This contract does not hard-code concrete model names.

If the configured resource policy is missing, unavailable, lower than required, or fallback would reduce final-review reasoning strength, Final Review must return:

```yaml
decision: blocked_resource_policy
```

and must not perform review.

## Resource policy precedence

Resource policy is evaluated before substantive review.

If the `final_review_leader` profile cannot be resolved or satisfied, the only valid decision is:

```text
blocked_resource_policy
```

This has precedence over:

- object consistency review;
- Test evidence review;
- Execution evidence review;
- Debate consistency review;
- causal candidate assessment.

A missing or insufficient resource policy must not be converted into `request_more_evidence_via_master`, `request_test_expansion_via_master`, or any acceptance label.

## 7. Required input package

A valid Final Review request must include or reference:

```yaml
request_id: ...
source: test
final_code_ref: ...
implementation_candidate_ref: ...
tested_candidate_ref: ...
execution_final_report_ref: ...
execution_causal_chain_ref: ...
test_final_report_ref: ...
test_plan_ref: ...
test_route_report_refs:
  - ...
test_evidence_refs:
  - ...
reproducibility_set_ref: ...
artifact_manifest_ref: ...
known_limits:
  - ...
uncovered_scope:
  - ...
governance_blockers:
  - ...
debate_refs:
  - ...
resource_policy_ref: optional until root policy exists
```

Final Review must not invent missing evidence.

## 8. Required review dimensions

The Leader must evaluate at least:

1. candidate object consistency;
2. Execution output completeness;
3. Test evidence sufficiency;
4. scope coverage and uncovered scope;
5. known limits and risk disclosure;
6. Debate consistency if Debate was used;
7. causal candidate quality;
8. responsibility boundary integrity;
9. governance blocker presence;
10. final handoff completeness for Master.

## 9. Decision labels

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

All decisions are returned to Master through `final_review -> master`.

The suffix `via_master` means Final Review recommends a downstream route, but does not directly route there.

## 10. Acceptance rule

Final Review may return `accept_for_master` only when all conditions hold:

1. final code, implementation candidate, and tested candidate are consistent;
2. Execution output is complete enough for Master review;
3. Test evidence supports the declared validation scope;
4. all mandatory Test routes passed;
5. no unresolved blocker remains;
6. `known_limits` is empty;
7. `blocked_scope` is empty;
8. `missing_evidence` is empty;
9. no hidden uncovered scope remains;
10. causal candidate status is not misrepresented as global causal truth;
11. resource policy requirements are satisfied.

`material_conditions` may be present, but material conditions are not limiting known limits.

If any condition limits the accepted scope, Final Review must not use `accept_for_master`.

## 11. Scope-limited acceptance rule

Final Review may return `accept_for_master_with_scope_limit` when:

1. object consistency is proven;
2. all mandatory Test routes passed;
3. remaining limits are explicit;
4. `known_limits` and/or `blocked_scope` describe the limitation;
5. missing evidence is either absent or explicitly non-material to the accepted scope;
6. Master receives enough information to decide whether scoped acceptance is acceptable.

Any material `known_limits` that constrain the accepted scope must use this label or a non-accept label.

Do not use unconditional `accept_for_master` when limiting `known_limits` are present.

## 12. Rejection and request rules

Final Review must return `reject_to_execution_via_master` when the candidate or Execution output is defective and the next action belongs to Execution.

Final Review must return `request_test_expansion_via_master` when Test evidence or coverage is insufficient and the next action belongs to Test.

Final Review must return `request_more_evidence_via_master` when evidence is missing, stale, contradictory, or not reproducible enough, and the owner is not uniquely Test or Execution.

Final Review must return `governance_blocker_to_master` when Master must decide policy, authority, responsibility, or causal merge boundary.

## 13. Causal boundary

Final Review result is a recommendation to Master.

It may include causal assessment, but it must not directly merge global causal truth.

Only Master or the authorized causal merge process may merge, reject, supersede, or promote causal candidates into global causal state.
