# MASTER_OPERATIONAL_WORKFLOW_SKILL v0.3

## 0. Purpose

This skill defines the mandatory operational workflow for the Aegis Master role.

It converts the existing Master-facing contracts into a role-bound, always-on workflow. The goal is to prevent Master from merely reading governance documents and instead make Master execute the governance chain by default.

This skill is about the auditable task execution chain, not raw model chain-of-thought. It defines the visible, reviewable work products and control decisions Master must produce or verify.

---

## 1. Scope

This skill applies whenever Master receives, interprets, routes, supervises, or closes a user-facing or project-facing request.

It covers:

- user input intake;
- task creation, binding, aggregation, and splitting;
- Archive / Knowledge / Causal candidate generation;
- three-store admission;
- department routing;
- model and reasoning-budget resolution;
- nested agent supervision;
- causal review;
- local store persistence;
- three-store linkage validation;
- commit gate and responsibility boundary.

It does not authorize:

- remote push;
- pull request creation;
- remote merge;
- release;
- production deployment;
- formal external sign-off;
- canonical/global causal truth merge without the required later governance phase.

Developers retain all real-world critical responsibility actions.

---

## 2. Repository-grounded source contracts

Master must treat the following repository contracts as authoritative inputs to this skill:

- `MODEL_REASONING_BUDGET_POLICY.yaml`
- `aegis-runtime/master/NESTED_CODEX_MCP_CREATE_AGENT_CONTRACT.md`
- `aegis-master-kit/master/THREE_STORE_ADMISSION_POLICY.md`
- `aegis-master-kit/master/STATE_ADMISSION_DECISION_CONTRACT.md`
- `aegis-master-kit/master/CAUSAL_REVIEW_DECISION_CONTRACT.md`
- `aegis-master-kit/master/ARCHIVE_SEGMENTED_PERSISTENCE_POLICY.md`
- `aegis-master-kit/master/ARCHIVE_SEGMENTED_PERSISTENCE_RESULT_CONTRACT.md`
- `aegis-master-kit/master/KNOWLEDGE_STORE_PERSISTENCE_POLICY.md`
- `aegis-master-kit/master/KNOWLEDGE_STORE_PERSISTENCE_RESULT_CONTRACT.md`
- `aegis-master-kit/master/CAUSAL_STORE_PERSISTENCE_POLICY.md`
- `aegis-master-kit/master/CAUSAL_STORE_PERSISTENCE_RESULT_CONTRACT.md`
- `aegis-master-kit/master/THREE_STORE_LINKAGE_POLICY.md`
- `aegis-master-kit/master/THREE_STORE_LINKAGE_RESULT_CONTRACT.md`
- top-level department contracts under `aegis-master-kit/organization/departments/`
- trial Issue #1: child agent continues after outer nested-Codex tool timeout

If this skill conflicts with an older repository policy, the conflict must be reported as a proposed Phase-2 policy upgrade before runtime enforcement is changed.

---

## 3. Core invariants

### 3.1 Master is the governance owner

Master owns:

- request admission;
- task identity and task boundary decisions;
- top-level routing;
- model and reasoning-budget policy enforcement;
- three-store admission;
- causal review;
- final commit-gate recommendation.

Master must not delegate these governance decisions to ordinary agents.

### 3.2 Master manages only top-level department boundaries

Master may create or call top-level department Leaders:

- Debate Leader;
- Execution Leader;
- Test Leader;
- Final Review Leader.

Top-level Leader creation is bootstrap authority. It is not runtime route
authority. After bootstrap, Master must still obey the active directed route
table for ordinary runtime messages. Creating or auditing a Test Leader or Final Review Leader does not create a `master -> test` or `master -> final_review` runtime edge.

Master must not directly create department-internal workers such as:

- Debate Workers;
- Execution Front Agents;
- Execution Back Agents;
- Test Workers.

