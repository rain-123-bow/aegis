# Aegis

Aegis is a layered AI organization architecture for governed multi-agent software engineering.

It is not a generic agent chat framework. The first prototype focuses on two things:

1. `aegis-master-kit`: a project-independent organization architecture kit for the Master agent.
2. `aegis-router`: a lightweight MCP-style local message router for agent communication domains.

## Core idea

```text
aegis-master-kit = organization constitution / management architecture / Master-level governance
specific business = code-repo + aegis-archive + aegis-causal + aegis-knowledge
```

`aegis-master-kit` is not a project knowledge base, not a causal truth store, not a task archive, and not a code repository. It only tells the Master how to organize work.

## High-level governance flow

The following diagram shows the high-level Master governance flow. It is not a complete system architecture diagram.

![Aegis high-level governance flow](docs/aegis-high-level-governance-flow.png)

## Repository layout

```text
aegis/
  docs/                 Project definitions, technical baseline, and phase scope
  aegis-master-kit/     Master constitution and top-level organization architecture
  aegis-router/         Python implementation of a local MCP-style message router
  aegis-runtime/        Demo/runtime implementations that execute master-kit contracts
  examples/             Demo business skeleton showing how code + three libraries may coexist
```

## Phase-1 scope

Phase 1 validates the following chain:

```text
Developer -> Codex Master -> aegis-master-kit -> top-level departments -> department leaders -> aegis-router communication
```

Phase 1 does **not** implement a full autonomous software company, a full causal database, or automatic code submission.

## Responsibility boundary

Aegis can generate candidates. Developers retain all critical responsibility actions, including remote push, main-branch merge, release, and formal external sign-off.
