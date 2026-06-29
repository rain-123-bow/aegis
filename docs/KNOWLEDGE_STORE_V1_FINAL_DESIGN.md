# Knowledge Store v1 Final Design

## Status

Design baseline for the Aegis v0.1.2 LangGraph rebuild.

This document defines the agent-native Knowledge Store. It is intentionally aligned with `docs/CAUSAL_STORE_V1_FINAL_DESIGN.md`, but it does not duplicate the Causal Store.

## Executive Decision

Aegis Knowledge Store v1 is a project-local, SQLite-backed verified fact store.

The canonical object is `KnowledgeFact`. A knowledge fact is a verified static fact, constraint, environment property, interface contract, customer-written requirement, platform rule, or measured non-causal condition.

The Knowledge Store is not optimized for direct human reading. It is optimized for agent retrieval, mandatory applicability recall, missing-knowledge detection, and typed evidence traceability.

The store must solve a problem that simple semantic search cannot solve:

> An agent may not know that an unusual verified fact is relevant to the current task.

Therefore, each fact must include not only the fact itself, but also an applicability profile describing when the fact must be recalled.

## Relationship to Other Stores

### Project history

git commit history records what happened.

git commit history entries do not automatically become Knowledge facts.

### Knowledge

Knowledge stores verified static facts and constraints.

Knowledge does not store causal conclusions. It can support causal review, but it cannot directly become a Causal Store write.

### Causal

Causal stores inferred judgments with why, evidence, scope, assumptions, and invalidation conditions.

Knowledge facts may be referenced by Causal dependency groups, but Knowledge facts are not themselves causal chains.

## Core Requirements

The Knowledge Store must support:

- exact `knowledge_id` lookup
- structured fact lookup
- mandatory applicability-trigger recall
- semantic retrieval as a supplemental recall path
- CJK and mixed-language deterministic lexical recall
- project, repository, module, device, host, platform, version, customer, and time scoping
- typed evidence refs
- candidate vs admitted separation
- rejection of semantically incomplete facts
- detection of missing required knowledge
- invalidation and revalidation of dependent facts
- supersession without historical deletion
- deterministic local tests
- agent-native output packages

The Knowledge Store must prevent:

- raw user text becoming a fact
- developer claims becoming admitted Knowledge
- git commit history entries becoming Knowledge facts without verification
- Knowledge facts becoming Causal truth without causal construction and review
- common model-internal knowledge polluting the project store
- semantic search being treated as complete recall
- facts without scope, evidence, or applicability being admitted
- human-readable Markdown files becoming the canonical database

## Non-Goals

V1 must not:

- optimize primary storage for direct human browsing
- use Markdown files as the canonical Knowledge Store
- use a vector database as the canonical truth store
- solve arbitrary open-world relevance by infinite semantic expansion
- treat every possible fact as globally relevant
- store general common knowledge already internalized by the model
- admit facts from user preference alone
- admit causal claims as Knowledge facts
- solve distributed multi-user consistency

## Conceptual Model

The Knowledge Store has two equally important parts:

1. `KnowledgeFact`: the verified fact itself.
2. `ApplicabilityProfile`: the conditions under which the fact must be considered.

Facts are not enough. A fact that cannot be reliably recalled when relevant is not operationally useful.

Example:

```text
Fact:
Component X aging causes high-load CPU-to-storage read throughput to decline by 12%-28%.

Applicability:
Must be considered when a task involves CPU throughput, storage read performance,
high-load benchmarks, unexplained I/O latency, or capacity planning on affected hosts.
```

An agent does not need to guess that "component aging" is relevant. The retrieval system must recall this fact because the task context matches the applicability profile.

## Common Knowledge Policy

Do not store AI-internalized common knowledge as explicit Knowledge facts.

Normally do not store:

- CSV is tabular
- Python can parse JSON
- high load can reduce performance
- servers have CPU and memory
- tests can produce evidence

Store only verified project-specific facts or constraints:

- customer written requirements
- platform limits
- repository-specific contracts
- host-specific hardware facts
- measured benchmark results
- dependency versions actually used by the project
- deployment environment constraints
- interface schemas
- safety or governance rules accepted by Master

## Data Model

### KnowledgeFact

