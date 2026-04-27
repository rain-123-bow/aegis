# Archive Security Invariants

The following invariants must hold:

1. Archive plaintext is not committed to the project repository.
2. Developer cannot directly mutate Archive records.
3. Master is the only authority for decrypt/update/seal/validate.
4. Private security material is not disclosed.
5. Sealed records are corrected by amendment, not silent overwrite.
6. Public indexes are generated and non-sensitive.
7. Archive does not produce truth.
8. Archive is not an ordinary agent execution dependency.
9. Cross-session freshness requires latest trusted Master-side seal.
10. Missing or broken seal is a governance violation, not a warning.
