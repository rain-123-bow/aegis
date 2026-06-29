# Knowledge Store v1 Production Test Plan

## Status

Draft test plan for Knowledge Store v1 production readiness verification.

This plan is written after the source-level hardening fixes for:

- mandatory applicability recall;
- fact validity scope gating;
- missing-knowledge satisfaction;
- CJK near-lexical retrieval;
- invalidation rule ownership;
- historical/review retrieval;
- `no_known_invalidation` persistence;
- truthful query plans;
- canonical JSON hardening;
- audit reason validation;
- revalidation queue APIs.

This document is a test plan only. It does not claim that the tests have already passed.

## Goal

Verify that Knowledge Store v1 is safe to treat as a production-grade personal local SQLite-backed Aegis Knowledge Store.

The verification must prove two core responsibilities:

1. The store recalls facts that must be considered.
2. The store reports missing required knowledge instead of silently assuming.

The tests must also prove that lifecycle, audit, retrieval, persistence, backup, and indexing semantics remain correct under realistic local project usage.

## Non-Goals

- Do not test git history or Causal Store behavior except where Knowledge Store references their evidence IDs.
- Do not add vector database, embedding provider, or external search dependency.
- Do not benchmark cloud or multi-user production deployment.
- Do not claim semantic omniscience. The store can enforce indexed applicability and missing-knowledge rules, but it cannot infer every possible unstated dependency.
- Do not put verification artifacts under git-tracked source paths.

## Test Environment

Repository:

```text
C:\Users\playm\Documents\self-git\aegis
```

Python:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe
```

Primary commands:

```powershell
cd C:\Users\playm\Documents\self-git\aegis
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest tests\test_knowledge_store.py tests\test_knowledge_store_hardening.py tests\test_knowledge_store_source_hardening.py -vv
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest -vv
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m ruff check .
git diff --check
git status --short
```

Evidence output root:

```text
module_test_reports/knowledge_store_v1_production_verification_<YYYYMMDD_HHMMSS>/
```

Required evidence subdirectories:

```text
artifacts/
db_snapshots/
logs/
reports/
```

`module_test_reports/` is test evidence and should remain git-ignored.

## Verification Levels

### Level 1: Focused Regression

Purpose: Prove the source-review fixes directly.

Command:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest tests\test_knowledge_store_source_hardening.py -vv
```

Required result:

```text
all tests passed
```

### Level 2: Knowledge Store Suite

Purpose: Prove all Knowledge Store tests still pass together.

Command:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest tests\test_knowledge_store.py tests\test_knowledge_store_hardening.py tests\test_knowledge_store_source_hardening.py -vv
```

Required result:

```text
all tests passed
```

### Level 3: Full Repository Regression

Purpose: Prove Knowledge Store changes did not break unrelated Aegis modules.

Command:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m pytest -vv
```

Required result:

```text
all tests passed
```

### Level 4: Static Hygiene

Purpose: Prove code and whitespace are clean.

Commands:

```powershell
& 'C:\Users\playm\secret\.venv\Scripts\python.exe' -m ruff check .
git diff --check
```

Required result:

```text
ruff: passed
git diff --check: passed
```

### Level 5: Evidence Package

Purpose: Produce reviewable proof.

Required files:

```text
reports/KNOWLEDGE_STORE_V1_PRODUCTION_VERIFICATION_REPORT.md
artifacts/mandatory_recall_results.json
artifacts/fact_validity_scope_results.json
artifacts/missing_need_satisfaction_results.json
artifacts/cjk_ngram_retrieval_results.json
artifacts/invalidation_rule_ownership_results.json
artifacts/historical_review_mode_results.json
artifacts/no_known_invalidation_results.json
artifacts/query_plan_truthfulness_results.json
artifacts/canonical_json_results.json
artifacts/revalidation_queue_api_results.json
artifacts/concurrency_results.json
artifacts/backup_restore_results.json
logs/pytest_knowledge_store.log
logs/pytest_full.log
logs/ruff.log
logs/git_diff_check.log
```

Every JSON artifact must include:

```json
{
  "test_group": "...",
  "status": "passed|failed",
  "case_count": 0,
  "failed_cases": [],
  "domain_error_codes": [],
  "knowledge_ids": [],
  "rule_ids": [],
  "profile_ids": [],
  "notes": []
}
```

## Test Matrix

### 1. Mandatory Applicability Recall

