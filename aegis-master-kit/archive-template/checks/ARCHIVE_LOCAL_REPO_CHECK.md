# Archive Local Repo Check

This check is safe to run locally because it does not validate private integrity proof.

It only checks repo-visible structural invariants:

- no plaintext task dossier paths
- no obvious secret/key files
- required public files exist
- encrypted payload placeholder exists or status is bootstrap_pending

It cannot prove Archive authenticity.

Authenticity requires Master-side private validation.
