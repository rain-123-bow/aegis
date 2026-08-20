# Aegis v2 independent reference model

This directory is an evaluation-side implementation. It is not production
code and does not import `aegis`, `aegis.sut`, or any module under `src/`.
The SUT and this reference model may share serialized contracts and JSON
Schema files; they do not share executable helpers.

## Runtime contract

- CPython: `>=3.11,<3.14`
- `rfc8785==0.1.4`
- `jsonschema[format-nongpl]==4.26.0`
- Network access: not required
- JSON canonicalization: RFC 8785 JCS, UTF-8, no BOM, duplicate keys rejected
- Output framing: one JCS object followed by `LF` for each JSONL record

The exact executable source bindings, transitive source files, import policy,
entry hashes, and 16 comparator-spec preimages are frozen in
`source_manifest.v1.json`.

## Algorithms

| Algorithm ID | Python interface | Result |
| --- | --- | --- |
| `GENERATOR-VERDICT-CARTESIAN-V1` | `generator.iter_assignments`, `generator.instance_id` | 552,960 assignments |
| `GENERATOR-BLOCKER-CLOSURE-CARTESIAN-V1` | `generator.iter_assignments`, `generator.instance_id` | 144 assignments |
| `ORACLE-VERDICT-PRIORITY-TABLE-V1` | `verdict.evaluate_verdict_assignment`, `verdict.evaluate_verdict_input`, `verdict.verdict_sut_decision` | Independent 14-level verdict |
| `ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1` | `closure.evaluate_closure_assignment`, `closure.evaluate_closure`, `closure.closure_sut_decision` | Abstract and full closure decisions |
| `COMPARATOR-SUT-DECISION-EXACT-JCS-V1` | `comparator.compare_outputs` | Schema, self-hash, array-order, and exact-JCS comparison |
| `COMPARATOR-REFERENCE-TRACE-AUDITABLE-V1` | `comparator.compare_reference_traces` | Recovery and side-effect trace comparison |
| `REFERENCE-CLI-JSONL-V1` | `cli.main` | Unified deterministic JSONL CLI |

## Cartesian order and identity

`iter_assignments` preserves the property-suite `domain` member order and each
domain array order. It performs no sorting and no sampling.

`instance_id` is:

```text
sha256:<hex SHA-256(JCS({"suite_id": suite_id, "assignment": assignment}))>
```

JCS fixes object-key order. Enumeration order remains the manifest's field and
array order. A generated `ReferencePropertyInstance.v1` carries the assignment,
ordinal, algorithm IDs, and an expected context-free `SutDecision.v1`. It does
not put case identity, runner identity, or expected labels into the SUT
decision.

`--limit` is a diagnostic preview only. Release evaluation must omit it and
consume exactly 552,960 verdict instances and 144 closure instances.

## Verdict fact mask

The seven-bit `FACT-MASK-NNN` mapping is:

| Bit | Fact |
| ---: | --- |
| 0 | `UNKNOWN_SIDE_EFFECT` |
| 1 | `UPSTREAM_DEFECT` |
| 2 | `BLOCKING_PROCESS_BLOCKER` |
| 3 | `STAGNATION_CONFIRMED` |
| 4 | `UNCLASSIFIED_MISSING_CASE` |
| 5 | `OPEN_REQUIRED_ENVIRONMENT_GAP` |
| 6 | `CONFIRMED_PRODUCT_FINDING` |

The first matching verdict level wins:

1. cancellation `REQUESTED` or `QUIESCING`;
2. cancellation terminated with active work;
3. cancellation quiescent;
4. invalid or unknown workflow integrity;
5. unknown side effect or upstream defect;
6. blocking process blocker plus confirmed stagnation;
7. blocking process blocker;
8. invalid/stale evidence or an unclassified missing case;
9. unfinished phase A through F;
10. invalid terminal E/F chain;
11. open required environment gap;
12. confirmed product finding with complete or safety-limited coverage;
13. valid complete pass;
14. master/user discussion fallback.

The complete-input oracle selects the earliest blocking owner by
`(stage_rank, opened_event_id, blocker_id)`. The abstract oracle uses the
frozen representative blocker and owner A.

## Blocker closure

The 144-assignment oracle accepts only `INDEPENDENT` reviewer relation plus
valid owner evidence and valid reviewer evidence. The full-object oracle also
checks:

- source blocker is open and has no prior closed event;
- closure is append-only, schema-valid, bound to the exact blocker preimage,
  and self-hashed;
- blocker ID, origin role, owner role, source baseline, test-plan revision,
  and execution contract match;
- owner role matches owner identity;
- reviewer role is neither origin nor owner;
- reviewer and owner do not reuse the same `(thread_id, session_id)`;
- owner and reviewer evidence-reference sets are nonempty and disjoint;
- each evidence record is schema-valid, active, identity-bound, baseline-bound,
  plan-bound, contract-bound, and backed by exact raw bytes;
- severity, affected artifacts, and affected cases propagate exactly;
- prohibited substitutes are absent.

## Comparison rules

`compare_outputs` validates both values against
`sut_decision.v1.schema.json`, verifies each
`sut_decision_sha256 = SHA-256(JCS(object without that member))`, compares
`reason_ids` and `assertion_ids` in exact expected order, then compares complete
JCS bytes.

Trace normalization has two modes:

- `NONE`: preserve every member.
- `DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES`: recursively remove
  only `observation_time_utc` and `observed_at_utc`.

Array order, event identity, action identity, and operation identity are never
removed. Recovery/side-effect audit rejects missing identities, negative or
regressing effect counts, repeated non-idempotent effects, and automatic replay
of unjournaled operations.

## CLI

Run from the repository root:

```powershell
python -m evaluation.aegis_v2.reference generate `
  --manifest evaluation/aegis_v2/evaluation_manifest.v1.json `
  --suite-id PROPERTY-VERDICT-EXHAUSTIVE-V1
```

Other subcommands are `verdict-assignment`, `verdict-input`,
`closure-assignment`, `closure`, `compare-decision`, and `compare-trace`.
Single-object commands accept a JSON file; assignment commands also accept
stdin with `--input -`. Full closure input uses
`evidence_bytes_base64: {evidence_id: canonical-base64}`.

## Verification

```powershell
python -m unittest discover `
  -s evaluation/aegis_v2/reference/tests `
  -p 'test_*.py' -v
```

The tests import no SUT code. They verify exact Cartesian counts and order,
stable instance IDs, all 14 priority levels, conflict precedence, closure
identity/evidence/hash/propagation mutations, `SutDecision` schema and
self-hash, exact reason/assertion order, trace audit behavior, JSONL byte
determinism, source-manifest hashes, and the forbidden-import boundary.
