# Execution Real Front/Back Agent Contract

## 1. Purpose

This contract defines the request-scoped real nested-Codex Front/Back agent boundary for the Execution Department.

Phase 19B introduces real agent acceptance below the Execution Leader. It does not change the Master-layer topology.

## 2. Shape

```text
Execution Leader
  -> Execution Group
       -> Front Agent
       -> Back Agent
```

The Execution Leader is the only external Execution Department boundary.

Master must not directly create Front Agents, Back Agents, Execution Groups, or group branches.

## 3. Model policy

In the current phase:

```text
Execution Leader      -> gpt-5.5 / high
Execution Front Agent -> gpt-5.5 / high
Execution Back Agent  -> gpt-5.5 / high
```

Forbidden:

- `medium` Execution Front Agent;
- `medium` Execution Back Agent;
- fallback;
- silent downgrade;
- agent self-selection of model or reasoning budget.

## 4. Front Agent responsibility

A Front Agent is bound to one Execution Group.

It must produce:

```yaml
front_output:
  agent_id: <string>
  role_id: execution_front_agent
  group_id: <string>
  subtask_id: <string>
  implementation_summary: <string>
  touched_files:
    - <repo-relative-path>
  local_test_evidence:
    - command: <string>
      result: pass|fail|not_run
      evidence_ref: <string>
  group_causal_fork:
    statement: <string>
    why: <string>
    evidence:
      - <string>
    scope: <string>
    assumptions:
      - <string>
    status: causal_candidate
  known_limits:
    - <string>
```

The Front Agent must not:

- bypass the Back Agent;
- self-approve its own work;
- push branches;
- open PRs;
- merge to remote;
- release;
- claim global causal truth.

## 5. Back Agent responsibility

A Back Agent is bound to the same Execution Group as the Front Agent it reviews.

It must independently review:

- Front output;
- branch diff;
- touched files;
- local test evidence;
- contract compliance;
- first-principles suitability;
- scope and risk.

It must produce:

```yaml
back_review:
  agent_id: <string>
  role_id: execution_back_agent
  group_id: <string>
  subtask_id: <string>
  reviewed_front_agent_id: <string>
  review_decision: accept|reject|request_changes|request_more_evidence|scope_violation|contract_violation
  review_summary: <string>
  blocking_objections:
    - <string>
  evidence_checked:
    - <string>
  risk_notes:
    - <string>
  status: review_candidate
```

Back Agent approval is required before the group can be considered ready for Leader integration.

## 6. Proof rule

For real acceptance, every Front and Back Agent must leave a proof file.

Missing proof is failure, not skip.

Each proof must record:

```yaml
agent_id: <string>
role_id: execution_front_agent|execution_back_agent
created_by: execution_leader
creation_mechanism: real nested-codex MCP / Codex CLI
requested_model: gpt-5.5
policy_model: gpt-5.5
requested_reasoning_effort: high
policy_reasoning_budget: high
topology_scope: execution_group_local_domain
run_id: <string>
group_id: <string>
subtask_id: <string>
created_at_utc: <string>
proof_statement: <string>
```

## 7. Boundary

Real Front/Back acceptance is still not production Execution lifecycle closure.

It does not include:

- production worker supervision;
- restart/recovery;
- remote branch governance;
- PR creation;
- remote merge;
- release;
- global causal merge.
