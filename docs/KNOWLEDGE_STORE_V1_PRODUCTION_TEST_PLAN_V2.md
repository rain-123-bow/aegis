# Knowledge Store v1 Production Test Plan v2

## Status

Revised production-readiness test plan.

This version supersedes `KNOWLEDGE_STORE_V1_PRODUCTION_TEST_PLAN.md` as the preferred execution plan for Knowledge Store v1 verification.

The revision incorporates the external test-plan review while preserving three boundary corrections:

1. Pydantic/model validation failures are allowed at the model boundary. They are not public store API failures.
2. Invalid enum values such as invalid fact kind, subject kind, object kind, and evidence ref type are model/schema validation cases, not required `KnowledgeStoreError` domain codes unless they reach a public store method.
3. Archive / Knowledge / Causal boundary tests verify that Knowledge Store does not perform implicit cross-store mutation. Full three-store orchestration belongs to the three-store linkage layer, not to Knowledge Store itself.

This document is a test plan only. It does not claim that tests have passed.

## Goal

Verify that Knowledge Store v1 is production-ready for personal local Aegis use as a SQLite-backed project Knowledge Store.

The test result must prove the two defining responsibilities:

1. Recall facts that must be considered.
2. Report missing required knowledge instead of silently assuming.

The test result must also prove source snapshot traceability, schema integrity, migration behavior, indexed query paths, lifecycle auditability, boundary safety, and concurrency sanity.

## Scope

In scope:

- `src/aegis/stores/knowledge/`
- `tests/test_knowledge_store*.py`
- Knowledge Store model validation, SQLite persistence, retrieval, audit, lifecycle, backup, and evidence generation

Out of scope:

- Archive Store implementation internals
- Causal Store implementation internals
- LangGraph parent graph behavior
- Real LLM/nested-Codex agent behavior
- Cloud-scale or multi-user deployment benchmarks
- Vector database or embedding-based retrieval

## Core Boundaries

### Boundary 1: Model Validation vs Store API Errors

Model construction can fail with Pydantic `ValidationError` for malformed inputs such as:

- invalid `fact_kind`;
- invalid `subject_kind`;
- invalid `object_kind`;
- invalid evidence ref type;
- empty required model fields;
- invalid Literal values.

Public `KnowledgeStore` methods must not leak raw `sqlite3.*` exceptions for expected negative paths.

Expected boundary:

```text
malformed model input -> Pydantic validation failure
public store operation failure -> KnowledgeStoreError with domain code
unexpected infrastructure failure -> controlled failure record in report
```

### Boundary 2: Knowledge Store Does Not Own Cross-Store Promotion

Knowledge Store may store verified static facts and typed evidence references.

It must not:

- auto-create Knowledge from Archive;
- auto-write Causal claims;
- turn developer claims into admitted Knowledge;
- turn user preferences into project facts without accepted evidence.

Full cross-store admission workflow is tested in three-store linkage tests. This plan only verifies that Knowledge Store itself does not perform implicit cross-store mutation.

### Boundary 3: Indexed Recall Is Required, Semantic Omniscience Is Not

Knowledge Store v1 must enforce structured applicability, scope, missing-need rules, and deterministic lexical/CJK recall.

It is not required to infer every unstated relation without a rule, applicability profile, semantic key, or indexed token.

## Test Environment

Repository:

```text
C:\Users\playm\Documents\self-git\aegis
```

Python:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe
```

Evidence root:

```text
module_test_reports/knowledge_store_v1_production_verification_<YYYYMMDD_HHMMSS>/
```

Required evidence layout:

```text
module_test_reports/knowledge_store_v1_production_verification_<YYYYMMDD_HHMMSS>/
  reports/
    KNOWLEDGE_STORE_V1_PRODUCTION_VERIFICATION_REPORT.md
  artifacts/
  db_snapshots/
  logs/
