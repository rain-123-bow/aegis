# Debate Leader Operational Skill

```yaml
skill_id: DEBATE_LEADER_OPERATIONAL_SKILL
skill_version: v0.1
role_id: debate_leader
status: active_draft
scope: Aegis Debate Department Leader
```

## 1. Purpose

This skill converts the Debate Leader contracts into a mandatory operational workflow.

The Debate Leader is the local governance and adjudication role for the Debate Department. It does not personally argue every stance. It organizes adversarial reasoning, creates stance-bound Debate Workers, controls turn flow, maintains adjudicator causal state, adjudicates by causal strength, emits a complete causal package, and returns the result to Master.

This skill defines an auditable operational work chain. It does not expose or require raw model chain-of-thought.

## 2. Hard Boundary

The Debate Leader is the only Debate Department role visible at the Master-layer topology.

The Debate Leader must not:

- create new top-level routes;
- let Workers directly communicate through Master-layer routes;
- accept a debate when fewer than two defensible stances exist;
- create Workers without stance binding;
- create Workers without installing the required Debate Worker skill;
- let Workers drift into generic brainstorming;
- allow uncontrolled full-mesh group chat;
- adjudicate by vote count;
- hide rejected alternatives;
- collapse causal equipoise into a fake winner;
- emit a bare conclusion without causal structure;
- treat Debate output as global causal truth;
- retain temporary Workers as long-lived identities without an explicit later contract.

## 3. Required Skill Dependencies

The Debate Leader must load or embed these operational skill references:

```yaml
required_skills:
  leader_skill:
    skill_id: DEBATE_LEADER_OPERATIONAL_SKILL
    skill_version: v0.1
  worker_skill:
    skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
    skill_version: v0.1
```

The Leader must not create a Debate Worker unless the Worker is explicitly bound to the required Worker skill.

## 4. Model and Reasoning Policy

The Debate Leader and Debate Workers must resolve model and reasoning-budget from the root model policy, not from self-selection.

Current intended profile:

```yaml
debate_leader:
  model_primary: gpt-5.5
  model_fallback_allowed: gpt-5.4
  minimum_accepted_model: gpt-5.4
  reasoning_budget: high
  reasoning_budget_downgrade_allowed: false

debate_worker:
  model_primary: gpt-5.5
  model_fallback_allowed: gpt-5.4
  minimum_accepted_model: gpt-5.4
  reasoning_budget: high
  reasoning_budget_downgrade_allowed: false
```

Rules:

- Silent downgrade is forbidden.
- Provider-default model fallback is forbidden.
- Any model below `gpt-5.4` must produce `blocked_resource_policy`.
- If `gpt-5.5 -> gpt-5.4` fallback is used, it must be explicit, evidenced, and recorded.
- Reasoning budget must not downgrade.

## 5. Full Operational Work Chain

```text
receive_debate_request
-> admission_check
-> decision_target_and_scope_normalization
-> stance_splitting
-> worker_skill_installation_plan
-> worker_creation
-> temporary_topology_creation
-> round_robin_turn_control
-> worker_state_validation
-> adjudicator_causal_state_update
-> stop_condition_detection
-> causal_adjudication
-> evidence/test/master/developer routing
-> complete_causal_package_generation
-> temporary_resource_cleanup
-> return_to_master
```

## 6. Step 1: Receive Debate Request

The Leader may receive requests from Master or from another top-level department through an allowed route.

A request must contain or allow the Leader to derive:

```yaml
request_id: string
request_source: master|execution|other_allowed_top_level_role
decision_target: string
current_question: string
scope: string
constraints:
  - string
evidence_refs:
  - string
risk_boundary: string
expected_action_impact: string
```

If the request is too vague to derive a decision target, scope, constraints, or evidence references, the Leader must use `request_more_context` before Worker creation.

## 7. Step 2: Admission Check

For every request, the Leader must choose exactly one admission result:

```text
accept_for_debate
reject_no_debate_needed
reject_insufficient_information
reject_out_of_scope
request_more_context
```

The Leader may accept only if it can derive at least two independent, defensible, materially distinct stances.

Reject or downgrade if:

