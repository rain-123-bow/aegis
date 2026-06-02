from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import MasterRuntimeContractError, ModelProfile, ModelReasoningPolicy


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise MasterRuntimeContractError(f"expected boolean, got: {value}")


def _strip(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def load_model_reasoning_policy(path: str | Path) -> ModelReasoningPolicy:
    """Load the locked root model/reasoning-budget policy.

    This parser is intentionally small and schema-specific so the demo runtime
    does not add a YAML dependency. It parses the current policy shape only.
    """
    policy_path = Path(path)
    text = policy_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    top: dict[str, str] = {}
    phase_boundary: dict[str, str] = {}
    fallback_policy: dict[str, str] = {}
    profiles: dict[str, dict[str, Any]] = {}

    section: str | None = None
    current_profile: str | None = None

    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if not raw.startswith(" "):
            current_profile = None
            if ":" in raw:
                key, value = raw.split(":", 1)
                key = key.strip()
                value = value.strip()
                if value:
                    top[key] = _strip(value)
                    section = None
                else:
                    section = key
            continue

        if section == "phase_boundary" and raw.startswith("  ") and ":" in raw:
            key, value = raw.split(":", 1)
            phase_boundary[key.strip()] = _strip(value)
            continue

        if section == "fallback_policy" and raw.startswith("  ") and ":" in raw:
            key, value = raw.split(":", 1)
            fallback_policy[key.strip()] = _strip(value)
            continue

        if section == "profiles":
            if raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
                current_profile = raw.strip()[:-1]
                profiles[current_profile] = {}
                continue
            if current_profile and raw.startswith("    ") and ":" in raw:
                key, value = raw.split(":", 1)
                key = key.strip()
                value = _strip(value)
                if key in {"fallback_allowed", "dynamic_adjustment_allowed"}:
                    profiles[current_profile][key] = _parse_bool(value)
                elif key in {"role_id", "model", "reasoning_budget", "fallback_authority", "parallel_internal_workers"}:
                    profiles[current_profile][key] = value
                continue

    required_top = ["policy_id", "version", "status"]
    for key in required_top:
        if key not in top:
            raise MasterRuntimeContractError(f"policy missing top-level field: {key}")

    parsed_profiles = {key: ModelProfile.from_mapping(value) for key, value in profiles.items()}
    if not parsed_profiles:
        raise MasterRuntimeContractError("policy has no profiles")

    dynamic_adjustment_enabled = _parse_bool(phase_boundary.get("dynamic_adjustment_enabled", "false"))
    default_fallback_allowed = _parse_bool(fallback_policy.get("default_fallback_allowed", "false"))
    silent_downgrade_allowed = _parse_bool(fallback_policy.get("silent_downgrade_allowed", "false"))
    explicit_gpt55_to_gpt54_fallback_allowed = _parse_bool(
        fallback_policy.get("explicit_gpt55_to_gpt54_fallback_allowed", "false")
    )
    fallback_authority = fallback_policy.get("authority", "root_policy_only")

    if dynamic_adjustment_enabled:
        raise MasterRuntimeContractError("dynamic adjustment must be disabled in current phase")
    if default_fallback_allowed:
        raise MasterRuntimeContractError("default fallback must be disabled in current phase")
    if silent_downgrade_allowed:
        raise MasterRuntimeContractError("silent downgrade must be disabled in current phase")
    if not explicit_gpt55_to_gpt54_fallback_allowed:
        raise MasterRuntimeContractError("explicit gpt-5.5 to gpt-5.4 fallback gate must be present")
    if fallback_authority != "root_policy_only":
        raise MasterRuntimeContractError("fallback authority must remain root_policy_only")

    return ModelReasoningPolicy(
        policy_id=top["policy_id"],
        version=top["version"],
        status=top["status"],
        profiles=parsed_profiles,
        dynamic_adjustment_enabled=dynamic_adjustment_enabled,
        default_fallback_allowed=default_fallback_allowed,
        silent_downgrade_allowed=silent_downgrade_allowed,
        explicit_gpt55_to_gpt54_fallback_allowed=explicit_gpt55_to_gpt54_fallback_allowed,
        fallback_authority=fallback_authority,
    )
