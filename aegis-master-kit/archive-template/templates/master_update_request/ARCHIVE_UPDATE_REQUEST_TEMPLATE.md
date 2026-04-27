# Archive Update Request Template

Developer or agent may submit this request to Master.

They must not directly mutate Archive files.

```yaml
request_id: <id>
request_type: create_task|append_timeline|add_decision|add_artifact|amend_record|close_task|reopen_task
requested_by: <actor>
requested_at: <timestamp>
reason: <why this Archive update is needed>
target_task_id: <task id or null>
evidence_refs:
  - <reference>
proposed_content:
  summary: <summary>
  details: <structured details or pointer>
```

Master may accept, reject, downgrade, or request more evidence.
