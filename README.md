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

This is demo closure, not production closure.

## Phase-1 scope

Phase 1 validates the following chain:

```text
Developer -> Codex Master -> aegis-master-kit -> top-level departments -> department leaders -> aegis-router communication
```

The Debate Department and Execution Department have demo-level closures.

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

Before committing local changes:

```powershell
git diff --check
git status --short
```

Do not commit generated files such as virtual environments, runtime state, mailbucket folders, cache directories, generated keys, or generated secrets.

## Verification reports

Important runtime reports:

```text
runtime_test_reports/PHASE_9_COMMIT_GATE_READINESS_AUDIT_REPORT.md
runtime_test_reports/PHASE_10_DEBATE_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_11_DEBATE_ROUTER_INTEGRATED_CLOSURE_REPORT.md
runtime_test_reports/PHASE_12_DEBATE_CAUSAL_CHAIN_CLOSURE_REPORT.md
runtime_test_reports/PHASE_13_EXECUTION_RUNTIME_DEMO_IMPLEMENTATION_REPORT.md
runtime_test_reports/PHASE_14_EXECUTION_DEBATE_HANDOFF_CLOSURE_REPORT.md
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
- real git branch/worktree orchestration;
- real nested-Codex multi-agent process orchestration;
- real Test Department runtime;
- real Final Review Department runtime;
- real Archive / Knowledge / Causal admission;
- real global causal merge;
- production branch protection;
- remote push / PR / merge / release.

## Responsibility boundary

Aegis can generate candidates and reports.

Developers retain all critical responsibility actions, including remote push, main-branch merge, release, production deployment, and formal external sign-off.