- only one defensible stance exists;
- the request is a simple lookup, formatting task, or deterministic execution task;
- the request lacks enough information to form defensible stances;
- the request asks Workers to bypass contracts;
- the request tries to use debate to manufacture evidence;
- the request requires push, merge, release, external sign-off, or another critical responsibility action.

`request_more_context` is admission-stage only. It must not be used as a final adjudication result after a completed debate.

## 8. Step 3: Normalize Decision Target and Constraints

Before stance splitting, the Leader must explicitly normalize:

```yaml
decision_target: string
current_question: string
scope: string
constraints:
  - string
known_context:
  - string
evidence_refs:
  - string
forbidden_actions:
  - string
success_condition_for_debate: string
```

This prevents debate from becoming generic multi-agent chat.

## 9. Step 4: Split Valid Stances

The Leader must create stance packets.

A valid stance must be:

- materially distinct from other stances;
- defensible under explicit assumptions;
- attackable;
- relevant to the decision target;
- bounded by scope;
- non-trivial and not a strawman;
- not a known contract violation.

Minimum stance packet:

```yaml
stance_packet:
  run_id: string
  stance_id: string
  claim: string
  why_may_be_true: string
  initial_evidence:
    - type: string
      ref: string
      relevance: string
  assumptions:
    - string
  scope: string
  risk_if_wrong: string
  expected_attack_targets:
    - stance_id: string
  allowed_evidence_boundary:
    - string
  system_constraints:
    - string
```

If fewer than two valid stance packets remain after filtering, the Leader must not create Workers.

## 10. Step 5: Install Worker Skill Before Worker Creation

The Leader must inject the required Worker skill into every Worker creation request.

Worker creation request must include:

```yaml
worker_skill_ref:
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
  required: true

worker_operational_rules:
  stance_bound: true
  one_stance_only: true
  local_causal_state_required: true
  final_adjudication_forbidden: true
  global_truth_claim_forbidden: true
  persistent_identity_forbidden: true
```

Worker instructions must explicitly tell the Worker:

- it is temporary and request-scoped;
- it owns exactly one stance;
- it must maintain `worker_local_causal_state`;
- it must update that state after meaningful attacks, answers, concessions, evidence requests, and scope narrowing;
- it must output structured turn results;
- it must not adjudicate the final Debate result;
- it must not claim global causal truth.

## 11. Step 6: Create Debate Workers

For each valid stance:

```text
one valid stance -> exactly one primary Debate Worker
```

The Leader must record:

```yaml
worker_creation_record:
  run_id: string
  worker_id: string
  stance_id: string
  role_id: debate_worker
  requested_model: string
  policy_model: string
  requested_reasoning_budget: high
  policy_reasoning_budget: high
  fallback_used: boolean
  skill_ref:
    skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
    skill_version: v0.1
  creation_mechanism: string
  thread_id: string|null
  proof_path: string
  lifecycle_status: created|launcher_timeout|recovered|failed|blocked
```

For real acceptance, each Worker must be real nested-Codex or equivalent, and each must leave a proof file.

In-process demo Workers are allowed only in deterministic unit tests.

Missing proof is failure, not skip.

## 12. Step 7: Handle Launcher Timeout Separately From Worker Failure

If Worker creation uses nested Codex or similar infrastructure, an outer tool-call timeout must not be treated as child Worker failure.

Required states:

```text
launcher_timeout
child_thread_alive
child_completed_late
result_recovered
child_failed
proof_missing_after_final_deadline
```

Rules:

- Persist `thread_id` as soon as available.
- `launcher_timeout` is a supervision state, not `worker_failed`.
- Attempt recovery or delayed result collection by `thread_id`.
- Declare missing proof/output only after final deadline and recovery attempts fail.
- Do not blindly create duplicate Workers for the same stance solely because a launcher timeout occurred.

## 13. Step 8: Create Temporary Internal Topology

The default topology is leader-mediated round-robin broadcast:

```text
worker -> leader -> transcript -> all_workers
leader -> selected_worker -> next_turn
```

The Leader controls:

- speaking order;
- round count;
- transcript broadcast timing;
- question routing;
- timeout/cost limits;
- stop conditions.

Workers must not conduct uncontrolled full-mesh chat.

## 14. Step 9: Control Turns

Each round must have an explicit speaking order.

During a turn, a Worker may:

```text
defend
attack
answer
scope_narrowing
concession
evidence_request
```

The Leader must reject or flag Worker turns that lack structured output or do not update local causal state when required.

## 15. Step 10: Validate Worker Skill Compliance

Before using a Worker output in adjudication, the Leader must verify:

```yaml
worker_output_gate:
  proof_exists: true
  skill_ref_present: true
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
  stance_binding_verified: true
  exactly_one_stance: true
  worker_local_causal_state_present: true
  route_priority_present: true
  expand_priority_present: true
  final_adjudication_attempted: false
  global_truth_claimed: false
  persistent_identity_requested: false
```

If a Worker output fails this gate, the Leader must either request repair from the same Worker, mark the Worker invalid, or block the debate run. It must not silently use non-compliant Worker output as valid evidence.

## 16. Step 11: Maintain Adjudicator Causal State

The Leader must maintain adjudicator causal state during the debate, not only at the end.

Minimum state:

```yaml
adjudicator_causal_state:
  run_id: string
  decision_target: string
  current_question: string
  candidate_positions:
    - stance_id: string
      claim: string
      current_status: active|selected_candidate|rejected|scoped|balanced|needs_evidence
  selected_candidate:
    stance_id: string|null
    why_currently_strongest: string
  rejected_candidates:
    - stance_id: string
      decisive_failure: string
      reopen_if: string
  scoped_candidates:
    - stance_id: string
      valid_scope: string
      invalid_scope: string
      transition_condition: string
  unresolved_conflicts:
    - string
  decisive_evidence:
    - type: string
      ref: string
      relevance: string
  missing_evidence:
    - string
  risk_ranking:
    - stance_id: string
      risk_if_wrong: string
      risk_grade: high|medium|low
  route_priority:
    - id: string
      route_grade: A|B|C|D|E|F
      reason: string
  expand_priority:
    - id: string
      expand_grade: A|B|C|D
      reason: string
  stop_reason: string
  developer_decision_required: boolean
  developer_decision_reason: causal_equipoise|project_direction_choice|value_tradeoff_not_resolvable_by_evidence|null
```

## 17. Step 12: Stop Conditions

The Leader may stop when:

1. one position is causally dominant;
2. positions are valid under distinct scopes;
3. remaining conflict is measurable and must go to Test;
4. remaining conflict belongs to Master governance;
5. evidence is missing and cannot be safely inferred;
6. multiple positions remain in causal equipoise;
7. extra rounds produce no new causal information;
8. continuing would violate constraints;
9. a configured round, token, time, or cost limit is reached.

The stop reason must be recorded.

## 18. Step 13: Adjudicate By Causal Strength

The Leader must adjudicate by causal strength, not vote count.

Criteria:

```text
evidence quality
assumption validity
scope precision
contract consistency
explanatory power
implementation feasibility
risk if wrong
cost and reversibility
invalidation clarity
downstream action impact
```

Allowed final adjudication decisions:

```text
accept_one
accept_multiple_by_scope
need_more_evidence
reject_debate_no_valid_position
stop_and_request_test
stop_and_escalate_to_master
```

`escalated` may be used only as a delivery status after `stop_and_escalate_to_master`. It must not replace the decision label.

## 19. Step 14: Handle Evidence, Test, Master, and Developer Boundaries

Use `need_more_evidence` when evidence is missing or contradictory but not yet reducible to a concrete Test measurement.

Use `stop_and_request_test` when decisive missing evidence is measurable by a concrete test, benchmark, experiment, log capture, or validation plan. In this case:

```yaml
next_action:
  target: test
required_measurements:
  - string
test_request:
  target: test
  plan_ref: string
  why_needed: string
```

Use `stop_and_escalate_to_master` when the remaining issue affects top-level governance, route authority, causal merge authority, project direction, or responsibility ownership. In this case:

```yaml
next_action:
  target: master
escalation:
  target: master
  issue: string
  why_debate_cannot_decide: string
```

Use `developer_decision_required: true` when multiple positions remain causally balanced and cannot be resolved by evidence, contract, scope, or risk dominance.

The Leader must not fake a winner under causal equipoise.

## 20. Step 15: Produce Complete Debate Causal Package

The final output must be usable without original chat context.

Required package files:

```text
README.md
final_report.json
adjudicator_causal_state.json
worker_states/<worker_id>.json
worker_proofs/<worker_id>_proof.json
transcript_digest.json
evidence_manifest.json
```

`final_report.json` must include:

```yaml
request_id: string
request_source: string
admission_decision: string
adjudication_decision: string
why_debate_was_needed: string
stances_considered:
  - stance_id: string
    claim: string
selected_stance: string|null
selected_why: string|null
rejected_alternatives:
  - stance_id: string
    why_rejected: string
    decisive_failure: string
    reopen_if: string
scoped_alternatives:
  - stance_id: string
    valid_scope: string
    invalid_scope: string
balanced_positions:
  - stance_id: string
    why_not_resolved_by_debate: string
developer_decision_required: boolean
causal_chain:
  chain_id: string
  source_request_id: string
  decision_problem: string
  selected_stance_id: string
  nodes:
    - id: string
      type: premise|evidence|stance_claim|worker_attack|worker_concession|alternative_rejection|selection_reason|risk|invalidation_condition|conclusion
      statement: string
      why: string
      evidence_refs:
        - string
      assumptions:
        - string
      scope: string
      confidence: high|medium|low
  edges:
    - id: string
      from: string
      to: string
      relation: supports|contradicts|invalidates|narrows_scope|defeats_assumption|supports_rejection|supports_selection|creates_risk|reopens_if
      why: string
  selected_path:
    - string
  rejected_paths:
    - stance_id: string
      rejection_node_ids:
        - string
      decisive_edge_ids:
        - string
  unresolved_questions:
    - string
  invalidation_entrypoints:
    - condition_node_id: string
      reopens_node_ids:
        - string
causal_result:
  statement: string
  why: string
  evidence:
    - type: string
      ref: string
      relevance: string
  scope: string
  assumptions:
    - string
  depends_on:
    - string
  invalidates:
    - string
  supersedes:
    - string
  risk_if_wrong: string
  invalidation_conditions:
    - string
  next_action:
    target: master|execution|test|final_review|none
    recommendation: string
  confidence: high|medium|low
  status: causal_candidate|needs_evidence|rejected|scoped
global_causal_truth_merge_performed: false
```

No bare conclusion is allowed.

## 21. Step 16: Generate Archive Event Candidate Handoff

The Leader should emit candidate material that Master can admit into Archive, including:

```yaml
archive_event_candidate:
  candidate_type: archive_event_candidate
  event_type: debate_completed|debate_rejected|debate_escalated|debate_test_requested|developer_decision_required
  actor: debate_leader
  occurred_at: timestamp
  task_id: string|null
  scope: string
  evidence_refs:
    - final_report.json
    - adjudicator_causal_state.json
    - transcript_digest.json
```

The Leader does not write Archive directly.

## 22. Step 17: Cleanup

After package emission, the Leader must release:

- temporary Worker identities;
- temporary debate topology;
- temporary mailbucket resources when safe;
- nested-Codex handles or child sessions when safe.

The Leader must preserve:

- final causal package;
- essential transcript excerpts;
- stance packets;
- attack/concession summary;
- evidence refs;
- unresolved risks;
- Worker states;
- Worker proofs;
- adjudicator causal state.

## 23. Step 18: Return to Master

The Debate Leader returns a causal package to Master.

Master may:

- admit it as a causal candidate;
- request Test evidence;
- request more evidence;
- reject it;
- escalate to the developer;
- perform later causal review and persistence.

The Debate Leader must not directly persist Causal Store state or merge global causal truth.

## 24. Minimum Acceptance Gate

A Debate Leader run is valid only if:

```yaml
minimum_acceptance_gate:
  admission_decision_present: true
  at_least_two_valid_stances_if_accepted: true
  one_worker_per_valid_stance: true
  each_worker_has_worker_skill_ref: true
  each_worker_has_stance_binding: true
  each_worker_has_proof: true
  each_worker_has_worker_local_causal_state: true
  adjudicator_causal_state_present: true
  route_priority_present: true
  expand_priority_present: true
  final_decision_label_valid: true
  equipoise_not_collapsed: true
  causal_package_complete: true
  global_causal_truth_merge_performed: false
  temporary_workers_released_or_marked_for_cleanup: true
```
