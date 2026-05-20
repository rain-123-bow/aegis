# Debate Leader / Worker Skill Enforcement Contract

## 1. Purpose

Phase 25A replaces the superseded Debate Leader / Worker role contracts with role-bound operational skills:

```text
DEBATE_LEADER_OPERATIONAL_SKILL.md
DEBATE_WORKER_OPERATIONAL_SKILL.md
```

This contract defines the minimum validation boundary for a Debate run that claims to use those skills.

It is not production Debate lifecycle closure and does not create new top-level routes, production store writes, remote push, PR, merge, release, or global causal truth merge.

## 2. Required skill binding

A valid Debate Leader run must reference:

```yaml
skill_ref:
  skill_id: DEBATE_LEADER_OPERATIONAL_SKILL
  skill_version: v0.1
```

Every Worker creation request produced by the Debate Leader must include:

```yaml
worker_skill_ref:
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
  required: true
```

Every Worker proof and Worker output must include:

```yaml
skill_ref:
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
skill_received: true
skill_applied: true
```

## 3. Leader obligations

The Debate Leader must:

- perform admission before Worker creation;
- reject or request more context when fewer than two defensible stances exist;
- create stance packets before Workers;
- create exactly one Worker per valid stance;
- install the Worker skill into every Worker;
- use a leader-mediated topology, not uncontrolled group chat;
- validate Worker skill compliance before adjudication;
- maintain adjudicator causal state throughout the run;
- adjudicate by causal strength, not vote count;
- preserve equipoise instead of inventing a winner;
- emit a complete causal package;
- release or mark temporary resources for cleanup;
- return to Master without claiming global causal truth.

## 4. Worker obligations

Every Debate Worker must:

- receive exactly one stance packet;
- verify that it received the Worker skill;
- maintain `worker_local_causal_state`;
- preserve route priority and expand priority;
- defend its assigned stance from first principles;
- attack competing stances causally, not rhetorically;
- answer attacks and update local causal state;
- narrow scope when required;
- request evidence when required;
- concede only with a causal reason;
- emit structured turn output;
- emit final worker state for Leader adjudication;
- never adjudicate the final Debate result;
- never claim global causal truth;
- never request persistent identity by default.

## 5. Required validation result

A skill-enforced Debate run validation result must include:

```yaml
debate_skill_validation_result_id: string
phase: phase25a_debate_role_operational_skills
status: validated|rejected
decision: accepted_debate_role_skill_enforcement|rejected
reason: string
leader_skill_ref:
  skill_id: DEBATE_LEADER_OPERATIONAL_SKILL
  skill_version: v0.1
worker_skill_ref:
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
stance_count: integer
worker_creation_count: integer
worker_output_count: integer
violations:
  - field: string
    reason: string
leader_skill_installed: boolean
worker_skill_installation_verified: boolean
worker_skill_outputs_verified: boolean
adjudicator_causal_state_verified: boolean
causal_package_verified: boolean
global_causal_truth_merge_performed: false
production_store_write_performed: false
remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
created_at: string
```

## 6. Rejection conditions

The validator must reject when:

- the Leader skill reference is missing or wrong;
- an accepted Debate has fewer than two valid stances;
- a valid stance has no Worker creation request;
- a Worker creation request lacks `worker_skill_ref`;
- a Worker output lacks the Worker skill reference;
- a Worker output lacks `worker_local_causal_state`;
- route priority or expand priority is missing;
- a Worker attempts final adjudication;
- a Worker claims global truth;
- a Worker requests persistent identity by default;
- adjudicator causal state is missing;
- final package files are incomplete;
- equipoise is marked but developer decision is not preserved;
- production, push, PR, merge, release, or global truth flags are true.

## 7. Superseded role contracts

The following old role-contract files are superseded by the two operational skills and should be removed by the Phase 25A patch:

```text
DEBATE_LEADER_CONTRACT.md
DEBATE_WORKER_CONTRACT.md
DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md
DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md
ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md
```

The Debate Department package may keep non-role support files such as lifecycle, topology, mailbucket package, schemas, templates, and rationale files until later phases decide whether they should also become skills.
