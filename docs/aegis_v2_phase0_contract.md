# Aegis v2 Phase 0A Normative Contract

Status: **Revised normative draft; independent rereview required; Phase 0A
pending freeze evidence**

Date: 2026-07-27

This document defines the falsifiable contract that all Aegis v2 schemas, tests,
runtime components, and releases MUST satisfy. `MUST`, `MUST NOT`, `SHOULD`, and
`MAY` are normative.

`PHASE0A_CONTRACT_REVIEW.md` currently records `FAIL`. This revision does not
convert that result into PASS. Phase 0A is not complete merely because this file
exists or because blockers were edited. Completion requires synchronized
schemas, corpus, fixtures, hashes, a new independent review with no open
blocker, and the externally anchored freeze record defined in Section 16.
Before accepting the first v2 implementation commit, the gate MUST prove that
commit is later than and based on the exact recorded freeze state.

## 1. Scope and authorization

Phase 0A freezes:

- the dual-plane authority boundary;
- A/B, C/D, and E/F role separation;
- identity, generation, retention, provisioning, and replacement semantics;
- baseline, evidence, event, dispatch, receipt, blocker, cancellation, and
  verdict semantics;
- `evaluation_manifest.v1` mutation rules and per-case release expectations;
- Phase 0B capability gates.

This document does **not** authorize:

- implementation of the v2 kernel or relay;
- a live Phase 0B Codex capability probe;
- creation, replacement, or closure of probe agents;
- creation of formal product-test A–F agents;
- execution of a formal product test.

A live Phase 0B probe may start only after Phase 0A passes and the user gives a
separate, explicit approval after the probe scope, retained-agent impact,
failure injections, Desktop restart, and cleanup choices are shown. Automatic
cleanup of provisional orphans requires a separate preauthorization limited to
the named provisioning batch. Without that cleanup preauthorization, Phase 0B
MUST NOT start the six create/validate-boundary failure-injection experiments.

A formal product run has another boundary. The Master MUST freeze and present
the source baseline, then receive an explicit user confirmation equivalent to
“start testing” before it creates formal A–F instances or dispatches a test
action. Phase 0B approval is not formal-test approval.

Until Phase 0A, Phase 0B, and Phases 1–5 all pass, v2 MAY run only dedicated
probes, fixtures, substitutes, and frozen corpus cases. It MUST NOT test a real
target project.

During an active run, user messages are read-only observations. A request that
changes scope, requirements, expected results, or acceptance facts MUST cancel
the current run through the same independent cancellation-convergence protocol
as an explicit user cancel. Only after that run has reached a cancellation
terminal may a new baseline and run be created. User risk
acceptance and release decisions are appended after the machine verdict; they
MUST NOT rewrite it.

`PASS` is not the quality objective. `FAIL_PRODUCT`, `BLOCKED_ENVIRONMENT`,
`NEEDS_MASTER_USER_DISCUSSION`, cancellation, and integrity failure are valid
high-quality outcomes when they are the deterministic result of current facts.

## 2. Dual-plane authority model

### 2.1 Codex Master: interaction and transport plane

The Codex user task is the Master and remains outside LangGraph. The Master MAY:

- conduct pre-test user interaction and adversarial requirement review;
- request authorized provisioning, replacement, retention, and closure actions;
- dispatch the kernel's exact action through parent-owned native collaboration
  tools;
- persist raw transport receipts and expose read-only progress;
- discuss the immutable result with the user after terminal evaluation.

The Master MUST NOT:

- produce or alter A–F findings, review results, blocker closure, coverage, or
  verdict fields;
- paraphrase an action or result as the machine-authoritative payload;
- use its own narrative, memory, or metadata as source identity proof;
- inject active-run user text into an agent payload;
- skip, reorder, or synthesize a kernel transition.

### 2.2 LangGraph durable kernel: control plane

The kernel is the sole authority for:

- typed state, phase, node, leases, attempts, and state sequence;
- durable dispatch actions and unique action consumption;
- schema, identity, path, hash, baseline, evidence, and transition validation;
- blocker effects and closure validation;
- deterministic routing, cancellation convergence, and terminal verdicts;
- append-only state-transition, action, receipt, gate, and human-decision
  events.

The kernel MUST use a durable checkpointer and event store. Chat history, a
human Markdown summary, a file's mere existence, or an agent's statement is not
kernel state.

### 2.3 Long-lived execution roles

| Pair | Author/executor | Independent reviewer | Required boundary |
|---|---|---|---|
| A/B | A writes the test plan, traceability, cases, and execution prerequisites. | B reviews coverage, executable proof, boundaries, and false-positive/false-negative risk. | A cannot approve its plan or close B's blocker. |
| C/D | C executes only the B-approved plan and records raw execution, findings, gaps, and external jobs. | D validates inputs, environment, commands, return codes, timestamps, raw output, coverage, and deductions. | C cannot change expected results or classify its omission as an environment gap. |
| E/F | E drafts a report only from the current D-accepted fact snapshot. | F checks report/evidence identity, omissions, evidence life, conclusion bounds, and unresolved facts. | E cannot approve its report; F cannot modify product code or acceptance facts. |

One child instance MUST NOT hold adjacent author/reviewer roles. A, C, and E
MUST NOT close blockers concerning their own output. B, D, and F are evaluated
for accurate fact expression, not for producing a pass.

A confirmed product finding MUST NOT route into product repair. C continues
other independent approved cases unless continued execution could damage data,
equipment, safety, or later evidence; such a stop must use B's approved
objective safety policy and preserve every unexecuted case and reason.

A–F MUST NOT communicate directly, create descendant agents, write another
role's outbox, or use shared files as an unapproved side channel. The platform
MUST either prevent these actions or an authoritative event source MUST detect
all such attempts and make the run `INTERNAL_INTEGRITY_ERROR`. Prompt-only
isolation is insufficient.

## 3. No fallback transport

`CodexNativeMasterRelay` is a candidate transport, not a currently verified
capability. Until Phase 0B passes, documentation and code MUST label it
`UNVERIFIED`.

The following are prohibited v2 fallbacks:

- `codex exec resume <child_thread_id>`;
- external `turn/start` or `turn/steer` against a V2 child;
- ordinary top-level Codex tasks in place of parent-owned A–F children;
- untracked or non-recoverable agent instances;
- a prompt instructing an old thread to ignore a previous baseline;
- the v1 one-shot CLI/graph path as a substitute for the durable relay.

Failure of a required Phase 0B capability stops Phase 1–5. It MUST NOT select
one of these fallbacks or silently weaken the contract.

An app-server relay MAY be added only after a live probe proves a supported
parent collaboration RPC, Desktop attachment, durable identity, and
authoritative event access. Failure of this optional path keeps it disabled; it
does not invalidate a separately proven native Master relay. The app-server
path is currently `UNVERIFIED`.

## 4. Identity and baseline model

### 4.1 Durable identifiers

The v2 domain MUST use typed, non-empty identifiers:

- `campaign_id`: one business objective across runs, UUIDv7;
- `run_id`: one execution against one immutable source baseline, UUIDv7;
- `source_baseline_id`: canonical pre-test source manifest hash;
- `registry_snapshot_id`: canonical A–F registry snapshot hash;
- `test_plan_revision_id`: canonical B-approved plan revision hash;
- `execution_environment_snapshot_id`: canonical actual execution environment
  hash;
- `execution_contract_id`: non-self-referential execution identity;
- `source_generation_id`: the six-role generation for a source baseline;
- `role_slot_id`: stable A–F role slot;
- `instance_revision`: monotonic replacement revision within a role slot;
- `provision_batch_id` and `replacement_batch_id`: durable lifecycle operation
  identities;
