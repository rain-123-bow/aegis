# Project Knowledge Repository Shell

This is the repo-visible shell of a project Knowledge Base.

It must contain only:

- encrypted payload
- public metadata
- public index summaries
- opaque seals
- public ledger summary

It must not contain real plaintext Knowledge entries, keys, seeds, private proof material, or reproducible verification procedures.

A Master-side runtime decrypts, updates, validates, and reseals the payload.
