# Windows Runtime Coordinator

## Boundary

The coordinator adds four mechanisms to the existing flat A-F graph:

1. verify the latest project seal before opening runtime state;
2. start and monitor the independent TraceRelay application;
3. persist LangGraph node boundaries to project-local SQLite;
4. atomically persist current node, evidence paths, and failures in `artifact_path`.

It does not restore the deleted legacy Aegis graph or let TraceRelay control Aegis.

## One-time setup

```powershell
cd C:\code\aegis
python -m pip install --user .\submodules\TraceRelay
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
```

`tracerelay.exe` must be on `PATH` or supplied through
`--tracerelay-command`. TraceRelay remains installed and may outlive one Aegis
run. Aegis never stops an instance it did not exclusively create for a test.

## Record an authorized source state

Run this after authorized `src/` or `include/` changes and before committing:

```powershell
$env:AEGIS_PROJECT_ROOT = 'C:\code\target-project'
$env:AEGIS_GIT_HEAD = git -C $env:AEGIS_PROJECT_ROOT rev-parse HEAD
@'
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\code\aegis\src")))
from project_seal_store import record_project_seal

record = record_project_seal(
    os.environ["AEGIS_PROJECT_ROOT"],
    git_head_before_record=os.environ["AEGIS_GIT_HEAD"],
)
print(record.expected_seal)
'@ | C:\code\aegis\.venv\Scripts\python.exe -B -
```

The append-only record is stored at:

```text
<project>/.aegis/reasoning_ledger/artifacts/facts/project-seal.json
```

Missing, malformed, broken, or mismatched records block graph startup.

## Start a new test run

```powershell
.\.venv\Scripts\python.exe -B src\main.py `
  --project-root C:\code\target-project `
  --artifact-path C:\code\aegis_artifacts\target\current `
  --tracerelay-command "$env:APPDATA\Python\Python313\Scripts\tracerelay.exe"
```

The TraceRelay upstream defaults to the loopback `HTTPS_PROXY`/`HTTP_PROXY`
port. It can be fixed explicitly with `--tracerelay-upstream-port`.

Each `codex exec resume` child receives a fresh TraceRelay registration before
the process starts. This matches TraceRelay v1's single-client, non-reconnectable
session boundary while covering every A-F agent interaction.

## Resume a failed run

Read the generated run ID from `RUN_STATE.json`, then use:

```powershell
.\.venv\Scripts\python.exe -B src\main.py `
  --project-root C:\code\target-project `
  --artifact-path C:\code\aegis_artifacts\target\current `
  --resume-run-id <run-id> `
  --tracerelay-command "$env:APPDATA\Python\Python313\Scripts\tracerelay.exe"
```

Resume uses the same LangGraph thread ID and passes no new input state. The
failed node runs again; completed nodes do not.

## Durable state

```text
<project>/.aegis/runtime/checkpoints.sqlite3
<artifact_path>/.aegis/runs/<run-id>/RUN_STATE.json
```

`RUN_STATE.json` records the current node, last completed node, latest graph
state, TraceRelay session paths, verification results, and the terminal error.
TraceRelay failure terminates the active Codex child; Aegis writes the failure
state and exits without restarting TraceRelay or continuing the graph.
