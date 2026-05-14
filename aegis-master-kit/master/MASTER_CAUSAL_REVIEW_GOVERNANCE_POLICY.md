# Master Causal Review Governance Policy

## 1. Purpose

Phase 22B defines the Master-owned high-budget causal review process after Phase 22A has structurally staged a `causal_candidate`.

Phase 22B answers:

```text
Can this staged causal_candidate become a canonical merge candidate?
```

It does **not** answer by writing the Causal Store. It produces a `causal_review_decision`.

Phase 22B is not:

- production Causal Store write closure
- canonical/global causal truth merge
- production storage backend
- a fifth department
- a long-lived Causal Review Agent
- a replacement for developer responsibility

## 2. Required input state

The Master causal review must combine:

```text
staged causal_candidate
+ relevant Knowledge context
+ relevant active/tentative Causal context
+ current constraints
+ evidence and uncertainty state
```

The review is invalid if it only checks candidate shape and ignores existing Knowledge and Causal state.

The review must consider that the objective world and project constraints can change over time. Older Causal facts may be narrowed, superseded, invalidated, or reopened by new constraints.

## 3. Required review gates

Master must evaluate at least these gates:

1. **Candidate gate**
   - candidate was staged by Phase 22A;
   - candidate remains a candidate, not global truth.

2. **Structure gate**
   - statement, why, evidence, scope, assumptions, and source origin exist.

3. **Knowledge context gate**
   - relevant Knowledge is loaded or the absence of relevant Knowledge is explicitly justified.

4. **Causal context gate**
   - relevant active/tentative Causal facts are loaded or their absence is explicitly justified.

5. **Evidence gate**
   - evidence actually supports `why`, not only `statement`.

6. **Scope gate**
   - scope is not overbroad;
   - production/global overclaims are rejected or narrowed.

7. **Conflict gate**
   - candidate is checked against existing active/tentative Causal facts;
   - conflicting facts cannot silently coexist under the same version context and scope.

8. **Dependency / supersession / invalidation gate**
   - depends_on, supersedes, and invalidates references must be explicit when used.

9. **Confidence gate**
   - decisive acceptance requires high-confidence support when the conclusion affects project direction;
   - high-confidence support may be statistical, deterministic_proof, contract_proven, test_evidence_backed, or static_analysis_backed;
   - heuristic, qualitative, or unknown confidence must not be used as decisive high-confidence support.

10. **Responsibility gate**
    - when high-confidence conclusion is not available, Master must escalate to Developer instead of taking decisive responsibility.

## 4. Allowed decisions

```text
stage_canonical_merge_candidate
stage_scope_limited_merge_candidate
stage_supersession_candidate
stage_invalidation_candidate
reject_candidate
needs_more_evidence
needs_debate
developer_decision_required
reject_direct_merge_or_store_write
```

All decisions are still review artifacts.

No Phase 22B decision performs canonical/global causal merge.

## 5. High-confidence acceptance rule

Master may stage a canonical merge candidate only when:

```text
master_confidence.type in {
  statistical,
  deterministic_proof,
  contract_proven,
  test_evidence_backed,
  static_analysis_backed
}
and the confidence entry must carry sufficient supporting evidence references.
For statistical confidence, value must also satisfy the configured threshold.
no unresolved conflict exists
scope is valid
candidate evidence supports the causal why
Knowledge and Causal context were considered
```

If the review uses heuristic or qualitative confidence, the output must not be represented as a high-confidence supported conclusion.

## 6. Confidence source types

Phase 22B recognizes these confidence source types:

- statistical:
  Data-backed probability or confidence interval. Requires numeric value and threshold.
- deterministic_proof:
  Deterministic proof, invariant proof, or exhaustive mechanical check.
- contract_proven:
  Directly derived from explicit Aegis contract / policy text.
- test_evidence_backed:
  Supported by passed tests, CLI validation, compile checks, or reproducible verification artifacts.
- static_analysis_backed:
  Supported by static analysis, schema validation, or diff/topology inspection.
- heuristic:
  Reasoned estimate only. Must not satisfy decisive high-confidence gate.
- qualitative:
  Non-numeric qualitative judgment. Must not satisfy decisive high-confidence gate.
- unknown:
  Missing or unspecified confidence. Must not satisfy decisive high-confidence gate.

Statistical probability must not be fabricated from heuristic reasoning.

## 7. Developer decision escalation

When Master cannot reach a high-confidence supported conclusion, and the decision affects project direction or responsibility, Master must output:

```text
developer_decision_required
```

The output must include a developer decision package:

```text
- staged causal candidate
- relevant Knowledge context used
- relevant existing Causal context used
- conflicts / supersession / invalidation analysis
- multiple possible conclusions
- probability or confidence for each conclusion
- whether probabilities are statistical or heuristic
- evidence and assumptions for each conclusion
- risk_if_wrong for each conclusion
- Master recommendation, if any
- reason why Master cannot own the decisive conclusion
```

If the system cannot construct this package, it must output `needs_more_evidence`.

## 8. Archive requirement for developer decision

Whenever `developer_decision_required` is emitted, the event must be recorded as an Archive candidate.

The Archive candidate must record:

```text
- candidate reviewed
- uncertainty reason
- alternatives presented
- probability / confidence package
- developer decision required
- responsibility boundary
- follow-up required after developer decision
```

Archive records what happened. It does not produce truth.

## 9. Master responsibility boundary

Master owns the review process.

Master does not own real-world decisive responsibility when high-confidence support is insufficient.

Developer owns the final decision when Master escalates with `developer_decision_required`.

## 10. Forbidden actions

Phase 22B must not:

- write `/project-root/causal`
- mutate canonical/global causal truth
- mutate Archive / Knowledge / Causal production stores
- create a separate causal-review department
- create a long-lived Causal Review Agent
- add router topology
- treat Debate Leader output as automatically accepted
- treat heuristic probability as statistical probability
- hide uncertainty from Developer
- skip Archive candidate generation for developer-decision escalation

## 11. Summary

```text
22A stages causal candidates.
22B reviews staged causal candidates against Knowledge + existing Causal + current constraints.
22B may produce canonical merge candidates, but does not merge them.
Unresolved uncertainty or insufficient high-confidence support escalates to Developer and must be archived.
```