Objective: Verify every documented trigger dimension either recalls the fact or is explicitly classified as non-trigger.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| MR-001 | `task_intents`-only profile matches query task intent | fact appears in `mandatory_facts` |
| MR-002 | `risk_classes`-only profile matches query risk class | fact appears in `mandatory_facts` |
| MR-003 | `affected_entities`-only profile matches query entity | fact appears in `mandatory_facts` if scope is valid |
| MR-004 | `affected_operations`-only profile matches query operation | fact appears in `mandatory_facts` |
| MR-005 | `affected_qualities`-only profile matches query quality | fact appears in `mandatory_facts` under v1 trigger policy |
| MR-006 | `lifecycle_phases`-only profile matches lifecycle phase | fact appears in `mandatory_facts` |
| MR-007 | `must_consider_when` matches query context | fact appears in `mandatory_facts` |
| MR-008 | required condition missing | fact does not become active mandatory truth |
| MR-009 | `exclude_when` matches query context | fact is rejected with `excluded_by_applicability_profile` |
| MR-010 | matching trigger but pending revalidation | fact is hidden in active mode |

Evidence artifact:

```text
artifacts/mandatory_recall_results.json
```

### 2. Fact Validity Scope

Objective: Verify `fact_validity_scope` is a hard active-retrieval gate.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| VS-001 | server-A fact queried for server-B | not active |
| VS-002 | project-A fact queried for project-B | not active |
| VS-003 | dependency version fact queried for different dependency | not active |
| VS-004 | runtime fact queried for different runtime | not active |
| VS-005 | platform fact queried for different platform | not active |
| VS-006 | explicitly global fact queried in matching project context | active if other gates pass |
| VS-007 | project-wide fact queried in same project | active if other gates pass |
| VS-008 | scope mismatch appears in `rejected_facts` when the fact is nominated | reason includes `fact_validity_scope_mismatch` or `scope_mismatch` |

Evidence artifact:

```text
artifacts/fact_validity_scope_results.json
```

### 3. Missing-Knowledge Satisfaction

Objective: Verify hard-block missing needs are cleared only by relevant admitted facts.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| MK-001 | deploy project-B while only project-A runtime fact exists | missing need remains |
| MK-002 | right subject kind but wrong subject ID exists | missing need remains |
| MK-003 | right subject kind but wrong predicate/dimension exists | missing need remains |
| MK-004 | right fact exists but is pending revalidation | missing need remains |
| MK-005 | rejected fact exists | missing need remains |
| MK-006 | invalidated fact exists | missing need remains |
| MK-007 | superseded fact exists without admitted replacement | missing need remains |
| MK-008 | matching admitted scoped fact exists | missing need clears |
| MK-009 | advisory need does not behave as hard-block need | advisory is reported separately or documented as unsupported |

Evidence artifact:

```text
artifacts/missing_need_satisfaction_results.json
```

### 4. CJK and Mixed-Language Retrieval

Objective: Verify deterministic Chinese and mixed-language near-lexical recall.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| CJK-001 | full Chinese phrase query | fact recalled |
| CJK-002 | partial Chinese phrase query | fact recalled |
| CJK-003 | Chinese bigram query | fact recalled |
| CJK-004 | Chinese trigram query | fact recalled |
| CJK-005 | mixed Chinese-English query | fact recalled |
| CJK-006 | FTS table dropped, token fallback used | fact recalled with degradation warning |
| CJK-007 | `rebuild_indexes()` preserves CJK retrieval | fact recalled after rebuild |
| CJK-008 | English token retrieval still works after CJK changes | English fact recalled |

Evidence artifact:

```text
artifacts/cjk_ngram_retrieval_results.json
```

### 5. Invalidation Rule Ownership

Objective: Verify invalidation cannot use another fact's rule.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| IO-001 | invalidate fact A using fact A rule | succeeds |
| IO-002 | invalidate fact A using fact B rule | rejected with `INVALIDATION_RULE_NOT_OWNED_BY_FACT` |
| IO-003 | invalidate fact A using missing rule | rejected |
| IO-004 | failed invalidation does not update status | old status preserved |
| IO-005 | failed invalidation does not write audit row | no invalidation record written |

Evidence artifact:

```text
artifacts/invalidation_rule_ownership_results.json
```

### 6. Historical and Review Retrieval Modes

Objective: Verify default active retrieval hides non-active facts, while review modes can retrieve them with reasons.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| HR-001 | active mode with rejected fact | hidden |
| HR-002 | review mode with rejected fact | visible or reported with rejection reason |
| HR-003 | historical mode with invalidated fact | visible or reported as invalidated |
| HR-004 | historical mode with superseded fact | visible or reported as superseded |
| HR-005 | active mode with pending revalidation | hidden with `pending_revalidation` reason |
| HR-006 | review mode with pending revalidation | visible or diagnosable |

Evidence artifact:

```text
artifacts/historical_review_mode_results.json
```

### 7. `no_known_invalidation`

