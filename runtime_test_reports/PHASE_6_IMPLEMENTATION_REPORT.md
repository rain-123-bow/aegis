# Phase 6 Implementation Report

## Phase Name

PHASE 6: Local mailbucket shared-root and sender-side message-folder flow.

## Exact Scope

Implemented only the local mailbucket shared-root and sender-side message-folder flow.

In scope:

- Router-owned/configured shared communication root.
- Sender-side creation of one unique message folder under the shared root.
- Folder naming with sender, receiver, UTC timestamp, and nonce.
- `README.md` materialization as the message body.
- Optional attachment copying into the same message folder.
- Protected path token generation compatible with Phase 5 path resolution.
- Envelope payload remains a small path-only reference.

Out of scope:

- Cleanup grace period.
- Expired-folder deletion.
- Production receiver-only cryptography.
- Ed25519/public-key hardening.
- Causal governance.
- Archive / Knowledge / Causal admission.
- README semantic parsing.
- Attachment semantic parsing.
- Permanent public-mailbucket retention.

## Files Changed

Runtime:

- `aegis-router/aegis_router/mailbucket.py`
- `aegis-router/aegis_router/core.py`
- `aegis-router/aegis_router/__init__.py`

Tests:

- `aegis-router/tests/test_mailbucket_protocol.py`

Report:

- `runtime_test_reports/PHASE_6_IMPLEMENTATION_REPORT.md`

## Runtime Behavior Added

`Router` now has a deterministic shared communication root:

```python
router.shared_communication_root
```

If no root is supplied, it defaults to:

```text
<router state parent>/mailbucket
```

Added sender-side helper:

```python
create_mailbucket_message(...)
```

The helper:

- validates safe sender, receiver, and nonce filename components;
- creates the shared root if needed;
- creates exactly one unique message folder;
- writes `README.md`;
- copies optional attachments into the same folder;
- rejects unsafe folder or attachment destination components;
- returns a Phase 5-compatible protected path token and resolver material.

The router still does not read `README.md`, inspect attachments, determine semantic value, or make retention decisions.

## Mailbucket Shared-Root Design

The shared root is a router-owned/configured local filesystem path. It is normalized with `Path(...).resolve()` and exposed as `Router.shared_communication_root`.

The root is used by the sender-side mailbucket helper. It is temporary public communication infrastructure, not a vault, archive, or private workspace.

## Mailbucket Message-Folder Design

Each mailbucket message uses one folder named:

```text
<sender>__<receiver>__<utc_timestamp>__<nonce>
```

The timestamp format is:

```text
YYYYMMDDTHHMMSSffffffZ
```

`README.md` is required structurally. Optional attachments are copied under destination names supplied by the caller, but destination paths must stay inside the message folder.

The helper rejects:

- unsafe sender/receiver/nonce components;
- missing or empty `readme_text`;
- attachment destination traversal;
- absolute attachment destinations;
- non-file attachment sources;
- duplicate message folder names.

## Protected Path Integration With Phase 5

`create_mailbucket_message(...)` returns:

```text
protected_path
resolver_material
```

`protected_path` uses the Phase 5 development token format:

```text
aegis-dev-path-token:v1:<folder_name>
```

The token can be resolved by:

```python
resolve_route_envelope_path(...)
```

The route envelope still carries only the opaque protected token. It does not carry README text or attachment content inline.

## Dependency Result

No dependency was added.

The Phase 6 implementation uses only Python standard-library modules:

- `datetime`
- `pathlib`
- `re`
- `shutil`
- `typing`
- `uuid`

## Tests Changed

Converted these Phase 6 xfail tests to normal passing tests:

- `test_contract_router_owns_shared_mailbucket_root`
- `test_contract_mailbucket_folder_requires_readme`

Added Phase 6 tests:

- `test_contract_sender_creates_unique_mailbucket_folder_with_readme_and_attachment`
- `test_contract_mailbucket_protected_path_resolves_to_created_folder`
- `test_contract_mailbucket_rejects_unsafe_folder_and_attachment_destinations`
- `test_contract_router_envelope_carries_only_mailbucket_reference`

Kept future-phase xfail intact:

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
collected 52 items

tests\test_mailbucket_protocol.py ......................x                [ 44%]
tests\test_mcp_server.py ...                                             [ 50%]
tests\test_router_core.py .......                                        [ 63%]
tests\test_top_level_route_protocol.py ...................               [100%]

======================== 51 passed, 1 xfailed in 0.37s ========================
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
 M aegis-router/aegis_router/__init__.py
 M aegis-router/aegis_router/core.py
 M aegis-router/aegis_router/server.py
 M aegis-router/pyproject.toml
 M docs/ROUTER_DESIGN.md
?? aegis-master-kit/organization/contracts/
?? aegis-master-kit/organization/topologies/master_top_level_v1.yaml
?? aegis-router/aegis_router/mailbucket.py
?? aegis-router/aegis_router/path_resolution.py
?? aegis-router/tests/test_mailbucket_protocol.py
?? aegis-router/tests/test_top_level_route_protocol.py
?? runtime_test_reports/
```

Line-ending scan for Phase 6 edited files:

```text
NO_CRLF aegis-router/aegis_router/mailbucket.py
NO_CRLF aegis-router/aegis_router/core.py
NO_CRLF aegis-router/aegis_router/__init__.py
NO_CRLF aegis-router/tests/test_mailbucket_protocol.py
```

## Xfail Count Before and After

- Before Phase 6: `45 passed, 3 xfailed`
- After Phase 6: `51 passed, 1 xfailed`

Phase 6 converted two xfailed mailbucket root/README tests and added four passing sender-side mailbucket-flow tests. The remaining xfail is cleanup-only and belongs to Phase 7.

## Remaining Gaps

Still intentionally not implemented:

- Cleanup grace period.
- Expired-folder deletion.
- Production receiver-only path encryption.
- Ed25519/public-key hardening.
- Governance message hooks.
- Archive / Knowledge / Causal admission.
- Semantic retention or public-mailbucket vault behavior.

## Ambiguity

No blocking ambiguity for Phase 6 runtime tests.

The contract says the sender creates the message folder while the router owns/configures the shared root. The implementation keeps those roles separate: `Router` exposes the configured root, and `create_mailbucket_message(...)` performs sender-side folder materialization.

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- Cleanup behavior was not implemented.
- Expired-folder deletion was not implemented.
- README semantic parsing was not implemented.
- Attachment semantic parsing was not implemented.
- Causal governance behavior was not implemented.
- Archive / Knowledge / Causal admission behavior was not implemented.
- The public mailbucket was not made into a vault or archive.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, temporary mailbucket data, generated private keys, private key material, or generated mailbucket folders were added.

PHASE 6 PASSED. Waiting for developer approval before next phase.
