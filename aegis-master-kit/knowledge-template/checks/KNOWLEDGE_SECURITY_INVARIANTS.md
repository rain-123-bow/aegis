# Knowledge Security Invariants

These invariants must remain true for Knowledge v1.

1. Real project Knowledge plaintext is not committed to developer-visible repository.
2. Developer cannot directly write active Knowledge.
3. Developer and agents submit proposals only.
4. Master is the only authority for admission, update, status migration, and seal.
5. Private security material is never stored in template, project repo, logs, or public documentation.
6. Public digests and public manifests are not sufficient to forge valid Knowledge updates.
7. Cross-session freshness requires trusted seal succession.
8. Rollback to an old locally consistent payload must be detectable when Master has latest trusted seal.
9. Knowledge is accessible to all roles through governed access, not raw local plaintext.
10. Knowledge entries are retained after invalidation or supersession.
