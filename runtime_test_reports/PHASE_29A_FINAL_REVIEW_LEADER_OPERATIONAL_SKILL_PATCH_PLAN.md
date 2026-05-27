# Phase 29A Final Review Leader Operational Skill Patch Plan

## Verdict Target

```text
accepted_phase29a_final_review_leader_operational_skill_document_boundary
```

## Purpose

Phase 29A converts the Final Review Leader role contract into a role-bound operational skill while preserving the current Final Review architecture:

```text
test -> final_review -> master
single Final Review Leader
no internal Final Review Workers
```

## Patch Scope

Added:

```text
aegis-master-kit/organization/departments/final_review/FINAL_REVIEW_LEADER_OPERATIONAL_SKILL.md
runtime_test_reports/PHASE_29A_FINAL_REVIEW_LEADER_OPERATIONAL_SKILL_PATCH_PLAN.md
```

Modified:

```text
README.md
aegis-master-kit/organization/departments/final_review/README.md
aegis-master-kit/organization/departments/final_review/MANIFEST.yaml
aegis-master-kit/organization/departments/final_review/schemas/final_review_input_package.schema.yaml
aegis-master-kit/organization/departments/final_review/schemas/final_review_result.schema.yaml
aegis-master-kit/organization/departments/final_review/templates/final_review_result.md
```

Removed:

```text
aegis-master-kit/organization/departments/final_review/FINAL_REVIEW_LEADER_CONTRACT.md
```

## Skill Boundary

The skill requires:

- single Final Review Leader only;
- no internal Final Review Workers;
- no parallel reviewer fanout;
- route table preserved as `test -> final_review` and `final_review -> master`;
- `resource_policy_ref` resolved into `resource_policy` before substantive review;
- resource-policy failure returns `blocked_resource_policy` before whole-chain review starts;
- Debate applicability explicit through `debate_applicability`;
- whole-chain review exposed as auditable `whole_chain_review`;
- `status: final_review_recommendation` in final result;
- no push / PR / merge / release / deployment / external sign-off / production store write / global causal truth merge.

## Schema / Template Synchronization

The patch synchronizes the following with the role skill:

```text
schemas/final_review_input_package.schema.yaml
schemas/final_review_result.schema.yaml
templates/final_review_result.md
```

Required synced fields include:

```text
whole_chain_review
debate_applicability
no_debate_used_reason
requested_reasoning_budget
resolved_reasoning_budget
dynamic_adjustment_used
material_conditions
assumptions
status: final_review_recommendation
```

Resource-blocked results must expose:

```yaml
whole_chain_review:
  status: not_started
  graph_built: false
  not_started_reason: blocked_resource_policy
```

Non-resource-blocked results must expose:

```yaml
whole_chain_review:
  status: completed
  graph_built: true
```

## Validation Plan

From repo root:

```powershell
# Package application
py -3.13 .\apply_phase29a_final_review_leader_operational_skill_patch.py --repo-root C:\Users\playm\Documents\self-git\aegis --dry-run
py -3.13 .\apply_phase29a_final_review_leader_operational_skill_patch.py --repo-root C:\Users\playm\Documents\self-git\aegis

# Static checks
git diff --check
git status --short
```

Static document audit should verify:

```text
No generated artifacts anywhere in package
SHA256SUMS passes
FINAL_REVIEW_LEADER_OPERATIONAL_SKILL.md exists
FINAL_REVIEW_LEADER_CONTRACT.md removed
MANIFEST skills.leader points to FINAL_REVIEW_LEADER_OPERATIONAL_SKILL.md
MANIFEST no longer lists contracts.leader
README references role-bound operational skill
final_review_result.schema.yaml includes whole_chain_review
final_review_result.schema.yaml includes debate_applicability
final_review_result.schema.yaml includes no_debate_used_reason
final_review_result.schema.yaml enforces resource-blocked graph not-started state
final_review_result.schema.yaml enforces non-resource-blocked graph completed state
final_review_result.schema.yaml uses requested_reasoning_budget / resolved_reasoning_budget
final_review_input_package.schema.yaml includes debate_applicability and no_debate_used_reason
templates/final_review_result.md includes whole_chain_review and debate applicability fields
root README includes Phase 29A status
```

## Non-Goals

Phase 29A does not implement:

- runtime validator;
- production Final Review lifecycle supervision;
- production release review;
- durable artifact backend;
- remote branch governance;
- route changes;
- router changes;
- root model policy changes;
- remote push / PR / merge / release / deployment;
- global causal truth merge.
