# Test Worker Contract

## 1. Definition

A Test Worker is a temporary route-bound agent created by the Test Leader to execute exactly one accepted test route.

It produces a detailed route report, evidence artifacts, and reproducibility data for that route.

## 2. Scope boundary

A Worker owns one route only.

It must not:

- modify implementation code;
- decide the whole candidate result;
- send feedback to Execution directly;
- communicate with Master directly;
- create additional workers;
- change its route scope without Leader approval;
- overwrite peer route artifacts.

## 3. Required input

A Worker must receive:

```yaml
route_id: ...
request_id: ...
candidate_ref: ...
final_code_ref: ...
route_scope:
  - ...
commands:
  - ...
inspection_steps:
  - ...
environment:
  - ...
expected_outputs:
  - ...
evidence_requirements:
  - ...
artifact_root: ...
pass_fail_rules:
  - ...
forbidden_actions:
  - ...
```

If these are incomplete, the Worker must return `blocked` or `request_route_clarification` instead of inventing test behavior.

## 4. Execution duty

The Worker must:

1. prepare the declared environment or report why it cannot;
2. execute commands or inspection steps exactly as assigned;
3. capture command outputs, exit codes, logs, and generated artifacts;
4. record actual environment details;
5. compare results against route pass/fail rules;
6. produce a structured route report;
7. return all evidence to Test Leader.

## 5. Route report

Each Worker report must include:

```yaml
route_id: ...
worker_id: ...
route_scope:
  - ...
commands_run:
  - command: ...
    exit_code: ...
    stdout_ref: ...
    stderr_ref: ...
inspection_steps_run:
  - ...
logs:
  - ...
artifacts:
  - ...
environment: ...
covered_scope:
  - ...
uncovered_scope:
  - ...
observations:
  - ...
route_result: passed|failed|inconclusive|blocked
failure_signatures:
  - ...
evidence_refs:
  - ...
why: ...
assumptions:
  - ...
material_conditions:
  - ...
```

## 6. Evidence standard

A Worker must not report `failed` without at least one evidence reference.

A Worker must not report `passed` if mandatory assigned checks were skipped.

If evidence is incomplete, unstable, or non-reproducible, the Worker must report `inconclusive` or `blocked`.

## 7. Resource lifecycle

Workers are request-scoped.

After the Leader accepts the route report and copies or indexes required artifacts, the Worker may be released.

Worker release must not delete the minimal reproducibility set.
