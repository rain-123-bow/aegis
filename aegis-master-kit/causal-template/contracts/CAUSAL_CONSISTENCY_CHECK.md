# Causal Consistency Check

## Repo-visible layout checks

A project Causal Store must contain:

- `causal_manifest.yaml`
- `encrypted/`
- `public/`
- `integrity/`
- `integrity/session_seals/`

Real project repositories must not contain plaintext causal payload.

## Master-side semantic checks

Master must check:

1. Every active claim has claim, why, evidence_refs, scope, version_context, valid_when, assumptions, proof_mode, confidence, and status.
2. Every active claim is an inferred judgment, not a direct fact that belongs in Knowledge.
3. Every direct fact submitted as Causal is rejected as Causal and routed to Knowledge when appropriate.
4. Every claim references valid Knowledge/Causal/Archive evidence where applicable.
5. No active conflicts exist under the same condition set.
6. Invalidated/superseded/rejected claims are preserved with transition metadata.
7. Every proposal has submitter, base version, operation intent, and proposed claim.
8. Every agent-generated output is either accepted as Causal Proposal or rejected as Global Causal Write.
9. Every accepted proposal has a review record before it becomes active global truth.
10. Every merged delta has a merge record.
11. Every route plan is tied to a current query and causal version.
12. Route/expand plans are not treated as permanent claim attributes.
13. Route/expand changes are covered by seal/integrity state.
14. Public indexes are derived helpers and not source of truth.
15. Seal mismatch, rollback, missing integrity, or stale state must stop governance actions requiring trusted Causal continuity.

## Terminal action

If Causal integrity or consistency fails, Master must not treat the local Causal Store as current trusted reasoning baseline until recovery, bootstrap, or revalidation succeeds.
