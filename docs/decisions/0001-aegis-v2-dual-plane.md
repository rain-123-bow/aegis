# ADR-0001: Use a dual-plane architecture for Aegis v2

## Status

Revised after independent Phase 0A review; pending independent rereview.
Operational feasibility remains contingent on a separately authorized,
fail-closed Phase 0B capability probe. This status is not Phase 0A PASS.

## Date

2026-07-27

## Context

Aegis must preserve deterministic gates, durable state, recovery, evidence
invalidation, and auditable verdicts while keeping the user's current Codex task
as the visible Master of long-lived A–F subagents.

The current repository does not establish that contract:

- the graph is invoked as a one-shot flow without a durable checkpointer;
- empty agent identities can reach execution;
- the transport uses `codex exec resume <child_thread_id>`, which is not a
  supported V2 child-agent transport;
- state relies on booleans, free dictionaries, fixed filenames, retry budgets,
  and numeric review thresholds;
- machine-local thread/session IDs and absolute paths are mixed with portable
  project configuration;
- file existence and agent claims can be mistaken for provenance.

One component must not simultaneously transport messages, judge their truth,
and claim the final result. The design must also tolerate interruption,
replacement, stale evidence, uncertain external side effects, and user
cancellation without manufacturing a pass.

## Decision

Adopt two authority planes:

```text
User
  ↕
Codex Master outside LangGraph
  - user interaction
  - authorized A–F lifecycle
  - exact action transport
  - raw receipt capture and read-only progress
  ↕
LangGraph durable kernel
  - typed state and checkpoint recovery
  - append-only events
  - identity, baseline, evidence, and transition gates
  - deterministic routing, cancellation, and verdict
  ↕
A plan author / B plan reviewer
C test executor / D evidence reviewer
E report author / F final reviewer
```

The Master is a transport and lifecycle adapter, not a quality judge. It cannot
rewrite actions or receipts, close blockers, change coverage, or set a verdict.
The kernel accepts only schema-valid, identity-bound, hash-bound,
authoritatively sourced records.

A/B, C/D, and E/F remain separate author/reviewer pairs. Adjacent roles cannot
share a child instance. A, C, and E cannot close their own blockers. D is not a
terminal node: every product failure, environment block, and pass candidate
must be reported by E and independently reviewed by F against the current fact
basis.

Each immutable source baseline receives a new, atomic six-role generation.
Replacements advance one role's `instance_revision`; they never impersonate the
lost identity. Retained, provisional, orphan, lost, and superseded identities
remain counted and traceable until authoritative closure.

Portable repository content is limited to source artifacts such as schemas,
role specifications, machine-independent policies, migrations, examples,
publishable Skill sources, and explicitly versioned reasoning-ledger data.
Live registries, authoritative thread/session IDs, optional sourced agent
handles, Master task IDs, absolute paths, checkpoints, events, receipts,
evidence indexes, and capability results stay in a machine-local runtime root.

Codex CLI `0.145.0` exposes no independent authoritative `agent_id`. Physical
identity is `thread_id + session_id`; an `agent_handle` is optional metadata and
is valid only with its observed source. Generated app-server bundle raw bytes
are not reproducible, so JCS semantic SHA-256 defines protocol compatibility.
Raw bundle path, size, and SHA-256 are retained only as acquisition evidence.

The execution contract excludes mutable registry state. It binds source
baseline, B-approved plan, execution-environment snapshot, and schema version.
Every action, claim, receipt, evidence record, and authority event binds its own
registry snapshot, `thread_id + session_id`, generation, and revision. A
replacement invalidates only affected unfinished work; evidence already
program-validated and accepted by D retains its original producer and registry
segment.

Cancellation and active-run scope change use one independent highest-priority
control path. Once accepted, it stops ordinary routing and converges every
dispatched action and external job to a terminal or a complete active-work
registration. Integrity or upstream defects remain cancellation facts and
cannot divert the run back into ordinary verdict routing.

Evaluation cases are immutable. Requirement-driven supersession is an
append-only event bound to the original case hash, user decision, and
independent review. Release membership is recomputed from the complete parent
chain's latest valid active set; a superseded contradictory expectation remains
auditable but is no longer an active gate.

Declared environment-contract changes create a new source baseline, run, and
generation. Observed execution-snapshot drift terminates the current run and
invalidates its C–F evidence. If the declaration is unchanged, a new run may
reuse the same verified generation and still-applicable approved plan while
capturing a new environment snapshot and execution contract.

Verdicts are produced by a pure function over a complete canonical
`VerdictInput.v1`. Agent self-report, self-score, confidence, majority vote,
file existence, time, cost, or a configurable numeric threshold cannot affect a
gate. E/F completion and current basis hashes are mandatory for product,
environment, and pass terminals.

