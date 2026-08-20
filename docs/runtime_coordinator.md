# Runtime Coordinator

Authoritative architecture: `docs/AEGIS_ARCHITECTURE_CONTRACT.md`.

## Responsibilities

`RuntimeCoordinator` owns workflow-run identity, project Seal verification, protected remote witness verification, dynamic role-thread allocation, skill/runtime-profile binding, TraceRelay evidence, A-F attempt state, planning rounds, test-evidence manifests, recovery, and terminal outcome.

Master owns requirements, implementation plan, code, reasoning facts, and confirmation of F failure. A-F roles never own coordinator state.

## Storage

`.aegis/` contains only the project reasoning-ledger instance and its facts. Runtime state is outside the project:

```text
%LOCALAPPDATA%/Aegis/runtime/<project-id>/
  project_state/
    checkpoints.sqlite3
    dynamic_agent_registry.json
    dynamic_agent_registry.sqlite3
    instruction_receipts/
  runs/<workflow-run-id>/
    RUN_STATE.json
    responses/
    artifacts/
      graph/A/<round-id>/
      evidence/<attempt-id>/
      evidence-manifests/<attempt-id>.request.json
      evidence-manifests/<attempt-id>.json
      instruction-receipts/
```

Run state uses `aegis.run_state.v14`. The SQLite reservation row stores the authoritative state blob, digest, status, and project accountability marker in one transaction. `RUN_STATE.json` is a rebuildable projection. Older schemas are rejected; they are not guessed or silently migrated. v14 adds immutable reviewer fact results and Coordinator-derived private review stages without exposing workflow routing to reviewers. It retains the v13 sealed run-authority snapshot covering the Project Seal, remote witness requirement/result, and observed TraceRelay runtime identity. Before F starts, the Coordinator writes `aegis.final_review_input_manifest.v2` and freezes the exact project-runtime files, Scope controls, engineering inputs, reasoning context, approved plan, planning handoff, non-blank test report, every completed A/B response and instruction receipt (including C-start reuse snapshots), every C evidence manifest and recursive raw evidence file, and every completed C-E response and instruction receipt. F cannot reach a terminal verdict unless every required descriptor, authority, input manifest, and non-blank `FINAL_REVIEW.md` has exact bytes.

Every new run requires a Master-authored `aegis.engineering_input_manifest.v1` manifest. It lists at least one requirements document and one implementation-plan document by absolute path, byte size, and SHA-256. The Coordinator copies it into the run artifacts and revalidates every document before and after every A-F node.

The reasoning-ledger context pack is the only ledger view exposed to agents during A-F. Coordinator directly exports the live ledger in a read-only repeatable-read transaction, checks every pack item/edge against that export, freezes the snapshot bytes, and revalidates the live snapshot at boundaries. Agent live-ledger queries are forbidden. An insufficient or changed pack/snapshot fails closed and requires a new A-start run.

A new run may start only at A or C. Starting at C requires `--reuse-planning-from-run-id`, a current reasoning-ledger context pack, and an engineering-input manifest whose document set exactly matches the terminal parent run. The approved test plan, review report, and source run state are copied into the new run as immutable evidence. Any engineering-input difference forces a full A-F run from A.

An F failure ends the workflow with `master_review_status=PENDING`. Master then runs `confirm-f-failure` with a standalone Master review and evidence paths. The command unconditionally loads the SQLite reservation's authoritative state blob, accepts only a terminal F failure, seals `MASTER_FINAL_REVIEW.md` and `MASTER_FINAL_REVIEW_CONFIRMATION.json`, indexes `FINAL_REVIEW.md` plus the supplied evidence, and moves the state to `CONFIRMED` or `DISPUTED`. Artifact writes and the authoritative state transition run under one `BEGIN IMMEDIATE` reservation lock with an old-state digest compare-and-swap. Editing the `RUN_STATE.json` projection cannot authorize confirmation. The command never changes `delivery_eligible=false`; later state loads and project audits revalidate the confirmation, Master review, and indexed evidence.

## Preflight

Preflight fails closed unless all enabled checks pass:

1. `aegis.project_seal_chain.v3` parses, binds the approved scope-decision SHA-256, and its latest record is contiguous.
2. The user-confirmed runtime behavior scope resolves deterministically.
3. Scope policy hash, resolved manifest hash, file contents, Seal, project ID, seal-chain ID, sequence, and previous Seal match.
4. Production mode reads the canonical repository URL and protected ref from `config/seal_witness.json`, fetches into an isolated temporary bare repository with the pinned Git/SSH environment, and matches the witness commit to the latest locally verified Seal.
5. The workflow-run reservation is unique.
6. The dynamic project registry has no ambiguous allocation or cross-role thread reuse.
7. Resume state preserves runtime root, artifact root, role skills, role runtime profiles, registration intents, attempts, responses, and evidence identities.

Remote witness verification is disabled only in isolated unit construction. `src/main.py` always enables it. There is no production offline fallback.

## Role runtime contract

`config/agent_registry.json` is a role-template registry. It contains no real thread IDs.

For each role, the Coordinator binds:

- shared and role skill name, version, and SHA-256;
- model and reasoning effort;
- developer-instruction SHA-256;
- dynamic thread identity and lifecycle.

The configured model and reasoning effort are injected into the Codex App Server command. The returned thread handle must report the same values. `ultra` is rejected.

