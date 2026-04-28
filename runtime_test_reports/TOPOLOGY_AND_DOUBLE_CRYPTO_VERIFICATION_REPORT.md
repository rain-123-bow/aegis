# Topology and Double-Crypto Verification Report

## Verification Name

Strict top-level topology and double-crypto completeness verification.

## Repository Branch / Ref Tested

- Branch: `v0.1.0-alpha`
- HEAD: `3e7c068`

## Files Inspected

- `README.md`
- `docs/ROUTER_DESIGN.md`
- `aegis-master-kit/organization/ORGANIZATION_MODEL.md`
- `aegis-master-kit/organization/topologies/master_top_level_v1.yaml`
- `aegis-master-kit/organization/contracts/TOP_LEVEL_ROUTE_TOPOLOGY_CONTRACT.md`
- `aegis-master-kit/organization/contracts/ROUTE_ENVELOPE_AND_MAILBUCKET_CONTRACT.md`
- `aegis-router/aegis_router/core.py`
- `aegis-router/aegis_router/models.py`
- `aegis-router/aegis_router/server.py`
- `aegis-router/aegis_router/path_resolution.py`
- `aegis-router/aegis_router/mailbucket.py`
- `aegis-router/tests/test_top_level_route_protocol.py`
- `aegis-router/tests/test_mailbucket_protocol.py`
- `aegis-router/tests/test_governance_hooks.py`
- `runtime_test_reports/PHASE_1_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_2_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_3_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_4_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_5_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_6_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_7_IMPLEMENTATION_REPORT.md`
- `runtime_test_reports/PHASE_8_IMPLEMENTATION_REPORT.md`

No required file was missing.

## Tests Added or Changed

Added:

- `aegis-router/tests/test_topology_exhaustive_enforcement.py`
- `aegis-router/tests/test_crypto_completeness_classification.py`

No production runtime code was changed.

## Tests Run

Command:

```powershell
cd C:\Users\playm\Documents\self-git\aegis\aegis-router
.\.venv\Scripts\python.exe -m pytest
```

Exact final output:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\playm\Documents\self-git\aegis\aegis-router
configfile: pyproject.toml
testpaths: tests
collected 121 items

tests\test_crypto_completeness_classification.py .....                   [  4%]
tests\test_governance_hooks.py ..............                            [ 15%]
tests\test_mailbucket_protocol.py ........................               [ 35%]
tests\test_mcp_server.py ...                                             [ 38%]
tests\test_router_core.py .......                                        [ 43%]
tests\test_top_level_route_protocol.py ...................               [ 59%]
tests\test_topology_exhaustive_enforcement.py .......................... [ 80%]
.......................                                                  [100%]

============================= 121 passed in 0.86s =============================
```

## Git Checks

Command:

```powershell
git diff --check
```

Result: passed with no output.

Line-ending scan:

```text
NO_CRLF aegis-router/tests/test_topology_exhaustive_enforcement.py
NO_CRLF aegis-router/tests/test_crypto_completeness_classification.py
```

## Strict Topology Verification Result

TOPOLOGY_HARD_ENFORCEMENT_PASS

The runtime mechanically enforces the documented top-level directed graph.

## Exhaustive Route Matrix Summary

The new matrix test covers all 25 sender/receiver role pairs for:

```text
master
debate
execution
test
final_review
```

Only the 10 documented directed edges pass:

```text
master -> debate
master -> execution
debate -> master
execution -> test
test -> final_review
final_review -> master
test -> execution
execution -> debate
debate -> execution
execution -> master
```

All other role pairs fail, including self-send pairs.

Additional topology checks passed:

- same-domain visibility does not imply send permission;
- protocol pairs do not become unrestricted bidirectional chat channels;
- `route_envelope` cannot bypass directed-edge enforcement;
- deactivated agents cannot send;
- unregistered/cross-domain paths cannot bypass topology enforcement.

## Governance Type Matrix Summary

The new governance matrix verifies:

- all allowed edge/type pairs pass;
- a disallowed governance message type on a valid edge fails;
- a valid governance message type on an invalid edge fails.

Allowed edge/type pairs verified:

```text
master -> debate:
  debate_request, status_update

