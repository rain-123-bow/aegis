# Execution Phase 19B Acceptance Contract

## 1. Phase definition

Phase 19B validates real nested-Codex Execution Front/Back agent acceptance.

It builds on Phase 19A local git topology closure.

## 2. Accepted chain

```text
Master
  -> Execution Leader
      -> target sandbox local clone
      -> split validation
      -> Execution Groups
          -> real nested-Codex Front Agent
          -> real nested-Codex Back Agent
      -> Front/Back proof audit
      -> Front/Back output audit
      -> Leader integration / Test handoff using Phase 19A topology
```

## 3. Required target repository

The intended target repository is:

```text
rain-123-bow/aegis-execution-sandbox
```

It must be used as a business-code sandbox, not as Aegis control-plane code.

## 4. Acceptance label

A successful Phase 19B run may be labeled:

```text
accepted_real_execution_front_back_agent_closure
```

It must not be labeled:

```text
production_execution_lifecycle_closure
```

## 5. Required evidence

A valid Phase 19B acceptance package must contain:

```text
execution_agent_creation_requests.json
expected_execution_agent_proofs.json
expected_execution_agent_outputs.json
front_agent_proofs/
back_agent_proofs/
front_outputs/
back_reviews/
group_states/
execution_phase19b_acceptance_summary.json
```

## 6. Strict boundaries

Phase 19B must preserve these boundaries:

- Master creates or calls only the Execution Leader.
- Execution Leader creates Front and Back Agents.
- Front/Back Agents are group-internal request-scoped agents.
- Missing proof fails.
- Missing output fails.
- No deterministic/mock Front or Back Agent may be counted as real acceptance.
- No remote push.
- No PR.
- No remote merge.
- No release.
- No production sign-off.
- No global causal truth claim.

## 7. Relationship to Phase 19A

Phase 19A proves local git branch and integration topology.

Phase 19B proves the real Front/Back agent layer.

Phase 19B may reuse the Phase 19A sandbox branch/integration workflow, but it must not relabel Phase 19A deterministic group changes as real Front/Back agent work.
