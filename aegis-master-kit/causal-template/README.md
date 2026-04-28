# Aegis Causal Template v1

This template defines the project-level **Causal Store** used by Aegis.

The Causal Store is not a generic memory folder and not a conclusion cache. It is a versioned, encrypted, Master-reviewed reasoning-state store. It preserves reusable causal structures and the route/expand state needed to control which causal structures enter the current reasoning context.

## Core definition

```text
Causal Store =
  project-level encrypted causal premise store
  + current-query route/expand external attention state
  + proposal/review/merge records
  + Master-private integrity boundary
```

The Causal Store answers two questions:

1. **Causal validity**: why a judgment holds, under what scope, with what evidence, assumptions, and dependency relations.
2. **Current reasoning load control**: which causal claims should enter the current reasoning, in what priority, and how deeply they should be expanded.

## Relation to the three external state stores

```text
Archive   = what happened; task history, responsibility, audit trail.
Knowledge = what is known; neutral facts, constraints, environment, versions.
Causal    = why a judgment holds; reusable reasoning premises and route/expand views.
```

Knowledge may contain conditional objective facts. Causal contains inferred judgments built from Knowledge, Archive evidence, code, tests, logs, contracts, or prior causal claims.

Direct facts are invalid as Causal claims. A proposal that contains only an objective fact, environment fact, dependency version, customer constraint, platform property, or other neutral fact must be rejected as Causal and routed to Knowledge when appropriate.

Examples:

- `Target OS is Ubuntu 22.04` -> Reject as Causal; route to Knowledge.
- `Customer requires memory usage < 500MB` -> Reject as Causal; route to Knowledge.
- `Because target OS is Ubuntu 22.04 and dependency X is unavailable, implementation path Y is incompatible under this environment` -> eligible as a Causal proposal after review.

## Branch model

The Causal Store follows the project Git branch together with code, Archive, and Knowledge.

```text
branch = code + archive + knowledge + causal
```

Ordinary agents must not directly mutate the canonical global Causal Store. They may submit causal proposals or branch-local causal deltas. Before merge into the canonical branch, the proposals must go through high-budget Causal Review by Master/Adjudicator.

Agent-generated causal output must use dual-label handling:

- Accept as Causal Proposal when it has claim, why, evidence, scope, version context, and assumptions.
- Reject as Global Causal Write when it attempts to mutate canonical Causal Store directly.
- Keep it pending Master/Adjudicator high-budget review.
- Do not treat it as active global truth until reviewed and merged.

## Security model

The Causal Store has the strongest external-state security requirement.

Repository-visible project state must contain only:

- encrypted causal payload placeholder or encrypted payload
- public manifest/index summaries
- opaque integrity/seal records

Repository-visible project state must not contain:

- plaintext causal payload
- decryption keys
- private proof material
- proof-generation internals
- reproducible private verification procedure
- real encryption/decryption implementation

Master may disclose high-level verification status and non-sensitive summaries only.

## Model-readable causal view

AI models should not reason directly over binary causal payloads. Master must decrypt and verify the payload server-side, select and expand relevant claims, then inject a model-readable causal view in YAML/JSON/Markdown.

```text
encrypted payload
  -> Master decrypts + verifies
  -> structured causal graph
  -> route/expand selection
  -> model-readable causal view
  -> agent reasoning
  -> causal proposal
  -> high-budget causal review
  -> sealed merge into next global causal baseline
```

## Template vs project instance

This directory is a reusable Master-held template. It does not contain real project causal state.

A concrete project Causal Store is instantiated under:

```text
project-root/causal/
```

## Directory map

```text
causal-template/
  contracts/   Causal governance rules.
  schemas/     Minimal schemas for claims, proposals, routing, review, merge, and seals.
  templates/   Project repo shell, Master plaintext payload skeleton, update request templates.
  demos/       Safe examples illustrating repo-visible and Master-side shapes.
  checks/      Human-readable checks and invariants.
  tools/       Layout-only bootstrap/check helpers. No private crypto or proof logic.
```
