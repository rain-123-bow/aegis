# Phase 23C Three-Store Linkage Patch Plan

## Verdict

Prepare a minimal Phase 23C patch that validates local demo Archive / Knowledge / Causal cross-store reference integrity.

## Scope

Phase 23C adds:

- Master-owned three-store linkage policy;
- result contract for linkage validation artifacts;
- dependency-free Python runtime under `aegis-runtime/three_store_linkage`;
- pytest suite covering valid links, missing refs, type mismatches, promoted-assets target-store rejection, Knowledge-evidence boundary rejection, boundary violations, request validation, sealed archive zip indexing, and CLI output;
- README update instructions and validation commands.

## Non-goals

Phase 23C does not add:

- production Archive / Knowledge / Causal backend;
- production encryption or key lifecycle;
- remote sync;
- new department topology;
- long-lived linkage agent profile;
- ordinary-agent direct store writes;
- Archive / Knowledge / Causal persistence mutation;
- canonical or global causal truth merge.

## Files Added

```text
aegis-master-kit/master/THREE_STORE_LINKAGE_POLICY.md
aegis-master-kit/master/THREE_STORE_LINKAGE_RESULT_CONTRACT.md
aegis-runtime/three_store_linkage/pyproject.toml
aegis-runtime/three_store_linkage/aegis_three_store_linkage/__init__.py
aegis-runtime/three_store_linkage/aegis_three_store_linkage/cli.py
aegis-runtime/three_store_linkage/aegis_three_store_linkage/linkage.py
aegis-runtime/three_store_linkage/aegis_three_store_linkage/validator.py
aegis-runtime/three_store_linkage/tests/test_phase23c_three_store_linkage.py
runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_PATCH_PLAN.md
runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_ACCEPTANCE_REPORT.md
```

## README Updates

The patch package includes an apply script that inserts Phase 23C README sections:

- Current status item for Phase 23C;
- Phase-1 scope subsection for Three-store linkage validation;
- dedicated `Three-store linkage integrity` section;
- Quick validation commands.

## Validation Commands

```powershell
py -3.13 -m venv .venv-three-store-linkage-phase23c
.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m pip install -U pip
.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m pip install -e ".\aegis-runtime\three_store_linkage[dev]"

.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m compileall .\aegis-runtime\three_store_linkage\aegis_three_store_linkage
.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m pytest .\aegis-runtime\three_store_linkage -vv
.\.venv-three-store-linkage-phase23c\Scripts\python.exe -m aegis_three_store_linkage.cli --help

git diff --check
git status --short
```

Expected targeted runtime result:

```text
22 passed
```
