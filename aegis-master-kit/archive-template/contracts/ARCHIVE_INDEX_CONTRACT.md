# Archive Index Contract

## 1. Purpose

Archive indexes make records searchable and auditable.

Indexes are generated views, not source of truth.

## 2. Source of truth

The source of truth is the sealed Master-side plaintext payload plus its valid seal chain.

Repo-visible indexes are auxiliary.

If an index conflicts with task dossier content, Master must treat the index as stale and regenerate it.

## 3. Required indexes

Archive v1 should support these indexes:

```text
by_status.yaml
by_owner.yaml
by_source.yaml
by_date.yaml
by_module.yaml
```

Public indexes must contain only non-sensitive information.

## 4. Public index policy

Because project Archive is encrypted, public indexes must be minimal.

Allowed public index fields:

- task id
- status class if non-sensitive
- coarse date
- module tag if non-sensitive
- payload version
- opaque root token

Forbidden public index fields unless explicitly allowed:

- full discussion text
- responsibility-sensitive details
- private artifact content
- customer-sensitive data
- hidden causal conclusions
- secrets or credentials

## 5. Index rebuild

Master may rebuild indexes from plaintext payload after successful decryption and seal validation.

Rebuild must update public metadata and produce a new seal if it changes repo-visible state.

## 6. Index corruption

If indexes are missing or corrupted but encrypted payload and seal are valid, Master may rebuild indexes.

If indexes are modified and seal does not validate, Master must mark unauthorized mutation suspected.