- `attempt_id`, `action_id`, and `event_id`: UUIDv7 attempt, dispatch, and event
  identities.

Every dispatch and receipt MUST bind the campaign, run, source baseline,
registry snapshot, plan revision when available, execution contract when
available, node, attempt, action, target role, target authoritative
`thread_id + session_id`, source generation, instance revision, protocol
version, payload path and hash, issuance UTC time, expiry UTC time, nonce, graph
transition, and state sequence.

### 4.2 Four non-self-referential identity layers

1. `source_baseline_id` hashes requirements, implementation plan, source,
   dependencies, Aegis/Codex/Skill versions, and machine-independent policy
   that exist before A/B work or agent registration.
2. `registry_snapshot_id` hashes the A–F slots, authoritative `thread_id` and
   `session_id`, optional sourced agent handle, parent task, generation,
   instance revisions, and capability status. It MAY reference the source
   baseline; the source baseline MUST NOT reference it.
3. `test_plan_revision_id` hashes the B-approved plan, traceability, stable case
   index, A/B attempts, and source baseline. A/B rework creates a new revision,
   not a new source baseline.
4. `execution_contract_id` is the canonical hash of
   `ExecutionContractManifest.v1{schema_version, source_baseline_id,
   test_plan_revision_id, execution_environment_snapshot_id}`. Registry state
   is deliberately excluded. None of those inputs may contain the resulting ID.

Registry identity is a per-work-unit segment. Every dispatch, claim, completion
receipt, ingest receipt, evidence record, and authoritative event MUST bind its
own `registry_snapshot_id`, authoritative `thread_id + session_id`, source
generation, role slot, and instance revision. A terminal fact set MAY contain
evidence from multiple verified registry segments. Replacement MUST NOT
relabel old evidence with a new snapshot or revision.

Canonical manifests MUST use UTF-8 JSON, sorted keys, no insignificant
whitespace, JCS canonicalization, and SHA-256. File evidence additionally uses
SHA-256 over original bytes. UTC is authoritative; local time is display-only.

`SchemaBundle.v1` uses one domain only. Each JSON schema is parsed with
duplicate object members rejected, serialized as RFC 8785 JCS, encoded as UTF-8
without BOM, and its entry `byte_size/sha256` are computed over those JCS bytes.
Entries are ordered by `path` in Unicode code-point order. `bundle_sha256` is
computed over the complete bundle JCS with only `bundle_sha256` omitted.
Worktree LF/CRLF bytes and Git blob bytes are not schema-entry preimages. The
repository `.gitattributes` MUST still keep schemas/evaluation/docs at LF and
fixtures at `-text` so checkout transformations cannot silently alter source or
exact-byte fixtures.

### 4.3 Frozen dependencies and executable isolation

The Phase 0A machine-independent dependency policy is:

- build backend `setuptools==83.0.0`;
- `jsonschema[format-nongpl]==4.26.0`;
- `rfc8785==0.1.4`;
- `langgraph==1.2.9`;
- `langgraph-checkpoint-sqlite==3.1.0`.

`psycopg` is legacy-only optional input and MUST NOT enter the v2 core execution
environment. `pyproject.toml` and the current Windows CPython 3.13 lock
`pylock.windows-py313.toml` are normative freeze inputs.
`SUPPORTED_PLATFORM_SET={windows-cpython313}` for this v1 freeze. Linux and
every other platform are unsupported and fail closed until an independent PEP
751 platform lock, runner-contract revision, execution-environment
certification, and new Phase 0A freeze are created. That platform extension MUST
NOT rewrite existing evaluation cases, expected outputs, generator definitions,
or other corpus bytes.

`EvaluationRunnerContract.v1` contains only a machine-independent executable
policy. An evaluation execution MUST create a fresh isolated virtual
environment outside the repository, install the content-addressed project wheel
and all locked wheels with hash verification, and invoke the resolved virtual
environment interpreter directly. The working directory is a repository-external
`ISOLATED_EXECUTION_ROOT`. The exact argv is
`[<absolute-venv-python>,"-I","-X","utf8","-m","aegis.sut",
"<ENTRYPOINT_ID>"]`. Editable installs, `PYTHONPATH`, user-site packages,
repository-source imports, PATH interpreter lookup, and shell interpolation are
forbidden. The SUT environment is a non-inherited exact map containing only
`AEGIS_RUNNER_MODE=FROZEN_EVALUATION` and
`LANGGRAPH_STRICT_MSGPACK=true`.

A release-grade run additionally requires an authenticated isolation backend
whose authority is outside the SUT. It MUST prove that the SUT can read only the
external virtual environment with read/execute access and the current case's
verified fixtures read-only. Its invocation outbox is write-only/create-new;
the SUT cannot read it. Repository root, `evaluation/`, expected store,
reference generator/oracle/comparator source, other cases, and all undeclared
paths are unreadable. Network access is denied. On a Windows host without such
a proved backend, the isolation binding is `UNVERIFIED_ISOLATION`; the outer
output is `BLOCKED_UNVERIFIED_ISOLATION`, contains no SUT decision or process
record, and the SUT is not spawned. The release gate remains blocked.
Best-effort ACLs, prompts, five-field projection, or process claims cannot
upgrade that result to PASS.

Before materialization, every catalog fixture referenced by an ordinary or
runner-conformance case MUST resolve through that case's exact runner contract.
Each declared `logical_runtime_path` MUST be a canonical absolute Windows path
strictly below that runner's `fixture_mount.logical_runtime_root`. Dot
segments, alternate data streams, trailing-space/dot aliases, another drive,
UNC escape, and root equality are rejected before any directory or file is
created. A negative SUT case cannot justify an outer-runner path escape.

Each execution retains the actual interpreter path, resolved real path, exact
file size/hash, CPython version and ABI tag, platform lock bytes/hash, project
wheel bytes/hash, and complete installed-distribution snapshot. Before every SUT
invocation, the runner revalidates those facts. It MUST prove that the imported
transitive `xxhash==3.8.1` distribution and module originate from the locked
virtual environment; an import resolving to repository `src/xxhash.py` or any
other checkout path fails closed.

The Codex app-server protocol compatibility acquisition is exactly:

```text
codex app-server generate-json-schema --experimental --out <new-empty-directory>
```

The executable MUST be the recorded Codex version and its SHA-256, argv, cwd,
feature configuration, return code, and UTC interval MUST be retained. The
output directory MUST be empty before invocation. The compatibility preimage is
the single JSON value parsed from
`codex_app_server_protocol.v2.schemas.json`; legacy aggregates and any
directory-wide `{path,json}` wrapper are excluded. The compatibility key is
SHA-256 over that value's RFC 8785 JCS UTF-8 bytes. The selected file's absolute
path, byte size, and raw SHA-256 remain acquisition evidence only.

The source manifest MUST include repository identity and absolute path, commit,
clean/dirty state, staged and unstaged diff-byte hashes, every non-ignored
untracked file path/size/hash, requirement and plan hashes, tool/model/Skill
identity, model reasoning effort, dependency locks, and declared
local/remote/hardware contracts. Excluded non-material fields require
schema-defined names and reasons.

The staged and unstaged preimages are the raw stdout bytes from these exact
argument vectors, respectively:

```text
git --no-pager -c color.ui=false -c core.autocrlf=false -c core.safecrlf=false -c core.quotepath=true -c diff.external= -c diff.renames=false -c diff.algorithm=myers diff --cached --no-ext-diff --no-textconv --binary --full-index --abbrev=40 --src-prefix=a/ --dst-prefix=b/ --
git --no-pager -c color.ui=false -c core.autocrlf=false -c core.safecrlf=false -c core.quotepath=true -c diff.external= -c diff.renames=false -c diff.algorithm=myers diff --no-ext-diff --no-textconv --binary --full-index --abbrev=40 --src-prefix=a/ --dst-prefix=b/ --
```

