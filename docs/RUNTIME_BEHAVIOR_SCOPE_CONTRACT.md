# Runtime Behavior Scope Contract

Policy path: `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope.json`.

Decision path: `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-decision.json`.

Schema: `aegis.runtime_behavior_scope.v2`.

```json
{
  "schema": "aegis.runtime_behavior_scope.v2",
  "project_id_hex": "32 lowercase hex digits",
  "version": 1,
  "status": "user_confirmed",
  "include_roots": ["src", "config", "skills"],
  "include_files": ["pyproject.toml"],
  "exclude_roots": ["test", "tests", "demo", "demos", "example", "examples", "benchmark", "benchmarks", "docs"],
  "exclude_files": [],
  "force_include_files": [],
  "external_tools": {
    "git_sha256": "64 lowercase hex digits",
    "git_runtime_sha256": "64 lowercase hex digits"
  },
  "runtime_authority_id": "32 lowercase hex digits",
  "review": {
    "verdict": "PASS",
    "report_sha256": "64 lowercase hex digits"
  },
  "user_confirmation": {
    "confirmation_id": "stable external decision ID",
    "statement_sha256": "64 lowercase hex digits"
  }
}
```

All paths are normalized, project-relative, UTF-8 paths with `/`. Include roots and include files must exist. Selected symlinks and unsupported file types are rejected.

The policy is not approved by arbitrary hash-shaped strings. The v2 decision manifest must bind the canonical policy SHA-256, project ID, fixed reviewer report descriptor, fixed user-confirmation statement descriptor, stable confirmation ID, and `decision=APPROVED`. Every descriptor is rehashed. Production additionally requires the protected remote Git witness, which repeats `runtime_authority_id`; the decision evidence, policy, Git trust pin, and authority identity are commit-bound.

The Git launcher and its complete supported runtime closure (`mingw64/bin`, `mingw64/libexec/git-core`, and `usr/bin`, including SSH and shell dependencies) remain under one verified Windows share-lock session from pin validation through the final Git subprocess. Local Seal checks, runtime-identity capture, remote witness fetch, and authority-initialization absence proof may not cross an unlocked validation-to-execution boundary. Git subprocesses receive a replacement environment rather than inherited `GIT_*`, HOME config, proxy, askpass, or exec-path controls. The sealed witness config binds a canonical SSH URL, one SHA-256-bound ordinary identity file, and a sealed known-hosts file. SSH receives an isolated HOME and disables default identities, agents, PKCS#11, and FIDO/security-key providers; therefore `usr/lib/ssh` helpers are outside the supported execution graph. Remote operations use an isolated temporary bare repository.

`exclude_roots` and `exclude_files` remove non-production material. `force_include_files` overrides exclusion for a specific file that production imports, loads, packages, migrates, or otherwise uses at runtime.

`.aegis` cannot be selected as runtime code. Its policy is a reasoning fact; its canonical SHA-256 is injected into the Seal as metadata. Resolution creates an exact path/size/SHA-256 manifest; that manifest hash is also injected. A policy content change requires a higher version and a new Seal.

The native SealCore validates only normalized relative entries. It does not decide which directory is production code.
