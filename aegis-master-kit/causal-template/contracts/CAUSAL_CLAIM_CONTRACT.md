# Causal Claim Contract

## Definition

A causal claim is an inferred judgment that may be reused as a reasoning premise under declared scope, version context, conditions, and assumptions.

A direct fact is not a causal claim. Direct objective facts, environment facts, dependency versions, customer constraints, platform properties, and neutral requirements must be rejected as Causal claims and routed to Knowledge when appropriate.

## Required fields

An accepted claim must include:

- `id`
- `claim`
- `why`
- `scope`
- `version_context`
- `valid_when`
- `assumptions`
- `evidence_refs`
- `proof_mode`
- `confidence`
- `status`
- `admitted_by`
- `admitted_at`

## Why field

`why` is the minimal supporting cause. It must not contain full chain-of-thought. It should be short enough to audit and reusable enough to explain why the claim holds.

## Evidence references

Evidence may reference:

- Knowledge entries
- Archive artifacts
- code inspection locations
- logs
- tests
- statistical results
- contracts
- prior causal claims
- external specifications

Evidence references must identify source type, reference, and enough scope to be audited.

## Proof mode

Each claim must declare proof mode, such as:

- `first_principles`
- `contract_deduction`
- `code_inspection`
- `reproducible_test`
- `statistical_evidence`
- `observation_only`
- `expert_report`

Observation-only claims must not become high-confidence hard premises without explicit review.

## No auto-promotion

Knowledge facts do not automatically become causal claims.

Archive events do not automatically become causal claims.

## Direct fact examples

```text
Target OS is Ubuntu 22.04
-> Reject as Causal; route to Knowledge.

Customer requires memory usage < 500MB
-> Reject as Causal; route to Knowledge.

Because target OS is Ubuntu 22.04 and dependency X is unavailable,
implementation path Y is incompatible under this environment
-> Eligible as a Causal proposal after review.
```