The collector MUST capture stdout as bytes without shell text redirection or
newline conversion, retain stderr separately, require exit code zero, and bind
the Git executable hash/version, complete argv, canonical cwd, current commit,
and `.gitattributes` raw bytes/size/SHA-256.

`registry_state_sha256` MUST be SHA-256 over the RFC 8785 JCS UTF-8 bytes of
`RegistryStatePreimage.v1` exported in one read transaction. That preimage MUST
contain schema/version, source baseline, parent task thread/session, capacity
contract, role pointers sorted by role, every physical instance sorted by its
identity (including retained/provisional/orphan/lost/superseded/replacement
states), all lifecycle batches, capability states, and
`registry_event_head_seq + registry_event_head_hash`. It MUST omit
`registry_state_sha256`, `registry_snapshot_id`, export time, and database
locator. Acquisition metadata remains outside the hash. The gate MUST re-export
at the same event head and compare exact JCS bytes.

Source, dependency, Skill, policy, configuration, or **declared execution
environment contract** change terminates the run as `SOURCE_BASELINE_DRIFT` and
requires a new source baseline, run, and six-role generation. Registry drift
invalidates only unfinished work for the changed role/revision. Approved-plan
drift returns to A/B and invalidates dependent C–F evidence.

An **observed execution-environment snapshot drift** is different: it terminates
the current run as `EXECUTION_ENVIRONMENT_DRIFT`, invalidates that run's old
execution contract and all C–F evidence, and forbids in-place continuation. If
the declared environment contract is unchanged, a new run keeps the same
source baseline and MAY reuse the still-verified generation; it MAY reuse the
B-approved plan only if its execution prerequisites still hold. The new run
MUST capture a new environment snapshot and execution contract. If the
declaration must change, the source-baseline rule above applies.

The kernel MUST recompute the applicable mutable inputs before every dispatch,
receipt ingest, gate, and final commit. A mismatch takes the drift path for that
identity layer before another transition can occur.

## 5. Generations, retention, and capacity

A source generation is an atomic six-role A–F group. A new source baseline MUST
use six new physical threads. Old generations remain observable history and
MUST NOT receive actions for the new baseline. Reusing an old thread with a new
prompt is prohibited.

Before the first formal run, the user chooses:

- `max_retained_source_generations = G`;
- `replacement_reserve = R`;
- `physical_instance_budget = P`, where `P >= 6 * G + R`.

The base certification contract is `G=2`, `R=6`, and `P>=18`. A larger contract
requires the same live capacity, restart, retention, and sidebar-location proof
as Phase 0B.

Capacity includes active, retained, provisional, orphan, lost-but-visible,
superseded-but-visible, and replacement instances. An instance leaves the count
only after an authoritative close receipt and platform confirmation that it no
longer occupies capacity.

Before generation creation, preflight MUST prove six free slots and the `G`
limit. Before replacement, it MUST prove one free slot and remaining `R`.
Failure occurs before creation as `CAPACITY_BLOCKED_BY_RETENTION` or
`CAPACITY_BLOCKED_REPLACEMENT`.

Aegis MUST NOT automatically close or hide retained instances. If capacity is
insufficient, the user may explicitly close a listed complete old generation
or stop the new run. Refusal to close preserves history and keeps the new run
blocked.

Except for a batch-specific orphan cleanup preauthorization, closing any
long-lived retained, lost, superseded, replacement, or other A–F instance
requires explicit user confirmation that identifies the target.

## 6. Provisional provisioning and replacement

Native creation of six agents is not atomic. The kernel MUST model it as a
provisional batch:

1. Persist the batch ID, expected six slots, and `PROVISIONING` before creation.
2. After each creation, persist its real identity, parent, role, generation,
   time, and creation event as `PROVISIONAL`.
3. Provisional instances receive no test action.
4. After all six identities, parent links, visibility, and capabilities pass,
   atomically commit the batch as `ACTIVE_GENERATION`.
5. On any failure, mark the batch `ABORTED` and created instances
   `PROVISIONAL_ORPHAN`; preserve the prior generation and dispatch zero
   actions.
6. Orphans count against capacity. A retry uses a new batch ID and MUST NOT
   assemble a generation from old orphans.
7. Close batch orphans automatically only when the user preauthorized cleanup
   for that exact batch; persist every close receipt.

The authoritative physical identity is:

```text
(source_generation_id, role_slot_id, instance_revision, thread_id, session_id)
```

Codex CLI `0.145.0` provides no independent authoritative `agent_id`.
`agent_handle` is optional display/routing metadata. A non-null handle MUST
carry its observed source and MUST NOT replace or independently prove the
`thread_id + session_id` identity.

On loss, the kernel pauses dispatch, records the old instance `LOST_VISIBLE`,
checks reserve capacity, persists a replacement batch, and creates a
`PROVISIONAL_REPLACEMENT`. Only after identity, parent, role, visibility, and
capability validation may one transaction advance the role pointer to
`instance_revision + 1`, mark the new instance `ACTIVE`, and mark the old one
`SUPERSEDED_LOST`.

There MUST never be two dispatchable identities for a role revision transition.
Late old-revision receipts are audit events only. Evidence fully committed,
program-validated, and accepted by D before replacement keeps its original
registry snapshot, revision, `thread_id + session_id`, and producer; terminal
evaluation validates that historical segment instead of requiring the current
registry snapshot. Only an attempt for the replaced role that lacks a complete
D-accepted record is invalidated and restarted under the new revision. Other
roles and completed accepted attempts remain valid. Possible C-side effects
MUST be queried or classified `UNKNOWN_SIDE_EFFECT` before any retry.

Failed replacement validation creates an orphan without pretending the old
role is healthy. Exhausted capacity or an unrecoverable role routes to
`NEEDS_MASTER_USER_DISCUSSION`.

## 7. Dispatch, receipts, and authoritative events

Large payloads MUST travel by a contained local absolute path plus SHA-256.
Commands and collaboration messages carry only a short envelope. A target
agent MUST atomically claim a unique `action_id` before work:

- first valid claim: `CLAIMED`;
- already complete: return the existing result identity without re-execution;
- already running: `IN_PROGRESS`, with no second execution;
- wrong agent, role, generation, revision, baseline, or hash: `REJECTED`.

The child writes its result atomically to its own run/role/attempt outbox. The
Master MUST NOT transcribe result content. The kernel ingests the outbox only
after binding it to authoritative Codex events and then consumes the action
once.

Master-provided narrative and self-reported sender metadata are untrusted.
Phase 0B MUST prove at least one source the Master cannot rewrite that exposes
all of:

- sender and receiver authoritative thread/session identity;
- actual dispatched prompt;
- turn and tool-call identity;
- agent generation/revision and lifecycle state;
- either the result identity from the authoritative child turn, or a binding
  from the child-written outbox to that authoritative turn.

The kernel MUST cross-check action ID, payload hash, target generation/revision,
unique claim, and result hash. Forged, truncated, omitted, reordered, stale,
wrong-role, wrong-generation, or rewritten events MUST fail closed.

The initial protocol makes no cryptographic-signature claim against another
process under the same OS user. Nonces, hashes, append-only events, unique
consumption, and authoritative event binding provide replay and provenance
checks. “Signed” may be used only after an independently protected key service
exists.

## 8. Durability, recovery, and side effects

The kernel MUST persist state in this order:

1. acquire a run lease and persist one action;
2. dispatch;
3. persist raw dispatch/claim/result events;
4. validate and consume the receipt idempotently;
5. commit checkpoint and gate event;
6. issue the next action.

