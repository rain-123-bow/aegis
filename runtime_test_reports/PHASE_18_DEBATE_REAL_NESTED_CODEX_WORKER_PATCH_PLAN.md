# Phase 18 Debate Real Nested-Codex Worker Patch Plan

## Scope

This patch moves the Debate Department from demo-only in-process worker closure toward strict real nested-Codex Debate Worker acceptance.

It does not claim production nested-Codex lifecycle closure.

## Frozen Decisions

```text
Debate Department = Debate Leader + stance-bound Debate Workers
Debate Leader     = gpt-5.5 / high
Debate Worker     = gpt-5.5 / high
```

Forbidden in the current phase:

- medium Debate Worker profile;
- silent downgrade;
- fallback from real worker to in-process worker in acceptance;
- independent evidence collector agent;
- independent scope checker agent;
- independent researcher agent;
- persistent expert persona;
- Master-created Debate Workers.

## Key Semantics

1. Master sees only the Debate Leader.
2. Debate Leader creates one request-scoped real nested-Codex Debate Worker per valid stance.
3. Each Worker owns its whole stance work: information collection within allowed evidence boundaries, defense, attack, answer, scope narrowing, and causal concession.
4. Each Worker maintains worker-local causal state, route priority, and expand priority.
5. Worker causal state has higher authority for later turns than compressed transcript context.
6. Debate Leader maintains adjudicator causal state across the run.
7. Leader adjudication is causal-strength based, not voting.
8. Causal equipoise must be preserved and marked with `developer_decision_required: true`.
9. Final Debate output is a complete causal package for mailbucket delivery to Master.
10. Debate output remains `causal_candidate` unless Master later admits it into global causal truth.

## v0.2 Patch Application Hardening

v0.2 adds patch tooling safety beyond v0.1:

- `--repo-root` parameter;
- repository root validation;
- dirty git tree fail-fast unless `--allow-dirty` is passed;
- no overwrite of differing existing files unless `--force` is passed;
- `--dry-run` preview;
- corrected usage instructions for running the patch script from outside the repo root.

## Expected Runtime Artifacts

Strict real-worker preparation creates:

```text
.aegis-debate-real-worker/
  worker_creation_requests.json
  expected_worker_proofs.json
```

Real nested-Codex Worker creation must produce:

```text
.aegis-debate-real-worker/worker_proofs/
  <worker_id>_proof.json
```

The proof audit is strict. Missing proof means failure.

## Production Boundary

Not included:

- persistent nested-Codex process lifecycle;
- restart/recovery;
- production worker supervision;
- production key lifecycle;
- real CI / artifact backend integration;
- real global causal merge;
- push / PR / merge / release.

This patch claims only strict contract/profile/schema/tooling support for real nested-Codex Debate Worker acceptance.
