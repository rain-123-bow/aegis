# Test Leader / Worker Skill Enforcement Contract

```yaml
contract_id: TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT
version: v0.1
phase: phase27a_test_role_operational_skills
```

## 1. Purpose

Phase 27A replaces the superseded Test Leader / Worker role contracts with role-bound operational skills:

```text
TEST_LEADER_OPERATIONAL_SKILL.md
TEST_WORKER_OPERATIONAL_SKILL.md
```

This contract defines the minimum validation boundary for a Test run that claims to use those skills.

It validates role-skill usage and work-chain evidence only. It does not perform production Test lifecycle closure, production CI, durable environment provisioning, remote branch governance, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.

## 2. Required skill binding

A valid Test Leader run must reference:

```yaml
skill_ref:
  skill_id: TEST_LEADER_OPERATIONAL_SKILL
  skill_version: v0.1
```

Every Test Worker creation request produced by the Test Leader must include:

```yaml
worker_skill_ref:
  skill_id: TEST_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
  required: true
```

Every Worker proof and Worker output must include:

```yaml
skill_ref:
  skill_id: TEST_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
skill_received: true
skill_applied: true
```

## 3. Thread identity hard rule

Worker lifecycle status must be judged by subagent `thread_id`, not by whether the outer MCP / `tools/call` launcher returned before timeout.

```text
launcher_timeout != worker_failed
thread_id is the Worker lifecycle identity key
```

A skill-enforced Test run must prove:

- the Leader persists `thread_id` as soon as it is available;
- launcher timeout with captured `thread_id` is recorded as `launcher_timeout`, not `worker_failed`;
- the Leader does not create a duplicate Worker for the same route solely because launcher timeout occurred;
- final Worker proof includes non-empty `thread_id`;
- final Worker output includes non-empty `thread_id`;
- Leader creation record, Worker proof, and Worker output use the same `thread_id`;
- missing proof/output is accepted as failure only after final deadline and recovery attempts fail.

## 4. Leader obligations

The Test Leader must:

- accept only Execution implementation candidate handoffs under the current topology;
- reject, block, or request context when minimum handoff material is missing;
- perform governance blocker checks before route execution;
- validate handoff material before testing;
- design a reproducible test plan before creating Workers;
- split routes only when validation purpose and independence are justified;
- create exactly one Test Worker per accepted route;
- install `TEST_WORKER_OPERATIONAL_SKILL v0.1` into every Worker;
- supervise Workers by `thread_id`;
- audit Worker proof and Worker output before aggregation;
- aggregate route evidence by strict evidence-state semantics;
- preserve reproducibility set and artifact manifest;
- send failed / inconclusive / ordinary blocked / missing context material to Execution Leader;
- send passed / passed_with_scope_limit / governance-review material to Final Review;
- never send passed results directly to Master under the current topology;
- never claim global causal truth from Test output.

## 5. Worker obligations

Every Test Worker must:

- receive exactly one accepted route assignment;
- verify that it received and applied `TEST_WORKER_OPERATIONAL_SKILL v0.1`;
- preserve its `thread_id` in proof and output;
- write proof before substantive route work;
- execute only assigned commands or inspection steps;
- capture command evidence, logs, artifacts, actual environment, and route observations;
- classify route result by evidence state;
- provide advisory owner hints only when safely inferable;
- emit structured route evidence to Test Leader;
- never decide whole-candidate acceptance;
- never modify implementation code;
- never send feedback directly to Execution;
- never route directly to Master;
- never push, PR, merge, release, deploy, sign off production readiness, or claim global causal truth.


## 6. Field compatibility rules

### 6.1 Reasoning effort field

Role-skill proof, Worker creation, Worker output, and Leader audit records must use the canonical requested reasoning field:

```yaml
requested_reasoning_effort: high
```

`requested_reasoning_budget` is not the canonical Phase 27A role-skill field and must not replace `requested_reasoning_effort` in accepted proof, Worker creation, Worker output, or Leader audit records.

A compatibility adapter may read legacy `requested_reasoning_budget` only when the adapter is explicitly documented and maps it into canonical `requested_reasoning_effort` before role-skill validation.