Recovery uses `run_id`, `state_seq`, `action_id`, lease owner/expiry, checkpoint,
and events. It MUST NOT depend on Master chat memory. A resend uses the same
action ID and cannot execute twice.

Every recovery experiment MUST emit `RecoveryRecord.v1` containing the run and
state sequence, lease, checkpoint/action/claim/dispatch/result/receipt/event
identities, crash boundary, effect class, durable-journal or target-query
evidence, pre/post state hashes, recovery decision, and terminal trace hash.
The runner MUST first execute an uninterrupted reference with the same fixture,
seed, and action identities, then inject one crash. The oracle compares a
schema-defined observable trace: ordered transition/action/receipt/event kinds,
unique-consumption counts, terminal state, result hashes, and observable effect
counts. Only schema-listed nondeterministic fields such as UTC and lease owner
may be normalized. Boolean summaries and aggregate counts without raw trace
preimages are insufficient.

C MUST classify every approved action:

- `PURE_READ`: retryable with the same action;
- `IDEMPOTENT_QUERYABLE`: target receives `operation_id=action_id` and supports
  result lookup;
- `NON_IDEMPOTENT`: target durable wrapper claims the operation before one
  execution; duplicates query only;
- `NON_IDEMPOTENT_UNJOURNALED`: no automatic execution. A user may approve one
  pre-test window, but uncertainty becomes `UNKNOWN_SIDE_EFFECT`.

The contract does not claim general exactly-once external effects. A durable
wrapper provides at-most-once effects plus queryable results. Without one, an
uncertain window MUST never auto-replay.

Side-effect must-detect cases MUST actually issue a duplicate or replay request.
An `IDEMPOTENT_QUERYABLE` action must return the target's existing query result;
a journaled `NON_IDEMPOTENT` action must return the durable wrapper's existing
record; an uncertain unjournaled action must reject replay as
`UNKNOWN_SIDE_EFFECT`. The oracle reads raw journal/query/effect-counter
fixtures. `automatic_replay_requested=false` or an agent's claimed replay count
cannot prove this invariant.

State/evidence inconsistency is `INTERNAL_INTEGRITY_ERROR`. Agent timeout is a
waiting condition, not product failure. A fixed retry count MUST NOT force
pass, failure, or closure. Repeated identical or wording-only attempts may set
`stagnation_state=CONFIRMED` and escalate without weakening a blocker.

## 9. Evidence and storage boundary

The portable repository contains only product source artifacts: versioned
schemas, role specifications, machine-independent default policies, migrations,
examples, publishable Skill sources, and explicitly versioned reasoning-ledger
instance data. It MUST NOT contain a live Master/agent registry, current
thread/session IDs, optional observed handles, a Master task ID, absolute user
paths, checkpoints, leases, receipts, capability results, or machine-local
evidence.

The local runtime contains those machine-specific records under a run-isolated
root:

```text
<runtime_root>/campaigns/<campaign_id>/runs/<run_id>/
  baseline/
  inbox/
  outbox/
  artifacts/
  evidence/
  reports/
  events/
```

Local `artifact_path` values MUST be absolute Windows paths inside the current
run root. Resolution MUST reject `..`, symlink, junction, reparse-point, UNC,
drive-case, or other containment bypasses. Writers use a temporary file and an
atomic rename. A manifest identifies a specific attempt artifact; a fixed
legacy filename is never “the latest” authority.

Remote evidence may remain remote, but the local evidence index MUST record:

- stable host identity and absolute locator/object ID;
- exact command or API call and return code;
- start/end UTC timestamps;
- environment fingerprint;
- content hash or verifiable digest;
- producer role/physical identity, run, and attempt;
- retention period and reacquisition method.

Inaccessible remote evidence without sufficient retained raw material becomes
invalid evidence. Text that looks successful cannot override a non-zero return
code. Existing path cannot override changed bytes.

Evidence whose declared baseline, execution contract, producer, role,
generation, revision, attempt, or registry segment does not match its own
program-validated action chain is rejected. Terminal evaluation MAY retain a
D-accepted historical segment after replacement; it MUST validate the segment's
original binding and MUST NOT rewrite it to the current registry. Cross-run
reuse is considered only before a new run: A provides a versioned
dependency/impact proof, B independently approves it, and the kernel applies
conservative propagation. Shared code, state, build, interface, or declared
environment-contract changes invalidate all dependent evidence by default.
Observed snapshot drift invalidates all C–F evidence in that terminated run.

Global quality law is injected once and cannot be weakened by a role Skill.
Each role receives one role contract and only the context needed for its current
action. Skill versions and hashes enter the source baseline. Skill self-checks
are untrusted risk lists for independent review, never gate evidence.

Reasoning Ledger inputs use only `active`, `stale`, `invalid`, and
`superseded`. The current project audit found no configured ledger context
pack, so Phase 0A records `NOT_CONFIGURED` with an empty item set and makes no
ledger-consistency claim. Any later external context pack MUST record its
query, project ID, these four states, generation time, source version, and
content hash; that hash enters a new source baseline.

V1 artifacts are read-only `legacy_untrusted`. They cannot establish a v2 pass.
V1 and v2 MUST NOT dual-write.

## 10. Facts and blocker closure

Facts are disjoint:

- `PRODUCT_FINDING`: observed product behavior violates an approved
  requirement; the test graph does not fix or close it.
- `PROCESS_BLOCKER`: an A–F artifact or step is inadequate; route to its owner.
- `ENVIRONMENT_GAP`: valid evidence cannot be obtained or reproduced; only new
  D-accepted evidence resolves it.
- `UPSTREAM_DEFECT`: requirement, implementation plan, Master precondition, or
  baseline is defective; stop automatic work for user discussion.
- `REPORT_DEFECT`: report and reviewed facts differ; E reworks and F reviews.

A blocker MUST contain a stable ID, origin and owner roles, severity, claim,
violated requirement, evidence references, required closure evidence,
prohibited substitutes, affected artifacts/cases, source/plan/execution
identities, opening attempt/event, status, and kernel-derived gate effect.

Closure is append-only. It requires owner correction evidence, an independent
reviewer decision, and a program gate that verifies reviewer identity, current
baseline, hashes, and dependency propagation. The original blocker is not
overwritten. An author cannot lower severity or self-close. Disagreement
preserves the reviewer fact and escalates.

The kernel derives `gate_effect` without reviewer discretion:

- a case-process blocker affecting only optional cases is `DIAGNOSTIC`;
- a case-process blocker affecting a missing required case is `BLOCKING`;
- a plan, evidence, or report blocker outside case coverage is `BLOCKING`.

A missing or extra blocker record, missing owner, affected-case mismatch, or
incorrect `gate_effect` makes the normalized input invalid.

## 11. Mandatory E/F completion

D acceptance is not terminal. A confirmed product finding, environment block,
or apparent pass MUST all proceed through:

1. a kernel-frozen `d_review_snapshot_id`;
2. E's complete report candidate bound to that snapshot;
3. a `report_candidate_id` and basis hash generated by the kernel;
4. F review bound to the current report and complete normalized fact set;
5. `TERMINAL_EVALUATION` only after F approval.

The five referenced artifacts are content-addressed versioned preimages, not
opaque identifiers:

- `DReviewSnapshot.v1`: D's authoritative thread/session identity, run,
  attempt/state sequence, execution contract, complete sorted accepted
  evidence/finding/gap/job/blocker/coverage sets, and each evidence record's
  original registry segment and producer;
- `ReportCandidate.v1`: E identity, run/attempt, D snapshot, exact report
  locator/bytes/hash, and the complete normalized fact IDs stated by E;
