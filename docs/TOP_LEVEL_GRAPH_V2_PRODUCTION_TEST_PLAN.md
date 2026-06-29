# Top-Level Graph v2 Production Test Plan

## Status

Production-grade test plan for Top-Level Graph v2.

This file is a test plan only. It does not claim that tests have passed.

The plan verifies that the top-level parent graph is a thin resident router for
already-closed subgraphs. Passing this plan must prove route-contract
correctness, handoff-package correctness, resident-module lifecycle boundaries,
failure stop behavior, evidence preservation, and parent boundary enforcement.

Flow success alone is insufficient. A run is not accepted if the parent graph
routes correctly while bypassing subgraph contracts, carrying long-form payloads
in state, importing module business logic, silently recovering failed resident
modules, or claiming real-agent liveness that was not verified.

## Goal

Verify that Top-Level Graph v2 can compose the resident Aegis subgraphs:

1. Master
2. Debate
3. Execution
4. Test
5. Final Review

without owning their internal business semantics.

The parent graph must:

1. acquire one project-local runtime lock;
2. construct exactly one resident instance of each core subgraph;
3. keep Debate workers outside the global resident registry;
4. validate every cross-module route against the route schema registry;
5. transfer only artifact package references and small machine-readable fields;
6. validate package manifests and manifest hashes;
7. persist full route history outside graph state;
8. keep graph-state route history bounded;
9. stop the whole Aegis runtime on resident failure;
10. preserve failure evidence before stopping;
11. reserve runtime terminal status for Master closeout;
12. avoid Knowledge / Causal admitted truth mutation;
13. avoid push, PR, merge, release, deploy, or external publication.

## Scope

In scope:

- `src/aegis/top_level/`
- `tests/test_top_level_graph_v2_runtime.py`
- `docs/TOP_LEVEL_GRAPH_V2_DESIGN.md`
- `docs/TOP_LEVEL_GRAPH_V2_PRODUCTION_TEST_PLAN.md`
- parent runtime lock
- resident module registry
- route schema registry
- top-level handoff envelopes
- package manifest validation
- package hash validation
- bounded state route history
- persisted route history artifact
- failure evidence artifact
- interrupt package propagation
- runtime terminal closeout behavior
- parent source-level boundary checks
- deterministic runtime tests
- real resident-agent acceptance track

Out of scope:

- Master internal requirement intake logic
- Debate internal worker debate quality
- Execution implementation quality
- Test evidence execution quality
- Final Review code audit quality
- future lifecycle/token monitor implementation
- production external Codex resource scheduling
- real Knowledge / Causal truth admission
- automatic stale-lock stealing
- remote push, PR, merge, release, deploy, or publication

The out-of-scope items remain covered by their own module test plans or future
monitor-module plans. The parent graph test may verify that their package
contracts are respected, but it must not re-evaluate their internal semantics.

## Non-Negotiable Boundaries

1. The parent graph is a router, not a business workflow engine.
2. The parent graph must not import or execute module business logic.
3. The parent graph must not inspect long-form requirements, plans, evidence,
   reports, source diffs, or causal chains.
4. Large content must live in files or folders; graph state carries refs only.
5. Every handoff package must contain a `README.md` as the preferred first read.
6. Every handoff package must contain a machine-readable manifest.
7. Manifest hash mismatch must block the route.
8. Same project visibility must not imply route permission.
9. Runtime terminal status is allowed only for Master closeout.
10. Debate workers must not be registered as top-level resident modules.
11. Resident subgraph failure must stop the whole Aegis runtime.
12. Failure stop must preserve evidence before returning terminal failure.
13. Restarted metadata must not be treated as verified live agent liveness.
14. The future monitor may verify liveness and token usage; the parent graph may
    only record monitor refs or failure signals.
15. Top-level tests must distinguish deterministic flow success from real-agent
    behavior acceptance.

## Test Environment

Default repository:

```powershell
cd C:\Users\playm\Documents\self-git\aegis
```

Use a Python interpreter with LangGraph and the project dependencies installed:

