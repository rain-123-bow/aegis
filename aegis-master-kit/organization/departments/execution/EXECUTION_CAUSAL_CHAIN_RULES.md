# Execution Causal Chain Rules

## 1. Purpose

Execution output must be understandable without the original conversation context.

The final Execution report must be a causal candidate, not only a patch summary.

## 2. Minimum causal chain structure

```yaml
execution_causal_chain:
  chain_id: ...
  source_request_id: ...
  selected_plan: ...
  why_this_plan: ...
  debate_reference:
    used: true|false
    causal_chain_ref: ...
    selected_route: ...
  nodes:
    - id: ...
      type: request|plan|direct_decision|debate_decision|subtask_split|implementation|review|integration|test_feedback|risk|invalidation_condition|conclusion
      statement: ...
      why: ...
      evidence_refs:
        - ...
      group_id: ...
      branch_name: ...
      confidence: high|medium|low
  edges:
    - from: ...
      to: ...
      relation: supports|depends_on|invalidates|narrows_scope|requires_rework|proves|supports_release|reopens_if
      why: ...
  selected_path:
    - ...
  group_paths:
    - group_id: ...
      node_ids:
        - ...
  rejected_or_unused_plans:
    - plan_id: ...
      why_not_used: ...
      reopen_if: ...
  invalidation_entrypoints:
    - condition_node_id: ...
      reopens_node_ids:
        - ...
  final_status: test_passed|needs_rework|blocked|cancelled
  status: causal_candidate
```

## 3. Required content after test success

After Test passes, the chain must include selected implementation plan, subtask split proof, each group result, Back Agent review result, integration result, Test success feedback, group release decision, remaining risks, invalidation conditions, and recommendation to Master.

## 4. Required content after test failure

After Test fails, the chain must include failure evidence, mapping from failure to group(s), rework decision, current status, missing evidence, and next action.

## 5. No bare implementation summary

The following is invalid:

```text
Implemented feature X. Tests passed.
```

The following is valid:

```text
Implemented feature X by splitting the task into A/B because their interfaces were frozen and their file ownership did not overlap. Group A changed files [...] because [...]. Group B changed files [...] because [...]. Back Agent challenged [...], resolved by [...]. Integration branch [...] merged both without conflict. Test feedback [...] passed scope [...]. Reopen if contract [...] changes or new logs contradict [...].
```

## 6. Boundary to global causal truth

Execution causal chains are causal candidates or branch-local causal forks.

They are not automatically global causal truth.

Master or the configured adjudication authority performs global causal merge.