```

`module_test_reports/` must remain git-ignored.

## Required Commands

Run from repository root:

```powershell
cd C:\Users\playm\Documents\self-git\aegis
```

Focused Knowledge Store tests:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest tests\test_knowledge_store.py tests\test_knowledge_store_hardening.py tests\test_knowledge_store_source_hardening.py -vv
```

Full repository tests:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest -vv
```

Static checks:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m ruff check .
git diff --check
git status --short
```

## Evidence Package

The final evidence package must include at least:

```text
artifacts/source_manifest.json
artifacts/source_tree_sha256.txt
artifacts/source_patch.diff
artifacts/source_patch_sha256.txt
artifacts/schema_results.json
artifacts/migration_results.json
artifacts/sqlite_query_plans.txt
artifacts/mandatory_recall_results.json
artifacts/fact_validity_scope_results.json
artifacts/missing_need_satisfaction_results.json
artifacts/cjk_ngram_retrieval_results.json
artifacts/invalidation_rule_ownership_results.json
artifacts/historical_review_mode_results.json
artifacts/no_known_invalidation_results.json
artifacts/query_plan_truthfulness_results.json
artifacts/canonical_json_results.json
artifacts/audit_reason_validation_results.json
artifacts/revalidation_queue_api_results.json
artifacts/lifecycle_transactionality_results.json
artifacts/domain_error_contract_results.json
artifacts/fact_completeness_gate_results.json
artifacts/store_boundary_results.json
artifacts/concurrency_results.json
artifacts/backup_restore_results.json
artifacts/scale_complexity_results.json
logs/pytest_knowledge_store.log
logs/pytest_full.log
logs/ruff.log
logs/git_diff_check.log
```

Each JSON artifact must include:

```json
{
  "test_group": "...",
  "status": "passed|failed|blocked",
  "case_count": 0,
  "failed_cases": [],
  "domain_error_codes": [],
  "model_validation_errors": [],
  "raw_exception_types": [],
  "knowledge_ids": [],
  "rule_ids": [],
  "profile_ids": [],
  "notes": []
}
```

## Source Snapshot Evidence

Objective: Prove which source snapshot was tested.

Required artifacts:

```text
artifacts/source_manifest.json
artifacts/source_tree_sha256.txt
artifacts/source_patch.diff
artifacts/source_patch_sha256.txt
```

`source_manifest.json` must include:

```json
{
  "git_branch": "...",
  "git_commit": "...",
  "working_tree_clean": false,
  "tracked_modified_files": [],
  "untracked_relevant_files": [],
  "tested_source_identified_by_commit_only": false,
  "source_tree_sha256": "...",
  "source_patch_sha256": "..."
}
```

Acceptance:

```text
PASSED is allowed only if:
1. working tree is clean and commit identifies tested source; or
2. working tree is dirty but source tree hash and patch hash are recorded.
```

## Schema, Migration, and SQLite Query Plan Evidence

Objective: Prove schema shape, migration behavior, and indexed query paths.

Required artifacts:

```text
artifacts/schema_results.json
artifacts/migration_results.json
artifacts/sqlite_query_plans.txt
```

`schema_results.json` must include:

- table existence;
- index existence;
- CHECK constraints existence where SQLite exposes them;
- foreign key definitions;
- partial unique index for active fact identity;
- FTS table existence;
- `schema_migrations` content;
- `PRAGMA integrity_check`;
- `PRAGMA foreign_key_check`.

`migration_results.json` must include:

- fresh database initialization;
- idempotent initialization on an existing database;
- future schema version rejection;
- no partial schema state after failed migration if tested;
- final `schema_migrations` rows.

`sqlite_query_plans.txt` must include `EXPLAIN QUERY PLAN` for:

- `knowledge_id` primary-key lookup;
- subject lookup;
- predicate lookup;
- applicability term lookup;
- semantic token lookup;
- evidence ref lookup;
- revalidation queue lookup;
- missing-knowledge rule lookup;
- FTS lookup;
- conflict detection lookup.

