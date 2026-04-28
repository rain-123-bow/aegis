# Aegis Knowledge Template v1

Knowledge Template defines how a Master creates and governs a project-level Knowledge Base.

A project Knowledge Base is a neutral fact and constraint store. It is accessible to all roles during reasoning and execution through governed access, but it is not a task history ledger and it is not a causal truth store.

## Definition

```text
Knowledge = project-level neutral facts and constraints,
            with source, scope, version context, applicability,
            Master-reviewed admission,
            encrypted local storage,
            append-preserved history,
            and tamper-detectable integrity.
```

Knowledge records what is known about the project or environment:

- platform and hardware facts
- OS and dependency versions
- runtime environment constraints
- customer requirements
- interface specifications
- resource budgets
- toolchain facts
- objective conditional facts
- externally imposed policies

Knowledge does not record:

- task history
- responsibility chains
- discussion trajectory
- causal conclusions
- strategic judgments
- implementation opinions
- unreviewed claims as active facts

## Core difference from Archive

```text
Archive   = what happened, for audit and responsibility.
Knowledge = what is known, for all-role reasoning.
```

Archive is not an ordinary execution dependency. Knowledge is part of the governed reasoning context used by Master and task agents.

## Core difference from Causal

```text
Knowledge = reality facts and constraints.
Causal    = because these facts hold, this conclusion follows.
```

Knowledge may contain conditional facts, but only when the condition and result are objective and source-backed.

Example Knowledge:

```text
When chip temperature exceeds 85 C, target device X severely downclocks.
```

Not Knowledge:

```text
Because the device downclocks at high temperature, the current architecture is invalid.
```

The second statement is a causal or design conclusion and must go through Causal admission.

## Master ownership and contribution model

Developer and agents may submit Knowledge proposals.

Only Master may approve, update, invalidate, supersede, seal, or expose Knowledge entries.

```text
candidate input -> Master review -> accepted/tentative/rejected/conflicted -> sealed Knowledge update
```

## Security baseline

Knowledge shares the same external-state security class as Archive and Causal:

- local repository stores encrypted payload only
- plaintext exists only in Master-controlled runtime
- private keys, seeds, integrity secrets, proof internals, and reproducible verification procedures are never stored in the repo
- developer cannot directly mutate Knowledge
- unauthorized mutation, rollback, missing seal, invalid payload, or freshness loss must be detectable by Master

## Template vs project instance

This directory is a Master-held template.

A concrete project instance is created under:

```text
/project-root/knowledge/
```

The template must not contain real project Knowledge entries. Demo entries are examples only.
