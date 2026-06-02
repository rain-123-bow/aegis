# Phase 30B Nested-Codex Behavioral Model Attestation Report

## Scope

Phase 30B adds a behavioral model/reasoning-budget attestation path for
nested-Codex agents when tool-level attestation is unavailable.

This phase does not claim tool-level proof of actual backend model execution.

## Problem

The nested-Codex tool may not independently return authoritative runtime
metadata such as:

- actual resolved model;
- actual resolved reasoning budget;
- fallback status;
- fallback reason.

Phase 30A made this explicit through `requested_policy_only` and `unattested`.
Phase 30B adds a stronger inferential option: `behaviorally_attested`.

## Behavioral Attestation Rule

Master may challenge a created agent with a fixed deep-reasoning task:

```text
aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md
```

The challenge checks whether the agent can reason correctly about:

- `test -> master` route rejection;
- topology patch admission;
- role-local fallback versus root-policy-only fallback;
- `tool_attested` versus `behaviorally_attested` versus `requested_policy_only` versus `unattested`;
- counterexamples where fluent answers still fail;
- the difference between policy conclusions and behavioral inference.

Passing the challenge may record:

```text
model_attestation_status: behaviorally_attested
behavioral_attestation_status: behavior_consistent_with_requested_profile
```

It must not record:

```text
model_attestation_status: tool_attested
```

unless the tool itself provides authoritative runtime metadata.

## Runtime Validation

The Master operational skill validator now checks behavioral attestation records.

Accepted behavioral attestation requires:

- `agent_id`
- `role_id`
- `thread_id`
- `requested_model`
- `policy_model`
- `requested_reasoning_budget`
- `policy_reasoning_budget`
- `challenge_id`
- `challenge_prompt_ref`
- `rubric_ref`
- `started_at_utc`
- `completed_at_utc`
- positive `elapsed_ms`
- `answer_quality_score >= minimum_quality_score`
- empty `failed_constraints`

The validator rejects:

- behavioral records that claim `tool_attested`;
- low-quality answers;
- accepted records with failed constraints;
- malformed behavioral attestation status.

## Files Changed

- `MODEL_REASONING_BUDGET_POLICY.yaml`
- `README.md`
- `aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL.md`
- `aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md`
- `aegis-runtime/master/NESTED_CODEX_MCP_CREATE_AGENT_CONTRACT.md`
- `aegis-runtime/master/README.md`
- `aegis-runtime/master/aegis_master_runtime/models.py`
- `aegis-runtime/master/aegis_master_runtime/operational_skill.py`
- `aegis-runtime/master/tests/test_master_top_level_policy_and_bootstrap.py`
- `aegis-runtime/master/tests/test_phase24a_master_operational_workflow_skill.py`
- `aegis-runtime/master/tests/test_phase30a_governance_ambiguity_hardening.py`

## Boundary

- Behavioral attestation is inferential.
- It can detect obvious low-model or low-budget behavior.
- It is stronger than request/policy-only evidence.
- It remains distinct from tool-level attestation.
- It does not prove exact backend model identity.
- It does not change topology, router behavior, production closure, remote push,
  PR, merge, release, or global causal truth.

## Validation

Commands run:

```powershell
.\.venv-master-skill-phase24a\Scripts\python.exe -m pytest .\aegis-runtime\master -q
git diff --check
```

Results:

```text
pytest: 39 passed, 2 skipped in 0.23s
git diff --check: passed
LF audit: passed
```
