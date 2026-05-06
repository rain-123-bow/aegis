# Aegis Master Runtime Demo

This package implements the Master-side top-level leader bootstrap demo.

It is **not** production Master runtime.

It demonstrates:

- root `MODEL_REASONING_BUDGET_POLICY.yaml` parsing;
- locked model/reasoning-budget resolution for Master and top-level Leaders;
- no silent downgrade and no fallback in the current phase;
- nested-codex MCP create-agent request generation;
- real nested-codex MCP create-agent validation path;
- top-level Router registration for created Leaders;
- top-level `status_update` route verification;
- audit report generation.

## Boundary

This runtime does not:

- create module-internal workers/front/back agents;
- enable Master dynamic model adjustment;
- modify topology;
- modify router;
- claim production closure.

## Real nested-codex validation

For real validation, use:

```powershell
.\.venv-master-runtime\Scripts\python.exe -m aegis_master_runtime.cli validate-real `
  --policy .\MODEL_REASONING_BUDGET_POLICY.yaml `
  --router-state .\.aegis-master-runtime\router_state.json `
  --output-dir .\.aegis-master-runtime `
  --mcp-command "codex mcp-server" `
  --mcp-tool "<nested-codex-create-agent-tool-name>"
```

The runtime will fail if the nested-codex MCP server does not actually create all required top-level Leader agents.

## Test validation

Unit tests use an injected recording client only to verify local contract behavior.

They do not claim real nested-codex creation.

```powershell
py -3.13 -m venv .venv-master-runtime
.\.venv-master-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-master-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-master-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\master[dev]"

.\.venv-master-runtime\Scripts\python.exe -m pytest .\aegis-runtime\master
```
