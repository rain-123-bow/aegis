# Test Plan and Route Split Contract

## 1. Purpose

This contract prevents the Test Department from degenerating into ad hoc command execution.

Testing must begin with a reproducible plan and only then split into routes.

## 2. Test plan minimum fields

```yaml
plan_id: ...
request_id: ...
implementation_candidate_ref: ...
final_code_ref: ...
objective: ...
validation_scope:
  - ...
success_criteria_map:
  criterion_id: route_id|manual_review|not_testable_here
changed_scope:
  - ...
known_risks:
  - ...
mandatory_routes:
  - ...
optional_routes:
  - ...
environment_assumptions:
  - ...
artifact_policy: ...
pass_policy: ...
failure_policy: ...
uncovered_scope_policy: ...
```

## 3. Route categories

The Leader may use route categories such as:

- contract/schema validation;
- unit or local behavior validation;
- integration behavior validation;
- regression validation;
- security/boundary validation;
- performance/resource validation;
- reproducibility validation;
- manual inspection route when automation is not sufficient.

A category does not automatically justify a route. The route must map to task scope and success criteria.

## 4. Route independence proof

Every parallel route must declare:

```yaml
independence_reason: ...
shared_state:
  - ...
isolation_rule: ...
order_dependency: none|before:<route_id>|after:<route_id>
conflict_if_parallel: ...
```

If two routes share mutable state and no isolation rule exists, they must not run in parallel.

## 5. Mandatory versus optional routes

A mandatory route is required for the final result.

An optional route may add confidence or risk insight, but its absence must not be hidden.

If an optional route finds a blocker, the final result cannot remain unconditional `passed`.

## 6. Pass policy

`passed` requires:

1. all mandatory routes passed;
2. declared validation scope is covered;
3. uncovered scope is empty or non-material;
4. no unresolved blocker remains;
5. route reports contain sufficient evidence refs;
6. reproducibility metadata exists.

`passed_with_scope_limit` requires:

1. all mandatory routes that were executed passed;
2. uncovered or untested scope is explicit;
3. Final Review can inspect the limitation;
4. the limitation does not contradict the claimed scope.

## 7. Failure policy

A failed route must preserve:

- failing command or inspection step;
- observed output;
- expected output;
- artifact refs;
- environment details;
- reproduction instructions;
- affected scope;
- owner hint if safely inferable.

Failure policy must return evidence to Execution Leader, not directly to groups.

## 8. Inconclusive policy

Use `inconclusive` when:

- evidence conflicts;
- environment is unstable;
- results cannot be reproduced;
- logs are missing;
- the route was partially executed;
- the candidate reference is inconsistent;
- success criteria cannot be measured with available data.
