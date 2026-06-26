"""Contracts for the Top-Level Graph v2 resident router."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


ModuleName = Literal["master", "debate", "execution", "test", "final_review"]
RouteTarget = Literal["master", "debate", "execution", "test", "final_review", "closeout"]


class RouteStatus(str, Enum):
    """Status returned by a resident subgraph to the parent router."""

    READY = "ready"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"
    MODULE_TERMINAL = "module_terminal"
    RUNTIME_TERMINAL = "runtime_terminal"
    FAILED = "failed"


class TopLevelTerminalStatus(str, Enum):
    """Top-level runtime status."""

    RUNNING = "running"
    INTERRUPTED = "interrupted"
    BLOCKED = "blocked"
    CLOSED = "closed"
    STOPPED_DUE_TO_MODULE_FAILURE = "stopped_due_to_module_failure"


class ResidentStatus(str, Enum):
    """Resident module lifecycle state."""

    INITIALIZING = "initializing"
    READY = "ready"
    RECOVERED_UNVERIFIED = "recovered_unverified"
    FAILED = "failed"
    STOPPED = "stopped"
    MONITOR_REQUIRED = "monitor_required"


class TopLevelPackageFile(StrictModel):
    """One package manifest file entry."""

    rel_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    required: bool = True

    @field_validator("rel_path", "sha256")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class TopLevelPackageManifest(StrictModel):
    """Deterministic package manifest routed by the parent graph."""

    schema_version: Literal["top_level.package_manifest.v1"] = "top_level.package_manifest.v1"
    run_id: str
    package_root: str
    readme_path: str
    producer_module: ModuleName
    producer_module_instance_id: str
    created_at_utc: str = Field(default_factory=utc_now)
    files: list[TopLevelPackageFile]

    @field_validator("run_id", "package_root", "readme_path", "producer_module_instance_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class TopLevelHandoffEnvelope(StrictModel):
    """Compact handoff envelope. Long content stays in package files."""

    schema_version: Literal["top_level_handoff_v1"] = "top_level_handoff_v1"
    run_id: str
    source_module: ModuleName
    target_module: RouteTarget
    source_module_instance_id: str
    target_module_instance_id: str
    handoff_kind: str
    package_path: str
    package_manifest_path: str
    package_sha256: str
    declared_next_route: RouteTarget
    created_at_utc: str = Field(default_factory=utc_now)

    @field_validator(
        "run_id",
        "source_module_instance_id",
        "target_module_instance_id",
        "handoff_kind",
        "package_path",
        "package_manifest_path",
        "package_sha256",
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @model_validator(mode="after")
    def _declared_route_matches_target(self) -> "TopLevelHandoffEnvelope":
        if self.declared_next_route != self.target_module:
            raise ValueError("declared_next_route must match target_module")
        return self


class DeveloperInterruptPackage(StrictModel):
    """Machine-readable developer interrupt surfaced by the parent graph."""

    schema_version: Literal["top_level.interrupt.v1"] = "top_level.interrupt.v1"
    run_id: str
    source_module: ModuleName
    source_module_instance_id: str
    interrupt_type: Literal[
        "human_approval_required",
        "missing_input",
        "required_secret",
        "unsafe_action",
        "ambiguous_requirement",
        "external_dependency",
    ]
    message_ref: str
    allowed_resume_actions: list[str]
    required_user_inputs: list[dict[str, Any]] = Field(default_factory=list)
    created_at_utc: str = Field(default_factory=utc_now)


class ModuleRouteDecision(StrictModel):
    """Compact route decision returned by a resident module."""

    source_module: ModuleName
    route_status: RouteStatus
    next_route: RouteTarget | None = None
    handoff_kind: str | None = None
    output_handoff: TopLevelHandoffEnvelope | None = None
    blockers: list[str] = Field(default_factory=list)
    interrupt_ref: str | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _status_consistency(self) -> "ModuleRouteDecision":
        if self.route_status in {RouteStatus.READY, RouteStatus.MODULE_TERMINAL}:
            if self.next_route is None:
                raise ValueError("routable decisions require next_route")
            if self.output_handoff is None:
                raise ValueError("routable decisions require output_handoff")
        if self.route_status == RouteStatus.RUNTIME_TERMINAL:
            if self.source_module != "master" or self.next_route != "closeout":
                raise ValueError("runtime_terminal is reserved for Master closeout")
        if self.route_status == RouteStatus.INTERRUPTED and self.interrupt_ref is None:
            raise ValueError("interrupted decisions require interrupt_ref")
        if self.route_status == RouteStatus.FAILED and not self.failure_reason:
            raise ValueError("failed decisions require failure_reason")
        return self


class ResidentModuleRecord(StrictModel):
    """Registry metadata for one resident subgraph."""

    module_type: ModuleName
    module_instance_id: str
    resident_agents: list[str] = Field(default_factory=list)
    status: ResidentStatus = ResidentStatus.READY
    checkpoint_thread_id: str | None = None
    created_at_utc: str = Field(default_factory=utc_now)
    last_route_at_utc: str | None = None
    failure_ref: str | None = None


class ParentRouteEvent(StrictModel):
    """One compact parent route event."""

    event_index: int
    run_id: str
    source_module: ModuleName
    target_module: RouteTarget
    handoff_kind: str
    route_status: RouteStatus
    package_ref: str | None = None
    validation_ref: str | None = None
    created_at_utc: str = Field(default_factory=utc_now)


class TopLevelGraphState(StrictModel):
    """Compact parent graph state."""

    aegis_instance_id: str
    project_root: str
    run_id: str
    thread_id: str
    current_module: RouteTarget = "master"
    resident_modules: dict[str, ResidentModuleRecord]
    active_handoff_ref: TopLevelHandoffEnvelope | None = None
    route_history_tail: list[ParentRouteEvent] = Field(default_factory=list)
    route_history_log_ref: str | None = None
    route_count: int = 0
    pending_interrupt_ref: str | None = None
    blockers: list[str] = Field(default_factory=list)
    terminal_status: TopLevelTerminalStatus = TopLevelTerminalStatus.RUNNING
    closeout_package_ref: str | None = None
    failure_evidence_ref: str | None = None

    @field_validator("aegis_instance_id", "project_root", "run_id", "thread_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class RouteValidationResult(StrictModel):
    """Machine-readable result of parent route validation."""

    status: Literal["passed", "failed"]
    source_module: ModuleName
    target_module: RouteTarget
    handoff_kind: str
    reasons: list[str] = Field(default_factory=list)
    envelope_ref: str | None = None
    manifest_ref: str | None = None