```powershell
$env:AEGIS_PYTHON = "<path-to-python-with-aegis-dependencies>"
& $env:AEGIS_PYTHON -m pytest
& $env:AEGIS_PYTHON -m ruff check .
```

Do not use an interpreter that lacks LangGraph dependencies.

## Evidence Output Folder

Each full verification run must create one timestamped folder:

```text
module_test_reports/top_level/TOP_LEVEL_GRAPH_V2_PRODUCTION_VERIFICATION_<YYYYMMDD_HHMMSS>/
```

Required folder contents:

```text
README.md
test_plan_used.md
source/
  source_manifest.json
  source_tree_sha256.txt
  source_snapshot.zip
  source_snapshot_sha256.txt
  source_patch.diff
  source_patch_sha256.txt
fixtures/
  fixture_manifest.json
  route_fixture_manifest.json
  handoff_package_fixture_manifest.json
  resident_registry_fixture_manifest.json
  failure_fixture_manifest.json
  interrupt_fixture_manifest.json
commands/
  pytest_targeted.txt
  pytest_full.txt
  ruff_check.txt
  git_diff_check.txt
  crlf_scan.txt
  source_boundary_scan.txt
  store_boundary_scan.txt
outputs/
  pytest_targeted.out.txt
  pytest_full.out.txt
  ruff_check.out.txt
  git_diff_check.out.txt
  git_status_short.out.txt
  crlf_scan.out.txt
  source_boundary_scan.out.txt
  source_boundary_scan_classification.json
  store_boundary_scan.out.txt
  store_boundary_scan_classification.json
artifacts/
  route_schema_matrix.json
  route_validation_results.jsonl
  flow_result_matrix.json
  normal_flow/
    README.md
    runtime_instance.json
    route_history.jsonl
    package_manifests/
    terminal_state.json
  master_debate_flow/
    README.md
    route_history.jsonl
    package_manifests/
    terminal_state.json
  execution_debate_flow/
    README.md
    route_history.jsonl
    package_manifests/
    terminal_state.json
  test_failure_loop/
    README.md
    route_history.jsonl
    package_manifests/
    terminal_state.json
  failure_stop/
    README.md
    route_history.jsonl
    failure_evidence.json
    terminal_state.json
  interrupt_flow/
    README.md
    route_history.jsonl
    interrupt_package.json
    terminal_state.json
  lock_conflict/
    README.md
    first_runtime_lock.json
    second_runtime_rejection.json
hashes/
  package_manifest_hashes.json
  route_history_hashes.json
  evidence_hashes.json
  source_hashes.json
  fixture_hashes.json
real_agent/
  README.md
  creation_proofs/
  thread_ids.json
  liveness_observations.json
  behavior_summary.md
final_report.md
```

`module_test_reports/` is verification evidence and must remain gitignored.

## Phase 0: Source and Fixture Provenance

### Purpose

Prove that the verification package can be audited later even when the working
tree was dirty during testing.

### Required Source Manifest

`source/source_manifest.json` must record:

1. branch name;
2. commit hash;
3. dirty status;
4. source files under `src/aegis/top_level/`;
5. `tests/test_top_level_graph_v2_runtime.py`;
6. `docs/TOP_LEVEL_GRAPH_V2_DESIGN.md`;
7. `docs/TOP_LEVEL_GRAPH_V2_PRODUCTION_TEST_PLAN.md`;
8. per-file sha256 for every source and test file in scope;
9. `source_patch.diff` sha256 when the working tree is dirty;
10. `source_snapshot.zip` sha256 when a source snapshot is produced.

If the working tree is dirty and the verification package lacks source patch or
source snapshot evidence, the final report must mark the run:

```text
non_archival
```

or:

```text
blocked_for_missing_source_provenance
```

### Required Fixture Manifest

`fixtures/fixture_manifest.json` must list every fixture package used by the
top-level graph tests.

Each fixture entry must include:

1. `fixture_id`;
2. `scenario_name`;
3. input artifact paths;
4. expected source module;
5. expected target module;
6. expected handoff kind;
7. expected terminal status;
8. expected failure, interrupt, route, or closeout result;
9. expected evidence paths;
10. fixture sha256.

