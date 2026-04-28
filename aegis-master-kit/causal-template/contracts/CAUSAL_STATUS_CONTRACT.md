# Causal Status Contract

## Claim statuses

Allowed claim statuses:

- `active`
- `tentative`
- `conflicted`
- `invalidated`
- `superseded`
- `deprecated`
- `rejected`

## Proposal statuses

Allowed proposal statuses:

- `draft`
- `submitted`
- `pending_review`
- `accepted`
- `accepted_as_tentative`
- `rejected`
- `needs_more_evidence`
- `superseded_by_review`

## Preservation rule

Causal claims and proposals must not be physically deleted when invalidated, superseded, rejected, or deprecated.

They must be preserved with status transition metadata.

## Required invalidation metadata

Invalidated claims must record:

- invalidated_at
- invalidated_by
- invalidation_reason
- invalidation_evidence_refs
- superseded_by if applicable

## Tentative use rule

Tentative causal claims must not be used as hard premises unless Master explicitly allows constrained use and marks the assumption visible in the model-readable causal view.