- `ReportCandidateBasis.v1`: kernel-recomputed expected and actual fact sets, their
  differences, report hash, D snapshot, and basis event;
- `FinalReview.v1`: F identity, run/attempt, current E candidate/basis, decision,
  report-defect IDs, and exact review artifact;
- `FinalReviewBasis.v1`: kernel-recomputed D/E/F bindings, complete fact set,
  execution contract, state sequence, and final-review event.

Each artifact ID MUST equal SHA-256 over its complete RFC 8785 JCS UTF-8 bytes.
The gate MUST load the preimage from a content-addressed store, validate its
production schema, recompute the ID, and verify role, `thread_id + session_id`,
run, attempt, state sequence, execution contract, and every predecessor
binding. Missing objects and syntactically valid all-zero IDs fail closed.

Fact changes invalidate the report candidate and return to E. Evidence defects
return through D; plan defects return through A/B; upstream defects stop for
discussion. Missing, rejected, stale, or mismatched F review makes
`PASS`, `FAIL_PRODUCT`, and `BLOCKED_ENVIRONMENT` illegal.

## 12. Deterministic state and verdict

`VerdictInput.v1` MUST be a complete, canonical byte value. It contains:

- execution/plan identities and phase/node;
- D snapshot, E candidate/basis, F review/basis/completion identities;
- the B-approved objective safety-stop policy and its hash;
- approved, required, optional, D-accepted, missing, environment-blocked,
  process-blocked, safety-stopped, cancelled, and unclassified case sets;
- workflow integrity, evidence, coverage, report, cancellation, and stagnation
  states;
- active external jobs and unknown side effects;
- open process blockers and upstream defects;
- proposed/confirmed/rejected product findings and open/resolved environment
  gaps.

The kernel is the sole producer of phase/node, integrity, required/optional
partitions, missing-case classifications, coverage, blocker gate effects, and
cancellation state.

Set arrays MUST be duplicate-free and sorted by their canonical string value.
Structured record arrays MUST be sorted by stable record ID. JCS alone does not
canonicalize array order.

Before verdict calculation, the kernel MUST prove:

- phase/node is one of A/B, C/D, E/F, cancel coordinator, or terminal;
- required and optional cases are disjoint and exactly partition approved
  cases;
- missing required cases equal required minus D-accepted required;
- environment, process, safety, and cancelled classifications are disjoint and
  exactly cover missing required cases;
- every classification has its required gap/blocker/job record and owner;
- confirmed findings reference D-accepted case evidence;
- resolved gaps reference later D-accepted evidence;
- evidence, report, and final-review hashes bind the current execution contract
  and complete fact set;
- terminal evaluation has a current, approved F basis.

Any failed invariant sets integrity to `INVALID`. The verdict function accepts
only this canonical input, performs no external lookup, and returns either
`ROUTE(target_node, reason_ids)` or `TERMINAL(verdict)`.

A cancel or scope-change control has a separate minimal-schema ingress. Once
the kernel durably accepts it, the same transaction stops new dispatch and
enters `CANCEL_CONTROL` before ordinary verdict construction. Integrity defects,
upstream defects, and unknown side effects discovered afterward remain facts to
register during convergence; they MUST NOT resume or preempt ordinary routing.

Fixed priority within canonical verdict input is:

| Priority condition | Decision |
|---|---|
| Cancellation is requested or quiescing | Route `KERNEL_CANCEL_COORDINATOR` |
| Cancellation terminated with registered active work | `CANCELLED_WITH_ACTIVE_EXTERNAL_WORK` |
| Cancellation is quiescent | `CANCELLED_BY_USER` |
| Integrity is `INVALID` or `UNKNOWN` | `INTERNAL_INTEGRITY_ERROR` |
| Unknown side effects or verified upstream defects exist | `NEEDS_MASTER_USER_DISCUSSION` |
| A blocking process blocker exists and stagnation is confirmed | `NEEDS_MASTER_USER_DISCUSSION` |
| A blocking process blocker exists | Route its earliest-stage owner; tie-break by opening event |
| Evidence is invalid/stale, or a missing case is unclassified | `INTERNAL_INTEGRITY_ERROR` |
| Workflow is in A, B, C, D, E, or F | Route that node |
| Terminal phase lacks current E/F approval and basis | `INTERNAL_INTEGRITY_ERROR` |
| Current F-approved terminal facts contain a required open environment gap that accounts for the non-process missing coverage | `BLOCKED_ENVIRONMENT` |
| Current F-approved terminal facts contain a confirmed finding and coverage is complete or policy-limited by an approved safety stop | `FAIL_PRODUCT` |
| Current F-approved terminal facts have no confirmed finding, complete valid evidence and required coverage, and no open required gap | `PASS` |
| Any other valid combination | `NEEDS_MASTER_USER_DISCUSSION` |

Identical canonical input bytes MUST produce identical decision bytes. The
decision function requires exhaustive property tests over state and fact-set
combinations; it has no unspecified default pass.

Agent self-score, confidence, satisfaction, “done”, majority vote, output-file
existence, retry count, token use, elapsed time, or a configurable numeric score
MUST NOT affect routing or verdict. V2 schemas MUST NOT define a numeric pass
threshold. Legacy score fields MAY produce migration diagnostics only and are
never verdict inputs.

## 13. Cancellation convergence

A user cancel request or active-run scope/requirement/expectation change sets
`cancel_state=REQUESTED`, immediately stops ordinary verdicts and new actions,
invalidates unsent actions, and sends cancellation control for dispatched
actions using their existing identities.

The kernel then enters `QUIESCING`. C must have recorded stable IDs for local
processes, remote jobs, device operations, and non-interruptible work. The
kernel enumerates every dispatched action from the event store and queries each
action and job. Late receipts are appended but cannot resume normal routing.

Only these cancellation terminals are legal:

- `CANCELLED_BY_USER`: every dispatched action has a terminal receipt, every
  external job is terminal, and no active registration remains;
- `CANCELLED_WITH_ACTIVE_EXTERNAL_WORK`: new dispatch is stopped and every
  non-terminal or unverifiable dispatched action and external job has one
  registration containing stable identity, authority/host/device locator, last
  state, possible side effects, owner, and follow-up method.

A missing or extra action/job registration makes the cancellation input
invalid but does not restore ordinary routing; the cancel coordinator continues
until the inventory closes. Integrity defects, upstream defects, and unknown
side effects are recorded in that inventory/report. Only after a scope-change
cancellation terminal may a replacement baseline/run be created.

Cancellation MUST NOT be rewritten as pass, product failure, or environment
block. Tests MUST cover cancellation before execution, during execution, before
receipt commit, and during non-interruptible work.

## 14. `evaluation_manifest.v1`

### 14.1 Immutable history and parent hash

Every case has a permanent stable ID, immutable input, expected route/verdict,
defect class, severity, denominator membership, and `case_sha256`. Its original
bytes and these fields MUST NOT be edited or deleted. Case status is not updated
in place.

`manifest_sha256` is SHA-256 over the complete manifest's RFC 8785 JCS UTF-8
bytes with only `manifest_sha256` omitted. A non-root
`parent_manifest_hash` MUST equal the parent artifact's declared
`manifest_sha256`, not the parent's raw-file hash or full JCS hash including its
self-hash. The parent MUST be retrievable from
`manifests/sha256/<parent_manifest_hash>.json` or an equivalent
content-addressed locator anchored by the freeze record.

The cross-version gate walks the complete chain from its root, rejects missing
parents, cycles, unresolved forks, duplicate `case_id`, changed old case bytes
or hashes, and events targeting absent cases. New cases and events are
append-only. The root contains the initial cases; each child manifest is a
delta containing only newly introduced cases and events. A child references an
old case by ID/hash and MUST NOT copy or reserialize it. Thus each `case_id` is
introduced exactly once across the chain.

