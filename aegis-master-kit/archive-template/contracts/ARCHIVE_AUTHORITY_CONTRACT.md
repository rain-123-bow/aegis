# Archive Authority Contract

## 1. Authority rule

Master is the only authority allowed to create, decrypt, update, seal, validate, close, reopen, or amend Archive records.

## 2. Developer boundary

Developer may:

- request a new Archive entry
- provide evidence or materials
- request correction of an Archive error
- object to an Archive record
- approve responsibility-bearing external actions

Developer must not:

- directly edit Archive records
- directly edit encrypted payload bytes
- directly edit public seal records
- directly edit public ledger records
- directly edit generated indexes
- generate or modify integrity proof material
- request private security material

## 3. Ordinary agent boundary

Ordinary agents may be recorded in Archive.

They must not treat Archive as a normal execution input.

They may receive from Master:

- current query
- task constraints
- relevant Knowledge
- relevant Causal facts
- specific artifact references selected by Master

They must not independently mine Archive history as an execution dependency unless Master explicitly creates a governed retrieval task.

## 4. Update request model

Developer and agents submit Archive update requests, not direct writes.

A valid update request should include:

```yaml
request_type: create_task|append_timeline|add_artifact|add_decision|amend_record|close_task
requested_by: <actor>
reason: <why this update is needed>
evidence_refs:
  - <reference>
proposed_content: <summary or structured content>
```

Master decides whether to accept, reject, or request more evidence.

## 5. Violation handling

If Master detects direct mutation, missing seal, broken seal, stale payload, rollback, or unauthorized edit, Master must mark the Archive state as compromised until resolved.

Allowed actions:

- stop using local Archive copy
- report integrity violation
- ask developer for recovery instruction
- restore from last trusted seal if available
- create a new Archive branch only with explicit governance record

Forbidden actions:

- silently repair without recording a violation
- accept edited records as valid
- downgrade security failure to formatting warning
