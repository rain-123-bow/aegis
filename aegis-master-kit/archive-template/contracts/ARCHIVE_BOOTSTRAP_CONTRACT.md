# Archive Bootstrap Contract

## 1. Purpose

This contract defines how Master creates a concrete project Archive from `aegis-master-kit/archive-template`.

## 2. Bootstrap rule

When Master accepts a project, Master must create one project-level Archive.

Default location:

```text
/project-root/archive
```

The concrete Archive must follow `templates/project_archive_repo/`.

## 3. Repo-visible layout

The project repository should contain only encrypted payload and non-sensitive metadata.

```text
archive/
  README.md
  archive_manifest.yaml
  encrypted/
    archive_payload.bin
  public/
    archive_public_manifest.yaml
    indexes/
      by_status.yaml
      by_owner.yaml
      by_source.yaml
      by_date.yaml
      by_module.yaml
  integrity/
    ledger_public.jsonl
    latest_public_root.txt
    session_seals/
```

## 4. Master-only plaintext layout

The decrypted plaintext payload must exist only inside Master-controlled runtime.

It follows `templates/master_plaintext_payload/`:

```text
plaintext_payload/
  payload_manifest.yaml
  tasks/
    TYYYYMMDD-NNN-short-slug/
      task.yaml
      timeline.md
      decisions.md
      artifacts/
      amendments.md
      postmortem.md
```

This plaintext layout must not be committed into the project repository.

## 5. Bootstrap steps

Master must:

1. create the repo-visible `archive/` directory
2. create an initial Master-side plaintext payload
3. create initial public metadata
4. encrypt the plaintext payload into `archive/encrypted/archive_payload.bin`
5. generate a Master-private seal and public seal record
6. write a first public ledger entry
7. remove plaintext from any developer-visible filesystem path

## 6. No plaintext fallback

If encryption or seal generation is unavailable, Master must not create a plaintext Archive fallback inside the repository.

Allowed behavior:

- create only the empty repo-visible shell
- mark Archive as `bootstrap_pending`
- report that Master-side sealing is required

Forbidden behavior:

- commit `archive/tasks/*` plaintext
- commit `plaintext_payload/*`
- store decryption material in repo
- expose proof generation internals

## 7. Bootstrap manifest

The repo-visible `archive_manifest.yaml` must state:

- `archive_version`
- `project_id`
- `created_at`
- `created_by`
- `storage_mode: encrypted_payload`
- `plaintext_in_repo_allowed: false`
- `developer_direct_mutation_allowed: false`
- `ordinary_agent_execution_dependency: false`
