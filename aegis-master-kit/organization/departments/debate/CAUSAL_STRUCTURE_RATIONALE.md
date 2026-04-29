# Why Debate Must Preserve Causal Structure Instead of Only Conclusions

## 1. Core rule

The Debate Department must preserve causal structure because reasoning results are conditional, while many objective facts appear materially stable.

A conclusion without its cause can be mistaken for an unconditional objective fact.

That is unacceptable for an AI organization that must survive context loss, session changes, role handoff, hardware changes, and project evolution.

## 2. Objective reality vs reasoning result

Some objective facts or physical principles are hard to overturn under the same universe-level conditions.

For example, a physical principle such as the invariance of light speed is not normally treated as a project-local conclusion that disappears when a local engineering condition changes.

Engineering reasoning results are different.

A reasoning result is usually true only because certain concrete conditions hold:

- hardware capability;
- resource budget;
- deployment environment;
- customer constraint;
- interface contract;
- measured evidence;
- safety requirement;
- cost boundary;
- current implementation structure.

When those material conditions change, the reasoning result may become false, irrelevant, too broad, or incomplete.

## 3. The danger of conclusion-only storage

A conclusion-only record has this form:

```text
CPU usage must not exceed 60%.
```

This representation looks similar to a static fact or unconditional rule.

It hides the conditions that made it true.

A later agent may inherit it without knowing whether it is:

- a physical constraint;
- a customer rule;
- a safety limit;
- a temporary performance workaround;
- a platform-specific compromise;
- a historical conclusion that should now be invalidated.

The result is stale rule preservation.

## 4. The causal version

The correct representation is causal:

```text
Because the current chip is weak and CPU usage above 60% would reduce scheduling margin for critical tasks, CPU usage must not exceed 60% on the current platform.
```

This preserves:

```text
condition: current chip is weak
mechanism: high CPU usage reduces critical scheduling margin
scope: current platform
conclusion: CPU usage must not exceed 60%
invalidation condition: chip, scheduling margin, workload, or resource policy changes
```

Now the system knows how to reason when the chip changes.

If a stronger chip is introduced, the condition `current chip is weak` may no longer hold. The old conclusion is not automatically carried forward. It must be rechecked, narrowed, superseded, or invalidated.

## 5. Why this matters for Debate

The Debate Department exists exactly for project-direction decisions.

Its outputs may decide architecture, contracts, task routing, module boundaries, implementation strategy, or whether evidence is sufficient.

If the Debate Department stores only conclusions, it creates hidden authoritarian facts:

```text
Use solution A.
Do not use solution B.
CPU limit is 60%.
This contract must stay unchanged.
This module should own this responsibility.
```

Later agents cannot know why these statements were produced or whether they still hold.

If the Debate Department stores causal structure, later agents can safely inherit, audit, and modify the result:

```text
Condition unchanged -> inherit.
Condition changed -> re-evaluate.
Evidence contradicted -> reopen.
Scope too broad -> narrow.
Alternative assumption now holds -> reconsider rejected alternative.
```

## 6. Material-condition invalidation rule

Every Debate final result must include invalidation conditions.

A result must answer:

```text
What material condition made this conclusion true?
What concrete change would make this conclusion questionable?
What new evidence would reopen the debate?
What scope boundary prevents overuse?
```

Without these fields, the result is not safe for context-free handoff.

## 7. Relation to materialist dialectics

This rule follows a materialist and dialectical view of reasoning:

- conclusions are not isolated entities;
- conclusions arise from concrete conditions and contradictions;
- when material conditions change, the validity of a conclusion may change;
- practice, evidence, and conditions determine whether a conclusion remains active, becomes scoped, or is overturned.

In engineering terms:

```text
A conclusion is maintained by its premises, evidence, scope, and material conditions.
When those supports change, the conclusion must be revalidated.
```

This is not philosophical decoration. It is a system safety rule.

## 8. Required causal fields

Therefore Debate outputs must preserve at least:

- statement;
- why;
- evidence;
- scope;
- assumptions;
- material conditions;
- rejected alternatives and why they failed;
- scoped alternatives and where they still hold;
- risk if wrong;
- invalidation conditions;
- depends_on / invalidates / supersedes relations;
- confidence and status;
- version context.

## 9. Forbidden reduction

The following output is invalid:

```text
Conclusion: Choose A.
```

The following is valid:

```text
Choose A because it satisfies the current contract, minimizes integration risk, and preserves the agreed ownership boundary under the current platform constraints. Reject B because it violates the caller-owned memory assumption. Reject C because it is valid only if the runtime owns resource scheduling, which is outside the current scope. Reopen this result if the ownership contract changes or if the runtime is explicitly granted scheduling authority.
```

## 10. Final compression

```text
Objective facts are stabilized by reality.
Reasoning conclusions are stabilized by their conditions.
Aegis stores causal structure so condition changes can invalidate, narrow, or reopen conclusions.
```
