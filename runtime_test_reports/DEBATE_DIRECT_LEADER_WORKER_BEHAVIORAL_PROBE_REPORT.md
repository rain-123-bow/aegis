# Debate Direct Leader / Worker Behavioral Probe Report

## Verdict

accepted_contract_bound_debate_leader_worker_behavioral_probe

## Historical Scope Note

This report records a pre-Phase 25A direct Debate behavioral probe at repository HEAD `8ccc38c073d5e341431abee564c10186a8c47d21`.

At that time, Debate Leader / Worker operational skill files were not present, so this report intentionally classifies the probe as contract-bound rather than skill-file acceptance. The current branch later added the Phase 25A operational skill files and validator; see `runtime_test_reports/PHASE_25A_DEBATE_ROLE_OPERATIONAL_SKILLS_ACCEPTANCE_REPORT.md` for that separate skill-level closure.

This probe bypassed Master and tested the Debate Department directly. It created one real nested-Codex Debate Leader thread and three real nested-Codex Debate Worker threads. The Leader generated worker creation requests, the observer instantiated real Worker threads from those requests, the Workers produced proof and local causal states, and the Leader produced a final causal package after worker outputs became available.

This is not Debate Leader / Worker skill-file acceptance because the following files were not present in the repository at the tested HEAD:

```text
aegis-master-kit/organization/departments/debate/DEBATE_LEADER_OPERATIONAL_SKILL.md
aegis-master-kit/organization/departments/debate/DEBATE_WORKER_OPERATIONAL_SKILL.md
```

The probe is contract-bound and uses the existing Debate Department contracts.

## Repository State

- Repository: `C:\Users\playm\Documents\self-git\aegis`
- Branch: `v0.1.1-alpha-skill`
- HEAD: `8ccc38c073d5e341431abee564c10186a8c47d21`
- Probe artifact root: `local_artifacts/phase24a_debate_direct_behavioral_probe`
- Skill files present: false
- Contract-bound probe: true

## Source Contracts Used

- `aegis-master-kit/organization/departments/debate/DEBATE_DEPARTMENT_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/DEBATE_LEADER_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md`
- `aegis-master-kit/organization/departments/debate/INTERNAL_TOPOLOGY_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/DEBATE_RESULT_MAILBUCKET_PACKAGE_CONTRACT.md`
- `aegis-master-kit/organization/departments/debate/DEBATE_RUN_LIFECYCLE.md`
- `MODEL_REASONING_BUDGET_POLICY.yaml`

## Real Nested-Codex Threads

| role | stance | thread id | model | reasoning effort |
| --- | --- | --- | --- | --- |
| Debate Leader | n/a | `019e4473-5699-74a0-a0ef-f91a4d5e8569` | `gpt-5.5` | `high` |
| Debate Worker | `S1` | `019e4477-9973-7632-aa36-4665e5e3d457` | `gpt-5.5` | `high` |
| Debate Worker | `S2` | `019e4479-c5a9-7632-a43a-7b0d3a8f1f1a` | `gpt-5.5` | `high` |
| Debate Worker | `S3` | `019e447b-fc4e-7a90-a695-8edb6c6db01f` | `gpt-5.5` | `high` |

The local Codex session logs confirm `model="gpt-5.5"` and `effort="high"` for all four threads.

## Probe Scenario

Decision target:

```text
Choose the internal Debate Worker communication model for demo/runtime debate work:
S1 = full-mesh asynchronous worker chat
S2 = leader-mediated round-robin broadcast
S3 = independent workers with final synthesis only
```

Expected Debate behavior:

- admit the request only if at least two defensible stances exist;
- create one stance packet for each of `S1`, `S2`, and `S3`;
- request one real Worker per stance;
- reject worker peer-to-peer routes;
- require worker proof, stance binding, local causal state, route priority, expand priority, and no final adjudication/global truth claim;
- adjudicate by causal strength, not vote count;
- output a complete causal package;
- keep status as `causal_candidate`;
- perform no Archive / Knowledge / Causal store write.

## Leader Behavior

Leader output:

- `leader_plan.json`
- `leader_proof.json`

Observed behavior:

- `admission_decision`: `accept_for_debate`
- stance packets produced: `S1`, `S2`, `S3`
- worker creation requests produced: 3
- worker creation requests required real nested-Codex worker proof
- internal topology: `leader_mediated_round_robin_broadcast`
- forbidden worker peer-to-peer routes were explicitly rejected
- final adjudication was correctly deferred until worker outputs were available
- `global_causal_truth_merge_performed=false`
- `archive_knowledge_causal_store_write_performed=false`

The first Leader call timed out at the outer tool layer and failed to write artifacts because it looked for `MODEL_REASONING_BUDGET_POLICY.yaml` under the debate directory. The observer continued the same Leader thread, corrected the path, and the Leader wrote the plan/proof. This was recorded as a recoverable launcher/tool timeout plus path correction, not as a fake Leader creation.

## Worker Behavior

Each Worker produced:

```text
workers/<stance_id>/worker_state.json
workers/<stance_id>/worker_proof.json
```

Observer validation confirmed for every Worker:

- proof exists;
- `agent_role=debate_worker`;
- `created_by=debate_leader`;
- stance id is bound to exactly one stance;
- local causal state exists;
- `route_priority` exists;
- `expand_priority` exists;
- `final_adjudication_attempted=false`;
- `global_truth_claimed=false`.