Route, handoff, resident registry, failure, and interrupt fixtures must also be
mirrored in their dedicated manifest files.

### Commands

```powershell
git rev-parse --abbrev-ref HEAD *> module_test_reports\top_level\<RUN_ID>\source\branch.txt
git rev-parse HEAD *> module_test_reports\top_level\<RUN_ID>\source\commit.txt
git status --short *> module_test_reports\top_level\<RUN_ID>\source\git_status_short.txt
git diff --binary *> module_test_reports\top_level\<RUN_ID>\source\source_patch.diff
```

### Required Assertions

1. Every file under test has a recorded sha256.
2. Dirty working tree verification includes patch or source snapshot evidence.
3. Every route, handoff, registry, failure, and interrupt scenario has a fixture
   manifest entry.
4. Final report states whether the evidence package is archival or
   non-archival.

## Phase 1: Static Source Boundary Scan

### Purpose

Prove that the parent graph package does not absorb business logic from Master,
Debate, Execution, Test, Final Review, Knowledge or Causal stores.

### Commands

```powershell
rg -n "requirement|debate worker|implementation plan|test evidence|threat finding|causal truth" src\aegis\top_level
rg -n "from aegis.modules|import aegis.modules|knowledge|causal" src\aegis\top_level
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k source -vv
```

### Required Assertions

1. `src/aegis/top_level/` contains parent routing, registry, lock, manifest, and
   state code only.
2. Parent graph source does not import module business implementations.
3. Parent graph source does not write Knowledge / Causal admitted
   truth.
4. Source boundary tests use structural checks where possible, not brittle
   string-only acceptance.

### Evidence

- source scan output
- `outputs/source_boundary_scan_classification.json`
- targeted source-boundary pytest output
- final report excerpt listing allowed and rejected imports

### Classification Requirements

`outputs/source_boundary_scan_classification.json` must classify every relevant
source scan match with:

```json
{
  "match": "string",
  "file": "path",
  "line": 1,
  "classification": "allowed_schema_name|allowed_route_enum|allowed_test_fixture|forbidden_business_import|forbidden_business_call|forbidden_truth_store_write",
  "reason": "string",
  "blocking": false
}
```

The test must not fail only because a forbidden word appears in a schema,
fixture, documentation quote, or negative test. It must fail when the
classification shows a real forbidden parent-graph dependency or side effect.

## Phase 2: Runtime Lock and Instance Identity

### Purpose

Prove that one Aegis runtime binds one canonical project root and that a second
active runtime for the same project is rejected before resident modules are
created.

### Required Scenarios

1. Clean project root acquires lock.
2. Runtime lock writes `runtime_instance.json`.
3. Runtime instance records canonical project root, process id, host, created
   time, and status.
4. Second runtime on the same canonical root is rejected.
5. Lock failure prevents resident subgraph construction.
6. Different project roots may each acquire independent locks.
7. Two startup attempts racing for the same canonical root result in exactly
   one successful lock owner.
8. The losing startup attempt creates no resident modules.
9. A lock owner mismatch cannot release another runtime's lock.
10. Stale lock recovery is not automatic and requires a future explicit recovery
    command or user approval.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "runtime_lock or canonical" -vv
```

### Required Assertions

1. Same-root lock conflict returns a controlled failure.
2. No route history is created for a runtime that never acquired the lock.
3. No resident module is constructed after lock acquisition failure.
4. Runtime lock evidence is written to the verification folder.
5. Race tests prove lock acquisition is atomic enough for local production use.
6. Lock ownership is explicit and release-safe.

## Phase 3: Resident Module Registry

### Purpose

Prove that the parent runtime owns exactly one resident module each for Master,
Debate, Execution, Test, and Final Review.

### Required Scenarios

1. Registry accepts exactly one resident `master`.
2. Registry accepts exactly one resident `debate`.
3. Registry accepts exactly one resident `execution`.
4. Registry accepts exactly one resident `test`.
5. Registry accepts exactly one resident `final_review`.
6. Duplicate resident module registration is rejected.
7. Missing resident module blocks runtime start.
8. Debate worker registration at top-level scope is rejected.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "registry or resident or debate_worker" -vv
```

