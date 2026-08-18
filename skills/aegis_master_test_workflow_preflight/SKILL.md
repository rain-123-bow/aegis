---
name: aegis-master-test-workflow-preflight
version: 4
description: Verify immutable inputs, runtime dependencies, dynamic role contracts, evidence controls, and user authorization before A-F.
---

# Master A-F Preflight

Master runs this preflight outside A-F. It must not start A-F without explicit durable user authorization.

## Required inputs

- governed project root and project ID;
- user-confirmed requirements and implementation plans;
- `aegis.engineering_input_manifest.v1`;
- complete task-relevant reasoning-ledger context pack;
- user-confirmed runtime behavior scope;
- current Seal chain and protected remote witness;
- runtime root outside `.aegis/`;
- TraceRelay and loopback upstream;
- Codex CLI/App Server capability;
- A-F role templates plus global/role skill hashes;
- launch mode: A-start, resume, or verified C-start reuse.

## Storage

`.aegis/` contains only the reasoning-ledger instance and causal artifacts. Runtime state belongs under:

```text
<runtime-root>/
  project_state/dynamic_agent_registry.json
  project_state/dynamic_agent_registry.sqlite3
  project_state/checkpoints.sqlite3
  runs/<workflow-run-id>/
```

## Immutable checks

1. Validate engineering-input schema, project identity, paths, sizes, and hashes.
2. Validate frozen context-pack path and hash.
3. Validate the fixed scope decision manifest, reviewer report, user statement, policy binding, and protected witness.
4. Resolve the exact runtime manifest.
5. Verify Seal and fetch the protected witness; no offline fallback.
6. Confirm Git identity and the clean-tree rule used when issuing the Seal.

A-F may read only the frozen context pack. Live ledger queries are forbidden.

## Role checks

- Static registry contains templates only.
- Every role binds global and role skill hashes.
- Model is `gpt-5.6-sol`; A-E use `high`; F uses `xhigh`; `ultra` is forbidden.
- Resume requires matching project, role, skill, instructions, model, and effort.
- Faulty threads may be retired and replaced with durable history.
- Require a fresh GPT instruction receipt for every role turn; non-GPT compatibility is outside scope.
- Acquire the project-level single-active-run lease.
- Do not precreate A-F subagents.

## Launch modes

A-start requires new identity, frozen inputs, valid Seal/witness, and user authorization.

Resume uses saved frozen state only.

C-start requires a terminal parent with completed planning, identical engineering document set, sealed approved test plan/review/source state, current frozen context pack, and no unresolved `REQUIRES_USER_REASON` run. Any requirement or plan change forces A-start.

## Dependencies

Verify imports, PostgreSQL/pgvector for ledger export, TraceRelay identity, Codex CLI version, App Server configuration support, writable runtime paths, and remote witness reachability. Missing evidence is a blocker.

## Evidence controls

- C produces `aegis.test_execution_request.v3`, exactly matching the reviewed `aegis.test_execution_policy.v2` block including its complete environment; Coordinator produces v3 execution receipts and `aegis.test_evidence_manifest.v2`.
- D/E/F receive sealed C attempt manifests.
- F produces `aegis.final_review_verdict.v1`.
- F failure requires separate Master confirmation and remains ineligible.
- Frozen-input mutation blocks new runs until the user's reason is sealed.

## Decision

`READY` requires every mandatory check and user authorization. `BLOCKED` names the failed check, exact evidence, and remedy. No implicit degraded launch.
