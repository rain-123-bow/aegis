# Recorder frozen review batch protocol

Status: `ACTIVE_AUTHORING_AND_REVIEW_CONTROL`

## 1. Objective

The review process minimizes total time and total rework required to reach one
stable snapshot with zero P0/P1 findings. It does not minimize the time from
one finding to one patch.

Finding discovery and author remediation are separate phases. A finding may be
recorded immediately, but it cannot trigger an immediate source edit.

## 2. State machine

```text
AUTHORING
  -> SNAPSHOT_FROZEN
  -> REVIEWERS_PROVISIONED
  -> DISPATCH_FROZEN
  -> REVIEW_BATCH_RUNNING
  -> REVIEW_RESULTS_COMPLETE
  -> REVIEW_AGGREGATED
  -> REVIEW_BATCH_CLOSED
  -> AUTHORING
```

Only `AUTHORING` may modify reviewed source files. Only
`REVIEW_BATCH_RUNNING` may run reviewers. No state permits both.

Missing, malformed, or contradictory batch state fails closed. It never
authorizes a reviewer or a source modification.

## 3. Frozen snapshot identity

Before any reviewer starts, Master creates a repository-external local Windows
artifact directory:

```text
C:\code\aegis-review-artifacts\<batch_id>\
```

`batch_id` is the UTC creation timestamp plus the first twelve hexadecimal
characters of the aggregate snapshot SHA-256. It is unique in time and content.

The batch contains:

```text
SNAPSHOT_MANIFEST.json
SNAPSHOT\
REVIEW_DISPATCH.json       # absent until the achievable roster is provisioned
RESULTS\
AGGREGATE.md              # absent until all reviewer calls finish
BATCH_STATE.md
```

`SNAPSHOT` is an exact copied allowlist, not the active checkout. Reviewers
receive only this snapshot path. They must not read the active checkout,
conversation history, prior review results, or another reviewer result.

The manifest records:

- schema and batch ID;
- creation UTC;
- repository path for provenance only;
- Git branch and HEAD commit;
- exact `git status --short --branch`;
- each copied repository-relative path, decimal byte size, and lowercase
  SHA-256;
- aggregate SHA-256.

Git HEAD is not the snapshot identity when the worktree is dirty or contains
untracked inputs. The aggregate SHA-256 is authoritative. Its preimage is, for
each file in strict UTF-8 repository-path order:

```text
lowercase_sha256 + SP + decimal_byte_size + SP + repository_path + LF
```

Snapshot files are marked read-only after copying. Every reviewer independently
recomputes all file hashes and the aggregate before and after its scan. A
mismatch makes that reviewer result `INVALID_SNAPSHOT`; it does not permit the
reviewer to switch to the live checkout.

## 4. Provisioning and immutable dispatch

Reviewer creation and reviewer execution are separate. A newly provisioned
reviewer receives only a wait instruction, the intended batch ID, and its
requested role. It must not read the snapshot until Master sends the frozen
dispatch hash.

Master first provisions the achievable reviewer roster and records every
successful real agent/task ID and every failed creation attempt. A creation
failure occurs before review starts and cannot be represented as a reviewer
result. Master may reassign the complete planned scope among successfully
provisioned reviewers only while state is `REVIEWERS_PROVISIONED`.

Master then create-new writes exact canonical `REVIEW_DISPATCH.json`:

```text
batch_id
created_at_utc
reviewers=[
  {
    agent_id,
    primary_scope,
    result_path,
    reviewer_id
  }
]
schema="AegisFrozenReviewDispatch.v1"
snapshot_id
```

Reviewer IDs, agent IDs, scopes, and result paths are unique. The reviewer
array is strictly raw-ASCII `reviewer_id` ordered and has 1..16 items. Each
result path is exactly `RESULTS/<reviewer_id>.md`. The dispatch content ID is
SHA-256 over
`"AEGIS_FROZEN_REVIEW_DISPATCH_V1\0"` plus its exact UTF-8 bytes.

After independently reopening and hashing the dispatch, Master enters
`DISPATCH_FROZEN` and sends that one content ID to every listed agent. Only a
listed agent receiving the exact ID may enter `REVIEW_BATCH_RUNNING`. From
that point:

- expected reviewer count, IDs, scopes, and result paths are immutable;
- a missing, blocked, or crashed reviewer blocks the batch;
- no reviewer can be removed or have its scope reassigned;
- a new agent requires a new dispatch and therefore a new batch;
- failed creation attempts remain in `BATCH_STATE.md` but never become fake
  agents or expected result files.

This barrier permits Codex agents to be created before any review begins,
while still binding real agent IDs. It also prevents thread-limit discovery
from changing a running review roster.