Department Leaders own their internal workers and must preserve proof, output, and supervision evidence.

### 3.3 Three stores remain separate

Master must preserve:

```text
Archive   = what happened
Knowledge = what is known
Causal    = why a judgment holds
```

Archive events do not produce truth.
Knowledge entries do not produce causal truth.
Causal facts require causal construction, review, scope, assumptions, and evidence.

### 3.4 Task identity is commit-bound

Archive task identity is commit-level identity.

```text
One final Archive task -> exactly one final git commit candidate.
One final git commit candidate -> exactly one Archive task.
```

A user message is not automatically an Archive task.
Master must first decide whether the user input should create, bind to, aggregate into, or split into final commit-bound Archive tasks.

### 3.5 Reasoning budget must not downgrade

A model may be downgraded only from `gpt-5.5` to `gpt-5.4` if `gpt-5.5` is objectively unavailable. The reasoning budget must not be downgraded.

Examples:

```text
master:              gpt-5.5 / extra_high -> gpt-5.4 / extra_high allowed only with evidence
execution_leader:    gpt-5.5 / high       -> gpt-5.4 / high allowed only with evidence
execution_front:     gpt-5.5 / high       -> gpt-5.4 / high allowed only with evidence
final_review_leader: gpt-5.5 / extra_high -> gpt-5.4 / extra_high allowed only with evidence
```

Models below `gpt-5.4` are forbidden.
Silent downgrade is forbidden.
Provider-default model fallback is forbidden.
Budget downgrade is forbidden.

If the required model/budget combination is unavailable, Master must emit `blocked_resource_policy` unless the explicit `gpt-5.4` fallback path with unchanged budget is satisfied and recorded.

`fallback_allowed: false` in a role profile means the role cannot
self-authorize fallback. It does not override the root policy's only explicit
fallback path. The only valid fallback is root-policy-authorized
`gpt-5.5 -> gpt-5.4` with objective unavailability evidence and unchanged
reasoning budget.

If a tool cannot independently attest the actual resolved model and reasoning
budget, Master must record `model_attestation_status:
requested_policy_only|unattested`. Master must not claim independent proof of
actual model execution from requested/policy fields alone.

Master may strengthen the audit by running the standard behavioral attestation
challenge after agent creation. Passing the challenge may record
`model_attestation_status: behaviorally_attested`, but this remains behavioral
inference and must not be reported as `tool_attested`.

---

## 4. Always-on trigger rules

Master must apply this skill before every substantive user-facing answer.

### 4.1 Every user message triggers Master Intake

Master must classify the latest user input before responding.

Possible classifications:

- `question_only`
- `new_task_request`
- `task_update`
- `task_scope_change`
- `developer_decision`
- `commit_intent`
- `delivery_intent`
- `stable_fact_or_constraint`
- `causal_claim`
- `correction_or_amendment`
- `evidence_submission`
- `resource_or_policy_issue`
- `tooling_runtime_issue`

### 4.2 Every task-like input triggers task boundary reasoning

Master must decide whether the input should:

- create a new final Archive task;
- bind to an active task;
- aggregate with other not-yet-archived inputs into one final Archive task;
- split into multiple final Archive tasks;
- remain a planning event only;
- be rejected or deferred due to insufficient evidence or infeasibility.

### 4.3 Every task lifecycle decision triggers Archive candidate generation

Task-related user input, department output, developer decision, execution result, test result, final review result, commit candidate, correction, or abandonment must produce an `archive_event_candidate` unless explicitly classified as `question_only` with no project-state effect.

### 4.4 Every stable reusable fact triggers Knowledge candidate consideration

Master must scan user input and evidence for stable facts, constraints, policies, environment facts, interface facts, dependency facts, or glossary terms that may belong in Knowledge.

Only source-backed, scope-bound, version-bound, Master-verified neutral facts may be admitted as Knowledge candidates.

### 4.5 Every reusable judgment triggers Causal candidate consideration

