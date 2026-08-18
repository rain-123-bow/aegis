# Runtime Behavior Scope Contract

The approval chain is ordered and acyclic:

`canonical definition -> structured review result -> structured user confirmation -> decision manifest -> resolved manifest -> Seal`

Every JSON artifact uses canonical UTF-8 JSON: sorted keys, no insignificant whitespace, no trailing newline, and no NaN values.

## Canonical definition

Path: `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope.json`.

Schema: `aegis.runtime_behavior_scope_definition.v1`.

```json
{
  "schema": "aegis.runtime_behavior_scope_definition.v1",
  "project_id_hex": "32 lowercase hex digits",
  "version": 1,
  "include_roots": ["src", "config", "skills"],
  "include_files": ["requirements-runtime.txt"],
  "exclude_roots": ["test", "tests", "demo", "demos", "example", "examples", "benchmark", "benchmarks", "docs"],
  "exclude_files": [],
  "force_include_files": [],
  "external_tools": {
    "git_sha256": "64 lowercase hex digits",
    "git_runtime_sha256": "64 lowercase hex digits"
  },
  "runtime_authority_id": "32 lowercase hex digits"
}
```

The definition contains no review verdict, user decision, or evidence hash. Its canonical SHA-256 is stable before review begins.

## Structured review result

Human report path: `.aegis/reasoning_ledger/artifacts/reviews/runtime-behavior-scope-review.md`.

Result path: `.aegis/reasoning_ledger/artifacts/reviews/runtime-behavior-scope-review.json`.

Schema: `aegis.runtime_behavior_scope_review.v1`.

The result contains exactly: schema, non-empty review ID, project ID, canonical definition SHA-256, `verdict=PASS|FAIL`, and the fixed report path/size/SHA-256 descriptor. Production accepts only `PASS`.

## Structured user confirmation

Path: `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-user-confirmation.json`.

Schema: `aegis.runtime_behavior_scope_user_confirmation.v1`.

The confirmation contains exactly: schema, stable confirmation ID, project ID, canonical definition SHA-256, the fixed review-result path/size/SHA-256 descriptor, `decision=CONFIRMED`, and the user's non-empty statement. A statement cannot confirm a different definition or an earlier review result.

## Decision manifest

Path: `.aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-decision.json`.

Schema: `aegis.runtime_behavior_scope_decision.v3`.

The decision contains `decision=APPROVED`, project ID, and exact descriptors for the canonical definition, structured review result, and structured user confirmation. The confirmation descriptor repeats its stable confirmation ID. Coordinator resolution re-reads and rehashes every artifact before accepting the decision.

## Resolution and Seal

All paths are normalized project-relative UTF-8 paths with `/`. Include roots must be directories. `include_files` and `force_include_files` must be regular files; directory values are rejected. Selected symlinks and unsupported file types are rejected. `exclude_roots` and `exclude_files` remove non-production material; `force_include_files` overrides exclusions for specific production inputs.

`.aegis` cannot be selected as runtime code. Immutable reasoning-ledger configuration lives at `config/reasoning_ledger.json`; live ledger state remains under `.aegis`. The canonical definition SHA-256 and canonical decision SHA-256 are injected into the Seal as separate metadata. The decision SHA-256 is also part of `aegis.resolved_runtime_behavior_scope.v3`; replacement of an internally consistent approval chain therefore invalidates the old Seal. A definition change requires a higher version, a new review, a new user confirmation, a new decision, and a new Seal.

The Git launcher and complete supported runtime closure remain under one verified Windows share-lock session from pin validation through the final Git subprocess. `aegis.project_seal_chain.v3` and `aegis.remote_seal_witness.v3` both expose the exact decision SHA-256. Production additionally requires the protected remote witness to repeat the definition hash, decision hash, resolved manifest hash, project ID, Seal chain identity, sequence, Seal, governed commit, and `runtime_authority_id`.

The native SealCore validates normalized relative entries. It does not decide which files belong to production behavior.