### Required Assertions

1. Registry shape is deterministic.
2. Resident module ids are stable for the runtime instance.
3. Debate workers remain owned by Debate Leader, not by the parent graph.
4. Registry errors are controlled and evidence-bearing.

## Phase 4: Handoff Package Contract

### Purpose

Prove that every cross-module route carries a compact envelope referencing an
artifact package and that the manifest hash guards package identity.

### Required Scenarios

1. Valid handoff envelope is accepted.
2. Missing package manifest is rejected.
3. Missing `README.md` is rejected.
4. Manifest hash mismatch is rejected.
5. Manifest path outside artifact root is rejected.
6. Inline long-form payload is rejected or excluded from graph state.
7. Package manifests are copied or referenced in verification evidence.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "manifest or envelope or hash or package" -vv
```

### Required Assertions

1. `package_sha256` is computed over the manifest bytes.
2. The parent validates hash and path before route dispatch.
3. The parent does not parse report body text to decide route semantics.
4. Handoff package evidence includes manifest hash records.
5. `hashes/package_manifest_hashes.json` records `manifest_path`,
   `computed_sha256`, `envelope_package_sha256`, `matches`, `package_root`, and
   `required_files_checked`.
6. Every route validation result references the matching package hash row.

## Phase 5: Route Schema Registry

### Purpose

Prove that legal module edges are explicit and invalid edges are rejected even
when modules share the same project runtime.

### Legal Routes

| Source | Target | Expected use |
| --- | --- | --- |
| master | debate | requirement or design dispute |
| master | execution | approved requirement handoff |
| debate | master | Master-requested debate result |
| debate | execution | adjudicated route result |
| execution | debate | non-dominated implementation route dispute |
| execution | test | implementation candidate to test |
| test | execution | failed or incomplete evidence loop |
| test | final_review | passed evidence package |
| final_review | master | final review result |
| master | closeout | runtime terminal closeout |

### Invalid Routes

At minimum:

1. test -> master
2. master -> test
3. debate -> test
4. final_review -> execution
5. final_review -> debate
6. execution -> final_review without Test
7. any module -> Knowledge / Causal admitted truth

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "route or schema or invalid" -vv
```

### Required Assertions

1. Same project membership does not imply route permission.
2. Allowed route requires allowed handoff kind.
3. Invalid route returns controlled `blocked` or `failed` state.
4. Runtime terminal status is accepted only for Master closeout.

### Required Route Evidence

The verification package must include:

1. `artifacts/route_schema_matrix.json`
   - allowed edges;
   - allowed handoff kinds;
   - expected package schema;
   - expected next route.
2. `artifacts/route_validation_results.jsonl`
   - every route attempt;
   - source;
   - target;
   - handoff kind;
   - validation status;
   - package ref;
   - package hash row id;
   - rejection or acceptance reason.
3. `artifacts/flow_result_matrix.json`
   - flow id;
   - expected route sequence;
   - actual route sequence;
   - pass/fail;
   - terminal status.

## Phase 6: Deterministic Parent Flow Tests

### Purpose

Prove that the parent graph can route complete deterministic module outputs
without embedding module logic.

### Required Flows

1. Normal:
   `Master -> Execution -> Test -> Final Review -> Master -> closeout`
2. Master-triggered Debate:
   `Master -> Debate -> Execution -> Test -> Final Review -> Master -> closeout`
3. Execution-triggered Debate:
   `Master -> Execution -> Debate -> Execution -> Test -> Final Review -> Master -> closeout`
4. Test failure loop:
   `Master -> Execution -> Test -> Execution -> Test -> Final Review -> Master -> closeout`
5. Failure stop:
   resident module failure -> evidence preserved -> runtime stopped
