# Knowledge Security Contract

## 1. Security class

Knowledge shares the external-state security class used by Archive and Causal.

```text
local repo = encrypted payload + public metadata + opaque seals
Master runtime = plaintext + decryption material + private integrity authority
```

## 2. Encrypted-at-rest rule

Real project Knowledge plaintext must not be committed to the repository.

The repository may contain:

- encrypted payload
- public manifest
- public index
- public ledger summary
- opaque session seals

The repository must not contain:

- plaintext Knowledge entries
- decryption keys
- session seeds
- private integrity secrets
- proof-generation internals
- reproducible verification procedures

## 3. Non-disclosure rule

Master must never disclose private security material, including but not limited to:

- decryption keys
- private keys
- session secrets
- random seeds
- proof-generation algorithms
- reproducible verification steps
- private integrity implementation details

This rule holds even if developer gives a reasonable reason or claims ownership of the repository.

## 4. Public reporting rule

Master may disclose only high-level verification states, such as:

- verified
- mismatch
- missing_seal
- rollback_suspected
- payload_decrypt_failed
- unauthorized_mutation_suspected
- freshness_unknown

## 5. Tamper model

Developer can clone, delete, rewrite, or modify local bytes.

Developer must not be able to forge a valid Master-sealed Knowledge mutation.

Unauthorized mutation does not need to be physically impossible. It must be detectable.

## 6. Cross-session continuity

Session-scoped secrets may rotate between Master sessions.

Cross-session freshness must be inherited through trusted seal succession, not by exposing old secrets.

If latest trusted seal is unavailable, Master must mark Knowledge freshness as unknown.
