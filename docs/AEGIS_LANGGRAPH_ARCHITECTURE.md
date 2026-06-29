# Aegis LangGraph Architecture

This branch implements the first runnable LangGraph-oriented Aegis v2 milestone.

LangGraph State is runtime state only. Checkpoints are thread-scoped recovery state only.
LangGraph Store is intentionally not used for Aegis project memory. Durable project state
is stored in the target project repository under:

```text
artifacts/
knowledge/
causal/
```

The runtime is intentionally conservative. Tool calls with unclear purpose or irreversible
external effects return a developer interrupt instead of executing automatically.

## Directed Flow Contracts

The runtime declares legal control-flow edges in `aegis.graph.routing`. The first milestone allows:

- Master -> Debate
- Master -> Execution
- Debate -> Execution
- Execution -> Debate
- Execution -> Test
- Test -> Execution
- Test -> Final Review
- Final Review -> Master closeout

Runtime route functions call the routing policy before returning a target node. Same-state visibility
does not create permission to jump to an undeclared node.

## LLM Node Contract

LLM-backed behavior is isolated behind `LlmNodeRequest` and `LlmNodeResult`. The default adapter is
deterministic and CI-safe. Real LLM execution is intentionally disabled until a later pilot.

Every LLM node result is checked for:

- schema validity;
- required output fields;
- self-audit fields;
- tool requests that remain inside the node's allowed tool list;
- Tool Governance approval before any side-effectful action.

Invalid LLM output is blocked instead of being admitted into Knowledge or Causal state.