A Phase 27A role-skill validator must reject proof, Worker creation, Worker output, or Leader audit records that expose only `requested_reasoning_budget` and omit `requested_reasoning_effort`.

### 6.2 Worker command evidence field

Role-skill-compliant Worker final outputs must use the canonical field:

```yaml
command_evidence:
  - command: string
    exit_code: integer
    stdout_ref: string
    stderr_ref: string
```

`commands_run` is a legacy runtime/model field and must not be used as the final role-skill Worker output field.

A compatibility adapter may read legacy `commands_run` only when the adapter is explicitly documented and maps it into canonical `command_evidence` before role-skill validation.

A Phase 27A role-skill validator must reject Worker final outputs that expose only `commands_run` and omit `command_evidence`.

## 7. Required validation result

A skill-enforced Test run validation result should include:

```yaml
test_skill_validation_result_id: string
phase: phase27a_test_role_operational_skills
status: validated|rejected
decision: accepted_test_role_skill_enforcement|rejected
reason: string
leader_skill_ref:
  skill_id: TEST_LEADER_OPERATIONAL_SKILL
  skill_version: v0.1
worker_skill_ref:
  skill_id: TEST_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
route_count: integer
worker_creation_count: integer
worker_proof_count: integer
worker_output_count: integer
violations:
  - field: string
    reason: string
leader_skill_installed: boolean
worker_skill_installation_verified: boolean
thread_id_supervision_verified: boolean
worker_proofs_verified: boolean
worker_outputs_verified: boolean
evidence_state_aggregation_verified: boolean
reproducibility_set_verified: boolean
artifact_manifest_verified: boolean
global_causal_truth_merge_performed: false
production_store_write_performed: false
remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
deployment_performed: false
external_signoff_performed: false
created_at: string
```

## 8. Rejection conditions

The validator must reject when:

- the Leader skill reference is missing or wrong;
- a Worker creation request lacks `worker_skill_ref`;
- a Worker proof lacks `TEST_WORKER_OPERATIONAL_SKILL v0.1`;
- a Worker output lacks `TEST_WORKER_OPERATIONAL_SKILL v0.1`;
- a Worker proof or output lacks `skill_received: true` / `skill_applied: true`;
- a final Worker proof lacks non-empty `thread_id`;
- a final Worker output lacks non-empty `thread_id`;
- a Worker creation, proof, output, or Leader audit record omits canonical `requested_reasoning_effort`;
- a Worker creation, proof, output, or Leader audit record uses only legacy `requested_reasoning_budget` without an explicit compatibility adapter mapping to `requested_reasoning_effort`;
- Leader creation record, Worker proof, and Worker output have mismatched `thread_id`;
- the Leader treats launcher timeout as Worker failure while `thread_id` exists;
- the Leader creates duplicate Workers for the same route solely due to launcher timeout;
- a Worker final output omits canonical `command_evidence`;
- a Worker final output uses only legacy `commands_run` without an explicit compatibility adapter mapping to `command_evidence`;
- a Worker handles more than one route;
- a Worker modifies implementation code;
- a Worker decides whole-candidate acceptance;
- proven failure is downgraded to inconclusive because owner assignment is ambiguous;
- `passed_with_scope_limit` is used while a mandatory route failed, was blocked, or was inconclusive;
- a passed result hides uncovered material scope;
- the run sends passed results directly to Master under the current topology;
- production, push, PR, merge, release, deployment, external sign-off, production store write, or global truth flags are true.

## 9. Superseded role contracts

The following old role-contract files are superseded by the two operational skills and should be removed by the Phase 27A patch:

```text
TEST_LEADER_CONTRACT.md
TEST_WORKER_CONTRACT.md
```

The Test Department package keeps non-role support files such as department contract, plan/route split, evidence retention, result handoff, Phase 20A handoff validation, Phase 20B acceptance, real worker acceptance, schemas, templates, and constraint tests until later phases decide whether they should also become skills.

## 10. Acceptance label

A successful Phase 27A validation may be labeled:

```text
accepted_test_role_skill_enforcement
```

It must not be labeled:

```text
accepted_real_test_worker_closure
production_test_lifecycle_closure
production_ci_closure
global_causal_truth_merge_closure
```
