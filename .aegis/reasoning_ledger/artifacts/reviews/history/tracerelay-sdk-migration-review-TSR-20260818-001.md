# TraceRelay SDK Migration Review

- Review ID: `TSR-20260818-001`
- Review date: `2026-08-18`
- Reviewer: independent fresh-context Codex/GPT reviewer
- Verdict: `FAIL`
- Remaining blocking findings: `2`
- Cross-model review: skipped by the user's model-boundary decision
- Tests: not run by user instruction; review used static inspection, hashes, and Git object queries

## Reviewed identities

- Aegis base commit: `26983719d3c5ed4945e6f9e79adf4a7880af8489`
- TraceRelay source repository: `git@github.com:rain-123-bow/TraceRelay.git`
- TraceRelay source commit: `cb52a01de5d388add796e40887ffb4fd255c2cf7`
- SDK manifest SHA-256: `a9af89c828081b98d194462375c64742d3dcdcdac2a82587476217a5b162d9ef`
- Proposal SHA-256: `d158274835f79d1bfa2fb799f8a4f44d98469253fc24acef382de1336be2be62`
- Runtime identity implementation SHA-256: `b8f36ced0e24706278002d9c6a2d509d2de193a0baa71523cac27b5e9b25b545`
- TraceRelay client SHA-256: `56d2b3bf4caa27bc818658142c8bb0c03e9e570eee22630f8a41e21087add5e8`
- Importer SHA-256: `725f41cfc9ad6489688a190f350b751d82dfefc795b5d7ce52c3b69b159ff3e3`
- Provenance file SHA-256: `8ecc9efc12aecaa8489b9dab40e04f8eae56724cb4b142c2d1fd76045d91add7`

## Closed during disposition

### Installed code executed before validation

The first draft used `importlib.import_module("tracerelay")` to locate the package, which could execute unverified `__init__.py`. The implementation now locates exactly one `TraceRelay` distribution through metadata, resolves its declared `tracerelay/__init__.py` without importing it, then verifies the exact package tree before TraceRelay execution.

### Importer Git identity was inherited

The first draft trusted `git` from `PATH` and inherited Git control variables. The importer now requires approved launcher and Git-for-Windows runtime manifest hashes, holds that runtime stable across all queries, uses Aegis's non-inherited Git environment, disables replace objects, and reads explicit commit blobs.

### Importer rollback could remove untouched targets

The first draft's error path removed all targets. The importer now separately records targets moved to backup and targets installed during the current attempt. Rollback removes only installed targets and restores only completed backups.

## P1-1: Detached Supervisor loses the verified interpreter contract

TraceRelay commit `cb52a01de5d388add796e40887ffb4fd255c2cf7` relaunches Supervisor at `third_party/TraceRelay/src/tracerelay/supervisor.py:43` and `:254` with `python -m tracerelay.supervisor`, without preserving the initial `-I -B` flags. Aegis sanitizes Python environment variables and sets safe-path, no-user-site, and no-bytecode controls for descendants, but protocol v1 does not let the daemon attest or self-check the required flags.

Closure requires a later approved upstream commit that launches every Supervisor and Service process with the required interpreter isolation, fails closed when flags differ, and is re-imported through the pinned importer.

## P1-2: Existing daemon identity is not provable

TraceRelay protocol v1 returns `started=false` and accepts an existing compatible daemon at `third_party/TraceRelay/src/tracerelay/cli.py:155-169`. Aegis validates product, protocol, state, and PIDs, but the status payload does not bind Python executable bytes, package manifest, startup flags, process creation identities, or an Aegis-issued runtime nonce. Crash recovery therefore cannot prove that an existing daemon belongs to the SDK frozen for the run.

Closure requires a durable protocol identity jointly implemented by TraceRelay and Aegis. Aegis must persist it before accepting work and require an exact match during recovery. Fresh execution must reject an existing daemon without that identity.

## Final decision

The submodule-to-SDK development-form migration is structurally valid but not production-eligible. Do not issue Scope PASS, v2 Seal, user-confirmed migration, remote witness, or runtime readiness evidence until both P1 findings are closed and independently reviewed.
