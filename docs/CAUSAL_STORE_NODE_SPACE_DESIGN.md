# Causal Store Node Space Design

## Status

Draft design for the Aegis v0.1.2 LangGraph rebuild.

## Purpose

The Causal Store is the long-term project-local store for conditional causal reasoning. It is not a Markdown archive, not a Knowledge Store replacement, and not a vector database of free text. Its core abstraction is a reusable causal node space where each node can act as a result in one reasoning chain and as a cause in another reasoning chain.

The design optimizes for agent retrieval, causal reuse, invalidation, traceability, and low-complexity exact lookup. Human-readable exports are optional debugging or reporting views, not the primary storage format.

## Requirements

The Causal Store must support:

- Exact `node_id` lookup with low complexity.
- Semantic retrieval of relevant causal nodes.
- Reuse of one causal node across multiple reasoning chains.
- Sparse storage that avoids recording AI-internalized common knowledge.
- Conditional validity through scope, assumptions, conditions, confidence, and invalidation conditions.
- Traceability to project facts, Archive evidence, Test evidence, or external evidence when such evidence is relevant.
- Project-local operation for personal local git projects.
- Rebuildable retrieval indexes that do not become the source of truth.
- Admission separation between candidate causal output and admitted causal state.

The Causal Store must not:

- Store common-sense or basic model-internal knowledge as explicit dependencies.
- Treat Knowledge facts as causal conclusions by default.
- Treat Archive records as system facts by default.
- Treat Debate output as admitted global causal truth by default.
- Use Markdown files as the canonical causal database.
- Use vector similarity as causal truth.

## Design Premises

Cause and effect are relative positions, not fixed identities. A node can be an effect in one reasoning context and a cause in another. Therefore, the Causal Store should not be designed as a fixed two-dimensional chain or strict layered graph.

Example:

```text
A -> B -> C -> D
E -> F -> G
```

A valid later reasoning chain can directly use:

```text
B + E -> H
```

The system does not need to traverse from `A` every time it wants to use `B`. If `B` is already a valid node under its own conditions, it can directly serve as a causal dependency in a new reasoning context.

Therefore:

- The canonical abstraction is `CausalNode`.
- Dependency groups belong to nodes.
- Reasoning chains are query-time projections over the node space.
- Storage may use normalized tables for efficiency, but those tables must not change the conceptual model into edge-first reasoning.

## Technology Selection

### Canonical Store: SQLite

SQLite is the authoritative local database.

Reasons:

- It is local and project-friendly.
- It supports transactional writes.
- It supports reliable primary-key lookup.
- It supports B-tree indexes and FTS5.
- It does not require a separate service.
- It fits the Aegis personal local git project target.

### Exact Lookup

Use a primary key index for `node_id`.

Recommended v1 choice:

```text
node_id: positive 63-bit INTEGER
```

SQLite `INTEGER` is signed 64-bit. Using the positive 63-bit range preserves simple indexing and is sufficient for personal project scale. If full unsigned `uint64_t` range is later required, it can be represented as `BLOB(8)` or canonical decimal `TEXT`, but that should not be the v1 default.

### Lexical and Semantic-Key Search

Use SQLite FTS5 for:

- node content
- semantic summary
- semantic keys
- scope terms
- condition terms
- invalidation terms

FTS5 is not the source of truth. It is a recall mechanism.

### Vector Retrieval

Use a rebuildable sidecar semantic index behind an interface.

Initial implementations may be:

- SQLite-stored embedding blobs plus in-process top-k search for small stores.
- A local FAISS or hnswlib sidecar for larger stores.
- A future SQLite vector extension if it is stable in the project environment.

The vector index is cache-like:

- It can be deleted.
- It can be rebuilt from SQLite.
- It cannot admit causal truth.
- It cannot override status, scope, assumptions, or invalidation rules.

## Core Model

### CausalNode

```yaml
CausalNode:
  node_id: uint64
  created_at_utc: string
  content: string
  semantic_summary: string
  semantic_keys: list[string]
  status: candidate | admitted | invalidated | deprecated | superseded
  dependency_groups: list[DependencyGroup]
  source:
    module: master | debate | execution | test | final_review | causal_review
    run_id: string | null
    artifact_ref: string | null
```

