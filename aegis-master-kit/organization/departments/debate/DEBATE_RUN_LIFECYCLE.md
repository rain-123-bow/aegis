# Debate Run Lifecycle Contract

## 1. Definition

A debate run is one request-scoped Debate Department activation.

Each run has a unique `debate_run_id` and is independent by default from other runs.

## 2. States

```text
RECEIVED
ADMISSION_CHECK
REJECTED
STANCE_SPLIT
WORKERS_CREATED
TOPOLOGY_READY
ROUND_RUNNING
ADJUDICATION
FINAL_REPORT_READY
RESOURCES_RELEASED
RETURNED
```

## 3. State transitions

### RECEIVED -> ADMISSION_CHECK

The Leader receives a request from an allowed top-level sender.

### ADMISSION_CHECK -> REJECTED

The Leader rejects if debate is not applicable.

A rejection must include a causal reason.

### ADMISSION_CHECK -> STANCE_SPLIT

The Leader accepts only if at least two defensible independent stances can be derived.

### STANCE_SPLIT -> WORKERS_CREATED

The Leader creates one temporary worker per stance.

### WORKERS_CREATED -> TOPOLOGY_READY

The Leader creates a request-scoped internal debate topology.

### TOPOLOGY_READY -> ROUND_RUNNING

The Leader starts round-robin debate and broadcasts the initial transcript.

### ROUND_RUNNING -> ADJUDICATION

The Leader stops debate when a termination condition is met.

### ADJUDICATION -> FINAL_REPORT_READY

The Leader produces a complete causal final report.

### FINAL_REPORT_READY -> RESOURCES_RELEASED

The Leader releases temporary workers, temporary topology, and temporary runtime resources.

### RESOURCES_RELEASED -> RETURNED

The Leader returns the result to the original requester through an allowed top-level route.

## 4. Rejection output

A rejected debate request must include:

```yaml
status: rejected
reason_code: no_independent_stances|insufficient_information|out_of_scope|contract_violation|not_debate_work
why: ...
suggested_next_route: master|execution|test|none
```

## 5. Accepted run metadata

Every accepted run must record:

```yaml
debate_run_id: ...
request_source: master|execution
request_id: ...
accepted_at: ...
stance_count: ...
worker_count: ...
internal_topology: leader_mediated_round_robin_broadcast
termination_policy: ...
```

## 6. Cleanup requirement

A run is incomplete until temporary workers and temporary topology are released or explicitly marked as failed-to-release with reason and recovery instructions.

## 7. Persistence boundary

Persist after a run:

- final causal report;
- stance packets;
- attack summary;
- concession summary;
- evidence references;
- transcript excerpts required for audit.

Do not persist as default long-lived identities:

- workers;
- request-local topology;
- temporary runtime handles;
- temporary process state.
