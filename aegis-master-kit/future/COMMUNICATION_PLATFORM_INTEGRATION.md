# Communication Platform Integration

A future communication platform will allow Codex to call Codex CLI MCP-server-backed agents and route messages through Aegis routers.

Phase 1 does not require full platform implementation.

The expected integration is:

```text
Master owns top router domain.
Department leader owns department router domain.
Every agent registers with its owning router.
Messages are routed by identity, not by global broadcast.
```
