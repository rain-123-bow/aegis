# Phase 19B Execution Real Front/Back Agent Patch Plan

## Scope

This patch moves Execution Department from Phase 19A local git topology closure toward strict real nested-Codex Front/Back agent acceptance.

It does not claim production Execution lifecycle closure.

## Frozen decisions

```text
Execution Leader      = gpt-5.5 / high
Execution Front Agent = gpt-5.5 / high
Execution Back Agent  = gpt-5.5 / high
```

Forbidden in this phase:

- medium Execution Front Agent;
- medium Execution Back Agent;
- silent downgrade;
- fallback from real Front/Back agent to deterministic or in-process output in acceptance;
- Master-created Front/Back agents;
- remote push;
- PR creation;
- production merge;
- release.

## Key semantics

1. Master sees only the Execution Leader.
2. Execution Leader creates one Front and one Back Agent per accepted Execution Group.
3. Front Agent owns implementation and local evidence for its group.
4. Back Agent independently reviews Front output and has blocking authority.
5. Missing Front/Back proof is failure, not skip.
6. Missing Front/Back output is failure, not skip.
7. Phase 19B reuses the sandbox repository boundary introduced in Phase 19A.
8. Output remains a causal candidate unless Master later admits it into global causal truth.

## Production boundary

Not included:

- persistent nested-Codex process lifecycle;
- restart/recovery;
- production worker supervision;
- remote branch governance;
- PR creation;
- remote merge;
- release;
- global causal merge.

## v0.2 Patch Safety Notes

- Patch package excludes `__pycache__/` and compiled Python artifacts.
- Apply script defensively skips `__pycache__/`, `*.pyc`, and `*.pyo`.
- Unit tests validate request/proof/output audit logic; real nested-Codex creation must still be performed through the available local MCP/Codex surface.
- Standardized stdio MCP support is provided as tooling, not proof that the current Codex session exposes that exact tool shape.
