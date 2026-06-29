# Causal Store Node Space Hardened Design

## Status

Draft v2 design for the Aegis v0.1.2 LangGraph rebuild.

This document supersedes the initial causal node-space draft as the implementation-oriented design baseline. The core abstraction remains unchanged: the Causal Store is a reusable causal node space, not a Markdown document collection, not a raw vector store, and not a fixed chain graph.

## Executive Decision

Use SQLite as the canonical local Causal Store, with:

- `CausalNode` as the primary causal object.
- node-owned `DependencyGroup` records for conditional support.
- group-level evidence and knowledge references.
- admission, invalidation, supersession, and revalidation audit records.
- FTS5 and vector indexes as rebuildable recall indexes only.
- query-time causal projections instead of stored fixed chains.

The system must preserve causal candidates without letting temporary agent output become admitted project truth.

## Design Goals

The Causal Store must support:

- exact `node_id` lookup
- semantic retrieval
- causal reuse across contexts
- conditional validity
- admission separation
- invalidation and revalidation
- evidence traceability
- local project operation
- deterministic tests
- future DebateSubgraph integration

The Causal Store must prevent:

- common knowledge pollution
- vector search as truth
- Markdown as canonical storage
- Debate or Execution directly writing admitted causal truth
- mixing evidence across dependency groups
- admitted nodes depending on unadmitted candidates
- silent invalidation of dependent reasoning

## First-Principles Model

Cause and effect are contextual roles. A node can be an effect in one chain and a cause in another.

Example:

```text
A -> B -> C -> D
E -> F -> G

Later:
B + E -> H
```

The later reasoning does not need to traverse from `A` if `B` is already a valid causal node under the current context.

Therefore:

- The canonical object is `CausalNode`.
- Dependencies belong to the node.
- Dependency groups express conditional support for a node.
- Reasoning chains are query-time projections over the node space.
- Storage tables may normalize dependencies, but the conceptual model remains node-first.

## Non-Goals

The v1 implementation must not:

- introduce Neo4j or another service database
- use Chroma, LanceDB, or a vector DB as canonical truth
- store raw debate transcripts as causal chains
- record general model-internal common knowledge
- make all causal data human-readable by default
- implement global truth admission inside Debate, Execution, Test, or Final Review
- solve distributed multi-user causal store consistency

## Technology Selection

### Canonical Store

Use SQLite.

Reasoning:

- Aegis v0.1.2 targets personal local git projects.
- SQLite is local, deterministic, transactional, and easy to test.
- SQLite supports primary-key lookup, normal indexes, WAL mode, and FTS5.
- No separate runtime service is required.

### Exact Lookup

Use a positive 63-bit SQLite `INTEGER` primary key for `node_id`.

SQLite stores signed 64-bit integers. Positive 63-bit IDs keep the implementation simple and stable. If the project later requires the full unsigned `uint64_t` range, add an external representation field instead of changing the primary storage contract.

### Lexical Recall

Use SQLite FTS5 as a rebuildable recall index.

FTS5 must not be treated as canonical storage. It can be deleted and rebuilt from canonical tables.

### Semantic Recall

Use a rebuildable vector index behind an interface.

Initial options:

- SQLite BLOB embeddings with in-process top-k search for small stores.
- FAISS or hnswlib sidecar for larger local stores.
- A SQLite vector extension later if stable in the local environment.

The vector index:

- may be stale
- must expose staleness
- must be rebuildable
- must not decide causal validity
- must not override status, scope, assumptions, invalidation, or admission state

## Core Data Model

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
  content_hash: string
  semantic_fingerprint: string | null
  duplicate_of_node_id: int | null
```

`content` is the smallest useful causal statement. Long reports, transcripts, raw documents, or broad narratives must be stored as artifacts or artifact evidence and referenced from the node.

### DependencyGroup

```yaml
DependencyGroup:
  group_id: string
  node_id: int
  causal_dependencies: list[int]
  knowledge_refs: list[string]
  evidence_refs: list[string]
  scope: string
  conditions: list[string]
  assumptions: list[string]
  confidence: high | medium | low
  invalidation_conditions: list[string]
```

### DependencyGroup Semantics

The logical semantics are mandatory:

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
  AND conditions match
  AND assumptions are accepted
  AND required evidence refs are present
  AND invalidation conditions are not triggered
```

Agents must not mix one group's evidence with another group's scope, assumptions, or conditions.

## Common Knowledge Policy

Do not store common-sense or model-internalized facts as Knowledge dependencies.

Normally do not store:

- summer is hot
- air conditioning can cool a room
- lower temperature can improve thermal comfort
- CSV is tabular
- charts can visualize numeric data

Store Knowledge refs only for project-specific verified facts:

- customer written constraints
- platform or deployment constraints
- verified project configuration
- test-proven limits
- contractual requirements
- repository-specific facts

## SQLite Schema Direction

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
  content_hash TEXT NOT NULL,
  semantic_fingerprint TEXT,
  duplicate_of_node_id INTEGER,
  CHECK (status IN ('candidate', 'admitted', 'invalidated', 'deprecated', 'superseded')),
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

This is a storage index for node-owned dependencies. It is not the conceptual causal object.

### causal_node_refs

Use node refs for broad provenance and source artifacts.

```sql
CREATE TABLE causal_node_refs (
  node_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (node_id, ref_type, ref_id),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### causal_group_refs

Use group refs for validity support.

```sql
CREATE TABLE causal_group_refs (
  group_id TEXT NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (group_id, ref_type, ref_id),
  FOREIGN KEY (group_id) REFERENCES causal_dependency_groups(group_id)
);
```

Allowed `ref_type` values:

```text
artifact
knowledge
test
external
artifact
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

