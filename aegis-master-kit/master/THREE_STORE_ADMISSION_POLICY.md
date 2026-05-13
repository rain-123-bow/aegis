# Three Store Admission Policy

## 1. Purpose

This policy defines the Master-owned admission rules for the three external business state stores:

```text
Archive   = what happened
Knowledge = what is known
Causal    = why a judgment holds
```

Phase 22A implements the admission boundary only. It does not implement production storage, global causal truth merge, production encryption, or persistent database semantics.

## 2. Ownership

Three-store admission is a Master governance capability.

It is not a fifth top-level department and not a long-lived independent agent in Phase 22A.

```text
Department outputs / developer claims / Master observations
  -> Master-owned admission gate
  -> archive_candidate | knowledge_candidate | causal_candidate | rejection | debate request
```

Only Master may approve, reject, downgrade, route, or request more evidence for three-store candidates.

Ordinary agents may emit candidate material or evidence references, but must not directly write Archive, Knowledge, or Causal stores.

## 3. Archive admission

Archive is Master-maintained project history and responsibility ledger.

Archive records:

- who requested a task
- when the task was requested
- who participated
- what stage occurred
- what artifact was produced
- what decision was made
- what outcome or rollback happened

Archive does not produce truth.

An archive entry may prove that a statement was made or an event happened. It does not prove the statement is correct.

Archive admission may accept event and responsibility records with enough timeline and evidence references, but must reject attempts to mark archived statements as Knowledge, Causal, or global truth.

Other agents do not require Archive as ordinary reasoning context. Master may extract selected material from Archive when needed.

## 4. Knowledge admission

Knowledge is Master-reviewed static project facts, constraints, and rules.

Knowledge may include:

- platform facts
- environment facts
- stable interface contracts
- customer or developer-confirmed constraints
- toolchain or dependency facts
- accepted glossary definitions
- project policies and templates

Knowledge must include:

- statement
- source or evidence
- scope
- version context or applicability context

Knowledge must not include causal reasoning chains, design conclusions, strategic judgments, or unsupported developer claims as active facts.

A proposal that contains `why`, causal dependencies, invalidation relations, or a "because ... therefore ..." design conclusion must be rejected as Knowledge and routed to Causal admission when appropriate.

## 5. Causal admission

Causal is the highest-value reasoning-state store.

Causal records reusable causal structures that can affect future project reasoning. It is not a conclusion cache and not a generic memory folder.

A Causal candidate must include at least:

- statement
- why
- evidence
- scope
- assumptions
- source origin
- candidate status

Causal candidates may also include:

- depends_on
- invalidates
- supersedes
- confidence
- route priority
- expand priority
- version context

Phase 22A can only stage a Causal candidate.

A staged Causal candidate is not canonical/global causal truth.

A staged Causal candidate is not a production Causal Store write.

The accepted Phase 22A Causal candidate sources are:

1. `master_unique_conclusion`:
   Master reaches a unique or near-unique project-direction conclusion with sufficient evidence, scope, assumptions, and limits.
   Master may directly construct and structurally admit the Causal candidate.

2. `debate_leader_adjudication`:
   Debate Leader emits an adjudicated causal chain after adversarial reasoning.
   This output is not automatically accepted.
   Master must perform structural admission review before it can be staged as a Causal candidate.

3. `execution_leader_directional_reasoning`:
   Execution Leader emits project-directional reasoning only when the implementation path is effectively unique and does not require Debate.
   Non-unique or non-dominated alternatives must route to Debate.

The following sources are not directly admissible as project-level causal state:

- `debate_worker_local`: local Debate Worker causal state used for debate quality.
- `ordinary_execution_detail`: local implementation reasoning that does not affect project direction.
- `test_route_evidence_only`: Test route evidence without causal construction.
- unsupported developer assertion.

If Master cannot determine a unique conclusion, or if a proposal declares multiple plausible solution paths, the admission decision must route to Debate instead of accepting a project-level causal candidate.

## 6. Master second review

A Debate Leader final causal chain does not directly become global truth.

```text
Debate Worker local causal state
  -> Debate Leader adjudicated causal chain
  -> Master structural admission review
  -> staged Causal candidate
  -> future high-budget Causal Review / merge phase
```

Master also has a separate unique-conclusion path:

```text
Master unique / near-unique conclusion
  -> Master constructs Causal candidate
  -> Master structural admission review
  -> staged Causal candidate
  -> future high-budget Causal Review / merge phase
```

No Phase 22A path writes canonical/global causal truth.

No Phase 22A path performs production Causal Store mutation.

Phase 22A ends at admission decision. It must not perform the later global causal merge.

## 7. Admission decisions

Allowed Phase 22A decisions:

```text
accept_archive_candidate
accept_knowledge_candidate
stage_causal_candidate
reject_wrong_store
reject_insufficient_evidence
reject_direct_global_write
reject_local_only_causal
needs_more_evidence
needs_debate
needs_master_structural_admission_review
```

`stage_causal_candidate` must carry a required next step:

```text
future_high_budget_causal_review_before_global_merge
```

## 8. Forbidden actions

Phase 22A must not:

- create a fifth department
- create a long-lived State Admission Agent
- let ordinary agents directly write Archive, Knowledge, or Causal stores
- expose Archive as ordinary agent context
- write unsupported developer claims into Knowledge
- write bare conclusions into Causal
- promote Archive directly to Knowledge or Causal
- promote Knowledge directly to Causal without causal construction
- merge active global Causal truth
- perform production storage, encryption, release, push, PR, merge, or deployment

## 9. Summary

```text
Three-store admission is Master-owned governance.
Archive records history; it does not produce truth.
Knowledge stores verified facts and constraints; it does not store causal reasoning.
Causal stores reusable causal structures; Phase 22A admits candidates only.
```
