# Aegis LangGraph Runtime

Aegis v0.1.2 rebuilds the prototype around a LangGraph runtime control plane.

The first milestone is an executable minimum closure:

```text
MasterGraph -> conditional Debate -> Execution Actor -> Dynamic TestSubgraph
  -> Final Review -> Master closeout
```

Core boundaries:

- Master remains the governance owner.
- Debate is conditional, not a fixed phase.
- Execution v2 uses one single-project Execution Actor by default.
- Test is graph-shaped through a deterministic `TestGraphSpec` compiler.
- Final Review is a single Leader node; it does not create workers, run tests, or edit code.
- Every side-effectful runtime tool call goes through Tool Governance.
- LangGraph checkpointer is used for run recovery and interrupts.
- LangGraph Store is not used for project memory.
- Long-term project state remains local to the project repository under `archive/`, `knowledge/`, and `causal/`.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run

```powershell
aegis run --project-root .\examples\demo-project --goal "implement a small feature"
aegis inspect --project-root .\examples\demo-project --thread-id <thread-id>
aegis resume --project-root .\examples\demo-project --thread-id <thread-id> --decision "{\"approved\": false}"
```

The default SQLite checkpoint database is:

```text
<project-root>/.aegis/runtime/checkpoints.sqlite3
```

## Test

```powershell
python -m pytest
```

