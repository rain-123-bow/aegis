# TraceRelay SDK runtime snapshot

This directory is Aegis's commit-bound runtime reference for the independently maintained TraceRelay component.

- Upstream: `git@github.com:rain-123-bow/TraceRelay.git`
- Upstream commit: `9775e26e6f0999a7047e0cff72e13c62da99c065`
- Production execution: `-I -B -m tracerelay` under the same Python executable as Aegis
- Runtime proof: Aegis validates this provenance manifest and requires the installed `tracerelay` package to have exactly the same files and bytes as `src/tracerelay`

The snapshot is not a build workspace. It intentionally excludes upstream tests, documentation, packaging caches, `egg-info`, and other generated files. An installed package containing extra runtime files, bytecode, native modules, or shadows is rejected. `LICENSE` is retained as legal metadata and is not runtime code.

Install an approved TraceRelay wheel into the same Python environment used by Aegis. Use `python -m pip install --no-compile --no-deps <wheel>` so installation does not create package bytecode. Runtime preflight rejects a missing package, another environment, or package bytes that differ from this snapshot.

The imported commit implements Aegis protocol v2: detached relaunches preserve `-I -B`, Supervisor and Service self-check the frozen Python/SDK digests, and every managed response binds the caller nonce plus both process creation identities. Static independent review `TRV2-20260818-001` accepted the combined implementation. Production activation still requires the user-authorized tests and an exact installed-package match. See `docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md` for the remaining activation contract.

To update the snapshot, run the committed importer against a clean upstream checkout:

```powershell
python tools/import_tracerelay_sdk.py `
  --upstream-worktree C:\path\to\TraceRelay `
  --source-commit <full-40-character-commit> `
  --git-command C:\absolute\path\to\git.exe `
  --git-sha256 <approved-git-executable-sha256> `
  --git-runtime-sha256 <approved-git-runtime-manifest-sha256>
```

The importer rejects a different origin, a different HEAD, tracked or untracked changes, non-regular Git entries, and an empty runtime package. It locks the approved Git executable and complete Git-for-Windows runtime manifest, uses Aegis's non-inherited Git environment, disables replace objects, and reads only runtime-package and `LICENSE` blobs from the explicit commit object. It never imports mutable worktree bytes and derives `PROVENANCE.json` deterministically.

Update all Aegis runtime-path expectations in the same change. Run the applicable local and real TraceRelay acceptance checks before committing the update.

Do not copy the upstream `.git` directory or restore the former Git submodule.