Acceptance:

```text
Normal retrieval must not depend on broad full-table scans.
Maintenance-only full traversal is allowed only when explicitly labeled.
```

## Test Matrix

### 1. Mandatory Applicability Recall

Objective: Verify every documented trigger dimension can nominate a fact and that validation gates still apply.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| MR-001 | `task_intents`-only profile matches query task intent | fact appears in `mandatory_facts` |
| MR-002 | `risk_classes`-only profile matches query risk class | fact appears in `mandatory_facts` |
| MR-003 | `affected_entities`-only profile matches query entity | fact appears if scope is valid |
| MR-004 | `affected_operations`-only profile matches operation | fact appears if scope is valid |
| MR-005 | `affected_qualities`-only profile matches quality | fact appears under v1 trigger policy |
| MR-006 | `lifecycle_phases`-only profile matches lifecycle phase | fact appears |
| MR-007 | `must_consider_when` matches context | fact appears |
| MR-008 | required condition missing | fact not active |
| MR-009 | `exclude_when` matches context | fact rejected with `excluded_by_applicability_profile` |
| MR-010 | matching trigger but pending revalidation | fact hidden in active mode |

Artifact:

```text
artifacts/mandatory_recall_results.json
```

### 2. Fact Validity Scope

Objective: Verify `fact_validity_scope` is a hard active-retrieval gate.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| VS-001 | server-A fact queried for server-B | not active |
| VS-002 | project-A fact queried for project-B | not active |
| VS-003 | dependency fact queried for different dependency | not active |
| VS-004 | runtime fact queried for different runtime | not active |
| VS-005 | platform fact queried for different platform | not active |
| VS-006 | explicitly global fact queried in matching context | active if other gates pass |
| VS-007 | project-wide fact queried in same project | active if other gates pass |
| VS-008 | nominated fact has scope mismatch | `rejected_facts` reports scope mismatch |

Artifact:

```text
artifacts/fact_validity_scope_results.json
```

### 3. Missing-Knowledge Satisfaction

Objective: Verify hard-block missing needs are cleared only by relevant admitted scoped facts.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| MK-001 | project-B deploy while only project-A runtime fact exists | missing need remains |
| MK-002 | right subject kind but wrong subject ID exists | missing need remains |
| MK-003 | right subject kind but wrong dimension exists | missing need remains |
| MK-004 | right fact exists but pending revalidation | missing need remains |
| MK-005 | rejected fact exists | missing need remains |
| MK-006 | invalidated fact exists | missing need remains |
| MK-007 | superseded fact exists without active replacement | missing need remains |
| MK-008 | matching admitted scoped fact exists | missing need clears |
| MK-009 | advisory/model-suggested need | separated from rule-grounded hard block or explicitly unsupported |

Artifact:

```text
artifacts/missing_need_satisfaction_results.json
```

### 4. CJK and Mixed-Language Retrieval

Objective: Verify deterministic CJK near-lexical recall.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| CJK-001 | full Chinese phrase query | fact recalled |
| CJK-002 | partial Chinese phrase query | fact recalled |
| CJK-003 | Chinese bigram query | fact recalled |
| CJK-004 | Chinese trigram query | fact recalled |
| CJK-005 | mixed Chinese-English query | fact recalled |
| CJK-006 | FTS unavailable, token fallback used | fact recalled with degradation warning |
| CJK-007 | rebuild indexes | CJK recall preserved |
| CJK-008 | English token retrieval after CJK changes | English recall preserved |

Artifact:

```text
artifacts/cjk_ngram_retrieval_results.json
```

### 5. Invalidation Rule Ownership

Objective: Verify invalidation cannot use another fact's rule.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| IO-001 | invalidate fact A using fact A rule | succeeds |
| IO-002 | invalidate fact A using fact B rule | `INVALIDATION_RULE_NOT_OWNED_BY_FACT` |
| IO-003 | invalidate fact A using missing rule | controlled store error |
| IO-004 | failed invalidation | status unchanged |
| IO-005 | failed invalidation | no audit row written |

