# Aegis

Aegis is a layered AI organization architecture for governed multi-agent software engineering.

It is not a generic agent chat framework. Aegis is designed to make AI collaboration auditable, contract-bounded, causally traceable, and safe to inherit across sessions.

## Core idea

```text
aegis-master-kit = organization constitution / management architecture / Master-level governance
specific business = code-repo + aegis-archive + aegis-causal + aegis-knowledge
aegis-router     = local communication mechanism for governed agent domains
aegis-runtime    = demo/runtime implementations that execute master-kit contracts
```

`aegis-master-kit` is not a project knowledge base, not a causal truth store, not a task archive, and not a code repository. It only tells the Master how to organize work.

The project separates:

- organization rules;
- communication enforcement;
- runtime demos;
- business code;
- archive / knowledge / causal state.

## Why Aegis exists

Single-agent coding can produce useful patches, but complex engineering work needs more than code generation.

Aegis focuses on the missing organizational layer:

```text
semantic alignment
-> request admission
-> adversarial debate when needed
-> contract-first task split
-> implementation
-> verification
-> final review
-> causal result handoff
-> archive / knowledge / causal promotion
```

> [!IMPORTANT]
> Aegis stores **causal structure**, not bare conclusions.
>
> A bare conclusion can look like an unconditional fact. A causal result records why the conclusion currently holds, what evidence supports it, what assumptions and material conditions it depends on, where it applies, what alternatives failed, and what changes would invalidate or reopen it.
>
> This distinction is a system safety rule: objective facts may remain stable under the same material conditions, but engineering reasoning results are maintained by their premises, evidence, scope, assumptions, and material conditions. When those supports change, the conclusion must be inherited, narrowed, reopened, superseded, or invalidated instead of blindly preserved.
>
> Full rationale: `aegis-master-kit/organization/departments/debate/CAUSAL_STRUCTURE_RATIONALE.md`.

## High-level governance flow

The following diagram shows the high-level Master governance flow. It is not a complete system architecture diagram.

![Aegis high-level governance flow](docs/aegis-high-level-governance-flow.png)

## Repository layout

```text
aegis/
  docs/                 Project definitions, technical baseline, and phase scope
  aegis-master-kit/     Master constitution and top-level organization architecture
  aegis-router/         Python implementation of a local MCP-style message router
  aegis-runtime/        Demo/runtime implementations that execute master-kit contracts
  examples/             Demo business skeleton showing how code + three libraries may coexist
  runtime_test_reports/ Runtime verification reports for completed demo phases
```

Important boundary:

```text
aegis-master-kit/organization/departments/*
  = department contracts, schemas, prompts, and governance rules

aegis-runtime/*
  = executable demo/runtime implementations of those contracts
```

Runtime code must not be moved into `aegis-master-kit` unless the project intentionally changes that boundary.

## Current status

Current branch: `v0.1.0-alpha`.

The current prototype has closed the following demo-level mechanisms:

1. Top-level Master communication topology.
2. Router-enforced directed communication.
3. Route envelope and mailbucket communication model.
4. Real route-envelope path protection demo path:
   - Ed25519 sender identity signing;
   - RSA-OAEP/SHA-256 receiver-only path encryption.
5. Debate Department contract package.
6. Debate Department router-integrated runtime demo.
7. Debate Leader explicit causal-chain output.
8. Execution Department contract package.
9. Execution Department deterministic runtime demo.
10. Execution router-integrated closure across:
    - `master -> execution`;
    - `execution -> test`;
    - `test -> execution`;
    - `execution -> debate`;
    - `debate -> execution`;
    - `execution -> master`.
11. Execution Leader final `execution_causal_chain` output as a `causal_candidate`.
12. Test Department contract package with strict evidence-state result semantics.
13. Test Department deterministic runtime demo.
14. Test router-integrated closure across:
    - `execution -> test`;
    - `test -> execution`;
    - `test -> final_review`.
15. Test result retention of reproducibility set and artifact manifest.
16. Test result output as scoped evidence, not global causal truth.
17. Final Review Department contract package with single-Leader whole-chain review semantics.
18. Final Review Department deterministic runtime demo.
19. Final Review router-integrated closure across:
    - `test -> final_review`;
    - `final_review -> master`.
