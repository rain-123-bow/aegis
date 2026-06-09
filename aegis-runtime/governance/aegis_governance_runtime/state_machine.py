from __future__ import annotations

from .models import GovernanceViolation, StateTransition


class StateMachineRegistry:
    """Role-local finite-state transition registry.

    This gate prevents agents from skipping required lifecycle states merely
    because a natural-language instruction asks for a shortcut.
    """

    def __init__(self, transitions: tuple[StateTransition, ...]):
        self._transitions = transitions

    def allowed_next_state(
        self,
        *,
        role_id: str,
        current_state: str,
        action: str,
        artifact_refs: tuple[str, ...] = (),
    ) -> tuple[str | None, list[GovernanceViolation]]:
        matches = [
            item
            for item in self._transitions
            if item.role_id == role_id and item.from_state == current_state and item.action == action
        ]
        if not matches:
            return None, [
                GovernanceViolation(
                    "state_transition",
                    f"no transition for role={role_id}, state={current_state}, action={action}",
                    "state_transition_not_allowed",
                )
            ]
        transition = matches[0]
        missing = [item for item in transition.required_artifacts if item not in artifact_refs]
        if missing:
            return None, [
                GovernanceViolation(
                    "artifact_refs",
                    "state transition missing artifact ref(s): " + ", ".join(sorted(missing)),
                    "state_transition_missing_artifact",
                )
            ]
        return transition.to_state, []