Objective: Verify explicit no-known-invalidation declarations are auditable.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| NI-001 | fact with no invalidation rules and `no_known_invalidation=true` | accepted as candidate |
| NI-002 | persisted fact is read back | `no_known_invalidation == true` |
| NI-003 | fact without invalidation rules and without declaration | rejected at model validation |
| NI-004 | backup/restore preserves declaration | restored fact keeps declaration |

Evidence artifact:

```text
artifacts/no_known_invalidation_results.json
```

### 8. Query Plan Truthfulness

Objective: Verify `query_plan` reports actual execution paths.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| QP-001 | normal supplemental query with FTS available | `fts_used=true`, `fts_failed=false` |
| QP-002 | FTS unavailable | `fts_failed=true`, `degraded_recall=true` |
| QP-003 | token fallback used | `fallback_token_lookup_used=true` |
| QP-004 | no full scan is performed | `full_scan_used=false` |
| QP-005 | historical mode query | `historical_mode=true` |
| QP-006 | missing need rules checked | `missing_need_rules_checked=true` |

Evidence artifact:

```text
artifacts/query_plan_truthfulness_results.json
```

### 9. Canonical JSON and Hash Stability

Objective: Verify fact identity hashing is deterministic and rejects unstable JSON.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| CJ-001 | NFC and NFD equivalent strings | same identity hash / duplicate blocked |
| CJ-002 | object key order differs | same identity hash |
| CJ-003 | object contains NaN | rejected |
| CJ-004 | object contains Infinity | rejected |
| CJ-005 | nested Unicode strings | normalized recursively |
| CJ-006 | tuple-like input if accepted by model | serialized deterministically as array |

Evidence artifact:

```text
artifacts/canonical_json_results.json
```

### 10. Audit Reason Validation

Objective: Verify audit-critical reason fields cannot be empty.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| AR-001 | empty rejection reason | validation error |
| AR-002 | whitespace rejection reason | validation error |
| AR-003 | empty invalidation reason | validation error |
| AR-004 | empty supersession reason | validation error |
| AR-005 | empty need rule rationale | validation error |
| AR-006 | empty need rule required dimension | validation error |
| AR-007 | empty revalidation queue reason | validation error |
| AR-008 | empty revalidation resolution rationale | validation error |

Evidence artifact:

```text
artifacts/audit_reason_validation_results.json
```

### 11. Revalidation Queue API

Objective: Verify public revalidation APIs control active retrieval.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| RQ-001 | queue revalidation | pending queue created |
| RQ-002 | queue duplicate active revalidation | existing queue returned, `created=false` |
| RQ-003 | pending revalidation hides admitted fact in active mode | fact not active |
| RQ-004 | resolve revalidation | fact active again if otherwise valid |
| RQ-005 | cancel revalidation | behavior matches documented semantics |
| RQ-006 | fail revalidation | fact remains hidden or flagged according to documented semantics |
| RQ-007 | missing queue ID | controlled `REVALIDATION_QUEUE_NOT_FOUND` |

Evidence artifact:

```text
artifacts/revalidation_queue_api_results.json
```

### 12. Lifecycle and Audit Transactionality

Objective: Verify lifecycle writes are atomic and auditable.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| LA-001 | admit fact with unregistered evidence | rejected, status unchanged |
| LA-002 | unauthorized module tries admission | rejected, status unchanged |
| LA-003 | reject candidate | status rejected and audit row written |
| LA-004 | invalidation failure | no partial status/audit write |
| LA-005 | supersession failure | old/new statuses unchanged |
| LA-006 | successful supersession | old superseded, new admitted |
| LA-007 | conflict detection after admission | open conflict record created, not auto-resolved |

Evidence artifact:

```text
artifacts/lifecycle_transactionality_results.json
```

### 13. Concurrency

Objective: Verify local SQLite behavior is safe for personal local concurrent access.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| CC-001 | 16 concurrent identical candidate writes | exactly one success, rest `DUPLICATE_FACT` |
| CC-002 | concurrent different candidate writes | all succeed |
| CC-003 | concurrent reads during writes | no raw SQLite errors escape public API |
| CC-004 | concurrent admission of same fact | one success or controlled already-admitted error |
| CC-005 | concurrent backup during reads | backup succeeds and integrity check passes |

Evidence artifact:

```text
artifacts/concurrency_results.json
```

### 14. Backup, Restore, and Index Rebuild

Objective: Verify the store can be recovered and indexes can be rebuilt.

Required cases:

| Case ID | Scenario | Expected |
| --- | --- | --- |
| BR-001 | backup live DB | backup file exists |
| BR-002 | restored DB query behavior equals source DB | same relevant facts returned |
| BR-003 | `PRAGMA integrity_check` | `ok` |
| BR-004 | `PRAGMA foreign_key_check` | empty |
| BR-005 | drop/rebuild FTS | query behavior restored |
| BR-006 | rebuild semantic tokens | CJK and English retrieval preserved |