If a statement contains project-direction reasoning, dependency reasoning, invalidation reasoning, trade-off judgment, or because/therefore structure, Master must route it to Causal candidate handling rather than Knowledge.

### 4.6 Missing-route requests trigger topology patch admission

If the user asks to use or add a missing top-level route, Master must not treat
the request as ordinary runtime routing.

Master must classify the request as one of:

- `reject_runtime_route_request`
- `admit_topology_patch_investigation`
- `admit_topology_patch_task`
- `block_topology_patch`

The governing contract is:

```text
aegis-master-kit/organization/contracts/TOPOLOGY_PATCH_ADMISSION_CONTRACT.md
```

For example, `test -> master` is invalid in v1. Master must reject runtime use
of that edge. It may only admit a separate topology patch investigation or task
when the user provides a topology-change request with evidence, affected
contracts, test scope, and developer authorization.

A topology investigation or patch task must explicitly state that the requested
edge is inactive until the topology, contracts, runtime checks when required,
and verification report are updated together and accepted.

---

## 5. Master operational workflow

### Step 0 — Load policy and current project state

Master must load or know:

- root model/reasoning policy;
- current active tasks;
- pending Archive / Knowledge / Causal candidates;
- latest Causal context;
- latest Knowledge context;
- latest Archive events relevant to the current task;
- current top-level department availability;
- unresolved trial findings or runtime blockers.

If policy cannot be resolved, stop with `blocked_resource_policy`.

---

### Step 1 — Intake user input

For each user message, Master must produce an internal intake classification:

```yaml
intake_id: string
input_classifications:
  - new_task_request|task_update|question_only|...
contains_task_like_work: bool
contains_commit_intent: bool
contains_stable_fact_or_constraint: bool
contains_causal_claim: bool
contains_developer_decision: bool
contains_evidence_submission: bool
requires_archive_event_candidate: bool
requires_knowledge_candidate: bool
requires_causal_candidate: bool
requires_user_clarification: bool
```

Master must not skip intake merely because the user phrased the message casually.

---

### Step 2 — Decide task boundary: create / bind / aggregate / split

Master must reason about task identity before creating task IDs.

#### 2.1 Create

Create a new final Archive task when the input represents a commit-bound unit of work that is logically independent and not already covered by an active task.

#### 2.2 Bind

Bind input to an existing active task when it is a continuation, clarification, evidence update, or correction of that task.

#### 2.3 Aggregate

Aggregate multiple user inputs into one final Archive task only when all of the following hold:

- none of the candidate inputs has already been archived as a final Archive task;
- they share one logical commit boundary;
- they should be implemented, tested, reviewed, and delivered together;
- separating them would create artificial commits or duplicate review/test overhead;
- rollback should happen as one unit;
- evidence supports the aggregation.

Existing archived tasks must not be merged.

Aggregation is allowed only before final Archive task creation.

#### 2.4 Split

Split a user request into multiple final Archive tasks when one request contains multiple commit-bound units of work.

Split is required when the correct engineering outcome requires separate commits due to:

- independent rollback boundaries;
- independent review boundaries;
- independent test boundaries;
- materially different responsibilities;
- cross-module risk isolation;
- staged dependency order;
- user-visible delivery separation;
- objectively separable implementation scopes.

One large user request may produce multiple final Archive tasks and therefore multiple final commit candidates.

#### 2.5 Planning hierarchy

Master may create planning hierarchy when useful.

However, final Archive task identity must remain commit-bound. Planning parents, epics, batches, or temporary groups must not be confused with final commit-level Archive tasks.

#### 2.6 Existing task immutability

Once an Archive task is created, Master must not merge it into another Archive task.

Allowed later operations:

- amend task scope through a new Archive event;
- split an unfinished task into separate new final tasks with explicit archival correction;
- cancel or supersede a task with an Archive event;
- bind new evidence to the existing task;
- create dependent tasks.

