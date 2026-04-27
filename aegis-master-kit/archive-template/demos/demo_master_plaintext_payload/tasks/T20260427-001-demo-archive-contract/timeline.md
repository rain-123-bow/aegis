# Timeline - T20260427-001-demo-archive-contract

## E001 - Archive requirements proposed

- time: 2026-04-27T00:00:00Z
- actor: developer-demo
- event_type: task_proposed
- summary: Developer requested Archive v1 design.
- confirmed_points:
  - Archive must record task start and completion time.
  - Archive must record full task trajectory.
  - Archive must preserve stage artifacts.
  - Archive must record developer owner.
- unresolved_points:
  - Security model still needed.
- evidence_refs:
  - conversation:2026-04-27

## E002 - Task source added

- time: 2026-04-27T00:06:00Z
- actor: developer-demo
- event_type: requirement_added
- summary: Developer added that Archive must record task source.
- confirmed_points:
  - Task source is a first-class field.
- unresolved_points: []
- evidence_refs:
  - conversation:2026-04-27

## E003 - Security boundary accepted

- time: 2026-04-27T00:15:00Z
- actor: master-main
- event_type: architecture_clarified
- summary: Archive must be encrypted locally and sealed by Master-private security material.
- confirmed_points:
  - Developer cannot directly mutate Archive.
  - Local repo must not contain plaintext Archive content.
  - Master may disclose only verification results, not security internals.
- unresolved_points:
  - Concrete server-side implementation is outside repo-visible template.
- evidence_refs:
  - contracts/ARCHIVE_SECURITY_CONTRACT.md