20. Final Review resource-policy gate with `blocked_resource_policy` precedence.
21. Final Review output as recommendation to Master, not production release or global causal truth.
22. Root model and reasoning-budget policy for Master and top-level department Leaders.
23. Master top-level runtime demo for policy-bound nested-Codex Leader creation.
24. Real nested-Codex creation proof for Debate, Execution, Test, and Final Review Leaders.
25. Phase 17 proof audit with sha256 for all four real nested-Codex Leader proof files.

This is demo closure, not production closure.

## Phase-1 scope

Phase 1 validates the following chain:

```text
Developer -> Codex Master -> aegis-master-kit -> top-level departments -> department leaders -> aegis-router communication
```

The Debate, Execution, Test, and Final Review Departments have demo-level closures. The root model and reasoning-budget policy is locked for Master and top-level department Leaders in this phase. Master can now bootstrap top-level Leaders through nested-Codex creation and audit their proof files. The Test and Final Review closures are deterministic demo infrastructure only; they are not production Test or Final Review closure.

Phase 1 does **not** implement a full autonomous software company, a full causal database, automatic code submission, or production branch governance.

## Aegis Router

`aegis-router` is a lightweight local MCP-style message router.

It is responsible for:

- creating routing domains;
- registering agents;
- enforcing authoritative directed route tables;
- rejecting invalid sender -> receiver edges;
- sending small route envelopes by identity;
- maintaining inbox / outbox state;
- supporting ack and heartbeat;
- owning temporary mailbucket folders.

It is not responsible for:

- judging task quality;
- evaluating causal truth;
- parsing README or attachments;
- writing Archive / Knowledge / Causal stores;
- acting as a vault.

Router tests currently validate strict topology, envelope validation, mailbucket behavior, governance message boundaries, and the real double-crypto route-envelope path.

## Debate Department

The Debate Department is responsible for adversarial reasoning when a request has multiple defensible solution paths, unresolved causal conflict, significant ambiguity, or project-direction impact.

External boundary:

```text
Master / Execution <-> Debate Leader
```

Internal demo structure:

```text
Debate Leader
  -> temporary request-scoped workers
  -> leader-mediated round-robin broadcast
  -> adjudication
  -> explicit causal_chain
  -> cleanup
```

Key rules:

- The Debate Leader is the only external department boundary.
- Debate Workers are temporary and request-scoped.
- Each worker is bound to one stance.
- Workers do not become top-level Master-route agents.
- The internal default communication model is leader-mediated round-robin broadcast, not full-mesh chat.
- The Leader adjudicates by causal strength, not vote count.
- The final report must contain `causal_chain`, not only a conclusion summary.
- Debate output is a `causal_candidate`, not global causal truth.

The current router-integrated Debate demo topic selects:

```text
S2 = leader-mediated round-robin broadcast
```

It rejects:

```text
S1 = full-mesh asynchronous worker chat
S3 = independent workers with final synthesis only
```

The result is returned to Master through the router/mailbucket path with a persisted `causal_chain` containing nodes, edges, selected path, rejected paths, and invalidation entrypoints.

## Execution Department

The Execution Department is responsible for turning admitted executable work into traceable implementation candidates.

External boundary:

```text
Master / Debate / Test <-> Execution Leader
```

Internal demo structure:

```text
Execution Leader
  -> contract/context check
  -> plan selection or Debate request
  -> objective subtask split
  -> Execution Groups
  -> Front Agent implementation
  -> Back Agent review
  -> Leader-owned integration branch/workspace
  -> Test handoff
  -> Test feedback mapping
  -> rework when needed
  -> final execution_causal_chain
  -> cleanup/release of active groups after success
```

Key rules:

