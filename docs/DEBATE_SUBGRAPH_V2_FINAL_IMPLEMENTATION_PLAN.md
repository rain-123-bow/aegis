# Debate Subgraph v2 Final Implementation Plan

## Conclusion

DebateSubgraph v2 is a bounded, project-store-grounded causal adjudication subgraph.

It must:

1. bind to the managed project's local Archive, Knowledge, and Causal store instances;
2. validate whether Debate should start;
3. admit only genuinely contested defensible stances;
4. run stance-bound Debate Workers under a Leader adjudicator;
5. enforce Knowledge and Causal constraints;
6. merge worker causal drafts into a structured causal candidate;
7. write a project-local Causal Store update candidate;
8. return a stable `DebateOutputPackage` to the caller.

It must not:

1. mutate admitted Causal truth directly;
2. mutate Knowledge truth;
3. write governance artifacts under `project-root/code`;
4. pass long text through LangGraph state;
5. rely on skills alone as the system boundary.

Skills guide Leader and Worker behavior. Schemas, path policies, node contracts, artifact contracts, and tests enforce the boundary.

## Managed Project Store Model

Default managed project layout:

```text
project-root/
  code/
    ...pure project code...
  archive/
  knowledge/
  causal/
```

This layout is the default project convention, not a hard-coded graph assumption.

Runtime must use `ProjectStoreBinding`. If future projects store these under another layout, only the binding layer changes. Graph nodes must not manually concatenate `archive/`, `knowledge/`, or `causal/` paths.

## Implementation Placement

Runtime package:

```text
src/aegis/modules/debate/
  __init__.py
  models.py
  errors.py
  config.py
  graph.py
  node_contracts.py
  store_binding.py
  artifacts.py
  context.py
  admission.py
  leader.py
  worker.py
  merge.py
  candidate_writer.py
  skills.py
```

Tests:

```text
tests/debate/
  test_debate_models.py
  test_debate_store_binding.py
  test_debate_artifacts.py
  test_debate_context_bundle.py
  test_debate_hard_constraints.py
  test_debate_stance_admission.py
  test_debate_stance_relations.py
  test_debate_worker_protocol.py
  test_debate_leader_convergence.py
  test_debate_causal_candidate_mapping.py
  test_debate_resume_idempotency.py
  test_debate_graph_contracts.py
  test_debate_subgraph_integration.py
```

Skill templates:

```text
src/aegis/modules/debate/skills/leader/SKILL.md
src/aegis/modules/debate/skills/worker/SKILL.md
```

Runtime evidence:

```text
module_test_reports/debate_subgraph_v2_<timestamp>/
```

## Public Contract

### DebateInputPackage

```yaml
DebateInputPackage:
  schema_version: "debate.input.v2"
  request_id: string
  source_module: master|execution|final_review|causal_review
  project_root: path
  decision_problem: string
  decision_scope: string
  required_outcome: choose_one|rank|scope_split|reject_all|need_measurement|need_master
  candidate_positions:
    - stance_id: string
      statement: string
      summary: string
      claimed_advantages: list[string]
      claimed_risks: list[string]
      source_artifact_refs: list[path]
  hard_constraints:
    - constraint_id: string
      statement: string
      source: user|master|execution|test|final_review|knowledge|causal
      evidence_ref: string|null
  knowledge_query_hints:
    subject_refs: list[string]
    applicability_terms: list[string]
    required_dimensions: list[string]
  causal_query_hints:
    node_ids: list[uint64]
    semantic_terms: list[string]
    neighborhood_depth: int
  artifact_refs:
    requirement_doc: path|null
    review_doc: path|null
    execution_context: path|null
    test_evidence: path|null
```

### DebateOutputPackage

Every terminal path returns this structure. Callers must not parse human-readable reports to decide routing.

