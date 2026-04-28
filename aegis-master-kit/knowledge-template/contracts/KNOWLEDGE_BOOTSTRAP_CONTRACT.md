# Knowledge Bootstrap Contract

## Purpose

When Master accepts a project, Master must create one project-level Knowledge Base using this template.

Default location:

```text
/project-root/knowledge/
```

## Project-level uniqueness

A project has exactly one Knowledge Base unless the project is explicitly split into separate projects.

Modules, departments, or agents must not create independent competing Knowledge Bases.

Use categories, indexes, and scopes inside the single Knowledge Base instead.

## Repo-visible shell

The local repository may contain only a repo-visible shell:

```text
knowledge/
  README.md
  encrypted/
    knowledge_payload.bin
  public/
    knowledge_public_manifest.yaml
    knowledge_public_index.yaml
  integrity/
    latest_public_root.txt
    ledger_public.jsonl
    session_seals/
```

This shell must not contain real plaintext Knowledge entries.

## Master-side plaintext payload

The decrypted Knowledge payload may exist only inside Master-controlled runtime or trusted server-side storage.

Template documentation may include demo plaintext payloads, but real project repositories must not store plaintext Knowledge entries.

## Bootstrap states

A newly created repo-visible shell may be marked:

```text
bootstrap_pending
```

It becomes usable only after Master-side encryption and sealing complete.
