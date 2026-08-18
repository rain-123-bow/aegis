# Aegis Runtime Behavior Scope Proposal

Status: `PROPOSED`; not accepted by the Coordinator until reviewer evidence and explicit user confirmation are recorded.

Project ID: `5339f0f6f03b4d3c8059fcfd314b2423`.

## Include roots

- `src`: Aegis coordinator, Seal adapter, reasoning ledger, App Server and TraceRelay clients.
- `config`: role templates, node schema, protected witness configuration.
- `skills`: shared, Master, A-F role behavior contracts; skill content changes agent runtime behavior.
- `third_party/TraceRelay/src/tracerelay`: commit-bound runtime source snapshot of the independently maintained TraceRelay SDK.
- `third_party/AegisSealCore/windows-x64`: pinned native sealing executable.

## Include files

- `requirements-runtime.txt`: exact production Python version pins. Coordinator additionally hashes every installed distribution file; the pin alone is not treated as a byte lock.
- `third_party/TraceRelay/PROVENANCE.json`: upstream repository, source commit, and exact runtime-source manifest for the vendored SDK snapshot.

## Exclusions

- `test`, `tests`, `demo`, `demos`, `example`, `examples`, `benchmark`, `benchmarks`.
- `docs`, Markdown/readme material, logs, build output, local virtual environments as repository content.
- `config/agent_registry.json.bak.20260706145929`; this ignored local backup is not loaded by production. Any future backup under an include root remains fail-closed until explicitly classified.
- TraceRelay upstream tests, documentation, packaging metadata, caches, and build output; they are not copied into the SDK runtime snapshot.
- `third_party/TraceRelay/README.md` and `third_party/TraceRelay/LICENSE`; they are maintenance and legal metadata, not runtime inputs.
- AegisSealCore provenance/readme files; the executable bytes and pinned SHA-256 are already bound.

## Forced inclusions

None currently. If production imports, loads, packages, or migrates a file under an excluded tree, that exact file must be added to `force_include_files` before a new Seal is issued.

## TraceRelay component boundary

TraceRelay remains an independently maintained component at `git@github.com:rain-123-bow/TraceRelay.git`. Aegis does not use a Git submodule and does not build TraceRelay from this repository. Development occurs in the upstream repository; an approved upstream commit is imported as ordinary parent-repository blobs under `third_party/TraceRelay/src/tracerelay`, with its identity recorded in `third_party/TraceRelay/PROVENANCE.json`.

Production executes the installed TraceRelay SDK as `-I -B -m tracerelay` under the exact Python executable already running Aegis. Alternate launchers and Python environments are rejected. Aegis validates the provenance manifest and requires the installed `tracerelay` package file set and bytes to equal the commit-bound SDK source snapshot exactly. Upstream tests, docs, bytecode, native modules, shadows, `egg-info`, source-distribution contents, and other build artifacts cannot enter the production package through this path.

TraceRelay commit `9775e26e6f0999a7047e0cff72e13c62da99c065` implements protocol v2. Detached Supervisor relaunches preserve isolated, no-bytecode Python flags. The control identity binds the Python executable digest, SDK manifest, interpreter startup flags, Supervisor and Service PID plus Windows creation time, and an Aegis-issued runtime nonce. Mutating requests also carry that nonce and are rejected before state change when it differs. Aegis writes the nonce, frozen digests, and launch intent before its only launch call, then immediately persists the observed process identity. Recovery requires that persisted identity and uses status-only attachment; a crash before identity persistence fails closed because a same-nonce live process cannot be proven to be the original. The snapshot manifest is `6f56afaba4b9b2fc9c49ec6b8c1af0847291d3c2f88f6d9b3ccd0867e2f0afd2`. Production activation remains blocked until the final Aegis validation and exact installed-package match both pass.

## External runtime closure

Project Seal covers committed repository bytes. The per-run frozen runtime manifest provides the equivalent boundary for executed bytes outside the repository:

- Aegis startup automatically re-executes under Python `-I -B` with a unique empty `pycache_prefix`;
- active Python/base executables, CPython DLLs, stdlib, native modules, every import root, every loaded module, and all site-packages bytes including existing bytecode;
- every dependency in the complete exact closure in `requirements-runtime.txt`, with dependency metadata checked for closure;
- Codex launcher, Node.js executable, and the complete installed `@openai/codex*` package closure;
- TraceRelay command prefix bound to the active Aegis Python plus the installed SDK package, with exact file-set and byte comparison against sealed `third_party/TraceRelay/src/tracerelay` and strict validation of its provenance manifest;
- Git launcher and its Git-for-Windows runtime tree; the runtime-scope policy pins both the launcher SHA-256 and canonical runtime-tree manifest SHA-256 before Git may provide Seal assertions;
- SHA-256 of every inherited environment value, including secret values without storing plaintext.

Coordinator re-hashes this closure at every A-F boundary and recursively watches every external import/tool root during node execution. Existing or newly created bytecode is therefore either frozen or an immediate mutation. Any difference terminates the run.

`src`, `config`, `skills`, and other production include roots must contain no `__pycache__`, `.pyc`, or `.pyo`. Scope resolution rejects them even if an exclusion rule would otherwise hide them. Production launch must disable bytecode writes; `test` and `demo` remain outside this rule because they are outside production roots.

The confirmed policy must include `external_tools.git_sha256`, `external_tools.git_runtime_sha256`, and one permanent 128-bit `runtime_authority_id`. The protected remote witness repeats that authority ID. Before publishing the witness, the migration step creates a matching local anchor and SQLite authority row. Production preflight never initializes them implicitly; missing anchor or database is treated as deletion, so removing `checkpoints.sqlite3` cannot reset mutation accountability.

## Migration gate

After the TraceRelay activation blockers are closed:

1. Write canonical definition version 1 to `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope.json`; it contains no approval evidence.
2. Record the independent structured review result that binds the definition SHA-256 and fixed review report.
3. Obtain the user's structured confirmation of that exact definition and review-result descriptor.
4. Write decision v3 binding the definition, review result, confirmation, project ID, confirmation ID, and `APPROVED`.
5. Commit the governed source, Scope definition, structured PASS review, user confirmation, and decision. Record that immutable commit ID.
6. Against that committed HEAD, create the local `aegis.project_seal_chain.v3`, retaining the existing project ID, binding the approved scope-decision SHA-256, and creating an explicit seal-chain ID. The Seal record is local reasoning-library instance state and is ignored by Git; committing it would change HEAD and invalidate its own commit binding.
7. Initialize the external runtime authority using `python src/main.py initialize-runtime-authority --project-root <project> [--runtime-root <path>]`; it consumes the sealed definition's `runtime_authority_id`.
8. Publish `aegis-seal-witness.json`, including the committed governed HEAD and same authority ID, to the protected `refs/heads/aegis-seal-witness` ref.
9. Fetch and verify the witness through production preflight.

Do not issue the v3 Seal against an uncommitted working tree. Do not add the local Seal record to Git. Do not fabricate reviewer or user-confirmation hashes.