```yaml
DebateOutputPackage:
  schema_version: "debate.output.v2"
  debate_id: string
  request_id: string
  status:
    completed|debate_not_required|need_more_context|need_measurement|non_convergent|failed
  decision_type:
    choose_one|rank|scope_split|reject_all|need_measurement|need_master
  selected_stance_ids: list[string]
  ranked_stance_ids: list[string]
  rejected_stance_ids: list[string]
  scope_splits:
    - stance_id: string
      scope: string
      reason: string
  causal_candidate_ref: path|null
  causal_store_candidate_id: string|null
  final_report_ref: path
  context_bundle_ref: path|null
  manifest_ref: path
  worker_audit_refs: list[path]
  leader_audit_refs: list[path]
  boundary:
    wrote_causal_truth: false
    wrote_knowledge_truth: false
    modified_code: false
  errors:
    - code: DebateErrorCode
      message: string
      recovery_action: string|null
```

## Runtime Configuration

All bounded runtime behavior must come from `DebateRuntimeConfig`.

```yaml
DebateRuntimeConfig:
  max_rounds: int
  max_turns_per_worker: int
  max_worker_repair_attempts: int
  stable_selected_stance_round_threshold: int
  max_protocol_violations_per_worker: int
  allow_scope_limited_verdict_on_max_rounds: bool
  allow_real_agent_adapter: bool
  write_canonical_transcript: bool
  deterministic_mode: bool
```

Default local development values:

```yaml
max_rounds: 4
max_turns_per_worker: 4
max_worker_repair_attempts: 1
stable_selected_stance_round_threshold: 2
max_protocol_violations_per_worker: 2
allow_scope_limited_verdict_on_max_rounds: true
allow_real_agent_adapter: false
write_canonical_transcript: true
deterministic_mode: true
```

Tests may pass smaller values. Real-agent acceptance may override `allow_real_agent_adapter`.

## Error Contract

Public graph invocation must return `DebateOutputPackage` or a domain error object. It must not expose raw exceptions as the public contract.

```text
DebateErrorCode:
  PROJECT_STORE_NOT_FOUND
  PROJECT_STORE_BINDING_INVALID
  PATH_POLICY_VIOLATION
  INPUT_SCHEMA_INVALID
  HARD_CONSTRAINT_UNSUPPORTED
  INSUFFICIENT_DEFENSIBLE_STANCES
  INSUFFICIENT_CONTESTED_STANCES
  MISSING_REQUIRED_CONTEXT
  MEASUREMENT_REQUIRED_BEFORE_DEBATE
  KNOWLEDGE_STORE_UNAVAILABLE
  CAUSAL_STORE_UNAVAILABLE
  DEGRADED_RECALL_BLOCKING
  WORKER_PACKET_INVALID
  WORKER_PROTOCOL_VIOLATION_FATAL
  LEADER_NON_CONVERGENCE
  CAUSAL_CANDIDATE_MAPPING_FAILED
  CAUSAL_CANDIDATE_WRITE_FAILED
  ARTIFACT_WRITE_FAILED
  RESUME_MANIFEST_INVALID
```

## Node Result Contract

Every graph node returns a `DebateNodeResult`.

```yaml
DebateNodeResult:
  node_name: string
  status: ok|terminal|failed
  updated_state_fields: map[string, object]
  artifact_refs: list[path]
  error:
    code: DebateErrorCode|null
    message: string|null
    blocking: bool
    recovery_action: string|null
```

Node contract rule:

- Each node has explicit inputs, outputs, written artifacts, possible errors, state updates, and idempotency behavior.
- Each node must be independently unit-testable.
- Each artifact-writing node must be safe to retry or resume.

## Graph Node Contracts

