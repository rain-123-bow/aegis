# Phase 23C v0.2 Three-Store Linkage Acceptance Report

## 1. Repository State

- repository: `C:\Users\playm\Documents\self-git\aegis`
- branch: `v0.1.0-alpha`
- HEAD before patch: `d07e79f09858be41e577b541f37a4a2d38d81323`
- HEAD summary: `d07e79f Add Phase 23B Knowledge Store persistence boundary`
- Python: `3.13.13`
- venv: `.venv-three-store-linkage-phase23c`

## 2. Patch Application Result

Patch package:

```text
C:\Users\playm\Documents\AAA\aegis_phase23c_three_store_linkage_patch_v0_2\aegis_phase23c_three_store_linkage_patch_v0_2
```

Application result: applied.

Apply command:

```powershell
py -3.13 C:\Users\playm\Documents\AAA\aegis_phase23c_three_store_linkage_patch_v0_2\aegis_phase23c_three_store_linkage_patch_v0_2\apply_phase23c_patch.py --repo-root C:\Users\playm\Documents\self-git\aegis
```

Changed files:

```text
README.md
aegis-master-kit/master/THREE_STORE_LINKAGE_POLICY.md
aegis-master-kit/master/THREE_STORE_LINKAGE_RESULT_CONTRACT.md
aegis-runtime/three_store_linkage/aegis_three_store_linkage/__init__.py
aegis-runtime/three_store_linkage/aegis_three_store_linkage/cli.py
aegis-runtime/three_store_linkage/aegis_three_store_linkage/linkage.py
aegis-runtime/three_store_linkage/aegis_three_store_linkage/validator.py
aegis-runtime/three_store_linkage/pyproject.toml
aegis-runtime/three_store_linkage/tests/test_phase23c_three_store_linkage.py
runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_PATCH_PLAN.md
runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_ACCEPTANCE_REPORT.md
```

## 3. Boundary Audit Result

Forbidden-path audit: pass.

No changes were made under:

```text
aegis-router/
aegis-runtime/archive_store/
aegis-runtime/knowledge_store/
aegis-runtime/causal_store/
aegis-runtime/debate/
aegis-runtime/execution/
aegis-runtime/test/
aegis-runtime/final_review/
aegis-master-kit/organization/topologies/
```

Production/global-write audit: pass.

Runtime source grep found no positive production/write/global-merge `True` assignments. One test fixture intentionally sets `global_causal_truth_merge_performed=True` to verify rejection of Causal boundary leakage. All result payloads kept these fields false:

```text
production_linkage_persistence
production_encryption
remote_sync_performed
archive_store_write_performed
knowledge_store_write_performed
causal_store_write_performed
global_causal_truth_merge_performed
ordinary_agent_direct_write_allowed
```

## 4. Test Result

Compile command:

```powershell
.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m compileall .\aegis-runtime\three_store_linkage\aegis_three_store_linkage
```

Compileall result: pass.

Pytest command:

```powershell
.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m pytest .\aegis-runtime\three_store_linkage -vv
```

Pytest result:

```text
22 passed in 0.25s
```

Required negative boundary tests present:

- `test_promoted_assets_archive_target_store_rejected`
- `test_promoted_assets_archive_typed_string_rejected`
- `test_knowledge_evidence_causal_ref_rejected`
- `test_knowledge_evidence_knowledge_ref_rejected`

Supplemental manual runtime check also validated:

- Causal evidence may cite Archive, Knowledge, Causal, and external source material.
- Causal `depends_on`, `supersedes`, and `invalidates` accept existing Causal facts.
- Causal `depends_on: knowledge:K0001` rejects with type mismatch.

## 5. CLI Smoke Result

CLI command shape:

```powershell
python -m aegis_three_store_linkage.cli validate --archive-root <archive> --knowledge-root <knowledge> --causal-root <causal> --output <result>
```

Results:

| case | status | decision | key proof |
| --- | --- | --- | --- |
| valid Archive / Knowledge / Causal linkage | `validated` | `accepted_local_three_store_linkage` | `checked_reference_count=7` |
| invalid Archive `promoted_assets -> archive:E0001` | `rejected` | `rejected` | `type_mismatches[0].field=promoted_assets`, `target_store=archive`, `target_id=E0001` |
| invalid Knowledge `evidence_refs -> causal:F0001` | `rejected` | `rejected` | `type_mismatches[0].field=evidence_refs`, `target_store=causal`, `target_id=F0001` |
| invalid Knowledge `evidence_refs -> knowledge:K0001` | `rejected` | `rejected` | `type_mismatches[0].field=evidence_refs`, `target_store=knowledge`, `target_id=K0001` |
| supplemental valid Causal dependency/evidence case | `validated` | `accepted_local_three_store_linkage` | `depends_on`, `supersedes`, `invalidates`, and Causal evidence refs validated |
| supplemental invalid Causal `depends_on -> knowledge:K0001` | `rejected` | `rejected` | type mismatch on `depends_on` |

Result artifacts were copied under ignored local evidence:

```text
local_artifacts/phase23c_three_store_linkage_evidence/cli_results/
```

## 6. Documentation Audit Result

Documentation audit: pass.

The following files state that Phase 23C is local demo linkage validation only and does not introduce production persistence, new department topology, long-lived agent profile, remote sync, encryption, store mutation, or global causal truth merge:

```text
README.md
aegis-master-kit/master/THREE_STORE_LINKAGE_POLICY.md
aegis-master-kit/master/THREE_STORE_LINKAGE_RESULT_CONTRACT.md
runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_PATCH_PLAN.md
runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_ACCEPTANCE_REPORT.md
```

The documentation also states:

- Archive `promoted_assets` may target only Knowledge or Causal.
- Archive `promoted_assets` targeting Archive is rejected.
- Knowledge `evidence_refs` may cite Archive or external source material only.
- Knowledge `evidence_refs` targeting Knowledge or Causal is rejected.

## 7. Final Verdict

accepted_phase23c_v0_2_three_store_linkage_boundary

## 8. Blockers / Notes

No blockers.

Notes:

- Phase 23C validates linkage only. It does not write Archive, Knowledge, or Causal stores.
- The test suite has 22 passing tests.
- Supplemental manual CLI checks were added for explicit Causal dependency/evidence behavior.
- Generated local smoke roots and venv are ignored and must not be committed.
- No push, merge, release, or PR was performed.
