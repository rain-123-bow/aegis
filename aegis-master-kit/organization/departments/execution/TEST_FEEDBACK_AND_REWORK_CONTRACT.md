# Test Feedback and Rework Contract

## 1. Purpose

This contract defines how Execution handles Test feedback.

Test feedback is mandatory whether the candidate passes or fails.

## Test Feedback Decision Labels

- test_passed:
  Test feedback proves the integration candidate passed the declared validation scope.
  Execution Leader may release active Execution Groups only after preserving responsibility records and producing the final execution causal chain.

- test_failed_mapped:
  Test feedback has evidence and maps clearly to a group, subtask, branch, file, or integration owner.
  Use map_to_group or map_to_integration_owner.

- test_failed_missing_evidence:
  Test feedback claims failure but lacks concrete evidence.
  Use request_failure_evidence.

- test_failed_ambiguous_owner:
  Test feedback has evidence but does not yet prove responsible owner.
  Use triage_required.

- map_to_group:
  Use when failure clearly maps to an Execution Group's responsibility scope.

- map_to_integration_owner:
  Use when failure was introduced by Leader-owned integration branch, merge resolution, or integration glue.

- rework_required:
  Use after owner mapping when a responsible group or integration owner must fix the issue.

Test must give feedback whether pass or fail.

Success feedback is still evidence and must be recorded.

Failure feedback must be evidence-backed before assigning rework.

Group release after success releases active identity/workspace only; it does not delete responsibility records.

## 2. Feedback route

Test returns feedback through:

```text
test -> execution
```

Feedback must include evidence or evidence references.

## 3. Failure feedback

Failure feedback must be mapped before rework.

If mapping is impossible, the Leader must classify the failure as integration-level, split invalidity, insufficient test evidence, or unknown requiring investigation.

It must not randomly assign rework.

## 4. Rework rule

The original responsible Execution Group handles the fix unless the Leader records a justified reassignment.

The Back Agent must review the fix before reintegration.

## 5. Success feedback

Success feedback must still be processed.

The Leader may release groups only after confirming all group scopes are covered or uncovered areas are explicitly accepted, no unresolved group objection remains, no Test failure remains open, final execution causal chain is produced, and responsibility records are preserved.

## 6. Release after success

Group release means deactivating runtime agents/workspaces.

It does not mean deleting group responsibility records, branch records, review reports, test feedback, rework history, or causal chain.

## 7. Final handoff after success

After success feedback and group release, the Execution Leader sends the final execution causal candidate to Master through:

```text
execution -> master
```

This handoff is not a global causal merge. Master remains the default merge authority.
