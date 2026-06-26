"""Resident module registry for Top-Level Graph v2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aegis.top_level.models import ModuleName, ModuleRouteDecision, ResidentModuleRecord


class ModuleRegistryError(ValueError):
    """Raised when resident module registry invariants are violated."""


@runtime_checkable
class ResidentModule(Protocol):
    """Minimal interface owned by the parent router."""

    module_type: str
    module_instance_id: str
    resident_agents: list[str]

    def handle(self, state: dict[str, object]) -> ModuleRouteDecision:
        """Handle a compact parent route state and return a route decision."""


REQUIRED_MODULES: tuple[ModuleName, ...] = (
    "master",
    "debate",
    "execution",
    "test",
    "final_review",
)


class ModuleRegistry:
    """Registry of exactly one resident instance per core module."""

    def __init__(
        self,
        modules: dict[ModuleName, ResidentModule],
        records: dict[ModuleName, ResidentModuleRecord],
    ) -> None:
        self.modules = modules
        self.records = records

    @classmethod
    def from_modules(cls, modules: list[ResidentModule]) -> "ModuleRegistry":
        by_type: dict[ModuleName, ResidentModule] = {}
        records: dict[ModuleName, ResidentModuleRecord] = {}
        for module in modules:
            module_type = _module_name(module.module_type)
            if module_type in by_type:
                raise ModuleRegistryError(f"duplicate resident module: {module_type}")
            expected_instance_id = f"{module_type}:default"
            if module.module_instance_id != expected_instance_id:
                raise ModuleRegistryError(
                    f"{module_type} module_instance_id must be {expected_instance_id}"
                )
            if module_type == "debate":
                for agent in module.resident_agents:
                    if agent.startswith("debate_worker"):
                        raise ModuleRegistryError("Debate workers must not enter global registry")
            by_type[module_type] = module
            records[module_type] = ResidentModuleRecord(
                module_type=module_type,
                module_instance_id=module.module_instance_id,
                resident_agents=list(module.resident_agents),
                checkpoint_thread_id=f"{module_type}:default",
            )
        missing = [module for module in REQUIRED_MODULES if module not in by_type]
        if missing:
            raise ModuleRegistryError(f"missing resident modules: {', '.join(missing)}")
        return cls(by_type, records)

    def get(self, module_type: ModuleName) -> ResidentModule:
        try:
            return self.modules[module_type]
        except KeyError as exc:
            raise ModuleRegistryError(f"missing resident module: {module_type}") from exc


def _module_name(value: str) -> ModuleName:
    if value not in REQUIRED_MODULES:
        raise ModuleRegistryError(f"unknown resident module: {value}")
    return value  # type: ignore[return-value]
