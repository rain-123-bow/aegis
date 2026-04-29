# PHASE 9 Double-Crypto Hardening Report

## Phase Name

PHASE 9: Real double-crypto runtime hardening.

## Final Classification

REAL_DOUBLE_CRYPTO_RUNTIME_IMPLEMENTED

FULL_PRODUCTION_KEY_LIFECYCLE_STILL_FUTURE_WORK

## Exact Scope

Implemented a real double-crypto runtime path for route envelopes:

- Outer layer: Ed25519 sender identity signing and router-side verification.
- Inner layer: RSA-OAEP with SHA-256 receiver-only path encryption and receiver-side decryption.
- Preserved existing directed topology enforcement, role-local route derivation, mailbucket behavior, cleanup behavior, governance hooks, and dev/test compatibility.

This phase does not implement full production key lifecycle, key rotation, certificate chains, remote trust infrastructure, hardware-backed keys, payload encryption, Archive/Knowledge/Causal admission, debate reasoning, evidence sufficiency judgment, dynamic topology loading, JSON store locking, or MCP caller/session binding.

## Files Changed

- `aegis-router/pyproject.toml`
- `aegis-router/aegis_router/__init__.py`
- `aegis-router/aegis_router/core.py`
- `aegis-router/aegis_router/path_resolution.py`
- `aegis-router/tests/test_crypto_completeness_classification.py`
- `aegis-router/tests/test_real_double_crypto_protocol.py`
- `runtime_test_reports/PHASE_9_DOUBLE_CRYPTO_HARDENING_REPORT.md`

## Dependency Decision

The instruction required a real cryptographic implementation and preferred `cryptography`.

Decision:

- Added `cryptography>=47.0.0` as a runtime dependency in `pyproject.toml`.
- Installed `cryptography 47.0.0` into the local router virtual environment for testing.
- No custom cryptographic primitive was implemented.

## Algorithms Used

- Sender identity signing: Ed25519.
- Receiver-only path encryption: RSA-OAEP with SHA-256.
- Existing dev/test mode remains available as `aegis-dev-hmac-sha256`.
- Existing dev/test path token mode remains available as `aegis-dev-path-token:v1:<token>`.

## Key Registry Shape

Agent metadata may contain two independent public-key registries:

```python
metadata = {
    "identity_public_keys": {
        "identity-ed25519-1": {
            "alg": "ed25519",
            "public_key": "<PEM Ed25519 public key>"
        }
    },
    "path_public_keys": {
        "path-rsa-oaep-1": {
            "alg": "rsa-oaep-sha256",
            "public_key": "<PEM RSA public key>"
        }
    }
}
```

Private keys are not stored by the router. Tests generate private keys in memory only.

## Envelope Canonical Signature Material

The router verifies signatures over this exact canonical material:

```text
sender | receiver | path | nonce | timestamp
```

The implementation joins those five values with `|` and encodes the result as UTF-8 bytes before Ed25519 verification.

## Path Encryption Token Format

The real encrypted path token format is:

```text
aegis-rsa-oaep-sha256:v1:<receiver_path_key_id>:<base64_ciphertext>
```

The router treats this value as an opaque string. Receiver-side path resolution parses and decrypts it using the receiver private path key.

## Runtime Behavior Added

- Added `aegis-ed25519-v1` route envelope auth support.
- Router loads the sender Ed25519 public identity key from `metadata.identity_public_keys`.
- Router rejects missing sender public key, wrong key ID, wrong algorithm, forged signature, and modified signed fields.
- Router preserves replay nonce rejection and stale/future timestamp rejection.
- Added RSA-OAEP encrypted path token creation helper.
- Added receiver-side RSA-OAEP path decryption and root-safety validation.
- Receiver-side helper rejects malformed tokens, wrong private keys, tampered ciphertext, outside-root decrypted paths, and traversal paths.
- Router still never decrypts `path`, never reads README.md, never reads attachments, and never performs Archive/Knowledge/Causal admission.

## Tests Changed

Added `aegis-router/tests/test_real_double_crypto_protocol.py` covering:

1. real Ed25519 signed route envelope accepted on a valid directed edge;
2. forged sender signature rejected;
3. missing registered sender public key rejected;
4. wrong `auth.key_id` rejected;
5. modifying `sender` invalidates signature;
6. modifying `receiver` invalidates signature;
7. modifying encrypted `path` invalidates signature;
8. modifying `nonce` invalidates signature;
9. modifying `timestamp` invalidates signature;
10. replayed nonce rejected;
11. stale timestamp rejected;
12. receiver decrypts real encrypted path with the correct private key;
13. wrong receiver private key cannot decrypt path;
14. tampered path ciphertext cannot decrypt;
15. decrypted outside-root path rejected;
16. decrypted traversal path rejected;
17. router stored/forwarded envelope does not contain decrypted path;
18. router state has no receiver private path key;
19. README.md and attachments remain unread by router;
20. strict topology rejects invalid edge even with valid crypto;
21. valid crypto does not imply payload truth or causal admission.

Updated `aegis-router/tests/test_crypto_completeness_classification.py` so it now classifies:

- dev/test HMAC mode remains explicitly development scoped;
- real Ed25519 + RSA-OAEP runtime path is present;
- full key lifecycle remains future work.

## Tests Run

Command:

```powershell
cd C:\Users\playm\Documents\self-git\aegis\aegis-router
.\.venv\Scripts\python.exe -m pytest
```

Exact output:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-router
configfile: pyproject.toml
testpaths: tests
collected 142 items

tests\test_crypto_completeness_classification.py .....                   [  3%]
tests\test_governance_hooks.py ..............                            [ 13%]
tests\test_mailbucket_protocol.py ........................               [ 30%]
tests\test_mcp_server.py ...                                             [ 32%]
tests\test_real_double_crypto_protocol.py .....................          [ 47%]
tests\test_router_core.py .......                                        [ 52%]
tests\test_top_level_route_protocol.py ...................               [ 65%]
tests\test_topology_exhaustive_enforcement.py .......................... [ 83%]
.......................                                                  [100%]

============================ 142 passed in 11.82s =============================
```

Prior tests still pass.

## Remaining Gaps

The following items remain future work and do not block Phase 9:

- full key lifecycle;
- key rotation;
- hardware-backed keys;
- remote trust model;
- certificate chain;
- payload/content encryption for README.md and attachments;
- nonce TTL garbage collection;
- dynamic topology YAML loading;
- MCP caller/session binding;
- JSON store locking;
- real Archive / Knowledge / Causal admission.

## Ambiguity

No ambiguity blocked this phase. The instruction required real cryptography and named preferred algorithms; `cryptography` was available after installation, so implementation proceeded with Ed25519 and RSA-OAEP/SHA-256.

## Safety Statement

- No push was performed.
- No merge was performed.
- No pull request was created.
- No commit was created.
- No generated private key was added to the repository.
- No private key material was stored in repo-visible files.
- Test private keys are generated in memory.
- No runtime state, temporary mailbucket folder, `.venv`, `.pytest_cache`, `__pycache__`, or `.pyc` file was added to git status.
- Existing topology tests were not removed or bypassed.
- The router still does not decrypt receiver-only paths.
- The router still does not inspect README.md or attachments.
- The router still does not mutate Archive, Knowledge, or Causal stores.