6. Interrupt:
   developer interrupt package emitted -> state persisted -> resume decision handled

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -vv
```

### Required Assertions

1. Each route step records a route event.
2. Full route history is persisted to `route_history.jsonl`.
3. Graph state keeps only a bounded route-history tail.
4. Terminal state includes closeout package ref.
5. Failure stop does not continue routing.
6. Interrupt state is inspectable and resumable.
7. `flow_result_matrix.json` proves expected and actual route sequences match.

## Phase 7: Bounded State and Artifact Persistence

### Purpose

Prove that parent graph state does not grow with long reports or full route
history while preserving enough artifact evidence for audit.

### Required Scenarios

1. Many route events exceed the in-state tail limit.
2. In-state history remains bounded.
3. Full route history remains complete in file artifact.
4. Large manifest metadata remains in package files, not graph state.
5. Terminal state records refs and hashes, not long-form package bodies.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "history or bounded or artifact" -vv
```

### Required Assertions

1. State size remains bounded under repeated route steps.
2. `route_history.jsonl` has every event in order.
3. Artifact hashes are deterministic.
4. No long-form markdown body appears in parent graph state.

## Phase 8: Failure, Stop, and Evidence Preservation

### Purpose

Prove that an observable resident module failure stops the entire Aegis runtime
and preserves enough evidence for developer diagnosis.

### Required Scenarios

1. Module returns failed handoff result.
2. Module raises controlled runtime error.
3. Route schema rejects invalid handoff.
4. Manifest hash mismatch occurs.
5. Failure evidence is written before runtime terminal failure.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "failure or failed or stop" -vv
```

### Required Assertions

1. Failure does not trigger automatic resident module reconstruction.
2. Failure does not continue to the next route.
3. Failure evidence records source module, attempted target, route id, reason,
   package ref, and timestamp.
4. Failure terminal state is distinct from successful Master closeout.

## Phase 9: Restart and Resume Semantics

### Purpose

Prove that persisted runtime metadata can be inspected after restart without
claiming unverified live-agent continuity.

### Required Scenarios

1. Runtime writes instance metadata and route history.
2. Process restart can inspect persisted metadata.
3. Restarted runtime can recover logical module ids.
4. Restarted runtime must not mark old in-memory agents as live without monitor
   verification.
5. Resume after interrupt uses the same top-level `thread_id`.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "restart or resume or interrupt or thread" -vv
```

### Required Assertions

1. Recovered metadata is labeled as recovered metadata.
2. Live liveness is labeled unknown unless monitor verification exists.
3. The parent graph does not fake agent liveness after restart.
4. Resume appends route history instead of overwriting it.

## Phase 10: Real Resident-Agent Acceptance Track

### Purpose

Prove behavior in a realistic runtime where resident module agents are actually
created and observable. This track is required before production acceptance, but
it is separate from deterministic CI.

### Required Real Agents

1. Master PM / review resident identity
2. Debate Leader resident identity
3. Execution executor / reviewer resident identities
4. Test executor / checkers / report handler resident identities
5. Final Review Leader resident identity

Debate workers are excluded from global top-level monitoring because their
lifecycle is owned by Debate Leader.

### Required Proof Fields

Each resident proof must record:

1. module id
2. resident agent role id
3. thread id or runtime identity
4. created by top-level runtime or module owner
5. creation time
6. model request
7. reasoning budget request
8. proof statement
9. output artifact path
10. sha256 of proof file

### Required Observations

1. Each resident agent remains reachable across at least one relevant route.
2. Parent graph records only resident ids and monitor refs.
3. Parent graph does not inspect agent reasoning text.
4. Parent graph stops if a required resident agent is missing or failed.
5. A timeout in an external nested-Codex command is not treated as success by
   itself; success requires later proof or observable output.

### Evidence

- `real_agent/thread_ids.json`
- `real_agent/creation_proofs/*.json`
- `real_agent/liveness_observations.json`
- `real_agent/behavior_summary.md`
- sha256 table in final report

## Phase 11: Store Boundary Verification

### Purpose

Prove that the parent graph does not mutate Knowledge or Causal
admitted truth and does not use LangGraph Store as project memory.

### Commands

