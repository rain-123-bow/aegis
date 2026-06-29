# Knowledge Store v1 Hardened Final Design

## Status

Final implementation-ready design contract.

This document supersedes the earlier Knowledge Store v1 baseline design for implementation planning. It keeps the same core direction, but hardens lifecycle, audit, applicability matching, missing-knowledge detection, admission authority, evidence binding, conflict detection, and schema constraints.

## Executive Decision

Aegis Knowledge Store v1 is an agent-native verified fact store.

It is not a Markdown knowledge base, not a human-facing wiki, and not a pure vector database. Its canonical store is SQLite. Full-text and embedding indexes may exist only as rebuildable recall layers.

The store exists to solve this problem:

```text
An agent must recall relevant verified facts even when normal semantic search would not naturally retrieve them.
```

Therefore, every admitted fact must include:

- what is true
- the subject it is true about
- where and when it is valid
- evidence proving it
- when agents must consider it
- how it can become invalid
- lifecycle and audit records

## Relationship to the Three Stores

### Project history

git commit history records what happened. It may provide evidence references for Knowledge admission. git commit history entries do not automatically become Knowledge facts.

### Knowledge

Knowledge stores verified static facts and constraints. It does not store causal conclusions, inferred judgments, strategy preferences, or developer claims as truth.

### Causal

Causal stores inferred causal structures with why, evidence, scope, assumptions, and invalidation conditions. A Knowledge fact may support a Causal candidate, but it must not mutate global Causal truth directly.

## Non-Goals

Knowledge Store v1 does not:

- optimize for direct human reading
- replace Project history
- replace Causal
- infer causal truth
- treat developer claims as facts
- rely on semantic search as complete recall
- traverse every fact during normal retrieval
- use LangGraph Store as project memory
- use a vector database as the canonical fact store

## First Principles

1. A fact is operationally useful only if it can be recalled when it matters.
2. Semantic similarity is helpful but incomplete.
3. Mandatory recall must be driven by deterministic applicability triggers.
4. Missing required facts must be explicit; they must not be replaced by assumptions.
5. Rejected, invalidated, superseded, or pending-revalidation facts must not appear in default active retrieval.
6. All lifecycle-changing operations must be auditable and transactional.
7. Knowledge is static fact state, not causal judgment.

## Core Abstractions

### KnowledgeFact

Canonical verified fact candidate or admitted fact.

```yaml
KnowledgeFact:
  knowledge_id: int
  knowledge_uuid: string
  status: candidate|admitted|rejected|invalidated|deprecated|superseded
  fact_kind: environment|dependency|platform|customer_constraint|repository_source|test_result|policy|interface|configuration|business_rule|other
  subject_kind: project|module|file|function|class|dependency|runtime|platform|customer|device|host|service|api|schema|other
  subject_id: string
  subject_attributes: object
  predicate: string
  object_kind: scalar|range|set|object|version|path|url|identifier|boolean|other
  object: object
  unit: string|null
  qualifiers: object
  fact_validity_scope: object
  validity_window: object|null
  semantic_summary: string
  semantic_keys: list[string]
  source_module: master|debate|execution|test|final_review|knowledge_review|store_import
  source_run_id: string|null
  source_artifact_ref: string|null
  fact_identity_hash: string
  strict_content_hash: string
  semantic_fingerprint: string|null
```

`semantic_summary` and `semantic_keys` are recall aids. They are not canonical truth.

### ApplicabilityProfile

Machine-readable conditions under which a fact must be considered.

```yaml
ApplicabilityProfile:
  profile_id: string
  knowledge_id: int
  applicability_scope: object
  affected_entities: list[string]
  affected_operations: list[string]
  affected_qualities: list[string]
  required_conditions: list[string]
  risk_classes: list[string]
  task_intents: list[string]
  lifecycle_phases: list[string]
  must_consider_when: list[string]
  exclude_when: list[string]
  priority: low|normal|high|critical
```

Applicability is not the same as fact validity.

- Fact validity scope: where the fact is true.
- Applicability recall scope: when the fact should be considered.

Example:

```text
Fact validity scope:
server-A.storage-controller.X123

Applicability recall scope:
tasks involving storage read performance, I/O latency, high-load benchmark interpretation, and capacity planning.
```

### EvidenceRef

Typed evidence supporting a candidate or admitted fact.

```yaml
EvidenceRef:
  knowledge_id: int
  ref_type: test|external|artifact|customer_written|platform_doc|repository_source
  ref_id: string
  verifier: master|debate|execution|test|final_review|knowledge_review
  verified_at_utc: string
  verification_method: string
```

Manual admission is not an evidence type. It is an admission method.

### MissingKnowledgeNeed

Deterministic declaration that required knowledge is absent.

```yaml
MissingKnowledgeNeed:
  need_id: string
  rule_id: string
  required_dimension: string
  subject_kind: string
  subject_id: string|null
  why_needed: string
  blocking_level: hard_block|needs_user_clarification|request_test_measurement|request_evidence_artifact_lookup|advisory
  acceptable_sources: list[string]
```

Every hard-block missing-knowledge need must cite a deterministic `rule_id`.

Model-suggested advisory needs are allowed only when `blocking_level = advisory`.

## Canonical Store

SQLite is the only canonical store in v1.

Reasons:

- integer primary-key lookup for `knowledge_id`
- B-tree indexes for deterministic structured recall
- WAL mode for local concurrent readers and serialized writers
- FTS5 for rebuildable lexical recall
- transactional lifecycle and audit writes
- simple backup and integrity checks for local git projects

Embeddings may be added later as rebuildable side indexes. They must not become canonical truth.

## SQLite Schema

