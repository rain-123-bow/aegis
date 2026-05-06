# Resource Policy Reference Contract

## 1. Purpose

This contract defines how Final Review refers to model and reasoning-budget policy without creating that policy file.

The concrete root policy file is intentionally out of scope for this patch.

## 2. Separation of concerns

Final Review contract owns:

- required capability class;
- fail-fast behavior when resource policy is not satisfied;
- audit fields proving which resource policy was used.

Root model/reasoning budget policy owns:

- concrete model names;
- exact reasoning budget values;
- fallback rules;
- role-to-profile mapping.

## 3. Required profile

Final Review must resolve:

```text
final_review_leader
```

from the root resource policy when it exists.

## 4. Required capability

The required capability is:

```yaml
required_model_class: highest_available_reasoning_model
reasoning_budget: maximum_available
parallel_internal_workers: forbidden
```

This file does not name a concrete model.

## 5. Missing or insufficient policy behavior

If the root policy is missing, unavailable, lower than required, or fallback would reduce review strength, Final Review must return:

```yaml
decision: blocked_resource_policy
resource_policy:
  status: missing|unavailable|insufficient|fallback_forbidden
```

## Pre-review precedence

Resource policy resolution happens before any substantive Final Review.

If the required profile is missing, unavailable, insufficient, or fallback is forbidden, Final Review must return:

```yaml
decision: blocked_resource_policy
target: master
resource_policy:
  required_profile: final_review_leader
  status: missing|unavailable|insufficient|fallback_forbidden
```

Final Review must not continue to:

- object consistency review;
- Test evidence review;
- Execution evidence review;
- Debate consistency review;
- acceptance decision.

Resource policy failure is not `request_more_evidence_via_master`.

## 6. Audit fields

Every Final Review result must include:

```yaml
resource_policy:
  policy_ref: ...
  required_profile: final_review_leader
  resolved_profile: ...
  reasoning_budget: maximum|unknown
  fallback_used: false|true
  status: satisfied|missing|unavailable|insufficient|fallback_forbidden
```

## 7. Forbidden behavior

Final Review must not choose its own concrete model without policy, silently downgrade, use fallback without recording it, accept when fallback is forbidden, or use multiple parallel reviewers to compensate for lower reasoning strength.

Final Review must not:

- continue review after resource policy failure;
- convert resource policy failure into ordinary missing evidence;
- accept with `resource_policy.status != satisfied`;
- compensate for missing required resource by creating parallel weaker reviewers.