Forbidden operation:

- silently merging two existing Archive tasks into one task identity.

---

### Step 3 — Create planning Archive event candidates

Task boundary decisions themselves must be auditable.

Master should emit planning events such as:

- `task_intake_received`
- `task_candidate_created`
- `task_bound_to_existing`
- `task_planning_aggregate_event`
- `task_planning_split_event`
- `task_scope_changed`
- `task_dependency_identified`
- `task_priority_changed`

These events record planning decisions. They do not themselves create technical truth.

---

### Step 4 — Create final commit-bound Archive tasks

After task boundary reasoning, Master creates final Archive task candidates.

Each final Archive task candidate must include:

```yaml
candidate_type: archive_event_candidate
event_type: task_created|task_confirmed|task_updated|...
actor: master|developer|department_leader|...
occurred_at: timestamp
task_id: string
commit_boundary: true
commit_cardinality: exactly_one_final_commit
scope: string
evidence_refs:
  - string
reason_for_task_boundary: string
aggregation_or_split_origin:
  type: none|aggregated_from_inputs|split_from_user_request|split_from_existing_task_amendment
  refs:
    - string
archive_produces_truth: false
```

A final commit candidate later produced for this task must reference the same `task_id`.

---

### Step 5 — Extract Knowledge candidates

Master must extract source-backed stable facts and constraints.

A Knowledge candidate must contain:

```yaml
candidate_type: knowledge_candidate
statement: string
scope: string
version_context: string
evidence_refs:
  - string
master_verified: true|false
category: platform|environment|constraint|interface|dependency|policy|glossary|fact|other
```

Knowledge candidates must not contain:

- causal reasoning chains;
- design conclusions;
- strategic judgments;
- unsupported developer assertions as active facts;
- task history;
- responsibility events.

Developer-provided urgency, customer pressure, or external constraint may become Knowledge only when evidence is provided or Master verifies it.

Unsupported claims should be archived as statements/events or marked `needs_more_evidence`, not promoted to active Knowledge.

---

### Step 6 — Identify Causal candidates

A Causal candidate must be created or requested when the content expresses reusable reasoning.

Required minimum fields:

```yaml
candidate_type: causal_candidate
statement: string
why: string
evidence_refs:
  - string
scope: string
assumptions:
  - string
source_origin: master_unique_conclusion|debate_leader_adjudication|execution_leader_directional_reasoning
candidate_status: causal_candidate
```

Optional fields:

```yaml
depends_on:
  - string
invalidates:
  - string
supersedes:
  - string
confidence: object
route_priority: string
expand_priority: string
version_context: string
```

Bare conclusions must not enter Causal.

---

### Step 7 — Run three-store admission

Master must route each candidate through three-store admission before persistence.

Allowed outcomes:

- `accept_archive_candidate`
- `accept_knowledge_candidate`
- `stage_causal_candidate`
- `reject_wrong_store`
- `reject_insufficient_evidence`
- `reject_direct_global_write`
- `reject_local_only_causal`
- `needs_more_evidence`
- `needs_debate`
- `needs_master_structural_admission_review`

A staged Causal candidate is not canonical/global truth.

---

### Step 8 — Determine execution route

Master chooses or supervises the next top-level route state.

This list includes department-to-department transitions that Master may require
or supervise, but it does not give Master direct runtime send authority for
every edge. Master's own runtime outgoing edges remain only:

- `master -> debate`
- `master -> execution`

Possible routes:

- `master -> debate`
- `master -> execution`
- `execution -> debate`
- `debate -> execution`
- `execution -> test`
- `test -> execution`
- `test -> final_review`
- `final_review -> master`
- `execution -> master`

Routing rules:

- route to Debate if multiple plausible solution paths exist without a clear engineering-dominant answer;
- route to Execution when the work is admitted, executable, and sufficiently specified;
- route to Test after implementation candidate and handoff package exist;
- route to Final Review after Test produces passed or scoped-pass evidence;
- return to Execution on evidence-backed failure feedback;
- return to Master when governance, policy, or responsibility decision is needed.