| Node | Inputs | Outputs | Artifacts | Main errors |
| --- | --- | --- | --- | --- |
| `debate_intake` | input package path or object | validated input ref | `input_package.json` | `INPUT_SCHEMA_INVALID` |
| `project_store_bind` | project root | `ProjectStoreBinding` | `project_store_binding.json` | `PROJECT_STORE_NOT_FOUND`, `PATH_POLICY_VIOLATION` |
| `validate_hard_constraints` | input, binding | validations | `hard_constraint_validations.json` | `HARD_CONSTRAINT_UNSUPPORTED` if caller marked unsupported as mandatory |
| `build_context_retrieval_plan` | input, validations | retrieval plan | `retrieval_plan.json` | `MISSING_REQUIRED_CONTEXT` |
| `load_knowledge_context` | plan, binding | knowledge refs | `knowledge_context.json` | `KNOWLEDGE_STORE_UNAVAILABLE`, `DEGRADED_RECALL_BLOCKING` |
| `load_causal_context` | plan, binding | causal refs | `causal_context.json` | `CAUSAL_STORE_UNAVAILABLE` |
| `build_context_bundle` | knowledge and causal refs | context bundle | `context_bundle.json` | `MISSING_REQUIRED_CONTEXT` |
| `stance_admission_gate` | input, context bundle, validations | admission records | `stance_admission_records.json` | `INSUFFICIENT_DEFENSIBLE_STANCES` |
| `stance_relation_analysis` | admitted stances | relation records | `stance_relation_records.json` | `INSUFFICIENT_CONTESTED_STANCES` |
| `create_worker_assignments` | admitted contested stances | assignments | `worker_assignments/*.json` | `ARTIFACT_WRITE_FAILED` |
| `round_robin_debate_loop` | assignments, transcript | worker packets | `worker_packets/*.json`, `canonical_transcript/*.md` | `WORKER_PACKET_INVALID` |
| `leader_round_assessment` | packets, prior assessments | assessment | `leader_round_assessments/*.json` | `WORKER_PROTOCOL_VIOLATION_FATAL`, `LEADER_NON_CONVERGENCE` |
| `merge_worker_causal_chains` | usable packets, assessments | merged chain | `merged_causal_chain.json` | `CAUSAL_CANDIDATE_MAPPING_FAILED` |
| `map_to_causal_candidate` | merged chain | candidate package | `causal_store_update_candidate.json` | `CAUSAL_CANDIDATE_MAPPING_FAILED` |
| `write_causal_store_candidate` | candidate package | write result | `causal_candidate_write_result.json` | `CAUSAL_CANDIDATE_WRITE_FAILED` |
| `build_output_package` | all refs, status | output package | `debate_output_package.json`, `final_report.md` | `ARTIFACT_WRITE_FAILED` |

## Project Store Binding

```yaml
ProjectStoreBinding:
  project_root: path
  code_root: path
  archive_store_root: path
  knowledge_store_root: path
  causal_store_root: path
  debate_candidate_root: path
  path_policy:
    forbid_writes_under_code: true
    forbid_symlink_escape: true
    require_all_artifacts_under_candidate_root: true
```

Rules:

1. Canonicalize every path.
2. Reject all writes under `code_root`.
3. Reject symlink escape.
4. Require all Debate artifacts under `debate_candidate_root`.
5. Do not hard-code store paths inside graph logic.
6. Test with non-default store layout to prove binding abstraction.

## Run Manifest and Resume

```yaml
DebateRunManifest:
  schema_version: "debate.run_manifest.v2"
  debate_id: string
  run_status:
    initialized|context_loaded|admitted|debating|merged|candidate_written|completed|failed
  created_at_utc: string
  updated_at_utc: string
  input_hash: string
  context_bundle_hash: string|null
  candidate_hash: string|null
  artifacts:
    - path: string
      sha256: string
      kind: string
```

Rules:

1. Use atomic writes.
2. Update manifest after each durable stage.
3. Resume from the last completed stage.
4. Candidate write must be idempotent.
5. Duplicate run with same input hash must not duplicate candidate nodes.

## Hard Constraint Validation

Input hard constraints are untrusted claims until validated.

```yaml
HardConstraintValidation:
  constraint_id: string
  input_statement: string
  evidence_ref: string|null
  validation_status: verified|unsupported|conflicting|out_of_scope
  matched_knowledge_refs: list[string]
  matched_causal_refs: list[uint64]
  matched_test_evidence_refs: list[string]
  first_principles_necessity: FirstPrinciplesNecessityCheck|null
  rejection_reason: string|null
```

```yaml
FirstPrinciplesNecessityCheck:
  statement: string
  category:
    logic|mathematics|physical_constraint|type_system_constraint|security_invariant|governance_invariant
  depends_on_project_fact: bool
  required_project_fact_ref: string|null
  accepted: bool
  rejection_reason: string|null
```

Rules:

1. User preference is not a hard constraint.
2. Developer claim is not a hard constraint.
3. If first-principles necessity depends on project fact, it must cite Knowledge, Causal, artifact, or Test evidence.
4. Unsupported hard constraints remain in audit and cannot defeat a stance.

