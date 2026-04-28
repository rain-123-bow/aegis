# Knowledge Consistency Check

Master should run consistency checks before trusting or sealing Knowledge.

## Required checks

1. Project has exactly one Knowledge Base instance.
2. Repo-visible Knowledge contains no real plaintext payload.
3. Encrypted payload and integrity structure exist.
4. No private keys, seeds, session secrets, or proof internals are present in repo-visible files.
5. Each Knowledge entry has source, scope, version_context, applicability, status, and confidence.
6. Every active entry has at least one source.
7. Every conditional entry has objective applicability conditions.
8. No strategy, recommendation, or causal conclusion is stored as Knowledge.
9. No two conflicting entries are both active under the same scope/version_context.
10. Deprecated, invalidated, superseded, and conflicted entries are retained and not deleted.
11. Invalidated entries contain invalidation reason and evidence.
12. Superseded entries link to successor entries.
13. Public indexes are derived and do not contain sensitive plaintext.
14. If public indexes disagree with sealed payload, regenerate indexes after seal validation.
15. If seal validation fails, stop project governance actions that require Knowledge continuity and report integrity violation.
16. If latest trusted seal is unavailable, mark freshness as unknown.
