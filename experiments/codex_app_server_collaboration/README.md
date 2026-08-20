# Codex App Server collaboration PoC

## Scope

This directory is isolated from the A-F runtime. It does not read the agent
registry, call `src/main.py`, start TraceRelay, or change project seals.

The probe tests one orchestration shape:

```text
producer -> [reviewer_boundary, reviewer_evidence] -> aggregator
```

LangGraph is the only router. Every role receives a separate top-level Codex
thread. Reviewers read the same frozen producer payload and cannot communicate
directly.

## Acceptance conditions

- four completed role executions;
- four unique Codex thread IDs and turn IDs;
- both reviewers start before either reviewer completes;
- both reviewers receive the producer handoff token;
- the aggregator receives both reviewer receipts;
- events are correlated by `(codex_thread_id, codex_turn_id)`;
- every persistent thread and turn is readable before restart;
- the aggregator thread and completed turn remain readable after restarting the
  App Server process.

The model's semantic PASS/FAIL decision is recorded but does not control the
transport verdict. The PoC verdict answers whether the collaboration mechanism
worked, not whether the synthetic proposal was correct.

## Commands

Unit tests:

```powershell
python -B -m unittest `
  experiments.codex_app_server_collaboration.test_app_server_client `
  experiments.codex_app_server_collaboration.test_collaboration_graph
```

Real acceptance probe:

```powershell
python -B -m experiments.codex_app_server_collaboration.run_acceptance
```

Evidence is written under:

```text
C:\code\aegis_artifacts\app_server_collaboration_poc\<graph-run-id>\
```

`RUN_STATE.json` is written before model execution and updated at stable
checkpoints. `ACCEPTANCE_REPORT.json` is the final result.

## Current result

The first Windows-local run passed all ten control-plane checks with
`codex-cli 0.145.0`, `gpt-5.6-sol`, and reasoning effort `high`.

Run ID:

```text
appserver-poc-20260806T025543Z-4d2e5cc0
```

Report SHA-256:

```text
CB2B2C927D3BA4A2515AD7F9A76FF52FCFD07B38EF96AB4F73E86B04CE8B2AA9
```

The two reviewer turns overlapped for 15.341 seconds. The App Server was then
terminated, restarted, and the aggregator thread was resumed with its completed
turn still readable.

## Proven and unproven boundaries

Proven for this pinned environment:

- different top-level threads execute concurrently;
- LangGraph fan-out/fan-in works;
- request responses and lifecycle events do not cross between turns;
- persistent thread history survives a clean App Server restart.

Not proven:

- recovery after a process crash during an active turn;
- a maximum safe global concurrency level;
- Desktop V2 child grouping or sidebar presentation;
- TraceRelay coverage for one long-lived App Server process;
- compatibility with another Codex CLI version.

Do not connect this experiment to A-F without a version pin, startup contract
test, per-thread single-flight guard, durable job ledger, and TraceRelay
lifecycle design.
