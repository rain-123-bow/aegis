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

First commit the authorized `src/` or `include/` source snapshot locally. Generate
the next seal from a clean checkout of that exact commit, then commit only the
updated seal record. The seal file is outside `src/` and `include/`, so this does
not create a self-reference cycle.

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
`git_head_before_record` identifies the source commit used to create the record;
it is provenance metadata, not a second startup integrity gate.

## Start a new test run

```powershell
.\.venv\Scripts\python.exe -B src\main.py `
  --project-root C:\code\target-project `
  --artifact-path C:\code\aegis_artifacts\target\current `
  --tracerelay-command "$env:APPDATA\Python\Python313\Scripts\tracerelay.exe"
```

The TraceRelay upstream defaults to the loopback `HTTPS_PROXY`/`HTTP_PROXY`
port. It can be fixed explicitly with `--tracerelay-upstream-port`.

Each C-F `codex exec resume` child receives a fresh TraceRelay application-session
registration before the process starts. Its endpoint remains stable for the
child application's sequential and concurrent proxy connections until Aegis
explicitly closes the evidence session. The child runs in a
Windows Job Object; a relay fault terminates the full `cmd/node/codex/tool`
descendant tree. Proxy bypass variables are removed and all HTTP proxy selectors
are pinned to the registered relay endpoint.

### A/B App Server pilot

When the graph starts at A or B, the coordinator starts one traced
`codex app-server` before `graph.invoke` and creates two persistent top-level
threads:

```text
TEST_PLAN_AUTHOR -> TEST_PLAN_REVIEWER
```

Both roles share the App Server process and one TraceRelay session, but retain
different Codex thread IDs. A failed review keeps the same process and role
threads for the B -> A loop. A passing review stops the App Server and requires
`VALID_COMPLETE` evidence with bytes in both directions before node C can start.
C-F retain the existing per-node `codex exec resume` path during this pilot.

The installed Codex CLI path and version are saved when the App Server starts.
A resumed run rejects a different CLI version. Each `turn/start` receipt is
written to `RUN_STATE.json` before waiting for completion; raw final responses
and SHA-256 values are saved under `<run>/responses/`. A pending turn is read
from its saved persistent thread on resume and is never silently resubmitted.
`planning_stage_status` remains `active` across an interrupted A/B stage and
changes to `completed` only after its TraceRelay session closes as verified
`VALID_COMPLETE` evidence. Later C-F resume operations therefore cannot reopen
the planning App Server.

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
New runs reserve the same identity in `RUN_STATE.json` and SQLite before
TraceRelay starts. Only `--resume-run-id` may reopen that identity.
Raw Codex responses remain under `<run>/responses/`, including malformed output.
TraceRelay failure terminates the active Codex child; Aegis writes the failure
state and exits without restarting TraceRelay or continuing the graph.

The real A/B control-plane acceptance is opt-in:

```powershell
$env:TRACERELAY_COMMAND = 'C:\path\to\tracerelay.exe'
$env:TRACERELAY_UPSTREAM_PORT = '7899'
.\.venv\Scripts\python.exe -B test\test_traced_app_server_real_integration.py
```

It creates a sealed synthetic project, two persistent Codex threads, two real
turns, one TraceRelay session, and an external `ACCEPTANCE_REPORT.json`. It does
not start the A-F graph or use a user project.

Current Windows acceptance:

```text
verdict: PASS
codex-cli: 0.145.0
model: gpt-5.6-sol
reasoning effort: high
report: C:\code\aegis_artifacts\as_pilot\8528efd6a6b6\ACCEPTANCE_REPORT.json
report SHA-256: D172F9FC2F2159062006408A862BF6F35ECB6322B594771B29D233EC9AE2C4CA
TraceRelay evidence: VALID_COMPLETE
```

## Recorded follow-up work

- The legacy `test/test.py` still targets hard-coded archived threads and is not
  part of deterministic test discovery.
- `test_reasoning_ledger.py` still expects the removed flat-reset `ledger`
  command. This predates the runtime coordinator and remains outside this stage.