- The Execution Leader is the only external department boundary.
- Execution Groups are internal responsibility units, not top-level Master-route agents.
- A task may be split only when independence, contracts, ownership, local validation, and feedback mapping are objectively justified.
- Each independent subtask maps to one Execution Group.
- Each Execution Group has a Front Agent and a Back Agent.
- The Back Agent has blocking review authority.
- Group branches/workspaces must remain traceable to task, subtask, group, branch, and touched files.
- The Leader owns integration, not the individual groups.
- Test feedback is mandatory whether it passes or fails.
- Failure feedback must be evidence-backed and mapped before rework.
- Success feedback allows active group release only after responsibility records and causal output are preserved.
- Execution output is a `causal_candidate`, not global causal truth.

The current Execution runtime demo validates:

```text
Master -> Execution -> Test -> Execution -> Master
```

It also validates the conditional handoff:

```text
Execution -> Debate -> Execution
```

The Debate handoff demo selects `PLAN_B` and binds Debate's causal candidate into the final Execution causal chain.

## Test Department

The Test Department is responsible for converting integrated implementation candidates into reproducible evidence and scoped test conclusions.

External boundary:

```text
Execution / Final Review <-> Test Leader
```

Internal demo structure:

```text
Test Leader
  -> implementation candidate intake
  -> contract/context check
  -> deterministic test plan generation
  -> one Test Worker per accepted route
  -> route-level evidence production
  -> result aggregation by evidence state
  -> failed/inconclusive/ordinary blocked feedback to Execution Leader
  -> passed/scoped-pass/final-governance blocked material to Final Review
  -> reproducibility set and artifact manifest retention
```

Key rules:

- The Test Leader is the only external department boundary.
- Test Workers are route-scoped internal workers, not top-level Master-route agents.
- Test owns evidence production and scoped test conclusions, not implementation modification.
- Test may provide owner hints, but Execution Leader owns rework assignment.
- Proven candidate failure with ambiguous owner remains `failed`.
- Missing, unstable, or insufficient evidence becomes `inconclusive` or `blocked`.
- Governance or policy bypass becomes `blocked` with `blocker_kind: governance`.
- Passed or scoped-pass results go to Final Review, not directly to Master.
- Test output is evidence/scoped conclusion, not global causal truth.

The current Test runtime demo validates:

```text
Execution -> Test -> Execution
Execution -> Test -> Final Review
```

The runtime uses request-provided candidate snapshots and in-process route workers. It does not perform production git checkout, real CI, real environment provisioning, or nested-Codex Test Worker orchestration.

## Final Review Department

The Final Review Department is responsible for single-Leader whole-chain consistency review before results return to Master.

External boundary:

```text
Test / Master <-> Final Review Leader
```

Internal demo structure:

```text
Final Review Leader
  -> final review package intake from Test
  -> resource-policy gate
  -> single-subject whole-chain review
  -> object consistency check
  -> Execution/Test/Debate reference completeness check
  -> evidence, scope, and governance review
  -> final_review_result generation
  -> final_review_result handoff to Master
```

Key rules:

- The Final Review Leader is the only external department boundary.
- Final Review has no internal workers in v0.1.
- Parallel reviewer fanout is forbidden.
- Final Review reviews evidence and references; it does not modify code or run tests.
- Final Review may recommend Execution rework or Test expansion only through Master.
- Resource-policy failure returns `blocked_resource_policy` before substantive review.
- `accept_for_master` requires no `known_limits`, `blocked_scope`, or `missing_evidence`.
- `accept_for_master_with_scope_limit` requires explicit accepted limits.
- Final Review returns only to Master under the current topology.
- Final Review output is a recommendation, not a release action or global causal truth.

The current Final Review runtime demo validates:

```text
Test -> Final Review -> Master
```

The runtime is deterministic demo infrastructure. It does not call real external models, create root model/reasoning-budget policy files, perform production artifact review, or merge global causal truth.

## Model and reasoning-budget policy

Root policy file:

```text
MODEL_REASONING_BUDGET_POLICY.yaml
```

The current phase uses a locked static policy:

```text
Master                      -> gpt-5.5 / extra_high
Debate Leader               -> gpt-5.5 / high
Execution Leader            -> gpt-5.5 / high
Test Leader                 -> gpt-5.5 / high
Final Review Leader         -> gpt-5.5 / extra_high
```

Hard rules:

- model and reasoning-budget selection is owned by the root policy;
- agents must not self-select models or budgets;
- fallback and silent downgrade are forbidden in the current phase;
- Master dynamic adjustment is deferred;
- module-internal worker/front/back profiles are deferred.