Artifact:

```text
artifacts/invalidation_rule_ownership_results.json
```

### 6. Historical and Review Retrieval Modes

Objective: Verify active mode hides non-active facts and review modes expose them only for inspection.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| HR-001 | active mode with rejected fact | hidden |
| HR-002 | review mode with rejected fact | visible or diagnosable as rejected |
| HR-003 | historical mode with invalidated fact | visible or diagnosable as invalidated |
| HR-004 | historical mode with superseded fact | visible or diagnosable as superseded |
| HR-005 | active mode with pending revalidation | hidden |
| HR-006 | review mode with pending revalidation | visible or diagnosable |

Artifact:

```text
artifacts/historical_review_mode_results.json
```

### 7. `no_known_invalidation`

Objective: Verify no-known-invalidation declarations are persisted and auditable.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| NI-001 | no invalidation rules and `no_known_invalidation=true` | candidate accepted |
| NI-002 | read back persisted fact | declaration is true |
| NI-003 | no rules and no declaration | model validation failure |
| NI-004 | backup/restore | declaration preserved |

Artifact:

```text
artifacts/no_known_invalidation_results.json
```

### 8. Query Plan Truthfulness

Objective: Verify `query_plan` reports actual execution paths.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| QP-001 | FTS available and used | `fts_used=true`, `fts_failed=false` |
| QP-002 | FTS unavailable | `fts_failed=true`, `degraded_recall=true` |
| QP-003 | token fallback used | `fallback_token_lookup_used=true` |
| QP-004 | normal retrieval path | `full_scan_used=false` |
| QP-005 | historical mode query | `historical_mode=true` |
| QP-006 | missing rules checked | `missing_need_rules_checked=true` |

Artifact:

```text
artifacts/query_plan_truthfulness_results.json
```

### 9. Canonical JSON and Hash Stability

Objective: Verify identity hashing is deterministic and rejects unstable JSON.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| CJ-001 | NFC and NFD equivalent strings | same identity / duplicate blocked |
| CJ-002 | object key order differs | same identity |
| CJ-003 | object contains NaN | model/store boundary rejects before persistence |
| CJ-004 | object contains Infinity | model/store boundary rejects before persistence |
| CJ-005 | nested Unicode strings | normalized recursively |
| CJ-006 | tuple-like value if accepted | deterministic array serialization |

Artifact:

```text
artifacts/canonical_json_results.json
```

### 10. Audit Reason Validation

Objective: Verify audit-critical reason fields cannot be blank.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| AR-001 | empty rejection reason | model validation failure |
| AR-002 | whitespace rejection reason | model validation failure |
| AR-003 | empty invalidation reason | model validation failure |
| AR-004 | empty supersession reason | model validation failure |
| AR-005 | empty need rule rationale | model validation failure |
| AR-006 | empty need rule required dimension | model validation failure |
| AR-007 | empty revalidation queue reason | model validation failure |
| AR-008 | empty revalidation resolution rationale | model validation failure |

Artifact:

```text
artifacts/audit_reason_validation_results.json
```

### 11. Revalidation Queue API

Objective: Verify public revalidation APIs control active retrieval.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| RQ-001 | queue revalidation | pending queue created |
| RQ-002 | duplicate active queue request | existing queue returned, `created=false` |
| RQ-003 | pending revalidation | admitted fact hidden in active mode |
| RQ-004 | resolve revalidation | fact active again if otherwise valid |
| RQ-005 | cancel revalidation | behavior matches documented semantics |
| RQ-006 | fail revalidation | behavior matches documented semantics |
| RQ-007 | missing queue ID | `REVALIDATION_QUEUE_NOT_FOUND` |

Artifact:

```text
artifacts/revalidation_queue_api_results.json
```

### 12. Lifecycle and Audit Transactionality

