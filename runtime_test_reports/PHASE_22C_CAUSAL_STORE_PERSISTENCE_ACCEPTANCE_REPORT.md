# Phase 22C Causal Store Persistence Acceptance Report

## 1. Scope And Boundary

Phase 22C validates local demo Causal Store persistence after Phase 22B Master causal review.

Accepted scope:

- Apply the corrected Phase 22C v0.4 patch package.
- Validate local persistence of accepted Phase 22B review decisions.
- Validate local causal facts, index, semantic changelog, change records, snapshots, and rollback metadata.
- Validate rejected decisions do not write causal facts.
- Validate conflict protection for an existing non-identical fact target.

Out of scope:

- Production Causal Store backend.
- Production encryption or key lifecycle.
- Remote sync.
- Archive persistence.
- Knowledge persistence.
- Router or topology changes.
- Separate causal-store department closure.
- Long-lived causal-store agent closure.
- Global causal truth merge.

## 2. Repository State Before And After

Repository:

```text
C:\Users\playm\Documents\self-git\aegis
```

Branch before apply:

```text
v0.1.0-alpha
```

HEAD before apply:

```text
d58e22970c6e10f5fb638571a2b7ac076849047c
```

Working tree before apply:

```text
clean
```

Working tree after validation contains only Phase 22C source/report changes and ignored local evidence artifacts.

## 3. Patch Package Hygiene

Patch package:

```text
C:\Users\playm\Documents\AAA\aegis_phase22c_causal_store_persistence_patch_v0_4\aegis_phase22c_causal_store_persistence_patch_v0_4
```

Hygiene checks:

| Check | Result |
| --- | --- |
| Generated caches in patch package | none |
| CRLF files in patch package | none |
| Apply script has skip-identical handling | pass |
| Apply script has not-patchable guard | pass |
| Apply script references Phase 22A patch plan | pass |
| Apply script references Phase 22B patch plan | pass |
| Apply script uses byte-preserving writes | pass |
| Forbidden causal-store top-level route strings | absent |
| Forbidden separate department/agent compact names | absent |
| Production persistence/encryption/sync true flags | absent |

One wording issue was corrected in the patch package before apply: a negative-boundary phrase was changed from the exact forbidden department label to `separate causal-store department`.

## 4. Apply Dry-Run And Apply

Dry-run command:

```powershell
.\apply_phase22c_patch.ps1 -RepoRoot C:\Users\playm\Documents\self-git\aegis -DryRun
```

Dry-run result:

```text
pass
```

Apply command:

```powershell
.\apply_phase22c_patch.ps1 -RepoRoot C:\Users\playm\Documents\self-git\aegis
```

Apply result:

```text
pass
```

## 5. Files Changed

Added:

```text
aegis-master-kit/master/CAUSAL_STORE_PERSISTENCE_POLICY.md
aegis-master-kit/master/CAUSAL_STORE_PERSISTENCE_RESULT_CONTRACT.md
aegis-runtime/causal_store/pyproject.toml
aegis-runtime/causal_store/aegis_causal_store/__init__.py
aegis-runtime/causal_store/aegis_causal_store/cli.py
aegis-runtime/causal_store/aegis_causal_store/persistence.py
aegis-runtime/causal_store/tests/test_phase22c_causal_store_persistence.py
runtime_test_reports/PHASE_22C_CAUSAL_STORE_PERSISTENCE_PATCH_PLAN.md
runtime_test_reports/PHASE_22C_CAUSAL_STORE_PERSISTENCE_ACCEPTANCE_REPORT.md
```

Modified:

```text
README.md
```

## 6. Compile Validation

Command:

```powershell
.\.venv-causal-store-phase22c\Scripts\python.exe -m compileall .\aegis-runtime\causal_store\aegis_causal_store
```

Result:

```text
pass
```

Log:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/compileall_output.txt
```

## 7. Pytest Validation

Command:

```powershell
.\.venv-causal-store-phase22c\Scripts\python.exe -m pytest .\aegis-runtime\causal_store
```

Result:

```text
14 passed in 0.12s
```

The patch originally provided 12 tests. Two focused tests were added during acceptance hardening:

- missing supersession/invalidation references are rejected without writing a new fact;
- an existing non-identical target fact is not overwritten.

Log:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/pytest_output.txt
```

## 8. Semantic Grep

Checked patterns:

| Check | Count |
| --- | ---: |
| remote key-rotation command token | 0 |
| remote push command token | 0 |
| exact forbidden department label | 0 |
| exact forbidden agent compact name | 0 |
| causal store to master route spelling | 0 |
| master to causal store route spelling | 0 |
| production persistence enabled flag | 0 |
| production encryption enabled flag | 0 |
| remote sync enabled flag | 0 |
| Archive write enabled flag | 0 |
| Knowledge write enabled flag | 0 |
| `semantic changelog` | present |
| `rollback` | present |
| `snapshot` | present |
| `JSON-formatted YAML-compatible` | present |

Log:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/semantic_grep_output.txt
```

## 9. Topology, Department, And Agent Boundary

Validation result:

- No router files changed.
- No topology files changed.
- No new top-level route was added.
- No new top-level department was added.
- No long-lived causal-store agent was introduced.
- The runtime is a local demo persistence utility under `aegis-runtime/causal_store`.

## 10. CLI Persistence Validation

Command shape:

```powershell
.\.venv-causal-store-phase22c\Scripts\python.exe -m aegis_causal_store.cli persist `
  --review-decision <decision.json> `
  --causal-root <project>\causal `
  --output <result.json>
```

