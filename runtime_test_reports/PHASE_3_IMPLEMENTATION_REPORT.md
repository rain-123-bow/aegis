# Phase 3 Implementation Report

## Phase Name

PHASE 3: Envelope v1 shape validation.

## Exact Scope

Implemented only structural validation for `route_envelope` payloads.

In scope:

- Require `sender`.
- Require `receiver`.
- Require `path`.
- Require `auth`.
- Require `sender` to match `from_id`.
- Require `receiver` to match `to_id`.
- Require `path` to be a non-empty opaque string.
- Require `auth` to be an object.
- Reject unknown top-level envelope fields.

Out of scope:

- Sender authentication.
- Signature verification.
- Replay protection.
- Encrypted path implementation.
- Mailbucket.
- Cleanup.
- Causal governance.
- Route topology changes.
- Business payload interpretation.

## Files Changed

Runtime:

- `aegis-router/aegis_router/core.py`

Tests:

- `aegis-router/tests/test_mailbucket_protocol.py`
- `aegis-router/tests/test_top_level_route_protocol.py`

Report:

- `runtime_test_reports/PHASE_3_IMPLEMENTATION_REPORT.md`

## Runtime Behavior Added

`Router.send_message()` now validates Envelope v1 shape only when:

```text
message_type == "route_envelope"
```

The router validates the envelope as a structural contract. It does not treat the envelope as a security proof.

The router still does not:

- verify signatures;
- bind caller identity;
- verify nonce/timestamp replay windows;
- decrypt `path`;
- inspect mailbucket contents;
- judge business semantics.

Non-`route_envelope` messages keep the existing payload-object behavior.

## Tests Changed

Converted the Phase 3 logical xfail test to normal passing behavior:

- `test_contract_envelope_requires_sender_receiver_path_and_auth`

The test remains parameterized across four malformed envelopes:

- missing `sender`
- missing `receiver`
- missing `path`
- missing `auth`

Updated Phase 1/2 top-level route tests to send structurally valid route envelopes so they continue testing route behavior rather than malformed envelope behavior.

No future-phase xfails were intentionally changed:

- forged sender identity remains xfail;
- signature coverage/replay remains xfail;
- mailbucket root remains xfail;
- README validation remains xfail;
- cleanup remains xfail.

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
collected 38 items

tests\test_mailbucket_protocol.py ....xxxxx                              [ 23%]
tests\test_mcp_server.py ...                                             [ 31%]
tests\test_router_core.py .......                                        [ 50%]
tests\test_top_level_route_protocol.py ...................               [100%]

======================== 33 passed, 5 xfailed in 0.26s ========================
```

Repository checks:

```powershell
git diff --check
git status --short
```

`git diff --check` result: passed with no output.

Line-ending scan:

```text
NO_CRLF_FOUND_IN_PHASE_3_FILES
```

## Xfail Count Before and After

- Before Phase 3: `29 passed, 9 xfailed`
- After Phase 3: `33 passed, 5 xfailed`

The instruction expected `30 passed, 8 xfailed` if one pytest item changed. The existing Envelope v1 xfail was one logical test but four parameterized pytest items. Converting exactly that logical test lowered the pytest item-level xfail count by four. No unrelated future-phase xfail was touched.

## Remaining Gaps

Still intentionally not implemented:

- Sender authentication.
- Signature verification.
- Nonce/timestamp replay policy.
- Receiver-only encrypted path handling.
- Mailbucket shared root and send flow.
- Mailbucket README validation.
- Mailbucket cleanup grace period.
- Governance message hooks.

## Ambiguity

No blocking ambiguity for Phase 3.

The current contract does not define an explicit envelope version field, so Phase 3 does not require one. The router validates only the documented v1 logical fields: `sender`, `receiver`, `path`, and `auth`.

`auth` is validated only as a required object. Its cryptographic meaning remains for Phase 4.

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- No auth/signature/replay behavior was implemented.
- No encrypted path behavior was implemented.
- No mailbucket or cleanup behavior was implemented.
- No causal governance behavior was implemented.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, temporary mailbucket data, or generated private keys were added.

PHASE 3 PASSED. Waiting for developer approval before next phase.
