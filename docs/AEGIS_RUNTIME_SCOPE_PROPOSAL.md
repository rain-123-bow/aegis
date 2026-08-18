# Aegis Runtime Behavior Scope Proposal

Status: `PROPOSED`; not accepted by the Coordinator until reviewer evidence and explicit user confirmation are recorded.

Project ID: `5339f0f6f03b4d3c8059fcfd314b2423`.

## Include roots

- `src`: Aegis coordinator, Seal adapter, reasoning ledger, App Server and TraceRelay clients.
- `config`: role templates, node schema, protected witness configuration.
- `skills`: shared, Master, A-F role behavior contracts; skill content changes agent runtime behavior.
- `submodules/TraceRelay/src`: managed relay implementation used by production execution.
- `third_party/AegisSealCore/windows-x64`: pinned native sealing executable.

## Include files

- `requirements-runtime.txt`: exact production Python version pins. Coordinator additionally hashes every installed distribution file; the pin alone is not treated as a byte lock.
- `submodules/TraceRelay/pyproject.toml`: TraceRelay build/runtime metadata.
- `.gitmodules`: production submodule source binding.

## Exclusions

- `test`, `tests`, `demo`, `demos`, `example`, `examples`, `benchmark`, `benchmarks`.
- `docs`, Markdown/readme material, logs, build output, local virtual environments as repository content.
- TraceRelay test and documentation trees.
- AegisSealCore provenance/readme files; the executable bytes and pinned SHA-256 are already bound.

## Forced inclusions

None currently. If production imports, loads, packages, or migrates a file under an excluded tree, that exact file must be added to `force_include_files` before a new Seal is issued.

## External runtime closure

Project Seal covers committed repository bytes. The per-run frozen runtime manifest provides the equivalent boundary for executed bytes outside the repository:

- Aegis startup automatically re-executes under Python `-I -B` with a unique empty `pycache_prefix`;
- active Python/base executables, CPython DLLs, stdlib, native modules, every import root, every loaded module, and all site-packages bytes including existing bytecode;
- every dependency in the complete exact closure in `requirements-runtime.txt`, with dependency metadata checked for closure;
- Codex launcher, Node.js executable, and the complete installed `@openai/codex*` package closure;
- TraceRelay launcher and installed Python source, with byte-for-byte comparison against sealed `submodules/TraceRelay/src/tracerelay`;
- Git launcher and its Git-for-Windows runtime tree; the runtime-scope policy pins both the launcher SHA-256 and canonical runtime-tree manifest SHA-256 before Git may provide Seal assertions;
- SHA-256 of every inherited environment value, including secret values without storing plaintext.

Coordinator re-hashes this closure at every A-F boundary and recursively watches every external import/tool root during node execution. Existing or newly created bytecode is therefore either frozen or an immediate mutation. Any difference terminates the run.

`src`, `config`, `skills`, and other production include roots must contain no `__pycache__`, `.pyc`, or `.pyo`. Scope resolution rejects them even if an exclusion rule would otherwise hide them. Production launch must disable bytecode writes; `test` and `demo` remain outside this rule because they are outside production roots.

The confirmed policy must include `external_tools.git_sha256`, `external_tools.git_runtime_sha256`, and one permanent 128-bit `runtime_authority_id`. The protected remote witness repeats that authority ID. Before publishing the witness, the migration step creates a matching local anchor and SQLite authority row. Production preflight never initializes them implicitly; missing anchor or database is treated as deletion, so removing `checkpoints.sqlite3` cannot reset mutation accountability.

## Migration gate

After reviewer PASS and user confirmation:

1. Write policy version 1 to `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope.json` with evidence hashes.
2. Create `aegis.project_seal_chain.v2`, retaining the existing project ID and creating an explicit seal-chain ID.
3. Initialize the external runtime authority using `python src/main.py initialize-runtime-authority --project-root <project> [--runtime-root <path>]`; it consumes the sealed policy's `runtime_authority_id`.
4. Commit the governed source and Seal record.
5. Publish `aegis-seal-witness.json`, including the same authority ID, to the protected `refs/heads/aegis-seal-witness` ref.
6. Fetch and verify the witness through production preflight.

Do not issue the v2 Seal against an uncommitted working tree. Do not fabricate reviewer or user-confirmation hashes.
