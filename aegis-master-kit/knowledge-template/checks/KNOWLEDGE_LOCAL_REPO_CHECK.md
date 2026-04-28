# Knowledge Local Repo Check

This check validates only repo-visible structure.

It must not attempt to decrypt payloads or reproduce private integrity proof generation.

## Checks

1. `knowledge/README.md` exists.
2. `knowledge/encrypted/` exists.
3. `knowledge/public/knowledge_public_manifest.yaml` exists.
4. `knowledge/public/knowledge_public_index.yaml` exists.
5. `knowledge/integrity/latest_public_root.txt` exists.
6. `knowledge/integrity/ledger_public.jsonl` exists.
7. `knowledge/integrity/session_seals/` exists.
8. No obvious plaintext entry directories such as `knowledge/entries/` exist in repo-visible project Knowledge.
9. No files named like `*key*`, `*secret*`, `*seed*`, or `*private*` exist under repo-visible Knowledge.
10. Public manifest declares `plaintext_present: false`.

If these checks pass, the repo-visible shell layout is acceptable. It does not prove cryptographic validity.
