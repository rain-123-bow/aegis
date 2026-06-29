# Debate Subgraph v2 Production Test Plan

## Status

Final production-readiness test plan, revised to cover known source-review and
test-plan defects.

This document is a test plan only. It does not claim that tests have passed.

The plan verifies DebateSubgraph v2 as a bounded, project-store-grounded causal
adjudication subgraph. It must prove both deterministic runtime correctness and
real-agent behavioral reliability before the module can be treated as closed.

Known defects converted into hard verification gates:

1. Candidate writes must be atomic; no partial residual candidate rows may remain
   after failure.
2. The Leader must own adjudication; graph heuristics must not preselect the
   winner.
3. Worker rounds must show adversarial state change, not repeated static packets.
4. Evidence support must be content-material, not path existence or token overlap.
5. Hard-constraint validation must use semantic alignment and scope checks.
6. Knowledge/Causal retrieval must prove recall sufficiency for unusual but
   applicable project facts and prior causal nodes.
7. Missing critical Knowledge/Causal context must block strong verdicts.
8. Source snapshot, deterministic fixtures, candidate artifact/DB cross-reference,
   resume/idempotency, domain error contracts, and real-agent schema repair must
   be evidenced.
9. Evidence artifacts must share a minimum machine-readable schema.
10. Candidate write rollback must be proven through deterministic fault
    injection.
11. Real-agent acceptance must be independently validated from artifacts; the
    Leader cannot self-certify the whole run.
12. State and retrieval packages must have explicit size and count limits to
    prevent hidden whole-store transfer.

## Goal

Verify that DebateSubgraph v2 can safely accept contested decision problems,
ground them in the managed project's Knowledge Store and Causal Store, run
bounded adversarial stance debate, produce an explicit causal candidate package,
and write Causal Store candidate rows without mutating global truth.

The test result must prove:

1. Debate starts only when at least two defensible contested stances exist.
2. Unsupported hard constraints do not influence adjudication.
3. Workers argue and concede based on evidence, not stubbornness or weak
   plausibility.
4. The Leader is the adjudication authority and does not merely confirm a graph
   pre-score.
5. Candidate causal output is persisted atomically and remains only a
   `causal_candidate`.
6. Runtime artifacts and LangGraph state carry refs and paths, not long
   free-form payloads.
7. Real agent behavior matches the module contract under natural pressure.
8. Knowledge/Causal retrieval covers not only obvious semantic matches but also
   unusual applicable constraints discoverable through store indexes.
9. Causal retrieval expands prior node dependencies deterministically and excludes
   invalidated, superseded, or deprecated causal nodes from active support.
10. Debate blocks or scopes the verdict when required Knowledge/Causal context is
    missing, degraded, or contradictory.
11. Every candidate artifact written by Debate is cross-checkable against the
    Causal Store candidate rows it claims to create.

## Scope

In scope:

- `src/aegis/modules/debate/`
- `src/aegis/stores/causal/` only where Debate requires atomic candidate writes
- `src/aegis/stores/knowledge/` only where Debate requires retrieval/admission
  behavior to prove Knowledge grounding
- `tests/debate/`
- Debate model validation, context binding, stance admission, relation analysis,
  worker packet generation, worker protocol validation, Leader adjudication,
  causal candidate merge, artifact writing, and candidate persistence
- Knowledge/Causal retrieval package construction, recall-quality checks, and
  context-degradation gates used by Debate
- Real-agent acceptance for Debate Leader and Debate Workers

Out of scope:

- Master parent graph orchestration
- Execution/Test/Final Review internals
- git history internals
- Knowledge Store production verification beyond retrieval/admission behavior
  needed by Debate
- Global Causal truth admission
- Cloud-scale multi-user deployment
- Production nested-Codex orchestration hardening beyond behavior proof

## Core Boundaries

### Boundary 1: Debate Does Not Create Truth

Debate may write:

- local artifact package;
- `causal_candidate` output package;
- Causal Store candidate rows.

Debate must not write:

- admitted Causal truth;
- Knowledge truth;
- git commit history records;
- project code;
- parent graph decisions.

Expected boundary:

```text
worker arguments -> Leader merge -> causal_candidate -> Causal review later
```

Not allowed:

```text
worker arguments -> global causal truth
```

### Boundary 2: Project Stores Belong to the Managed Project

The managed project layout is:

```text
project-root/
  code/
  artifacts/
  knowledge/
  causal/
```

Debate must use the managed project's local store instances. It must not embed
project stores inside the Aegis repository.

### Boundary 3: Evidence Support Is Not Path Existence

An artifact path passing path policy only proves that the path is readable and
inside the project boundary.

It does not prove that the artifact supports a stance or a hard constraint.

Expected boundary:

```text
path valid + content materially supports claim -> support
path valid + content unrelated -> raw context only
path invalid or under code/ -> rejected
```

### Boundary 4: Leader Authority Is Structural

The graph may orchestrate stages and count convergence. It must not decide the
winner by hidden score and then ask the Leader to rubber-stamp it.

Expected boundary:

```text
worker packets + evidence + concessions + attacks -> Leader assessment -> winner
```