Objective: Verify lifecycle writes are atomic and auditable.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| LA-001 | admit with unregistered evidence | rejected, status unchanged |
| LA-002 | unauthorized admission module | rejected, status unchanged |
| LA-003 | reject candidate | status rejected and audit row written |
| LA-004 | invalidation failure | no partial status/audit write |
| LA-005 | supersession failure | old/new statuses unchanged |
| LA-006 | successful supersession | old superseded, new admitted |
| LA-007 | conflict detection after admission | open conflict record created |

Artifact:

```text
artifacts/lifecycle_transactionality_results.json
```

### 13. Domain Error Contract

Objective: Verify public store methods expose machine-readable domain failures.

Boundary rule:

```text
Pydantic/model construction may raise ValidationError.
Public KnowledgeStore methods must not expose raw sqlite3 exceptions for expected negative paths.
```

Required store error codes:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| DE-001 | duplicate active fact identity | `DUPLICATE_FACT` |
| DE-002 | missing fact ID in `get_fact` | `FACT_NOT_FOUND` |
| DE-003 | invalid admission status | `INVALID_ADMISSION_STATUS` |
| DE-004 | unauthorized admission module | `UNAUTHORIZED_ADMISSION_MODULE` |
| DE-005 | admission evidence not registered | `ADMISSION_EVIDENCE_NOT_REGISTERED` |
| DE-006 | invalidation evidence not registered | `INVALIDATION_EVIDENCE_NOT_REGISTERED` |
| DE-007 | invalidation rule from another fact | `INVALIDATION_RULE_NOT_OWNED_BY_FACT` |
| DE-008 | missing revalidation queue | `REVALIDATION_QUEUE_NOT_FOUND` |

Required model/schema validation cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| DE-101 | invalid fact kind | Pydantic validation failure or SQLite CHECK if injected below model |
| DE-102 | invalid subject kind | Pydantic validation failure or SQLite CHECK if injected below model |
| DE-103 | invalid object kind | Pydantic validation failure or SQLite CHECK if injected below model |
| DE-104 | invalid evidence ref type | Pydantic validation failure or SQLite CHECK if injected below model |

Artifact:

```text
artifacts/domain_error_contract_results.json
```

### 14. Fact Completeness Gate

Objective: Verify incomplete, vague, causal, or unsupported claims cannot become admitted Knowledge.

Required missing-field cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| FC-001 | missing `subject_id` | model validation failure |
| FC-002 | missing/blank `predicate` | model validation failure |
| FC-003 | missing object | rejected by model construction or explicit test wrapper |
| FC-004 | missing `fact_validity_scope` | model validation failure |
| FC-005 | missing typed evidence refs | model validation failure |
| FC-006 | missing applicability profile | model validation failure |
| FC-007 | missing invalidation rule and no declaration | model validation failure |
| FC-008 | blank semantic summary | model validation failure |

Required semantic boundary cases:

| Case ID | Statement | Expected |
| --- | --- | --- |
| FC-101 | "Current component is unstable." | cannot be admitted without subject, scope, evidence, and precise predicate |
| FC-102 | "Use Python because it is better." | user/developer preference, not Knowledge fact |
| FC-103 | "The user prefers this, so it is a project constraint." | not admitted without policy/customer-written evidence |
| FC-104 | "This design will reduce failure rate." | causal candidate, not Knowledge fact |
| FC-105 | developer claim without verification | candidate may exist, admission must fail or be rejected |

Artifact:

```text
artifacts/fact_completeness_gate_results.json
```

### 15. Store Boundary Tests

Objective: Verify Knowledge Store does not perform implicit cross-store mutation.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| SB-001 | Archive ref exists in evidence field | does not auto-create admitted Knowledge |
| SB-002 | Archive ref supports admission | only through explicit evidence binding and admission request |
| SB-003 | admitted Knowledge fact exists | does not auto-write Causal Store |
| SB-004 | Knowledge fact used by causal workflow | only as explicit reference outside Knowledge Store |
| SB-005 | developer claim submitted | candidate/rejection only, not admitted fact |
| SB-006 | user preference submitted | not project fact without accepted evidence |

