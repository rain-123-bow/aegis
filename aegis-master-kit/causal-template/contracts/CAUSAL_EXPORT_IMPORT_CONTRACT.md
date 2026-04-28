# Causal Export and Import Contract

## Purpose

Export/import exists to support cross-session continuity and branch review without falling back to raw conversation history.

## Export contents

A causal export may include:

- causal version metadata
- active/tentative/conflicted claim summaries
- accepted route plans
- current query snapshots
- review/merge summaries
- status transition summaries
- public seal references

It must not include:

- plaintext payload if the export is developer-visible
- decryption keys
- private proof material
- proof-generation internals
- full chain-of-thought

## Import semantics

Imported causal state is a baseline and route reference, not raw truth unless its seal and version continuity are validated by Master.

## Cross-session continuity

Cross-session continuity must use trusted seal succession and Master-side latest trusted seal state. It must not rely on reusing old session secrets or exposing old private material.