```yaml
KnowledgeFact:
  knowledge_id: int
  knowledge_uuid: string
  created_at_utc: string
  updated_at_utc: string
  status: candidate | admitted | invalidated | deprecated | superseded
  fact_kind: environment | platform | dependency | interface | customer_constraint | hardware | performance_limit | policy | repository | test_observation | external_requirement
  subject:
    kind: project | repository | module | file | function | host | device | component | dependency | customer | platform | runtime | api | dataset | process
    id: string
    attributes: object
  predicate: string
  object:
    kind: value | range | enum | ref | structured
    value: object
    unit: string | null
  qualifiers:
    conditions: list[string]
    assumptions: list[string]
    measurement_context: object
    validity_window: object
  semantic_summary: string
  semantic_keys: list[string]
  fact_identity_hash: string
  strict_content_hash: string
  semantic_fingerprint: string | null
  source_module: master | debate | execution | test | final_review | knowledge_review
  source_run_id: string | null
  source_artifact_ref: string | null
```

`subject`, `predicate`, and `object` form the canonical static fact.

`semantic_summary` and `semantic_keys` are recall aids, not canonical truth.

### ApplicabilityProfile

```yaml
ApplicabilityProfile:
  profile_id: string
  knowledge_id: int
  applies_to_scope:
    projects: list[string]
    repositories: list[string]
    modules: list[string]
    files: list[string]
    hosts: list[string]
    devices: list[string]
    platforms: list[string]
    versions: list[string]
    customers: list[string]
    environments: list[string]
  affected_entities: list[string]
  affected_operations: list[string]
  affected_qualities: list[string]
  required_conditions: list[string]
  risk_classes: list[string]
  task_intents: list[string]
  lifecycle_phases: list[string]
  must_consider_when: list[string]
  exclude_when: list[string]
  priority: critical | high | medium | low
```

Applicability fields are machine-oriented. They are not prose summaries.

The `must_consider_when` field is the hard recall mechanism. If current task context matches it, the fact must be returned even when semantic search alone would miss it.

### EvidenceRef

```yaml
EvidenceRef:
  ref_type: test | external | artifact | customer_written | platform_doc | repository_source | manual_admission
  ref_id: string
  verifier: master | test | knowledge_review | external_authority
  verified_at_utc: string
  verification_method: string
```

Developer claims may be preserved as source artifacts, but they are not sufficient evidence for admitted Knowledge.

### InvalidationRule

```yaml
InvalidationRule:
  rule_id: string
  knowledge_id: int
  invalidation_condition: string
  affected_scope: object
  revalidation_required: bool
```

Examples:

- component replaced
- dependency upgraded
- customer requirement superseded
- platform version changed
- benchmark no longer reproduces
- source artifact withdrawn

### MissingKnowledgeNeed

```yaml
MissingKnowledgeNeed:
  need_id: string
  task_context_id: string
  required_dimension: string
  reason_required: string
  blocking_level: hard_block | needs_user_clarification | request_test_measurement | request_evidence_artifact_lookup
  acceptable_sources: list[string]
  generated_at_utc: string
```

The Knowledge Store must not silently assume missing facts.

If a task requires a fact that is not present, the system must return a missing-knowledge need.

## Canonical Store

Use SQLite.

Reasons:

- Aegis v0.1.2 targets personal local git projects.
- SQLite is local, deterministic, transactional, and testable.
- SQLite supports primary-key lookup, B-tree indexes, WAL mode, and FTS5.
- It avoids service dependency and operational complexity.

SQLite is the only canonical store.

FTS and embedding indexes are rebuildable recall layers.

## Suggested SQLite Schema

### knowledge_facts

```sql
CREATE TABLE knowledge_facts (
  knowledge_id INTEGER PRIMARY KEY,
  knowledge_uuid TEXT NOT NULL UNIQUE,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_kind TEXT NOT NULL,
  subject_kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  subject_attributes_json TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_kind TEXT NOT NULL,
  object_json TEXT NOT NULL,
  unit TEXT,
  qualifiers_json TEXT NOT NULL,
  semantic_summary TEXT NOT NULL,
  source_module TEXT NOT NULL,
  source_run_id TEXT,
  source_artifact_ref TEXT,
  fact_identity_hash TEXT NOT NULL,
  strict_content_hash TEXT NOT NULL,
  semantic_fingerprint TEXT,
  CHECK (status IN ('candidate', 'admitted', 'invalidated', 'deprecated', 'superseded'))
);
```

### knowledge_semantic_keys

