# Aegis Capability Boundary Contract

## 1. Purpose

This contract defines the Phase 31A capability boundary for Aegis runtime actions.

The goal is to move critical invariants out of role-skill prose and into runtime-authorized capabilities.

## 2. Authority rule

```text
A role may reason about any action, but it may execute only host-granted capabilities.
```

If a requested action is not present in the role capability rule, the runtime gate must reject it.

If a requested action is explicitly denied by the role capability rule, the runtime gate must reject it even when a natural-language instruction asks for a shortcut.

## 3. Phase 31A role capability boundaries

### Master

Master may govern, classify, dispatch to valid top-level outgoing routes, create top-level leaders, and create local candidates.

Master must not directly create department-internal workers.

Denied examples:

```text
master -> create_debate_worker
master -> create_execution_front_agent
master -> create_execution_back_agent
master -> create_test_worker
master -> dispatch_to_test
master -> dispatch_to_final_review
```

### Execution Leader

Execution Leader owns execution request validation, group branch creation, Front/Back child creation, accepted group integration, and Test handoff.

Execution Leader must not perform remote push, PR creation, remote merge, release, or deployment.

### Execution Front Agent

Execution Front Agent may modify only allowed files inside its configured Front work root and only after the required group branch proof exists.

Denied examples:

```text
self_approve
review_front_output
remote_push
create_pr
```

### Execution Back Agent

Execution Back Agent reviews Front output and emits review artifacts.

It must not modify implementation code or self-approve.

### Test Leader

Test Leader validates test requests, creates Test Workers, aggregates evidence, and emits Final Review handoff.

It must not modify implementation code.

### Test Worker

Test Worker may read the implementation candidate, run assigned validation, write route-local evidence, and emit a test worker report.

It must not modify implementation code or decide whole-candidate acceptance.

### Final Review Leader

Final Review Leader may read the Final Review package, resolve resource policy, build whole-chain review, and emit a Final Review result.

Denied examples:

```text
create_worker
run_test
modify_code
dispatch_to_execution
dispatch_to_test
```

## 4. Write-root rule

When a role has write access, it must be bounded by configured write roots.

A write outside that root must be rejected before execution.

Phase 31A examples:

```text
execution_front_agent -> workspaces/execution/front
test_worker -> artifacts/test/worker
final_review_leader -> artifacts/final_review
```

## 5. Artifact precondition rule

Actions may require artifact references before execution.

Examples:

```text
execution_front_agent.modify_allowed_files requires group_branch_proof
execution_back_agent.review_front_output requires front_output_candidate
test_worker.emit_test_worker_report requires test_worker_report_candidate
final_review_leader.build_whole_chain_review requires final_review_input_package
```

Missing required artifact refs must reject the action.

## 6. Boundary statement

Capability denial is not a model judgment. It is a host/runtime authorization result.

The runtime must not ask the model to reinterpret denied capabilities.