## Master top-level nested-Codex bootstrap

The Master runtime can now create the four top-level department Leaders through nested-Codex and register them into the top-level Router domain:

```text
Master
  -> Debate Leader
  -> Execution Leader
  -> Test Leader
  -> Final Review Leader
```

The current Phase 17 proof verifies:

- root policy parsing for Master and all top-level Leaders;
- nested-Codex creation request construction with the locked model and reasoning budget;
- real nested-Codex MCP creation for all four top-level Leaders;
- Router registration for the created Leaders;
- all 10 v1 top-level route checks, including `debate -> master`;
- proof-file audit with sha256 for each real nested-Codex Leader proof.

This is still demo closure. It does not create module-internal workers, does not enable Master dynamic model adjustment, and does not claim production Master runtime closure.

## Quick validation

From repository root on Windows PowerShell.

### Debate runtime

```powershell
py -3.13 -m venv .venv-debate-runtime
.\.venv-debate-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-debate-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-debate-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\debate[dev]"

.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-router
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-runtime\debate
.\.venv-debate-runtime\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_router_integrated_debate_closure.py -vv
.\.venv-debate-runtime\Scripts\python.exe -m aegis_debate_runtime.cli --request .\aegis-runtime\debate\examples\demo_request.json
```

### Execution runtime

```powershell
py -3.13 -m venv .venv-execution-runtime
.\.venv-execution-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-execution-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-execution-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\execution[dev]"

.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution
.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution\tests\test_router_integrated_execution_closure.py -vv
.\.venv-execution-runtime\Scripts\python.exe -m pytest .\aegis-runtime\execution\tests\test_execution_debate_handoff_closure.py -vv
.\.venv-execution-runtime\Scripts\python.exe -m aegis_execution_runtime.cli --request .\aegis-runtime\execution\examples\demo_request.json
```

### Test runtime

```powershell
py -3.13 -m venv .venv-test-runtime
.\.venv-test-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-test-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\test[dev]"

.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test
.\.venv-test-runtime\Scripts\python.exe -m pytest .\aegis-runtime\test\tests\test_router_integrated_test_closure.py -vv
.\.venv-test-runtime\Scripts\python.exe -m aegis_test_runtime.cli --request .\aegis-runtime\test\examples\demo_request_pass.json
.\.venv-test-runtime\Scripts\python.exe -m aegis_test_runtime.cli --request .\aegis-runtime\test\examples\demo_request_failure.json
```

### Final Review runtime

```powershell
py -3.13 -m venv .venv-final-review-runtime
.\.venv-final-review-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-final-review-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-final-review-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\final_review[dev]"

.\.venv-final-review-runtime\Scripts\python.exe -m pytest .\aegis-runtime\final_review
.\.venv-final-review-runtime\Scripts\python.exe -m pytest .\aegis-runtime\final_review\tests\test_router_integrated_final_review_closure.py -vv
.\.venv-final-review-runtime\Scripts\python.exe -m aegis_final_review_runtime.cli --request .\aegis-runtime\final_review\examples\demo_request_accept.json
.\.venv-final-review-runtime\Scripts\python.exe -m aegis_final_review_runtime.cli --request .\aegis-runtime\final_review\examples\demo_request_blocked_resource.json
.\.venv-final-review-runtime\Scripts\python.exe -m aegis_final_review_runtime.cli --request .\aegis-runtime\final_review\examples\demo_request_scope_limit.json
```

### Master top-level runtime

```powershell
py -3.13 -m venv .venv-master-runtime
.\.venv-master-runtime\Scripts\python.exe -m pip install -U pip
.\.venv-master-runtime\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-master-runtime\Scripts\python.exe -m pip install -e ".\aegis-runtime\master[dev]"

.\.venv-master-runtime\Scripts\python.exe -m pytest .\aegis-runtime\master -vv
.\.venv-master-runtime\Scripts\python.exe -m pytest .\aegis-runtime\master\tests\test_master_nested_codex_agent_proof_audit.py -vv

.\.venv-master-runtime\Scripts\python.exe -m aegis_master_runtime.cli validate-recording `
  --policy .\MODEL_REASONING_BUDGET_POLICY.yaml `
  --router-state .\.aegis-master-runtime\router_state.json `
  --output-dir .\.aegis-master-runtime
