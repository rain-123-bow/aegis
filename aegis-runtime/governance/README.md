# Aegis Governance Runtime Kernel

This package implements the Phase 31A runtime hard-gate kernel.

It is the first executable boundary that separates role-skill guidance from runtime action authority.

## What it provides

```text
aegis_governance_runtime.models
aegis_governance_runtime.skill_registry
aegis_governance_runtime.capability
aegis_governance_runtime.artifact_contract
aegis_governance_runtime.state_machine
aegis_governance_runtime.runtime_check
```

## Core rule

```text
Skill is guidance. Runtime capability is authority.
```

A model may reason about a shortcut, but the runtime must reject an action when the role lacks the required capability, state transition, artifact reference, or artifact contract shape.

## Phase 31A status

This package is a kernel foundation.

It does not yet wire every department runtime path through the kernel. That integration belongs to the next phase.

## Local validation

From repository root:

```powershell
py -3.13 -m venv .venv-governance-runtime
.\.venv-governance-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-governance-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\governance[dev]"
.\.venv-governance-runtime\Scripts\python.exe -m pytest .\aegis-runtime\governance -q
```

## Boundary

This package does not provide Docker, OS sandboxing, Git server-side enforcement, production tool brokering, release authority, or global causal truth merge authority.
