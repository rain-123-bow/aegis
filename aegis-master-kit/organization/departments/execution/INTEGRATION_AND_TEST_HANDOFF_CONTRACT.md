# Integration and Test Handoff Contract

## 1. Purpose

This contract defines how Execution turns group outputs into an implementation candidate and sends it to Test.

## 2. Candidate readiness

Execution may send a candidate to Test only when every included group has Back Agent approval, blocking objections are resolved, group branch ownership is recorded, integration conflicts are resolved and attributed, local validation evidence is recorded, known limitations are documented, changed files are mapped to group ids, and candidate status is `implementation_candidate`.

## 3. Handoff route

Execution submits the candidate to Test through the top-level route:

```text
execution -> test
```

The decision label for this handoff is `send_implementation_candidate_to_test`.

`send_implementation_candidate_to_test` requires:

- integration branch;
- merged group branches;
- group_id -> subtask_id -> branch mapping;
- changed files;
- local tests;
- Back Agent review result;
- known risks;
- expected Test validation scope;
- evidence references.

This is different from `request_test_measurement`.

`request_test_measurement` asks Test to produce measurement evidence before final implementation route selection or before Debate. It is not an implementation candidate handoff and must not be used to send code for validation.

## 4. Handoff payload

```yaml
implementation_candidate:
  decision: send_implementation_candidate_to_test
  task_id: ...
  source_request_id: ...
  integration_branch: ...
  base_branch: ...
  merged_group_branches:
    - group_id: ...
      branch_name: ...
  changed_files:
    - path: ...
      group_id: ...
      change_type: add|modify|delete
      why_changed: ...
  local_tests:
    - group_id: ...
      command: ...
      result: pass|fail|not_run
      evidence_ref: ...
  back_reviews:
    - group_id: ...
      decision: accept|reject|request_changes|request_more_evidence|scope_violation|contract_violation
      evidence_ref: ...
  integration_conflicts:
    - ...
  known_limits:
    - ...
  risk_if_wrong: ...
  expected_test_focus:
    - ...
  evidence_refs:
    - ...
  feedback_mapping_table:
    - file_or_module: ...
      group_id: ...
      subtask_id: ...
  status: implementation_candidate
```

## 5. Measurement request payload

```yaml
measurement_request:
  decision: request_test_measurement
  source_request_id: ...
  required_measurements:
    - ...
  why_needed: ...
  decision_dependency: ...
  evidence_refs:
    - ...
  status: measurement_request
```

## 6. Handoff boundary

The implementation candidate is not a final project result.

Test must validate it and return feedback.

Execution must not bypass Test and send directly to Final Review.
