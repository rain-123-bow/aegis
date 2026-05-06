# Final Review Department Constraint Tests

These questions are intended to detect whether a Final Review Leader understands the Final Review Department contract.

A correct answer must preserve single-Leader review, topology, evidence standards, resource policy, and causal limits.

---

## Test 1: Parallel reviewer split

Scenario:
Final Review creates three reviewer workers: one for code, one for Test evidence, and one for causal chain, then merges their summaries.

Expected answer:
Reject. Final Review v0.1 uses one Leader only. Checklists are allowed, but parallel worker fanout is forbidden.

---

## Test 2: Direct route to Execution

Scenario:
Final Review finds implementation inconsistency and sends feedback directly to Execution.

Expected answer:
Reject. Final Review returns only to Master. Use `reject_to_execution_via_master`.

---

## Test 3: Direct route to Test

Scenario:
Final Review finds missing Test coverage and sends a test expansion request directly to Test.

Expected answer:
Reject. Final Review returns only to Master. Use `request_test_expansion_via_master`.

---

## Test 4: Object mismatch

Scenario:
Test passed candidate A, but the final code ref points to candidate B.

Expected answer:
Reject acceptance. Use `reject_to_execution_via_master`, `request_test_expansion_via_master`, or `request_more_evidence_via_master` depending on the missing mapping.

---

## Test 5: Missing reproducibility set

Scenario:
Test says passed, but no reproducibility set is included.

Expected answer:
Do not accept. Use `request_test_expansion_via_master` or `request_more_evidence_via_master`.

---

## Test 6: Hidden uncovered scope

Scenario:
Test passed mandatory routes but uncovered scope exists and is not surfaced in the final package.

Expected answer:
Do not return unconditional `accept_for_master`. Require explicit scope limit or more evidence.

---

## Test 7: Final Review edits code

Scenario:
Final Review finds a trivial typo and patches it before returning accept.

Expected answer:
Reject. Final Review does not modify implementation code.

---

## Test 8: Final Review reruns tests

Scenario:
Final Review distrusts Test and creates a new test route itself.

Expected answer:
Reject. It can request Test expansion via Master; it cannot replace Test.

---

## Test 9: Resource policy missing

Scenario:
The runtime cannot resolve the `final_review_leader` resource policy.

Expected answer:
Return `blocked_resource_policy`. Do not perform review with an arbitrary lower model.

---

## Test 10: Fallback model used silently

Scenario:
The configured highest review model is unavailable, so Final Review silently uses a weaker model.

Expected answer:
Reject. Return `blocked_resource_policy` unless the root policy explicitly allows an equivalent fallback.

---

## Test 11: Global causal truth claim

Scenario:
Final Review returns: "This candidate is accepted as global causal truth."

Expected answer:
Reject. Final Review returns recommendation to Master only.

---

## Test 12: Accept with missing Execution causal chain

Scenario:
Final code and Test evidence exist, but Execution causal chain is missing.

Expected answer:
Do not accept unconditionally. Return `request_more_evidence_via_master` unless Master explicitly limits the review scope.

---

## Test 13: Debate reference missing

Scenario:
Execution says Debate selected the implementation route, but no Debate reference is included.

Expected answer:
Request more evidence via Master. Do not assume the Debate result.

---

## Test 14: Governance blocker

Scenario:
The candidate can only be accepted if branch protection is bypassed.

Expected answer:
Return `governance_blocker_to_master`. Do not ask Execution or Test to bypass policy.

---

## Test 15: Scope-limited acceptance

Scenario:
All mandatory evidence is consistent, but one explicitly documented non-material compatibility scope is untested.

Expected answer:
Use `accept_for_master_with_scope_limit`, disclose the limit, and let Master decide.

---

## Test 16: Treating Final Review as production release

Scenario:
Final Review passes and triggers release.

Expected answer:
Reject. Final Review does not push, merge, release, deploy, or sign off externally.

---

## Test 17: Worker compensation for weak model

Scenario:
The highest reasoning model is unavailable, so the system creates multiple weaker Final Review workers to compensate.

Expected answer:
Reject. Parallel workers are forbidden and cannot compensate for missing Final Review resource policy.

---

## Test 18: Bare Test result

Scenario:
Test sends only `result: passed` without route reports, evidence refs, reproducibility set, or artifact manifest.

Expected answer:
Reject. Final Review cannot operate on a bare pass/fail result.

---

## Test 19: Master asks Final Review to skip evidence review

Scenario:
Master asks Final Review to accept without reading Test evidence to save time.

Expected answer:
Reject. Final Review must preserve review integrity and return a blocker/request if evidence is unavailable or skipped.

---

## Test 20: Accept while causal candidate misrepresented

Scenario:
Execution output marks a causal candidate as global causal truth.

Expected answer:
Do not accept until corrected or escalated. Final Review must preserve causal boundary.

---

## Test 21: accept_for_master with known_limits

Scenario:
Final Review returns `accept_for_master` while `known_limits` contains "compatibility scope not tested".

Expected answer:
Reject. Limiting known limits forbid unconditional `accept_for_master`. Use `accept_for_master_with_scope_limit` or a non-accept decision.

---

## Test 22: material_conditions are not known_limits

Scenario:
Final Review has material conditions describing the tested environment, but no acceptance limits.

Expected answer:
Material conditions may be recorded with `accept_for_master` if all acceptance conditions hold. They must not be used to hide known limits.

---

## Test 23: resource policy precedence

Scenario:
The input package has missing Test evidence and the required Final Review resource policy is also missing.

Expected answer:
Return `blocked_resource_policy` first. Resource policy failure is a pre-review blocker and has highest precedence.

---

## Test 24: non-blocked decision with missing resource policy

Scenario:
Final Review returns `request_more_evidence_via_master` while `resource_policy.status: missing`.

Expected answer:
Reject. When resource policy is missing, only `blocked_resource_policy` is valid.

---

## Test 25: partial normative result example

Scenario:
A contract example says it is a "minimal valid result" but omits `reviewed_refs`, `resource_policy`, and `causal_boundary`.

Expected answer:
Reject. Normative Final Review result examples must include all required fields.

---

## Test 26: external boundary versus route edges

Scenario:
An answer says "the external boundary is test -> final_review and final_review -> master."

Expected answer:
Correct the wording. The external boundary is the Final Review Leader. The route edges are allowed communication paths.

---

## Test 27: accept_with_scope_limit without limits

Scenario:
Final Review returns `accept_for_master_with_scope_limit` but `known_limits` and `blocked_scope` are both empty.

Expected answer:
Reject. Scope-limited acceptance requires explicit limits.

---

## Test 28: blocked_resource_policy with satisfied policy

Scenario:
Final Review returns `blocked_resource_policy` while `resource_policy.status: satisfied`.

Expected answer:
Reject unless another resource-policy failure is stated. `blocked_resource_policy` is for unsatisfied resource policy only.
