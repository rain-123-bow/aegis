# Decision-to-Debate Rules

## 1. Purpose

The Execution Leader must know when to decide directly and when to ask the Debate Department for adjudication.

Debate is powerful but expensive. It must not be used for deterministic engineering choices.

## 2. Debate trigger

The Leader must request Debate only when all conditions hold:

1. Multiple implementation plans exist.
2. Each remaining plan is valid under current contracts.
3. Each remaining plan has meaningful advantages and disadvantages.
4. Plans affect architecture, ownership, contract, risk, or project direction.
5. No plan has complete engineering dominance.
6. Missing evidence cannot first be resolved by a direct measurement request.

`request_debate` is not valid when a decisive missing fact can first be measured by Test, benchmark, log capture, experiment, or validation plan. In that case the correct label is `request_test_measurement`.

## 3. Direct decision allowed

The Leader may decide directly when:

- only one plan satisfies constraints;
- one plan dominates others by engineering practice;
- alternatives violate frozen contracts;
- alternatives are only stylistic variants;
- cost/risk difference is objectively decisive;
- the choice is a deterministic contract lookup.

If one plan has complete engineering dominance, do not request Debate. Choose the dominant plan and record why.

If an option violates frozen contracts, it is not a Debate candidate.

## 4. Complete gap rule

A complete gap exists when one plan is clearly and broadly superior under the accepted constraints.

When a complete gap exists, Debate is not required.

The Leader must still record why the decision was direct.

## 5. Measurement before Debate

If missing evidence is measurable and decisive, use `request_test_measurement` before Debate.

The measurement request must include:

```yaml
decision: request_test_measurement
required_measurements:
  - ...
why_needed: ...
decision_dependency: ...
```

## 6. Debate request payload

When Debate is required, the Leader sends:

```yaml
debate_request:
  source: execution
  decision_problem: ...
  candidate_plans:
    - plan_id: ...
      claim: ...
      why_it_may_work: ...
      strengths:
        - ...
      weaknesses:
        - ...
      assumptions:
        - ...
      scope: ...
      risk_if_wrong: ...
  constraints:
    - ...
  evidence_refs:
    - ...
  required_output: adjudicated_route_with_causal_chain
```

## 7. After Debate returns

The Leader must:

- accept the adjudicated route unless a new contract conflict or evidence contradiction appears;
- bind the decision into the implementation plan;
- reference the Debate causal chain in the execution final causal report;
- not re-litigate the same decision without new material conditions.
