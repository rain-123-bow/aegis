# Test Evidence and Retention Contract

## 1. Purpose

The Test Department must preserve enough evidence to make the current task's testing reproducible and inspectable.

The goal is not to retain every raw byte forever. The goal is to retain the minimum structure needed to reproduce, audit, or challenge the test result later.

## 2. Evidence classes

Evidence may include:

- test plan;
- route definitions;
- commands and inspection steps;
- command outputs;
- logs;
- generated files;
- screenshots or binary artifacts when relevant;
- environment metadata;
- branch/commit/candidate references;
- worker route reports;
- final Test Leader report;
- artifact manifest.

## 3. Minimal reproducibility set

The minimal retained set must include:

```yaml
test_plan_ref: ...
routes:
  - route_id: ...
    commands_or_steps:
      - ...
    expected_results:
      - ...
    actual_result_summary: ...
environment:
  os: ...
  runtime: ...
  dependencies:
    - ...
input_refs:
  base_branch: ...
  integration_branch: ...
  commit: ...
  implementation_candidate_ref: ...
  final_code_ref: ...
evidence_refs:
  - ...
artifact_manifest_ref: ...
cleanup_policy: ...
```

If raw artifacts are pruned, the manifest must state what was pruned, when, why, and which summary remains.

## 4. Artifact manifest

Every artifact manifest must include:

```yaml
artifact_id: ...
route_id: ...
path_or_uri: ...
artifact_type: log|stdout|stderr|report|data|screenshot|binary|other
producer: test_leader|test_worker
created_at: ...
retention: retained|temporary|pruned
semantic_role: evidence|debug_context|repro_input|repro_output
checksum: optional
```

## 5. Evidence integrity

A report must not cite an artifact that is neither retained nor described in the manifest.

If an artifact is temporary, the report must preserve enough summary information to avoid making the final result unverifiable after cleanup.

## 6. Evidence-state distinction

Evidence retention must preserve enough information to distinguish:

1. candidate failure;
2. inconclusive evidence;
3. blocked execution of the test route;
4. governance blocker.

A failure record must identify the evidence proving candidate behavior or contract violation.

An inconclusive record must identify what evidence was missing, unstable, contradictory, or insufficient.

A blocked record must identify the missing prerequisite or blocking condition.

A governance blocker record must identify the policy, authority boundary, or responsibility boundary that would be violated.

## 7. Retention boundary

Retaining test evidence does not promote it into Archive, Knowledge, or Causal stores by itself.

Archive, Knowledge, and Causal admission require their own governance process.

Test evidence may later be promoted as source material, but it is not automatically global truth.

## 8. Cleanup rule

Cleanup may remove large raw artifacts only after:

1. the final test report exists;
2. the artifact manifest exists;
3. the minimal reproducibility set exists;
4. any required handoff to Execution or Final Review has copied or referenced the needed material.
