# Aegis Recorder design artifacts

Human authoring/evidence reading order:

1. `REVIEW_BATCH_PROTOCOL.md` — frozen-snapshot batch review and artifact
   retention rules.
2. `REQUIREMENT_ADDENDUM.md` — authorized scope and acceptance requirements.
3. `THREAT_MODEL.md` — protected facts, attacks, and non-authority boundary.
4. `JOURNAL_PROTOCOL_V1.md` — exact byte format and forwarding semantics.
5. `SUPERVISOR_CONTRACT.md` — Windows lifecycle and failure behavior.
6. `SUPERVISION_SIDECAR_CONTRACT.md` — guard-owned Windows termination and
   reclamation evidence.
7. `POSIX_ADAPTER_CONTRACT.md` — normative Linux/WSL adapter boundary.
8. `VERIFIER_CONTRACT.md` — independent parser, result, reasons, and exits.
9. `CODEBASE_FACTS.md` — command-backed repository and toolchain snapshot.
10. `REASONING_LEDGER_STATUS.md` — unavailable project-ledger context boundary.
11. `IMPLEMENTATION_PLAN_FINAL.md` — source layout and TDD stages.
12. `PLAN_REVIEW_REPORT.md` — independent FAIL rounds and reconciliation
    history; it is not a normative plan input.
13. `USER_CONFIRMATION.md` — general authorization plus the still-required
    exact-plan acceptance gate before R11A.

`IMPLEMENTATION_PLAN_DRAFT.md` is retained only as the exact artifact that the
first independent reviewer rejected.

This navigation file is not part of a fresh final-review domain. A final
reviewer reads only the allowlist in the current validated review-snapshot
manifest. Unlisted repository files, including this README, the draft,
`PLAN_REVIEW_REPORT.md`, and `CONTINUATION.md`, are default-denied. No normative
claim may exist only in review history or navigation prose.

Architecture decisions:

```text
docs/decisions/0002-recorder-session-directory-evidence.md
docs/decisions/0003-recorder-protected-runtime-deployment.md
```

Machine-readable result schema:

```text
schemas/aegis/v2/recorder_verification_report.v1.schema.json
```

Current status:

```text
ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS
NO RECORDER CODE IMPLEMENTED
AUTHORITY_UNVERIFIED
```