Artifact:

```text
artifacts/store_boundary_results.json
```

### 16. Concurrency

Objective: Verify local SQLite behavior is safe for personal local concurrent access.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| CC-001 | 16 concurrent identical candidate writes | exactly one success, rest `DUPLICATE_FACT` |
| CC-002 | concurrent different candidate writes | all succeed |
| CC-003 | concurrent reads during writes | no raw SQLite errors escape public API |
| CC-004 | concurrent admission of same fact | one success or controlled error |
| CC-005 | concurrent backup during reads | backup valid |
| CC-006 | mixed lifecycle workload | controlled errors only, no corrupted lifecycle/audit state |

Mixed lifecycle workload operations:

```text
put_candidate
admit_fact
query
queue_revalidation
resolve_revalidation
invalidate_fact
supersede_fact
backup_to
```

Each concurrency event must include:

```json
{
  "worker_id": "...",
  "operation": "...",
  "knowledge_id": null,
  "latency_ms": 0.0,
  "status": "ok|controlled_error|failed",
  "domain_error_code": null,
  "raw_exception_type": null,
  "transaction_result": "...",
  "timestamp_utc": "..."
}
```

Artifact:

```text
artifacts/concurrency_results.json
```

### 17. Backup, Restore, and Index Rebuild

Objective: Verify recovery and index rebuild behavior.

| Case ID | Scenario | Expected |
| --- | --- | --- |
| BR-001 | backup live DB | backup file exists |
| BR-002 | restored DB query | same relevant facts returned |
| BR-003 | integrity check | `ok` |
| BR-004 | foreign key check | empty |
| BR-005 | drop/rebuild FTS | query behavior restored |
| BR-006 | rebuild semantic tokens | CJK and English retrieval preserved |

Artifact:

```text
artifacts/backup_restore_results.json
```

### 18. Scale and Complexity Sanity

Objective: Verify indexed paths remain bounded for personal local project scale.

Dataset sizes:

```text
small: 100 facts
medium: 10,000 facts
large-local: 50,000 facts
```

| Case ID | Scenario | Required Evidence |
| --- | --- | --- |
| SC-001 | ID lookup | elapsed time and query plan |
| SC-002 | mandatory applicability query | elapsed time and indexed path |
| SC-003 | supplemental token query | elapsed time and indexed path |
| SC-004 | CJK token query | elapsed time and indexed path |
| SC-005 | missing-need detection | elapsed time and candidate counts |
| SC-006 | conflict detection admission | elapsed time and conflict count |

Recommended local guardrails:

```text
ID lookup at 50k facts: < 20 ms typical local run
mandatory recall at 50k facts: < 200 ms typical local run
supplemental token recall at 50k facts: < 300 ms typical local run
normal retrieval query_plan.full_scan_used = false
```

Artifact:

```text
artifacts/scale_complexity_results.json
```

## Realistic Scenario Tests

### Scenario A: Unusual Hardware Constraint Recall

Fact:

```text
Server-A storage controller X123 aging reduces storage-read throughput under high load.
```

Expected:

- Mandatory for server-A high-load storage read benchmark.
- Not active for server-B.
- Hidden when pending revalidation after X123 replacement event.

### Scenario B: Deployment Needs Runtime Version

Need rule:

```text
deploy requires target_runtime_version
```

Expected:

- Project-A runtime fact does not satisfy project-B deploy need.
- Project-B scoped runtime fact clears project-B missing need.

### Scenario C: Chinese Knowledge Recall

Fact:

```text
高负载存储读取性能会下降
```

Expected:

- Queries for `存储读取`, `吞吐下降`, and `高负载` recall the fact.
- FTS failure still recalls through token fallback with warning.

