# Knowledge Freshness Contract

## 1. Why freshness exists

Some facts remain stable for long periods. Others become stale when environment, customer requirements, dependencies, platform, or release branches change.

Knowledge must support explicit freshness and revalidation metadata.

## 2. Freshness fields

Entries may include:

- last_verified_at
- expires_at
- revalidate_on
- freshness_status

Allowed freshness_status values:

- fresh
- stale
- unknown
- not_applicable

## 3. Revalidation triggers

Common triggers:

- environment_change
- hardware_change
- OS_upgrade
- dependency_upgrade
- customer_requirement_change
- release_branch_change
- performance_budget_change
- integration_failure
- test_failure

## 4. Stale entry rule

Stale does not automatically mean false.

A stale entry should be treated as requiring revalidation before being used as a current planning premise.

## 5. Master responsibility

Master must decide whether stale Knowledge can be used, must be refreshed, or must be downgraded to tentative.