Supersession is a separate `CaseSupersessionEvent.v1`. It MUST bind the target
`case_id + case_sha256`, the explicit user requirement-change decision and its
hash, an independent review artifact/event, replacement case IDs, rationale,
parent manifest hash, and event self-hash. Only a demonstrated conflict with a
new user requirement may supersede a case. Replaying all valid events over the
complete parent chain computes the chain head's latest valid `ACTIVE` set.
Release evaluation runs the must-detect members of that set. A legitimately
superseded conflicting expectation remains retained and auditable but is not an
active release gate.

### 14.2 Runner, SUT, output, and comparator

`EvaluationRunnerContract.v1` MUST map each `input_schema_id` to an exact
production schema `$id + JSON Pointer`, `sut_entrypoint_id`, direct process argv,
exact SUT-decision and outer-output schemas, fixture mount, comparator
ID/version, and oracle type. Unknown IDs fail closed.

`EvaluationRunnerInput.v1` is an outer evaluator envelope. The SUT receives a
new JCS object containing exactly these five members:
`subject`, `context_objects`, `fixture_refs`, `mutation`, and `observed_state`.
It receives no runner contract ID, input-binding ID, case ID, expected value,
manifest path, runner metadata, or comparator/oracle configuration. Its
authenticated filesystem view and import graph MUST enforce the isolation
boundary above. Any SUT output that depends on, echoes, or requires an unknown
case ID is a lookup-table leak and fails closed.
`oracle.reference_trace_fixture_id` is outer-evaluator-only. It MUST NOT appear
in the same case's `input.fixture_refs` or any SUT-visible mount; the gate
rejects any intersection before process creation.

SUT stdout contains exactly one schema-valid `SutDecision.v1` JCS value and no
framing. Its closed fields are `schema_version`, `outcome`, `decision`,
`reason_ids`, `assertion_ids`, and `sut_decision_sha256`. After the SUT exits,
the outer evaluator freezes runner/case/input identities, runner-input and
SUT-stdin hashes, exact argv/cwd/environment, process identity/times/return
code, exact stdout/stderr bytes, Python binding, and per-invocation runtime
revalidation, plus the isolation binding and invocation-time isolation
revalidation, as `RunnerExecutionRecord.v1`. It then embeds the validated
decision and that record in `EvaluationRunnerOutput.v1`; only after this
evidence is immutable may a separately isolated comparator load expected data.

Reference generators, reference oracles, and comparators execute outside the
SUT environment and MUST NOT import, invoke, copy, or share the SUT decision
function or its implementation modules. Their complete executable source,
dependency/import policy, and source manifest are content-addressed freeze
inputs under `evaluation/aegis_v2/reference/`: `generator.py`, `verdict.py`,
`closure.py`, `comparator.py`, `canonical.py`, `manifest.py`,
`schema_validation.py`, `cli.py`, `coverage.py`, `materialization.py`,
`materialize_closure.py`, `materialize_verdict.py`,
`closure_materialization_data.py`, `verdict_facts.py`, `__init__.py`,
`__main__.py`, `README.md`, `tests/test_reference.py`, and
`tests/test_audit_remediation.py`, plus `source_manifest.v1.json`. Hash-only
declarations without retrievable source preimages are invalid. The exhaustive
property domain MUST run in full; sampling, early-pass exit, and coverage
reduction are forbidden.

The AST/import-policy gate is only a frozen-source change-review gate; Python
source inspection is not a runtime sandbox. Release-grade reference execution
therefore requires a separately authenticated evaluator isolation backend that
denies network and shell/process creation, excludes production packages and
repository paths, and exposes only the exact frozen source plus role-declared
input/output channels. Without that proof, reference execution cannot produce
release PASS evidence.

`source_manifest.v1.json` MUST validate against the bundled and frozen
`schemas/aegis/v2/reference_source_manifest.v1.schema.json`
(`ReferenceSourceManifest.v1`). Harness self-validation without that independent
closed schema is insufficient.

The five-field projection prevents direct interface leakage; it does not stop a
same-OS-user process from reading a public corpus. Pre-publication corpus
visibility is therefore a retained risk, not a solved security property. The
contract reduces it with independently authored expectations/reference code,
unpublished holdout cases where available, complete property-domain execution,
and the authenticated isolation backend. None of those controls permits a
claim that a public corpus was unknowable to the model or implementation.

For pure outputs the evaluator validates `SutDecision.v1` and any embedded
production decision schema. The comparator compares observed
`sut_decision_sha256` with the frozen expected `SutDecision.v1` self-hash,
including exact decision IDs and reason/assertion ordering. For stateful, event,
recovery, and side-effect cases it compares the versioned raw trace/oracle
defined by the case. A final label, self-reported boolean, or aggregate count is
not an oracle. Non-zero return, extra framing, missing fixture, invalid output,
unregistered comparator, hash mismatch, or unverified isolation fails closed.

### 14.3 Raw fixture contract

Ordinary corpus bytes MUST be either:

- immutable repository-relative exact bytes under
  `evaluation/aegis_v2/fixtures/<sha256>/...`; or
- exact inline bytes with an explicit base64 or UTF-8 encoding.

Every fixture records encoding, BOM/EOL policy, byte size, SHA-256, read-only
mount path, and deterministic generator source/hash when generated. Absolute
temporary paths are acquisition metadata only. Fixture bytes use no Git text
conversion. Synthetic fixtures MAY validate ordinary protocol logic; they MUST
NOT satisfy Phase 0B capability gates, which require real Codex child, event,
version, interruption, capacity, and restart evidence.

### 14.4 Required oracle matrices

Recovery cases use `RecoveryRecord.v1` and the uninterrupted-reference
comparison from Section 8. They MUST include crash pre/post state, action,
claim, receipt, event, journal/query evidence, and observable effect trace.

Side-effect cases MUST issue an actual duplicate/replay request. Queryable and
journaled operations return the existing result; unjournaled uncertainty
returns `UNKNOWN_SIDE_EFFECT` with zero automatic replay.

Generation fault cases MUST include:

- cleanup preauthorization false: reject before the first native create, with
  zero instance and zero batch mutation;
- cleanup preauthorization true: separate single-fault cases for native create,
  create-event/provisional persistence, thread/session/role identity, parent
  binding, panel/capability validation, and pre-activation registry commit;
- an aborted batch, every created instance registered as a visible provisional
  orphan, unchanged prior generation, zero dispatch, and authoritative close
  receipts only for the exact preauthorized batch.

Isolation is the Cartesian product of actors A–F and four attack classes:
direct sibling contact, descendant creation, cross-role outbox write, and
shared-file messaging. Input evidence MUST be a platform denial raw result or
an immutable authority event containing sender, receiver, path, turn,
tool-call, and raw bytes. Conclusion booleans are not evidence.

Protocol mutation MUST vary exactly one binding field at a time while preserving
all other raw bytes: protocol, campaign, run, source baseline, registry
snapshot, plan, execution contract, node, attempt, action, target role,
thread, session, generation, revision, payload path/hash, issued/expiry UTC,
nonce, transition, state sequence, result hash, claim/receipt IDs, and authority
event IDs. Separate cases cover duplicate consumption, expired action, old
turn, omitted/inserted/reordered events, duplicate/out-of-order receipts, and
forged/truncated raw bytes. Every mutation fails closed.

The frozen corpus MUST also contain clean and must-detect counterparts for:

- Windows traversal, drive-case, UNC, junction, and symlink escape;
- stale fixed filenames;
- dirty worktree, untracked file, dependency, and Skill drift;
- non-zero return code with success-looking text;
- unchanged remote locator with changed bytes;
- source/environment drift after A, B, C, D, E, and before F commit;
- A self-approval, adjacent-role reuse of one thread/session, C changing an
  expectation, C misclassifying omission as environment gap, and D ignoring a
  non-zero return-code preimage.

After cancellation precedence is fixed, verdict property tests MUST generate
every pair of simultaneous priority conditions, all schema-valid and invalid
closure combinations, required/optional fact-set combinations, and missing or
extra blocker/gap/action/job registrations. An independent reference model
compares exact decision bytes and ordered reason IDs.

### 14.5 Extreme scenarios and risk register

An extreme scenario enters the corpus only when it has a demonstrable trigger
inside the declared runtime and enough probability/exposure to affect the
quality judgment, or when a low-probability trigger can cause safety, privilege,
irreversible data, legal, or systemic harm. Every inclusion and exclusion is an
`ExtremeScenarioDecision.v1` containing stable scenario ID, defect class,
trigger, boundary, probability/exposure evidence or explicit assumption,
impact, rationale, source evidence, decision actor, independent review, event,
and prior register hash.

Exclusions are appended to immutable `ExclusionRiskRegister.v1`; none may be
silently dropped. Its head hash is bound by both the evaluation manifest and
the Phase 0A root.

An independent contract reviewer MUST approve case inputs, exact expectations,
oracle mappings, denominator and must-detect membership, supersession events,
and the risk-register head before the root freezes.

Release acceptance is exact per case, never an average or score:

- every latest-valid `ACTIVE` must-detect invariant case rejects the prohibited
  state;
- every proven clean reference case produces its exact expected result;
- every stale/baseline/producer/generation mismatch is rejected;
- no author self-closes and no blocker closes without required evidence;
- every recoverable crash window converges to equivalent state/events without a
  skipped node;
- journaled non-idempotent effects occur at most once; unjournaled uncertainty
  never auto-replays;
- every isolation attack is prevented or authoritatively detected;
- active-run user text enters zero node payloads;
- every report conclusion exactly matches D-accepted evidence and F's current
  basis.

Exploratory mutation findings are reported separately. Aggregate recall,
reviewer score, speed, token use, retry count, and wall-clock time cannot mask a
single failed must-detect case.

## 15. Phase 0B fail-closed capability gates

All entries below are currently `UNVERIFIED`. Documentation, probes, and code
MUST NOT state or imply otherwise before live evidence exists.

The initial target baseline is Codex CLI `0.145.0` and Codex Desktop
`26.721.4979.0`. Probe evidence applies only to the exact recorded versions and
environment; version drift requires re-certification.

| Capability | Required live proof |
|---|---|
| Parent-owned identity | Stable authoritative `thread_id + session_id`, parent relationship, role, generation, revision, creation time, and sidebar identity binding. An optional `agent_handle` is accepted only with its observed source and is not an identity key. |
| Cross-turn relay | One complete persist/dispatch/claim/outbox/authoritative-ingest/gate cycle, then recovery from a Master-turn interruption using checkpoint state only. |
| Authoritative provenance | Actual sender/receiver, prompt, turn/tool-call, lifecycle generation, and child-result binding from a source the Master cannot rewrite. |
| Durable retention | Two six-role source generations remain individually observable and addressable after a real Codex Desktop shutdown/restart. |
| Certified capacity | With 12 retained instances, a third generation is blocked before any creation; six role replacements reach 18; a seventh replacement is blocked before creation. |
| Provisional atomicity | Without cleanup preauthorization the experiment is rejected before the first create. With exact batch-scoped cleanup preauthorized, separate faults at native create, create-event/provisional persistence, thread/session/role identity, parent binding, panel/capability validation, and pre-activation registry commit yield a registered aborted batch, observable provisional orphans, authoritative close receipts, zero partial activation, zero dispatch, and unchanged prior generation. |
| Replacement atomicity | For every role and each crash boundary around creation, validation, and pointer commit, recovery leaves at most one dispatchable identity; old/late identities remain traceable and cannot drive a gate. |
| Role isolation | Direct sibling contact, descendant creation, cross-role writes, and indirect shared-file messaging are all prevented or completely detected by authoritative events. |
| User visibility | All retained, lost, superseded, replacement, and orphan identities remain locatable under the original parent within the certified contract. |

Phase 0B uses synthetic baselines but real Codex children, native parent tools,
events, capacity, interruption, and Desktop restart. Simulated evidence cannot
satisfy these gates.

Failure of identity binding, cross-turn recovery, authoritative provenance,
retention/capacity, lifecycle atomicity, visibility, or isolation means the
current Codex version cannot implement this contract. Phase 1–5 and formal
product tests MUST stop.

## 16. Phase 0A exit evidence

### 16.1 Normative file domain and root

`Phase0FreezeRecord.v1` MUST enumerate these logical artifacts explicitly; a
glob without its resolved entries is invalid:

1. the repository-canonical requirements
   `docs/aegis_v2_requirements.md`, reviewed implementation plan
   `docs/aegis_v2_upgrade_plan.md`, and static Codex capability evidence
   `docs/aegis_v2_codex_static_evidence.md`. Their temp-source paths and
   pre-archive hashes are provenance only and MUST NOT replace these repository
   locators;
2. this contract and the dual-plane ADR;
3. `.gitattributes`, `pyproject.toml`, and the current platform lock
   `pylock.windows-py313.toml`;
4. `schema_bundle.v1.json` and every versioned schema listed by it;
5. the latest evaluation manifest, its complete parent chain, raw fixtures,
   fixture catalog, runner contract, and exclusion risk register;
6. every reference generator, oracle, and comparator executable source plus the
   complete source manifest that maps its stable ID to retrievable source bytes,
   dependency/import policy, byte size, and hash. The resolved set is
   `evaluation/aegis_v2/reference/{__init__.py,__main__.py,canonical.py,cli.py,
   closure.py,closure_materialization_data.py,comparator.py,coverage.py,
   generator.py,manifest.py,materialization.py,materialize_closure.py,
   materialize_verdict.py,schema_validation.py,verdict.py,verdict_facts.py,
   README.md,tests/test_audit_remediation.py,tests/test_reference.py,
   source_manifest.v1.json}`; unresolved globs are invalid.

The versioned schema
`schemas/aegis/v2/reference_source_manifest.v1.schema.json` MUST be present in
the schema bundle and therefore in item 4; its validated
`evaluation/aegis_v2/reference/source_manifest.v1.json` instance is the
`EVALUATION_REFERENCE_SOURCE_MANIFEST` leaf in item 6.

The independent final review artifact is a review binding, not a leaf in the
normative root it reviews.

Each `FreezeInput` leaf has exactly
`{logical_path, locator, artifact_kind, byte_domain, byte_size, raw_sha256,
semantic_jcs_sha256, leaf_sha256}`. `locator` is an explicit union of
repository-relative location and external acquisition location. `byte_domain`
and hashes bind these preimages:

- JSON: `byte_domain=JCS_RFC8785`; parse with duplicate members rejected,
  require the locator bytes to be UTF-8 without BOM and LF-only, retain those
  exact locator bytes in `byte_size/raw_sha256`, and separately bind the RFC
  8785 JCS UTF-8 hash in `semantic_jcs_sha256`;
- Markdown: `byte_domain=UTF8_LF_NO_BOM`; the locator bytes themselves MUST
  already be UTF-8 without BOM and LF-only, bind them unchanged in
  `byte_size/raw_sha256`, and set `semantic_jcs_sha256=null`;
