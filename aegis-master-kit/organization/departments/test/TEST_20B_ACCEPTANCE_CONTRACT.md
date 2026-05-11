# Test Phase 20B Acceptance Contract

## 1. Phase definition

Phase 20B validates real nested-Codex Test Worker acceptance.

It builds on Phase 20A Test handoff validation.

## 2. Accepted chain

```text
Execution Phase 19B handoff package / Phase 20A validation output
  -> Test Leader
      -> accepted validation routes
      -> real nested-Codex Test Worker per route
      -> Test Worker proof audit
      -> Test Worker output audit
      -> scoped route evidence
      -> Test Leader aggregation material
```

## 3. Acceptance label

A successful Phase 20B run may be labeled:

```text
accepted_real_test_worker_closure
```

It must not be labeled:

```text
production_test_lifecycle_closure
```

## 4. Required evidence

A valid Phase 20B package must contain:

```text
test_worker_creation_requests.json
expected_test_worker_proofs.json
expected_test_worker_outputs.json
test_worker_proofs/*_proof.json
test_worker_outputs/*_output.json
test_worker_prompts/*.md
worker_output_audit_summary.json
worker_proof_audit_summary.json
```

## 5. Strict boundaries

- Master creates or calls only the Test Leader.
- Test Leader creates Test Workers.
- Test Workers are route-internal request-scoped agents.
- Missing proof fails.
- Missing output fails.
- No deterministic/mock Test Worker may be counted as real acceptance.
- No source code modification.
- No remote push.
- No PR.
- No remote merge.
- No release.
- No production sign-off.
- No global causal truth claim.

## 6. Relationship to Phase 20A

Phase 20A proves Test Leader can consume Execution handoff and run local evidence production.

Phase 20B proves the real Test Worker layer.

Phase 20B may reuse the Phase 20A handoff validation output, but it must not relabel Phase 20A deterministic/in-process validation as real Test Worker work.