## Context Bundle

```yaml
DebateContextBundle:
  schema_version: "debate.context.v2"
  context_bundle_id: string
  debate_id: string
  knowledge_refs: list[KnowledgeContextRef]
  rejected_knowledge_refs: list[RejectedKnowledgeRef]
  causal_refs: list[CausalContextRef]
  rejected_causal_refs: list[RejectedCausalRef]
  missing_knowledge_needs: list[MissingKnowledgeNeed]
  measurement_needs: list[MeasurementNeed]
  degraded_recall_warnings: list[DegradedRecallWarning]
  retrieval_audit: RetrievalAudit
```

`MissingKnowledgeNeed.blocking_level` must reuse Knowledge Store levels:

```text
hard_block
needs_user_clarification
request_test_measurement
request_archive_lookup
advisory
```

Gate rules:

- `hard_block` prevents Debate.
- `request_test_measurement` on a decisive dimension returns `need_measurement`.
- Critical degraded recall prevents strong verdict.
- Rejected refs must be visible to Leader and unavailable to Worker as support.

## Stance Admission

```yaml
StanceAdmissionRecord:
  stance_id: string
  status: admitted|rejected|needs_context|needs_measurement
  defensibility_basis:
    knowledge_refs: list[string]
    causal_refs: list[uint64]
    first_principles_claims: list[FirstPrinciplesNecessityCheck]
    artifact_refs: list[path]
  unsupported_claims: list[string]
  duplicate_of_stance_id: string|null
  dominated_by_stance_id: string|null
  hard_constraint_conflicts: list[string]
  rejection_reason: string|null
```

Minimum admission:

- At least one positive support basis exists.
- No verified hard constraint directly defeats the stance.
- No blocking missing knowledge is required by the stance.
- The stance is not a duplicate.
- The stance is not fully dominated under the same scope.

## Stance Relation Matrix

Two admitted stances do not automatically require Debate. They must be contested under the decision scope.

```yaml
StanceRelationRecord:
  left_stance_id: string
  right_stance_id: string
  relation:
    duplicate|compatible|mutually_exclusive|scope_split_candidate|left_dominates_right|right_dominates_left|measurement_needed
  reason: string
  evidence_refs: list[string]
  causal_refs: list[uint64]
```

Debate starts only when at least two admitted stances are genuinely contested:

- `mutually_exclusive`;
- unresolved dominance;
- contested `scope_split_candidate`;
- relation requires adversarial causal adjudication.

If stances are compatible, return `scope_split` or merged path instead of Debate.

## Worker Packet

```yaml
WorkerTurnPacket:
  schema_version: "debate.worker_turn.v2"
  turn_id: string
  debate_id: string
  worker_id: string
  stance_id: string
  round_index: int
  observed_canonical_transcript_ref: path
  defense:
    claims: list[string]
    supporting_knowledge_refs: list[string]
    supporting_causal_refs: list[uint64]
    first_principles_claims: list[FirstPrinciplesNecessityCheck]
    local_causal_nodes: list[object]
  attacks:
    - target_stance_id: string
      attacked_claim: string
      attack_reason: string
      evidence_refs: list[string]
      causal_refs: list[uint64]
      materiality: decisive|material|minor
  concessions:
    - conceded_point: string
      why_conceded: string
      defeating_ref: string
      impact_on_stance: fatal|scope_limit|minor
  chain_delta:
    added_local_nodes: list[object]
    added_edges: list[object]
    invalidated_local_nodes: list[string]
  open_questions: list[string]
  self_audit:
    knowledge_constraints_checked: true
    causal_refs_checked: true
    unsupported_claims: list[string]
    possible_protocol_violations: list[string]
```

## Worker Protocol Violation

```yaml
WorkerProtocolViolation:
  worker_id: string
  turn_id: string
  violation_type:
    - unsupported_invention
    - ignored_hard_constraint
    - premature_concession
    - dead_end_over_defense
    - candidate_truth_confusion
    - store_mutation_attempt
  severity: warning|material|fatal
  action:
    - mark_turn_unusable
    - request_worker_repair
    - leader_override
    - terminate_worker
    - abort_debate
  reason: string
```