Scenarios:

| Scenario | Result |
| --- | --- |
| canonical add | persisted as `add_fact`, fact `F0001` |
| scope-limited add | persisted as `scope_limited_add`, fact `F0002` |
| supersession | persisted as `supersede`, fact `F0003`, updated `F0001` |
| invalidation | persisted as `invalidate`, fact `F0004`, updated `F0002` |
| developer decision required | rejected |
| direct global merge/write request | rejected |
| missing supersession reference | rejected |

CLI summary:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/cli_validation_summary.txt
```

Full CLI output audit:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/cli_output_audit.txt
```

## 11. Causal Store Structure

Generated local causal root:

```text
local_artifacts/phase22c_cli_test/project/causal
```

Structure:

```text
causal/index.yaml
causal/facts/F0001.yaml
causal/facts/F0002.yaml
causal/facts/F0003.yaml
causal/facts/F0004.yaml
causal/history/changelog.md
causal/history/changes/C0001.yaml
causal/history/changes/C0002.yaml
causal/history/changes/C0003.yaml
causal/history/changes/C0004.yaml
causal/snapshots/S0001.yaml
causal/snapshots/S0002.yaml
causal/snapshots/S0003.yaml
causal/snapshots/S0004.yaml
causal/rollback/R0001.yaml
causal/rollback/R0002.yaml
causal/rollback/R0003.yaml
causal/rollback/R0004.yaml
```

Index summary:

```text
fact_count: 4
F0001: superseded
F0002: invalidated
F0003: active
F0004: active
```

Structure log:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/causal_store_tree.txt
local_artifacts/phase22c_causal_store_persistence_evidence/logs/index_output.txt
```

## 12. Semantic Changelog

Semantic changelog:

```text
causal/history/changelog.md
```

Validated entries:

```text
C0001: add_fact
C0002: scope_limited_add
C0003: supersede
C0004: invalidate
```

Each entry records source review decision, affected facts, affected scope, reason, and rollback reference.

Log:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/changelog_output.txt
```

## 13. Snapshot Validation

Snapshots written:

```text
S0001.yaml
S0002.yaml
S0003.yaml
S0004.yaml
```

Each persisted operation wrote a local snapshot artifact. Snapshot output was logged at:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/snapshots_output.txt
```

## 14. Rollback Validation

Rollback metadata written:

```text
R0001.yaml
R0002.yaml
R0003.yaml
R0004.yaml
```

Validated rollback metadata fields:

- `change_id`
- `affected_fact_ids`
- `created_files`
- `updated_files`
- `previous_file_contents`
- `source_review_decision_id`

Rollback output was logged at:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/rollback_output.txt
```

## 15. Conflict And Idempotence

Conflict scenario:

- A pre-existing non-identical `facts/F0001.yaml` was created.
- A canonical add decision attempted to persist `F0001`.
- Runtime rejected the operation.
- Existing file content remained unchanged.

Conflict result:

```text
status: rejected
reason: Target fact file already exists and would be overwritten: facts/F0001.yaml
facts/F0001.yaml after rejected write: preexisting: conflicting-content
```

Log:

```text
local_artifacts/phase22c_causal_store_persistence_evidence/logs/conflict_test_output.txt
```

Patch application idempotence is handled by the patch apply script through skip-identical and not-patchable guards. Runtime persistence conflict safety is handled by rejecting non-identical target overwrites.

## 16. Git Status After Tests

Final hygiene commands:

```powershell
git diff --check
git status --short
```

Expected state:

- source/report files changed for Phase 22C;
- generated virtualenv, caches, pyc files, and local causal evidence artifacts are not tracked.

## 17. Evidence Bundle

Evidence directory:

```text
local_artifacts/phase22c_causal_store_persistence_evidence
```

Expected zip:

```text
local_artifacts/phase22c_causal_store_persistence_evidence.zip
```

The evidence bundle contains command logs, CLI input decisions, CLI outputs, generated local causal store state, conflict test output, and a copy of this report.

## 18. Final Yes/No Answers

1. Does Phase 22C persist Phase 22B reviewed causal decisions locally? Yes.
2. Does it persist canonical accepted facts? Yes.
3. Does it persist scope-limited facts with narrowed accepted scope? Yes.
4. Does it persist supersession decisions? Yes.
5. Does it persist invalidation decisions? Yes.
6. Does it reject unresolved developer decisions? Yes.
7. Does it reject direct global merge/store write attempts? Yes.
8. Does it reject missing referenced facts for supersession/invalidation? Yes.
9. Does it protect existing non-identical fact targets from overwrite? Yes.
10. Does it write an index? Yes.
11. Does it write fact files? Yes.
12. Does it write semantic change records? Yes.
13. Does it write a semantic changelog? Yes.
14. Does it write snapshots? Yes.
15. Does it write rollback metadata? Yes.
16. Does it perform production persistence? No.
17. Does it perform production encryption? No.
18. Does it perform remote sync? No.
19. Does it write Archive or Knowledge stores? No.
20. Does it change router or topology? No.
21. Does it claim production closure? No.

## 19. Final Verdict

accepted_local_causal_store_persistence_boundary
