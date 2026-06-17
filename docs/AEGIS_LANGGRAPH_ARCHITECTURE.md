# Aegis LangGraph Architecture

This branch implements the first runnable LangGraph-oriented Aegis v2 milestone.

LangGraph State is runtime state only. Checkpoints are thread-scoped recovery state only.
LangGraph Store is intentionally not used for Aegis project memory. Durable project state
is stored in the target project repository under:

```text
archive/
knowledge/
causal/
```

The runtime is intentionally conservative. Tool calls with unclear purpose or irreversible
external effects return a developer interrupt instead of executing automatically.