```sql
CREATE TABLE knowledge_semantic_keys (
  knowledge_id INTEGER NOT NULL,
  semantic_key TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, semantic_key),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_applicability_profiles

```sql
CREATE TABLE knowledge_applicability_profiles (
  profile_id TEXT PRIMARY KEY,
  knowledge_id INTEGER NOT NULL,
  applies_to_scope_json TEXT NOT NULL,
  affected_entities_json TEXT NOT NULL,
  affected_operations_json TEXT NOT NULL,
  affected_qualities_json TEXT NOT NULL,
  required_conditions_json TEXT NOT NULL,
  risk_classes_json TEXT NOT NULL,
  task_intents_json TEXT NOT NULL,
  lifecycle_phases_json TEXT NOT NULL,
  must_consider_when_json TEXT NOT NULL,
  exclude_when_json TEXT NOT NULL,
  priority TEXT NOT NULL,
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_applicability_terms

```sql
CREATE TABLE knowledge_applicability_terms (
  knowledge_id INTEGER NOT NULL,
  term_kind TEXT NOT NULL,
  term TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (knowledge_id, term_kind, term),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_evidence_refs

```sql
CREATE TABLE knowledge_evidence_refs (
  knowledge_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  verifier TEXT NOT NULL,
  verified_at_utc TEXT NOT NULL,
  verification_method TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, ref_type, ref_id),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_invalidation_rules

```sql
CREATE TABLE knowledge_invalidation_rules (
  rule_id TEXT PRIMARY KEY,
  knowledge_id INTEGER NOT NULL,
  invalidation_condition TEXT NOT NULL,
  affected_scope_json TEXT NOT NULL,
  revalidation_required INTEGER NOT NULL,
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_admission_records

```sql
CREATE TABLE knowledge_admission_records (
  knowledge_id INTEGER NOT NULL,
  admitted_at_utc TEXT NOT NULL,
  admitted_by_module TEXT NOT NULL,
  admission_run_id TEXT,
  rationale TEXT NOT NULL,
  evidence_ref TEXT NOT NULL,
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_revalidation_queue

```sql
CREATE TABLE knowledge_revalidation_queue (
  queue_id TEXT PRIMARY KEY,
  knowledge_id INTEGER NOT NULL,
  trigger_type TEXT NOT NULL,
  triggered_by_ref TEXT,
  queued_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  resolved_at_utc TEXT,
  resolution_rationale TEXT,
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_facts_fts

```sql
CREATE VIRTUAL TABLE knowledge_facts_fts USING fts5(
  knowledge_id UNINDEXED,
  semantic_summary,
  semantic_keys,
  subject_terms,
  predicate_terms,
  object_terms,
  applicability_terms,
  scope_terms,
  condition_terms,
  invalidation_terms
);
```

## Required Indexes

```sql
CREATE UNIQUE INDEX idx_knowledge_active_fact_identity
ON knowledge_facts(fact_identity_hash)
WHERE status IN ('candidate', 'admitted', 'deprecated', 'superseded');

CREATE INDEX idx_knowledge_status
ON knowledge_facts(status);

CREATE INDEX idx_knowledge_subject
ON knowledge_facts(subject_kind, subject_id);

CREATE INDEX idx_knowledge_predicate
ON knowledge_facts(predicate);

CREATE INDEX idx_knowledge_applicability_term
ON knowledge_applicability_terms(term_kind, term, knowledge_id);

CREATE INDEX idx_knowledge_revalidation_status
ON knowledge_revalidation_queue(status, knowledge_id);
```

## Query Model

### TaskKnowledgeContext

```yaml
TaskKnowledgeContext:
  task_context_id: string
  natural_language_query: string
  project_id: string | null
  repository: string | null
  module: string | null
  file_paths: list[string]
  hosts: list[string]
  devices: list[string]
  platforms: list[string]
  dependencies: list[string]
  operations: list[string]
  qualities: list[string]
  conditions: list[string]
  risk_classes: list[string]
  task_intents: list[string]
  lifecycle_phase: string | null
  known_evidence_refs: list[string]
```

The agent-facing caller must not pass only free text for non-trivial work. It must derive a structured task context first.

### KnowledgeQueryResult

```yaml
KnowledgeQueryResult:
  task_context_id: string
  admitted_facts: list[KnowledgeFact]
  candidate_facts: list[KnowledgeFact]
  rejected_facts:
    - knowledge_id: int
      reason: string
  mandatory_recall_matches:
    - knowledge_id: int
      matched_triggers: list[string]
  missing_knowledge_needs: list[MissingKnowledgeNeed]
  warnings:
    - code: string
      message: string
  degraded_recall: bool
```

## Retrieval Pipeline

```text
Task request
  -> derive TaskKnowledgeContext
  -> exact knowledge_id lookup if provided
  -> deterministic scope filtering
  -> applicability trigger lookup
  -> mandatory recall union
  -> semantic lexical recall
  -> CJK bigram/trigram recall
  -> optional embedding recall
  -> merge candidate knowledge_ids
  -> load canonical rows from SQLite
  -> status filter
  -> scope filter
  -> evidence/admission filter
  -> invalidation/revalidation filter
  -> missing-knowledge detector
  -> return KnowledgeQueryResult
```

Mandatory trigger recall has higher priority than semantic search.

Semantic search may add candidates. It may not prove that recall is complete.

If FTS or embedding recall is unavailable, the result must expose degraded recall through warnings.

## Applicability Trigger Matching

Applicability trigger matching must use deterministic indexes before semantic recall.

Example task context:

```yaml
operations:
  - storage_read
qualities:
  - throughput
  - latency
conditions:
  - high_load
risk_classes:
  - performance_regression
hosts:
  - server-A
```

Example fact applicability:

```yaml
affected_entities:
  - cpu
  - storage_controller
affected_operations:
  - storage_read
affected_qualities:
  - throughput
required_conditions:
  - high_load
risk_classes:
  - hardware_aging
  - performance_regression
must_consider_when:
  - high_load_storage_read_performance
  - unexplained_io_latency
  - cpu_storage_throughput_regression
```

This fact must be recalled even if the query text does not mention component aging.

## Missing-Knowledge Detection

The Knowledge Store must support explicit missing-knowledge detection.

If a task context implies a required dimension and no admitted fact satisfies it, the result must include `missing_knowledge_needs`.

Examples:

- target runtime version unknown
- deployment platform unknown
- customer written constraint referenced but not verified
- benchmark required but no test evidence exists
- hardware condition affects performance but host identity is unknown
- dependency version affects API behavior but dependency version is absent

Missing knowledge must not be replaced by assumptions.

The caller may route missing needs to:

- user clarification
- Test measurement
- artifact lookup
- repository inspection
- external document verification

## Admission Rules

Candidate facts may be proposed by agents.

Admission requires:

- semantic completeness
- typed evidence refs
- explicit scope
- applicability profile
- invalidation rules or explicit statement that none are currently known
- no causal inference embedded in the fact
- no reliance on developer claim alone

Semantically incomplete input must be rejected or returned for clarification.

Example rejected input:

```text
Current XXXX component is unstable.
```

Required missing fields:

- component identity
- instability metric
- affected host/device scope
- observed condition
- evidence ref
- validity window
- applicability triggers
- invalidation condition

## Fact Completeness Gate

Every admitted fact must answer:

```text
What exactly is true?
About what subject?
Under what scope?
Under what conditions?
Based on what evidence?
When must agents consider it?
When might it become invalid?
```

If any answer is missing, the fact is not admission-ready.

## Lifecycle

Allowed status transitions:

```text
candidate -> admitted
candidate -> rejected
candidate -> invalidated
admitted -> invalidated
admitted -> deprecated
admitted -> superseded
deprecated -> superseded
```

Rejected candidate rows may be kept in a candidate/review log, but rejected facts must not appear in normal admitted retrieval.

Supersession requires:

- old fact is admitted or deprecated
- replacement fact is admitted
- old fact remains historically available
- normal retrieval hides superseded fact
- supersession record is written transactionally

## Boundary Rules

### Developer Claim Boundary

Developer claims are not admitted Knowledge.

They may become evidence only after verification by Test, repository source inspection, customer written material, platform documentation, or Master-approved external evidence review.

### Project History Boundary

git commit history records are not Knowledge facts.

Project history may provide evidence refs for Knowledge admission.

### Causal Boundary

Knowledge does not become Causal by direct promotion.

If a Knowledge fact supports a causal conclusion, a Causal candidate must still be constructed with why, evidence, scope, assumptions, and invalidation conditions.

### User Preference Boundary

User preference is not a project fact unless supported by customer written requirement, project policy, platform constraint, legal/regulatory rule, or first-principles hard boundary.

## Retrieval Complexity

The store must avoid full traversal as a normal retrieval path.

Expected lookup paths:

- `knowledge_id` lookup: primary-key lookup.
- subject lookup: B-tree index.
- applicability trigger lookup: B-tree index over `(term_kind, term, knowledge_id)`.
- status filter: B-tree index.
- FTS recall: rebuildable FTS index.
- embedding recall: rebuildable side index or SQLite BLOB scan for small local stores.

Full scan is acceptable only in explicit maintenance jobs, migrations, validation scripts, or small test fixtures.

## CJK and Mixed-Language Recall

V1 must support deterministic CJK near-lexical recall.

Recommended tokenizer:

- ASCII word tokens for English and code identifiers.
- CJK bigrams and trigrams for Chinese/Japanese/Korean text.
- Same tokenizer for insertion, rebuild, and query.

Mixed-language queries must not degrade English query behavior.

## Example

### User/Artifact Source

```text
Maintenance report says storage-controller X123 on server-A shows aging.
High-load benchmark shows CPU-to-storage read throughput drops by 12%-28%.
```

### Candidate Knowledge Fact

```yaml
fact_kind: hardware
subject:
  kind: component
  id: server-A.storage-controller.X123
predicate: degrades
object:
  kind: structured
  value:
    metric: cpu_storage_read_throughput
    degradation_percent_range: [12, 28]
    condition: high_load
  unit: percent
qualifiers:
  conditions:
    - high_load
    - server-A uses storage-controller X123
  assumptions: []
  measurement_context:
    benchmark: storage-read-high-load
scope:
  host: server-A
  component: storage-controller.X123
evidence_refs:
  - ref_type: test
    ref_id: test/storage-read-high-load-20260622
  - ref_type: artifact
    ref_id: artifacts/maintenance-report-20260620
applicability_profile:
  affected_entities:
    - cpu
    - storage_controller
  affected_operations:
    - storage_read
  affected_qualities:
    - throughput
    - latency
  required_conditions:
    - high_load
  risk_classes:
    - performance_regression
    - hardware_aging
  must_consider_when:
    - high_load_storage_read_performance
    - unexplained_io_latency
    - cpu_storage_throughput_regression
invalidation_rules:
  - component_replaced
  - benchmark_no_longer_reproduces
  - firmware_updated_and_retested
```

## Agent Workflow

### Write Path

```text
source material
  -> agent normalizes into structured candidate
  -> completeness gate
  -> evidence verification
  -> applicability profile generation
  -> duplicate detection
  -> admission review
  -> admitted KnowledgeFact
```

### Read Path

```text
task request
  -> derive structured task context
  -> query Knowledge Store
  -> retrieve mandatory facts
  -> retrieve semantic supplemental facts
  -> detect missing required knowledge
  -> return fact package to caller
```

The caller must not silently ignore `missing_knowledge_needs`.

## Test Plan

### Unit Tests

- fact schema validation
- semantic incompleteness rejection
- developer claim rejection
- typed evidence ref round trip
- applicability trigger round trip
- CJK tokenizer consistency
- fact identity deduplication
- exact `knowledge_id` lookup
- subject lookup
- applicability term lookup
- FTS degraded-recall warning
- missing-knowledge detector
- invalidation and revalidation queue
- supersession lifecycle

### Integration Tests

- admitted fact retrieved by mandatory trigger even when semantic query misses it
- current task missing required platform fact produces `missing_knowledge_needs`
- user preference without evidence is rejected as hard constraint
- customer written requirement becomes admitted fact after evidence binding
- artifact ref supports Knowledge admission but does not auto-upgrade
- Knowledge fact supports Causal candidate construction but does not auto-write Causal
- CJK fact retrieved by CJK and mixed-language query
- invalidated fact excluded from normal retrieval
- superseded fact available only in historical mode
- query plan uses applicability indexes

### Production Verification Artifacts

Final verification should produce:

```text
artifacts/all_domain_results.json
artifacts/source_manifest.json
artifacts/source_tree_sha256.txt
artifacts/schema_results.json
artifacts/applicability_trigger_results.json
artifacts/missing_knowledge_results.json
artifacts/evidence_ref_roundtrip_results.json
artifacts/cjk_retrieval_results.json
artifacts/query_plan_results.json
artifacts/concurrency_results.json
artifacts/backup_restore_results.json
```

## Acceptance Criteria

Knowledge Store v1 is implementation-ready when:

- SQLite is the only canonical store.
- `KnowledgeFact` is the primary abstraction.
- raw user text is never canonical truth.
- developer claims are not admitted facts.
- every admitted fact has scope, evidence, applicability, and invalidation handling.
- mandatory applicability triggers work without semantic guesswork.
- missing required knowledge is returned explicitly.
- CJK and mixed-language deterministic recall work.
- FTS and embedding indexes are rebuildable recall layers.
- degraded recall is visible to callers.
- candidate/admitted separation is enforced.
- invalidated and superseded facts are excluded from normal retrieval.
- artifact refs remain evidence refs, not Knowledge truth.
- Knowledge refs do not directly mutate Causal truth.
- full traversal is not used for normal retrieval.
- tests prove trigger recall, missing-knowledge detection, typed refs, lifecycle, and retrieval complexity.

## Final Position

The Knowledge Store is not a document library.

It is an agent-native verified fact store with mandatory applicability triggers.

Its purpose is not to help humans browse facts. Its purpose is to make agents reliably retrieve verified project facts and constraints they would otherwise fail to associate with the current task.
