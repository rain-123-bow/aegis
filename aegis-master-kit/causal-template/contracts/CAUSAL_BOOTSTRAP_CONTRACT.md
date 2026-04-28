# Causal Bootstrap Contract

## Project instance location

A concrete project Causal Store must be created under:

```text
project-root/causal/
```

## Required repo-visible structure

```text
causal/
  causal_manifest.yaml
  encrypted/
  public/
  integrity/
```

The repo-visible store is only a shell and sealed encrypted state. It is not the Master-side plaintext causal graph.

## Required repo-visible files

- `causal_manifest.yaml`
- `encrypted/causal_payload.bin` or placeholder before first seal
- `public/causal_public_manifest.yaml`
- `public/causal_public_index.yaml`
- `integrity/latest_public_root.txt`
- `integrity/ledger_public.jsonl`
- `integrity/session_seals/`

## Bootstrap status

A freshly bootstrapped Causal Store is `bootstrap_pending` until Master performs server-side payload creation, encryption, and sealing.

## Branch model

When a Git branch is created, code, Archive, Knowledge, and Causal state branch together. The Causal Store must record its base Git branch, base commit if known, and causal version when available.

## No private implementation

Bootstrap tools in this template must not implement real encryption, decryption, secret generation, or private proof generation.
