# Top-Level Route Protocol Runtime Test Report

## Final Recommendation

Runtime implementation gap exists.

Phase 1 update: authoritative directed top-level route table enforcement is now implemented and tested. The latest runtime result is:

```text
28 passed, 10 xfailed in 0.28s
```

The remaining implementation gaps are role-local route table representation, envelope v1 shape, sender authentication, encrypted path handling, mailbucket lifecycle, cleanup, and governance message hooks.

The repository now contains the top-level route topology and route/mailbucket protocol files, and the existing router runtime still passes its original tests. After Phase 1, directed top-level route enforcement exists for the top-level domain. The runtime still does not implement route envelope authentication, encrypted path handling, mailbucket lifecycle, or cleanup behavior.

## Repository Under Test

- Repository path: `C:\Users\playm\Documents\self-git\aegis`
- Branch tested: `v0.1.0-alpha`
- Commit/ref tested: `3e7c068a6bbd58e68e01ba32dbd898b32fd1dc35`
- Working tree state: uncommitted protocol documentation, runtime contract tests, and reports are present.

## Protocol Patch Presence

All required top-level route protocol files are present:

| Required file | Status |
| --- | --- |
| `README.md` | Present |
| `docs/ROUTER_DESIGN.md` | Present |
| `aegis-master-kit/organization/ORGANIZATION_MODEL.md` | Present |
| `aegis-master-kit/organization/topologies/master_top_level_v1.yaml` | Present |
| `aegis-master-kit/organization/contracts/TOP_LEVEL_ROUTE_TOPOLOGY_CONTRACT.md` | Present |
| `aegis-master-kit/organization/contracts/ROUTE_ENVELOPE_AND_MAILBUCKET_CONTRACT.md` | Present |
| `aegis-router/aegis_router/core.py` | Present |
| `aegis-router/aegis_router/server.py` | Present |
| `aegis-router/aegis_router/models.py` | Present |
| `aegis-router/tests/test_router_core.py` | Present |
| `aegis-router/tests/test_mcp_server.py` | Present |

## Runtime Test Commands Executed

Nested reviewer:

```text
nested-codex model=gpt-5.4 reasoning_effort=medium sandbox=read-only
```

Local runtime tests:

```powershell
cd C:\Users\playm\Documents\self-git\aegis\aegis-router
.\.venv\Scripts\python.exe -m pytest
```

Whitespace check:

```powershell
git diff --check
```

Line-ending scan:

```text
NO_CRLF_FOUND_IN_RUNTIME_TEST_FILES
```

## Runtime Test Result

Final pytest result:

```text
collected 38 items
tests\test_mailbucket_protocol.py xxxxxxxxx                              [ 23%]
tests\test_mcp_server.py ...                                             [ 31%]
tests\test_router_core.py .......                                        [ 50%]
tests\test_top_level_route_protocol.py ..........xxxxxxxxx               [100%]

20 passed, 18 xfailed in 0.31s
```

Interpretation:

- `20 passed`: current implemented router behavior and contract-file presence checks are stable.
- `18 xfailed`: expected runtime implementation gaps for the new top-level route and mailbucket protocol.
- No runtime production code was modified.

## Tests Added

Added:

- `aegis-router/tests/test_top_level_route_protocol.py`
- `aegis-router/tests/test_mailbucket_protocol.py`

Updated test configuration:

- `aegis-router/pyproject.toml`

The `contract` pytest marker was registered so the new runtime contract tests run without marker warnings.

## Test Matrix

### A. Top-Level Directed Route Table

| Behavior | Runtime test | Result | Classification |
| --- | --- | --- | --- |
| Valid routes: all `E001`-`E010` pairs are sendable | `test_contract_valid_top_level_routes_are_currently_sendable` | Passed | Current same-domain runtime accepts them |
| Invalid routes: `test -> master`, `master -> test`, `debate -> test`, `final_review -> execution`, `final_review -> debate`, `test -> debate` | `test_contract_invalid_top_level_routes_are_rejected` | Xfailed | Directed route table not implemented |
| Same-domain visibility must not imply route permission | `test_contract_same_domain_visibility_does_not_imply_send_permission` | Xfailed | Visibility and permission are not separated |
| Protocol pairs must not become unrestricted bidirectional chat | `test_contract_protocol_pairs_do_not_create_unrestricted_chat` | Xfailed | Protocol-pair semantics not implemented |

### B. Router Authoritative Table vs Role-Local Table

