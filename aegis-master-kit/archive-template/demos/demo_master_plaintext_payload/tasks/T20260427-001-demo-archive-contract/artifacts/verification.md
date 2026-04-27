# Verification - T20260427-001-demo-archive-contract

## Scope

This verification covers the Archive v1 template package as a bounded governance template.

## Checks

- Archive template and concrete project Archive are separated.
- Repo-visible project Archive stores encrypted payload and non-sensitive public metadata only.
- Master-side plaintext payload is documented as non-repo-visible.
- Archive does not produce Knowledge or Causal truth.
- Developer direct mutation is forbidden.
- Private security material and proof-generation internals are intentionally not implemented in repo-visible tools.

## Result

Accepted for demo purposes.
