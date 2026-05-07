# Aegis Execution Sandbox

This repository is a small Python target project for testing the Aegis Execution Department.

It is not the Aegis control-plane repository. It is a business-code sandbox that Execution Leader, Execution Groups, Front Agents, Back Agents, Test Department, and Final Review can safely modify, test, review, and package.

## Purpose

The sandbox exists to validate real execution behavior without polluting the Aegis organization repository.

Aegis should treat this repository as:

```text
aegis-execution-sandbox = business code repo + archive + knowledge + causal stores
```

Aegis must keep the following boundaries:

- `src/` and `tests/` are ordinary project code and tests.
- `archive/` records what happened during tasks.
- `knowledge/` stores verified static facts and constraints.
- `causal/` stores governed causal structures and candidates.
- Archive entries do not automatically become truth.
- Knowledge facts do not automatically become causal truth.
- Causal entries must preserve why, evidence, scope, assumptions, and invalidation conditions.

## Current functional scope

The project implements a tiny work-item classifier.

It can:

- normalize a work-item title;
- validate work-item fields;
- compute a deterministic priority score;
- classify a work item into an execution route.

This scope is intentionally small. It gives the Aegis Execution Department enough surface area to test:

- single-subtask implementation;
- multi-subtask split;
- Front Agent implementation output;
- Back Agent review output;
- local unit tests;
- integration candidate packaging;
- Test feedback mapping;
- causal handoff records.

## Repository layout

```text
src/aegis_execution_sandbox/   Python package under test
tests/                         Unit tests
archive/                       Task/process records, not truth
knowledge/                     Verified static facts and constraints
causal/                        Causal structures and causal candidates
docs/                          Sandbox-specific testing guidance
```

## Quick start

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -vv
```

Linux/macOS equivalent:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -vv
```

## Responsibility boundary

This repository is a sandbox for Aegis execution tests. Aegis may generate implementation candidates and reports against it.

Developers retain responsibility for remote push, branch merge, release, deployment, and external sign-off.
