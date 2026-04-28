# Phase 8 Implementation Report

## Phase Name

PHASE 8: Governance message hooks only.

## Exact Scope

Implemented structural governance message hooks for the existing top-level route graph.

In scope:

- Explicit governance message type table.
- Edge/type validation for top-level governance messages.
- Governance messages continue to use Envelope v1 payload shape.
- Governance messages continue to require sender auth and replay protection.
- Tests proving no Archive / Knowledge / Causal mutation.

Out of scope:

- Causal merge.
- Archive / Knowledge / Causal admission.
- Debate reasoning.
- Final review reasoning.
- Evidence sufficiency judgment.
- README semantic parsing.
- Attachment semantic parsing.
- Production receiver-only path encryption.
- Ed25519/public-key hardening.

## Files Changed

Runtime:

- `aegis-router/aegis_router/core.py`

Tests:

- `aegis-router/tests/test_governance_hooks.py`

Report:

- `runtime_test_reports/PHASE_8_IMPLEMENTATION_REPORT.md`

## Runtime Behavior Added

Added `GOVERNANCE_MESSAGE_TYPES_BY_EDGE`, a small explicit route/type table for the top-level domain.

Allowed governance message types:

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

For governance message types, `Router.send_message()` now:

1. validates Envelope v1 payload shape;
2. enforces same-domain policy;
3. enforces the authoritative directed route table;
4. validates the governance message type is allowed on that directed edge;
5. verifies Envelope v1 auth and replay policy;
6. stores only the message envelope record.

`route_envelope` remains allowed as the generic envelope transport message type for prior phase tests.

## Governance Hook Design Used

Governance hooks are represented by the outer `message_type`.

The payload remains the existing Envelope v1 structure:

```text
sender
receiver
path
auth
```

This avoids weakening Phase 3 envelope shape validation and keeps governance metadata structural. The router may reject wrong edge/type combinations, but it does not judge causal truth, debate quality, final review correctness, evidence sufficiency, README truth, or attachment value.

`failure_feedback` uses the existing Envelope v1 `path` field as the structural evidence reference. The router checks that `path` exists and is signed through the existing Envelope v1 validation/auth path. It does not inspect the referenced README or attachments.

## Tests Changed

Added `aegis-router/tests/test_governance_hooks.py` with these checks:

- valid structural hooks are accepted on allowed edges;
- `execution -> master` accepts `causal_fork_submission`;
- causal fork submission does not mutate global Causal state;
- `execution -> debate` accepts `adjudication_request`;
- `debate -> execution` accepts `adjudication_result`;
- adjudication result does not grant global causal authority;
- `debate -> master` accepts `debate_result`;
- `test -> execution` accepts `failure_feedback`;
- `failure_feedback` without structural evidence path is rejected;
- `test -> final_review` accepts `test_result`;
- `final_review -> master` accepts `final_review_result`;
- invalid governance type on a valid edge is rejected;
- valid governance type on an invalid edge is rejected;
- README content is not treated as governance truth;
- private copy preservation does not trigger store admission.

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
collected 67 items

tests\test_governance_hooks.py ..............                            [ 20%]
tests\test_mailbucket_protocol.py ........................               [ 56%]
tests\test_mcp_server.py ...                                             [ 61%]
tests\test_router_core.py .......                                        [ 71%]
tests\test_top_level_route_protocol.py ...................               [100%]

============================= 67 passed in 0.44s ==============================
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
?? aegis-router/tests/test_governance_hooks.py
?? aegis-router/tests/test_mailbucket_protocol.py
?? aegis-router/tests/test_top_level_route_protocol.py
?? runtime_test_reports/
```

Line-ending scan for Phase 8 edited files:

```text
NO_CRLF aegis-router/aegis_router/core.py
NO_CRLF aegis-router/tests/test_governance_hooks.py
```

## Test Count Before and After

- Before Phase 8: `53 passed, 0 xfailed`
- After Phase 8: `67 passed, 0 xfailed`

Phase 8 added 14 passing governance-hook tests. No existing test regressed and the xfail count remained `0`.

## Remaining Gaps

Still intentionally not implemented:

- Real causal merge.
- Archive / Knowledge / Causal admission.
- Debate reasoning.
- Final review reasoning.
- Test evidence sufficiency judgment.
- README semantic parsing.
- Attachment semantic parsing.
- Production receiver-only path encryption.
- Ed25519/public-key hardening.

## Ambiguity

No blocking ambiguity for Phase 8 runtime tests.

The contract allowed either a static table or topology-derived message type policy. This phase uses a static table matching the documented top-level v1 route graph and the instruction's recommended message types. It does not add YAML parsing or a topology DSL.

## Safety Statement

- No push was performed.
- No merge was performed.
- No PR was created.
- No causal merge was implemented.
- No Archive / Knowledge / Causal admission was implemented.
- No README semantic parsing was implemented.
- No attachment semantic parsing was implemented.
- No production receiver-only path encryption was implemented.
- No Ed25519/public-key hardening was implemented.
- No `.venv`, `.pytest_cache`, `__pycache__`, runtime state, generated private keys, private key material, or generated mailbucket folders were added.

PHASE 8 PASSED. Waiting for developer approval before next phase.
