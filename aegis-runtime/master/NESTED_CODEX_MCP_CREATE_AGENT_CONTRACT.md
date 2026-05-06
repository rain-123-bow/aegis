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
    "topology_id": "master_top_level_v1"
  }
}
```

## Required response

The response must contain enough structured material for audit.

Minimum accepted structured response:

```json
{
  "agent_id": "execution",
  "role_id": "execution_leader",
  "status": "created",
  "resolved_model": "gpt-5.5",
  "resolved_reasoning_budget": "high"
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
- `resolved_model` differs from the root policy model;
- `resolved_reasoning_budget` differs from the root policy budget;
- response status is not one of `created`, `active`, or `ready`.

## No fake validation

The `validate-real` CLI path must use a real MCP stdio server.

Fake/in-memory clients are allowed only in unit tests.