Rules:

- Fatal turns are excluded from merge.
- Material violations require repair or Leader override.
- Unsupported invention never becomes a proposed causal node.
- Candidate/truth confusion must be repaired or excluded.

## Leader Convergence

```yaml
ConvergenceSignals:
  active_stance_count: int
  undefeated_stance_count: int
  unresolved_conflict_count: int
  new_material_argument_count: int
  decisive_constraint_count: int
  unresolved_blocking_missing_need_count: int
  worker_protocol_violation_count: int
  stable_selected_stance_rounds: int
```

Leader may stop only when one condition holds:

1. only one undefeated stance remains;
2. every rejected stance has decisive rejection edges;
3. selected stance is stable for configured threshold;
4. unresolved conflicts are zero and no new material argument appears;
5. blocking missing knowledge requires context or Test;
6. max rounds reached and only a scope-limited verdict is possible.

## Leader Round Assessment

```yaml
LeaderRoundAssessment:
  schema_version: "debate.leader_round.v2"
  debate_id: string
  round_index: int
  active_stances: list[string]
  dominated_stances: list[string]
  undefeated_stances: list[string]
  newly_resolved_conflicts: list[string]
  unresolved_conflicts: list[string]
  decisive_constraints: list[string]
  worker_protocol_violations: list[WorkerProtocolViolation]
  convergence_signals: ConvergenceSignals
  next_action:
    continue|request_worker_repair|leader_override|stop_converged|stop_need_context|stop_need_test|abort
  continue_reason: string|null
  stop_reason: string|null
```

## Causal Candidate Mapping

Debate has two candidate layers.

Layer 1: artifact candidate package.

```text
causal_store_update_candidate.json
```

Layer 2: Causal Store DB candidate rows.

```text
CausalNode status=candidate
DependencyGroup rows
source_artifact_ref -> debate candidate package
```

### CausalCandidateNode

```yaml
CausalCandidateNode:
  local_node_ref: string
  minimal_semantic_content: string
  semantic_summary: string
  semantic_keys: list[string]
  status: candidate
  dependency_groups:
    - group_id: string
      causal_dependencies:
        existing_node_ids: list[uint64]
        local_node_refs: list[string]
      knowledge_refs: list[string]
      evidence_refs: list[string]
      conditions: list[string]
      assumptions: list[string]
      scope: string
      confidence: high|medium|low
      invalidation_conditions: list[string]
  source:
    module: debate
    debate_id: string
    worker_turn_refs: list[path]
```

### CausalCandidateWriteResult

```yaml
CausalCandidateWriteResult:
  package_candidate_id: string
  artifact_ref: path
  db_candidate_node_ids: list[uint64]
  reused_node_ids: list[uint64]
  duplicate_nodes_skipped:
    - local_node_ref: string
      existing_node_id: uint64
      reason: string
  write_status: written|already_exists|partial_failed|failed
```

Rules:

1. Query Causal Store for equivalent admitted or deprecated nodes before writing.
2. Reuse equivalent admitted nodes.
3. Reference equivalent deprecated nodes when reopening is justified.
4. Create new candidate nodes only for new causal substance.
5. Ensure artifact package and DB candidate rows can trace each other.
6. Candidate writes are transactional or fail without half-written state.

## Artifact Package

```text
project-root/
  causal/
    candidates/
      debate/
        debate-<timestamp>-<short-id>/
          README.md
          manifest.json
          debate_output_package.json
          input_package.json
          project_store_binding.json
          hard_constraint_validations.json
          retrieval_plan.json
          knowledge_context.json
          causal_context.json
          context_bundle.json
          stance_admission_records.json
          stance_relation_records.json
          worker_assignments/
          canonical_transcript/
          worker_packets/
          leader_round_assessments/
          protocol_violations.json
          merged_causal_chain.json
          causal_store_update_candidate.json
          causal_candidate_write_result.json
          final_report.md
```

`README.md` must include:

- package purpose;
- read order;
- schema versions;
- whether DB candidate write happened;
- whether admitted causal truth was modified;
- manifest verification command.

## LangGraph State