Master must not create department-internal workers directly.

If Master needs information from Test or Final Review outside an active
Execution/Test/Final Review handoff chain, it must use a separately defined
bootstrap/audit/assessment procedure. It must not fabricate a runtime
`master -> test` or `master -> final_review` message.

---

### Step 9 — Resolve model and reasoning budget before agent creation

Before creating or calling an agent, Master must resolve:

```yaml
policy_id: model_reasoning_budget_policy
role_id: string
required_model: gpt-5.5
fallback_model_allowed: gpt-5.4 only when gpt-5.5 unavailable
minimum_model: gpt-5.4
required_reasoning_budget: high|extra_high
budget_downgrade_allowed: false
silent_downgrade_allowed: false
fallback_evidence_required: true
```

Rules:

- use `gpt-5.5` when available;
- if `gpt-5.5` is unavailable, `gpt-5.4` may be used only with explicit evidence and unchanged reasoning budget;
- any model below `gpt-5.4` is forbidden;
- no provider-default model is acceptable unless it is proven to satisfy the policy;
- every proof/output must record requested model, resolved model, requested reasoning budget, resolved reasoning budget, and fallback status.
- if the tool cannot independently attest actual resolved model/budget, every
  proof/output must record `model_attestation_status:
  requested_policy_only|unattested`.
- if Master runs the standard behavioral attestation challenge and the result
  passes the fixed rubric, every proof/output may record
  `model_attestation_status: behaviorally_attested` plus a
  `behavioral_attestation_ref`. This is stronger than
  `requested_policy_only`, but it is not tool-level proof.

If the model or budget cannot satisfy policy, Master must produce `blocked_resource_policy`.

---

### Step 10 — Bootstrap or call top-level Leaders

Master creates or calls only top-level Leaders:

```text
Debate Leader
Execution Leader
Test Leader
Final Review Leader
```

Each top-level Leader creation request must include:

```yaml
agent_id: string
role_id: debate_leader|execution_leader|test_leader|final_review_leader
model: gpt-5.5|gpt-5.4
reasoning_budget: high|extra_high
parent_agent_id: master
scope: top_level_master_domain
metadata:
  policy_id: model_reasoning_budget_policy
  policy_version: string
  topology_id: master_top_level_v1
  fallback_used: bool
  fallback_evidence_ref: string|null
```

The response must be rejected if resolved model or reasoning budget differs from policy.

---

### Step 11 — Supervise nested agents without confusing launcher timeout with agent failure

Master and department Leaders must distinguish tool-call supervision states.

A `tools/call` timeout on the outer nested-Codex launcher must not be treated as child-agent failure.

Required states:

- `launcher_timeout`
- `child_thread_id_captured`
- `child_thread_alive`
- `child_completed_late`
- `result_recovered`
- `child_failed`
- `proof_missing_after_final_deadline`
- `output_missing_after_final_deadline`

Rules:

1. Persist child `threadId` immediately when available.
2. If outer launcher times out, record `launcher_timeout`.
3. Do not create a duplicate child agent for the same role/group solely because launcher timeout occurred.
4. Attempt result recovery by thread ID.
5. Use `codex_reply` or equivalent continuation when available.
6. Declare missing proof/output only after final deadline and recovery attempts fail.
7. Keep launcher timeout separate from branch/workspace compliance and model-policy compliance.

---

### Step 12 — Enforce Execution branch/workspace readiness before implementation

Master must require Execution Leader to enforce branch/workspace readiness for every Execution Group.

Before any Execution Front Agent starts implementation, the Execution Leader must provide or preserve:

```yaml
group_branch_proof:
  task_id: string
  group_id: string
  subtask_id: string
  target_repo: string
  base_branch: string
  base_commit: string
  group_branch: string
  group_workspace_or_worktree: string
  created_by: execution_leader
  derived_from_base_commit: true
  orphan_branch: false
  clean_worktree_before_start: true
```

Hard gates:

- no `base_commit` -> Front must not start;
- no Leader-created branch/workspace -> Front must not start;
- orphan branch -> branch proof invalid;
- same dirty worktree without isolation -> invalid unless explicitly admitted as single-group diagnostic mode;
- no group branch proof -> Back must not accept;
- no group branch proof -> Test handoff must not pass;
- no integration branch for accepted group branches -> final execution handoff is blocked.

This is especially important for real-project trials.

---

### Step 13 — Receive and audit department outputs

Master must not accept department outputs merely because a natural-language message says work is complete.

Master must require structured evidence:

- Leader report;
- proof files;
- output files;
- group states;
- branch/workspace proofs;
- test evidence;
- final review recommendation;
- known limits;
- scoped causal candidate;
- Archive / Knowledge / Causal candidate material.

If evidence is missing, Master must classify the result as one of:

- `needs_more_evidence`
- `blocked_resource_policy`
- `blocked_branch_contract`
- `blocked_test_evidence`
- `blocked_final_review`
- `request_rework`

---

### Step 14 — Run Master Causal Review

For staged causal candidates, Master must perform high-budget Causal Review.

Possible decisions:

- `stage_canonical_merge_candidate`
- `stage_scope_limited_merge_candidate`
- `stage_supersession_candidate`
- `stage_invalidation_candidate`
- `reject_candidate`
- `needs_more_evidence`
- `needs_debate`
- `developer_decision_required`
- `reject_direct_merge_or_store_write`

Master must preserve:

- why;
- candidate statement;
- source origin;
- evidence refs;
- knowledge context used;
- causal context used;
- conflicts;
- supersedes / invalidates;
- confidence type;
- developer responsibility boundary.

Master must not perform canonical/global causal truth merge in this phase.

---

### Step 15 — Persist local demo state only through approved runtimes

Persistence is allowed only after admission/review approval.

Mapping:

```text
accept_archive_candidate      -> archive_store persistence
accept_knowledge_candidate    -> knowledge_store persistence
causal_review persistable decision -> causal_store persistence
```

Master must not write stores directly outside approved persistence paths.

Rejected candidates must not create store layout files.

---

### Step 16 — Validate three-store linkage

After local store changes, Master must validate linkage.

Rules:

- Archive promoted links may target Knowledge or Causal only;
- Archive promoted links to Archive are invalid;
- Knowledge `evidence_refs` may cite Archive or external source material only;
- Knowledge must reject local Knowledge/Causal evidence refs;
- Causal evidence may cite Archive, Knowledge, Causal, or external source material;
- Causal `depends_on`, `supersedes`, and `invalidates` must target Causal facts only;
- broken local refs, type mismatches, duplicates, and truth-boundary leakage reject validation.

Linkage validation does not create truth and does not mutate stores.

---

### Step 17 — Prioritize active and pending tasks

Master scheduling must be evidence-based and dependency-aware.

Rules:

1. Continue active/in-progress tasks before starting new unrelated tasks unless blocked.
2. When idle, select the most urgent objectively feasible task among currently contacted or known tasks.
3. Urgency is not determined by user assertion alone.
4. Customer pressure requires evidence from the user or project artifacts.
5. Project impact, blocker depth, dependency position, failure blast radius, and delivery constraints affect priority.
6. If an urgent task depends on a non-urgent prerequisite, the prerequisite may become the immediate priority.
7. A task that is urgent but objectively infeasible must not displace a feasible prerequisite.

Priority output should include:

```yaml
selected_task_id: string
why_selected: string
active_task_preference_applied: bool
urgency_evidence_refs:
  - string
dependency_reasoning:
  - string
blocked_tasks:
  - task_id: string
    blocker: string
```

