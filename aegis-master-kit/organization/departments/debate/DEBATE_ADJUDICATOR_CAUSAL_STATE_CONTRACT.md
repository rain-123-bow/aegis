# Debate Adjudicator Causal State Contract

## 1. Purpose

This contract defines the causal state that the Debate Leader must maintain while adjudicating a debate run.

The Leader is not a vote counter. The Leader is the local adjudicator for the Debate Department.

The Leader must continuously update its adjudicator causal state as workers defend, attack, narrow scope, request evidence, or concede.

---

## 2. Required adjudicator state

```yaml
adjudicator_causal_state:
  run_id: <string>
  decision_target: <string>
  current_question: <string>
  candidate_positions:
    - stance_id: <string>
      claim: <string>
      current_status: active|selected_candidate|rejected|scoped|balanced|needs_evidence
  selected_candidate:
    stance_id: <string|null>
    why_currently_strongest: <string>
  rejected_candidates:
    - stance_id: <string>
      decisive_failure: <string>
      reopen_if: <string>
  scoped_candidates:
    - stance_id: <string>
      valid_scope: <string>
      invalid_scope: <string>
      transition_condition: <string>
  unresolved_conflicts:
    - <string>
  decisive_evidence:
    - type: <string>
      ref: <string>
      relevance: <string>
  missing_evidence:
    - <string>
  risk_ranking:
    - stance_id: <string>
      risk_if_wrong: <string>
      risk_grade: high|medium|low
  route_priority:
    - id: <string>
      route_grade: A|B|C|D|E|F
      reason: <string>
  expand_priority:
    - id: <string>
      expand_grade: A|B|C|D
      reason: <string>
  stop_reason: <string>
  developer_decision_required: <boolean>
  developer_decision_reason: causal_equipoise|project_direction_choice|value_tradeoff_not_resolvable_by_evidence|null
```

---

## 3. Adjudication criteria

The Leader must adjudicate by causal strength, using at least:

- evidence quality;
- assumption validity;
- scope precision;
- contract consistency;
- explanatory power;
- implementation feasibility;
- risk if wrong;
- cost and reversibility;
- invalidation clarity;
- downstream action impact.

---

## 4. Stop conditions

The Leader may stop when:

1. one position is causally dominant;
2. positions are valid under distinct scopes;
3. remaining conflict is measurable and must go to Test;
4. remaining conflict belongs to Master governance;
5. evidence is missing and cannot be safely inferred;
6. multiple positions remain in causal equipoise;
7. extra rounds produce no new causal information;
8. continuing would violate constraints.

The stop reason must be recorded.

---

## 5. Equipoise rule

If multiple positions remain balanced, the Leader must not randomly pick one.

The final package must preserve all balanced positions and set:

```yaml
developer_decision_required: true
```

Master must then hand the project-direction decision to the developer.

---

## 6. Boundary to Master

The Debate Leader returns a causal candidate package to Master.

Master may:

- accept a unique, closed, scope-bounded conclusion;
- request Test evidence;
- reject the causal candidate;
- merge it into global causal state if governance rules allow;
- ask the developer to choose when the package marks developer decision required.