master -> execution:
  execution_request, status_update

debate -> master:
  debate_result, escalation, status_update

execution -> test:
  implementation_candidate, status_update

test -> final_review:
  test_result, status_update

final_review -> master:
  final_review_result, status_update

test -> execution:
  failure_feedback, status_update

execution -> debate:
  adjudication_request, status_update

debate -> execution:
  adjudication_result, status_update

execution -> master:
  causal_fork_submission, governance_blocker, status_update
```

The router validates only edge/type structure. It does not judge debate quality, causal truth, evidence sufficiency, final review correctness, README truth, or attachment meaning.

## MCP Bypass Verification Summary

MCP `tools/call/send_message` cannot bypass core constraints for the checked cases.

Verified:

- direct `Router.send_message()` rejects `master -> test`;
- MCP `send_message` also rejects `master -> test`;
- direct `Router.send_message()` rejects `execution -> master` with `test_result`;
- MCP `send_message` also rejects `execution -> master` with `test_result`.

MCP and direct Router behavior are consistent for these topology and governance rejection paths.

## Double-Crypto Verification Result

DOUBLE_CRYPTO_NOT_COMPLETE

The runtime has a two-layer structural protection interface, but not a real two-layer crypto mechanism.

## Implemented Crypto / Protection Mechanisms

Implemented structural protections:

- Envelope shape validation.
- Development/test sender authentication and integrity:

```text
aegis-dev-hmac-sha256
```

- Signature coverage over:

```text
sender | receiver | path | nonce | timestamp
```

- Replay nonce rejection.
- Timestamp replay window.
- Development/test protected path token:

```text
aegis-dev-path-token:v1:<token>
```

- Receiver-side resolver that maps the dev token to a path and validates it stays under the shared mailbucket root.
- Auth tampering tests prove changing the opaque path invalidates the sender auth signature.

## Missing Crypto Mechanisms

Sender identity / outer layer:

- No real public/private identity signing is implemented.
- No Ed25519 or equivalent public-key signature is implemented.
- Agents do not have registered public identity keys in the production cryptographic sense.
- Router verification uses a dev/test HMAC secret from metadata, not a sender public key.
- Router avoids generated private key storage because no production key lifecycle exists.
- Replayed nonces are rejected, but nonce TTL/cleanup is not implemented; nonce records can grow.

Receiver-only path confidentiality / inner layer:

- Path is not encrypted with the receiver public key.
- There is no receiver private-key decryption path.
- Another party with resolver material can resolve the token.
- The router does not decrypt the path, but this is because the current path is an opaque token, not encrypted ciphertext.
- The dev path token is resolver indirection, not encryption.

Payload/content encryption:

- README.md and attachments are plain local files under the mailbucket folder.
- Payload/content encryption is not implemented.
- Current contract phases treat content encryption as out of scope.

## Temporary Local Lightweight Mode Classification

The current dev/test protection model is acceptable only as a temporary local lightweight mode for runtime contract validation.

It is not acceptable as a production double-crypto security model because it lacks:

- public-key sender signatures;
- receiver-only path encryption;
- receiver private-key path decryption;
- production key lifecycle;
- nonce garbage collection;
- payload/content encryption, if future threat models require it.

## Recommended Next Step

Create a separate production crypto hardening phase.

Minimum recommended scope:

- Ed25519 or equivalent sender identity signing.
- Registered sender public identity keys.
- Router signature verification using sender public keys only.
- Receiver public-key path encryption.
- Receiver private-key path decryption helper outside router.
- Router remains unable to decrypt `path`.
- Nonce TTL cleanup.
- Explicit decision on whether README.md and attachments remain plaintext in local mailbucket mode or require content encryption.

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- No production crypto was implemented.
- No key generation was performed.
- No private keys were added.
- No mailbucket runtime data was added.
- No Archive / Knowledge / Causal mutation was performed.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, generated keys, or temporary mailbucket folders were added.
