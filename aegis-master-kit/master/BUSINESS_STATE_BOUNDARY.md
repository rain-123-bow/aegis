# Business State Boundary

## 1. Purpose

`aegis-master-kit` does not store business state.

It does not store:

- archive entries
- knowledge facts
- causal structures
- project-specific constraints
- customer-specific requirements
- task records
- code

However, the Master must understand the admission rules for external business state stores so that unsupported claims do not become system facts or causal truth.

## 2. Archive Boundary

The archive records what happened.

Examples:

- a task was requested
- an agent produced a candidate
- a reviewer approved or rejected a candidate
- a developer made an assertion
- a test was run

Archive entries do not automatically produce truth.

An archived statement is evidence that a statement was made or an event occurred. It is not, by itself, proof that the statement is true.

Archive entries must not be directly promoted to system facts.

## 3. Knowledge Boundary

The knowledge store contains verified static facts and constraints.

Knowledge entries require adequate evidence. Examples may include:

- verified platform constraints
- confirmed customer requirements
- stable interface contracts
- validated environmental facts
- accepted glossary or domain definitions

Developer claims must not be written directly into the knowledge store.

If evidence is insufficient, the claim may be recorded as `developer_asserted` in the archive, but it must not become knowledge.

## 4. Causal Boundary

The causal store contains causal structures, not plain facts.

A causal entry must include:

- why the causal relation is believed to hold
- supporting evidence
- scope of validity
- assumptions
- known uncertainty or limits

Developer claims must not be written directly into the causal store.

A causal entry requires causal construction and governance judgment. It cannot be created merely because a developer asserts a conclusion.

## 5. No Direct Knowledge-to-Causal Promotion

Knowledge does not automatically become causality.

A verified fact may support causal reasoning, but it is not itself a causal structure.

Before knowledge can support a causal entry, the system must establish:

- the causal relation being claimed
- evidence connecting cause and effect
- scope where the relation applies
- assumptions required for the relation to hold
- governance acceptance of the causal interpretation

## 6. No Direct Archive-to-Fact Promotion

Archive entries do not directly become system facts.

The archive may prove that something was said, attempted, observed, or recorded. It does not prove that the archived content is correct.

Before an archived statement becomes knowledge, it must pass claim verification and evidence review.

Before an archived statement becomes causal truth, it must pass causal construction, evidence review, and scope judgment.

## 7. Master Responsibility

The Master does not write project facts into `aegis-master-kit`.

The Master must enforce the boundary between:

- what was said or happened
- what is verified as fact
- what is accepted as causal structure

When evidence is insufficient, the Master may:

- reject the claim
- downgrade the task to investigation
- record the claim as `developer_asserted` in the archive

The Master must not:

- treat developer claims as system facts
- write unsupported claims into knowledge
- write unsupported conclusions into causal
- promote archive entries directly into truth
- promote knowledge directly into causal truth without causal construction and judgment

## 8. Summary

```text
archive   = what happened; not automatic truth
knowledge = verified static facts and constraints
causal    = why/evidence/scope/assumptions causal structures
```

`aegis-master-kit` stores the governance rule for these boundaries, not the business state itself.
