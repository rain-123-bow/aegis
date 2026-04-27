# Aegis Router v0.1.2 Engineering Verification Report

## Conclusion

v0.1.2 engineering verification hardening is complete.

No router behavior or contract semantics were changed in this step. The work only standardized installation, local testing, standalone acceptance verification, CI, and release documentation.

Local verification passed in the project-local virtual environment:

```text
python -m pytest                         -> 10 passed
python scripts/acceptance_router_contract.py -> 11 passed, 0 failed
```

## Virtual Environment

The virtual environment was created inside the `aegis-router` project root:

```text
C:\Users\playm\Documents\self-git\patch\aegis-implemented-v0.1\aegis\aegis-router\.venv
```

Creation command:

```powershell
C:\Users\playm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv --copies .venv
```

Note:

```text
python -m venv .venv
```

was initially blocked by Windows application control policy. Re-running with `--copies` succeeded.

Virtual environment Python:

```text
Python 3.12.13
```

Installed package state:

```text
aegis-router 0.1.2
pytest 9.0.3
```

Install commands:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Engineering Changes

### pyproject.toml

Updated:

```text
version = 0.1.2
```

Added explicit dev extra:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]
```

Expected commands now work:

```bash
pip install -e ".[dev]"
python -m pytest
```

### Standalone Acceptance Script

Added:

```text
scripts/acceptance_router_contract.py
```

The script is dependency-light and verifies the same 11 v0.1.1 contract checks.

### GitHub Actions CI

Added:

```text
.github/workflows/router-tests.yml
```

Matrix:

```text
os:
  ubuntu-latest
  windows-latest

python:
  3.11
  3.13
```

CI commands:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m pytest
python scripts/acceptance_router_contract.py
```

### README

Updated README with:

- supported Python: `>=3.11`
- recommended Python: `3.13`
- local runtime install command
- local dev install command
- pytest command
- acceptance script command
- note that v0.1.2 does not change router behavior

### CHANGELOG

Added:

```text
CHANGELOG.md
```

Entries:

- v0.1.1 contract closure summary
- v0.1.2 engineering verification summary
- v0.1.0 initial prototype summary

## Local Test Results

### python -m pytest

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result:

```text
platform win32 -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\playm\Documents\self-git\patch\aegis-implemented-v0.1\aegis\aegis-router
configfile: pyproject.toml
testpaths: tests
collected 10 items

tests\test_mcp_server.py ...      [ 30%]
tests\test_router_core.py ....... [100%]

10 passed in 0.07s
```

### Acceptance Script

Command:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_router_contract.py
```

Result:

```text
passed = 11
failed = 0
```

Acceptance checks:

```text
1. positive same-domain route with ack
2. cross-domain send rejected
3. unregistered send rejected
4. unregistered receive rejected
5. inactive send rejected
6. non-target ack rejected
7. cross-domain parent registration rejected
8. no-ack message reaches terminal completed state
9. heartbeat does not reactivate inactive agent
10. heartbeat rejects unregistered agent
11. malformed MCP call returns controlled InvalidRequestError
```

Representative acceptance output:

```text
positive same-domain route with ack:
  persisted_status = acked

cross-domain send rejected:
  cross-domain message is not allowed in phase 1: master_domain -> isolated_domain

no-ack message reaches terminal completed state:
  received_status = completed
  persisted_status = completed
  ack_error = message does not require ack

malformed MCP call returns controlled InvalidRequestError:
  code = -32000
  type = InvalidRequestError
  message = missing required argument(s) for register_agent: role
```

## Scope Control

No prohibited scope was added:

```text
no cross-domain routing
no topology DSL
no department automation
no new runtime framework dependency
no message lifecycle semantic change
no agent lifecycle semantic change
no unrelated refactor
```

The only new package dependency is `pytest`, and it is confined to the explicit `dev` extra.

## Final Judgment

The v0.1.2 goal is satisfied:

```text
install path standardized
pytest path standardized
standalone acceptance verification added
GitHub Actions workflow ready
README and CHANGELOG updated
local project virtual environment verified
all local tests passed
```
