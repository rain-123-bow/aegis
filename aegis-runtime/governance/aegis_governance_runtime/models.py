from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

DecisionStatus = Literal["allowed", "rejected"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GovernanceRuntimeError(ValueError):
    """Raised when governance runtime input is malformed."""


@dataclass(frozen=True)
class GovernanceViolation:
    field: str
    reason: str
    code: str = "governance_violation"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "reason": self.reason, "code": self.code}


@dataclass(frozen=True)
class GovernanceDecision:
    decision_id: str
    phase: str
    status: DecisionStatus
    action: str
    actor_role: str
    target_role: str | None
    reason: str
    checked_rule_count: int
    violations: list[GovernanceViolation] = field(default_factory=list)
    warnings: list[GovernanceViolation] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def build(cls, *, phase: str, action: str, actor_role: str, target_role: str | None, violations: list[GovernanceViolation], warnings: list[GovernanceViolation] | None = None, checked_rule_count: int = 0) -> "GovernanceDecision":
        status: DecisionStatus = "allowed" if not violations else "rejected"
        return cls(
            decision_id=f"governance-decision-{uuid4().hex}",
            phase=phase,
            status=status,
            action=action,
            actor_role=actor_role,
            target_role=target_role,
            reason="Runtime hard gate allowed the action." if status == "allowed" else "Runtime hard gate rejected the action.",
            checked_rule_count=checked_rule_count,
            violations=list(violations),
            warnings=list(warnings or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "phase": self.phase,
            "status": self.status,
            "action": self.action,
            "actor_role": self.actor_role,
            "target_role": self.target_role,
            "reason": self.reason,
            "checked_rule_count": self.checked_rule_count,
            "violations": [item.to_dict() for item in self.violations],
            "warnings": [item.to_dict() for item in self.warnings],
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ArtifactContract:
    contract_id: str
    required_fields: tuple[str, ...] = ()
    required_true_fields: tuple[str, ...] = ()
    required_false_fields: tuple[str, ...] = ()
    blocked_fields: tuple[str, ...] = ()
    allowed_values: dict[str, tuple[Any, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityRule:
    role_id: str
    allowed_actions: tuple[str, ...] = ()
    denied_actions: tuple[str, ...] = ()
    allowed_write_roots: tuple[str, ...] = ()
    required_artifacts_by_action: dict[str, tuple[str, ...]] = field(default_factory=dict)
    required_state_by_action: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class StateTransition:
    role_id: str
    from_state: str
    action: str
    to_state: str
    required_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    skill_version: str
    role_id: str
    authority: Literal["guidance_only", "runtime_hard_gate"]
    model_profile: str | None = None
    parent_role: str | None = None
    allowed_child_roles: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    denied_actions: tuple[str, ...] = ()
    required_output_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillRegistrySnapshot:
    registry_id: str
    version: str
    phase: str
    skills: tuple[SkillDefinition, ...]
    capability_rules: tuple[CapabilityRule, ...]
    state_transitions: tuple[StateTransition, ...]
    artifact_contracts: tuple[ArtifactContract, ...]


@dataclass(frozen=True)
class ActionRequest:
    actor_role: str
    action: str
    target_role: str | None = None
    current_state: str | None = None
    artifact_refs: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    write_path: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ActionRequest":
        if not isinstance(value, dict):
            raise GovernanceRuntimeError("action request must be an object")
        actor_role = str(value.get("actor_role", "")).strip()
        action = str(value.get("action", "")).strip()
        if not actor_role:
            raise GovernanceRuntimeError("actor_role is required")
        if not action:
            raise GovernanceRuntimeError("action is required")
        refs = value.get("artifact_refs", ()) or ()
        if not isinstance(refs, (list, tuple)) or any(not isinstance(item, str) or not item for item in refs):
            raise GovernanceRuntimeError("artifact_refs must be a list of non-empty strings")
        payload = value.get("payload", {}) or {}
        if not isinstance(payload, dict):
            raise GovernanceRuntimeError("payload must be an object")
        return cls(
            actor_role=actor_role,
            action=action,
            target_role=str(value["target_role"]) if value.get("target_role") is not None else None,
            current_state=str(value["current_state"]) if value.get("current_state") is not None else None,
            artifact_refs=tuple(refs),
            payload=payload,
            write_path=str(value["write_path"]) if value.get("write_path") is not None else None,
        )
