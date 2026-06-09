# Aegis Runtime Hard Gate Contract

## 1. Purpose

Phase 31A introduces the Aegis governance runtime kernel.

The kernel establishes a system-level boundary between role skill guidance and runtime authority.

A role skill may guide model reasoning. It is not the final authority for executing actions.

The runtime hard gate is the authority for pre-action permission, lifecycle state movement, and artifact-shape admission.

## 2. Core rule

```text
Skill is guidance. Runtime capability is authority.
```

A model may propose an action, reinterpret a request, or argue that a shortcut would improve task success. The runtime must still reject the action when the role lacks capability, required lifecycle state, required artifacts, or artifact contract compliance.

## 3. Phase 31A runtime package

The Phase 31A kernel lives under:

```text
aegis-runtime/governance/
```

It adds:

```text
aegis_governance_runtime.models
aegis_governance_runtime.skill_registry
aegis_governance_runtime.capability
aegis_governance_runtime.artifact_contract
aegis_governance_runtime.state_machine
aegis_governance_runtime.runtime_check
```

## 4. Boundaries enforced in Phase 31A

The kernel defines a machine-readable registry for the current top-level and internal roles:

- `master`
- `debate_leader`
- `debate_worker`
- `execution_leader`
- `execution_front_agent`
- `execution_back_agent`
- `test_leader`
- `test_worker`
- `final_review_leader`

The first hard-gate boundaries are:

- Master must not create department-internal workers.
- Execution Front Agent cannot modify files without `group_branch_proof`.
- Execution Front Agent writes are bounded to its configured write root.
- Execution Back Agent reviews Front output instead of modifying implementation code.
- Test Worker emits route-local evidence and must not modify implementation code.
- Final Review Leader must not create workers, run tests, modify code, or dispatch directly to Execution/Test.
- Commit candidate checks can require a `commit_gate_candidate` artifact.
- Artifact contracts can reject missing required fields and invalid boolean boundary fields.
- State transitions can reject lifecycle jumps when a known `current_state` is supplied.

## 5. Non-goals

Phase 31A does not claim production isolation.

It does not add:

- Docker / namespace / seccomp / AppArmor isolation;
- Git server-side hooks;
- remote branch protection;
- production tool broker service;
- durable audit ledger;
- production release authority;
- global causal truth merge authority.

## 6. Acceptance label

A valid Phase 31A result may be described as:

```text
accepted_phase31a_governance_runtime_kernel
```

It must not be described as:

```text
production_runtime_isolation_closure
production_tool_broker_closure
production_release_authority_closure
global_causal_truth_merge_closure
```
