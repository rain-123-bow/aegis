# Archive Sealing Contract

## 1. Purpose

Sealing makes Archive mutations auditable.

A seal records that Master accepted a particular Archive state transition.

## 2. Seal trigger events

Archive v1 should create a seal after:

- archive bootstrap
- task created
- task admitted
- task started
- contract frozen
- design accepted
- review completed
- verification completed
- task completed
- task aborted
- task superseded
- amendment added
- integrity repair completed

## 3. Seal content

A repo-visible seal record must contain only public and opaque fields.

Example shape:

```yaml
seal_id: S20260427-001
project_id: <project id>
archive_id: <archive id>
archive_version: v1
payload_version: 12
previous_seal_ref: <previous seal id or null>
public_root_token: <opaque Master-generated value>
ledger_seq_from: 1
ledger_seq_to: 12
sealed_at: <timestamp>
sealed_by: <master id>
verification_state: sealed
master_private_proof: <opaque value>
```

The contract intentionally does not define private cryptographic implementation details in repo-visible files.

## 4. Seal validation result

Master may report only:

```text
verified
mismatch
missing_proof
decrypt_failed
seal_broken
seal_not_successor
rollback_suspected
unauthorized_mutation_suspected
```

Master must not disclose private proof construction.

## 5. Seal succession

Each valid seal must reference the previous trusted seal unless it is the first bootstrap seal.

If a local repo state has a valid-looking old seal but is not the latest trusted successor known by Master, Master must report rollback suspected.

## 6. Public ledger

`integrity/ledger_public.jsonl` may contain append-only public summaries.

It is not the private verification source.

If public ledger and Master private seal chain disagree, Master private seal chain governs.
