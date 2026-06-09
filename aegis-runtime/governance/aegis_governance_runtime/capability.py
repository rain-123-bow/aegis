from __future__ import annotations

from pathlib import PurePosixPath

from .models import CapabilityRule, GovernanceViolation


class CapabilityRegistry:
    """Role capability registry used before any tool/action execution.

    This is a runtime authority layer. A role may reason about any action, but it
    may only execute actions allowed here.
    """

    def __init__(self, rules: tuple[CapabilityRule, ...]):
        self._rules = {rule.role_id: rule for rule in rules}

    def require_rule(self, role_id: str) -> CapabilityRule:
        try:
            return self._rules[role_id]
        except KeyError as exc:
            raise KeyError(f"capability rule missing for role: {role_id}") from exc

    def validate_action(
        self,
        *,
        role_id: str,
        action: str,
        artifact_refs: tuple[str, ...] = (),
        current_state: str | None = None,
        write_path: str | None = None,
    ) -> list[GovernanceViolation]:
        violations: list[GovernanceViolation] = []
        rule = self._rules.get(role_id)
        if rule is None:
            return [GovernanceViolation("actor_role", f"no capability rule for role {role_id}", "missing_capability_rule")]

        if action in rule.denied_actions:
            violations.append(GovernanceViolation("action", f"role {role_id} is denied action {action}", "denied_action"))
        if action not in rule.allowed_actions:
            violations.append(GovernanceViolation("action", f"role {role_id} is not allowed action {action}", "action_not_allowed"))

        required_artifacts = rule.required_artifacts_by_action.get(action, ())
        missing_artifacts = [item for item in required_artifacts if item not in artifact_refs]
        if missing_artifacts:
            violations.append(
                GovernanceViolation(
                    "artifact_refs",
                    "missing required artifact ref(s): " + ", ".join(sorted(missing_artifacts)),
                    "missing_required_artifact",
                )
            )

        required_states = rule.required_state_by_action.get(action, ())
        if required_states and current_state not in required_states:
            violations.append(
                GovernanceViolation(
                    "current_state",
                    f"action {action} requires state in {sorted(required_states)}, got {current_state}",
                    "invalid_state_for_action",
                )
            )

        if write_path is not None:
            path = _normalize_path(write_path)
            if not rule.allowed_write_roots:
                violations.append(
                    GovernanceViolation("write_path", f"role {role_id} has no write root", "write_not_allowed")
                )
            elif not any(_is_under_root(path, _normalize_path(root)) for root in rule.allowed_write_roots):
                violations.append(
                    GovernanceViolation(
                        "write_path",
                        f"write path {write_path} is outside role write roots",
                        "write_path_outside_capability",
                    )
                )
        return violations


def _normalize_path(value: str) -> PurePosixPath:
    return PurePosixPath(str(value).replace("\\", "/"))


def _is_under_root(path: PurePosixPath, root: PurePosixPath) -> bool:
    if path == root:
        return True
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
