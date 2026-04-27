# Decisions - T20260427-001-demo-archive-contract

## D001 - Archive is Master-maintained

- decided_at: 2026-04-27T00:20:00Z
- decided_by: master-main
- decision: accepted
- statement: Project Archive is maintained by Master and is not an ordinary agent execution dependency.
- rationale: Archive records history and responsibility. Execution agents should work from current query, Knowledge, Causal, and Master-issued constraints.
- alternatives:
  - Let ordinary agents directly depend on Archive.
  - Let developer directly maintain Archive.
- evidence_refs:
  - timeline.md#E003
- impact: Archive becomes governance asset, not execution input.

## D002 - Archive repository content is encrypted

- decided_at: 2026-04-27T00:25:00Z
- decided_by: master-main
- decision: accepted
- statement: Concrete project Archive stores encrypted payload in repo; plaintext exists only in Master-controlled runtime.
- rationale: Developer can clone the repository, so confidentiality and tamper detection must not rely on local trust.
- alternatives:
  - Store plaintext archive in repo.
  - Store security internals in repo.
- evidence_refs:
  - contracts/ARCHIVE_SECURITY_CONTRACT.md
- impact: Project archive layout contains encrypted/, public/, and integrity/ only.
