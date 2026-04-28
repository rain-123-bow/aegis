# Phase 7 Implementation Report

## Phase Name

PHASE 7: Mailbucket cleanup grace-period behavior.

## Exact Scope

Implemented only cleanup grace-period behavior for public shared mailbucket folders.

In scope:

- Cleanup API/helper.
- Grace-period deletion policy.
- Expired public message-folder deletion.
- Non-expired public message-folder preservation.
- Private copy preservation.
- Deterministic cleanup result summary.
- Cleanup based only on structural filesystem metadata.

Out of scope:

- Production receiver-only path encryption.
- Ed25519/public-key hardening.
- Causal governance.
- Archive / Knowledge / Causal admission.
- README semantic parsing.
- Attachment semantic parsing.
- Public-mailbucket vault behavior.
- Phase 8 governance hooks.

## Files Changed

Runtime:

- `aegis-router/aegis_router/mailbucket.py`
- `aegis-router/aegis_router/core.py`
- `aegis-router/aegis_router/__init__.py`

Tests:

- `aegis-router/tests/test_mailbucket_protocol.py`

Report:

- `runtime_test_reports/PHASE_7_IMPLEMENTATION_REPORT.md`

## Runtime Behavior Added

Added helper:

```python
cleanup_expired_mailbucket_messages(...)
```

Added router wrapper:

```python
Router.cleanup_mailbucket(...)
```

Cleanup accepts:

- shared mailbucket root;
- grace period in seconds;
- optional deterministic `now`.

Cleanup returns:

```text
root
deleted
skipped
```

`deleted` contains deleted public folder paths. `skipped` contains skipped entries with structural reasons.

## Cleanup Design Used

Cleanup scans only direct children of the configured shared mailbucket root.

It:

- skips missing roots as an empty cleanup result;
- rejects a non-directory cleanup root;
- skips symlinks;
- skips non-directory entries;
- resolves each candidate and confirms it remains under the shared root;
- deletes only expired directories;
- keeps non-expired directories;
- never traverses or deletes outside the configured root.

It does not read `README.md`, parse attachment content, inspect business meaning, or preserve public folders because content claims long-term value.

## Grace-Period Policy

The current policy compares:

```text
now - folder_mtime >= grace_period_seconds
```

Expired folders are deleted. Folders still inside the grace period are skipped with:

```text
within_grace_period
```

This uses filesystem metadata only.

## Tests Changed

Converted the final Phase 7 xfail to a normal passing test:

- `test_contract_mailbucket_cleanup_exists_and_preserves_private_copies`

Added one focused cleanup boundary test:

- `test_contract_mailbucket_cleanup_skips_files_and_is_deterministic`

The cleanup tests prove:

- expired public folder deletion;
- non-expired public folder preservation;
- private copy preservation;
- README text such as `KEEP FOREVER` does not preserve the public folder;
- attachment presence does not preserve the public folder;
- non-directory entries are skipped;
- deleted path ordering is deterministic.

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
collected 53 items

tests\test_mailbucket_protocol.py ........................               [ 45%]
tests\test_mcp_server.py ...                                             [ 50%]
tests\test_router_core.py .......                                        [ 64%]
tests\test_top_level_route_protocol.py ...................               [100%]

============================= 53 passed in 0.34s ==============================
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

Line-ending scan for Phase 7 edited files:

```text
NO_CRLF aegis-router/aegis_router/mailbucket.py
NO_CRLF aegis-router/aegis_router/core.py
NO_CRLF aegis-router/aegis_router/__init__.py
NO_CRLF aegis-router/tests/test_mailbucket_protocol.py
```

## Xfail Count Before and After

- Before Phase 7: `51 passed, 1 xfailed`
- After Phase 7: `53 passed, 0 xfailed`

Phase 7 converted the one cleanup xfail and added one cleanup boundary test.

## Remaining Gaps

Still intentionally not implemented:

- Production receiver-only path encryption.
- Ed25519/public-key hardening.
- Causal governance.
- Archive / Knowledge / Causal admission.
- Governance message hooks.
- Public-mailbucket semantic retention.

## Ambiguity

No blocking ambiguity for Phase 7 runtime tests.

The contract allows cleanup to use structural time, machine-readable lifecycle data, or folder metadata. This implementation uses direct child folder modification time as the current deterministic folder metadata policy.

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- Production receiver-only path encryption was not implemented.
- Ed25519/public-key hardening was not implemented.
- Causal governance behavior was not implemented.
- Archive / Knowledge / Causal admission behavior was not implemented.
- README semantic parsing was not implemented.
- Attachment semantic parsing was not implemented.
- Public mailbucket vault behavior was not implemented.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, generated private keys, private key material, or generated mailbucket folders were added.

PHASE 7 PASSED. Waiting for developer approval before next phase.