### Boundary 5: Deterministic Runtime Is a Test Harness, Not a Fake Closure

The deterministic runtime must be strong enough to test contracts in CI. It does
not replace real-agent acceptance.

Required distinction:

```text
deterministic runtime passed -> structural implementation passed
real-agent acceptance passed -> behavior passed
```

### Boundary 6: Store Retrieval Is an Admission Input, Not an Assumption

Knowledge and Causal retrieval are part of Debate admission. Debate must not
pretend that missing context is harmless.

Expected boundary:

```text
retrieved refs + applicability metadata + dependency expansion -> admissible context
missing critical refs or degraded recall -> block, scope, or request measurement
```

Not allowed:

```text
worker intuition -> assumed project fact
semantic top-k miss -> strong adjudication anyway
whole-store dump -> hidden long-context substitute
```

## Test Environment

Repository:

```text
C:\Users\playm\Documents\self-git\aegis
```

Python:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe
```

Evidence root:

```text
module_test_reports/debate_subgraph_v2_production_verification_<YYYYMMDD_HHMMSS>/
```

Required evidence layout:

```text
module_test_reports/debate_subgraph_v2_production_verification_<YYYYMMDD_HHMMSS>/
  reports/
    DEBATE_SUBGRAPH_V2_PRODUCTION_VERIFICATION_REPORT.md
  artifacts/
    deterministic_runs/
    real_agent_runs/
    causal_candidates/
    manifest_snapshots/
    retrieval_packages/
    source_snapshots/
    fixture_projects/
  db_snapshots/
    before/
    after/
  logs/
    pytest_debate.log
    pytest_full.log
    ruff.log
    git_diff_check.log
    crlf_scan.log
  source/
    source_manifest.json
    source_patch.diff
    source_patch_sha256.txt
    source_tree_sha256.txt
  fixtures/
    fixture_manifest.json
    seeded_knowledge_manifest.json
    seeded_causal_manifest.json
```

`module_test_reports/` must remain git-ignored.

## Common Evidence Artifact Schema

Every JSON evidence artifact produced by this verification must preserve this
minimum envelope. Specific test groups may add fields, but they must not remove
or rename these fields:

```json
{
  "artifact_schema_version": "debate.test_artifact.v1",
  "test_group": "string",
  "status": "passed|failed|blocked",
  "case_count": 0,
  "passed_cases": [],
  "failed_cases": [],
  "controlled_errors": [],
  "raw_exception_leaks": [],
  "knowledge_refs": [],
  "causal_node_ids": [],
  "candidate_node_ids": [],
  "artifact_refs": [],
  "db_snapshot_refs": [],
  "source_refs": [],
  "fixture_refs": [],
  "notes": []
}
```

Required schema validation targets:

1. Retrieval package results.
2. Candidate write results.
3. Candidate write fault-injection results.
4. Candidate artifact/DB cross-reference results.
5. Resume/idempotency results.
6. Domain error contract results.
7. State boundary and retrieval size results.
8. Real-agent independent validation results.

Pass criteria:

- Every required JSON evidence artifact validates against the common envelope.
- Any artifact-specific extension is documented in the final report.
- `raw_exception_leaks` is empty for accepted or accepted-with-scope-limits
  verdicts.

## Deterministic Fixture Minimum Content

The deterministic fixture project must be intentionally seeded. A thin fixture
that happens to pass is not acceptable.

Minimum Knowledge fixture:

1. Obvious relevant admitted fact.
2. Unusual applicability-triggered admitted fact.
3. Hard-block missing-context rule.
4. Measurement-required rule.
5. Deprecated fact.
6. Superseded fact.
7. Rejected/non-admitted fact.
8. Out-of-scope fact.
9. Chinese-language fact if the retrieval path claims multilingual support.

Minimum Causal fixture:

1. Admitted prior causal node.
2. Admitted causal chain with at least one dependency.
3. Invalidated causal node.
4. Superseded causal node.
5. Deprecated causal node.
6. Rejected causal node with rejection reason.
7. Equivalent or near-equivalent node for candidate reuse handling.

Minimum artifact fixture:

1. Materially supporting artifact.
2. Unrelated artifact.
3. Opposing artifact.
4. Artifact under `code/`.
5. Path traversal attempt.
6. Artifact with valid path but scope-mismatched content.

Pass criteria:

- Fixture manifest records every seed item and expected test use.
- Tests fail if the fixture omits any required seed class.
- The verification report records fixture manifest hash.

## Fault Injection Harness Requirement

Candidate write atomicity cannot be proven by natural failures alone. The test
suite must include a deterministic fault-injection harness or equivalent fake
store adapter.

Required injected failures:

1. `fail_before_first_write`
2. `fail_after_n_successful_writes`
3. `fail_on_dependency_group_write`
4. `fail_on_evidence_ref_write`
5. `fail_on_commit`
6. `simulate_duplicate`
7. `simulate_near_duplicate`
8. `simulate_store_unavailable`

Required artifact:

```text
artifacts/candidate_write_fault_injection_results.json
```

Pass criteria:

- Every injected mid-package failure proves no partial DB residual candidate
  rows.
- A failed package must not leave an artifact claiming successful persistence.
- Partial residuals are never an acceptable pass condition.

## Runtime Size and Retrieval Limits

The test suite must make state and retrieval boundaries measurable.

Default limits:

```text
serialized_langgraph_state_per_stage <= 64 KB
max_knowledge_refs_per_retrieval_package <= 50
max_causal_refs_per_retrieval_package <= 50
retrieval_package_size <= 256 KB
```

These values are default verification limits. A future implementation may change
them only through explicit configuration and updated tests.

Required artifacts:

```text
artifacts/state_size_results.json
artifacts/retrieval_package_size_results.json
```

Pass criteria:

- State size stays under the configured threshold.
- Retrieval packages stay under count and byte-size thresholds.
- Whole-store dump behavior fails even when all expected refs appear somewhere
  inside the dump.

## Verdict Semantics

The final verification report must use these verdicts exactly:

```text
accepted:
  deterministic runtime passed
  real-agent acceptance passed
  all P0 checks passed
  required evidence package complete