- fixtures, locks, source files, `.gitattributes`, and other exact-byte
  artifacts: `byte_domain=GIT_BLOB_BYTES`; bind the exact locator bytes in
  `byte_size/raw_sha256` and set `semantic_jcs_sha256=null`.

`byte_size/raw_sha256` always bind the exact bytes obtained from `locator`;
`byte_domain` never redirects those fields to a semantic serialization. For
JSON, both the exact raw binding and semantic JCS binding enter `leaf_sha256`,
so whitespace, EOL, or other raw formatting drift changes the freeze root even
when the parsed JSON value is unchanged.

A hash or source-manifest row without a retrievable locator and exact source
preimage is not a freeze input.

`leaf_sha256` is SHA-256 over the leaf's JCS bytes with only `leaf_sha256`
omitted. Leaves are sorted by `logical_path` in Unicode code-point order.
`freeze_root_id` is SHA-256 over RFC 8785 JCS UTF-8 bytes of the sorted array
`[{logical_path, leaf_sha256}, ...]`. Absolute acquisition locators remain
explicit but cannot replace logical identity. The repository `.gitattributes` enforces LF for
schemas/evaluation/docs and `-text` for fixtures, but checkout rules do not
replace the preimage definitions above.

### 16.2 Code-absence proof

`CodeAbsenceProof.v1` MUST bind:

- `freeze_base_commit`;
- the exact five-element direct argv
  `["git","ls-tree","-rz","--full-tree","<freeze_base_commit>"]`, with the last
  element equal to `freeze_base_commit`, repository-root cwd, exit code zero,
  empty stderr, and exact NUL-delimited stdout bytes/base64, size, and SHA-256;
- the complete sorted union of every base-tree tracked path and every
  non-ignored untracked path, including tracked deletions. Each inventory entry
  binds `entry_kind`, base/worktree exact-byte records, Git blob ID where
  applicable, external frozen-snapshot locator/event where applicable, and its
  self-omission content ID;
- the inventory self-omission ID, recomputed tracked and non-ignored-untracked
  counts, and the exact sorted allowed Phase 0A file-domain path set;
- `outside_domain_entries` as the exact inventory complement of the allowed
  domain, with one independent reviewer disposition artifact and exact
  locator/bytes/hash for every entry;
- the complete prohibited-implementation classifier set, separate base-tree and
  worktree match arrays, proof event, and proof UTC.

Modified and non-ignored untracked worktree bytes MUST become retrievable
content-addressed preimages before review. The repository-local acquisition is
the direct argv
`["git","hash-object","-w","--no-filters","<path>"]`, with `<path>` a previously
resolved literal repository-contained file path. It writes the exact bytes to
the Git object database without staging or committing them and without applying
clean/smudge filters. The collector requires exit code zero and a single valid
object ID, then reads `git cat-file blob <object-id>` as raw bytes and verifies
the recorded size and SHA-256 before using `source_kind=GIT_BLOB` and that
`git_blob_id` in the inventory. Missing objects, filtered-byte mismatch, path
escape, or garbage collection before the implementation-order proof invalidates
the freeze. An independently retained `FROZEN_SNAPSHOT` may be used instead only
through its schema-defined external locator and acquisition event.

An outside-domain entry may use `BASE_EQUAL` only when its tracked base/worktree
bytes are identical. Otherwise it requires `PREEXISTING_NON_V2`, exact bound
bytes, `NOT_V2_IMPLEMENTATION`, rationale, independent reviewer
thread/session/turn identity, and disposition-artifact locator/size/hash. Any
unclassified entry, missing inventory member, count mismatch, or v2 kernel,
relay, live capability-probe, or equivalent executable implementation makes the
proof fail. The proof's own ID is SHA-256 over its complete JCS preimage with
only `code_absence_proof_id` omitted.

### 16.3 Independent review and external anchor

The final independent reviewer MUST emit an authoritative Codex final event
from an append-only source the Master cannot rewrite. Its raw preimage MUST bind:

- preauthorized provider/policy identity, provider event ID, monotonic log
  position, authority committed UTC, and the exact Codex CLI version plus
  app-server protocol semantic hash;
- reviewer `thread_id + session_id`, parent identity, parent spawn and delivery
  tool-call IDs, reviewer turn and final item IDs;
- exact item type `agentMessage`, phase `final_answer`, item start/completion,
  turn start/completion, and terminal turn status `completed`;
- `freeze_root_id` and `code_absence_proof_id`;
- the complete review artifact's logical locator, byte size, and SHA-256;
- exact `verdict=PASS` and an empty blocker set.

The authority proof MUST retain exact parent spawn, item-completed, and
turn-completed record bytes, sizes, and SHA-256 values. The final item text MUST
be the exact canonical `Phase0ReviewFinalEvent` bytes. The freeze record stores
that payload's authority locator, exact raw bytes/size, and raw SHA-256. It also
persists the freeze producer's exact
`thread_id + session_id + turn_id`; reviewer independence MUST remain
verifiable from the record without caller-supplied identity. The review anchor
and authority anchor MUST identify the same reviewer-final delivery event.
`freeze_record_id` is SHA-256 over the complete freeze record's JCS bytes with
only `freeze_record_id` omitted; that record contains `freeze_root_id`,
code-absence proof, producer identity, review artifact, and event raw hash
without making the root depend on its later anchor. Rewriting any normative
leaf, proof, review, verdict, or event requires a new independent review and new
external event; recomputing repository-local hashes alone cannot preserve the
anchor.

A caller-provided boolean verifier or exact-byte reader is forbidden: both can
approve or echo caller-forged bytes. Local app-server/history, rollout JSONL,
SQLite, CAS, local hash chains, HMAC, and opaque attestation are non-authority.
A source becomes eligible only through a concrete provider adapter fixed by a
candidate-external preauthorized policy and a proof independently reusable by a
second consumer. With no such adapter or self-contained proof, public
finalization/verification MUST fail `AUTHORITY_UNVERIFIED`. An offline validator
may separately report structural validity, but MUST return overall invalid for
every `FROZEN` record whose external authority was not independently verified.
`PENDING` likewise returns `valid=false`, `phase_complete=false`, a nonzero
process exit, and explicit authority/freeze-evidence blockers; only
`structural_valid=true` may be reported separately. A consumer MUST NOT infer
phase completion from structural validity.
Synthetic test seams MUST be internal, unavailable through environment/config
flags, and incapable of producing a production-schema-valid frozen record or a
record accepted by the public validator.

### 16.4 Implementation ordering

Before the first v2 implementation commit is accepted, the gate MUST prove:

- its ancestry contains `freeze_base_commit`;
- its parent tree plus recorded worktree/untracked preimage equals the frozen
  repository snapshot;
- every implementation delta occurs after the authority committed UTC and
  external event order; reviewer-declared or caller-provided UTC is not an
  ordering authority;
- the implementation evaluates against the exact externally anchored
  `freeze_root_id`.

The freeze record does not require or authorize a spec-only commit. It makes
untracked normative bytes explicit, so `freeze_base_commit` alone is never
treated as binding those bytes.

Phase 0A may be marked complete only when:

1. this contract, the dual-plane ADR, every versioned Phase 0A schema, and the
   full manifest chain, raw fixtures, runner/oracles, and risk register are
   mutually consistent;
2. every schema and corpus hash is recomputed in its normative domain;
3. a new independent reviewer records no open blocker and emits the external
   event above;
4. `Phase0FreezeRecord.v1`, the normative root, and code-absence proof all
   validate;
5. case mutation fails, and legal supersession changes release membership only
   through a valid append-only event over the complete parent chain;
6. first-implementation ancestry/order validation passes when that commit
   exists.

Until then, the only accurate phase result is:

```text
PHASE_0A_PENDING_FREEZE_EVIDENCE
```