```yaml
DebateSubgraphState:
  debate_id: string
  thread_id: string
  project_root: path
  input_package_ref: path
  project_store_binding_ref: path|null
  context_bundle_ref: path|null
  run_manifest_ref: path|null
  output_package_ref: path|null
  status: string
  error_code: string|null
```

Forbidden:

- full transcript;
- full context bundle body;
- full causal chain body;
- worker packet bodies;
- Knowledge or Causal extracts.

## Leader Skill

Recommended installed skill:

```text
aegis-debate-leader-v2
```

Frontmatter:

```yaml
---
name: aegis-debate-leader-v2
description: Use when acting as Aegis Debate Leader v2 to admit or reject debate stances, supervise stance-bound Debate Workers, enforce Knowledge/Causal store constraints, detect worker protocol violations, decide structural convergence, merge worker causal chains, and produce Causal Store update candidates. Trigger for DebateSubgraph runtime, adversarial adjudication, causal candidate construction, and leader review of worker debate packets.
---
```

Core instructions:

```text
Act as adjudicator, not moderator.

Read only provided artifact refs.
Do not assume unprovided project facts.
Admit only defensible contested stances.
Validate hard constraints before use.
Detect unsupported invention, ignored constraints, premature concession, over-defense, candidate/truth confusion, and mutation attempts.
Stop only by structural convergence rules.
Merge only usable worker turns.
Output causal candidate artifacts.
Never write admitted causal truth, Knowledge truth, or project code.
```

References:

```text
references/schemas.md
references/convergence_rules.md
references/violation_handling.md
references/causal_candidate_mapping.md
```

Scripts:

```text
scripts/validate_debate_artifacts.py
scripts/compute_convergence_signals.py
scripts/validate_causal_candidate.py
```

## Worker Skill

Recommended installed skill:

```text
aegis-debate-worker-v2
```

Frontmatter:

```yaml
---
name: aegis-debate-worker-v2
description: Use when acting as an Aegis Debate Worker v2 assigned to defend one stance in a DebateSubgraph run, attack competing stances with evidence-backed reasoning, maintain a local causal-chain draft, concede only when materially defeated, and emit structured WorkerTurnPacket artifacts under Leader supervision.
---
```

Core instructions:

```text
You are stance-bound.

Defend the assigned stance with Knowledge refs, Causal refs, artifact evidence, or valid first-principles reasoning.
Attack alternatives by identifying unsupported facts, constraint conflicts, weaker causal closure, invalidation risk, or scope weakness.
Concede only when a material premise is defeated.
Do not invent project facts.
Do not ignore hard constraints.
Do not mutate stores.
Do not call candidate truth admitted truth.
Emit exactly one WorkerTurnPacket per turn.
```

References:

```text
references/worker_turn_packet_schema.md
references/evidence_rules.md
references/concession_rules.md
references/local_causal_chain_rules.md
```

Scripts:

```text
scripts/validate_worker_turn_packet.py
```

## Implementation Order

1. Models and enums.
   - Add all public schemas, config, error codes, and output package.
   - Tests: schema validation and invalid input rejection.

2. Project store binding and path policy.
   - Implement canonical paths, symlink checks, code-root write prohibition.
   - Tests: default and non-default layouts.

3. Artifact writer and run manifest.
   - Implement atomic writes, hash manifest, resume stage detection.
   - Tests: retry, resume, duplicate input hash.

4. Context bundle builder.
   - Integrate Knowledge and Causal store query interfaces.
   - Tests: rejected refs, degraded recall, missing needs, measurement needs.

5. Hard constraint validation.
   - Add `FirstPrinciplesNecessityCheck`.
   - Tests: user preference and developer claim rejection.

6. Stance admission and relation analysis.
   - Add defensibility gate and contested stance matrix.
   - Tests: duplicates, dominated stances, compatible stances, measurement-needed relations.

7. Deterministic worker fixtures.
   - Produce valid and invalid WorkerTurnPacket fixtures.
   - Tests: packet validation and protocol violation detection.

8. Leader convergence.
   - Implement convergence signals and structural stop rules.
   - Tests: stop, continue, repair, abort, non-convergent.

9. Causal chain merge and candidate mapping.
   - Map worker chain deltas to candidate nodes and dependency groups.
   - Tests: reuse equivalent nodes, skip duplicates, preserve rejected paths.

