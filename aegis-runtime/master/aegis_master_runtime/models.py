from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


TOP_LEVEL_LEADER_PROFILES: dict[str, str] = {
    "debate": "debate_leader",
    "execution": "execution_leader",
    "test": "test_leader",
    "final_review": "final_review_leader",
}

TOP_LEVEL_ROUTE_CHECKS: tuple[tuple[str, str], ...] = (
    ("master", "debate"),
    ("master", "execution"),
    ("debate", "master"),
    ("execution", "test"),
    ("test", "execution"),
    ("test", "final_review"),
    ("final_review", "master"),
    ("execution", "debate"),
    ("debate", "execution"),
    ("execution", "master"),
)


class MasterRuntimeContractError(ValueError):
    """Raised when Master top-level runtime violates its contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ModelProfile:
    role_id: str
    model: str
    reasoning_budget: str
    fallback_allowed: bool
    dynamic_adjustment_allowed: bool
    parallel_internal_workers: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ModelProfile":
        try:
            role_id = str(value["role_id"])
            model = str(value["model"])
            reasoning_budget = str(value["reasoning_budget"])
        except KeyError as exc:
            raise MasterRuntimeContractError(f"model profile missing field: {exc.args[0]}") from exc
        return cls(
            role_id=role_id,
            model=model,
            reasoning_budget=reasoning_budget,
            fallback_allowed=bool(value.get("fallback_allowed", False)),
            dynamic_adjustment_allowed=bool(value.get("dynamic_adjustment_allowed", False)),
            parallel_internal_workers=value.get("parallel_internal_workers"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "role_id": self.role_id,
            "model": self.model,
            "reasoning_budget": self.reasoning_budget,
            "fallback_allowed": self.fallback_allowed,
            "dynamic_adjustment_allowed": self.dynamic_adjustment_allowed,
        }
        if self.parallel_internal_workers is not None:
            data["parallel_internal_workers"] = self.parallel_internal_workers
        return data


@dataclass(frozen=True)
class ModelReasoningPolicy:
    policy_id: str
    version: str
    status: str
    profiles: dict[str, ModelProfile]
    dynamic_adjustment_enabled: bool
    default_fallback_allowed: bool
    silent_downgrade_allowed: bool

    def require_profile(self, profile_id: str) -> ModelProfile:
        try:
            profile = self.profiles[profile_id]
        except KeyError as exc:
            raise MasterRuntimeContractError(f"required model profile missing: {profile_id}") from exc
        if profile.fallback_allowed:
            raise MasterRuntimeContractError(f"fallback must be false in current phase: {profile_id}")
        if profile.dynamic_adjustment_allowed:
            raise MasterRuntimeContractError(f"dynamic adjustment must be false in current phase: {profile_id}")
        return profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "status": self.status,
            "dynamic_adjustment_enabled": self.dynamic_adjustment_enabled,
            "default_fallback_allowed": self.default_fallback_allowed,
            "silent_downgrade_allowed": self.silent_downgrade_allowed,
            "profiles": {key: profile.to_dict() for key, profile in self.profiles.items()},
        }


@dataclass(frozen=True)
class NestedCodexCreateRequest:
    agent_id: str
    role_id: str
    display_name: str
    model: str
    reasoning_budget: str
    parent_agent_id: str
    scope: str
    instructions: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "display_name": self.display_name,
            "model": self.model,
            "reasoning_budget": self.reasoning_budget,
            "parent_agent_id": self.parent_agent_id,
            "scope": self.scope,
            "instructions": self.instructions,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NestedCodexCreateResponse:
    agent_id: str
    role_id: str
    status: Literal["created", "active", "ready"]
    resolved_model: str
    resolved_reasoning_budget: str
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "NestedCodexCreateResponse":
        status = str(value.get("status", ""))
        if status not in {"created", "active", "ready"}:
            raise MasterRuntimeContractError(f"nested-codex response status is invalid: {status}")
        return cls(
            agent_id=str(value.get("agent_id", "")),
            role_id=str(value.get("role_id", "")),
            status=status,  # type: ignore[arg-type]
            resolved_model=str(value.get("resolved_model", value.get("model", ""))),
            resolved_reasoning_budget=str(value.get("resolved_reasoning_budget", value.get("reasoning_budget", ""))),
            raw_response=dict(value),
        )

    def assert_matches(self, request: NestedCodexCreateRequest) -> None:
        if self.agent_id != request.agent_id:
            raise MasterRuntimeContractError(f"nested-codex agent_id mismatch: {self.agent_id} != {request.agent_id}")
        if self.role_id != request.role_id:
            raise MasterRuntimeContractError(f"nested-codex role_id mismatch: {self.role_id} != {request.role_id}")
        if self.resolved_model != request.model:
            raise MasterRuntimeContractError(
                f"nested-codex resolved_model mismatch: {self.resolved_model} != {request.model}"
            )
        if self.resolved_reasoning_budget != request.reasoning_budget:
            raise MasterRuntimeContractError(
                "nested-codex resolved_reasoning_budget mismatch: "
                f"{self.resolved_reasoning_budget} != {request.reasoning_budget}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "status": self.status,
            "resolved_model": self.resolved_model,
            "resolved_reasoning_budget": self.resolved_reasoning_budget,
            "raw_response": self.raw_response,
        }


@dataclass(frozen=True)
class LeaderCreationRecord:
    agent_id: str
    role_id: str
    model: str
    reasoning_budget: str
    nested_codex_status: str
    router_registered: bool
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "model": self.model,
            "reasoning_budget": self.reasoning_budget,
            "nested_codex_status": self.nested_codex_status,
            "router_registered": self.router_registered,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class TopLevelBootstrapReport:
    report_id: str
    status: str
    policy_ref: str
    policy_version: str
    master_profile: dict[str, Any]
    leader_records: list[LeaderCreationRecord]
    route_checks: list[dict[str, Any]]
    audit: dict[str, Any]
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "status": self.status,
            "policy_ref": self.policy_ref,
            "policy_version": self.policy_version,
            "master_profile": dict(self.master_profile),
            "leader_records": [record.to_dict() for record in self.leader_records],
            "route_checks": list(self.route_checks),
            "audit": dict(self.audit),
            "created_at": self.created_at,
        }