```

Real nested-Codex validation is performed through the available local MCP surface and audited through the proof files under `agents_test`. The stdio `validate-real` path remains available for a future standardized create-agent MCP tool name.

Before committing local changes:

```powershell
git diff --check
git status --short
```

Do not commit generated files such as virtual environments, runtime state, mailbucket folders, cache directories, generated keys, generated secrets, proof directories, or runtime artifacts.

## Verification reports

Important runtime reports:

```text
runtime_test_reports/PHASE_9_COMMIT_GATE_READINESS_AUDIT_REPORT.md
runtime_test_reports/PHASE_10_DEBATE_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_11_DEBATE_ROUTER_INTEGRATED_CLOSURE_REPORT.md
runtime_test_reports/PHASE_12_DEBATE_CAUSAL_CHAIN_CLOSURE_REPORT.md
runtime_test_reports/PHASE_13_EXECUTION_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_14_EXECUTION_DEBATE_HANDOFF_CLOSURE_REPORT.md
runtime_test_reports/PHASE_15_TEST_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_15_TEST_RUNTIME_DEMO_LOCAL_VERIFICATION_REPORT.md
runtime_test_reports/PHASE_16_FINAL_REVIEW_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_16_FINAL_REVIEW_RUNTIME_DEMO_LOCAL_VERIFICATION_REPORT.md
runtime_test_reports/PHASE_17_MASTER_NESTED_CODEX_TOP_LEVEL_RUNTIME_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_17_MASTER_NESTED_CODEX_TOP_LEVEL_RUNTIME_LOCAL_VERIFICATION_REPORT.md
runtime_test_reports/PHASE_17_MASTER_NESTED_CODEX_AGENT_PROOF_AUDIT_REPORT.md
```

Current demo closure point:

```text
router-integrated communication closure
+ Debate temporary worker lifecycle closure
+ Debate Leader adjudication closure
+ Debate explicit causal-chain output closure
+ Execution group responsibility closure
+ Execution Test feedback/rework closure
+ Execution Debate handoff closure
+ Execution final causal-chain output closure
+ Test Department strict evidence-state semantics closure
+ Test deterministic route-worker evidence closure
+ Test failed-feedback-to-Execution closure
+ Test passed-result-to-Final-Review closure
+ Test reproducibility-set and artifact-manifest retention closure
+ Final Review single-Leader whole-chain review closure
+ Final Review resource-policy gate closure
+ Final Review object-consistency and evidence-sufficiency closure
+ Final Review result-to-Master closure
+ Root static model/reasoning-budget policy for Master and top-level Leaders
+ Master nested-Codex top-level Leader creation closure
+ Master top-level Router registration and 10-edge communication closure
+ Four-Leader proof-file sha256 audit closure
```

## Production hardening not yet included

The current prototype intentionally does not claim production closure.

Deferred production topics include:

- full key lifecycle;
- key rotation;
- hardware-backed keys;
- certificate chains and remote trust;
- payload/content encryption;
- nonce garbage collection;
- dynamic topology loading;
- MCP caller/session binding;
- JSON store locking;
- real persistent nested-Codex session lifecycle;
- standardized nested-Codex create-agent MCP tool name;
- real git branch/worktree orchestration;
- real nested-Codex multi-agent process orchestration below top-level Leaders;
- production Test Department runtime with real git checkout, CI, environment provisioning, and external artifact backend;
- production Final Review runtime with real external model invocation, root resource-policy integration, and production artifact review backend;
- Master-driven dynamic model and reasoning-budget adjustment;
- module-internal worker/front/back model profiles;
- real Archive / Knowledge / Causal admission;
- real global causal merge;
- production branch protection;
- remote push / PR / merge / release.

## Responsibility boundary

Aegis can generate candidates and reports.

Developers retain all critical responsibility actions, including remote push, main-branch merge, release, production deployment, and formal external sign-off.
