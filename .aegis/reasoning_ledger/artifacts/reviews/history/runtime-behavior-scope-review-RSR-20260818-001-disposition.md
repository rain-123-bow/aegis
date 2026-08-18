# Disposition of RSR-20260818-001

- Source review: `runtime-behavior-scope-review-RSR-20260818-001.md`
- Source review SHA-256: `e6868fd3c0b96bf9bd4f78ee1f52097d80fcea753a6450ae12c0f3ae75cd6028`
- Disposition date: `2026-08-18`
- Source review verdict remains: `FAIL`

## User clarification

TraceRelay is an independently maintained component at `git@github.com:rain-123-bow/TraceRelay.git`. The Git submodule existed only for development convenience. Production treats TraceRelay as a third-party Python SDK rather than building a source distribution from the Aegis checkout.

## Finding disposition

- `P1-1`: valid and actionable. Addressed by replacing the submodule with parent-repository runtime SDK blobs whose strict provenance manifest binds upstream commit `cb52a01de5d388add796e40887ffb4fd255c2cf7`; closure still requires independent review.
- `P1-2`: valid for the former live-worktree resolver. The TraceRelay `egg-info` case is addressed because build output is not copied into the SDK snapshot. The proposal now explicitly excludes the ignored, non-runtime `config/agent_registry.json.bak.20260706145929`; future unclassified files remain fail-closed.
- `P1-3`: contract misread after the user clarified the component boundary. Aegis does not build TraceRelay from this repository. Production executes the installed SDK as `-I -B -m tracerelay` under the same Python executable as Aegis. Alternate launchers and environments are rejected. The installed package must have exactly the source-snapshot file set and bytes, so upstream tests, docs, bytecode, native modules, packaging metadata, and source-distribution contents cannot enter through the package root.
- `P1-4`: valid and unresolved. Approval evidence still must bind the exact canonical Scope definition through a structured reviewer verdict and user confirmation.

## SDK migration adversarial review disposition

- Launcher/package environment mismatch: addressed by binding the command prefix to the active Aegis Python executable and executing `-I -B -m tracerelay`.
- Installed-package subset comparison: addressed by symmetric exact-tree comparison; any extra, missing, symbolic-link, size-mismatched, or hash-mismatched entry is rejected.
- Unexecuted provenance declaration: addressed by strict runtime parsing plus `tools/import_tracerelay_sdk.py`, which accepts only the canonical origin, exact clean HEAD, and Git-tracked runtime files before deriving the manifest.
- Ignored `config` backup: addressed by an exact proposal exclusion; policy materialization and independent review remain pending.
- Scope approval self-report: valid and unresolved; independent of the TraceRelay development-form migration.
- Vendoring authorization: the repository owner explicitly directed this development-form change in the governing task. The upstream `LICENSE` grants no general third-party redistribution rights; no broader permission is inferred.

## Final SDK migration review

The fresh-context review remains `FAIL` after the development-form change. Aegis-side package location now avoids executing installed code before validation. The importer now locks the complete approved Git runtime, removes inherited Git control state, disables replacement objects, and reads exact commit blobs. Its failure rollback tracks only targets actually moved or installed.

Two upstream-dependent P1 findings remain:

- TraceRelay protocol v1 relaunches Supervisor without preserving isolated Python flags.
- TraceRelay protocol v1 does not expose a durable runtime identity, so Aegis cannot prove that an existing daemon belongs to the verified SDK during crash recovery.

No production Scope PASS, v2 Seal, or readiness claim is permitted until a later approved TraceRelay commit and the Aegis client jointly close those findings.

This disposition does not convert the source review to `PASS`. A new full Scope review is required after the remaining findings and implementation changes are closed.
