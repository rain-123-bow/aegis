# Phase 30A Organization Governance Ambiguity Hardening Report

## Scope

This phase fixes the governance ambiguities exposed by the observed Master organization behavior probe.

It does not add new top-level routes, does not change router route enforcement, and does not claim production closure.

## Issues Addressed

### Model fallback semantics

Fixed ambiguity:

- `fallback_allowed: false` could be read as conflicting with the root policy's explicit `gpt-5.5 -> gpt-5.4` fallback path.

Current rule:

- roles cannot self-authorize fallback;
- provider-default fallback is forbidden;
- only root policy may authorize `gpt-5.5 -> gpt-5.4` fallback;
- fallback requires objective unavailability evidence;
- reasoning budget must remain unchanged;
- if a tool cannot independently attest actual resolved model/budget, the audit record must use `requested_policy_only` or `unattested`.

### Topology patch admission

Fixed ambiguity:

- a missing route request such as `test -> master` had no formal admission path.

Current rule:

- missing-edge runtime use must be rejected;
- topology-change requests may be classified as `reject_runtime_route_request`, `admit_topology_patch_investigation`, `admit_topology_patch_task`, or `block_topology_patch`;
- investigation or admission does not activate the requested edge;
- active topology remains `master_top_level_v1.yaml` until a separate accepted topology patch changes it.

### Bootstrap authority versus runtime route authority

Fixed ambiguity:

- Master can bootstrap Test and Final Review Leaders, but that could be confused with runtime send authority.

Current rule:

- top-level Leader creation is bootstrap/governance setup authority;
- runtime messaging still obeys the directed route table;
- Master runtime outgoing edges remain only `master -> debate` and `master -> execution` in v1;
- Master must not fabricate `master -> test` or `master -> final_review` runtime messages.

### Leader proof and task output boundaries

Fixed ambiguity:

- leader proof creation and later consultation/task output writes could share a proof-only write boundary.

Current rule:

- nested-Codex create-agent requests must carry a proof path and a separate task output directory;
- responses must include non-empty `thread_id`;
- bootstrap reports must record `thread_id`, proof path, task output directory, and model-attestation status.

## Files Changed

- `MODEL_REASONING_BUDGET_POLICY.yaml`
- `README.md`
- `aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL.md`
- `aegis-master-kit/organization/ORGANIZATION_MODEL.md`
- `aegis-master-kit/organization/contracts/TOP_LEVEL_ROUTE_TOPOLOGY_CONTRACT.md`
- `aegis-master-kit/organization/contracts/TOPOLOGY_PATCH_ADMISSION_CONTRACT.md`
- `aegis-master-kit/organization/departments/final_review/FINAL_REVIEW_LEADER_OPERATIONAL_SKILL.md`
- `aegis-master-kit/organization/departments/test/TEST_LEADER_OPERATIONAL_SKILL.md`
- `aegis-master-kit/organization/departments/test/TEST_WORKER_OPERATIONAL_SKILL.md`
- `aegis-runtime/master/NESTED_CODEX_MCP_CREATE_AGENT_CONTRACT.md`
- `aegis-runtime/master/README.md`
- `aegis-runtime/master/aegis_master_runtime/leader_bootstrap.py`
- `aegis-runtime/master/aegis_master_runtime/mcp_client.py`
- `aegis-runtime/master/aegis_master_runtime/models.py`
- `aegis-runtime/master/aegis_master_runtime/operational_skill.py`
- `aegis-runtime/master/aegis_master_runtime/policy.py`
- `aegis-runtime/master/tests/test_master_top_level_policy_and_bootstrap.py`
- `aegis-runtime/master/tests/test_phase24a_master_operational_workflow_skill.py`
- `aegis-runtime/master/tests/test_phase30a_governance_ambiguity_hardening.py`

## Validation

Commands run:

```powershell
.\.venv-master-skill-phase24a\Scripts\python.exe -m compileall .\aegis-runtime\master\aegis_master_runtime
.\.venv-master-skill-phase24a\Scripts\python.exe -m pytest .\aegis-runtime\master -q
git diff --check
```

Results:

```text
compileall: passed
pytest: 35 passed, 2 skipped in 0.16s
git diff --check: passed
```

Text scan:

```powershell
rg -n "fallback is forbidden because `fallback_allowed: false`|If the active.*fallback_allowed: false.*fallback is forbidden|minimum_accepted_model: gpt-5.5|fallback and silent downgrade forbidden|no fallback in the current phase" README.md MODEL_REASONING_BUDGET_POLICY.yaml aegis-master-kit/organization/departments aegis-master-kit/master aegis-runtime/master
```

Result:

```text
no stale fallback-conflict wording found
```

Line-ending audit:

```text
LF audit passed for Phase 30A changed text files
```

## Boundary Confirmation

- No router route-table expansion.
- No `test -> master` route added.
- No top-level topology edge added.
- No production closure claimed.
- No remote push, PR, merge, release, deployment, or external sign-off.
- No Archive / Knowledge / Causal production store mutation.

## Remaining Issues

The repository can now record `model_attestation_status`, but it still cannot independently prove actual resolved nested-Codex model and reasoning budget if the external nested-codex tool does not expose that metadata. This remains a production/tooling hardening topic.