| Behavior | Runtime test | Result | Classification |
| --- | --- | --- | --- |
| Router-side table is mechanism-level authority | Covered by invalid-route xfail tests | Xfailed | No runtime route table exists |
| Role-local outgoing/incoming policy is represented | `test_contract_role_local_policy_can_forbid_raw_router_route` | Xfailed | Role-local route table not represented |
| Role-local policy can forbid a message even if a raw route exists | `test_contract_role_local_policy_can_forbid_raw_router_route` | Xfailed | Runtime cannot enforce role-local policy |
| Runtime only supports same-domain routing | Existing `test_cross_domain_message_rejected`; new same-domain invalid-route xfails | Passed/Xfailed | Same-domain exists; directed routes absent |

### C. Envelope Protocol

| Behavior | Runtime test | Result | Classification |
| --- | --- | --- | --- |
| Envelope requires `sender` | `test_contract_envelope_requires_sender_receiver_path_and_auth` | Xfailed | Envelope v1 not implemented |
| Envelope requires `receiver` | `test_contract_envelope_requires_sender_receiver_path_and_auth` | Xfailed | Envelope v1 not implemented |
| Envelope requires `path` | `test_contract_envelope_requires_sender_receiver_path_and_auth` | Xfailed | Envelope v1 not implemented |
| Envelope requires `auth` | `test_contract_envelope_requires_sender_receiver_path_and_auth` | Xfailed | Envelope v1 not implemented |
| Forged sender identity rejected | `test_contract_forged_sender_identity_is_rejected` | Xfailed | Caller identity/auth binding not implemented |
| Signature covers sender, receiver, path, nonce, timestamp | `test_contract_auth_covers_path_nonce_and_timestamp` | Xfailed | Signature verification/replay checks not implemented |
| Router must not decrypt path | Not executable against current runtime | Gap | No encrypted path flow exists |
| Auth success must not imply payload truth | Classified in report | Gap/Boundary | Runtime has no auth and no semantic payload evaluator |

### D. Mailbucket Protocol

| Behavior | Runtime test | Result | Classification |
| --- | --- | --- | --- |
| Router owns shared communication root | `test_contract_router_owns_shared_mailbucket_root` | Xfailed | No shared mailbucket root exists |
| Sender creates unique folder under shared root | Not executable beyond missing-root test | Gap | Mailbucket send flow not implemented |
| Folder naming includes sender, receiver, UTC timestamp, nonce/equivalent | Not executable | Gap | Mailbucket naming not implemented |
| `README.md` required as message body | `test_contract_mailbucket_folder_requires_readme` | Xfailed | README validation not implemented |
| Attachments live inside message folder | Not executable | Gap | Mailbucket folder model not implemented |
| Envelope carries encrypted path only, not large inline payload | Covered by envelope xfail tests | Xfailed | Envelope v1 not implemented |
| Receiver may use one-time info in shared mailbucket | Not executable | Gap | Receiver mailbucket read flow not implemented |
| Sender/receiver copy long-term value into private folder | Not executable | Gap | Private folder preservation policy not implemented |
| Public mailbucket must not become vault/archive | Not executable | Gap | Cleanup/storage boundary not implemented |
| Cleanup deletes expired public folders after grace period | `test_contract_mailbucket_cleanup_exists_and_preserves_private_copies` | Xfailed | Cleanup not implemented |
| Cleanup does not inspect README/attachment semantics | Not executable | Gap | Cleanup not implemented |
| Deleting public folder does not delete private copies | `test_contract_mailbucket_cleanup_exists_and_preserves_private_copies` | Xfailed | Cleanup/private-copy model not implemented |

### E. Governance Boundary

| Behavior | Runtime classification | Result |
| --- | --- | --- |
| `execution -> master` may submit causal fork or merge-relevant reasoning state | Route is currently sendable only because same-domain routing allows it | Passed as generic send; semantics not enforced |
| Execution must not directly merge causal fork into global Causal | Not router-runtime behavior | Governance gap outside current router code |
| Debate must not directly merge into global Causal | Not router-runtime behavior | Governance gap outside current router code |
| `debate -> execution` returns adjudication result, not global authority | Runtime cannot validate semantic purpose | Gap |
| Mailbucket README does not become Archive/Knowledge/Causal truth automatically | Runtime has no mailbucket or store admission path | Boundary gap |
| Private copy does not imply Archive/Knowledge/Causal admission | Runtime has no private-copy or store admission path | Boundary gap |

## Passed Tests

Existing router behavior still passes:

- MCP tool listing and required-argument validation.
- Agent registration.
- Same-domain message send/receive/ack.
- Cross-domain message rejection.
- Non-target ack rejection.
- Cross-domain parent registration rejection.
- No-ack message lifecycle completion.
- Deactivate/unregister behavior.

New contract tests that pass:

- All ten valid top-level directed pairs are sendable under current same-domain runtime. This is only a weak positive result because the runtime does not know the route table; it accepts them because all roles are in the same domain.

## Failed Tests

No unmarked hard failures occurred.

The following classes are intentionally marked `xfail(strict=True)` and currently xfail as expected:

- Invalid same-domain directed routes are not rejected.
- Same-domain visibility still implies practical send permission.
- Protocol-pair constraints are not enforced.
- Role-local route tables are not represented.
- Envelope v1 required fields are not enforced.
- Forged sender/auth mismatch is not rejected.
- Signature coverage and replay fields are not verified.
- Router-owned shared mailbucket root does not exist.
- Mailbucket `README.md` validation does not exist.
- Mailbucket cleanup/grace-period behavior does not exist.

## Not-Implemented Runtime Gaps

The current runtime does not implement:

1. Authoritative top-level directed route table.
2. Loading or enforcing `master_top_level_v1.yaml`.
3. Role-local route table representation or enforcement.
4. Protocol-pair semantics.
5. Evidence-required edge validation for `test -> execution`.
6. Conditional edge validation for `execution -> debate`.
7. Special-purpose validation for `execution -> master`.
8. Route envelope v1 with `sender`, `receiver`, `path`, and `auth`.
9. Caller identity binding or sender anti-spoofing beyond caller-supplied `from_id`.
10. Public key registration or signature verification.
11. Nonce/timestamp replay window.
12. Receiver-encrypted path handling.
13. Router-owned shared communication root.
14. Mailbucket unique folder creation and naming.
15. Required `README.md` validation.
16. Attachment folder lifecycle.
17. Mailbucket cleanup after grace period.
18. Private-copy preservation model.

## Ambiguity Found

1. The contract says the router verifies auth using sender public identity key, but the current router has no identity key registry or caller/session identity model.
2. The contract says `test -> execution` feedback must contain evidence or a path to evidence, but it also says the router must not evaluate payload semantics. This likely belongs to role-local policy or receiver validation, not router semantic parsing.
3. The contract says `execution -> debate` is conditional, but does not yet define a machine-readable condition field or enforcement layer.
4. The contract says the router owns cleanup, but does not yet define exact folder metadata, grace-period config format, or read/consume state.

## Nested Agent Summary

One nested Codex CLI reviewer was requested with:

- model: `gpt-5.4`
- reasoning effort: `medium`
- sandbox: read-only

The first nested-codex call timed out without a report. A second constrained call was made because the first call was a tool-level hard blocker. The reviewer concluded:

- Current code can test active-agent gating, same-domain restriction, visibility listing, message lifecycle, target-only ack, and MCP tool plumbing.
- The required top-level route table is not stored or enforced.
- Same-domain visibility is not separated from route permission.
- Role-local route tables are absent.
- The v1 edge list `E001`-`E010` is not encoded in runtime.
- Envelope v1, auth, key registry, signature verification, nonce/timestamp replay checks, encrypted path flow, shared root, README validation, and cleanup are not implemented.
- Suggested tests should use `xfail` for missing protocol behaviors.

My local test matrix matches that independent conclusion.

## Files Added or Modified by This Verification

Added:

- `aegis-router/tests/test_top_level_route_protocol.py`
- `aegis-router/tests/test_mailbucket_protocol.py`
- `runtime_test_reports/TOP_LEVEL_ROUTE_PROTOCOL_RUNTIME_TEST_REPORT.md`

Modified:

- `aegis-router/pyproject.toml`

Already applied protocol patch files are also present in the working tree:

- `docs/ROUTER_DESIGN.md`
- `aegis-master-kit/organization/ORGANIZATION_MODEL.md`
- `aegis-master-kit/organization/contracts/TOP_LEVEL_ROUTE_TOPOLOGY_CONTRACT.md`
- `aegis-master-kit/organization/contracts/ROUTE_ENVELOPE_AND_MAILBUCKET_CONTRACT.md`
- `aegis-master-kit/organization/topologies/master_top_level_v1.yaml`

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- No production router implementation code was modified.
- No `.venv`, `.pytest_cache`, `__pycache__`, or runtime-generated files were intentionally added.