### schema_migrations

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at_utc TEXT NOT NULL
);
```

Required migration behavior:

- fresh database initializes deterministically
- migration is idempotent
- future schema version is rejected clearly
- migration failure rolls back

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
  fact_validity_scope_json TEXT NOT NULL,
  validity_window_json TEXT,
  semantic_summary TEXT NOT NULL,
  source_module TEXT NOT NULL,
  source_run_id TEXT,
  source_artifact_ref TEXT,
  fact_identity_hash TEXT NOT NULL,
  strict_content_hash TEXT NOT NULL,
  semantic_fingerprint TEXT,
  CHECK (status IN (
    'candidate',
    'admitted',
    'rejected',
    'invalidated',
    'deprecated',
    'superseded'
  )),
  CHECK (fact_kind IN (
    'environment',
    'dependency',
    'platform',
    'customer_constraint',
    'repository_source',
    'test_result',
    'policy',
    'interface',
    'configuration',
    'business_rule',
    'other'
  )),
  CHECK (subject_kind IN (
    'project',
    'module',
    'file',
    'function',
    'class',
    'dependency',
    'runtime',
    'platform',
    'customer',
    'device',
    'host',
    'service',
    'api',
    'schema',
    'other'
  )),
  CHECK (object_kind IN (
    'scalar',
    'range',
    'set',
    'object',
    'version',
    'path',
    'url',
    'identifier',
    'boolean',
    'other'
  )),
  CHECK (source_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review',
    'store_import'
  ))
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
  applicability_scope_json TEXT NOT NULL,
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
  CHECK (priority IN ('low', 'normal', 'high', 'critical')),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_applicability_terms

Flattened terms for indexed applicability lookup.

```sql
CREATE TABLE knowledge_applicability_terms (
  knowledge_id INTEGER NOT NULL,
  term_kind TEXT NOT NULL,
  term TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (knowledge_id, term_kind, term),
  CHECK (term_kind IN (
    'scope',
    'entity',
    'operation',
    'quality',
    'condition',
    'risk_class',
    'task_intent',
    'lifecycle_phase',
    'must_consider',
    'exclude'
  )),
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
  CHECK (ref_type IN (
        'test',
    'external',
    'artifact',
    'customer_written',
    'platform_doc',
    'repository_source'
  )),
  CHECK (verifier IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
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
  admission_method TEXT NOT NULL,
  rationale TEXT NOT NULL,
  CHECK (admitted_by_module IN (
    'master',
    'knowledge_review',
    'store_import'
  )),
  CHECK (admission_method IN (
    'master_manual_review',
    'knowledge_review',
    'test_verified',
    'repository_inspected',
    'external_authority_verified'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (knowledge_id, ref_type, ref_id)
    REFERENCES knowledge_evidence_refs(knowledge_id, ref_type, ref_id)
);
```

### knowledge_admission_evidence_refs

Admission may require multiple evidence refs.

```sql
CREATE TABLE knowledge_admission_evidence_refs (
  knowledge_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, ref_type, ref_id),
  CHECK (ref_type IN (
        'test',
    'external',
    'artifact',
    'customer_written',
    'platform_doc',
    'repository_source'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_rejection_records

```sql
CREATE TABLE knowledge_rejection_records (
  knowledge_id INTEGER NOT NULL,
  rejected_at_utc TEXT NOT NULL,
  rejected_by_module TEXT NOT NULL,
  rejection_run_id TEXT,
  reason TEXT NOT NULL,
  missing_fields_json TEXT NOT NULL,
  evidence_review_json TEXT NOT NULL,
  CHECK (rejected_by_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
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
  CHECK (revalidation_required IN (0, 1)),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_invalidation_records

```sql
CREATE TABLE knowledge_invalidation_records (
  knowledge_id INTEGER NOT NULL,
  invalidated_at_utc TEXT NOT NULL,
  invalidated_by_module TEXT NOT NULL,
  invalidation_run_id TEXT,
  reason TEXT NOT NULL,
  triggered_rule_id TEXT,
  evidence_ref_type TEXT,
  evidence_ref_id TEXT,
  CHECK (
    evidence_ref_type IS NULL OR evidence_ref_type IN (
            'test',
      'external',
      'artifact',
      'customer_written',
      'platform_doc',
      'repository_source'
    )
  ),
  CHECK (
    (evidence_ref_type IS NULL AND evidence_ref_id IS NULL)
    OR
    (evidence_ref_type IS NOT NULL AND evidence_ref_id IS NOT NULL)
  ),
  CHECK (invalidated_by_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (triggered_rule_id) REFERENCES knowledge_invalidation_rules(rule_id)
);
```

### knowledge_supersession_records

```sql
CREATE TABLE knowledge_supersession_records (
  old_knowledge_id INTEGER NOT NULL,
  new_knowledge_id INTEGER NOT NULL,
  superseded_at_utc TEXT NOT NULL,
  superseded_by_module TEXT NOT NULL,
  supersession_run_id TEXT,
  reason TEXT NOT NULL,
  CHECK (old_knowledge_id != new_knowledge_id),
  CHECK (superseded_by_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
  FOREIGN KEY (old_knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (new_knowledge_id) REFERENCES knowledge_facts(knowledge_id)
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
  CHECK (status IN (
    'pending',
    'in_progress',
    'resolved',
    'cancelled',
    'failed'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_need_rules

Deterministic source for missing-knowledge detection.

```sql
CREATE TABLE knowledge_need_rules (
  rule_id TEXT PRIMARY KEY,
  required_dimension TEXT NOT NULL,
  trigger_terms_json TEXT NOT NULL,
  trigger_task_intents_json TEXT NOT NULL,
  trigger_operations_json TEXT NOT NULL,
  trigger_qualities_json TEXT NOT NULL,
  required_subject_kinds_json TEXT NOT NULL,
  acceptable_sources_json TEXT NOT NULL,
  default_blocking_level TEXT NOT NULL,
  rationale TEXT NOT NULL,
  CHECK (default_blocking_level IN (
    'hard_block',
    'needs_user_clarification',
    'request_test_measurement',
    'request_evidence_artifact_lookup'
  ))
);
```

### knowledge_conflict_records

V1 must detect exact subject/predicate conflicts. It does not need full truth maintenance.

```sql
CREATE TABLE knowledge_conflict_records (
  conflict_id TEXT PRIMARY KEY,
  left_knowledge_id INTEGER NOT NULL,
  right_knowledge_id INTEGER NOT NULL,
  detected_at_utc TEXT NOT NULL,
  conflict_reason TEXT NOT NULL,
  status TEXT NOT NULL,
  CHECK (status IN ('open', 'resolved', 'accepted_with_scope_split', 'dismissed')),
  FOREIGN KEY (left_knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (right_knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
```

### knowledge_facts_fts

FTS is a rebuildable recall layer, not canonical truth.

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
CREATE UNIQUE INDEX idx_knowledge_fact_identity_active
ON knowledge_facts(fact_identity_hash)
WHERE status IN ('candidate', 'admitted');

CREATE INDEX idx_knowledge_status
ON knowledge_facts(status);

CREATE INDEX idx_knowledge_subject
ON knowledge_facts(subject_kind, subject_id);

CREATE INDEX idx_knowledge_predicate
ON knowledge_facts(predicate);

CREATE INDEX idx_knowledge_applicability_term
ON knowledge_applicability_terms(term_kind, term, knowledge_id);

CREATE INDEX idx_knowledge_evidence_ref
ON knowledge_evidence_refs(ref_type, ref_id);

CREATE INDEX idx_knowledge_revalidation_status
ON knowledge_revalidation_queue(status, knowledge_id);
```

## Canonical Hash Rules

Do not derive fact identity from prose.

`strict_content_hash`:

```text
sha256(canonical_json({
  subject_kind,
  subject_id,
  subject_attributes,
  predicate,
  object_kind,
  object,
  unit
}))
```

`fact_identity_hash`:

```text
sha256(canonical_json({
  subject_kind,
  subject_id,
  subject_attributes,
  predicate,
  object_kind,
  object,
  unit,
  qualifiers,
  fact_validity_scope
}))
```

Do not include these in identity hash:

- timestamps
- source run ID
- source artifact ref
- semantic summary
- semantic keys
- admission rationale

Canonical JSON requirements:

- UTF-8
- sorted object keys
- no insignificant whitespace
- stable numeric representation
- normalized Unicode form

## Lifecycle

Allowed lifecycle transitions:

```text
candidate -> admitted
candidate -> rejected
candidate -> invalidated
admitted -> invalidated
admitted -> deprecated
admitted -> superseded
deprecated -> superseded
```

Required audit records:

```text
candidate -> admitted requires admission record
candidate -> rejected requires rejection record
admitted -> invalidated requires invalidation record
admitted -> superseded requires supersession record
deprecated -> superseded requires supersession record
```

Failed lifecycle operations must not partially mutate status or audit rows.

Supersession API rules:

```text
old fact status must be admitted or deprecated
new fact status must be admitted
new fact must not be candidate, rejected, invalidated, deprecated, or superseded
old_knowledge_id must not equal new_knowledge_id
```

Default active retrieval must exclude:

- candidate
- rejected
- invalidated
- deprecated
- superseded
- admitted facts with pending or in-progress revalidation

Historical mode may include non-active facts with explicit reasons.

## Admission Rules

Admission requires:

- semantic completeness
- typed evidence refs
- explicit fact validity scope
- applicability profile
- invalidation rules or explicit no-known-invalidation statement
- no causal inference embedded in the fact
- no reliance on developer claim alone
- no manual admission as sole evidence for technical or environmental facts

Manual admission is allowed only as an admission method, not as evidence.

`master_manual_review` may admit project governance policy only when scope, rationale, and authority boundary are explicit.

Only `master`, `knowledge_review`, and `store_import` may admit Knowledge facts.

Debate, Execution, Test, and Final Review may generate candidate facts, evidence refs, review material, or handoff artifacts. They must not directly admit global Knowledge truth. If their output is useful, it must enter Knowledge admission through Master, Knowledge Review, or an explicit store import path.

`test_verified` is an admission method, not admission authority. Test may verify evidence. Test must not directly admit Knowledge facts.

Developer claims may create candidates. They must not directly become admitted facts.

artifact refs may support admission. They do not auto-upgrade into Knowledge truth.

## Fact Completeness Gate

Every admitted fact must answer:

```text
What exactly is true?
About what subject?
Where is it true?
During what validity window, if time-bound?
Under what conditions?
Based on what evidence?
When must agents consider it?
When might it become invalid?
```

If any answer is missing, the fact is not admission-ready.

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

## Applicability Trigger Boolean Semantics

Applicability matching is deterministic.

Evaluation order:

```text
1. Status filter always applies.
2. Pending or in-progress revalidation excludes the fact from default active retrieval.
3. exclude_when has highest applicability priority.
4. Fact validity scope must match before active mandatory recall.
5. required_conditions use ALL semantics.
6. affected_operations, affected_qualities, risk_classes, task_intents, and lifecycle_phases are trigger dimensions.
7. A strong match in any trigger dimension may nominate a fact.
8. must_consider_when match promotes a fact to mandatory recall only after status, scope, evidence, invalidation, and revalidation filters.
9. Scope mismatch may be returned only as rejected_facts with reason = scope_mismatch when diagnostic reporting is enabled.
10. exclude_when match may be returned only as rejected_facts with reason = excluded_by_applicability_profile when diagnostic reporting is enabled.
```

`required_conditions` are strict:

```text
If a fact requires [high_load, server_A], the task context must contain both.
```

`exclude_when` overrides `must_consider_when`.

`must_consider_when` bypasses semantic ranking, but it does not bypass lifecycle, evidence, invalidation, revalidation, or scope filters.

## Query Model

### TaskKnowledgeContext

```yaml
TaskKnowledgeContext:
  project_id: string
  task_intents: list[string]
  lifecycle_phase: string
  affected_entities: list[string]
  operations: list[string]
  qualities: list[string]
  conditions: list[string]
  risk_classes: list[string]
  subject_refs: list[object]
  query_terms: list[string]
  required_dimensions: list[string]
```

### KnowledgeQueryResult

```yaml
KnowledgeQueryResult:
  mandatory_facts: list[KnowledgeFact]
  supplemental_facts: list[KnowledgeFact]
  rejected_facts: list[object]
  missing_knowledge_needs: list[MissingKnowledgeNeed]
  degraded_recall_warnings: list[string]
  query_plan: object
```

## Retrieval Pipeline

Default retrieval pipeline:

```text
TaskKnowledgeContext
  -> validate context
  -> status/lifecycle filter
  -> revalidation filter
  -> applicability trigger lookup
  -> exact subject/predicate lookup
  -> FTS lexical recall
  -> optional embedding recall
  -> evidence/admission filter
  -> invalidation filter
  -> deterministic missing-knowledge detector
  -> rank and return with query plan evidence
```

Mandatory trigger recall has higher priority than semantic search.

Semantic search may add candidates. It may not prove that recall is complete.

If FTS or embedding recall is unavailable, the result must expose degraded recall through warnings.

Normal retrieval must not use full traversal.

## Missing-Knowledge Detection

Missing-knowledge detection uses `knowledge_need_rules`.

Examples:

```text
task_intent = deploy
=> required_dimension = target_runtime_version

operation = benchmark and quality = latency
=> required_dimension = benchmark_environment

dependency mentioned
=> required_dimension = dependency_version

customer_constraint referenced
=> required_dimension = customer_written_requirement_evidence
```

Hard-block missing knowledge must cite `rule_id`.

Model-suggested advisory needs may exist only as advisory. They cannot block by themselves.

The caller must not silently ignore hard-block `missing_knowledge_needs`.

## CJK and Mixed-Language Recall

V1 must support deterministic CJK and mixed-language recall for applicability terms.

Minimum requirements:

- store normalized CJK terms in `knowledge_applicability_terms`
- support exact CJK term match
- support mixed English/Chinese semantic keys
- include CJK facts in FTS rebuild tests
- do not rely on whitespace tokenization alone for CJK mandatory trigger recall

## Conflict Detection

V1 must detect exact active conflicts over the same subject, predicate, and overlapping validity scope.

The v1 overlap rule is intentionally conservative. A conflict candidate exists only when:

```text
same subject_kind
same subject_id
same predicate
different canonical object_json
both facts are active
and one of:
  - fact_validity_scope_json is canonical-equal
  - an explicit deterministic scope-overlap function returns true
```

The minimum v1 implementation must support canonical-equal validity-scope conflict detection.

Do not attempt broad range or logical overlap unless a deterministic scope-overlap function exists.

Example conflict:

```text
project runtime Python version is 3.11
project runtime Python version is 3.12
```

Conflict detection creates `knowledge_conflict_records`.

It does not automatically resolve truth. Master or Knowledge Review must adjudicate.

## Backup and Restore

Local project stores must support backup and restore smoke tests.

Required checks:

- SQLite backup creates a consistent snapshot
- restored snapshot supports `get`, `search`, and `query`
- restored snapshot passes `PRAGMA integrity_check`
- restored snapshot passes `PRAGMA foreign_key_check`

## Example: Non-Obvious Hardware Constraint

Source statement:

```text
On server-A, component X123 aging causes CPU storage-read throughput to drop by 12% to 18% under high-load conditions.
```

Candidate fact:

```yaml
fact_kind: environment
subject_kind: device
subject_id: server-A.storage-controller.X123
predicate: degrades
object_kind: range
object:
  metric: cpu_storage_read_throughput
  lower_percent: 12
  upper_percent: 18
unit: percent
fact_validity_scope:
  host: server-A
  component: X123
  operation: storage_read
  condition: high_load
semantic_summary: >
  Server-A storage controller X123 aging reduces CPU storage-read throughput by 12% to 18% under high load.
semantic_keys:
  - server-A
  - X123 aging
  - storage read throughput
  - high load IO latency
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
    - server-A
  risk_classes:
    - hardware_aging
    - performance_regression
  task_intents:
    - benchmark
    - performance_diagnosis
    - capacity_planning
  must_consider_when:
    - high_load_storage_read_performance
    - unexplained_io_latency
    - cpu_storage_throughput_regression
  exclude_when:
    - host_not_server-A
evidence_refs:
  - ref_type: test
    ref_id: test-run-2026-06-22-server-A-storage-benchmark
invalidation_rules:
  - component X123 is replaced
  - firmware update changes controller behavior
  - benchmark evidence is superseded by later test
```

Retrieval behavior:

```text
Task: diagnose high-load storage-read throughput regression on server-A.
Result: mandatory recall.

Task: diagnose low-load UI render latency on server-B.
Result: excluded by applicability profile.
```

## Agent Write Path

```text
raw observation or proposal
  -> semantic completeness check
  -> causal inference boundary check
  -> developer-claim boundary check
  -> evidence binding
  -> fact validity scope construction
  -> applicability profile construction
  -> invalidation rule construction
  -> canonical hash computation
  -> conflict detection
  -> admission review
  -> candidate/admitted/rejected lifecycle write
```

If the input is incomplete, write a rejected candidate with a rejection record or return a clarification request. Do not admit an incomplete fact.

## Agent Read Path

```text
task context
  -> structured TaskKnowledgeContext
  -> mandatory applicability lookup
  -> supplemental semantic recall
  -> missing-knowledge detection
  -> degraded recall warning check
  -> return KnowledgeQueryResult
```

Callers must treat hard-block missing knowledge as a blocking condition.

## Required Tests

### Unit Tests

- schema migration baseline
- enum CHECK constraints
- invalid `subject_kind` rejection
- invalid `object_kind` rejection
- fact schema validation
- semantic incompleteness rejection
- developer claim rejection
- manual admission boundary
- typed evidence ref round trip
- multiple admission evidence refs
- admission evidence refs must exist in `knowledge_evidence_refs`
- admission authority boundary
- canonical fact identity hash
- exact `knowledge_id` lookup
- subject lookup
- applicability term lookup
- applicability boolean semantics
- `exclude_when` overriding `must_consider_when`
- `required_conditions` ALL semantics
- missing-knowledge rule registry
- CJK applicability trigger lookup
- conflict detection
- revalidation queue status semantics

### Lifecycle Tests

- `candidate -> admitted` writes admission record
- `candidate -> rejected` writes rejection record
- `admitted -> invalidated` writes invalidation record
- `admitted -> superseded` writes supersession record
- self-supersession is rejected
- candidate cannot replace admitted fact
- admitted fact cannot be superseded by candidate fact
- failed lifecycle operation rolls back status and audit rows
- default retrieval excludes rejected facts
- default retrieval excludes invalidated facts
- default retrieval excludes superseded facts
- default retrieval excludes pending-revalidation facts
- historical mode returns non-active facts with reasons

### Integration Tests

- admitted fact retrieved by mandatory trigger even when semantic query misses it
- current task missing required platform fact produces `missing_knowledge_needs` with `rule_id`
- Debate, Execution, Test, and Final Review cannot directly admit Knowledge truth
- user preference without evidence is rejected as hard constraint
- customer written requirement becomes admitted fact only after evidence binding
- artifact ref supports Knowledge admission but does not auto-upgrade
- Knowledge fact supports Causal candidate construction but does not auto-write Causal
- CJK fact retrieved by CJK and mixed-language context
- query plan proves index usage
- same subject/predicate/scope with different object creates conflict record
- same subject/predicate/scope with same object does not create conflict
- invalidated, rejected, and superseded facts do not create active conflicts
- backup and restore smoke test passes

### Production Evidence Package

Verification should produce:

```text
module_test_reports/knowledge_store/
  KNOWLEDGE_STORE_V1_FINAL_TEST_PLAN.md
  KNOWLEDGE_STORE_V1_FINAL_TEST_REPORT.md
  artifacts/
    source_manifest.json
    source_tree_sha256.txt
    schema_results.json
    migration_results.json
    lifecycle_results.json
    rollback_results.json
    applicability_semantics_results.json
    missing_need_rule_results.json
    evidence_ref_results.json
    admission_authority_results.json
    admission_evidence_fk_results.json
    cjk_retrieval_results.json
    query_plan_results.json
    conflict_detection_results.json
    backup_restore_results.json
    concurrency_results.json
```

`module_test_reports/` remains local evidence unless explicitly force-added.

## Acceptance Criteria

Knowledge Store v1 is implementation-ready only when:

1. SQLite is the only canonical store.
2. `KnowledgeFact` remains the canonical object.
3. Candidate/admitted/rejected/invalidated/deprecated/superseded lifecycle is schema-enforced.
4. Admission, rejection, invalidation, and supersession are auditable.
5. Lifecycle writes are transactional.
6. Only Master, Knowledge Review, and store import can admit Knowledge facts.
7. Debate, Execution, Test, and Final Review can propose or verify, but cannot directly admit Knowledge truth.
8. Every admitted fact has typed evidence refs.
9. Admission evidence refs are backed by existing evidence refs.
10. Admission may use multiple evidence refs.
11. Developer claims cannot become admitted Knowledge without verification.
12. Manual admission is not ordinary evidence.
13. Manual admission cannot be sole evidence for technical or environmental facts.
14. `subject_kind` and `object_kind` are schema-constrained.
15. Fact identity hash is canonical and structured.
16. Supersession forbids self-replacement and enforces old/new status rules.
17. Applicability trigger matching has deterministic boolean semantics.
18. `exclude_when` overrides `must_consider_when`.
19. `required_conditions` use ALL semantics.
20. Missing-knowledge detection uses deterministic need rules.
21. Hard-block missing-knowledge needs cite `rule_id`.
22. CJK and mixed-language deterministic recall work.
23. FTS and embedding recall failures are visible to callers.
24. Invalidated, rejected, superseded, and pending-revalidation facts are excluded from default retrieval.
25. Historical/review modes can retrieve non-active facts with reasons.
26. Query plan evidence proves indexed primary lookup, subject lookup, and applicability term lookup.
27. Normal retrieval does not depend on full scans.
28. Schema migration baseline exists.
29. Backup/restore smoke test exists.
30. Conflict detection creates records but does not auto-resolve truth.
31. Knowledge facts do not directly mutate Causal truth.

## Final Position

The Knowledge Store v1 design is not a human-reading document system.

It is a structured, auditable, agent-native verified fact store with mandatory applicability recall.

Its central rule is:

```text
Verified facts must be stored together with the deterministic conditions under which agents must recall them.
```