```sql
CREATE TABLE causal_revalidation_queue (
  node_id INTEGER PRIMARY KEY,
  triggered_by_node_id INTEGER NOT NULL,
  queued_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id),
  FOREIGN KEY (triggered_by_node_id) REFERENCES causal_nodes(node_id)
);
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

### causal_nodes_fts

FTS is an independent rebuildable recall table.

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

### Admission Rule

Only Master or Causal Review may admit nodes.

Admission must:

- be transactional
- write an admission record
- validate dependency closure
- validate group-level evidence
- validate refs
- validate duplicate status
- validate root observation requirements

### Candidate Closure Rule

An admitted node must not depend on a candidate node.

Exception: a node and its dependencies may be admitted together in the same atomic admission transaction.

Admission validation:

```text
1. all dependency node_ids exist
2. all selected dependency nodes are admitted or admitted in the same transaction
3. no invalidated dependency is used
4. deprecated dependencies require explicit rationale
5. superseded dependencies are replaced unless historical reasoning is explicitly requested
```

### Root Causal Observation Rule

A root causal observation is allowed only when it has:

- `root_kind`
- trusted source ref
- admission rationale

Pure reasoning cannot create admitted root truth. Pure reasoning may create a candidate root node only.

### Invalidation Rule

Invalidation must:

- write an invalidation record
- preserve history
- enqueue reverse dependents for revalidation
- not automatically delete or blindly cascade invalidation

A dependent node remains valid only if at least one dependency group remains valid.

### Supersession Rule

Supersession must:

- write a supersession record
- preserve the old node
- hide superseded nodes from normal retrieval
- keep superseded nodes available for historical reasoning

## Time Semantics

`created_at_utc` records when the store row was created. It is not causal proof.

Do not use `created_at_utc` as a hard causal direction rule.

Hard rule:

```text
The admitted dependency graph must not contain cycles.
```

Optional future fields:

```text
observed_at_utc
valid_from_utc
valid_to_utc
```

These can be added later if project workflows need temporal validity reasoning.

## Retrieval Semantics

### Default Retrieval

Normal retrieval returns admitted nodes only.

Explicit retrieval modes:

```text
admitted_only
working_candidates
historical
include_invalidated_as_counterevidence
```

### Retrieval Pipeline

```text
query
  -> exact node_id lookup if present
  -> exact term recall from causal_node_terms
  -> FTS recall
  -> vector recall
  -> merge node_ids
  -> load canonical nodes from SQLite
  -> status filter
  -> scope/condition/assumption filter
  -> invalidation filter
  -> dependency group validation
  -> reverse-dependent expansion if useful
  -> agent rerank
  -> return causal context package
```

### Rejected Candidate Reporting

Search results should report informative rejects:

```yaml
rejected_nodes:
  - node_id: 123
    reason: invalidated
  - node_id: 456
    reason: scope_mismatch
  - node_id: 789
    reason: dependency_not_admitted
```

Agents need to know both what is usable and what must not be used.

## Query-Time Projection

The store does not treat chains as canonical objects. It produces projections for task-specific reasoning.

```yaml
CausalProjection:
  query: string
  mode: admitted_only | working_candidates | historical
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
```

## DebateSubgraph Integration

Debate workers maintain local causal chains during debate. The Debate Leader merges worker chains into a candidate causal package.

Debate output:

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

These runtime files should normally be ignored by git. If project snapshots become necessary later, define an explicit export format instead of committing live runtime databases by default.

## Implementation Order

Recommended implementation order:

1. SQLite schema and migration layer.
2. Pydantic models and JSON-safe validation.
3. Transaction layer with WAL mode.
4. `put_candidate` and `get_node`.
5. dependency validation and cycle detection.
6. group-level refs.
7. admission records and `admit_nodes`.
8. closure validation for admitted nodes.
9. invalidation records and revalidation queue.
10. supersession records.
11. FTS5 rebuildable recall index.
12. query-time projection.
13. embedding adapter and stale-index detection.
14. DebateSubgraph integration.
15. Master/Causal Review admission workflow.

Do not integrate DebateSubgraph before candidate write, closure validation, and admission records exist.

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
- invalidated node filtered from normal retrieval
- superseded node hidden from normal retrieval
- FTS index can be rebuilt
- stale embedding index detected
- common knowledge does not require Knowledge refs

### Integration Tests

- Debate causal package writes candidate nodes.
- Master/Causal Review admits selected nodes.
- semantic query returns relevant admitted nodes.
- search reports rejected-node reasons.
- invalidating predecessor queues dependent revalidation.
- invalidating one dependency group does not invalidate node if another group remains valid.
- artifact ref does not become Knowledge fact.
- Knowledge fact does not become causal conclusion.
- vector index deletion does not destroy canonical causal state.

## Acceptance Criteria

The Causal Store v1 is implementation-ready only when:

- `CausalNode` remains the primary abstraction.
- SQLite is the only canonical store.
- FTS/vector indexes are rebuildable recall layers.
- group-level refs exist.
- admission, invalidation, and supersession are auditable.
- admitted dependency closure is enforced.
- root observations require trusted sources.
- invalidation triggers revalidation instead of blind deletion.
- retrieval distinguishes admitted, candidate, historical, invalidated, deprecated, and superseded material.
- Debate can write candidate causal packages without mutating admitted global truth.

## Final Position

The design should not be rewritten into a graph database design. The original node-space abstraction is correct. The required change is hardening: make validity, evidence binding, admission, invalidation, and retrieval semantics explicit enough that future agents cannot turn candidate reasoning into unreviewed truth.
