from __future__ import annotations

from typing import Any

from .artifact_contract import ArtifactContractRegistry
from .capability import CapabilityRegistry
from .models import ActionRequest, GovernanceDecision, GovernanceViolation
from .skill_registry import PHASE, default_registry_snapshot
from .state_machine import StateMachineRegistry


class RuntimeCheck:
    """Unified pre-action check for the Phase 31A governance kernel."""

    def __init__(self):
        snapshot = default_registry_snapshot()
        self.capabilities = CapabilityRegistry(snapshot.capability_rules)
        self.artifacts = ArtifactContractRegistry(snapshot.artifact_contracts)
        self.states = StateMachineRegistry(snapshot.state_transitions)

    def check(self, request: ActionRequest | dict[str, Any]) -> GovernanceDecision:
        req = request if isinstance(request, ActionRequest) else ActionRequest.from_mapping(request)
        violations: list[GovernanceViolation] = []
        checked = 0

        checked += 1
        violations.extend(
            self.capabilities.validate_action(
                role_id=req.actor_role,
                action=req.action,
                artifact_refs=req.artifact_refs,
                current_state=req.current_state,
                write_path=req.write_path,
            )
        )

        checked += 1
        if req.current_state is not None:
            _next_state, state_violations = self.states.allowed_next_state(
                role_id=req.actor_role,
                current_state=req.current_state,
                action=req.action,
                artifact_refs=req.artifact_refs,
            )
            violations.extend(state_violations)

        checked += 1
        contract_id = req.payload.get("artifact_contract_id")
        artifact_payload = req.payload.get("artifact_payload")
        if isinstance(contract_id, str) and contract_id:
            if isinstance(artifact_payload, dict):
                violations.extend(self.artifacts.validate(contract_id, artifact_payload))
            else:
                violations.append(GovernanceViolation("artifact_payload", "artifact payload is required", "missing_artifact_payload"))

        return GovernanceDecision.build(
            phase=PHASE,
            action=req.action,
            actor_role=req.actor_role,
            target_role=req.target_role,
            violations=violations,
            checked_rule_count=checked,
        )


def check_runtime_action(request: ActionRequest | dict[str, Any]) -> GovernanceDecision:
    return RuntimeCheck().check(request)
