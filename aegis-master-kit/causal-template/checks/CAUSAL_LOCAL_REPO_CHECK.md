# Causal Local Repo Check

This check validates only the repo-visible Causal Store shell.

It must not decrypt payloads, generate private proofs, or validate Master-private integrity.

## Required structure

```text
causal/
  causal_manifest.yaml
  encrypted/
  public/
  integrity/
    session_seals/
```

## Required repo-visible files

- `encrypted/causal_payload.bin.placeholder` or encrypted payload file
- `public/causal_public_manifest.yaml`
- `public/causal_public_index.yaml`
- `integrity/latest_public_root.txt`
- `integrity/ledger_public.jsonl`

## Forbidden repo-visible content

- plaintext claims directory
- plaintext proposals directory
- private keys
- seeds
- proof-generation code
- decrypted causal graph
- real encryption/decryption implementation

## Result meaning

Passing this check means only that the local shell shape is correct. It does not prove semantic correctness or private integrity.

It also does not admit direct facts as Causal claims and does not authorize agent-generated output as global Causal writes. Those decisions require Master-side semantic checks and Causal Review.
