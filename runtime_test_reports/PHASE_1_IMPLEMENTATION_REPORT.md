# Phase 1 Implementation Report

## Phase

PHASE 1: Authoritative directed route table.

## Starting State

Phase 1 starts from an existing runtime classification where top-level route protocol tests exist and the router accepts any same-domain sender/receiver pair. That behavior lets valid top-level edges pass, but it also allows invalid same-domain edges.

Known pre-phase test state from `runtime_test_reports/TOP_LEVEL_ROUTE_PROTOCOL_RUNTIME_TEST_REPORT.md`:

```text
20 passed, 18 xfailed
```

## Phase Scope

Implement only directed top-level route enforcement.

In scope:

- Allow the ten v1 directed top-level edges.
- Reject invalid same-domain top-level edges.
- Preserve existing same-domain behavior for non-top-level generic router domains.
- Preserve cross-domain rejection.

Out of scope:

- Envelope auth.
- Encrypted path.
- Mailbucket.
- Cleanup.
- Causal governance.
- Role-local route table representation.

## Implementation

Changed runtime file:

- `aegis-router/aegis_router/core.py`

Runtime behavior added:

- Added an authoritative v1 top-level route table for `top_level_master_domain`.
- Added optional domain metadata support for `metadata.router_route_table`.
- `send_message()` still first enforces registered active sender/receiver and same-domain routing.
- After same-domain validation, `send_message()` now rejects missing directed edges when a domain has a configured route table.
- Generic domains without a configured route table keep the previous same-domain behavior for backward compatibility.

Meaning-free boundary:

- The router checks only structural sender/receiver directed-edge permission.
- The router does not inspect payload meaning.
- The router does not implement envelope auth, encrypted path, mailbucket, cleanup, or causal governance.

## Tests Changed

Changed test file:

- `aegis-router/tests/test_top_level_route_protocol.py`

Converted these Phase 1 xfail tests to normal passing tests:

- `test_contract_invalid_top_level_routes_are_rejected`
- `test_contract_same_domain_visibility_does_not_imply_send_permission`
- `test_contract_protocol_pairs_do_not_create_unrestricted_chat`

Kept future-phase xfail tests intact:

- `test_contract_role_local_policy_can_forbid_raw_router_route`
- all envelope/auth/mailbucket/cleanup tests in `test_mailbucket_protocol.py`

## Tests Run

Command:

```powershell
cd C:\Users\playm\Documents\self-git\aegis\aegis-router
.\.venv\Scripts\python.exe -m pytest
```

Result:

```text
collected 38 items
tests\test_mailbucket_protocol.py xxxxxxxxx                              [ 23%]
tests\test_mcp_server.py ...                                             [ 31%]
tests\test_router_core.py .......                                        [ 50%]
tests\test_top_level_route_protocol.py ..................x               [100%]

28 passed, 10 xfailed in 0.28s
```

Additional checks from repository root:

```powershell
git diff --check
git status --short
```

`git diff --check` result: passed with no output.

Line-ending scan:

```text
NO_CRLF_FOUND_IN_PHASE_1_FILES
```

## Xfail Count

- Before Phase 1: `18 xfailed`
- After Phase 1: `10 xfailed`
- Phase 1 removed `8` expected failures from the runtime gap list.

## Remaining Gaps

Still intentionally not implemented:

- Role-local route table representation.
- Envelope v1 shape validation.
- Sender authentication and signature verification.
- Nonce/timestamp replay policy.
- Receiver-only encrypted path handling.
- Mailbucket shared root and send flow.
- Mailbucket cleanup grace period.
- Governance message hooks.

## Ambiguity

No blocking ambiguity for Phase 1.

The contract says the top-level route table comes from `master_top_level_v1.yaml` or equivalent runtime route config. This phase uses an equivalent runtime route table for the documented v1 topology and supports explicit `metadata.router_route_table` on domains for configurable route tables. It does not add a YAML loader dependency.

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- No production changes outside Phase 1 route enforcement were made.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, temporary mailbucket data, or generated private keys were added.

## Phase Result

PHASE 1 PASSED.
