# Knowledge Index Contract

## 1. Index purpose

Knowledge indexes are derived helpers for lookup and routing.

Indexes are not source of truth.

## 2. Source of truth

The decrypted Master-side Knowledge payload is the source of truth after successful seal validation.

Repo-visible public indexes are non-sensitive summaries and must not be treated as complete Knowledge.

## 3. Required indexes

Recommended indexes:

- by_status
- by_category
- by_scope
- by_source_type
- by_version_context
- by_freshness

## 4. Conflict rule

If index content conflicts with sealed payload content:

- if seal validation succeeds, regenerate indexes from payload
- if seal validation fails, report integrity violation

## 5. Public index safety

Public indexes must not leak sensitive Knowledge plaintext.

They may contain IDs, categories, status counts, and safe summaries only.
