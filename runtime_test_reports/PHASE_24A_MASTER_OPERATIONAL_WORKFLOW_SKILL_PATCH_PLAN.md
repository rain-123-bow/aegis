# Phase 24A Master Operational Workflow Skill Patch Plan

## Goal

Convert the current Master-facing contract set into a role-bound Master operational workflow skill and add a deterministic runtime validator that rejects Master cycle artifacts that do not show skill usage.

## Why

Real-project trial exposed that passive contracts are not enough:

- Master did not automatically extract Knowledge candidates from user communication.
- Master did not automatically create or bind Archive tasks.
- Execution branch/workspace requirements were treated as prompt guidance rather than hard gates.
- Nested-Codex outer tool timeout could be misinterpreted as child agent failure.
- Model policy needed explicit gpt-5.5 -> gpt-5.4 fallback semantics while preserving reasoning budget.

## Files added

```text
aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL.md
aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL_ENFORCEMENT_CONTRACT.md
aegis-runtime/master/aegis_master_runtime/operational_skill.py
aegis-runtime/master/tests/test_phase24a_master_operational_workflow_skill.py
runtime_test_reports/PHASE_24A_MASTER_OPERATIONAL_WORKFLOW_SKILL_PATCH_PLAN.md
runtime_test_reports/PHASE_24A_MASTER_OPERATIONAL_WORKFLOW_SKILL_ACCEPTANCE_REPORT.md
```

## Files modified

```text
MODEL_REASONING_BUDGET_POLICY.yaml
aegis-runtime/master/aegis_master_runtime/__init__.py
aegis-runtime/master/aegis_master_runtime/cli.py
README.md
```

## Boundary

Phase 24A does not implement production autonomy, production scheduling, remote push, PR creation, remote merge, release, external sign-off, or global causal truth merge.

## Acceptance

Expected validation:

```text
python -m compileall aegis-runtime/master/aegis_master_runtime
python -m pytest aegis-runtime/master/tests/test_phase24a_master_operational_workflow_skill.py -vv
```

Expected result:

```text
19 passed
```