Evidence artifact:

```text
artifacts/backup_restore_results.json
```

### 15. Scale and Complexity Sanity

Objective: Verify the implementation does not regress to broad full scans in normal indexed paths.

Dataset sizes:

```text
small: 100 facts
medium: 10,000 facts
large-local: 50,000 facts
```

Required measurements:

| Case ID | Scenario | Required Evidence |
| --- | --- | --- |
| SC-001 | get by ID at all dataset sizes | elapsed time and query count |
| SC-002 | mandatory applicability query | query plan and elapsed time |
| SC-003 | supplemental token query | query plan and elapsed time |
| SC-004 | CJK token query | query plan and elapsed time |
| SC-005 | missing-need detection | elapsed time and candidate counts |
| SC-006 | conflict detection admission | elapsed time and conflict count |

Recommended local thresholds:

```text
ID lookup at 50k facts: < 20 ms typical local run
mandatory recall at 50k facts: < 200 ms typical local run
supplemental token recall at 50k facts: < 300 ms typical local run
no query plan reports full_scan_used=true for normal retrieval
```

These thresholds are local-development guardrails, not universal hardware-independent guarantees.

Evidence artifact:

```text
artifacts/scale_complexity_results.json
```

## Realistic Scenario Tests

### Scenario A: Unusual Hardware Constraint Recall

Input facts:

- Server-A storage controller X123 aging reduces storage-read throughput under high load.
- Fact validity scope: `project=demo`, `host=server-A`, `device=X123`.
- Applicability: benchmark, storage read, throughput, high load.

Task:

```text
Benchmark storage read performance on server-A under high load.
```

Expected:

- The X123 aging fact is mandatory.
- The same fact is not active for server-B.
- If X123 replacement is queued for revalidation, the fact is hidden and revalidation is visible.

### Scenario B: Deployment Needs Runtime Version

Need rule:

```text
deploy requires target_runtime_version
```

Facts:

- project-A Python runtime version is 3.11.
- project-B has no runtime fact.

Task:

```text
Deploy project-B.
```

Expected:

- Missing knowledge remains for project-B.
- Adding project-B scoped runtime fact clears the missing need.

### Scenario C: Chinese Knowledge Recall

Fact:

```text
高负载存储读取性能会下降
```

Queries:

```text
存储读取
吞吐下降
高负载
```

Expected:

- Relevant fact is recalled without exact full-phrase matching.
- FTS failure still recalls through token fallback with warning.

### Scenario D: Review Mode Investigation

Facts:

- One rejected developer claim.
- One invalidated runtime fact.
- One superseded platform fact.

Task:

```text
Review why a prior implementation route was rejected.
```

Expected:

- Active mode hides these facts.
- Review/historical mode can retrieve and explain non-active status.

## Required Report Structure

Create:

```text
module_test_reports/knowledge_store_v1_production_verification_<YYYYMMDD_HHMMSS>/reports/KNOWLEDGE_STORE_V1_PRODUCTION_VERIFICATION_REPORT.md
```

Report sections:

```markdown
# Knowledge Store v1 Production Verification Report

## Scope
## Repository State
## Commands Run
## Test Summary
## P0 Fix Verification
## P1 Hardening Verification
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
5. Mandatory recall works for every documented trigger dimension.
6. `fact_validity_scope` is a hard active-retrieval gate.
7. Missing-knowledge hard blocks are cleared only by scope- and dimension-matching admitted facts.
8. CJK near-lexical retrieval works through n-grams.
9. Invalidation rule ownership is enforced.
10. Historical/review mode can inspect non-active facts.
11. `no_known_invalidation` is persisted and auditable.
12. `query_plan` reflects actual execution path.
13. Canonical JSON normalizes Unicode and rejects NaN/Infinity.
14. Audit reason fields reject empty strings.
15. Revalidation queue APIs exist and affect active retrieval correctly.
16. Concurrent duplicate writes produce one persisted fact and controlled duplicate errors.
17. Backup/restore preserves query behavior.
18. Evidence artifacts are generated and stored under `module_test_reports/`.
19. No raw SQLite exceptions escape public APIs in tested public paths.
20. No generated runtime DB, cache, or report artifacts are staged for commit.

## Failure Handling

If a test fails:

1. Record the failing command and exact output.
2. Preserve the failing DB snapshot under `db_snapshots/`.
3. Record affected `knowledge_id`, `rule_id`, and `profile_id` when available.
4. Classify the failure:
   - `contract_failure`;
   - `implementation_bug`;
   - `test_bug`;
   - `environment_blocker`;
   - `performance_regression`.
5. Do not mark the store production-ready.

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

The test plan and source tests are commit candidates. Generated evidence is not.
