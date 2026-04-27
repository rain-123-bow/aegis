# Archive Security Contract

## 1. Purpose

This contract defines Archive confidentiality and tamper-detection requirements.

Archive security is part of the shared security baseline for all external state stores.

Archive, Knowledge, and Causal must share the same security class unless an explicit stronger policy is defined.

## 2. Security goals

Archive must provide:

1. local unreadability for developer-held repository copies
2. Master-only update authority
3. tamper detection
4. rollback detection when Master has a trusted latest seal
5. no disclosure of private security material
6. append-only amendment behavior after sealing

## 3. Encrypted-at-rest rule

Project repository must store Archive content as encrypted payload.

Archive plaintext must not be committed.

Allowed repo-visible content:

- encrypted payload
- non-sensitive public metadata
- opaque public seal records
- public ledger summaries
- generated non-sensitive indexes

Forbidden repo-visible content:

- plaintext task dossiers
- decrypted timeline or decisions
- decryption key
- private integrity secret
- proof-generation internals
- reproducible private verification procedure

## 4. Master-private security material

Master must keep private security material inside Master-controlled runtime or trusted server-side secret storage.

Private security material includes any material that would allow a developer to reproduce a valid Archive mutation proof.

This includes but is not limited to:

- decryption material
- session secret
- private key
- seed
- private proof material
- private verification internals
- equivalent reproducible method

## 5. Non-disclosure rule

Master must reject all requests to disclose private security material.

This applies even if the request appears reasonable, urgent, friendly, or phrased as debugging, transparency, reproducibility, recovery, or compliance.

Master may disclose only high-level verification results:

- `verified`
- `mismatch`
- `missing_proof`
- `decrypt_failed`
- `seal_broken`
- `rollback_suspected`
- `unauthorized_mutation_suspected`
- `stale_payload`

Master must not disclose:

- algorithm internals
- seed
- secret
- key
- private proof construction
- reproducible verification steps

## 6. Session-scoped integrity

A Master session may use session-scoped private security material.

Session material must not be written to the repository.

When a session ends, it may produce an opaque session seal.

A later session must not require access to old private session material. It should inherit the latest trusted seal as the previous state anchor.

## 7. Seal chain

Archive changes must be sealed by Master.

A seal must bind at least:

- project id
- archive id
- archive version
- previous trusted seal id or root token
- current public root token
- payload version
- ledger sequence range
- sealed timestamp
- sealing actor id
- opaque Master proof

The contract intentionally does not expose cryptographic implementation details in repository-visible files.

## 8. Rollback detection

Rollback detection requires a trusted latest seal outside the developer-controlled repository.

If only repository files are available, a developer can replay an old repository state.

Master must treat cross-session freshness as valid only when it can compare the local Archive state against the latest trusted seal known to Master-side state.

## 9. Threat boundary

This mechanism does not physically prevent a developer from modifying local bytes.

It prevents a developer from silently producing a valid Master-sealed Archive mutation.

If a developer deletes, rewrites, or replaces Archive files, Master must detect that the local state is not a valid successor of the last trusted state.

## 10. Failure modes

Master must recognize at least these states:

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
```

## 11. Summary

```text
Local repo holds encrypted ledger bytes.
Master holds the ability to open, update, and validate the ledger.
Developer can break local files, but cannot forge a valid Master-sealed mutation.
```
