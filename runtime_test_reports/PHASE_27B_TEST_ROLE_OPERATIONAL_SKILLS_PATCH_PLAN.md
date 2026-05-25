# Phase 27B Test Role Operational Skills Runtime Validator Patch Plan

## Verdict

This patch adds a local deterministic runtime validator for Phase 27A Test Leader / Worker operational skills and updates the root README to reflect Phase 27A and Phase 27B status.

## Scope

Phase 27B validates role-skill runtime artifacts for:

```text
TEST_LEADER_OPERATIONAL_SKILL.md
TEST_WORKER_OPERATIONAL_SKILL.md
TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md
```

It does not implement production Test lifecycle closure, production CI, durable environment provisioning, external artifact backend, remote branch governance, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.

## Files Added

```text
aegis-runtime/test/aegis_test_runtime/operational_skill.py
aegis-runtime/test/tests/test_phase27b_test_role_operational_skills.py
runtime_test_reports/PHASE_27B_TEST_ROLE_OPERATIONAL_SKILLS_PATCH_PLAN.md
```

## Files Modified

```text
README.md
aegis-master-kit/organization/departments/test/README.md
aegis-master-kit/organization/departments/test/MANIFEST.yaml
aegis-runtime/test/aegis_test_runtime/__init__.py
aegis-runtime/test/pyproject.toml
```

## Runtime Validator Gates

The validator rejects when:

- Leader skill reference is missing or wrong.
- Worker creation lacks `TEST_WORKER_OPERATIONAL_SKILL v0.1`.
- Worker proof/output lacks skill receipt/application evidence.
- Worker lifecycle lacks non-empty `thread_id`.
- Leader treats `launcher_timeout` as Worker failure while `thread_id` exists.
- Leader creates a duplicate Worker for the same route solely due to launcher timeout.
- Worker proof/output `thread_id` does not match Leader creation record.
- Proof, creation, output, or Leader audit omits canonical `requested_reasoning_effort`.
- Legacy `requested_reasoning_budget` is used without explicit adapter to `requested_reasoning_effort`.
- Worker output omits canonical `command_evidence`.
- Legacy `commands_run` is used without explicit adapter to `command_evidence`.
- Creation mechanism is not one of `real_nested_codex_mcp`, `mcp__nested_codex__.codex`, or `codex_cli_verified`.
- Worker modifies implementation code.
- Worker decides whole-candidate acceptance.
- Proven failure is downgraded to inconclusive because owner assignment is ambiguous.
- `passed_with_scope_limit` is used while a mandatory route failed, blocked, or was inconclusive.
- `passed` hides uncovered material scope.
- Test routes directly to Master.
- Production, push, PR, merge, release, deployment, external sign-off, store write, or global truth flags are true.

## Validation Commands

From repository root on Windows PowerShell:

```powershell
py -3.13 -m venv .venv-test-skill-phase27b
.\.venv-test-skill-phase27b\Scripts\python.exe -m pip install -U pip
.\.venv-test-skill-phase27b\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-skill-phase27b\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-skill-phase27b\Scripts\python.exe -m compileall .\aegis-runtime\test\aegis_test_runtime
.\.venv-test-skill-phase27b\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_phase27b_test_role_operational_skills.py -vv
.\.venv-test-skill-phase27b\Scripts\python.exe -m pytest .\aegis-runtime\test -vv
git diff --check
git status --short
```

Expected targeted Phase 27B result:

```text
35 passed
```

## CLI Smoke

```powershell
.\.venv-test-skill-phase27b\Scripts\python.exe -m aegis_test_runtime.operational_skill validate `
  --run .\local_artifacts\phase27b_test_skill\valid_test_skill_run.json `
  --leader-skill .\aegis-master-kit\organization\departments\test\TEST_LEADER_OPERATIONAL_SKILL.md `
  --worker-skill .\aegis-master-kit\organization\departments\test\TEST_WORKER_OPERATIONAL_SKILL.md `
  --enforcement-contract .\aegis-master-kit\organization\departments\test\TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md `
  --output .\local_artifacts\phase27b_test_skill\validation_result.json
```

A valid result has:

```yaml
status: validated
decision: accepted_test_role_skill_runtime_validation
violations: []
```

## Boundary

Phase 27B proves local role-skill artifact validation only. It does not replace Phase 20A/20B runtime evidence and does not create production Test lifecycle authority.