10. Causal candidate writer.
   - Write artifact package and DB candidate rows.
   - Tests: transactionality, idempotency, traceability.

11. LangGraph builder.
   - Build StateGraph node wiring.
   - Tests: all terminal paths return `DebateOutputPackage`.

12. Skill templates.
   - Add Leader and Worker skill templates.
   - Tests: skill validation and static contract checks.

13. Real-agent adapter.
   - Add opt-in adapter behind `allow_real_agent_adapter`.
   - Tests: schema validation, one repair attempt, failed repair exclusion.

14. Real-agent acceptance.
   - Run real Leader and Workers.
   - Preserve evidence package.

## Test Matrix

### Unit Tests

```text
test_debate_output_package_all_terminal_paths
test_node_result_contract_for_each_node
test_runtime_config_controls_boundaries
test_project_store_binding_default_layout
test_project_store_binding_non_default_layout
test_path_policy_rejects_code_write
test_path_policy_rejects_symlink_escape
test_manifest_resume_after_context_load
test_manifest_resume_after_worker_packets
test_unsupported_hard_constraint_rejected
test_first_principles_project_fact_requires_ref
test_context_bundle_degraded_recall_blocks_or_warns
test_stance_admission_defensible_gate
test_stance_relation_duplicate_prevents_debate
test_stance_relation_compatible_returns_scope_split
test_worker_protocol_violation_turn_unusable
test_leader_convergence_structural_stop
test_causal_candidate_maps_dependency_groups
test_causal_candidate_reuses_existing_node
test_candidate_write_idempotent
test_langgraph_state_refs_only
```

### Integration Tests

```text
test_master_triggered_debate_outputs_candidate
test_execution_triggered_debate_returns_route
test_missing_knowledge_hard_block_prevents_debate
test_measurement_required_routes_to_test
test_existing_causal_node_reused_not_duplicated
test_rejected_paths_preserved_as_negative_material
test_project_code_not_polluted_by_artifacts
test_resume_after_worker_packets_written
test_candidate_package_and_db_rows_trace_each_other
```

### Real-Agent Acceptance

Evidence layout:

```text
module_test_reports/debate_subgraph_v2_real_agent_<timestamp>/
  leader/
  workers/
  packets/
  assessments/
  violations/
  final_candidate/
  report.md
```

Required probes:

- worker invention detected;
- worker premature concession detected;
- worker over-defense detected;
- leader candidate/truth confusion detected;
- leader does not stop on vague plausibility;
- final causal chain traces to worker turns and store refs;
- code root remains clean.

## Acceptance Criteria

DebateSubgraph v2 is accepted only when:

1. Every terminal path returns `DebateOutputPackage`.
2. Every node has a tested node contract.
3. Bounded behavior is controlled by `DebateRuntimeConfig`.
4. Debate starts only with at least two contested defensible stances.
5. Hard constraints are validated before use.
6. First-principles necessity cannot hide missing project facts.
7. Context bundle represents retrieved, rejected, missing, measurement, and degraded context.
8. Worker violations affect merge eligibility.
9. Leader stop rules are structural.
10. Candidate mapping aligns with Causal Store candidate nodes and dependency groups.
11. Artifact package and DB candidate rows trace each other.
12. Candidate write is idempotent and resumable.
13. `project-root/code` is not polluted.
14. LangGraph state stores refs only.
15. Real-agent acceptance catches bad behavior, not only happy path.

## Done Definition

Implementation is done when:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe -m pytest tests\debate -vv
C:\Users\playm\secret\.venv\Scripts\python.exe -m pytest -vv
C:\Users\playm\secret\.venv\Scripts\python.exe -m ruff check .
git diff --check
```

All pass, and a real-agent acceptance report is written under `module_test_reports/`.

## Final Position

The final landing design is:

```text
Project-local Knowledge/Causal context
-> validated hard constraints
-> defensible contested stance admission
-> bounded stance-worker debate
-> structural Leader adjudication
-> causal-chain merge
-> Causal Store candidate package and DB candidate rows
-> stable DebateOutputPackage
```

This is implementable without relying on soft prompt discipline as the system boundary.
