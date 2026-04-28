# Causal Review Contract

## Definition

Causal Review is the high-budget audit process that decides whether candidate causal structures may enter the canonical Causal Store.

## Reviewer

Current v1 reviewer may be Master. A future system may use a dedicated Adjudicator.

## Reasoning budget

Causal Review must use high reasoning budget or equivalent strict review mode because it modifies reusable reasoning premises.

## Review checks

For every proposal, review must check:

- Is it Causal, not Knowledge or Archive?
- Is it an inferred judgment, not a direct fact that should be rejected as Causal and routed to Knowledge?
- Does it have claim, why, evidence, scope, version context, conditions, and assumptions?
- Does proof mode justify confidence?
- Does it overgeneralize?
- Does it conflict with active claims?
- Does it require scope split?
- Does it require Knowledge correction?
- Does it challenge an old claim?
- Is the branch stale?
- Is it being accepted only as a proposal, not as an unreviewed global Causal write?

## Allowed decisions

- `accept_as_active`
- `accept_as_tentative`
- `reject`
- `request_more_evidence`
- `mark_conflicted`
- `split_scope`
- `supersede_existing`
- `invalidate_existing`
- `mark_branch_stale`

## Review record

A review record stores decisions and rationale summaries. It must not store full chain-of-thought.

## Boundary decisions

Direct facts must be rejected as Causal and routed to Knowledge when appropriate.

Agent-generated causal output may be accepted as a proposal for review. It must be rejected as a global write unless Master/Adjudicator has completed review and merge.