### Scenario D: Review Mode Investigation

Facts:

- rejected developer claim;
- invalidated runtime fact;
- superseded platform fact.

Expected:

- Active mode hides them.
- Review/historical mode exposes them for investigation without treating them as active truth.

## Final Report

Create:

```text
module_test_reports/knowledge_store_v1_production_verification_<YYYYMMDD_HHMMSS>/reports/KNOWLEDGE_STORE_V1_PRODUCTION_VERIFICATION_REPORT.md
```

Required sections:

```markdown
# Knowledge Store v1 Production Verification Report

## Scope
## Source Snapshot
## Repository State
## Commands Run
## Test Summary
## Schema and Migration Evidence
## SQLite Query Plan Evidence
## P0 Fix Verification
## P1 Hardening Verification
## Boundary Verification
## Concurrency Verification
## Realistic Scenario Results
## Scale and Complexity Results
## Evidence Artifacts
## Failures
## Remaining Risks
## Final Verdict
```

Final verdict must be exactly one of:

```text
PASSED: Knowledge Store v1 is production-ready for personal local Aegis use.
FAILED: Knowledge Store v1 is not production-ready.
BLOCKED: Verification could not complete.
```

## Acceptance Criteria

Knowledge Store v1 can be accepted only if all are true:

1. Focused Knowledge Store regression tests pass.
2. Full repository pytest passes.
3. Ruff passes.
4. `git diff --check` passes.
5. Source snapshot or clean commit identifies the tested source.
6. Schema and migration evidence is present.
7. SQLite query plan evidence is present for core indexed paths.
8. Mandatory recall works for every documented trigger dimension.
9. `fact_validity_scope` is a hard active-retrieval gate.
10. Missing-knowledge hard blocks are cleared only by scope- and dimension-matching admitted facts.
11. CJK near-lexical retrieval works through n-grams.
12. Invalidation rule ownership is enforced.
13. Historical/review mode can inspect non-active facts.
14. `no_known_invalidation` is persisted and auditable.
15. `query_plan` reflects actual execution path.
16. Canonical JSON normalizes Unicode and rejects NaN/Infinity.
17. Audit reason fields reject empty strings.
18. Revalidation queue APIs exist and affect active retrieval correctly.
19. Domain error contract is verified at both model and public store boundaries.
20. Fact completeness gate is verified.
21. Archive / Knowledge / Causal boundary behavior is verified within Knowledge Store scope.
22. Concurrent duplicate writes produce one persisted fact and controlled duplicate errors.
23. Mixed lifecycle concurrency does not corrupt lifecycle or audit state.
24. Backup/restore preserves query behavior.
25. Evidence artifacts are generated under `module_test_reports/`.
26. No raw SQLite exceptions escape public APIs in tested public paths.
27. No generated DB, cache, or report artifacts are staged for commit.

## Failure Handling

If any test fails:

1. Record command, exit code, and exact output.
2. Preserve failing DB snapshot under `db_snapshots/`.
3. Record affected `knowledge_id`, `rule_id`, `profile_id`, and queue ID when available.
4. Classify failure:
   - `contract_failure`;
   - `implementation_bug`;
   - `test_bug`;
   - `environment_blocker`;
   - `performance_regression`;
   - `evidence_generation_failure`.
5. Final verdict must not be `PASSED`.

## Git Hygiene

Before any commit:

```powershell
git status --short
git diff --check
```

Must not commit:

```text
module_test_reports/
.aegis/
*.sqlite3
*.sqlite3-wal
*.sqlite3-shm
__pycache__/
.pytest_cache/
.ruff_cache/
.venv*/
```

Commit candidates:

```text
docs/KNOWLEDGE_STORE_V1_PRODUCTION_TEST_PLAN_V2.md
tests/test_knowledge_store*.py
src/aegis/stores/knowledge/
```

Generated evidence is not a commit candidate unless the developer explicitly requests it.
