# Aegis LangGraph Runtime

Aegis v0.1.2 rebuilds the prototype around a LangGraph runtime control plane.

The first milestone is an executable minimum closure:

```text
MasterGraph -> conditional Debate -> Execution Actor -> Dynamic TestSubgraph
  -> Final Review -> Master closeout
```

Core boundaries:

- Master remains the governance owner.
- Master is now a runtime module with continuity preflight, requirement drafting,
  user approval, independent requirement review, Debate-gated review handling,
  second user approval, and Execution handoff.
- Master node-to-node business content is file-ref based. Long-form requirement,
  review, and handoff artifacts live in local artifact packages whose entry file is
  `README.md`; LangGraph state carries refs and approval hashes.
- Master PM intake semantics are governed by
  `src/aegis/modules/master/PM_INTAKE_SEMANTIC_CONTRACT.md`. User pressure,
  insistence, or dissatisfaction is not evidence for admitting an implementation path
  as a hard constraint.
- Master requirement review semantics are governed by
  `src/aegis/modules/master/REQUIREMENT_REVIEW_SEMANTIC_CONTRACT.md`. Review must
  independently re-check PM output by semantic context, project Knowledge refs, and
  first principles; it must not use keyword matching or mechanical technology-name rules.
- Debate is conditional, not a fixed phase.
- Execution v2 uses one single-project Execution Actor by default.
- Test is now an independent Test Subgraph v2 module with input validation,
  plan review, command safety, execution records, code-diff checks, evidence
  checks, artifact schema checks, and file-ref based reports.
- Final Review is a single Leader node; it does not create workers, run tests, or edit code.
- Flow routing is checked through explicit edge contracts instead of unconstrained state visibility.
- LLM behavior is behind an `LlmNodeRequest` / `LlmNodeResult` contract; the default adapter is deterministic and does not call a real LLM.
- Every side-effectful runtime tool call goes through Tool Governance.
- LangGraph checkpointer is used for run recovery and interrupts.
- LangGraph Store is not used for project memory.
- Long-term project state remains local to the project repository under `knowledge/` and `causal/`.
- Project history is represented by git commit history; Aegis no longer maintains a separate project history store.
- Master continuity memory is stored outside the project by default at
  `%LOCALAPPDATA%/Aegis/continuity/continuity.sqlite3`.

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
aegis resume --project-root .\examples\demo-project --thread-id <thread-id> --decision "{\"approved\": true}"
aegis resume --project-root .\examples\demo-project --thread-id <thread-id> --decision "{\"approved\": true}"
```

Successful Master-driven execution now requires two human-in-the-loop approvals bound to
specific artifact package hashes:

1. approve the objective requirement document;
2. approve the independent requirement review document.

The default SQLite checkpoint database is:

```text
<project-root>/.aegis/runtime/checkpoints.sqlite3
```

## Test

```powershell
python -m pytest
python -m ruff check .
```

## First Milestone Status

The current implementation is deterministic-first. It proves the runtime kernel, Master approval
gates, continuity preflight, directed flow, interrupt/resume, standalone Test Subgraph v2,
local Knowledge/Causal candidate boundary, and LLM node contract without enabling real LLM execution
by default.

Master module behavior has also been tested with real subagents using `gpt-5.5` with high
reasoning effort on the concrete “one-time table/chart, user requests C++” scenario. The current
verdict is `real_agent_behavior_passed_with_gateway_limit`; see
`module_test_reports/master/MASTER_REAL_AGENT_ACCEPTANCE_REPORT.md`.

## Repository Layout

```text
src/aegis/modules/        Runtime module implementations, one folder per module.
docs/module_designs/      Complete module design diagrams, with Chinese and English versions.
module_test_reports/      Module-level validation reports.
demo/                     Empty development-stage demo workspace.
examples/demo-project/    Runnable minimal project used by current CLI smoke tests.
```
