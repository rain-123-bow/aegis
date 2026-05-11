# Phase 20B Test Real Worker Full Acceptance Report

## Summary

```yaml
acceptance_status: accepted_real_test_worker_closure
phase_boundary: real_test_worker_acceptance_not_production_test_lifecycle
aegis_repo: C:/Users/playm/Documents/self-git/aegis
sandbox_repo: C:/Users/playm/Documents/self-git/aegis-execution-sandbox
sandbox_remote: git@github.com:rain-123-bow/aegis-execution-sandbox.git
source_handoff: Execution Phase 19B / Test Phase 20A
base_branch: main
integration_branch: aegis/phase19b/integration-001
integration_commit: 386c2f5e1cb54991f1c4f720fa96ed98fa3b3ec4
test_workers:
  - test_worker__phase20b-test-real-workers-001__route_sandbox_pytest
  - test_worker__phase20b-test-real-workers-001__route_changed_files_scope
proof_audit_status: passed
output_audit_status: passed
route_results:
  route.sandbox_pytest: passed
  route.changed_files_scope: passed
final_test_result: passed
next_route: final_review
production_test_lifecycle_closure: false
remote_push_performed: false
pr_created: false
release_performed: false
production_merge_performed: false
global_causal_truth_mutation: false
```

Phase 20B passed. The Test Leader created exactly two real nested-Codex/Codex Test Worker agents, each Worker preserved proof, output, route evidence, and private work evidence, and strict proof/output audits passed.

This is real Test Worker acceptance closure. It is not production Test lifecycle closure, production CI closure, remote branch governance closure, release closure, production sign-off, or global causal truth closure.

## Patch Application

The instruction path referenced:

```text
C:\Users\playm\Documents\self-git\patch\aegis_test_phase20b_real_worker_patch_v0_2\aegis_test_phase20b_real_worker_patch_v0_2
```

That path was not present locally. The supplied and inspected v0.2 patch was present at:

```text
C:\Users\playm\Documents\AAA\aegis_test_phase20b_real_worker_patch_v0_2\aegis_test_phase20b_real_worker_patch_v0_2
```

The v0.2 patch dry-run and apply commands completed cleanly from the available path.

Added files:

- `aegis-master-kit/organization/departments/test/TEST_20B_ACCEPTANCE_CONTRACT.md`
- `aegis-master-kit/organization/departments/test/TEST_REAL_WORKER_CONTRACT.md`
- `aegis-runtime/test/aegis_test_runtime/real_worker_cli.py`
- `aegis-runtime/test/aegis_test_runtime/real_workers.py`
- `aegis-runtime/test/tests/test_test_real_worker_acceptance.py`
- `runtime_test_reports/PHASE_20B_TEST_REAL_WORKER_PATCH_PLAN.md`

Patched files:

- `MODEL_REASONING_BUDGET_POLICY.yaml`
- `aegis-master-kit/organization/departments/test/MANIFEST.yaml`
- `aegis-runtime/test/pyproject.toml`
- `aegis-runtime/test/aegis_test_runtime/__init__.py`

## Model Policy

`MODEL_REASONING_BUDGET_POLICY.yaml` now defines:

```yaml
test_worker:
  role_id: test_worker
  model: gpt-5.5
  reasoning_budget: high
  fallback_allowed: false
  dynamic_adjustment_allowed: false
```

`deferred_profiles` is now:

```yaml
deferred_profiles: []
```

`test_worker` is not deferred.

## Commands Run

