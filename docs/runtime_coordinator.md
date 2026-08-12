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

Each C-F turn receives a fresh TraceRelay application-session registration before
its App Server process starts. Its endpoint remains stable for the process's
sequential and concurrent proxy connections until Aegis explicitly closes the
evidence session. The process runs in a Windows Job Object; a relay fault
terminates the full `cmd/node/codex/tool` descendant tree. Proxy bypass variables
are removed and all HTTP proxy selectors are pinned to the registered relay
endpoint.

### A/B App Server and frozen planning handoff

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

Each A attempt receives a unique directory:

```text
<artifact_path>/.aegis/planning/<run-id>/round-NNNN/
```

A writes `TEST_PLAN.md`. The coordinator freezes its SHA-256 together with the
verified project seal and reasoning-context SHA-256 before B starts. B reviews
only that hash and writes the complete result to the separate
`TEST_PLAN_REVIEW.md`. The structured response carries the reviewed hash,
score, error count, warning count, and verdict. The coordinator requires the
reviewed hash to equal the frozen plan hash during live review and every
restore. The same binding is retained in `PLANNING_HANDOFF.json`.

The coordinator ignores the reviewer's routing `status`. It passes the round
only when score is at least 95, error count is zero, verdict is `PASS`, both
files still match their hashes, and the project seal and reasoning context are
unchanged. Passing publishes exact-byte `APPROVED_TEST_PLAN.md` plus the
machine-readable `PLANNING_HANDOFF.json`. A rejected round is retained and the
next A turn receives its review-report path. Completed author or reviewer turns
are replayed from their hashed response files after interruption; they are not
resubmitted.

The installed Codex CLI path and version are saved when the App Server starts.
A resumed run rejects a different CLI version. Each `turn/start` receipt is
created as a durable `submitting` intent before the remote call. The exact turn
ID is then persisted as `inProgress` before waiting for completion. If a crash
leaves `submitting` without a turn ID, the outcome is ambiguous and resume fails
closed; it never guesses by resubmitting. Raw final responses and SHA-256 values
are saved under `<run>/responses/`. A known pending turn is read from its saved
persistent thread on resume, while a completed turn is replayed from its hashed
local response.
`planning_stage_status` remains `active` across an interrupted A/B stage. It
changes to `completed` only when an approved handoff exists and every planning
TraceRelay session recorded for the run has both raw journal
`verification_status=VALID_COMPLETE` and
`application_verification_status=VALID_COMPLETE`. The application status is
set only when managed finalization returns after its bidirectional-byte check;
an exception records `INVALID` even if the raw journal closed as valid. A newer
valid session cannot hide an older incomplete session. Later C-F resume
operations therefore cannot reopen the planning App Server.

Round allocation and approval publication are recoverable state transitions.
An `allocating` round is recorded before its directory is created. An accepted
review is recorded as `publishing`; both root publication files are generated
and verified before the round becomes `approved`. Resume completes an
interrupted `publishing` operation idempotently. An `approved` round is never
trusted from its status alone: score, error count, verdict, frozen files,
published plan, and the complete handoff object are revalidated.

### C-F per-turn App Server transactions

C, D, E, and F each own one persistent, non-ephemeral Codex thread for the run. The
coordinator creates a new `codex app-server` process and a new TraceRelay
session for every C-F turn, resumes the role thread in that process, executes or
recovers exactly one turn, then closes and verifies both resources before the
node may return.

The coordinator records a monotonic execution attempt before entering C-F.
This identity separates a crash retry from the legal `C -> D -> C` loop. Each
turn records its attempt, role thread ID, turn ID, request hash, response path
and hash, TraceRelay session IDs, and App Server identity: PID plus Windows
process creation FILETIME. The role thread survives; process identity and
evidence session do not.

Recovery is fail-closed:

- a completed turn is replayed only from its hash-verified response after every
  linked journal is re-read from disk, returns `VALID_COMPLETE`, has nonzero
  traffic in both directions, and reproduces the recorded final hash;
- a known turn ID is read from the persistent thread in a new traced process and
  is never resubmitted;
- after a coordinator process crash, the saved PID is terminated only when its
  Windows process creation FILETIME still matches; a missing or reused PID is
  not terminated. The exact TraceRelay session is still sealed and verified
  before the known turn is recovered in a new session;
- `submitting` without a turn ID is ambiguous and cannot be retried;
- a lost `thread/start` result leaves the role `allocating` and cannot be
  replaced silently;
- an invalid older session cannot be hidden by a newer valid session;
- App Server close, process termination, or evidence finalization failure blocks
  routing.
- run completion requires the terminal graph state, last completed node, final
  attempt, response hash, and evidence to bind to F. F may return `status=false`;
  that remains a business verdict while the run lifecycle becomes completed.

## Resume a failed run

Read the generated run ID from `RUN_STATE.json`, then use:

```powershell
.\.venv\Scripts\python.exe -B src\main.py `
  --project-root C:\code\target-project `
  --artifact-path C:\code\aegis_artifacts\target\current `
  --resume-run-id <run-id> `
  --tracerelay-command "$env:APPDATA\Python\Python313\Scripts\tracerelay.exe"
```

Resume uses the same LangGraph thread ID and passes no new input state. A known
pending turn may resume only while its saved TraceRelay session remains
recoverable (`UNVERIFIED` with no application verdict). If finalization marked a
session `INVALID`, or the journal verifies as `VALID_INCOMPLETE`, the run remains
failed and resume is rejected before TraceRelay or a new Codex process starts.
Completed nodes do not run again.

## Durable state

```text
<project>/.aegis/runtime/checkpoints.sqlite3
<artifact_path>/.aegis/runs/<run-id>/RUN_STATE.json
```

`RUN_STATE.json` uses `aegis.run_state.v4` and records the current node, last completed node, latest graph
state, TraceRelay session paths, verification results, and the terminal error.
New runs reserve the same identity in `RUN_STATE.json` and SQLite before
TraceRelay starts. Only `--resume-run-id` may reopen that identity.
Raw Codex responses remain under `<run>/responses/`, including malformed output.
TraceRelay failure terminates the active Codex child; Aegis writes the failure
state and exits without restarting TraceRelay or continuing the graph.

Version-1 through version-3 run states are rejected on resume. Version 3 cannot
prove whether a legacy E/F turn already produced a report or final-review side
effect, so conversion could duplicate it. Start a new run instead.

The real App Server control-plane acceptance is opt-in:

```powershell
$env:TRACERELAY_COMMAND = 'C:\path\to\tracerelay.exe'
$env:TRACERELAY_UPSTREAM_PORT = '7899'
.\.venv\Scripts\python.exe -B test\test_traced_app_server_real_integration.py
```

It proves both boundaries on a sealed synthetic project: A/B share one traced
process, while C/D/C/D/E/F use six new processes and sessions, reuse the C and D
threads, keep all four execution roles independent, bind the E report into the F
review, and write an external `ACCEPTANCE_REPORT.json`. It does not use a user
project.

Current Windows acceptance:

```text
verdict: PASS
codex-cli: 0.145.0
model: gpt-5.6-sol
reasoning effort: high
report: C:\code\aegis_artifacts\as_pilot\1e1497df823c\ACCEPTANCE_REPORT.json
report SHA-256: 76CB7B776A1A2EC85A167FD693297D550D4010E562D0CC5B682AEDCA01DD12CC
TraceRelay journal evidence: VALID_COMPLETE
application evidence: VALID_COMPLETE
planning rounds: 1 (approved)
planning review: PASS, score 100, error count 0
approved plan SHA-256 equals reviewed plan SHA-256
C/D/C/D/E/F execution turns: 6
C/D/C/D/E/F TraceRelay sessions: 6, distinct
C/D/C/D/E/F App Server PIDs: 6, distinct
C/D/C/D/E/F App Server creation FILETIMEs: 6, distinct
TEST_EXECUTOR thread reused across both C turns
TEST_RESULT_REVIEWER thread reused across both D turns
TEST_REPORT_WRITER and FINAL_REVIEWER threads independent
synthetic command stdout: True
synthetic command exit code: 0
E report SHA-256: 3599CF889EFEB9CCB36A070462CD0BB153B41E1129C40086CB59AE83F1286492
F review binds the exact E report SHA-256: yes
```

Hard-crash recovery acceptance:

```text
verdict: PASS
node: F
report: C:\code\aegis_artifacts\as_crash_recovery\6660509e0f3f\CRASH_RECOVERY_REPORT.json
report SHA-256: 4BE86B73E6DE23E2523C4F77EC7A6C7D312286CB7193100762E6F82C0886CA61
forced coordinator exit code: 91
Codex turn IDs created: 1
TraceRelay sessions: 2, distinct
App Server Windows Job PIDs: 2, distinct
App Server creation FILETIMEs: 2, distinct
both saved Windows Job PIDs terminated after recovery: yes
old session sealed before known-turn recovery: yes
all raw and application evidence: VALID_COMPLETE
```

TraceRelay service-failure acceptance:

```text
verdict: PASS
report: C:\ar\ef0812d\RUNTIME_CODEX_ACCEPTANCE_20260812T094709Z.json
report SHA-256: EFB384730816D1E9631222BF026C5FDAAF965E92F59A864891F8A0598EEBBC70
normal F evidence: VALID_COMPLETE, bidirectional bytes > 0
fault F evidence: VALID_INCOMPLETE
fault RUN_STATE evidence: UNVERIFIED/INVALID
runner plus 10 observed descendants terminated: yes
same-run resume rejected before TraceRelay restart: yes
same-run resume started a Codex process: no
```

## Recorded follow-up work

- The legacy `test/test.py` still targets hard-coded archived threads and is not
  part of deterministic test discovery.
- `test_reasoning_ledger.py` still expects the removed flat-reset `ledger`
  command. This predates the runtime coordinator and remains outside this stage.
