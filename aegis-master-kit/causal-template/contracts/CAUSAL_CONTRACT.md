# Causal Store Contract

## Definition

Causal Store is the project-level, branch-versioned, encrypted reasoning-state store.

It stores:

- reviewed causal claims
- causal proposals
- causal relations
- conflict/review/merge records
- status transitions
- current-query route and expansion plans
- model-readable causal-view metadata

It does not store:

- complete chain-of-thought
- raw chat history
- task responsibility history
- pure environment facts
- pure external requirements
- unreviewed agent opinions as global causal truth

## First principle

A causal claim is reusable only if later agents can see:

- what the claim says
- why it holds
- what evidence supports it
- where it holds
- what assumptions/conditions it depends on
- what it depends on, supersedes, or invalidates
- whether it should enter the current reasoning and how deeply it should expand

## Boundary with Knowledge

Knowledge stores directly valid neutral facts and constraints.

Causal stores inferred judgments.

Example:

```text
Knowledge:
  Target device downclocks severely when chip temperature exceeds 85 C.

Causal:
  Because the device downclocks above 85 C and the current pipeline is near CPU budget,
  the current pipeline has real-time risk in high-temperature operation.
```

## Boundary with Archive

Archive records historical events and responsibility.

Archive may provide evidence references, but Archive does not produce causal truth.

## Direct fact rejection rule

Causal Store accepts inferred judgments, not raw facts.

A statement is not a Causal claim if it only records:

- objective fact
- environment fact
- dependency version
- customer constraint
- platform property
- neutral requirement

Such input must be rejected as Causal and reclassified as a Knowledge candidate when appropriate.

Examples:

```text
Target OS is Ubuntu 22.04
-> Reject as Causal; route to Knowledge.

Customer requires memory usage < 500MB
-> Reject as Causal; route to Knowledge.

Because target OS is Ubuntu 22.04 and dependency X is unavailable,
implementation path Y is incompatible under this environment
-> Eligible as a Causal proposal after review.
```

## Global consistency rule

Within the same scope, version context, valid conditions, assumptions, Knowledge baseline, and Causal baseline, canonical active causal claims must not conflict.

A conflict in review is an abnormal signal. It must be resolved before merge by rejection, scope split, assumption update, invalidation, supersession, or evidence request.

## Route/expand rule

Route and expansion grades are part of the Causal system because they prevent high-value causal state from being fully injected into every reasoning turn.

They are dynamic views under a current query, not permanent claim attributes.

## Proposal versus global truth

Agent-generated causal output may be accepted as a Causal Proposal when it satisfies proposal shape. It must be rejected as a Global Causal Write if it attempts to mutate canonical global Causal Store directly.

Accepted proposal is not active global causal truth. It remains pending Master/Adjudicator high-budget review until explicitly accepted and merged.
