# Archive Consistency Check

## 1. Purpose

This document defines the minimum checks Master must apply when validating a project Archive.

## 2. Structural checks

Master must check:

1. `archive_manifest.yaml` exists.
2. `encrypted/archive_payload.bin` exists or Archive is explicitly `bootstrap_pending`.
3. `public/archive_public_manifest.yaml` exists.
4. `integrity/` exists.
5. no plaintext task dossier directory is committed into repo-visible `archive/`.
6. no obvious key/secret/proof-internal file is committed.
7. public indexes exist or are marked as pending.

## 3. Security checks

Master must check:

1. encrypted payload can be opened in Master-controlled runtime.
2. local public root token matches Master-generated state.
3. seal chain is continuous.
4. local state is a successor of latest trusted seal.
5. public ledger sequence has no unexpected gap.
6. no repo-visible plaintext leak exists.
7. no developer-authored direct mutation is accepted as valid.

If Archive is missing, seal is broken, rollback is suspected, encrypted payload is invalid, or integrity continuity is unknown, Master must stop project governance actions that require Archive audit continuity. Master must not treat the local Archive as current or trusted until it is recovered, bootstrapped, or escalated.

This does not make Archive an ordinary execution dependency for task agents. Ordinary task execution must not directly depend on Archive history.

## 4. Plaintext leak checks

Repo-visible Archive must not contain:

```text
archive/tasks/
archive/plaintext/
archive/plaintext_payload/
archive/master_plaintext_payload/
archive/**/*.secret
archive/**/*.key
archive/**/decryption*
archive/**/private_proof*
```

If such content appears, Master must report `plaintext_leak_detected` or `secret_leak_detected`.

## 5. Dossier checks after decrypt

After successful Master-side decrypt, Master must check:

1. every task has `task.yaml`.
2. every task has `task_source`.
3. every task has lifecycle timestamps appropriate to its status.
4. terminal tasks have outcome.
5. completed tasks have `lifecycle.completed_at`.
6. completed tasks have a final accepted decision or accepted outcome.
7. completed tasks have required stage artifact references or explicit waiver amendment refs.
8. completed tasks have `outcome.verification_summary`.
9. completed tasks have `outcome.known_limits`.
10. completed tasks have postmortem unless explicitly waived by amendment.
11. timeline refs resolve.
12. decision refs resolve.
13. artifact refs resolve.
14. amendments refer to existing targets.
15. promoted Knowledge/Causal refs are references only.

If a task is marked `completed` and any required terminal record is missing, completed state is invalid. Master must block or reject terminal closure until required records or waiver amendment exist. If it was already marked completed, Master must reopen it or record a waiver amendment before accepting terminal state.

## 6. Index checks

Indexes are generated.

If index mismatch occurs and payload/seal are valid, regenerate indexes and record repair.

If index mismatch occurs with seal failure, treat as integrity violation.

## 7. Violation states

Master may report:

```text
archive_missing
payload_missing
payload_decrypt_failed
public_manifest_missing
public_root_mismatch
seal_missing
seal_broken
seal_not_successor
ledger_gap
rollback_suspected
unauthorized_mutation_suspected
plaintext_leak_detected
secret_leak_detected
index_corrupted
```