```powershell
rg -n "store=|LangGraph Store|knowledge|causal|admitted_truth|global_causal" src\aegis\top_level tests\test_top_level_graph_v2_runtime.py
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "store or truth or boundary" -vv
```

### Required Assertions

1. No `store=` is passed to LangGraph compile or invocation for project memory.
2. Parent graph state stores refs and candidates only.
3. Parent graph does not write admitted truth.
4. Closeout package may reference candidate artifacts, but it does not promote
   them.

### Classification Requirements

`outputs/store_boundary_scan_classification.json` must classify every relevant
store-boundary match with:

```json
{
  "match": "string",
  "file": "path",
  "line": 1,
  "classification": "allowed_negative_test|allowed_schema_field|allowed_documentation_quote|forbidden_langgraph_store_use|forbidden_truth_store_write",
  "reason": "string",
  "blocking": false
}
```

The test must fail on real LangGraph Store usage for project memory or admitted
truth-store mutation. It must not fail only because store names appear in
negative tests or boundary documentation.

## Phase 12: Performance and Scale Smoke Tests

### Purpose

Prove that parent routing overhead remains bounded under repeated route events
and large artifact packages.

### Required Scenarios

1. At least 1,000 route events in a synthetic route-history stress case.
2. At least 100 handoff package manifests with deterministic hash validation.
3. Large markdown report files referenced by path only.
4. No material in-state growth beyond configured bounded fields.

### Commands

```powershell
& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -k "stress or scale or bounded" -vv
```

### Required Metrics

Record:

1. route event count
2. route-history file size
3. in-state route-history tail length
4. maximum parent state serialized size if measured
5. manifest validation duration if measured

This is not a final performance benchmark. It is a production-risk smoke test.

### Required Pass Thresholds

1. route-history tail length is less than or equal to the configured tail limit;
2. `route_history.jsonl` line count equals the total route event count;
3. all synthetic manifests validate successfully;
4. every rejected synthetic manifest is rejected for the expected reason;
5. no long-form markdown body appears in serialized parent graph state;
6. no route-history event is lost from the persisted log.

## Phase 13: Full Local Verification

### Commands

```powershell
cd C:\Users\playm\Documents\self-git\aegis
$env:AEGIS_PYTHON = "<path-to-python-with-aegis-dependencies>"

& $env:AEGIS_PYTHON -m pytest .\tests\test_top_level_graph_v2_runtime.py -vv `
  *> module_test_reports\top_level\<RUN_ID>\outputs\pytest_targeted.out.txt

& $env:AEGIS_PYTHON -m pytest -vv `
  *> module_test_reports\top_level\<RUN_ID>\outputs\pytest_full.out.txt

& $env:AEGIS_PYTHON -m ruff check . `
  *> module_test_reports\top_level\<RUN_ID>\outputs\ruff_check.out.txt

git diff --check `
  *> module_test_reports\top_level\<RUN_ID>\outputs\git_diff_check.out.txt

git status --short `
  *> module_test_reports\top_level\<RUN_ID>\outputs\git_status_short.out.txt
```

### Packaging Commands

The verification run must also generate source and fixture provenance:

```powershell
git rev-parse --abbrev-ref HEAD *> module_test_reports\top_level\<RUN_ID>\source\branch.txt
git rev-parse HEAD *> module_test_reports\top_level\<RUN_ID>\source\commit.txt
git status --short *> module_test_reports\top_level\<RUN_ID>\source\git_status_short.txt
git diff --binary *> module_test_reports\top_level\<RUN_ID>\source\source_patch.diff