## 5. Reviewer execution contract

All reviewers in one batch start against the same snapshot ID. Each has one
disjoint primary focus, but every reviewer must read the complete frozen
implementation plan and all shared normative inputs required to test its
cross-contract relations.

A reviewer must:

1. verify its own immutable dispatch row and the dispatch content ID;
2. sample exact UTC before its first snapshot-manifest or snapshot read;
3. verify the snapshot before normative reading;
4. scan its complete assigned matrix;
5. continue after every P0/P1 finding;
6. cover normal, failure, crash, replay, concurrency, and boundary-value
   counterexamples where applicable;
7. accumulate all findings before returning;
8. verify the snapshot again after scanning;
9. write one independent Markdown result.

Finding one issue is never a completion condition. `scan_complete=true` is
legal only after the assigned matrix has been exhausted.

The exact started UTC sampled in step 2 is retained unchanged and copied into
the final result. It cannot be reconstructed from dispatch, file times, or a
later reconciliation timestamp. Failure to retain it produces
`scan_status=BLOCKED`.

## 6. Result files

Each reviewer owns exactly one file:

```text
RESULTS\<reviewer_id>.md
```

The file contains:

```text
# Review result

Snapshot ID
Snapshot aggregate SHA-256
Reviewer ID
Primary scope
Started/completed UTC
Start/end hash verification
Scan complete
Verdict
P0/P1/P2 counts
Coverage matrix
All findings
Unverified items
Quality self-check
```

Every finding contains a stable ID, severity, exact location, violated
contract, counterexample, consequence, and required fix. Optional suggestions
are separated from blockers.

The reviewer final message contains only:

```text
artifact_path=<absolute result Markdown path>
snapshot_id=<batch snapshot ID>
scan_status=COMPLETE|BLOCKED|INVALID_SNAPSHOT
```

Findings, summaries, arguments, and suggested patches are forbidden in chat or
agent final text. If a reviewer cannot complete, it still writes a Markdown
result describing the completed coverage, missing coverage, and blocker, then
returns only that path.

## 7. Master immutability rule

From snapshot freeze until every dispatched reviewer call has returned:

- Master does not modify any reviewed source file;
- Master does not replace or regenerate the snapshot;
- Master does not start an author or fixer;
- Master does not ask a reviewer to patch;
- Master does not discard a result because another result arrived first;
- Master does not declare the batch complete while any result is missing.

Writing reviewer result files and batch-control artifacts outside the snapshot
does not modify the reviewed source.

An external change to the active checkout does not invalidate a snapshot
review. It makes the active checkout a different future candidate. Results
remain valid evidence about their recorded snapshot.

## 8. Aggregation

After every reviewer call returns, Master verifies that every expected result
file exists and binds the same snapshot ID and aggregate hash. Master then
writes `AGGREGATE.md` without modifying reviewed source.

Aggregation:

1. retains every original result path and finding ID;
2. includes blocked and invalid-snapshot results;
3. groups duplicate counterexamples without deleting their sources;
4. records dependencies and conflicts between fixes;
5. assigns each finding one disposition:
   `ACCEPTED`, `REJECTED_WITH_EVIDENCE`, `NEEDS_USER_DECISION`, or
   `NONBLOCKING_DEFERRED`;
6. defines one ordered remediation batch.

A result whose source SHA is no longer the active checkout SHA is never
silently discarded. It remains in the aggregate. A later batch may mark the
finding `FIXED`, `STILL_APPLICABLE`, or `SUPERSEDED_BY_EXPLICIT_CHANGE`, with
evidence and a link to the original finding.

## 9. Unified remediation

Only after `AGGREGATE.md` is complete does Master close the review batch and
return to `AUTHORING`.

The author applies the accepted remediation batch once. No reviewer runs while
those edits occur. Partial fixes do not create intermediate review batches.

After all edits and direct consistency tests pass, Master creates a new
snapshot with a new batch ID. The next reviewers scan the full assigned matrix
against the new snapshot; they do not inspect only changed lines.

## 10. Pass boundary

A batch can authorize the next stage only when:

- every dispatched reviewer result exists;
- `REVIEW_DISPATCH.json` is valid, immutable, and binds every result;
- every result has `scan_complete=true`;
- every result records an exact pre-read started UTC;
- start/end snapshot hashes match;
- aggregation includes every result and finding;
- aggregate P0 and P1 counts are zero;
- no required scope is unverified;
- the reviewed snapshot is the exact candidate selected for the next stage.

Reviewer PASS is advisory plan quality evidence. It does not prove code,
tests, runtime behavior, user identity, or user acceptance.
