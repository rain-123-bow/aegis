# Top-Level Route Topology Contract

## 1. Purpose

This contract defines the first-layer communication topology between the Master and the top-level department leaders.

It does not define department internals.

It defines only the directed communication graph visible at the Master layer.

## 2. Top-level roles

The topology contains five logical roles:

| Role | Meaning |
| --- | --- |
| `master` | Top-level governance hub and final causal merge authority. |
| `debate` | Adversarial reasoning and adjudication module for ambiguous or multi-solution problems. |
| `execution` | Implementation module that produces candidate work and local causal fork branches. |
| `test` | System-level testing module that produces evidence-backed verification feedback. |
| `final_review` | Final review gate before results return to the Master. |

## 3. Router-side authoritative route table

The router must store an authoritative directed route table.

A message is valid only if its `sender -> receiver` edge exists in that table.

Same-domain visibility is not sufficient permission. An agent can be visible and still not be a valid receiver for a given sender.

## 4. Role-local route table

Every role must also carry a local route table.

The local route table must specify:

- outgoing roles;
- incoming roles;
- single-direction edges;
- protocol-level bidirectional pairs built from two directed edges.

A role must not invent a route that is absent from its local route table.

## 5. Directed edges

The first-layer topology contains exactly these directed edges in v1:

| Edge | From | To | Reason |
| --- | --- | --- | --- |
| `E001` | `master` | `debate` | The Master starts adversarial reasoning when ambiguity, risk, solution conflict, or causal incompleteness requires it. |
| `E002` | `master` | `execution` | The Master sends an admitted and executable task to the execution module. |
| `E003` | `debate` | `master` | The debate module returns debate results, conflict surfaces, adjudication material, or causal proposals to the Master. |
| `E004` | `execution` | `test` | The execution module submits candidate work to system-level testing. |
| `E005` | `test` | `final_review` | The test module sends evidence-backed test conclusions to final review. |
| `E006` | `final_review` | `master` | Final review sends the final review result back to the Master. |
| `E007` | `test` | `execution` | The test module sends evidence-backed failure feedback to execution for correction. |
| `E008` | `execution` | `debate` | Execution requests debate when implementation exposes multiple valid solution paths or causal uncertainty. |
| `E009` | `debate` | `execution` | Debate sends the selected adjudicated route back to execution. |
| `E010` | `execution` | `master` | Execution submits causal fork branches or execution escalation material to the Master for merge or governance. |

No other first-layer edge is valid in v1.

## 6. Protocol-level bidirectional pairs

The graph has protocol-level loops, but these loops are still made of directed edges.

| Pair | Directed edges | Protocol meaning |
| --- | --- | --- |
| `master <-> debate` | `master -> debate`, `debate -> master` | Master starts debate; debate returns structured results to Master. |
| `execution <-> debate` | `execution -> debate`, `debate -> execution` | Execution requests adjudication; debate returns a selected route. |
| `execution <-> test` | `execution -> test`, `test -> execution` | Execution submits candidate work; test returns evidence-backed failure feedback when needed. |

These pairs must not be treated as unrestricted chat channels.

## 7. Evidence and causal constraints

`test -> execution` feedback must contain evidence or a path to evidence. It must not be a bare opinion.

`execution -> debate` is conditional. It is triggered only when execution faces multiple plausible implementation routes, unresolved design conflict, contract ambiguity, or causal incompleteness.

`debate -> execution` must return a route decision with a reason structure sufficient for later causal admission.

`execution -> master` is not a bypass of testing or final review. Its primary purpose is submitting execution-generated causal forks, governance blockers, or merge-relevant reasoning state to the Master.

## 8. Causal fork rule

Execution may produce a branch-local causal fork.

A branch-local causal fork is not global causal truth.

Execution must send the causal fork to the Master through `execution -> master`.

Only the Master or the configured adjudication authority may merge, fuse, reject, or supersede a causal fork into the global causal baseline.

## 9. Router non-semantic rule

The router enforces identity and directed route validity.

The router must not evaluate the content of README files, attachments, causal proposals, test evidence, or debate results.