# Produce source_manifest.json, fixture_manifest.json, route_schema_matrix.json,
# route_validation_results.jsonl, flow_result_matrix.json, and hash tables with
# the repository verification helper or an equivalent deterministic script.
```

### Required Assertions

1. targeted top-level tests pass;
2. full pytest suite passes;
3. ruff passes;
4. `git diff --check` passes;
5. git status contains no runtime/cache/checkpoint/private-key artifacts;
6. no verification evidence is committed from `module_test_reports/`;
7. top-level graph source and tests remain the only runtime changes for this
   phase, apart from documentation.
8. source provenance exists and is archival unless explicitly marked
   non-archival.
9. fixture provenance exists for every executed scenario.

## Production Acceptance Criteria

Top-Level Graph v2 is accepted only if all of the following are true:

1. Static source boundary scan passes.
2. Runtime lock tests pass.
3. Resident registry tests pass.
4. Handoff package validation tests pass.
5. Route schema registry tests pass.
6. Normal parent flow passes.
7. Master-triggered Debate parent flow passes.
8. Execution-triggered Debate parent flow passes.
9. Test failure loop passes.
10. Failure stop preserves evidence and halts runtime.
11. Interrupt package is preserved and resumable.
12. Route history is bounded in state and complete on disk.
13. Restart/resume semantics do not fake live-agent liveness.
14. Store boundary verification passes.
15. Full pytest suite passes.
16. Ruff passes.
17. `git diff --check` passes.
18. Real resident-agent acceptance track has either passed or is explicitly
    reported as blocked. It must not be silently omitted.
19. Source provenance exists and is archival, or the run is explicitly marked
    non-archival.
20. Fixture provenance exists for every route, handoff, registry, failure, and
    interrupt scenario.
21. Source and store scan matches are structurally classified.
22. Route and flow matrices match the actual persisted route history.

## Report Requirements

The final verification report must include:

1. repository branch and commit;
2. exact Python interpreter used;
3. exact commands run;
4. targeted pytest summary;
5. full pytest summary;
6. ruff summary;
7. `git diff --check` result;
8. runtime lock evidence;
9. resident registry evidence;
10. route schema matrix;
11. package manifest hash table;
12. route history excerpts for every required flow;
13. failure stop evidence;
14. interrupt/resume evidence;
15. state-size or bounded-history evidence;
16. source-boundary scan evidence;
17. store-boundary scan evidence;
18. real-agent proof table if real-agent acceptance was run;
19. clear distinction between deterministic runtime acceptance and real-agent
    behavior acceptance;
20. remaining gaps.
21. source manifest and source hash table;
22. fixture manifests and fixture hash table;
23. source/store scan classification summaries;
24. route validation results matrix;
25. final recommendation enum.

## Final Recommendation Enum

The final report must use exactly one of these classifications:

```text
deterministic_runtime_accepted_real_agent_not_run
deterministic_runtime_accepted_real_agent_blocked
deterministic_runtime_accepted_real_agent_accepted
runtime_implementation_gap_exists
contract_ambiguity_blocks_runtime_test
verification_blocked_missing_archival_evidence
```

`not_run` means no real resident-agent acceptance was attempted. `blocked`
means it was attempted but could not complete for a recorded external or tool
reason. `accepted` requires real proof files, thread ids, and liveness
observations.

## Known Non-Acceptance Conditions

Any of the following fails production acceptance:

1. parent graph imports module business logic;
2. parent graph writes Knowledge / Causal admitted truth;
3. parent graph carries long-form package bodies in graph state;
4. same project membership allows an otherwise invalid route;
5. failed resident module is silently rebuilt;
6. stale lock is silently stolen;
7. restart metadata is claimed as live agent verification;
8. Debate workers are registered as top-level resident modules;
9. manifest hash mismatch is accepted;
10. final closeout occurs without Final Review result package;
11. real-agent acceptance is claimed without real proof files or thread ids.
12. dirty working tree verification lacks source patch or source snapshot
    evidence but still claims archival acceptance;
13. source/store scan matches are not classified;
14. flow result matrix does not match persisted route history.

## Expected Current Result

For the current implementation stage, the expected result is:

```text
deterministic top-level runtime tests: pass
full repository tests: pass
source boundary scan: pass
real resident-agent acceptance: not yet claimed unless separately run
future lifecycle/token monitor: not implemented in this phase
```

If deterministic tests pass but real resident-agent acceptance is not run, the
correct final classification is:

```text
Top-Level Graph v2 deterministic runtime acceptance passed.
Real resident-agent acceptance remains pending or separately scoped.
Production closure is not claimed until real-agent evidence is attached.
```
