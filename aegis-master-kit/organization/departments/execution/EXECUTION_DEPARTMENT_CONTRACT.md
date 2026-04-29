# Execution Department Contract

## 1. Purpose

The Execution Department is responsible for turning admitted executable work into an implementation candidate that can be tested, reviewed, traced, and handed back as a causal candidate.

It is not responsible for final global causal merge, production release, remote push, main-branch merge, or formal external sign-off.

## 2. External role

The department is represented externally by the top-level role:

```text
execution
```

The Execution Leader owns all communication across the department boundary.

Internal Execution Groups, Front Agents, and Back Agents must not be added to the top-level Master route table.

## 3. Top-level route obligations

The Execution Department may receive:

```text
master -> execution
```

for admitted executable work.

The Execution Department may send:

```text
execution -> debate
```

only when implementation planning exposes multiple suitable solution plans with real trade-offs and no complete engineering dominance.

The Execution Department may receive:

```text
debate -> execution
```

for adjudicated route decisions.

The Execution Department sends candidates to Test through:

```text
execution -> test
```

The Execution Department receives evidence-backed feedback through:

```text
test -> execution
```

The Execution Department may report branch-local causal forks, governance blockers, or merge-relevant reasoning through:

```text
execution -> master
```

## 4. Internal structure

```text
Execution Leader
  -> Execution Group 1
       -> Front Agent
       -> Back Agent
  -> Execution Group 2
       -> Front Agent
       -> Back Agent
  -> ...
```

The Leader creates groups based on an objectively justified task split.

Each Execution Group is bound to:

- one independent subtask;
- one group branch or workspace;
- one responsibility scope;
- one Front Agent;
- one Back Agent;
- one lifecycle record.

## 5. Department invariants

### 5.1 Contract-first execution

The Leader must load and preserve applicable contracts before implementation begins.

If cross-module interaction is involved, the relevant interface contract must be frozen before parallel implementation.

### 5.2 No arbitrary splitting

The Leader must not split a task merely because parallelism is desired.

A split is valid only if it is supported by objective engineering structure:

- independent responsibility;
- stable input/output boundaries;
- low conflict between touched files or modules;
- explicit dependencies;
- independent or local validation criteria;
- predictable integration order;
- traceable failure ownership.

### 5.3 Debate is conditional

The Leader must not invoke Debate for every design choice.

Debate is required only when multiple suitable plans exist, each has real strengths and weaknesses, and no plan is clearly dominated by engineering practice or contract constraints.

### 5.4 Execution Group persistence

Execution Groups are not disposable after initial implementation.

They remain responsible until Test feedback is resolved and the Leader either releases them after success or explicitly closes the project phase.

### 5.5 Front/Back separation

The Front Agent implements and locally tests.

The Back Agent independently reviews the implementation, test evidence, contract compliance, and first-principles suitability.

Back Agent approval is required before a group can become ready for Leader integration.

### 5.6 Integration is Leader-owned

Groups do not directly merge into the final integration branch.

The Leader creates an integration branch from the current project branch and merges accepted group branches into it.

### 5.7 Test feedback is mandatory

Test must feed back whether the candidate passes or fails.

Failure feedback triggers mapping to the responsible Execution Group.

Success feedback allows the Leader to release active groups only after preserving responsibility records and final causal output.

### 5.8 Causal handoff

The final Execution result must include a causal chain, not only a list of changed files.

It must explain:

- why the chosen plan was used;
- why task split was valid;
- what each group changed and why;
- what the Back Agent challenged;
- how integration was performed;
- what Test proved;
- what risks and invalidation conditions remain;
- what Master should merge, reject, or review.

## 6. Forbidden behavior

The Execution Department must not:

- invent work outside the admitted task;
- split tasks without an independence proof;
- parallelize across an unstable interface;
- create a group without local validation criteria;
- allow the Front Agent to bypass Back Agent review;
- allow a group to silently change its subtask scope;
- hide integration conflicts;
- map Test failures to arbitrary groups without evidence;
- delete group responsibility records after release;
- treat execution output as global causal truth;
- perform remote push, main merge, release, or external sign-off.
