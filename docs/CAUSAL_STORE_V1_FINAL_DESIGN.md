# Causal Store v1 Final Design

## Status

Final implementation baseline for the Aegis v0.1.2 LangGraph rebuild.

This document supersedes:

- `docs/CAUSAL_STORE_NODE_SPACE_DESIGN.md`
- `docs/CAUSAL_STORE_NODE_SPACE_HARDENED_DESIGN.md`

Those earlier documents remain useful as design history. New implementation work should follow this document.

## Executive Decision

Aegis Causal Store v1 is a project-local, SQLite-backed causal node space.

The canonical object is `CausalNode`. Dependency groups are node-owned validity structures. Reasoning chains are query-time projections over the node space. SQLite is the only canonical store. FTS and vector indexes are rebuildable recall layers, not truth stores.

The store must preserve reusable causal reasoning without allowing temporary agent output to become admitted project truth.

## Core Requirements

The Causal Store must support:

- exact `node_id` lookup
- semantic retrieval
- reusable causal nodes
- conditional validity by scope, assumptions, conditions, confidence, and invalidation rules
- evidence binding at dependency-group level
- candidate vs admitted separation
- atomic admission transactions
- invalidation without blind cascading
- revalidation of affected dependent nodes
- supersession without historical deletion
- deterministic local tests
- DebateSubgraph candidate causal output

The Causal Store must prevent:

- Markdown files becoming the causal database
- vector similarity becoming causal truth
- common-sense facts polluting the store
- Debate, Execution, Test, or Final Review directly admitting global causal truth
- dependency-group evidence mixing
- admitted nodes depending on unadmitted candidate nodes
- deprecated, superseded, invalidated, or pending-revalidation nodes being used as normal truth

## Conceptual Model

Cause and effect are contextual roles. A node can be an effect in one reasoning chain and a cause in another.

Example:

```text
A -> B -> C -> D
E -> F -> G

Later:
B + E -> H
```

The later chain can use `B` directly if `B` is valid under the current context. It does not need to traverse from `A` every time.

Therefore:

- `CausalNode` is the primary abstraction.
- Dependency groups belong to nodes.
- Multiple dependency groups for one node represent alternative validity routes.
- Chains are query-time projections, not canonical stored objects.
- SQL dependency tables are implementation indexes, not a conceptual switch to edge-first design.

## Non-Goals

V1 must not:

- introduce Neo4j or a graph database service
- use Chroma, LanceDB, or a vector DB as canonical truth
- store raw debate transcripts as causal chains
- record general model-internal common knowledge
- optimize primary storage for direct human reading
- admit causal truth inside Debate, Execution, Test, or Final Review
- solve distributed multi-user causal consistency

## Technology Selection

### Canonical Store

Use SQLite.

Reasons:

- Aegis v0.1.2 targets personal local git projects.
- SQLite is local, deterministic, transactional, and testable.
- SQLite supports primary-key lookup, B-tree indexes, WAL mode, and FTS5.
- It avoids service dependency and operational complexity.

### Node ID

Use positive 63-bit SQLite `INTEGER` as `node_id`.

SQLite integers are signed 64-bit. Positive 63-bit IDs are sufficient for v1 and preserve simple primary-key indexing. If full unsigned `uint64_t` support is ever required, add an external representation field instead of changing the v1 primary contract.

### Lexical Recall

Use SQLite FTS5 as an independent rebuildable recall table.

FTS must not be used as canonical storage. It can be deleted and rebuilt from canonical tables.

### Semantic Recall

Use a rebuildable vector index behind an interface.

Acceptable v1 implementations:

- SQLite BLOB embeddings with in-process top-k search for small stores.
- FAISS or hnswlib sidecar for larger local stores.
- A future SQLite vector extension if stable in the target environment.

The vector index:

- can be stale
- must expose staleness
- must be rebuildable
- must not admit causal truth
- must not override status, scope, assumptions, invalidation, or admission state

## Common Knowledge Policy

Do not store AI-internalized common knowledge as explicit Knowledge dependencies.

Normally do not store:

