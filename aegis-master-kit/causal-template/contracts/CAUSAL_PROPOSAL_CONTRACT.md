# Causal Proposal Contract

## Definition

A causal proposal is a candidate causal claim submitted by a developer or agent for review.

It is not global causal truth.

Accepting a submission as a Causal Proposal does not accept it as active global truth. The correct labels are:

- `Accept as Causal Proposal`
- `Reject as Global Causal Write`
- `Pending Master/Adjudicator high-budget review`
- `Not active global truth`

## Allowed submitters

- developer
- master
- debate agent
- implementation agent
- reviewer agent
- verification agent
- contract agent
- other authorized task agents

## Proposal requirements

A proposal must include:

- proposer identity and role
- task id or work context
- based-on Git branch/commit when available
- based-on Knowledge and Causal versions
- proposed claim with why/evidence/scope/conditions/assumptions
- intended operation: add, challenge, supersede, invalidate, split scope
- references to affected causal claims if any

If the submission contains only a direct fact, environment fact, dependency version, customer constraint, platform property, or neutral requirement, it must be rejected as Causal and routed to Knowledge when appropriate. It is not a valid causal proposal unless it contains an inferred judgment with why, evidence, scope, version context, and assumptions.

## Agent output handling

Debate, Reviewer, Verification, and Implementation Agent outputs may enter the proposal queue if they satisfy proposal shape. They must not mutate canonical global Causal Store.

Examples:

- Debate Agent submits a causal claim with why/evidence/scope/assumptions -> Accept as Causal Proposal; pending Causal Review.
- Debate Agent asks to write directly into global causal claims -> Reject as Global Causal Write.
- Reviewer submits an invalidation claim with evidence -> Accept as Causal Proposal; pending Causal Review.
- Reviewer directly marks a global claim invalidated -> Reject as Global Causal Write.

## Proposal status

Allowed proposal statuses:

- `draft`
- `submitted`
- `pending_review`
- `accepted`
- `accepted_as_tentative`
- `rejected`
- `needs_more_evidence`
- `superseded_by_review`

## Branch-local reasoning

Agents may extend causal reasoning locally through proposals or branch-local deltas. They must not mutate canonical global causal claims.
