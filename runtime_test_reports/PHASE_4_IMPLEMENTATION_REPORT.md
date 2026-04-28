# Phase 4 Implementation Report

## Phase Name

PHASE 4: Identity key registry and Envelope v1 auth verification.

## Exact Scope

Implemented sender authentication for `message_type == "route_envelope"` only.

In scope:

- Validate Envelope v1 `auth` fields.
- Verify sender identity using a registered sender identity key.
- Verify the signature covers `sender`, `receiver`, `path`, `nonce`, and `timestamp`.
- Reject replayed nonces.
- Reject stale timestamps outside the replay window.
- Preserve the router meaning-free boundary.

Out of scope:

- Receiver-side path decryption.
- Encrypted path implementation.
- Mailbucket shared root.
- README validation.
- Mailbucket cleanup.
- Causal governance.
- Archive / Knowledge / Causal admission.
- Business payload interpretation.

## Files Changed

Runtime:

- `aegis-router/aegis_router/core.py`

Tests:

- `aegis-router/tests/test_top_level_route_protocol.py`
- `aegis-router/tests/test_mailbucket_protocol.py`

Report:

- `runtime_test_reports/PHASE_4_IMPLEMENTATION_REPORT.md`

## Runtime Behavior Added

`Router.send_message()` now performs auth verification after the existing checks for:

- Envelope v1 shape.
- Registered active sender/receiver.
- Same-domain routing.
- Directed top-level route permission.

For route envelopes, `auth` must contain:

- `alg`
- `key_id`
- `nonce`
- `timestamp`
- `signature`

The implementation supports:

```text
aegis-dev-hmac-sha256
```

This is a deterministic development/test authentication abstraction built from Python standard-library HMAC-SHA256. It avoids adding a new runtime dependency in this phase. It is not presented as production public-key cryptography and does not implement Ed25519.

Identity keys are read from agent metadata:

```text
metadata.dev_identity_keys
```

`metadata.identity_keys` is also accepted for compatibility with simple registry fixtures.

The signature material is:

```text
sender|receiver|path|nonce|timestamp
```

Replay protection records used nonces in router state under:

```text
route_envelope_replay_nonces
```

Auth success proves only:

- the envelope matched the registered sender identity key for the configured dev/test auth algorithm;
- the signed routing fields were not modified;
- the nonce was not replayed inside the local router state.

Auth success does not prove:

- payload truth;
- causal validity;
- Archive / Knowledge / Causal admission;
- receiver path readability;
- mailbucket folder validity.

The router still does not decrypt `path`, read README files, inspect attachments, or judge message semantics.

## Dependency Result

No dependency was added.

The Phase 4 implementation uses only Python standard-library modules:

- `base64`
- `hashlib`
- `hmac`
- `datetime`

## Tests Changed

Converted these Phase 4 xfail tests to normal passing tests:

- `test_contract_forged_sender_identity_is_rejected`
- `test_contract_auth_covers_path_nonce_and_timestamp`

Added one direct Phase 4 replay test:

- `test_contract_replayed_nonce_is_rejected`

Added four direct Phase 4 boundary tests required by the complete instruction:

- `test_contract_signature_covers_sender_receiver_path_nonce_and_timestamp`
- `test_contract_missing_auth_fields_are_rejected`
- `test_contract_sender_without_registered_auth_material_is_rejected`
- `test_contract_stale_and_future_timestamps_are_rejected`

Updated existing top-level route tests to register dev identity keys and send signed route envelopes, so Phase 1 and Phase 2 continue testing route semantics under the Phase 4 auth requirement.

Kept future-phase xfails intact:

- `test_contract_router_owns_shared_mailbucket_root`
- `test_contract_mailbucket_folder_requires_readme`
- `test_contract_mailbucket_cleanup_exists_and_preserves_private_copies`

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
collected 43 items

tests\test_mailbucket_protocol.py ...........xxx                         [ 32%]
tests\test_mcp_server.py ...                                             [ 39%]
tests\test_router_core.py .......                                        [ 55%]
tests\test_top_level_route_protocol.py ...................               [100%]

======================== 40 passed, 3 xfailed in 0.34s ========================
```

Repository checks:

```powershell
git diff --check
git status --short
```

`git diff --check` result: passed with no output.

`git status --short` result:

```text
 M aegis-master-kit/organization/ORGANIZATION_MODEL.md
 M aegis-router/aegis_router/core.py
 M aegis-router/aegis_router/server.py
 M aegis-router/pyproject.toml
 M docs/ROUTER_DESIGN.md
?? aegis-master-kit/organization/contracts/
?? aegis-master-kit/organization/topologies/master_top_level_v1.yaml
?? aegis-router/tests/test_mailbucket_protocol.py
?? aegis-router/tests/test_top_level_route_protocol.py
?? runtime_test_reports/
```

Line-ending scan for Phase 4 edited files:

```text
NO_CRLF aegis-router/aegis_router/core.py
NO_CRLF aegis-router/tests/test_top_level_route_protocol.py
NO_CRLF aegis-router/tests/test_mailbucket_protocol.py
```

## Xfail Count Before and After

- Before Phase 4: `33 passed, 5 xfailed`
- After Phase 4: `40 passed, 3 xfailed`

Phase 4 removed two expected auth/signature failures and added five passing Phase 4 boundary checks. Four of those checks were added after reviewing the complete Phase 4 instruction because the earlier report did not explicitly prove missing auth fields, all signed field mutations, absent registered auth material, and timestamp-window rejection.

## Remaining Gaps

Still intentionally not implemented:

- Production public-key identity verification such as Ed25519.
- Receiver-only encrypted path handling.
- Receiver-side path resolution.
- Router-owned shared mailbucket root.
- Mailbucket folder creation flow.
- README validation.
- Mailbucket cleanup grace period.
- Governance message hooks.

## Ambiguity

No blocking ambiguity for Phase 4 runtime tests.

The contract prefers Ed25519 when a suitable library is already available or minimally justified. No existing cryptography dependency was present, and this phase stayed within the standard library by using a clearly named dev/test auth abstraction. Production-grade public-key identity signing remains a future hardening gap if the project requires real cryptographic security.

The complete instruction required canonical serialization to be documented if not already defined by tests or contract. The code now documents the deterministic order used by Phase 4:

```text
sender|receiver|path|nonce|timestamp
```

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- No path encryption was implemented.
- No receiver-side path decryption was implemented.
- No mailbucket shared root was implemented.
- No README or attachment inspection was implemented.
- No cleanup behavior was implemented.
- No causal governance behavior was implemented.
- No Archive / Knowledge / Causal write behavior was implemented.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, temporary mailbucket data, generated private keys, or private key material were added.

PHASE 4 PASSED. Waiting for developer approval before next phase.