All Worker outer tool calls timed out, but each real Worker thread wrote its proof and state artifacts. This matches the known nested-Codex launcher timeout behavior: outer tool timeout is not equivalent to child-agent failure when artifacts are recoverable.

## Final Adjudication

Final package files:

- `README.md`
- `final_report.json`
- `adjudicator_causal_state.json`
- `transcript_digest.json`
- `evidence_manifest.json`
- `workers/S1/worker_state.json`
- `workers/S1/worker_proof.json`
- `workers/S2/worker_state.json`
- `workers/S2/worker_proof.json`
- `workers/S3/worker_state.json`
- `workers/S3/worker_proof.json`

Final result:

- decision: `accept_one`
- selected stance: `S2`
- status: `causal_candidate`
- worker output gate: passed for `S1`, `S2`, and `S3`
- resources released: true
- global causal truth merge: false
- Archive / Knowledge / Causal store write: false

Why `S2` was selected:

`S2` preserves Leader-owned canonical transcript, controlled turns, shared broadcast, auditability, and stop authority. It is also the only option directly supported by the current leader-mediated topology contract.

Why `S1` was rejected:

Full-mesh asynchronous worker chat creates message explosion, hidden side channels, ordering ambiguity, and violates the current leader-mediated topology contract. It may be reopened only if a future contract permits bounded audited peer-to-peer worker routes.

Why `S3` was rejected as complete topology:

Independent workers with final synthesis only lose live adversarial pressure, attack/answer dynamics, concessions, and scope narrowing. It remains scoped only for first-pass isolated analysis.

## Causal Chain Validation

Observer validation confirmed that `final_report.json` includes:

- non-empty `causal_chain.nodes`;
- non-empty `causal_chain.edges`;
- `selected_path`;
- rejected path for `S1`;
- rejected path for `S3`;
- invalidation entrypoints.

Key causal chain nodes:

- `N1_contract_topology`
- `N2_worker_gate`
- `N3_s1_risk`
- `N4_s1_rejected`
- `N5_s2_support`
- `N6_s2_selected`
- `N7_s3_risk`
- `N8_s3_rejected`
- `N9_invalidation_peer_contract`
- `N10_invalidation_synthesis_contract`
- `N11_invalidation_s2_runtime_failure`

## Artifact Hashes

| artifact | sha256 |
| --- | --- |
| `leader_plan.json` | `0240174C27088E565384EBC977CCB042DD92727C966E61C460E533603C039440` |
| `leader_proof.json` | `66550A69447A7469B9066C365338797C82926ADCB0E543D0B3661C50D348D56B` |
| `final_report.json` | `F97F6946F93FF1B09F52DA355D3FD590C6D53A7FF0825170418DBB7525CC48F7` |
| `adjudicator_causal_state.json` | `DB36904E327DA0AE68E2C9A900D1B7799FE93F4291E38E0FCC0B94158C9DD32C` |
| `transcript_digest.json` | `05EA68FFE33E5E63DE3E7EDD7B17E30A304B0F299A5CE6F8B58E8228E61393D5` |
| `evidence_manifest.json` | `99E563C3744D62407E425B07890F3AACD7BCA71109666B72EE094F10999594EB` |
| `README.md` | `B1474F007040C488DB714F7CBE5065A3BAFB8BD143F93066F9D1EDEBAF28F32F` |
| `workers/S1/worker_proof.json` | `808F9CAFCFC5BFE76851507813062F0D129A4A81837ED38C272C5A5B7B82978E` |
| `workers/S1/worker_state.json` | `9AFB4EC7BDD2CAE544D6544FC7A7A4DA4A4F54751C2AB3781EF4C9BD62859E6B` |
| `workers/S2/worker_proof.json` | `CE1D83492FDD24F1B3FF24F35A8597A8FEBEDF8FDF37774048372A79AE1D1CBE` |
| `workers/S2/worker_state.json` | `28CDE90B7738CB933EE8F3426FECB1B6C1005EB9C9390D7E6D7E57B3BCDADCD3` |
| `workers/S3/worker_proof.json` | `2352C0E1BEEEBEE462F35FDE3CECA4AC96BD8DD13C5A0023DD0407D0BB37D445` |
| `workers/S3/worker_state.json` | `22EDC8D23320FEA51F048D886307FE7F67D547BB15482C5338A10F60BEA5E513` |

## Observer Validation Result

Validation script result:

```json
{
  "status": "passed",
  "errors": []
}
```

## Boundary Confirmation

- Master was bypassed intentionally for this direct Debate Department probe.
- No top-level route table was modified.
- No router runtime was modified.
- No production Debate automation was added.
- No source file was modified by the tested Leader or Workers.
- No Archive / Knowledge / Causal store write was performed.
- No global causal truth merge was claimed.
- No remote push, PR, merge, release, deployment, or external sign-off was performed.
- Local artifacts are under ignored `local_artifacts/`.

## Remaining Issues

1. Debate Leader / Worker operational skill files are still absent, so this is not skill-file acceptance.
2. Worker creation was observer-mediated from the Leader's explicit creation requests. This proves real Worker threads and Leader gating, but it is not production autonomous Debate orchestration.
3. The nested-Codex outer tool consistently timed out while child threads completed. The probe handled this by artifact and session-log recovery.

## Final Classification

The direct Debate Department behavioral probe passed at contract-bound demo level.

It does not claim production closure and does not replace future Debate Leader / Worker operational skill acceptance.