```powershell
py -3.13 "C:\Users\playm\Documents\AAA\aegis_test_phase20b_real_worker_patch_v0_2\aegis_test_phase20b_real_worker_patch_v0_2\apply_aegis_test_phase20b_real_worker_patch.py" --repo-root C:\Users\playm\Documents\self-git\aegis --dry-run
py -3.13 "C:\Users\playm\Documents\AAA\aegis_test_phase20b_real_worker_patch_v0_2\aegis_test_phase20b_real_worker_patch_v0_2\apply_aegis_test_phase20b_real_worker_patch.py" --repo-root C:\Users\playm\Documents\self-git\aegis

py -3.13 -m venv .venv-test-phase20b
.\.venv-test-phase20b\Scripts\python.exe -m pip install -U pip
.\.venv-test-phase20b\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-phase20b\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-phase20b\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_test_real_worker_acceptance.py -vv
.\.venv-test-phase20b\Scripts\python.exe -m pytest .\aegis-runtime\test -vv

.\.venv-test-phase20b\Scripts\python.exe -m aegis_test_runtime.real_worker_cli prepare-requests --policy .\MODEL_REASONING_BUDGET_POLICY.yaml --validation-package .\.aegis-phase20b-test-real-worker\inputs\phase20b_validation_package.json --run-id phase20b-test-real-workers-001 --output-dir .\.aegis-phase20b-test-real-worker\prepared --proof-dir .\.aegis-phase20b-test-real-worker\test_worker_proofs --worker-output-dir .\.aegis-phase20b-test-real-worker\test_worker_outputs

.\.venv-test-phase20b\Scripts\python.exe -m aegis_test_runtime.real_worker_cli audit-proofs --expected .\.aegis-phase20b-test-real-worker\prepared\expected_test_worker_proofs.json --proof-dir .\.aegis-phase20b-test-real-worker\test_worker_proofs --output .\.aegis-phase20b-test-real-worker\test_worker_proof_audit_summary.json
.\.venv-test-phase20b\Scripts\python.exe -m aegis_test_runtime.real_worker_cli audit-outputs --expected .\.aegis-phase20b-test-real-worker\prepared\expected_test_worker_outputs.json --worker-output-dir .\.aegis-phase20b-test-real-worker\test_worker_outputs --output .\.aegis-phase20b-test-real-worker\test_worker_output_audit_summary.json

git -C C:\Users\playm\Documents\self-git\aegis-execution-sandbox checkout aegis/phase19b/integration-001
.\.venv\Scripts\python.exe -m pytest -vv

git -C C:\Users\playm\Documents\self-git\aegis diff --check
git -C C:\Users\playm\Documents\self-git\aegis status --short
git -C C:\Users\playm\Documents\self-git\aegis-execution-sandbox status --short
```

## Test Results

Targeted Phase 20B tests:

```text
5 passed in 0.05s
```

Full Test runtime suite:

```text
16 passed, 1 warning in 3.15s
```

Direct sandbox pytest cross-check:

```text
14 passed in 0.02s
```

The warning is the existing pytest collection warning for the exception class `TestHandoffValidationError`; it does not affect Phase 20B acceptance.

## Real Agent Creation

Master created only the Test Leader:

```yaml
agent_id: test
role_id: test_leader
requested_model: gpt-5.5
requested_reasoning_effort: high
```

Test Leader created exactly two real nested-Codex/Codex Test Workers:

```yaml
created_by: test_leader_phase20b
creation_tool: mcp__nested_codex__.codex
actual_workers_created_by_leader: true
worker_count: 2
no_more_than_two_workers_created: true
```

Workers:

| worker_id | route_id | nested_codex_thread_id |
| --- | --- | --- |
| `test_worker__phase20b-test-real-workers-001__route_sandbox_pytest` | `route.sandbox_pytest` | `019e159e-1ea2-7d82-8a69-6003ed363016` |
| `test_worker__phase20b-test-real-workers-001__route_changed_files_scope` | `route.changed_files_scope` | `019e15a1-3323-7b12-9d34-c9894af68c70` |

The Test Leader proof is:

```text
.aegis-phase20b-test-real-worker/leader_proofs/test_leader_phase20b_proof.json
```

## Worker Proof Audit

Proof audit:

```yaml
status: passed
audited_count: 2
```

Worker proof hashes:

| worker_id | route_id | sha256 |
| --- | --- | --- |
| `test_worker__phase20b-test-real-workers-001__route_sandbox_pytest` | `route.sandbox_pytest` | `1759eccba3a20705e8eca57825be136a2c74b23be9c47304189788f46344dd2b` |
| `test_worker__phase20b-test-real-workers-001__route_changed_files_scope` | `route.changed_files_scope` | `c997d0ebff7241d2daeb0b5fb0a87b379f65b2959253b1d66bb6fa44de89323d` |

## Worker Output Audit

Output audit:

```yaml
status: passed
audited_count: 2
```

Worker output hashes:

| worker_id | route_id | sha256 |
| --- | --- | --- |
| `test_worker__phase20b-test-real-workers-001__route_sandbox_pytest` | `route.sandbox_pytest` | `c98ed2d30c8b9347db27345a9c4fa602eaf924ed168224e9b3d8c6b5fe8de2ae` |
| `test_worker__phase20b-test-real-workers-001__route_changed_files_scope` | `route.changed_files_scope` | `71eae9e5e1b8ed520bd0961c5efd6b2376cd61a1e60f8c5a8e307e2608d301cd` |