`content` should be the smallest useful semantic statement. It should not contain long debate transcripts, raw documents, or broad narrative reports. Long source material belongs in artifacts, Archive, or external refs.

### DependencyGroup

```yaml
DependencyGroup:
  group_id: string
  causal_dependencies: list[uint64]
  knowledge_refs: list[string]
  evidence_refs: list[string]
  conditions: list[string]
  assumptions: list[string]
  scope: string
  confidence: high | medium | low
  invalidation_conditions: list[string]
```

Meaning:

- A node may have zero or more dependency groups.
- A node is usable only under a dependency group whose conditions and scope match the current reasoning context.
- A dependency group is node-owned support structure, not the primary causal object.
- `knowledge_refs` are optional and should be used only for project-specific verified facts or constraints.
- `evidence_refs` may point to Archive, Test results, external documents, or other evidence artifacts.

### Common Knowledge Policy

Do not write common knowledge into `knowledge_refs` or dependency groups.

Examples that should normally not become explicit dependencies:

- summer is usually hot
- air conditioning can cool a room
- lower temperature can improve thermal comfort
- a chart can visualize numeric data
- CSV is a tabular data format

Examples that may become Knowledge refs:

- the current project requires Python 3.11
- the customer email explicitly requires CSV export
- the target deployment system is Windows
- the current production database is PostgreSQL
- the test report proves a specific latency bound was exceeded
- a contract requires a specific platform or library

## Conceptual Example

Statement sequence:

```text
Summer is hot.
Air conditioning lowers indoor temperature.
Lower indoor temperature improves comfort.
People at home tend to turn on air conditioning.
```

Canonical node projection:

```text
N1: summer environment has high temperature
N2: indoor thermal discomfort increases
N3: air conditioner is turned on
N4: indoor temperature decreases
N5: human comfort improves
N6: people at home tend to turn on air conditioning
```

One reasoning projection:

```text
N1 -> N2 -> N3 -> N4 -> N5 -> N6
```

Another later projection can directly use `N6`:

```text
N6 -> increased household summer electricity usage
```

The second projection does not need to restate or traverse all earlier nodes if `N6` is already valid under the current scope.

## SQLite Schema

### causal_nodes

