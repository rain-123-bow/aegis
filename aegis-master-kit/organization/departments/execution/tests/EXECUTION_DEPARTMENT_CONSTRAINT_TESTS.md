# Execution Department Constraint Tests

Use these tests to check whether a future Codex/AI understands the Execution Department contract.

Answer each case with structured YAML:

```yaml
test_id: ...
decision: accept|reject|request_more_context|request_test_measurement|request_debate|request_changes|send_implementation_candidate_to_test|request_failure_evidence|triage_required|resolve_internal_review_dispute|governance_blocker_to_master|submit_causal_fork_to_master|map_to_group|map_to_integration_owner|rework_required|release_groups|do_not_release
reason: ...
contract_principle: ...
correct_action: ...
risk_if_wrong: ...
```

## Section A - Department Boundary

### T01
A proposal says Execution Groups should be added to the top-level Master route table so Master can inspect them directly.

### T02
A proposal places executable runtime branch-management code inside `aegis-master-kit/organization/departments/execution/`.

### T03
A proposal says only the Execution Leader may communicate with Master, Debate, and Test at the top-level boundary.

## Section B - Debate Trigger

### T04
Two implementation plans exist. Plan A satisfies every constraint with lower risk, lower cost, clearer ownership, and better language support. Plan B is possible but clearly dominated. Should Execution request Debate?

### T05
Three implementation plans exist. All satisfy constraints, each has meaningful trade-offs, and choosing one affects project direction. Should Execution request Debate?

### T06
A task is a deterministic contract lookup. The Leader wants Debate because "more discussion is safer." Is that valid?

## Section C - Task Splitting

### T07
The Leader splits a task into three groups only because the task looks large. No ownership, interface, or local validation criteria are given.

### T08
Two subtasks share an unfrozen interface. The Leader wants two groups to implement both sides in parallel.

### T09
A split defines owned files, input/output contracts, dependency order, local tests, integration risk, and feedback mapping rule.

### T10
A group discovers it must modify another group's owned module. What should happen?

## Section D - Execution Group Lifecycle

### T11
A group finishes initial implementation and local tests. The Leader wants to release it before Test runs.

### T12
Test fails after integration. The Leader wants to create a new random group to fix it without mapping evidence to the original group.

### T13
Test passes. The Leader wants to release active group identities and workspaces while preserving responsibility records, branch history, reviews, test evidence, and causal chain.

## Section E - Front/Back Agent Duties

### T14
The Front Agent implements code and claims the group is accepted without Back Agent review.

### T15
The Back Agent finds a contract violation and returns `request_changes` with evidence. The Front Agent says the code works and refuses to answer.

### T16
The Back Agent rejects without explaining why.

## Section F - Branch and Integration

### T17
A group branch contains changes outside its assigned scope without Leader approval.

### T18
The Leader merges group branches into an integration branch and records branch ownership, changed files, conflicts, and conflict attribution.

### T19
A merge conflict proves two subtasks were not independent. The Leader resolves it manually and sends to Test without recording split invalidity.

## Section G - Test Feedback

### T20
Test passes but gives no feedback. Can Execution release groups?

### T21
Test fails and provides evidence. The Leader maps the failure to group id, subtask id, branch, files, and required fix.

### T22
Test passes with uncovered scope. The Leader releases all groups without recording uncovered scope.

## Section H - Final Causal Chain

### T23
Execution final report says: "Implemented feature X. Tests passed." No causal chain is included.

### T24
Execution final report includes selected plan, split proof, group results, Back Agent objections, integration evidence, Test success feedback, risks, invalidation conditions, and causal candidate status.

### T25
Execution Leader writes the final causal chain directly into global Causal Store without Master merge.

## Section I - Scenario

### T26
Master sends a task requiring two independent documentation updates and one router test update. The Leader proves the docs are independent but the router test depends on both docs. What split and dependency order is valid?

### T27
Test feedback says a failure occurs in a file touched by two groups through an integration conflict resolution. What must the Leader do before assigning rework?

### T28
A future runtime wants to delete group records after release to keep state small. Is that valid?

## Section J - Decision Label Boundary Cases

### T29
Master sends a vague task missing objective, scope, success criteria, affected area, and evidence references.

Expected decision: `request_more_context`.

This must not be labeled `request_failure_evidence`, because no Test failure exists.

### T30
Two valid implementation plans depend on benchmark evidence that has not yet been measured.

Expected decision: `request_test_measurement`.

This must not be labeled `request_debate`, because decisive measurable evidence should be produced first.
This must not be labeled `send_implementation_candidate_to_test`, because no integrated candidate exists.

### T31
Execution Leader has an integrated implementation candidate with integration branch, group mapping, local tests, Back Agent review evidence, known limits, expected Test scope, and evidence references.

Expected decision: `send_implementation_candidate_to_test`.

This is the normal execution -> test handoff.

### T32
Test reports failure but provides no logs, failing command, artifact path, assertion, reproduction step, changed scope, or environment condition.

Expected decision: `request_failure_evidence`.

This must not be labeled `request_more_context`, because the missing information is Test failure evidence, not Master admission context.
This must not be labeled `map_to_group`, because failure evidence does not exist yet.

### T33
Test provides evidence, but the failure could belong to group G1, group G2, or Leader-owned integration merge.

Expected decision: `triage_required`.

The Leader must inspect branch ownership, touched files, integration changes, affected modules, and evidence before assigning owner.

### T34
Test failure evidence shows the bug was introduced by Leader-owned integration glue.

Expected decision: `map_to_integration_owner`.

This must not be forced onto an Execution Group.

### T35
Front Agent and Back Agent disagree about implementation correctness inside one Execution Group.

Expected decision: `resolve_internal_review_dispute`.

The Leader must resolve using diff, tests, contracts, scope, evidence, and first-principles reasoning.

### T36
Front/Back dispute reveals two non-dominated valid implementation designs with real trade-offs.

Expected decision: `request_debate`.

The dispute should be escalated to Debate only because it exposes valid non-dominated alternatives.

### T37
Front/Back dispute reveals release policy, topology, global causal merge, or test-bypass authority issue.

Expected decision: `governance_blocker_to_master`.

This is a Master authority boundary issue, not an internal review disagreement.

### T38
Execution has final test-passed causal chain and branch-local causal fork ready for Master.

Expected decision: `submit_causal_fork_to_master`.

This is not a production merge and not global causal truth. Output status remains `causal_candidate` unless Master merges it.