Phase 0A also freezes the machine-independent evaluator policy. The dependency
set is `setuptools==83.0.0`,
`jsonschema[format-nongpl]==4.26.0`, `rfc8785==0.1.4`,
`langgraph==1.2.9`, and `langgraph-checkpoint-sqlite==3.1.0`; `psycopg`
remains legacy-only optional. The current Windows CPython 3.13 platform lock is
`pylock.windows-py313.toml`;
`SUPPORTED_PLATFORM_SET={windows-cpython313}`. Linux and other platforms fail
closed until a separate PEP 751 lock, runner-contract revision,
execution-environment certification, and new freeze exist. Such an extension
cannot rewrite existing evaluation cases, expected outputs, generators, or
other corpus bytes.

Every evaluation executes a content-addressed project wheel in a fresh
repository-external virtual environment. `PYTHONPATH`, editable installs,
user-site imports, PATH interpreter lookup, and shell invocation are forbidden;
the exact argv is absolute venv Python plus
`-I -X utf8 -m aegis.sut <ENTRYPOINT_ID>`. The SUT cwd is a repository-external
`ISOLATED_EXECUTION_ROOT`; its non-inherited environment contains exactly
`AEGIS_RUNNER_MODE=FROZEN_EVALUATION` and
`LANGGRAPH_STRICT_MSGPACK=true`. Per-run evidence binds the actual Python
path/hash/version/ABI, platform lock, project wheel, and installed
distributions. A repository `src/xxhash.py` import cannot satisfy the locked
transitive `xxhash==3.8.1` dependency.

A release-grade runner requires an authenticated isolation backend that proves
the external venv is read/execute, current fixtures are read-only, and the
invocation outbox is write-only/create-new. Repository, evaluation corpus,
expected/reference stores, other cases, and undeclared paths are unreadable,
and network access is denied. A Windows host without that proof yields
binding=`UNVERIFIED_ISOLATION` and
output=`BLOCKED_UNVERIFIED_ISOLATION`; the SUT is not spawned and release is
blocked, never best-effort PASS.

The SUT receives only
`subject/context_objects/fixture_refs/mutation/observed_state` and emits only a
`SutDecision.v1`. The outer evaluator owns case identity, expected data,
`RunnerExecutionRecord.v1`, and `EvaluationRunnerOutput.v1`; the latter embeds
the validated decision and execution record. Reference generators, oracles, and
comparators execute outside the SUT environment and cannot import or reuse the
SUT decision implementation. Their full sources and source manifest are
normative freeze inputs under `evaluation/aegis_v2/reference/`, with
`source_manifest.v1.json` as the source binding; hashes without retrievable
source preimages are insufficient. That manifest must validate against bundled
`ReferenceSourceManifest.v1`; harness self-validation is not an authority.

The five-field projection prevents interface leakage but cannot make a public
corpus unknowable to a same-OS-user implementation. That remains an explicit
risk, reduced through independent expected/reference authorship, unpublished
holdouts, full property-domain execution, and authenticated isolation.

The normative root also includes `.gitattributes`, `pyproject.toml`, the current
platform lock, all schemas/corpus/fixtures, and every reference
generator/oracle/comparator source. Each `FreezeInput` uses the exact closed
field set `logical_path/locator/artifact_kind/byte_domain/byte_size/raw_sha256/
semantic_jcs_sha256/leaf_sha256`. Size/raw hash always bind locator bytes; JSON
also binds its semantic JCS hash, and both enter the leaf. The code-absence proof
binds the exact direct `git ls-tree` argv, complete
base-tree/non-ignored-untracked inventory, and an independently sourced
disposition artifact for every outside-domain entry. Modified/untracked exact
bytes are retained as uncommitted, unstaged Git CAS blobs through
`git hash-object -w --no-filters <path>` and read back before review, or through
a separately acquired frozen snapshot.

The repository-canonical requirement, plan, and static-Codex-evidence inputs are
`docs/aegis_v2_requirements.md`, `docs/aegis_v2_upgrade_plan.md`, and
`docs/aegis_v2_codex_static_evidence.md`. Their temp origins are provenance,
not normative freeze locators.

The candidate native relay is capability-gated. The following are not fallback
transports:

- `codex exec resume`;
- direct external child-thread turns;
- ordinary top-level Codex tasks;
- untracked agents;
- old threads reprompted for a new baseline;
- the v1 one-shot graph/CLI path.

If Phase 0B cannot prove durable parent-owned identities, cross-turn recovery,
authoritative events, retention/capacity, provisional and replacement
atomicity, sidebar observability, and sibling isolation, Aegis v2 is not
implementable on that Codex version. Phase 1–5 stop.