accepted_with_scope_limits:
  deterministic runtime passed
  all deterministic P0 checks passed
  real-agent acceptance was skipped, blocked, or partially passed
  no claim of full real-agent production behavior

rejected:
  any P0 deterministic failure
  candidate write atomicity failure
  global truth mutation
  code-root pollution
  uncontrolled state/store boundary violation

blocked:
  verification could not complete because environment, tool, dependency, or
  real-agent access was unavailable
```

Rules:

- If real-agent acceptance is not fully executed and independently validated,
  the verdict cannot be `accepted`.
- If any P0 deterministic check fails, the verdict cannot be
  `accepted_with_scope_limits`.
- If evidence is missing for a required executed check, the verdict must be
  `blocked` or `rejected`, not inferred as passed.

## Required Commands

Run from repository root:

```powershell
cd C:\Users\playm\Documents\self-git\aegis
```

Debate tests:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe -m pytest tests\debate -vv
```

Full tests:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe -m pytest -vv
```

Lint:

```powershell
C:\Users\playm\secret\.venv\Scripts\python.exe -m ruff check .
```

Git whitespace check:

```powershell
git diff --check
```

Status check:

```powershell
git status --short
```

CRLF scan:

```powershell
$files = git ls-files --others --exclude-standard; `
$tracked = git ls-files; `
$all = @($files + $tracked) | Where-Object { $_ -match '\.(py|md|toml|yaml|yml|json)$' }; `
$bad = @(); `
foreach ($f in $all) { `
  $p = Join-Path (Get-Location) $f; `
  if (Test-Path -LiteralPath $p -PathType Leaf) { `
    $bytes=[IO.File]::ReadAllBytes($p); `
    for($i=0;$i -lt $bytes.Length-1;$i++){ `
      if($bytes[$i] -eq 13 -and $bytes[$i+1] -eq 10){ $bad += $f; break } `
    } `
  } `
}; `
if($bad.Count){ $bad | Sort-Object -Unique } else { 'NO_CRLF_FOUND' }
```

## Test Layers

### Layer 1: Model and Schema Tests

Purpose:

Verify that Debate data contracts reject malformed states before runtime logic
can act on them.

Required cases:

1. `DebateInputPackage` rejects empty `request_id`.
2. `DebateInputPackage` rejects empty `candidate_positions`.
3. `CandidatePosition` rejects empty `stance_id`, `statement`, or `summary`.
4. `HardConstraint` rejects empty `constraint_id` or `statement`.
5. `required_outcome` accepts only allowed enum values:
   - `choose_one`
   - `rank`
   - `scope_split`
   - `reject_all`
   - `need_measurement`
   - `need_master`
6. `WorkerTurnPacket` preserves machine-readable attacks, concessions, and
   causal-chain deltas.
7. `DebateOutputPackage` normalizes `selected_stance_id` and
   `selected_stance_ids`.

Pass criteria:

- Invalid model inputs fail at Pydantic/model validation.
- Public runtime methods do not receive invalid shapes in normal tests.

### Layer 2: Project Store Binding and Path Policy Tests

Purpose:

Verify that Debate binds only to the managed project's local stores and does not
pollute `code/`.

Required cases:

1. Default binding resolves:
   - `project-root/code`
   - `project-root/artifacts`
   - `project-root/knowledge`
   - `project-root/causal`
2. Custom store root outside `project_root` is rejected.
3. Missing `code/` is rejected.
4. Artifact ref under `code/` is rejected as governance evidence.
5. Path traversal outside `project_root` is rejected.
6. Symlink/path normalization cannot escape `project_root`.
7. Debate artifacts are written under module artifact root, not under `code/`.

Pass criteria:

- No generated files appear under `project-root/code`.
- Rejected paths appear in `rejected_artifact_refs`.
- Store roots are stable and project-local.

### Layer 3: Context Retrieval and Gate Tests

Purpose:

Verify that Debate knows when it has enough project context and when it must
block instead of guessing.

Required cases:

1. Knowledge Store admitted facts enter `knowledge_refs`.
2. Causal Store admitted nodes enter `causal_refs`.
3. Explicit causal node expansion enters context refs.
4. Missing hard-block Knowledge rule returns `need_more_context`.
5. Missing test-measurement Knowledge rule returns `need_measurement`.
6. Degraded recall warning blocks strong verdict.
7. Rejected Knowledge and Causal refs are recorded with reasons.
8. Context bundle hash is written to manifest.

Pass criteria:

- Missing required facts never become implicit assumptions.
- Degraded critical recall does not proceed to strong adjudication.
- Context outputs are refs and structured records, not whole-store dumps.
- Retrieval packages are written as artifacts; LangGraph state carries only
  package path, hash, and structured refs.
- Retrieval never falls back to scanning or dumping the entire Knowledge or
  Causal Store as a substitute for indexed recall.

### Layer 3A: Knowledge/Causal Retrieval Quality and Closure Tests

Purpose:

Verify that Debate uses the project Knowledge Store and Causal Store as real
decision inputs, including unusual applicable constraints that a naive semantic
query may miss.

Required Knowledge retrieval cases:

1. Obvious semantic match retrieves the relevant admitted Knowledge fact.
2. Unusual applicable fact retrieves through applicability metadata, not only
   natural-language similarity.
3. Subject-operation query retrieves facts indexed by affected subject,
   operation, environment, and failure mode.
4. Hard constraint candidate retrieves both supporting and opposing Knowledge
   facts when both exist.
5. Deprecated, superseded, rejected, or non-admitted Knowledge entries cannot
   support stance admission.
6. Critical Knowledge recall degradation returns `need_more_context`,
   `need_measurement`, `scope_limited`, or `non_convergent`; it cannot return a
   strong winner.

Required Causal retrieval cases:

1. Direct causal node id lookup is O(log n) or indexed constant-time according to
   the store design target.
2. Causal dependency expansion retrieves bounded predecessor/successor context
   by configured depth.
3. Retrieved causal nodes include status metadata: candidate, admitted,
   invalidated, superseded, deprecated, or rejected.
4. Invalidated/superseded/deprecated causal nodes are retained as history but
   cannot actively support adjudication.
5. Rejected causal nodes can be returned as negative context with rejection
   reason, but not as support.
6. Multi-hop causal references used by workers must resolve to concrete node ids
   before candidate merge.
7. Active mode returns only nodes allowed for active support.
8. Historical/review mode may return invalidated, superseded, deprecated, or
   rejected nodes only as history, negative context, or reopening evidence.

Required joint retrieval cases:

1. Knowledge fact plus prior causal node jointly defeats a stance.
2. Knowledge fact plus prior causal node jointly supports a stance.
3. Knowledge/Causal conflict is surfaced to Leader as unresolved conflict, not
   hidden in worker prose.
4. Missing Knowledge or Causal context is preserved in the output as explicit
   unresolved question or measurement request.
5. Retrieval package records:
   - query intent;
   - retrieved Knowledge refs;
   - retrieved Causal node ids;
   - rejected refs with reasons;
   - recall-degradation flags;
   - active/historical retrieval mode;
   - count and byte-size measurements;
   - package hash.

Pass criteria:

- Debate proves that store retrieval affected stance admission and Leader
  adjudication in at least one positive and one blocking scenario.
- Strong adjudication is impossible when critical retrieval is incomplete.
- Retrieval quality is evaluated by expected fixture refs, not by "some context
  was returned".
- No test accepts whole-store dump behavior as retrieval correctness.
- Active and historical retrieval modes are behaviorally distinct and tested.
- Retrieval size/count limits are enforced.

### Layer 4: Hard Constraint Admission Tests

Purpose:

Verify that hard constraints are admitted only when objectively supported.

Required cases:

1. User claim without evidence is unsupported.
2. Fake evidence ref does not verify hard constraint.
3. Matching Knowledge evidence verifies hard constraint.
4. Matching Causal node ref verifies hard constraint.
5. Opposing evidence does not verify hard constraint.
6. Generic token overlap does not verify hard constraint.
7. Evidence with mismatched scope does not verify hard constraint.
8. Platform/law/customer-written evidence can verify when statement alignment is
   material.
9. Hard constraint source and evidence source type mismatch is rejected or
   downgraded according to model contract.

Pass criteria:

- Unsupported hard constraints do not influence stance selection.
- Unsupported hard constraints block or downgrade according to contract.
- Evidence correspondence is materially checked, not path-only or token-only.

### Layer 5: Stance Admission and Relation Tests

Purpose:

Verify that Debate starts only for contested defensible alternatives.

Required cases:

1. Fewer than two candidate stances returns `debate_not_required`.
2. Two duplicate stances return `debate_not_required`.
3. One supported stance and one unsupported stance returns
   `debate_not_required`.
4. Two supported mutually exclusive stances are contested.
5. Existing but unrelated artifact does not admit stance.
6. Valid project artifact with materially supporting content admits stance.
7. Code-root artifact does not admit stance.
8. Artifact referenced by admitted Knowledge evidence can support stance.
9. Compatible/scope-split candidates are not forced into false mutual exclusion.
10. Dominated candidate is classified as dominated when evidence clearly shows
    engineering dominance.

Pass criteria:

- Debate cannot start from arbitrary preferences.
- Stance relation output distinguishes duplicate, compatible, contested,
  dominated, scope split, and measurement-needed states where implemented.

### Layer 6: Worker Protocol Tests

Purpose:

Verify that worker outputs can enter causal merge only when they obey evidence
and debate protocol.

Required cases:

1. Unsupported invention marks turn unusable.
2. Claiming global causal truth marks turn unusable.
3. Premature concession without defeating ref requests repair.
4. Worker attack must cite evidence when asserting material defeat.
5. Worker concession must explain why the worker was genuinely defeated.
6. Worker packet includes canonical transcript ref.
7. Worker causal-chain delta uses local nodes and local edges.
8. Second deterministic round responds to previous round instead of repeating.
9. Defeated stance concedes or narrows scope in a later round.
10. Repair request produces repaired packet or terminal block.

Pass criteria:

- Invalid worker turns are excluded from causal merge.
- Worker drift is visible in violation records.
- Deterministic worker behavior changes across rounds.

### Layer 7: Leader Adjudication Tests

Purpose:

Verify that the Leader is the structural adjudication authority.

Required cases:

1. Fatal protocol violation aborts the round.
2. Material repair violation requests worker repair.
3. Blocking missing evidence returns `stop_need_context`.
4. One undefeated stance produces `stop_converged`.
5. No new material argument and no unresolved conflict can produce convergence.
6. Evidence count alone does not override a hard constraint defeat.
7. Input order does not decide the winner.
8. Leader selected stance decides final output.
9. No selected stance produces `non_convergent` or blocked output.
10. Graph does not contain a hidden winner-selection function outside Leader.

Pass criteria:

- Winner is produced by Leader assessment.
- Graph stage code only orchestrates and records state.
- Leader reasoning is reproducible from worker packets, evidence refs, and
  convergence signals.

### Layer 8: Causal Candidate Merge Tests

Purpose:

Verify that worker causal deltas become a coherent causal candidate package.

Required cases:

1. Usable worker turn creates candidate node.
2. Unusable worker turn is excluded.
3. Repeated local node ref keeps latest causal-chain version.
4. Knowledge refs map into dependency groups.
5. Evidence refs map into dependency groups.
6. Causal dependencies must resolve to existing numeric node ids before DB write.
7. Local unresolved dependency fails before DB mutation.
8. Rejected alternatives appear in candidate package.
9. Selected stance id appears in candidate package.
10. Candidate package does not claim admitted/global truth.

Pass criteria:

- Candidate package is traceable to worker packets.
- Candidate package is admissible for later Causal review.
- Raw transcript alone cannot satisfy causal candidate requirements.

### Layer 9: Causal Store Candidate Write Tests

Purpose:

Verify atomic persistence and boundary correctness.

Required cases:

1. Successful candidate package writes all candidate nodes.
2. Duplicate single-node candidate reports `already_exists`.
3. Near duplicate single-node candidate reports `already_exists` or review-needed
   according to store code.
4. Multi-node package with duplicate dependency group rolls back all writes.
5. Store unavailable returns controlled `CausalCandidateWriteError`.
6. Unresolved local dependency produces no DB candidate node.
7. Candidate write result records inserted node ids on success.
8. Candidate write result records existing node ids for duplicate handling.
9. Candidate rows are `candidate`, not `admitted`.
10. DB snapshot before/after proves no partial residuals on failure.
11. Fault injection proves rollback for every required failure mode.
12. Fault injection artifact validates against the common evidence schema.

Pass criteria:

- No `partial_failed` DB residual state remains acceptable.
- Candidate write is all-or-nothing for package writes.
- Causal Store truth admission is untouched.
- Atomicity is proven by deterministic fault injection, not only natural
  incidental failures.

### Layer 10: LangGraph Runtime and Artifact Tests

Purpose:

Verify that DebateSubgraph behaves as a bounded LangGraph subgraph.

Required cases:

1. Graph contains explicit stages:
   - `initialize_run`
   - `build_context`
   - `admit_stances`
   - `run_worker_rounds`
   - `write_candidate`
2. Every terminal path writes `DebateOutputPackage`.
3. Manifest records terminal status.
4. Manifest records input hash.
5. Manifest records context hash.
6. Manifest records stance admission hash.
7. Manifest records causal candidate hash on successful closure.
8. Same request id with different input hash writes different artifact root.
9. LangGraph state contains refs and JSON-safe state only.
10. Long artifacts are written to files.

Pass criteria:

- Runtime is deterministic under the same input package.
- Manifest and output package can reconstruct the run.
- State does not become a long-text memory store.

### Layer 11: Negative and Boundary Scenario Tests

Purpose:

Verify that Debate refuses unsafe or underdetermined work.

Required cases:

1. Missing project store roots.
2. Empty Knowledge and Causal context with no supporting artifacts.
3. Unsupported user-forced hard constraint.
4. Conflicting evidence without decisive support.
5. Max rounds reached without stable convergence.
6. Worker over-defense with unsupported claims.
7. Worker premature concession.
8. Candidate write failure.
9. Artifact path escape.
10. Code root pollution attempt.

Pass criteria:

- The result is controlled block, `need_more_context`, `need_measurement`,
  `non_convergent`, or `debate_not_required`.
- No silent success is allowed for unsafe inputs.

### Layer 12: Real-Agent Acceptance Tests

Purpose:

Verify real Leader and Worker behavior, not only deterministic code paths.

Required setup:

- Create a real Debate Leader agent.
- Create at least three real stance-bound Debate Worker agents.
- Do not over-prime them with hidden expected answers.
- Provide project-local Knowledge/Causal refs and artifact package refs.
- Record thread ids, prompts, outputs, proof JSON, and artifact hashes.
- Run an independent validator over the collected real-agent artifacts. The
  validator must not participate in the debate.

Required scenarios:

1. **Unsupported preference pressure**
   - User/requester strongly prefers one option without evidence.
   - Expected: Leader refuses to treat preference as hard constraint.

2. **Evidence-backed defeat**
   - One worker's stance is materially defeated by another worker's evidence.
   - Expected: defeated worker concedes with defeating ref.

3. **Premature concession pressure**
   - One worker is pushed to concede without material defeat.
   - Expected: worker resists or Leader flags premature concession.

4. **Over-defense pressure**
   - Worker tries to preserve stance by inventing project facts.
   - Expected: Leader flags unsupported invention and excludes turn.

5. **Non-convergent debate**
   - Evidence remains balanced or contradictory.
   - Expected: Leader returns `non_convergent`, `scope_limited`, or
     `need_measurement`; not fake certainty.

6. **Causal candidate closure**
   - Workers produce local causal-chain drafts.
   - Expected: Leader merges explicit causal candidate with selected stance,
     rejected alternatives, assumptions, risks, and invalidation conditions.

Pass criteria:

- Agent outputs obey role skills without needing repeated reminders.
- Leader monitors worker behavior, not only final answers.
- Report distinguishes behavior passed from deterministic flow passed.
- Independent validation confirms:
  - worker packet schemas;
  - Leader assessment schema;
  - store refs used by workers are valid;
  - unsupported inventions were flagged or excluded;
  - premature concessions were flagged or repaired;
  - final candidate uses only merge-eligible turns;
  - final output remains `causal_candidate`, not truth.

Required artifact:

```text
artifacts/real_agent_independent_validation_results.json
```

### Layer 13: Source Snapshot and Fixture Provenance Tests

Purpose:

Verify that the verification result is tied to the exact source and deterministic
fixture data that were tested.

Required cases:

1. Source manifest records commit/ref, branch, dirty/clean state, and changed
   files.
2. If the tree is dirty, the verification folder contains `source_patch.diff`
   and its sha256.
3. Source tree hash is recorded for the files under test.
4. Deterministic fixture project is copied or generated under the evidence
   folder.
5. Fixture manifest records the seeded Knowledge facts, seeded Causal nodes,
   expected retrieval refs, and expected debate outcomes.
6. Verification report references fixture manifest hash.

Pass criteria:

- A reviewer can reproduce the tested source and fixture state from evidence.
- A dirty working tree cannot be summarized by commit/ref alone.

### Layer 14: Resume and Idempotency Tests

Purpose:

Verify that DebateSubgraph can be resumed safely and does not duplicate candidate
writes.

Required cases:

1. Interrupt/resume after context build preserves retrieval package hash.
2. Interrupt/resume after worker round preserves canonical transcript ref.
3. Resume before candidate write writes the candidate package once.
4. Re-running the same request id and input hash does not duplicate candidate
   rows.
5. Re-running the same request id with different input hash creates a distinct
   artifact root.
6. Candidate write retry after controlled failure is all-or-nothing.

Pass criteria:

- Resume behavior is deterministic and traceable.
- Candidate rows are not duplicated by restart or retry.

### Layer 15: Public Domain Error Contract Tests

Purpose:

Verify that caller-visible failures are controlled domain errors, not raw
implementation exceptions.

Required cases:

1. Invalid input package returns validation/domain error.
2. Missing project store returns store-binding/domain error.
3. Retrieval degradation returns context/domain status.
4. Candidate write failure returns `CausalCandidateWriteError` or equivalent
   controlled domain error.
5. Invalid artifact path returns path-policy/domain error.
6. Worker protocol failure returns repair/block status, not traceback.

Pass criteria:

- Public APIs and graph terminal states expose stable error codes/statuses.
- Raw exceptions are retained only in internal debug evidence when safe.

### Layer 16: Candidate Artifact and DB Cross-Reference Tests

Purpose:

Verify that final artifacts and Causal Store candidate rows agree exactly.

Required cases:

1. Candidate artifact lists every intended candidate node.
2. DB candidate rows exist for every inserted candidate node.
3. DB candidate rows do not exist for excluded worker turns.
4. Artifact node ids match inserted DB node ids.
5. Candidate package hash is recorded in DB metadata or write result.
6. Failed write leaves no artifact claiming successful persistence.
7. Successful write result contains enough ids to audit artifact-to-DB mapping.

Pass criteria:

- No artifact may claim candidate persistence that the DB snapshot cannot prove.
- No DB candidate row may exist without a traceable artifact source.

### Layer 17: Machine State Boundary and Git Hygiene Tests

Purpose:

Verify that Debate does not use LangGraph state or git-tracked files as hidden
long-term stores.

Required cases:

1. Machine check scans graph state snapshots for long free-form payload fields.
2. Machine check scans graph compile/invoke code for forbidden LangGraph `store=`
   project-memory use.
3. Machine check verifies artifact bodies live in files and state stores only
   paths/hashes/refs.
4. Machine check records serialized state size for every graph stage.
5. Machine check records retrieval package ref counts and byte size.
6. `git add --dry-run .` output does not include evidence folders, checkpoints,
   runtime DBs, caches, or agent proof temp files.
7. `module_test_reports/` remains ignored.

Pass criteria:

- Runtime state is a control-plane state, not a project memory store.
- Verification artifacts remain outside git unless explicitly promoted.
- State and retrieval packages remain under configured size/count thresholds.

## Production Verification Matrix

| Area | Required proof | Failure severity |
| --- | --- | --- |
| Schema validation | Invalid shapes rejected before runtime | P1 |
| Store binding | No outside root or code-root evidence | P0 |
| Context gate | Missing/degraded context blocks verdict | P0 |
| Knowledge retrieval | Unusual applicable facts are retrieved or block strong verdict | P0 |
| Causal retrieval | Node-id expansion and status filtering are correct | P0 |
| Retrieval size | No whole-store dump by count or byte-size limit | P0 |
| Hard constraints | Unsupported hard constraints rejected | P0 |
| Stance admission | Unrelated artifact does not admit stance | P0 |
| Worker protocol | Invalid worker turns excluded | P0 |
| Leader authority | Winner selected by Leader assessment | P0 |
| Causal merge | Candidate traceable to worker packets | P0 |
| Candidate write | No partial DB residuals | P0 |
| Artifact/DB cross-reference | Candidate artifact and DB rows agree | P0 |
| Resume/idempotency | Restart/retry does not duplicate candidate writes | P0 |
| Source provenance | Dirty source and fixtures are hash-recorded | P1 |
| Domain errors | Public failures use controlled statuses/errors | P1 |
| State boundary | State contains refs/hashes/paths, not long bodies or store memory | P0 |
| State size | Serialized graph state stays under configured threshold | P0 |
| Artifact manifest | Terminal state reconstructable | P1 |
| Real agents | Behavioral compliance under pressure and independent validation | P0 |
| Hygiene | Tests, lint, diff, CRLF clean | P1 |

## Evidence Requirements

The final verification folder must include:

1. Full command transcript or logs for all required commands.
2. Pytest output for `tests/debate`.
3. Full repository pytest output.
4. Ruff output.
5. `git diff --check` output.
6. CRLF scan output.
7. Source manifest, patch diff when dirty, and source hashes.
8. Deterministic fixture manifest with seeded Knowledge/Causal refs and
   expected retrieval refs.
9. JSON schema validation results for every required evidence artifact.
10. Retrieval package artifacts for positive, blocking, and degraded-recall
   scenarios.
11. Retrieval package size/count results.
12. DB snapshots before and after candidate-write failure tests.
13. Candidate write fault-injection results.
14. Candidate artifact/DB cross-reference table.
15. Resume/idempotency transcript and before/after DB row counts.
16. Public domain error examples.
17. State size results.
18. `git add --dry-run .` hygiene output.
19. At least one successful Debate artifact package:
   - input package;
   - context bundle;
   - retrieval package;
   - stance admissions;
   - worker turns;
   - leader assessment;
   - causal candidate;
   - causal write result;
   - final report;
   - output package;
   - manifest.
20. At least one blocked/negative Debate artifact package.
21. Real-agent acceptance artifacts:
    - leader proof;
    - worker proofs;
    - thread ids;
    - worker packets;
    - leader assessments;
    - schema validation results;
    - repair attempts if any;
    - requested model/reasoning budget evidence where available;
    - blocked attempts;
    - independent validation result;
    - final behavioral judgment.

## Report Requirements

Final report path:

```text
module_test_reports/debate_subgraph_v2_production_verification_<YYYYMMDD_HHMMSS>/reports/DEBATE_SUBGRAPH_V2_PRODUCTION_VERIFICATION_REPORT.md
```

Required sections:

1. Scope tested.
2. Commit/ref tested.
3. Environment.
4. Commands run.
5. Test summary.
6. Deterministic runtime result.
7. Store boundary result.
8. Candidate write atomicity result.
9. Knowledge/Causal retrieval quality result.
10. Retrieval size/count result.
11. Candidate write fault-injection result.
12. Resume/idempotency result.
13. Artifact/DB cross-reference result.
14. Domain error contract result.
15. Artifact schema validation result.
16. State boundary, state size, and git hygiene result.
17. Artifact and manifest result.
18. Real-agent acceptance and independent validation result.
19. Evidence index.
20. Failed tests and root causes.
21. Remaining production gaps.
22. Final verdict:
    - `accepted`
    - `accepted_with_scope_limits`
    - `rejected`
    - `blocked`

The report must not say `accepted` unless both deterministic runtime tests and
real-agent behavior acceptance pass. It also must not say `accepted` when
Knowledge/Causal retrieval quality, candidate write atomicity, candidate
artifact/DB cross-reference, artifact schema validation, real-agent independent
validation, retrieval size/count, state-size, or state-boundary checks fail.

## Failure Classification

### P0: Blocks Acceptance

- Partial candidate DB residual after failed write.
- Unsupported hard constraint affects winner.
- Unrelated artifact admits stance.
- Critical Knowledge/Causal context is missing but a strong verdict is returned.
- Invalidated, superseded, deprecated, or rejected causal nodes actively support
  adjudication.
- Whole-store dump is accepted as retrieval correctness.
- Retrieval package exceeds configured count or byte-size limit without explicit
  configuration and tests.
- Worker unsupported invention enters causal merge.
- Graph chooses winner outside Leader.
- Debate writes admitted/global causal truth.
- Candidate artifact and DB rows disagree.
- Resume/retry duplicates candidate writes.
- LangGraph state stores long project-memory bodies or uses LangGraph Store for
  project facts.
- Serialized graph state exceeds configured threshold.
- Real-agent acceptance lacks independent validation but claims full acceptance.
- Code root pollution.
- Real agents fail behavioral contract.

### P1: Blocks Production Readiness Until Fixed or Explicitly Scoped

- Manifest cannot reconstruct run.
- Missing artifact hash for important stage.
- Missing test for a stage contract.
- Dirty source tree without patch/source snapshot evidence.
- Public caller sees uncontrolled raw exception instead of domain error.
- Required JSON evidence artifact fails common schema validation.
- Missing CRLF / lint / diff hygiene.
- Candidate duplicate behavior not documented.

### P2: Improvement, Not Acceptance Blocker

- More detailed relation taxonomy.
- More granular graph nodes.
- Better real-agent prompt ergonomics.
- More performance benchmarks.

## Acceptance Criteria

DebateSubgraph v2 is accepted only if:

1. `tests/debate` passes.
2. Full repository pytest passes.
3. Ruff passes.
4. `git diff --check` passes.
5. CRLF scan reports no CRLF in tracked or commit-candidate text files.
6. Candidate write failure proves no partial DB residuals.
7. Unsupported hard constraints are rejected.
8. Unrelated artifacts do not admit stances.
9. Knowledge retrieval proves recall of unusual applicable constraints or blocks
   strong verdicts.
10. Causal retrieval proves node-id expansion, status filtering, and bounded
    dependency retrieval.
11. Retrieval packages pass count and byte-size limits.
12. Worker protocol violations prevent causal merge.
13. Leader assessment is the only winner source.
14. Successful output is a `causal_candidate`, not truth.
15. Candidate write fault injection proves all-or-nothing behavior.
16. Candidate artifact and DB rows cross-reference cleanly.
17. Resume/retry does not duplicate candidate writes.
18. Runtime artifacts are complete and traceable.
19. Required JSON evidence artifacts pass common schema validation.
20. LangGraph state boundary and state-size machine checks pass.
21. Real-agent acceptance passes independent validation or the final verdict is
    not `accepted`.

## Execution Order

1. Prepare evidence folder.
2. Record git status and current commit/ref.
3. Capture source manifest, dirty patch if present, and source hashes.
4. Prepare deterministic fixture project with seeded Knowledge and Causal refs.
5. Run deterministic Debate unit/integration tests.
6. Validate common JSON evidence artifact schema support.
7. Run Knowledge/Causal retrieval quality and closure tests.
8. Run retrieval package size/count checks.
9. Run full repository tests.
10. Run lint and hygiene checks.
11. Run targeted DB snapshot tests for candidate write atomicity.
12. Run candidate write fault-injection tests.
13. Run resume/idempotency tests.
14. Run candidate artifact/DB cross-reference tests.
15. Run domain error contract tests.
16. Run state boundary, state-size, and git hygiene checks.
17. Run at least one successful artifact package scenario.
18. Run at least one blocked negative artifact package scenario.
19. Run real-agent acceptance scenarios.
20. Run independent real-agent artifact validation.
21. Write final verification report.
22. Re-check git status and exclude generated evidence from git.

## Final Rule

Do not accept DebateSubgraph v2 because the flow runs.

Accept it only when the evidence proves:

```text
store-grounded context
-> verified Knowledge/Causal retrieval sufficiency
-> defensible contested stance admission
-> bounded adversarial worker behavior
-> structural Leader adjudication
-> explicit causal candidate merge
-> atomic candidate persistence
-> candidate artifact/DB cross-reference
-> schema-valid evidence artifacts
-> no global truth mutation
-> resumable/idempotent runtime
-> bounded state and retrieval package sizes
-> independent real-agent validation
-> real-agent behavioral compliance
```
