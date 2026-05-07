# Debate Department Contract

## 1. Definition

The Debate Department is the organization unit responsible for adversarial reasoning and adjudication when a request has multiple defensible solution paths, unresolved causal conflict, significant ambiguity, or project-direction impact.

The Department is represented externally by the Debate Leader. Internal Debate Workers are created per debate run and released after adjudication.

## 2. Scope

This contract applies to department-internal behavior below the top-level `debate` role.

It does not redefine the Master-layer route topology. At the Master layer, the Debate Department still appears as a single role named `debate`.

## 3. Department invariants

### 3.1 Leader is the only external boundary

Only the Debate Leader may communicate with top-level Master or other top-level department leaders.

Internal workers must not directly communicate through Master-layer routes.

### 3.2 Workers are request-scoped

A Debate Worker exists only for one debate run.

A worker must be bound to one stance. It must not become a persistent persona, persistent expert, or reusable long-lived department member.

### 3.3 Requests are independent by default

Each debate request starts with no inherited worker lineup.

Previous debate outputs may be referenced as evidence or prior causal candidates only if provided through governed context, but previous workers themselves do not persist.

### 3.4 Debate requires at least two defensible independent stances

The Debate Leader must refuse a request if it cannot derive at least two independent, defensible, and materially distinct stances.

The refusal must explain why adversarial debate is not applicable and suggest the correct next route when possible.

### 3.5 Debate is not group chat

The Department must not allow uncontrolled free-form multi-agent chat.

The internal communication model is leader-mediated round-robin broadcast. Each worker sees the shared transcript, but speaking turns are controlled by the Leader.

### 3.6 Leader is the adjudicator

The Debate Leader is responsible for deciding when the debate has produced enough information and must stop.

The Leader must prevent infinite debate.

### 3.7 Final output must be causal, not merely conclusive

The Department output must preserve a complete causal structure:

- why the selected position won;
- why rejected positions failed;
- which positions remain valid only under limited scope;
- what assumptions and evidence support the decision;
- what condition changes would invalidate the decision;
- what action should be taken next.


### 3.8 Two-layer Debate shape

The Debate Department has exactly two internal layers in the current phase:

```text
Debate Leader
  -> Debate Worker per valid stance
```

The following role splits are forbidden unless a later contract version explicitly adds them:

- independent evidence collector agent;
- independent scope checker agent;
- independent researcher agent;
- persistent expert persona;
- any worker not bound to exactly one stance.

Information collection, defense, attack, answer, scope narrowing, and concession are duties of the stance-bound Debate Worker itself.

### 3.9 Model and reasoning-budget policy

All active Debate Department reasoning agents use the high profile in the current phase:

```text
Debate Leader  -> gpt-5.5 / high
Debate Worker  -> gpt-5.5 / high
```

Medium Debate Workers, fallback, and silent downgrade are forbidden.

### 3.10 Real nested-Codex worker acceptance

In-process demo workers may be used only for deterministic unit tests.

A Debate run cannot be accepted as real nested-Codex closure unless the Debate Leader creates real nested-Codex Debate Workers for every valid stance and each worker leaves an auditable proof file.

If any required worker cannot be created, the Debate Leader must fail fast for that run. It must not silently replace the failed real worker with an in-process demo worker.

### 3.11 Complete causal retention

Every completed Debate run must preserve:

- each worker's local causal state;
- each worker's route priority and expand priority;
- the adjudicator causal state maintained by the Debate Leader;
- selected, rejected, scoped, and unresolved positions;
- attacks, concessions, and scope-narrowing history;
- evidence references and evidence gaps;
- invalidation conditions;
- developer decision requirement when causal equipoise remains.

The final result must be delivered as a causal package, not a bare conclusion.

## 4. Accepted request classes

The Department may accept a request when at least one condition is true:

1. Multiple plausible solutions exist and choosing one affects project direction.
2. A design conflict cannot be resolved by simple contract lookup.
3. A causal conclusion is uncertain and requires adversarial pressure.
4. Execution discovers multiple implementation routes with meaningful trade-offs.
5. Master needs conflict surfaces before making a governance decision.

## 5. Rejection classes

The Department must reject or downgrade a request when:

1. Only one defensible stance exists.
2. The request is a simple lookup, formatting task, or deterministic execution task.
3. The request lacks enough information to form any defensible stance.
4. The request asks workers to bypass system contracts.
5. The request attempts to treat debate as a way to manufacture evidence.
6. The request would require production authority, external sign-off, push/merge/release, or other critical responsibility actions.

## 6. Worker stance model

Each worker receives one stance packet containing:

- stance id;
- claim;
- why the claim may be true;
- initial evidence;
- assumptions;
- scope;
- risk if wrong;
- expected attack targets.

Workers may refine their stance but must not silently switch to a different stance.

If a worker is convinced that its stance is invalid, it must concede with a reasoned failure report.

## 7. Debate process model

A debate run contains rounds.

Each round has an explicit speaker order. During its turn, a worker may:

- defend its stance;
- attack another stance;
- answer attacks;
- narrow its scope;
- concede if defeated;
- request evidence clarification from the Leader.

The Leader may broadcast shared transcript updates after each turn or each round.

## 8. Termination model

The Leader may terminate debate when:

1. A position is clearly selected.
2. Multiple positions are accepted under different scopes.
3. Evidence is insufficient and further debate cannot resolve the issue.
4. All but one worker have conceded or been scoped out.
5. Additional rounds produce no new causal information.
6. A configured round, token, time, or cost limit is reached.
7. Continuing debate would violate system constraints.

## 9. Resource model

After termination, the Leader must release:

- temporary worker identities;
- temporary debate domain or internal topology;
- temporary mailbucket resources when safe;
- nested-codex processes or handles in runtime implementations.

The Leader must preserve:

- final causal report;
- essential transcript excerpts;
- stance packets;
- attack/concession summary;
- evidence references;
- unresolved risks.

## 10. Output model

The Department output must be fit for a later Master or department to understand without original chat context.

The final output must include at least:

- request id;
- request source;
- accepted/rejected status;
- stances considered;
- selected stance or scoped outcome;
- why selected;
- why alternatives failed or were scoped;
- material assumptions;
- evidence references;
- invalidation conditions;
- risk if wrong;
- next action recommendation;
- causal fork candidate for Master-level merge.

## 11. Boundary to global causal truth

The Debate Department can produce a causal candidate or branch-local causal fork.

It cannot unilaterally merge its result into global causal truth unless explicitly configured as the adjudication authority for that scope.

By default, final merge authority remains with the Master or configured adjudication authority.
