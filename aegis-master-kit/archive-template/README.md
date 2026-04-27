# Aegis Archive Template

`archive-template` defines how Master creates and maintains a project-level Archive.

It is a template and governance contract set. It is not a project archive instance.

## Core definition

```text
Archive = Master-maintained encrypted project audit ledger.
```

Archive records:

- where a task came from
- when it was created, admitted, started, blocked, completed, aborted, superseded, or reopened
- who carried real-world responsibility
- which agents participated
- what critical discussions and confirmations happened
- what decisions were made
- which stage artifacts were produced
- what final outcome was accepted
- what follow-up work remains

Archive does not decide truth.

```text
Archive   = what happened
Knowledge = what is verified as stable fact or constraint
Causal    = why/evidence/scope/assumptions causal truth
```

## Terminal completion gate

A task must not enter terminal status `completed` unless all required terminal records exist.

For completed tasks, Master must require at minimum:

- `lifecycle.completed_at`
- final decision or accepted outcome
- required stage artifact references, or explicit waiver amendment
- `outcome.verification_summary`
- `outcome.known_limits`
- postmortem reference
- valid outcome block

If these records are missing, the completed state is invalid. Master must reject terminal closure until the required records or an explicit waiver amendment exist.

## Audit continuity boundary

Archive is not an ordinary execution dependency for task agents. Ordinary task execution must not directly depend on Archive.

If Archive is missing, seal is broken, rollback is suspected, encrypted payload is invalid, or integrity continuity is unknown, Master must stop project governance actions that require Archive audit continuity. Master must not treat the local Archive as current or trusted until recovery, bootstrap, or escalation resolves the continuity issue.

## Two forms

```text
aegis-master-kit/archive-template/
  Generic template held by Master.
  It contains contracts, schemas, repo-layout templates, demos, and checks.

project-root/archive/
  Concrete encrypted project Archive instance created by Master from this template.
  It is unique inside one project.
```

## Security model

The concrete project Archive must be encrypted at rest.

The project repository may contain:

- encrypted archive payload
- non-sensitive public metadata
- opaque public seal records
- non-sensitive generated indexes

The project repository must not contain:

- archive plaintext
- decryption material
- integrity secret
- proof-generation internals
- reproducible private verification procedure

Master is the only authority that may decrypt, update, seal, and validate Archive.

Developer may request Archive changes, but must not directly mutate Archive records.

## Read order

```text
1. contracts/ARCHIVE_CONTRACT.md
2. contracts/ARCHIVE_BOOTSTRAP_CONTRACT.md
3. contracts/ARCHIVE_AUTHORITY_CONTRACT.md
4. contracts/ARCHIVE_SECURITY_CONTRACT.md
5. contracts/ARCHIVE_TASK_DOSSIER_CONTRACT.md
6. contracts/ARCHIVE_AMENDMENT_CONTRACT.md
7. contracts/ARCHIVE_INDEX_CONTRACT.md
8. contracts/ARCHIVE_SEALING_CONTRACT.md
9. contracts/ARCHIVE_CONSISTENCY_CHECK.md
10. schemas/*.schema.yaml
11. templates/project_archive_repo/
12. templates/master_plaintext_payload/
13. demos/
```

## What is intentionally deferred

This template does not define how each future department contributes records into Archive.

That must be defined later when department-level modules are designed. For now, Archive is maintained directly by Master.