## Route Results

```yaml
route.sandbox_pytest: passed
route.changed_files_scope: passed
```

`route.sandbox_pytest` ran sandbox pytest on:

```text
C:\Users\playm\Documents\self-git\aegis-execution-sandbox
```

Result:

```text
14 passed
```

`route.changed_files_scope` validated that the integration branch changed exactly the Phase 19B files:

```text
src/aegis_execution_sandbox/models.py
src/aegis_execution_sandbox/reasoning.py
tests/test_phase19b_route_reason.py
tests/test_phase19b_workitem_category.py
```

## Aggregation and Final Handoff

`test_worker_aggregation_summary.json` records:

```yaml
acceptance_status: accepted_real_test_worker_closure
proof_audit_status: passed
output_audit_status: passed
all_mandatory_routes_passed: true
next_route: final_review
production_test_lifecycle_closure: false
```

`final_test_result_phase20b.json` records:

```yaml
result: passed
status: scoped_test_conclusion
causal_status: causal_candidate
next_route: final_review
```

`final_review_handoff_package_phase20b.json` records:

```yaml
handoff_kind: test_real_worker_result
target: final_review
status: ready_for_final_review
final_test_result: passed
```

## Evidence Directories

Every independent Test Worker preserved a private evidence folder:

- `.aegis-phase20b-test-real-worker/worker_work_evidence/test_worker__phase20b-test-real-workers-001__route_sandbox_pytest/`
- `.aegis-phase20b-test-real-worker/worker_work_evidence/test_worker__phase20b-test-real-workers-001__route_changed_files_scope/`

Each folder includes proof, output, prompt, command log, git status before/after, diff evidence, stdout/stderr, route evidence, and causal summary. The pytest worker includes `pytest_output.txt`; the changed-files worker includes `inspection_notes.md`.

## Required Answers

1. Patch applied cleanly: yes.
2. `MODEL_REASONING_BUDGET_POLICY.yaml` defines `test_worker` as `gpt-5.5/high`: yes.
3. `test_worker` removed from `deferred_profiles`: yes.
4. Targeted Phase 20B tests passed: yes, `5 passed`.
5. Full Test runtime tests passed: yes, `16 passed`.
6. Master created only Test Leader: yes.
7. Test Leader created Test Workers: yes, exactly two real nested-Codex/Codex workers.
8. Each Test Worker proof exists and passed strict audit: yes.
9. Each Test Worker output exists and passed strict audit: yes.
10. Every independent Test Worker preserved a work evidence directory: yes.
11. `route.sandbox_pytest` passed: yes.
12. `route.changed_files_scope` passed: yes.
13. Final Test result is `passed`: yes.
14. Final result routes to `final_review`: yes.
15. Implementation code modified by Test: no.
16. Remote push, PR, remote merge, release, production sign-off, or global causal mutation occurred: no.
17. Why this is not production Test lifecycle closure: Phase 20B validates real request-scoped Test Worker acceptance and evidence production only. It does not provide production CI, durable environment provisioning, remote branch governance, external artifact backend, release authority, production sign-off, or global causal merge.

## Git State

Aegis repo:

```text
git diff --check: clean
```

Sandbox repo:

```yaml
branch: aegis/phase19b/integration-001
head: 386c2f5e1cb54991f1c4f720fa96ed98fa3b3ec4
status_short: ""
```

The sandbox ending on `aegis/phase19b/integration-001` is expected.

## Artifact Package

The artifact package is:

```text
C:\Users\playm\Documents\AAA\phase20b_test_real_worker_full_acceptance_artifacts.zip
```

It contains the report, validation package, prepared worker requests/prompts, leader proof, worker proofs, worker outputs, private worker evidence, leader evidence, aggregation outputs, audit summaries, and command evidence. It excludes virtual environments, caches, `__pycache__`, `.pyc`, large unrelated repo copies, secrets, SSH keys, and tokens.

## Final Verdict

Phase 20B is accepted as `accepted_real_test_worker_closure`.

It closes real Test Worker acceptance at demo/runtime level. It does not close production Test lifecycle.