The supported model boundary is Codex/GPT. Each role developer instruction contains a challenge derived from the project ID, role, base instruction hash, and skill-binding hash. Before every turn, GPT must freshly write the exact `aegis.gpt_instruction_receipt.v1`; the Coordinator snapshots it into the run. Missing or mismatched receipts fail closed. Compatibility with non-GPT models is outside the contract.

## Execution and evidence

Every App Server turn runs in a separately registered TraceRelay-managed process. Registration intent is persisted before process creation. A successful turn requires `VALID_COMPLETE` raw and application evidence with process identity and bidirectional traffic.

Node C receives `aegis.test_execution_control.v1` and writes only `aegis.test_execution_request.v3`. The Coordinator requires exact equality with the reviewed `aegis.test_execution_policy.v2`, uses only its complete explicit environment, locks and revalidates cwd/executable/inputs, rejects shell and inline/module execution, runs argv through a resource-limited Windows Job Object, records process identity and actual outputs, and exclusively creates `aegis.test_execution_receipt.v3` plus `aegis.test_evidence_manifest.v2`. D cannot start without valid Coordinator-generated evidence.

Before and after every A-F node, the Coordinator re-verifies frozen runtime inputs. A Windows recursive change journal also detects modify-then-restore events during the node. A watcher reports ready only after its first asynchronous directory request is armed; all required roots must exist, and every descriptor plus the complete Project Seal is revalidated while all listeners are active before the node operation can run. Every `.git` event is protected. The descriptor map is frozen before the node; exact files and structural changes to any ancestor directory are protected. A completed buffer is parsed even when stop is signalled concurrently, every root is drained independently, captured mutation outranks watcher errors, and a zero-byte overflow result fails closed. Mutation records paths, old/new hashes and sizes, file identities, node, time, Coordinator PID, and available TraceRelay sessions; then terminates with `engineering_verdict=INVALIDATED`, `termination_reason_code=FROZEN_INPUT_MUTATION`, and `master_review_status=REQUIRES_USER_REASON`.

Recording the user's mutation reason also loads the SQLite reservation's authoritative state blob unconditionally. A modified or token-stripped `RUN_STATE.json` projection cannot fabricate an accountability event or clear the project-level mutation marker.

Every Coordinator-owned Codex/AppServer process tree runs inside a uniquely named, kill-on-close Windows Job Object. Registration operations derive the name from the operation ID, and the runner rejects an existing name before binding the exact Coordinator PID and process-creation time. Crash acceptance opens that named Job, queries its authoritative member set, fixes the active-process limit at the current count, suspends every stable member except the runner, and re-queries the complete membership before crashing the Coordinator. The frozen set records creation times, executable paths, command lines, and an `app-server` plus `stdio://` binding; every frozen identity must terminate. `WAIT_FAILED`, handle errors, and unresolved creation-time probes fail the report instead of counting as termination. Recovery never adopts an uncheckpointed replacement runtime.

While any project run remains `REQUIRES_USER_REASON`, the SQLite project-accountability marker rejects every new run even if its JSON projection was deleted or changed. Master records the user's explanation through `record-mutation-reason`; the command seals the explanation and user-confirmation ID, then changes only the accountability status to `USER_REASON_RECORDED` under the same reservation lock and old-state digest compare-and-swap. Resolved accountability descriptors remain in the durable marker. Every future preflight, resume, node boundary, and node watcher revalidates the reason record and reason body; deleting, replacing, or modify-restoring them terminates the active run. The invalidated run remains terminal and ineligible for delivery.

The project lease binds run ID, Coordinator instance UUID, PID, process creation time, and heartbeat. A second instance is rejected even when it requests the same run ID. Recovery may take over only after the recorded process identity is confirmed dead.

In-process watcher events and file handles cannot survive Coordinator process
death. A takeover from `ready`, `running`, `starting_tracerelay`, or
`tracerelay_attached` therefore terminates the old run with
`FREEZE_CONTINUITY_LOST`; it never continues that run toward PASS. A new run may
reuse a completed planning stage and start at C when its engineering inputs,
reasoning context, approved plan, review, and authority evidence still match.
Orderly `failed` states remain resumable because their prior freeze boundary was
durably closed before the inactive interval.

## Terminal semantics

Terminal publication is two-phase. `terminal_finalizing` records the intended
outcome. The Coordinator synchronously drains every listener while retaining
all file and ancestor handles. `terminal_committed` then commits the resulting
non-deliverable A-F freeze boundary before those handles are released. Only
after guard release does it publish `completed`, `terminated`, or `failed`.
Confirmation and delivery reject both intermediate statuses. A crash before
publication fails closed to `failed`, except a durably committed frozen-input
mutation remains `terminated/REQUIRES_USER_REASON`; no intermediate state can
return to `ready` or `running`.

- E `status=false`: terminate at E; F is not invoked.
- F `status=true`: `SUCCEEDED/PASS`, delivery eligible.
- F `status=false`: `TERMINATED/FAIL`, delivery blocked, Master review pending.
- Frozen-input mutation: terminated, engineering verdict invalidated, user reason required.
- Infrastructure/protocol/evidence defect: failed, verdict undetermined.
- Active Coordinator process loss: terminated with `FREEZE_CONTINUITY_LOST`;
  start a new run, optionally reusing completed planning evidence.

## Verification boundary

Local unit tests may use fake App Server, TraceRelay, Git witness, and isolated runtime roots. Real Codex/App Server/TraceRelay and remote fetch/push acceptance require explicit authorization and separate evidence.