## Authorization boundary

This ADR accepts an architecture, not live execution authority.

- The user must separately approve the Phase 0B probe.
- Probe orphan cleanup requires batch-specific preauthorization.
- Formal A–F creation requires a later explicit confirmation of the frozen
  product-test baseline.
- Closing retained long-lived instances requires explicit user confirmation.

## Alternatives considered

### Patch `codex exec resume`

Rejected. It assumes an external input path that V2 child agents do not support
as the required parent-owned collaboration transport. More retries or wrapper
code cannot repair the authority mismatch.

### Remove LangGraph and let Codex agents self-orchestrate

Rejected. This loses deterministic gates, durable checkpoint routing,
programmatic evidence invalidation, reproducible cancellation, and a machine
verdict. Transport, execution, and judgment would collapse into model behavior.

### Create A–F as ordinary top-level Codex tasks

Rejected. It loses parent ownership and the required `Subagents` visibility and
retention model. Easier external addressing does not satisfy the user's
observable long-lived child-agent contract.

### Let an external LangGraph process drive child threads directly

Rejected as an unverified assumption. No supported public parent collaboration
RPC and authoritative Desktop event path have been proven for the target
versions. An app-server adapter may be considered only after a live capability
probe proves those properties.

### Rely on prompts for role isolation

Rejected. A biased agent can ignore a prompt or use another tool channel. The
platform must prevent sibling collaboration and cross-role writes, or an event
source outside Master narrative control must detect every attempt and terminate
the run.

## Consequences

Benefits:

- user interaction and agent visibility remain in Codex;
- gates, provenance, recovery, cancellation, and verdicts become deterministic
  and replayable;
- failures are classified as product, environment, process, upstream,
  integrity, cancellation, or discussion outcomes instead of one boolean;
- old evidence and old identities cannot silently satisfy a new baseline;
- accepted pre-replacement evidence remains verifiable without forcing it to
  impersonate the replacement identity;
- immutable cases can evolve through auditable requirement supersession without
  making mutually contradictory historical expectations simultaneously active;
- user risk decisions remain visible without corrupting machine facts.

Costs:

- two coordinated planes require a transport protocol, checkpointer, event
  store, registry, leases, inbox/outbox, and lifecycle recovery;
- every new baseline consumes six retained child identities;
- provisional creation and replacement need explicit capacity accounting and
  crash testing;
- reports take E/F work even when D already found a product failure;
- the design may correctly conclude that the current Codex version is
  incapable of supporting Aegis v2.

Risks and mitigations:

- Master could omit or rewrite transport facts: bind actions/results to
  authoritative Codex events and child-written outboxes.
- External effects cannot be generally exactly once: use durable target job
  wrappers or fail into `UNKNOWN_SIDE_EFFECT` without replay.
- Retention may exceed platform capacity: certify `G`, `R`, and `P`, count every
  visible/occupied identity, and block before creation.
- Partial native provisioning may leave agents: persist provisional batches,
  dispatch nothing until all six validate, and require user-scoped cleanup
  authority.
- Capability claims may be optimistic: label them `UNVERIFIED` until Phase 0B
  records real IDs, events, paths, hashes, timestamps, return codes, restart,
  fault injection, and attack-test evidence.
- A checkout-local module or editable install could contaminate evaluator
  behavior: execute only the locked wheel in a fresh venv, reject `PYTHONPATH`,
  bind imported-module origins, and require real locked `xxhash`.
- A same-user SUT could read repository tests despite a clean stdin: require an
  authenticated filesystem/network isolation backend and block as
  `UNVERIFIED_ISOLATION` when it is unavailable.
- A lookup-table SUT could recognize corpus cases: withhold case IDs and all
  expected/runner metadata, accept only the five-field projection, and compare
  outside the SUT after freezing execution evidence; retain public-corpus
  preknowledge as a disclosed risk.
- A generator and SUT could share the same implementation defect: freeze their
  complete source preimages and enforce a no-import/no-reuse boundary before
  running the full property domain.
- A local actor could rewrite an entire self-consistent freeze bundle: bind the
  normative root, code-absence proof, and review artifact to the independent
  reviewer's externally verifiable append-only Codex final event. Local
  app-server/history and caller-provided verifiers/readers are observations,
  not authority. Until a candidate-external preauthorized provider adapter or
  self-contained external proof exists, production freeze finalization,
  verification, and frozen-record validation fail closed.

## Related contract

The normative operational rules are in
[`../aegis_v2_phase0_contract.md`](../aegis_v2_phase0_contract.md). If this ADR
and that contract conflict, the Phase 0A contract governs runtime conformance;
this ADR governs the architectural choice and rationale.
