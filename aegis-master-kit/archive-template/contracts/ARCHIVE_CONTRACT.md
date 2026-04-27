# Archive Contract

## 1. Purpose

Archive is the project-level task history and responsibility ledger.

It records events, responsibility, decisions, artifacts, amendments, and outcomes.

It does not produce truth.

## 2. System position

Archive is one of the three external state stores:

```text
Archive   = what happened
Knowledge = verified static facts and constraints
Causal    = causal truth with why/evidence/scope/assumptions
```

Archive belongs to the project instance, not to `aegis-master-kit`.

`aegis-master-kit` stores only the Archive template and governance rules.

## 3. Project uniqueness

One project must have exactly one Archive unless the project is explicitly split into separate projects.

Default path:

```text
/project-root/archive
```

## 4. Ownership

Archive is created and maintained by Master.

Ordinary agents do not directly depend on Archive during task execution.

Archive is not an ordinary execution dependency for task agents. Ordinary task execution must not directly depend on Archive history. Master may issue selected constraints, Knowledge, Causal facts, or artifact references when a governed retrieval path is needed.

Developer may submit Archive update requests, evidence, corrections, and objections, but must not directly edit Archive records.

## 5. Non-truth rule

Archive entries are historical records.

They may prove that something was requested, discussed, attempted, observed, accepted, rejected, or completed.

They do not prove that archived claims are true.

An archived statement must not be treated as Knowledge or Causal truth without passing the corresponding external-state admission policy.

## 6. Core semantic capabilities

Archive v1 must support:

1. task source records
2. task lifecycle records
3. responsibility records
4. timeline records
5. decision records
6. stage artifact records
7. final outcome records
8. amendment records
9. generated indexes
10. integrity/seal records

## 7. Minimal task dossier fields

Every task dossier must include:

- `task_id`
- `title`
- `status`
- `task_source`
- `lifecycle`
- `responsibility`
- `scope`
- `success_criteria`
- `timeline_refs`
- `decision_refs`
- `artifact_refs`
- `terminal_completion_gate`
- `outcome`

Completed tasks have a stricter terminal completion gate. A task must not enter `completed` unless all required terminal records exist:

- `lifecycle.completed_at`
- final decision or accepted outcome
- required stage artifact references, or explicit waiver amendment
- `outcome.verification_summary`
- `outcome.known_limits`
- postmortem reference
- valid outcome block

If any required terminal record is missing, completed state is invalid. Master must reject terminal closure until the required records or a waiver amendment exist.

## 8. Non-goals

Archive v1 must not become:

- a general knowledge base
- a causal truth store
- a normal agent runtime context
- a source-code ownership database
- a natural-language dump of all conversations
- a developer-editable notes folder

## 9. Promotion boundary

Archive may reference promoted assets:

```yaml
promoted_to_knowledge:
  - K0001
promoted_to_causal:
  - F0001
```

But Archive does not perform promotion by itself.

Promotion must pass Knowledge or Causal admission rules.

## 10. Summary

```text
Archive is a Master-maintained encrypted audit ledger.
It records project task history and responsibility.
It does not produce truth.
It is not a direct execution dependency for ordinary agents.
```
