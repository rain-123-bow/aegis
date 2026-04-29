# Aegis Debate Runtime Demo

## Purpose

This package implements a demo-level executable runtime for the Debate Department contract.

It proves the core Debate Department mechanism:

```text
request admission
-> stance validation
-> one temporary worker per stance
-> leader-mediated round-robin broadcast
-> turn transcript
-> Leader adjudication
-> temporary worker/topology cleanup
-> persistent causal final report
```

## Non-goals

This package does not implement:

- production security hardening;
- remote trust;
- key lifecycle and rotation;
- certificate chain validation;
- real global Causal Store mutation;
- real Master-level causal merge;
- unrestricted full-mesh worker chat;
- persistent Debate Workers.

## Runtime boundary

The runtime is outside `aegis-master-kit` by design.

`aegis-master-kit` owns department contracts. This package executes a demo against those contracts.

This is demo runtime, not production runtime. It uses deterministic in-process
demo workers by default. Real nested-codex orchestration, production security,
remote trust, key lifecycle, and Master-level causal merge remain future work.

## Main invariant

```text
Debate Worker = temporary, one-run, stance-bound resource
Debate Result = persistent causal candidate for later governance
```

The runtime releases workers and internal topology after final report generation, while preserving the final causal report and transcript digest.

Router-integrated tests prove that a Master-created debate request can flow
through `aegis-router` into the Debate Leader, create a request-scoped internal
leader-mediated topology, return a causal candidate to Master, and clean up
temporary workers without mutating Archive, Knowledge, Causal, or global causal
stores.

Final output is `causal_candidate`, not global causal truth. Master-level causal
merge is outside this runtime.

## Running tests

```bash
cd aegis-runtime/debate
python -m pytest
```

## Running the demo

```bash
cd aegis-runtime/debate
python -m aegis_debate_runtime.cli --request examples/demo_request.json
```

The command prints a JSON final report.
