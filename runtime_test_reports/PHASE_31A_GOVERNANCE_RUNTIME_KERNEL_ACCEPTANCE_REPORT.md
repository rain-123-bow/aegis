# Phase 31A Governance Runtime Kernel Acceptance Report

## Verdict

Accepted as patch scope: `accepted_phase31a_governance_runtime_kernel`.

Phase 31A adds the first Aegis governance runtime hard-gate kernel. It moves selected role and action boundaries from skill-only prose into executable machine-readable registries and pre-action checks.

## Repository

- Branch: `v0.1.1-alpha-skill`
- Phase: `phase31a_governance_runtime_kernel`
- Push/merge/PR/release: not performed by this patch

## Files Added

```text
aegis-runtime/governance/pyproject.toml
aegis-runtime/governance/README.md
aegis-runtime/governance/aegis_governance_runtime/__init__.py
aegis-runtime/governance/aegis_governance_runtime/models.py
aegis-runtime/governance/aegis_governance_runtime/skill_registry.py
aegis-runtime/governance/aegis_governance_runtime/capability.py
aegis-runtime/governance/aegis_governance_runtime/artifact_contract.py
aegis-runtime/governance/aegis_governance_runtime/state_machine.py
aegis-runtime/governance/aegis_governance_runtime/runtime_check.py
aegis-runtime/governance/tests/test_phase31a_governance_runtime_kernel.py
aegis-master-kit/governance/AEGIS_RUNTIME_HARD_GATE_CONTRACT.md
aegis-master-kit/governance/CAPABILITY_BOUNDARY_CONTRACT.md
aegis-master-kit/governance/ROLE_STATE_MACHINE_CONTRACT.md
runtime_test_reports/PHASE_31A_GOVERNANCE_RUNTIME_KERNEL_ACCEPTANCE_REPORT.md
```

## Runtime Kernel Coverage

The governance runtime kernel introduces these executable boundaries:

1. Machine-readable role skill registry.
2. Capability registry.
3. Artifact contract registry.
4. Role-local finite-state transition registry.
5. Unified runtime pre-action check.

## Verified by Added Tests

The added test file covers the following expected behavior:

- default registry contains all Phase 31A roles;
- Master cannot create department-internal workers;
- Execution Front Agent requires `group_branch_proof` before modifying files;
- Execution Front Agent cannot write outside its capability root;
- Execution Front Agent can write under its configured root when required proof exists;
- Execution Leader cannot skip lifecycle state before creating Front Agent;
- Final Review Leader cannot create workers;
- artifact contract validation rejects incomplete `group_branch_proof`;
- inline artifact validation can allow a complete commit-gate candidate payload.

## Boundary Confirmation

Phase 31A does not claim production closure.

It does not add:

- Docker, namespace, seccomp, AppArmor, or VM isolation;
- production tool broker service;
- Git server-side hooks;
- remote branch protection;
- durable audit ledger;
- production release authority;
- global causal truth merge authority.

## Execution Note

This patch adds the pytest suite but was not locally executed by this assistant in the user's repository checkout.

Recommended local validation:

```powershell
py -3.13 -m venv .venv-governance-runtime
.\.venv-governance-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-governance-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\governance[dev]"
.\.venv-governance-runtime\Scripts\python.exe -m pytest .\aegis-runtime\governance -q
```

## Final Statement

Phase 31A establishes the Step 1 architecture foundation:

```text
skill guidance -> machine-readable registry -> capability/state/artifact checks -> runtime pre-action decision
```

This is the required base for the next phase, where department runtimes should route real orchestration actions through the governance kernel before executing them.