- summer is hot
- air conditioning can cool a room
- lower temperature can improve comfort
- CSV is tabular
- charts can visualize numeric data

Store Knowledge refs only for project-specific verified facts:

- customer written constraints
- platform constraints
- deployment constraints
- repository-specific facts
- test-proven limits
- contractual requirements

## Data Model

### CausalNode

```yaml
CausalNode:
  node_id: int
  node_uuid: string
  created_at_utc: string
  updated_at_utc: string
  content: string
  semantic_summary: string
  status: candidate | admitted | invalidated | deprecated | superseded
  source_module: master | debate | execution | test | final_review | causal_review
  source_run_id: string | null
  source_artifact_ref: string | null
  root_kind: observation | test_result | user_constraint | design_decision | external_evidence | null
  strict_content_hash: string
  causal_identity_hash: string
  semantic_fingerprint: string | null
  duplicate_of_node_id: int | null
```

`content` must be the smallest useful causal statement. Long reports, raw documents, debate transcripts, and broad narratives belong in artifacts or artifact evidence and should be referenced.

Hash semantics:

- `strict_content_hash`: `sha256(normalized_content)`. Used for exact text duplication.
- `causal_identity_hash`: `sha256(normalized_content + normalized_scope + normalized_conditions + normalized_assumptions)`. Used for likely same causal identity under the same validity frame.
- `semantic_fingerprint`: approximate semantic duplicate key for admission review. It is advisory, not authoritative.

### DependencyGroup

```yaml
DependencyGroup:
  group_id: string
  node_id: int
  causal_dependencies: list[int]
  validity_refs:
    - ref_type: knowledge | test | external | artifact | repository_source
      ref_id: string
  knowledge_refs: list[string]  # legacy compatibility; converted to validity_refs with ref_type=knowledge
  evidence_refs: list[string]   # legacy compatibility; converted to validity_refs with ref_type=test
  scope: string
  conditions: list[string]
  assumptions: list[string]
  confidence: high | medium | low
  invalidation_conditions: list[string]
```

### DependencyGroup Semantics

Mandatory logic:

```text
Multiple DependencyGroups for one node are OR.
Fields inside one DependencyGroup are AND.
```

Symbolically:

```text
Node usable = GroupA valid OR GroupB valid OR GroupC valid

Group valid =
  all causal dependencies are usable
  AND scope matches
  AND stored conditions are available to the caller's review context
  AND stored assumptions are available to the caller's review context
  AND required refs are present
  AND active invalidation/revalidation state does not reject the node
```

Agents must never combine one group's evidence with another group's scope, assumptions, or conditions.

V1 enforces status, scope, dependency closure, group refs, pending revalidation, and lifecycle filters in code.
It stores conditions, assumptions, and invalidation conditions as first-class review material, but it does not perform full logical entailment over arbitrary natural-language conditions.

## SQLite Schema

