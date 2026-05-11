# Test Real Worker Contract

## 1. Purpose

This contract defines request-scoped real Test Worker acceptance for the Test Department.

Phase 20B introduces real nested-Codex Test Workers below the Test Leader. It does not change top-level Master routing.

## 2. Shape

```text
Test Leader
  -> Test Worker per accepted validation route
```

The Test Leader is the only external Test Department boundary.

Master must not directly create Test Workers.

## 3. Model policy

In the current phase:

```text
Test Leader -> gpt-5.5 / high
Test Worker -> gpt-5.5 / high
```

Forbidden:

- `medium` Test Worker;
- fallback;
- silent downgrade;
- worker self-selection of model or reasoning budget.

## 4. Test Worker responsibility

A Test Worker is bound to one validation route.

It must produce:

```yaml
test_worker_output:
  agent_id: <string>
  role_id: test_worker
  route_id: <string>
  run_id: <string>
  route_result: passed|failed|inconclusive|blocked
  command_evidence:
    - command: <string>
      exit_code: <integer>
      stdout_ref: <string>
      stderr_ref: <string>
  observations:
    - <string>
  evidence_refs:
    - <string>
  test_data_refs:
    - <string>
  covered_scope:
    - <string>
  uncovered_scope:
    - <string>
  owner_hint:
    owner_type: group|integration|ambiguous|none
  status: test_worker_report_candidate
  causal_status: scoped_evidence_candidate
```

## 5. Proof rule

Every real Test Worker must leave a proof file.

Missing proof is failure, not skip.

Each proof must record:

```yaml
agent_id: <string>
role_id: test_worker
created_by: test_leader
creation_mechanism: real nested-codex MCP / Codex CLI
requested_model: gpt-5.5
policy_model: gpt-5.5
requested_reasoning_effort: high
policy_reasoning_budget: high
topology_scope: test_route_local_domain
run_id: <string>
route_id: <string>
created_at_utc: <string>
proof_statement: <string>
```

## 6. Boundaries

Test Workers must not:

- modify implementation code;
- push branches;
- open PRs;
- remote merge;
- release;
- deploy;
- promote global causal truth;
- route results directly to Master.

## 7. Production boundary

Real Test Worker acceptance is still not production Test lifecycle closure.

It does not include production CI, durable environment provisioning, external artifact backend, remote branch governance, release authority, or global causal merge.
