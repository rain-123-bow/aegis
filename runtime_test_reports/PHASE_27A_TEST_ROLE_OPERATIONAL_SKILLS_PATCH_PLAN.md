# Phase 27A Test Role Operational Skills Patch Plan

## Verdict intent

This patch converts Test Leader / Worker role behavior from superseded role contracts into role-bound operational skills.

It is a document/package hardening patch. It does not claim production Test lifecycle closure, production CI closure, remote branch governance closure, release closure, production sign-off, production store writes, or global causal truth merge.

## Scope

Add:

```text
aegis-master-kit/organization/departments/test/TEST_LEADER_OPERATIONAL_SKILL.md
aegis-master-kit/organization/departments/test/TEST_WORKER_OPERATIONAL_SKILL.md
aegis-master-kit/organization/departments/test/TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md
```

Modify:

```text
aegis-master-kit/organization/departments/test/README.md
aegis-master-kit/organization/departments/test/MANIFEST.yaml
```

Remove superseded role contracts:

```text
aegis-master-kit/organization/departments/test/TEST_LEADER_CONTRACT.md
aegis-master-kit/organization/departments/test/TEST_WORKER_CONTRACT.md
```

Keep support contracts:

```text
TEST_DEPARTMENT_CONTRACT.md
TEST_PLAN_AND_ROUTE_SPLIT_CONTRACT.md
TEST_EVIDENCE_AND_RETENTION_CONTRACT.md
TEST_RESULT_AND_HANDOFF_CONTRACT.md
TEST_20A_HANDOFF_VALIDATION_CONTRACT.md
TEST_20B_ACCEPTANCE_CONTRACT.md
TEST_REAL_WORKER_CONTRACT.md
```

## Critical semantic additions

1. Test Leader / Worker behavior is now represented by explicit role-bound operational skills.
2. Test Leader must install `TEST_WORKER_OPERATIONAL_SKILL v0.1` into every Worker.
3. Worker proof and output must prove skill receipt/application.
4. Test Worker lifecycle must be keyed by subagent `thread_id`.
5. MCP / `tools/call` timeout is not Worker failure when `thread_id` exists.
6. Final proof/output acceptance requires matching non-empty `thread_id`.
7. Unnamed compatible worker-creation mechanisms are not accepted; accepted mechanism names are limited to `real_nested_codex_mcp`, `mcp__nested_codex__.codex`, and `codex_cli_verified` unless a future contract/validator names another mechanism.
8. Current root `MODEL_REASONING_BUDGET_POLICY.yaml` profiles with `fallback_allowed: false` forbid fallback. Future fallback is allowed only if the root policy explicitly changes.
9. Proof and audit records use canonical `requested_reasoning_effort`; legacy `requested_reasoning_budget` is accepted only through an explicitly documented compatibility adapter.
10. Worker final outputs use canonical `command_evidence`; legacy `commands_run` is accepted only through an explicitly documented compatibility adapter.

## Recommended validation after apply

From repository root:

```powershell
py -3.13 -m venv .venv-test-skill-phase27a
.\.venv-test-skill-phase27a\Scripts\python.exe -m pip install -U pip
.\.venv-test-skill-phase27a\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-skill-phase27a\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-skill-phase27a\Scripts\python.exe -m compileall .\aegis-runtime\test\aegis_test_runtime
.\.venv-test-skill-phase27a\Scripts\python.exe -m pytest .\aegis-runtime\test -vv

git diff --check
git status --short
```

Static document checks that should pass:

```text
TEST_LEADER_OPERATIONAL_SKILL.md contains TEST_LEADER_OPERATIONAL_SKILL v0.1
TEST_WORKER_OPERATIONAL_SKILL.md contains TEST_WORKER_OPERATIONAL_SKILL v0.1
TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md exists
TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md contains command_evidence
TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md contains requested_reasoning_effort
MANIFEST.yaml no longer lists TEST_LEADER_CONTRACT.md / TEST_WORKER_CONTRACT.md as active role contracts
README.md lists the two old role contracts as superseded and removed
```

## Non-goals

This patch does not add the future Phase 27B runtime validator. A later patch should add:

```text
aegis-runtime/test/aegis_test_runtime/operational_skill.py
aegis-runtime/test/tests/test_phase27a_test_role_operational_skills.py
```

or the corresponding validator/test files after the role-skill document boundary is accepted.