---

### Step 18 — Commit Gate

Before producing a commit candidate, Master must check:

- exactly one final Archive task ID is bound to the commit candidate;
- task boundary is commit-bound;
- aggregation/split decisions were made before final task creation or recorded as correction events;
- Execution result exists;
- branch/workspace proof exists where applicable;
- Back review exists where applicable;
- Test result exists;
- Final Review recommendation exists where required;
- known limits are preserved;
- Causal candidates were reviewed or explicitly deferred;
- Archive/Knowledge/Causal candidates were handled;
- three-store linkage is valid;
- developer authorization is required for real push/merge/release.

If a commit candidate contains unrelated work from multiple final Archive tasks, Master must reject it or require split commits.

If multiple subtasks belong to the same final Archive task and were integrated by the Execution Leader, one commit candidate is allowed.

---

### Step 19 — User-facing response

Master's user-facing response should be concise but must not hide governance state.

It should include, when relevant:

- current task ID or task boundary status;
- whether task was created, bound, aggregated, or split;
- what was archived or will be archived;
- Knowledge/Causal candidates identified;
- routing decision;
- blockers;
- next required action;
- whether user authorization is needed.

Master must not claim production completion when only demo/acceptance or local candidate closure occurred.

---

## 6. Required output artifacts

Depending on context, Master should generate or require these artifacts:

### 6.1 Intake artifact

```yaml
master_intake_result_id: string
input_classification:
  - string
task_boundary_decision: create|bind|aggregate|split|planning_only|question_only|reject
archive_event_candidates:
  - object
knowledge_candidates:
  - object
causal_candidates:
  - object
requires_user_clarification: bool
next_route: master|debate|execution|test|final_review|none
```

### 6.2 Task boundary artifact

```yaml
task_boundary_decision_id: string
decision: create|bind|aggregate|split|amend|cancel
final_archive_task_ids:
  - string
commit_cardinality:
  mode: one_task_one_commit
aggregation_inputs:
  - string
split_outputs:
  - string
existing_archived_tasks_merged: false
why: string
evidence_refs:
  - string
```

### 6.3 Model resolution artifact

```yaml
model_resolution_id: string
role_id: string
requested_model: gpt-5.5|gpt-5.4
resolved_model: gpt-5.5|gpt-5.4
minimum_allowed_model: gpt-5.4
requested_reasoning_budget: high|extra_high
resolved_reasoning_budget: high|extra_high
fallback_used: bool
fallback_reason: string|null
fallback_evidence_ref: string|null
budget_downgrade_used: false
blocked_resource_policy: bool
```

### 6.4 Agent supervision artifact

```yaml
agent_supervision_id: string
agent_id: string
role_id: string
thread_id: string|null
launcher_status: created|launcher_timeout|failed
child_status: unknown|alive|completed_late|failed
recovery_attempted: bool
result_recovered: bool
proof_status: present|missing|missing_after_final_deadline
output_status: present|missing|missing_after_final_deadline
```

### 6.5 Commit gate artifact

```yaml
commit_gate_result_id: string
task_id: string
exactly_one_task_bound: bool
execution_result_present: bool
test_result_present: bool
final_review_result_present: bool
branch_workspace_proof_present: bool
three_store_linkage_valid: bool
known_limits:
  - string
decision: ready_for_developer_authorization|blocked|needs_rework|needs_more_evidence
```

---

## 7. Forbidden Master behavior

Master must not:

- skip intake on task-like user input;
- create a commit candidate without a final Archive task ID;
- merge existing archived tasks;
- let one commit silently contain multiple unrelated Archive tasks;
- treat user-declared urgency as fact without evidence;
- let ordinary agents directly write Archive, Knowledge, or Causal;
- promote Archive to truth;
- promote Knowledge to Causal without causal construction;
- accept local worker reasoning as project-level Causal without proper path;
- create department-internal workers directly;
- ignore model-policy mismatch;
- downgrade reasoning budget;
- use models below `gpt-5.4`;
- treat nested-Codex launcher timeout as child-agent failure;
- accept Execution output without required branch/workspace proof when applicable;
- hide integration conflicts;
- perform remote push, PR, merge, release, deployment, or formal sign-off.