### schema_migrations

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at_utc TEXT NOT NULL
);
```

### causal_nodes

```sql
CREATE TABLE causal_nodes (
  node_id INTEGER PRIMARY KEY,
  node_uuid TEXT NOT NULL UNIQUE,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  content TEXT NOT NULL,
  semantic_summary TEXT NOT NULL,
  status TEXT NOT NULL,
  source_module TEXT NOT NULL,
  source_run_id TEXT,
  source_artifact_ref TEXT,
  root_kind TEXT,
  strict_content_hash TEXT NOT NULL,
  causal_identity_hash TEXT NOT NULL,
  semantic_fingerprint TEXT,
  duplicate_of_node_id INTEGER,
  CHECK (status IN ('candidate', 'admitted', 'invalidated', 'deprecated', 'superseded')),
  CHECK (source_module IN ('master', 'debate', 'execution', 'test', 'final_review', 'causal_review')),
  CHECK (root_kind IS NULL OR root_kind IN ('observation', 'test_result', 'user_constraint', 'design_decision', 'external_evidence')),
  FOREIGN KEY (duplicate_of_node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_node_terms

```sql
CREATE TABLE causal_node_terms (
  node_id INTEGER NOT NULL,
  term TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (node_id, term),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_dependency_groups

```sql
CREATE TABLE causal_dependency_groups (
  group_id TEXT PRIMARY KEY,
  node_id INTEGER NOT NULL,
  scope TEXT NOT NULL,
  conditions_json TEXT NOT NULL,
  assumptions_json TEXT NOT NULL,
  confidence TEXT NOT NULL,
  invalidation_conditions_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  CHECK (confidence IN ('high', 'medium', 'low')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_dependency_nodes

```sql
CREATE TABLE causal_dependency_nodes (
  group_id TEXT NOT NULL,
  predecessor_node_id INTEGER NOT NULL,
  PRIMARY KEY (group_id, predecessor_node_id),
  FOREIGN KEY (group_id) REFERENCES causal_dependency_groups(group_id),
  FOREIGN KEY (predecessor_node_id) REFERENCES causal_nodes(node_id)
);
```

This table indexes node-owned dependencies. It is not the conceptual causal object.

### causal_node_refs

Node refs are broad provenance and source refs.

```sql
CREATE TABLE causal_node_refs (
  node_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (node_id, ref_type, ref_id),
  CHECK (ref_type IN ('knowledge', 'test', 'external', 'artifact', 'repository_source')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_group_refs

Group refs are validity-support refs.

```sql
CREATE TABLE causal_group_refs (
  group_id TEXT NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (group_id, ref_type, ref_id),
  CHECK (ref_type IN ('knowledge', 'test', 'external', 'artifact', 'repository_source')),
  FOREIGN KEY (group_id) REFERENCES causal_dependency_groups(group_id)
);
```

Rule:

```text
Use node refs for source/provenance.
Use group refs for validity support.
```

### causal_admission_records

```sql
CREATE TABLE causal_admission_records (
  node_id INTEGER NOT NULL,
  admitted_at_utc TEXT NOT NULL,
  admitted_by_module TEXT NOT NULL,
  admission_run_id TEXT,
  rationale TEXT NOT NULL,
  evidence_ref TEXT,
  CHECK (admitted_by_module IN ('master', 'causal_review')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_invalidation_records

```sql
CREATE TABLE causal_invalidation_records (
  node_id INTEGER NOT NULL,
  invalidated_at_utc TEXT NOT NULL,
  invalidated_by_module TEXT NOT NULL,
  invalidation_run_id TEXT,
  reason TEXT NOT NULL,
  invalidation_condition TEXT,
  CHECK (invalidated_by_module IN ('master', 'causal_review')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_supersession_records

```sql
CREATE TABLE causal_supersession_records (
  old_node_id INTEGER NOT NULL,
  new_node_id INTEGER NOT NULL,
  superseded_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  FOREIGN KEY (old_node_id) REFERENCES causal_nodes(node_id),
  FOREIGN KEY (new_node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_revalidation_queue

Use `queue_id` as primary key. A node may need revalidation for multiple independent reasons.

```sql
CREATE TABLE causal_revalidation_queue (
  queue_id TEXT PRIMARY KEY,
  node_id INTEGER NOT NULL,
  triggered_by_node_id INTEGER,
  trigger_type TEXT NOT NULL,
  queued_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  CHECK (trigger_type IN (
    'dependency_invalidated',
    'dependency_superseded',
    'dependency_deprecated',
    'scope_rule_changed',
    'knowledge_ref_changed',
    'evidence_ref_changed',
    'manual_review'
  )),
  CHECK (status IN ('pending', 'in_progress', 'resolved', 'dismissed')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id),
  FOREIGN KEY (triggered_by_node_id) REFERENCES causal_nodes(node_id)
);
```

Optional duplicate-spam guard:

```sql
CREATE UNIQUE INDEX idx_revalidation_dedupe_pending
ON causal_revalidation_queue(node_id, triggered_by_node_id, trigger_type)
WHERE status IN ('pending', 'in_progress');
```

### causal_embeddings

```sql
CREATE TABLE causal_embeddings (
  node_id INTEGER PRIMARY KEY,
  embedding_model_id TEXT NOT NULL,
  embedding BLOB NOT NULL,
  indexed_at_utc TEXT NOT NULL,
  source_content_hash TEXT NOT NULL,
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

`source_content_hash` should match `strict_content_hash`. A mismatch means the embedding is stale.

### causal_nodes_fts

Independent rebuildable FTS table:

```sql
CREATE VIRTUAL TABLE causal_nodes_fts USING fts5(
  node_id UNINDEXED,
  content,
  semantic_summary,
  semantic_keys,
  scope_terms,
  condition_terms,
  invalidation_terms
);
```

### Required Indexes

```sql
CREATE INDEX idx_dependency_predecessor
ON causal_dependency_nodes(predecessor_node_id);

CREATE INDEX idx_dependency_group_node
ON causal_dependency_groups(node_id);

CREATE INDEX idx_nodes_status
ON causal_nodes(status);

CREATE INDEX idx_nodes_duplicate_of
ON causal_nodes(duplicate_of_node_id);

CREATE INDEX idx_nodes_strict_content_hash
ON causal_nodes(strict_content_hash);

CREATE INDEX idx_nodes_causal_identity_hash
ON causal_nodes(causal_identity_hash);

CREATE UNIQUE INDEX idx_nodes_active_causal_identity_hash
ON causal_nodes(causal_identity_hash)
WHERE status IN ('candidate', 'admitted', 'deprecated', 'superseded');
```

## Lifecycle and Authority

### Status Lifecycle

```text
candidate -> admitted
candidate -> invalidated
admitted -> invalidated
admitted -> deprecated
admitted -> superseded
deprecated -> superseded
```

### Candidate Rule

Debate, Execution, and Final Review may propose candidate causal nodes. They may not directly admit nodes.

Test normally produces evidence/result refs, not causal truth.

### Admission Rule

Only Master or Causal Review may admit nodes.

Admission must:

- be transactional
- write admission records
- validate dependency closure
- validate group-level refs
- validate node refs
- validate duplicate state
- validate root observation requirements
- reject dependency cycles

### Candidate Closure Rule

An admitted node must not depend on a candidate node.

Exception:

```text
A node and its dependencies may be admitted together in the same atomic admission transaction.
```

Admission validation:

```text
1. all dependency node_ids exist
2. all selected dependencies are admitted or admitted in the same transaction
3. no invalidated dependency is used
4. no deprecated dependency is used in v1
5. superseded dependencies are replaced unless historical mode is explicitly requested
```

### Deprecated Dependency Policy

V1 forbids using deprecated dependencies in newly admitted nodes.

If future historical reasoning needs deprecated dependency use, add an explicit override table and review workflow. Do not leave deprecated dependency use implicit.

### Root Causal Observation Rule

An admitted root causal observation must have:

- `root_kind`
- trusted source ref
- admission rationale

Pure reasoning can create candidate root nodes only. It cannot create admitted root truth.

### Invalidation Rule

Invalidation must:

- write an invalidation record
- preserve history
- enqueue reverse dependents for revalidation
- not delete nodes
- not blindly cascade invalidation

A dependent node remains valid only if at least one dependency group remains valid.

### Supersession Rule

Supersession must:

- write a supersession record
- preserve the old node
- hide the old node from normal retrieval
- keep the old node available for historical retrieval
- reject self-supersession
- require the old node to be admitted or deprecated
- require the replacement node to be admitted

## Time Semantics

`created_at_utc` records when the row was created in the store. It is not causal proof.

Hard rule:

```text
The admitted dependency graph must not contain cycles.
```

Future optional fields:

```text
observed_at_utc
valid_from_utc
valid_to_utc
```

Do not implement those in v1 unless a tested workflow requires them.

## Retrieval Semantics

### Modes

```text
admitted_only
working_candidates
historical
include_invalidated_as_counterevidence
human_review
```

Default autonomous-agent retrieval mode:

```text
admitted_only
```

### Pending Revalidation Rule

Autonomous agent retrieval must exclude admitted nodes with pending or in-progress revalidation.

Human review and historical modes may include them with explicit warnings:

```yaml
node_id: 123
status: admitted
requires_revalidation: true
revalidation_reasons:
  - dependency_invalidated
  - knowledge_ref_changed
```

### Retrieval Pipeline

```text
query
  -> generate ASCII tokens and CJK bigrams/trigrams
  -> exact node_id lookup if present
  -> exact term recall from causal_node_terms
  -> FTS recall
  -> vector recall
  -> merge node_ids
  -> load canonical nodes from SQLite
  -> status filter
  -> pending-revalidation filter
  -> scope filter
  -> expose stored condition/assumption/invalidation material for review
  -> dependency group validation
  -> reverse-dependent expansion when useful
  -> agent rerank
  -> return causal context package
```

If FTS is unavailable, the result must expose degraded recall through warnings instead of silently hiding the failure.

### Rejected Node Reporting

Search results should include informative rejects:

```yaml
rejected_nodes:
  - node_id: 123
    reason: invalidated
  - node_id: 456
    reason: scope_mismatch
  - node_id: 789
    reason: dependency_not_admitted
  - node_id: 900
    reason: pending_revalidation
```

Agents must see both what is usable and what was rejected.

## Query-Time Projection

The store does not treat chains as canonical storage objects. It returns task-specific projections.

```yaml
CausalProjection:
  query: string
  mode: admitted_only | working_candidates | historical | include_invalidated_as_counterevidence | human_review
  root_node_ids: list[int]
  selected_nodes: list[int]
  selected_dependency_groups: list[string]
  dependency_paths: list[list[int]]
  rejected_nodes:
    - node_id: int
      reason: string
  invalidation_entrypoints:
    - node_id: int
      condition: string
```

## API Contract

```python
class CausalStore:
    def put_candidate(self, node: CausalNode) -> int:
        ...

    def get_node(self, node_id: int) -> CausalNode:
        ...

    def search_nodes(self, query: CausalQuery) -> CausalSearchResult:
        ...

    def expand_context(self, request: ExpandContextRequest) -> CausalContextPackage:
        ...

    def admit_nodes(self, request: AdmissionTransaction) -> AdmissionResult:
        ...

    def invalidate_node(self, request: InvalidationRequest) -> InvalidationResult:
        ...

    def supersede_node(self, request: SupersessionRequest) -> SupersessionResult:
        ...

    def rebuild_indexes(self) -> RebuildIndexResult:
        ...
```

### Error Codes

```text
NODE_NOT_FOUND
INVALID_DEPENDENCY
UNKNOWN_EXTERNAL_REF
CYCLE_DETECTED
STALE_EMBEDDING_INDEX
ADMISSION_REQUIRED
INVALIDATED_NODE_USED
INVALID_STATUS_TRANSITION
DEPENDENCY_NOT_ADMITTED
ROOT_SOURCE_REQUIRED
DUPLICATE_NODE
NEAR_DUPLICATE_REVIEW_REQUIRED
GROUP_REF_REQUIRED
SCOPE_MISMATCH
PENDING_REVALIDATION
DEPRECATED_DEPENDENCY_FORBIDDEN
SUPERSEDED_NODE_USED
```

## Interaction With Three Stores

Git history:

- records what happened
- can provide evidence refs
- does not become causal truth automatically

Knowledge:

- stores verified static facts and constraints
- can provide fact refs
- does not become causal conclusion automatically

Causal:

- stores conditional causal nodes
- admits only through Master or Causal Review
- preserves candidate/admitted/invalidation boundaries

## DebateSubgraph Integration

Debate workers maintain local causal chains during debate. Debate Leader merges worker chains into a candidate causal package.

Output shape:

```yaml
causal_package:
  selected_position: string
  rejected_positions: list[string]
  worker_chain_refs: list[string]
  merged_causal_nodes: list[CausalNode]
  dependency_groups: list[DependencyGroup]
  assumptions: list[string]
  scope: string
  invalidation_conditions: list[string]
  status: candidate
```

Rules:

- Debate output is candidate material.
- Debate does not admit global causal truth.
- Raw transcript is not a causal chain.
- A conclusion summary is not a causal chain.
- Worker attacks, concessions, and decisive objections may become causal nodes only when they contain reusable causal substance.
- Master or Causal Review handles admission.

## Project-Local File Layout

Recommended runtime layout:

```text
<project-root>/.aegis/stores/causal/causal.sqlite3
<project-root>/.aegis/stores/causal/vector.index
<project-root>/.aegis/stores/causal/index_meta.json
```

These runtime files should normally be ignored by git. If project snapshots are needed later, define an explicit export format instead of committing live databases by default.

## Implementation Order

1. SQLite migration system.
2. Final schema creation.
3. Pydantic models.
4. JSON-safe validation helpers.
5. `put_candidate`.
6. `get_node`.
7. dependency validation.
8. cycle detection.
9. group-level refs.
10. atomic `admit_nodes` transaction.
11. admission records.
12. invalidation records.
13. revalidation queue.
14. supersession records.
15. FTS rebuild.
16. retrieval modes.
17. query-time projection.
18. embedding adapter and stale-index detection.
19. DebateSubgraph integration.
20. Master or Causal Review admission workflow.

Do not integrate DebateSubgraph before these are working:

- `put_candidate`
- `admit_nodes`
- candidate closure validation
- cycle detection
- group-level refs
- admission records
- invalidation records
- revalidation queue

## Test Plan

### Unit Tests

- exact `node_id` lookup
- candidate write/read
- dependency group write/read
- group-level refs preserved
- node with multiple groups cannot mix refs across groups
- missing predecessor rejected
- dependency cycle rejected
- admitted node cannot depend on candidate node
- atomic admission can admit node and dependencies together
- root causal observation requires trusted source
- deprecated dependency rejected in v1
- invalidated node filtered from normal retrieval
- superseded node hidden from normal retrieval
- pending-revalidation node excluded from autonomous retrieval
- FTS index can be rebuilt
- FTS unavailability is visible as degraded recall
- CJK near-lexical retrieval works through deterministic CJK n-grams
- stale embedding index detected by hash mismatch
- strict duplicate detected by `strict_content_hash`
- active causal identity duplicate prevented by database-level `causal_identity_hash` uniqueness
- common knowledge does not require Knowledge refs

### Integration Tests

- Debate causal package writes candidate nodes.
- Master or Causal Review admits selected nodes.
- semantic query returns relevant admitted nodes.
- search reports rejected-node reasons.
- invalidating predecessor queues dependent revalidation.
- invalidating one dependency group does not invalidate node if another group remains valid.
- artifact ref does not become Knowledge fact.
- Knowledge fact does not become causal conclusion.
- vector index deletion does not destroy canonical causal state.
- schema migration table records applied migration.

## Acceptance Criteria

Causal Store v1 is implementation-ready when:

- `CausalNode` remains the primary abstraction.
- SQLite is the only canonical store.
- FTS and vector indexes are rebuildable recall layers.
- group-level refs exist and are enforced.
- group-level refs preserve exact ref type and ref id.
- admission, invalidation, supersession, and revalidation are auditable.
- admitted dependency closure is enforced.
- active causal identity duplicates are database-constrained.
- supersession follows the explicit lifecycle state machine.
- FTS recall degradation is visible to the caller.
- CJK lexical retrieval is covered by deterministic tests.
- root observations require trusted sources.
- dependency cycles are rejected.
- deprecated dependencies are forbidden in v1 admissions.
- pending-revalidation nodes are excluded from autonomous retrieval.
- retrieval distinguishes admitted, candidate, historical, invalidated, deprecated, superseded, and pending-revalidation material.
- Debate can write candidate causal packages without mutating admitted global truth.

## Final Position

The Causal Store v1 should not be rewritten into a graph database design. The node-space abstraction is correct.

The implementation priority is hard enforcement:

- make validity explicit
- bind evidence to the correct dependency group
- make admission auditable
- keep invalidation non-destructive
- keep retrieval truth-state-aware
- keep schema evolution deterministic

This is the final Causal Store design baseline for the Aegis v0.1.2 implementation phase.
