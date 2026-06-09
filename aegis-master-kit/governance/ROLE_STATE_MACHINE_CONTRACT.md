# Aegis Role State Machine Contract

## 1. Purpose

Phase 31A introduces role-local finite-state checks for lifecycle-sensitive Aegis actions.

A role must not skip lifecycle states just because a model or user instruction can describe a faster path.

## 2. Authority rule

```text
Known lifecycle state constrains the next executable action.
```

When a runtime action supplies `current_state`, the governance kernel checks that a valid transition exists for the role, state, and action.

If no transition exists, the action is rejected before execution.

## 3. Phase 31A transition examples

### Execution Leader

```text
execution_request_received
  --create_group_branch-->
group_branch_created

 group_branch_created
  --create_execution_front_agent + group_branch_proof-->
front_agent_created

back_review_accepted
  --integrate_accepted_groups + back_review_candidate-->
leader_integration_created
```

### Test Leader

```text
test_request_received
  --create_test_worker + test_route_plan-->
test_worker_created

test_evidence_aggregated
  --emit_final_review_handoff + final_test_result_candidate + artifact_manifest-->
final_review_handoff_emitted
```

### Final Review Leader

```text
final_review_package_received
  --resolve_resource_policy + final_review_input_package-->
resource_policy_resolved

resource_policy_resolved
  --build_whole_chain_review + final_review_input_package-->
whole_chain_review_built

whole_chain_review_built
  --emit_final_review_result + final_review_result_candidate-->
final_review_result_emitted
```

## 4. Artifact preconditions

A state transition may require artifact refs.

A valid action name alone is not sufficient.

Example:

```text
execution_leader.create_execution_front_agent
```

is invalid from `group_branch_created` unless `group_branch_proof` is present.

## 5. Phase 31A scope

This contract creates the first runtime state-machine kernel. It does not yet claim every department path is fully connected to the runtime main path.

The next phase should insert this check before real department orchestration actions.
