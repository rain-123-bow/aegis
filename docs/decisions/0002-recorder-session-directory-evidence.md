# ADR-0002: Verify Recorder evidence as one session directory

## Status

Proposed. Acceptance requires the independent Recorder plan reviewer to return
zero P0/P1 findings.

## Date

2026-07-28

## Context

Windows guard supervision can fail before the suspended engine executes its
first instruction. In that state `supervision.aegissup` exists, but
`journal.aegisrec` does not. A verifier that requires a journal path discards
the only durable evidence of the failed launch.

The evidence may also be copied from Windows to WSL for independent parsing.
Comparing the sidecar's recording-time session path with the verifier's current
path would make every legitimate relocation fail binding.

The Recorder must preserve local evidence without upgrading it to external
authority. Missing transport evidence must remain explicit.

## Decision

The verifier accepts one absolute session directory and derives only:

```text
journal.aegisrec
supervision.aegissup
```

On POSIX it traverses from `/` with held directory descriptors and
`openat(..., O_NOFOLLOW)`. On Windows it accepts only the frozen local-volume
path grammar, anchors the volume root, and opens every component relative to
the preceding held handle with `NtCreateFile`, `RootDirectory`, and
`FILE_OPEN_REPARSE_POINT`. Either adapter rejects every observed reparse/link
component and never follows a path found inside evidence.

The Windows guarantee starts when each component is first opened. Held handles
stabilize already-open objects and prevent reparse traversal. Without an
external expected FileId chain or oplock, an ordinary child replaced before its
first open is the current object selected by that open; the verifier does not
claim to recover or prove its historical identity.

The report carries `journal_present`, `evidence_platform_profile`, and
`supervision_journal_bound`.

- Journal present: use the journal-declared Windows or POSIX profile and the
  local transport evidence scope.
- Journal absent, sidecar structurally valid: use
  `WINDOWS_SUPERVISION_ONLY`, retain guard facts, and emit `JOURNAL_MISSING`.
  The bound flag distinguishes a pre-journal failure from a missing journal
  that previously existed.
- Journal absent, sidecar readable but invalid: use `UNDETERMINED`, the
  `NONE/NONE/NONE` assurance triple, and an invalid result. Retain only
  physical bytes and longest-legal-prefix diagnostics; do not claim local
  supervision integrity.
- Neither file readable: emit the no-evidence input-error row.

The journal and sidecar persist the same domain-separated recording-time
session-path digest. Binding compares those persisted values plus UUID and
journal genesis. The verifier's current path is advisory and excluded from
origin binding.

Sidecar-only evidence uses a supervision assurance/scope/ordering triple. It
never claims app-server transport integrity, clean transport, or PASS.
`authority_verified` and `release_authority_eligible` remain false for every
row.

## Alternatives considered

### Require `verify JOURNAL --supervision-sidecar ...`

Rejected. It cannot represent an engine-resume failure before journal creation
and permits mismatched arbitrary file locations.

### Add a separate sidecar-only report type

Rejected. Two report schemas would duplicate verdict, reason, authority, path,
and output-limit rules. One finite report relation can express journal,
supervision-only, and no-evidence rows without conflating their scopes.

### Compare against the verifier's current absolute path

Rejected. Artifact relocation is expected and does not alter recording-time
identity. Current-path comparison makes Windows-to-WSL verification
impossible.

### Treat a missing journal as generic input error

Rejected when a readable sidecar exists. That erases durable guard evidence
and makes pre-journal failure indistinguishable from no evidence.

## Consequences

- The report schema gains explicit presence/profile/binding fields and
  `JOURNAL_MISSING`.
- The verifier needs independent POSIX and Windows component-wise no-follow
  input adapters; a final-component-only Windows open is insufficient.
- Golden vectors must cover sidecar-only traces with and without
  `JOURNAL_BOUND`, header-only sidecars, copied directories, and invalid
  sidecars.
- A complete Windows PASS still requires a present valid journal plus a valid,
  bound, normally completed sidecar.
- Relocation changes only advisory report paths.
- Same-user storage rewrite and path races remain outside external-authority
  claims.
- The safe-read adapter proves no-reparse traversal and held-object stability,
  not pre-open path history.
