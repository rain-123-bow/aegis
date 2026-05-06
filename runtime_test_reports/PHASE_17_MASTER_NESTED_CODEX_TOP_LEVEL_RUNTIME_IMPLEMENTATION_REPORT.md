# Phase 17 Master Nested-Codex Top-Level Runtime Implementation Report

## Scope

This patch adds the first Master/top-level runtime demo for policy-bound nested-Codex leader creation.

It is demo closure work, not production closure.

## Added Files

```text
aegis-runtime/master/
runtime_test_reports/PHASE_17_MASTER_NESTED_CODEX_TOP_LEVEL_RUNTIME_IMPLEMENTATION_REPORT.md
PATCH_USAGE_MASTER_NESTED_CODEX_TOP_LEVEL.md
```

## Boundary

This patch does not modify:

- `aegis-router/`;
- `aegis-master-kit/organization/topologies/`;
- existing department runtimes;
- existing department contracts;
- `MODEL_REASONING_BUDGET_POLICY.yaml`.

It does not add module-internal worker/front/back profiles.

It does not enable Master dynamic model adjustment.

## Demo Mechanisms Implemented

The runtime implements deterministic demo behavior for:

- loading root `MODEL_REASONING_BUDGET_POLICY.yaml`;
- resolving Master and top-level Leader profiles;
- creating top-level Leaders through a nested-codex MCP client;
- registering created Leaders in the top-level Router domain;
- recording resolved model/reasoning budget in Router metadata;
- verifying top-level allowed communication edges through `status_update`;
- verifying the complete v1 top-level allowed communication edge set, including `debate -> master`;
- writing `top_level_bootstrap_report.json`.

## Real Nested-Codex Validation

The real validation command must use:

```powershell
.\.venv-master-runtime\Scripts\python.exe -m aegis_master_runtime.cli validate-real `
  --policy .\MODEL_REASONING_BUDGET_POLICY.yaml `
  --router-state .\.aegis-master-runtime\router_state.json `
  --output-dir .\.aegis-master-runtime `
  --mcp-command "codex mcp-server" `
  --mcp-tool "<nested-codex-create-agent-tool-name>"
```

This path must call a real MCP stdio server.

The local unit tests use `RecordingNestedCodexClient` only for non-MCP contract validation.

## Production Gaps

Deferred:

- production Master runtime;
- real persistent nested-Codex session lifecycle;
- exact MCP tool name standardization;
- real external model invocation semantics;
- module-internal worker/front/back agent profiles;
- Master-driven dynamic model and reasoning-budget adjustment;
- real git branch/worktree orchestration;
- real Archive / Knowledge / Causal admission;
- global causal merge;
- release / push / merge / deployment.
