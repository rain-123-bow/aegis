# Archive Task Dossier Contract

## 1. Purpose

A task dossier is the minimal auditable unit inside Archive.

It records task source, lifecycle, responsibility, trajectory, decisions, artifacts, amendments, and outcome.

## 2. Storage location

Task dossiers exist in the Master-side plaintext payload.

They must not be stored as plaintext in the project repository.

Repo-visible archive stores only encrypted payload and public metadata.

## 3. Task id

Task id format:

```text
TYYYYMMDD-NNN-short-slug
```

Examples:

```text
T20260427-001-archive-contract
T20260427-002-router-ack-policy
T20260428-001-master-department-model
```

Rules:

- `task_id` is immutable.
- `task_id` must not be reused.
- task title may change through amendment.
- task id date is the creation date.

## 4. Status state machine

Allowed statuses:

```text
created
admitted
in_progress
blocked
reviewing
verifying
completed
aborted
superseded
reopened
```

Terminal statuses:

```text
completed
aborted
superseded
```

Terminal task records must not be silently edited. Any correction requires an amendment record.

## 4.1 Terminal completion gate

A task must not enter terminal status `completed` unless all required terminal records exist.

For completed tasks, Master must require at minimum:

- `lifecycle.completed_at`
- a final accepted decision or accepted outcome
- required stage artifact references, or an explicit waiver amendment
- `outcome.verification_summary`
- `outcome.known_limits`
- a postmortem reference
- a valid outcome block

If any of these records are missing, the completed state is invalid.

Master must reject terminal closure until the required records exist or an explicit waiver amendment records why a terminal requirement is waived. The task must remain non-terminal, or be reopened if it was already marked completed incorrectly.

## 5. Required sections

A task dossier must include:

```yaml
task_id: <immutable id>
title: <human-readable title>
status: <task status>
task_source: <source record>
lifecycle: <time record>
responsibility: <responsibility chain>
scope: <goal, in-scope, out-of-scope>
success_criteria: <list>
timeline_refs: <references into timeline.md>
decision_refs: <references into decisions.md>
artifact_refs: <stage artifact manifest>
terminal_completion_gate: <terminal completion gate fields>
outcome: <result record>
```

## 6. Task source

Task source is first-class.

A task without source is not auditable.

Required fields:

```yaml
task_source:
  source_type: developer_request|master_generated|test_failure|review_blocker|incident|roadmap|external_requirement|followup
  source_ref: <reference or null>
  raised_by: <actor>
  raised_at: <timestamp>
  original_request: <compressed original request>
  trigger_reason: <why this became a task>
```

## 7. Lifecycle

Required lifecycle fields:

```yaml
lifecycle:
  created_at: <timestamp>
  admitted_at: <timestamp or null>
  started_at: <timestamp or null>
  blocked_at: <timestamp or null>
  completed_at: <timestamp or null>
  aborted_at: <timestamp or null>
  superseded_at: <timestamp or null>
```

`created_at` and final terminal timestamp must not be inferred silently.

## 8. Responsibility

Responsibility must distinguish AI candidate work from real-world responsibility.

```yaml
responsibility:
  developer_owner: <human owner>
  master_owner: <master id>
  final_human_approver: <human or null>
  ai_participants:
    - role: master|author|reviewer|verification|adjudicator|other
      id: <agent id>
      contribution: <summary>
```

AI may produce candidate work, reviews, and reports.

Developer retains responsibility for critical real-world actions such as push, main merge, release, and formal external sign-off.

## 9. Timeline

Timeline records critical events, not full chat logs.

Every critical event should have:

- event id
- timestamp
- actor
- event type
- summary
- confirmed points
- unresolved points
- references

## 10. Decisions

Decisions record what was accepted, rejected, deferred, or superseded.

A task is not complete if its final solution is not represented by a decision or outcome record.

## 11. Artifacts

Artifact references index stage documents such as:

- problem definition
- design document
- contract document
- implementation note
- review report
- verification report
- test report
- risk report
- handoff note
- postmortem

Artifacts inside Master plaintext payload may be encrypted in the repository payload.

Repo-visible public metadata must not leak sensitive artifact content.

## 12. Outcome

Terminal tasks require outcome.

Required fields:

```yaml
outcome:
  result: completed|aborted|superseded|rejected|null
  final_solution: <summary or null>
  changed_files: []
  verification_summary: <summary or null>
  known_limits: []
  followups: []
  promoted_to_knowledge: []
  promoted_to_causal: []
```

Promotion lists are references only. They do not create Knowledge or Causal entries.

## 13. Terminal closure validation

When `status: completed`, Master must validate:

1. `lifecycle.completed_at` is present.
2. `decision_refs` includes a final accepted decision, or `outcome.result: completed` represents accepted outcome.
3. Required stage artifact references are present, or waiver amendment refs explain each missing required artifact.
4. `outcome.verification_summary` is present.
5. `outcome.known_limits` is present, even if empty.
6. A postmortem reference is present.
7. The outcome block is structurally valid.

Failure of this validation means terminal completion must be blocked. Master must not describe this as a mere downgrade.
