# Nested-Codex MCP Create-Agent Contract

## Purpose

This document defines the minimum tool contract expected by the Master runtime for real nested-codex Leader creation validation.

The concrete MCP server is external to this repository.

## Required tool call

The Master runtime calls the configured MCP tool once for each top-level Leader.

Required arguments:

```json
{
  "agent_id": "execution",
  "role_id": "execution_leader",
  "display_name": "Execution Leader",
  "model": "gpt-5.5",
  "reasoning_budget": "high",
  "parent_agent_id": "master",
  "scope": "top_level_master_domain",
  "instructions": "...",
  "metadata": {
    "policy_id": "model_reasoning_budget_policy",
    "policy_version": "v0.1",
    "topology_id": "master_top_level_v1",
    "fallback_authority": "root_policy_only",
    "proof_path": "C:\\...\\leader_proofs\\execution_leader_proof.json",
    "task_output_dir": "C:\\...\\leader_outputs\\execution",
    "write_boundary": {
      "proof_json": "C:\\...\\leader_proofs\\execution_leader_proof.json",
      "task_outputs": "C:\\...\\leader_outputs\\execution",
      "proof_only_is_not_consultation_output": true
    }
  }
}
```

`proof_path` and `task_output_dir` are separate. A Leader may satisfy creation
proof by writing the proof JSON, but later consultation or task outputs must
use the task output directory. A proof-only write boundary must not be reused as
a complete task-output boundary.

## Required response

The response must contain enough structured material for audit.

Minimum accepted structured response:

```json
{
  "agent_id": "execution",
  "role_id": "execution_leader",
  "status": "created",
  "resolved_model": "gpt-5.5",
  "resolved_reasoning_budget": "high",
  "thread_id": "019e...",
  "model_attestation_status": "tool_attested"
}
```

Accepted `model_attestation_status` values:

```text
tool_attested
behaviorally_attested
requested_policy_only
unattested
```

If the external nested-codex tool does not expose independently attested actual
model and reasoning-budget metadata, the response must not claim
`tool_attested`. The runtime may record `requested_policy_only` or `unattested`,
but downstream reports must not treat that as independent proof of actual model
execution.

`behaviorally_attested` is allowed only after the creator challenges the created
agent with a standard deep-reasoning task and records the answer, elapsed time,
rubric score, failed constraints, and final behavioral decision. It is stronger
than `requested_policy_only`, but it is still not `tool_attested`.

Minimum behavioral attestation record:

```json
{
  "agent_id": "execution",
  "role_id": "execution_leader",
  "thread_id": "019e...",
  "requested_model": "gpt-5.5",
  "policy_model": "gpt-5.5",
  "requested_reasoning_budget": "high",
  "policy_reasoning_budget": "high",
  "model_attestation_status": "behaviorally_attested",
  "behavioral_attestation_status": "behavior_consistent_with_requested_profile",
  "challenge_id": "aegis-model-behavioral-attestation-v1",
  "challenge_prompt_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md",
  "rubric_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md#rubric",
  "started_at_utc": "2026-06-02T00:00:00Z",
  "completed_at_utc": "2026-06-02T00:00:30Z",
  "elapsed_ms": 30000,
  "answer_quality_score": 0.84,
  "minimum_quality_score": 0.75,
  "failed_constraints": []
}
```

Accepted status values:

```text
created
active
ready
```

## Hard validation

The Master runtime must reject a response if:

- `agent_id` is missing or differs from requested agent id;
- `role_id` is missing or differs from requested role id;
- `thread_id` is missing or empty;
- `resolved_model` differs from the root policy model;
- `resolved_reasoning_budget` differs from the root policy budget;
- `model_attestation_status` is not `tool_attested`,
  `behaviorally_attested`, `requested_policy_only`, or `unattested`;
- response status is not one of `created`, `active`, or `ready`.

## No fake validation

The `validate-real` CLI path must use a real MCP stdio server.

Fake/in-memory clients are allowed only in unit tests.
