from __future__ import annotations

from typing import Any

from .models import ArtifactContract, GovernanceViolation


class ArtifactContractRegistry:
    """Machine-readable artifact contract registry.

    This is intentionally simple for Phase 31A. It provides structural hard gates
    that can run before handoff, store writes, or commit-gate decisions.
    """

    def __init__(self, contracts: tuple[ArtifactContract, ...]):
        self._contracts = {contract.contract_id: contract for contract in contracts}

    def require_contract(self, contract_id: str) -> ArtifactContract:
        try:
            return self._contracts[contract_id]
        except KeyError as exc:
            raise KeyError(f"artifact contract missing: {contract_id}") from exc

    def validate(self, contract_id: str, payload: dict[str, Any]) -> list[GovernanceViolation]:
        contract = self._contracts.get(contract_id)
        if contract is None:
            return [GovernanceViolation("contract_id", f"unknown artifact contract: {contract_id}", "unknown_contract")]
        return validate_artifact(contract, payload)


def validate_artifact(contract: ArtifactContract, payload: dict[str, Any]) -> list[GovernanceViolation]:
    violations: list[GovernanceViolation] = []
    if not isinstance(payload, dict):
        return [GovernanceViolation("payload", "artifact payload must be an object", "invalid_artifact_payload")]

    for field in contract.required_fields:
        if _missing(payload.get(field)):
            violations.append(GovernanceViolation(field, "required field is missing", "missing_required_field"))

    for field in contract.required_true_fields:
        if payload.get(field) is not True:
            violations.append(GovernanceViolation(field, "field must be true", "required_true_field"))

    for field in contract.required_false_fields:
        if payload.get(field) is not False:
            violations.append(GovernanceViolation(field, "field must be false", "required_false_field"))

    for field in contract.blocked_fields:
        if field in payload and payload.get(field) not in {False, None, [], {}}:
            violations.append(GovernanceViolation(field, "field is blocked by artifact contract", "blocked_field_present"))

    for field, allowed in contract.allowed_values.items():
        if field in payload and payload.get(field) not in set(allowed):
            violations.append(
                GovernanceViolation(field, f"value must be one of {sorted(map(str, allowed))}", "invalid_field_value")
            )
    return violations


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