```sql
CREATE TABLE causal_nodes (
  node_id INTEGER PRIMARY KEY,
  created_at_utc TEXT NOT NULL,
  content TEXT NOT NULL,
  semantic_summary TEXT NOT NULL,
  status TEXT NOT NULL,
  source_module TEXT NOT NULL,
  source_run_id TEXT,
  source_artifact_ref TEXT
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

This table is a storage index for node-owned dependencies. It is not the conceptual causal object.

### causal_external_refs

```sql
CREATE TABLE causal_external_refs (
  node_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

Allowed `ref_type` values:

```text
archive
knowledge
test
external
artifact
```

### causal_embeddings

```sql
CREATE TABLE causal_embeddings (
  node_id INTEGER PRIMARY KEY,
  embedding_model_id TEXT NOT NULL,
  embedding BLOB NOT NULL,
  indexed_at_utc TEXT NOT NULL,
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);
```

### FTS5 Table

```sql
CREATE VIRTUAL TABLE causal_nodes_fts USING fts5(
  content,
  semantic_summary,
  semantic_keys,
  scope_terms,
  invalidation_terms,
  content='causal_nodes',
  content_rowid='node_id'
);
```

## Retrieval Flow

### Exact Retrieval

```text
node_id -> SQLite primary key lookup -> CausalNode
```

### Semantic Retrieval

```text
query
  -> FTS5 recall
  -> vector recall
  -> merge candidate node_ids
  -> load full nodes from SQLite
  -> filter by status, scope, time, invalidation
  -> expand predecessor and dependent nodes
  -> agent rerank
  -> return causal context package
```

The retrieval layer returns candidates. It does not decide causal validity.

## Query-Time Projection

Reasoning chains are not the primary stored object. They are projections produced for a specific task.

```yaml
CausalProjection:
  query: string
  root_node_ids: list[uint64]
  selected_nodes: list[uint64]
  dependency_paths: list[list[uint64]]
  rejected_nodes:
    - node_id: uint64
      reason: string
  invalidation_entrypoints:
    - node_id: uint64
      condition: string
```

This keeps the store node-centric while still letting Debate, Execution, Master, and Causal Review work with explicit chains when needed.

## Lifecycle

Recommended status lifecycle:

```text
candidate -> admitted -> superseded
candidate -> invalidated
admitted -> invalidated
admitted -> deprecated
```

Meaning:

- `candidate`: proposed causal node, not global truth.
- `admitted`: accepted into project causal state after review.
- `invalidated`: no longer valid under its previous scope or assumptions.
- `deprecated`: still historically meaningful, but should not be preferred.
- `superseded`: replaced by a newer causal node or structure.

Module permissions:

- Debate may produce `candidate`.
- Execution may produce `candidate`.
- Test usually produces evidence, not causal truth.
- Final Review may recommend admission or rejection.
- Master or a Causal Review node decides admission.
- No module may silently treat `candidate` as admitted truth.

## Consistency Rules

The store must enforce:

- `node_id` uniqueness.
- dependency references must point to existing causal nodes.
- adjacent predecessor `created_at_utc` should not be later than the dependent node.
- invalidated nodes are excluded from normal retrieval unless explicitly requested as historical counterevidence.
- admitted nodes must have at least one valid dependency group unless explicitly marked as a root causal observation.
- Knowledge refs must point to verified Knowledge Store facts, not developer claims.
- Archive refs are evidence references only, not automatic facts.
- Vector index staleness must be detectable.

## API Contract

Minimal Python-facing interface:

```python
class CausalStore:
    def put_candidate(self, node: CausalNode) -> int:
        ...

    def get_node(self, node_id: int) -> CausalNode:
        ...

    def search_nodes(self, query: CausalQuery) -> CausalSearchResult:
        ...

    def expand_context(self, node_ids: list[int], depth: int) -> CausalContextPackage:
        ...

    def admit_node(self, node_id: int, admission: AdmissionRecord) -> None:
        ...

    def invalidate_node(self, node_id: int, invalidation: InvalidationRecord) -> None:
        ...

    def rebuild_indexes(self) -> RebuildIndexResult:
        ...
```

Recommended error codes:

```text
NODE_NOT_FOUND
INVALID_DEPENDENCY
UNKNOWN_EXTERNAL_REF
CYCLE_DETECTED
STALE_EMBEDDING_INDEX
ADMISSION_REQUIRED
INVALIDATED_NODE_USED
INVALID_STATUS_TRANSITION
```

## Interaction With Debate

Debate Leader output should become a causal package:

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

- Debate does not write admitted global truth.
- Debate writes candidate causal nodes or returns candidate packages for Master/Causal Review.
- Worker attacks and concessions can become causal nodes when they contain reusable causal substance.
- Raw transcript is not a causal chain.
- A conclusion summary is not a causal chain.

## Project-Local File Layout

Recommended local runtime location:

```text
<project-root>/.aegis/stores/causal/causal.sqlite3
<project-root>/.aegis/stores/causal/vector.index
<project-root>/.aegis/stores/causal/index_meta.json
```

These files should normally be ignored by git unless a future explicit snapshot/export policy is defined.

## Testing Plan

Unit tests:

- exact `node_id` lookup
- candidate write/read
- dependency group write/read
- missing predecessor rejection
- FTS5 search
- vector index rebuild
- invalidated node filtering
- candidate does not equal admitted
- common knowledge does not require Knowledge refs

Integration tests:

- Debate causal package writes candidate nodes.
- Master/Causal Review admits selected nodes.
- semantic query returns relevant nodes and expands causal dependencies.
- invalidation condition excludes stale nodes.
- deleted vector index is rebuilt from SQLite.
- Knowledge refs and Archive refs remain references, not truth upgrades.

## Initial Implementation Recommendation

Implement v1 in this order:

1. SQLite schema and migrations.
2. Pydantic models for `CausalNode`, `DependencyGroup`, and query packages.
3. `put_candidate`, `get_node`, and dependency validation.
4. FTS5 semantic-key retrieval.
5. Query-time causal projection.
6. Admission and invalidation lifecycle.
7. Rebuildable embedding index adapter.
8. DebateSubgraph integration.

Do not introduce Neo4j, Chroma, LanceDB, or a service database in v1. They can be evaluated later only if local SQLite plus a rebuildable semantic index becomes insufficient.