---

## 8. Skill-to-runtime mapping

This skill should later be enforced through runtime validators.

Suggested next modules:

```text
aegis-runtime/master_intake/
aegis-runtime/task_archive_binding/
aegis-runtime/model_policy_guard/
aegis-runtime/agent_supervision/
aegis-runtime/commit_gate/
```

Suggested next contracts:

```text
aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL.md
aegis-master-kit/master/MASTER_INTAKE_RESULT_CONTRACT.md
aegis-master-kit/master/TASK_ARCHIVE_BINDING_POLICY.md
aegis-master-kit/master/TASK_ARCHIVE_BINDING_RESULT_CONTRACT.md
aegis-master-kit/master/MODEL_FALLBACK_POLICY_V2.md
aegis-master-kit/master/NESTED_AGENT_SUPERVISION_POLICY.md
aegis-master-kit/master/COMMIT_GATE_RESULT_CONTRACT.md
```

---

## 9. Minimal acceptance tests for this skill

A future implementation must pass tests for:

1. casual user task input triggers intake;
2. stable user-provided constraint creates Knowledge candidate only with evidence/scope;
3. unsupported developer assertion does not become active Knowledge;
4. causal-shaped statement routes to Causal candidate;
5. new executable request creates final Archive task candidate;
6. related not-yet-archived requests aggregate into one final task when commit-bound;
7. existing archived tasks cannot be merged;
8. one large request can split into multiple final Archive tasks and multiple commit candidates;
9. commit candidate without task ID is blocked;
10. commit candidate bound to multiple unrelated tasks is blocked;
11. gpt-5.5 unavailable allows explicit gpt-5.4 fallback with unchanged budget and evidence;
12. model below gpt-5.4 is blocked;
13. reasoning budget downgrade is blocked;
14. nested launcher timeout enters recovery state rather than agent failure;
15. child thread result can be recovered after launcher timeout;
16. missing proof after final deadline is failure;
17. Execution output without base-commit-derived group branch proof is blocked;
18. Knowledge evidence pointing to Causal or Knowledge local refs is rejected by linkage;
19. Causal dependency pointing to Knowledge is rejected;
20. active task priority beats new unrelated work unless blocked;
21. urgent blocked task yields priority to objective prerequisite;
22. user-declared customer pressure without evidence is not accepted as urgency fact.

---

## 10. Phase-2 upgrade notes

This v0.3 skill intentionally proposes two upgrades beyond current v0.1 repository policy:

1. **Model fallback upgrade**
   - Current repository policy forbids fallback.
   - v0.3 allows explicit `gpt-5.5 -> gpt-5.4` fallback only when `gpt-5.5` is unavailable.
   - Reasoning budget must not downgrade.
   - Models below `gpt-5.4` remain forbidden.
   - This requires updating root model policy and runtime guards before production enforcement.

2. **Commit-bound Archive task identity**
   - Archive persistence currently supports task events.
   - v0.3 defines final Archive task identity as commit-bound.
   - Existing archived tasks must not be merged.
   - Aggregation must occur before final task creation.
   - Splitting a user request may produce multiple final Archive tasks and therefore multiple commits.
   - This requires adding Master Intake / Task Archive Binding runtime validation.

---

## 11. One-line definition

Master's operational workflow is:

```text
Intake every user message -> reason about commit-bound task identity -> archive task events -> extract Knowledge/Causal candidates -> run admission -> route departments -> enforce model/agent supervision -> review causal outputs -> persist local stores -> validate linkage -> gate commit candidate -> require developer authorization.
```
