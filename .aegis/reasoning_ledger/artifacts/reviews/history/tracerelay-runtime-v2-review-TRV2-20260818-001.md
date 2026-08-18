# TraceRelay Runtime Protocol v2 Review

- Review ID: `TRV2-20260818-001`
- Review date: `2026-08-18`
- Reviewer: independent fresh-context Codex/GPT reviewer
- Verdict: `PASS`
- Remaining blocking findings in reviewed scope: `0`
- Cross-model review: skipped by the user's model-boundary decision
- Tests: not run by user instruction; verdict is limited to static implementation review

## Reviewed identities

- Aegis base commit: `26983719d3c5ed4945e6f9e79adf4a7880af8489`
- TraceRelay source repository: `git@github.com:rain-123-bow/TraceRelay.git`
- TraceRelay source commit: `861c0bf4e01162daa150cf37b92ac2d98e00d7e4`
- SDK snapshot manifest SHA-256: `006bf9a7dcfa4d92b96511d4a228daf82a7dcee69f23fe5cab622c509ed7f9ee`
- Proposal SHA-256: `9e1e25cfd627b203bd4dd0a16125a10690a2887e1fc2dc78b40ccd986c4045be`
- Runtime identity implementation SHA-256: `b8f36ced0e24706278002d9c6a2d509d2de193a0baa71523cac27b5e9b25b545`
- TraceRelay client SHA-256: `4e8c5adf026ec6efc5d63cd3d26e4ec32b8a7478eef5f2271f28f30bb77b0afe`
- Coordinator SHA-256: `e36ba5e26a9f381ee03a3831e00d309a30b4108beae06a09ea67c2242521bd55`
- Importer SHA-256: `725f41cfc9ad6489688a190f350b751d82dfefc795b5d7ce52c3b69b159ff3e3`
- Provenance file SHA-256: `21e1f1c37d1a9160a4a226ab4dfe0cdc6ad621f2ddafa8a70c9251c9507620ad`

## Closed findings

### Detached process chain preserves the verified runtime

TraceRelay explicitly launches the detached Supervisor with the verified Python executable and `-I -B`. Supervisor and Service independently verify the Python executable digest, exact SDK manifest, and interpreter startup flags before serving managed requests. The runtime identity binds both process IDs and Windows creation times.

### Existing daemon identity is caller-bound

Protocol v2 requires an Aegis-issued runtime nonce and the expected SDK/Python digests. Managed responses carry the complete runtime identity. Mutating `register`, `close`, and `stop` operations validate the nonce before state change. Aegis rejects an existing runtime unless all frozen bytes, flags, process roles, PIDs, and creation identities match.

### First-start crash recovery cannot launch a substitute runtime

RUN_STATE v11 commits `launch_intent_persisted=true` before the only authorized launch call. Every resume sets `require_existing_runtime=true`, including a crash state whose `observed_identity` is still null. Recovery therefore uses status-only attachment and fails when the original runtime is absent. Once the existing runtime is validated, Aegis immediately commits its observed identity before engineering-input validation, registration reconciliation, or session recovery.

The static regression cases cover an absent runtime after the pre-observation crash, a surviving runtime after that crash, and a different process with the same nonce and bytes after an identity was persisted.

### Source snapshot remains exact

The clean upstream commit and the vendored runtime snapshot contain the same 11 Python files with identical SHA-256 values. The canonical manifest remains `006bf9a7dcfa4d92b96511d4a228daf82a7dcee69f23fe5cab622c509ed7f9ee`.

## Scope boundary

This PASS closes the TraceRelay SDK migration and runtime protocol-v2 static review only. It does not issue a production-readiness claim, Scope PASS, user confirmation, v2 Seal, runtime authority, or remote witness.

Activation still requires the user-authorized test phase, an exact installed-SDK match in the real Aegis Python environment, the independent Scope approval-chain repair and review, user confirmation, an Aegis commit, v2 Seal, runtime authority, and protected remote witness.
