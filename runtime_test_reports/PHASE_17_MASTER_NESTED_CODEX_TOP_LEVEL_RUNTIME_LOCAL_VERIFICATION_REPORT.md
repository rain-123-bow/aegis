# Phase 17 Master Nested-Codex Top-Level Runtime Local Verification Report

## Scope

Local verification of the Master top-level nested-Codex Leader bootstrap patch.

This validates demo-level behavior only. It does not claim production Master runtime closure.

## Patch Application

The patch package was applied from:

```text
C:\Users\playm\Documents\self-git\patch\aegis_master_nested_codex_top_level_patch_v0_1
```

Added:

```text
PATCH_USAGE_MASTER_NESTED_CODEX_TOP_LEVEL.md
aegis-runtime/master/
runtime_test_reports/PHASE_17_MASTER_NESTED_CODEX_TOP_LEVEL_RUNTIME_IMPLEMENTATION_REPORT.md
```

## Required Fix Applied Before Validation

The original patch checked 9 top-level status_update edges and missed:

```text
debate -> master
```

The runtime was patched so `TOP_LEVEL_ROUTE_CHECKS` now includes:

```python
("debate", "master")
```

The router-integrated test was updated to expect 10 route checks and explicitly assert the `debate -> master` check exists.

## Commands Run

Working directory:

```text
C:\Users\playm\Documents\self-git\aegis
```

Commands:

```powershell
py -3.13 -m venv .venv-master-runtime
.\.venv-master-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-master-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-master-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\master[dev]"

.\.venv-master-runtime\Scripts\python.exe -m pytest .\aegis-runtime\master -vv

.\.venv-master-runtime\Scripts\python.exe -m aegis_master_runtime.cli validate-recording --policy .\MODEL_REASONING_BUDGET_POLICY.yaml --router-state .\.aegis-master-runtime\router_state.json --output-dir .\.aegis-master-runtime

codex --version
codex mcp-server --help
```

Cleanup:

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force .\.aegis-master-runtime -ErrorAction SilentlyContinue
```

## Local Runtime Test Results

Master runtime tests:

```text
3 passed in 0.13s
```

Validated test cases:

```text
test_router_state_contains_policy_bound_nested_codex_leaders
test_locked_policy_parses_top_level_profiles
test_master_uses_policy_to_create_all_top_level_leaders_and_register_router
```

Recording CLI validation output:

```json
{
  "created_agent_count": 4,
  "policy_version": "v0.1",
  "report_id": "top-level-bootstrap-31527031525d445b920b2298fdc1ad5a",
  "report_path": ".aegis-master-runtime\\top_level_bootstrap_report.json",
  "route_checks": 10,
  "status": "top_level_nested_codex_creation_verified"
}
```

## Route Check Proof

The recording validation report contained 10 verified `status_update` route checks:

```text
master -> debate
master -> execution
debate -> master
execution -> test
test -> execution
test -> final_review
final_review -> master
execution -> debate
debate -> execution
execution -> master
```

The added `debate -> master` route check was present and verified.

## Router Compatibility Fix

Initial test run failed because the Master runtime sent bare `status_update` payloads while the current router requires governance messages to use route envelope shape and auth.

Failure:

```text
route_envelope missing required field(s): path, auth
```

Minimal fix:

- Master route checks now send route-envelope-shaped `status_update` payloads.
- Master and created top-level Leaders are registered with dev HMAC identity keys for demo route-envelope auth.
- Router code was not modified.

## Real Nested-Codex Creation Verification

In addition to the local recording tests, this validation used real MCP calls through the current Codex environment:

```text
mcp__nested_codex__.codex
```

The current Master session invoked one real nested-Codex session for each top-level Leader:

| Agent | Role | Requested model | Requested reasoning effort | Policy budget | Thread ID | Proof file |
| --- | --- | --- | --- | --- | --- | --- |
| debate | debate_leader | gpt-5.5 | high | high | 019dfc5a-466f-7651-abd2-66a83ad9b04c | C:\Users\playm\Downloads\agents_test\debate_leader_proof.json |
| execution | execution_leader | gpt-5.5 | high | high | 019dfc5a-f08b-7e50-a9d3-5450de0f088f | C:\Users\playm\Downloads\agents_test\execution_leader_proof.json |
| test | test_leader | gpt-5.5 | high | high | 019dfc5b-a176-7d81-9dbc-953e7a2c8f6a | C:\Users\playm\Downloads\agents_test\test_leader_proof.json |
| final_review | final_review_leader | gpt-5.5 | xhigh | extra_high | 019dfc5c-3f35-7191-90d4-52e98a3cad37 | C:\Users\playm\Downloads\agents_test\final_review_leader_proof.json |

The policy value `extra_high` was requested through the Codex runtime effort spelling `xhigh` for the Final Review Leader.

The current Master was not re-created as a nested agent. This follows the developer instruction allowing the current Codex session to act as Master with its current high reasoning budget for this validation only.

## Agent Proof Files

All four nested agents wrote proof JSON files under:

```text
C:\Users\playm\Downloads\agents_test
```

Each proof file contains:

- `agent_id`;
- `role_id`;
- `created_by: master`;
- `creation_mechanism: real nested-codex MCP mcp__nested_codex__.codex call`;
- requested model;
- policy model;
- requested reasoning effort;
- policy reasoning budget;
- `topology_scope: top_level_master_domain`;
- timestamp;
- proof statement from the agent itself.

Validated proof contents:

```text
debate          debate_leader          gpt-5.5 high  -> policy high
execution       execution_leader       gpt-5.5 high  -> policy high
test            test_leader            gpt-5.5 high  -> policy high
final_review    final_review_leader    gpt-5.5 xhigh -> policy extra_high
```

## Important Distinction

The runtime unit tests use `RecordingNestedCodexClient`; those tests do not prove real nested-Codex creation by themselves.

The real-creation proof in this local run comes from the direct MCP tool calls to `mcp__nested_codex__.codex` and the agent-written files in `C:\Users\playm\Downloads\agents_test`.

The patch's `validate-real` stdio path was not used because it requires a concrete external create-agent MCP tool name. The available local MCP surface exposes real Codex session creation as `mcp__nested_codex__.codex`, which was used directly for this validation.

## Boundary

- no `aegis-router/` files changed
- no top-level topology files changed
- no existing department runtime files changed
- no existing department contract files changed
- no root model/reasoning-budget policy changed
- no module-internal worker/front/back profiles added
- no Master dynamic model adjustment enabled
- no production closure claimed
- no Archive / Knowledge / Causal mutation performed
- no push, merge, release, or PR performed

## Git Hygiene

Generated runtime/cache artifacts were removed:

```text
.aegis-master-runtime/
.pytest_cache/
__pycache__/
```

The virtual environment `.venv-master-runtime/` remains local and is not intended for commit.

