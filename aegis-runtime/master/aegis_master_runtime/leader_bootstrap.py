from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from .mcp_client import NestedCodexClientProtocol
from .models import (
    LeaderCreationRecord,
    MasterRuntimeContractError,
    NestedCodexCreateRequest,
    TOP_LEVEL_LEADER_PROFILES,
    TOP_LEVEL_ROUTE_CHECKS,
    TopLevelBootstrapReport,
)
from .policy import load_model_reasoning_policy

TOP_LEVEL_DOMAIN_ID = "top_level_master_domain"
TOPOLOGY_ID = "master_top_level_v1"
DEV_HMAC_AUTH_ALG = "aegis-dev-hmac-sha256"


class MasterTopLevelRuntime:
    """Master runtime for top-level nested-Codex Leader creation."""

    def __init__(
        self,
        *,
        policy_path: str | Path,
        nested_codex_client: NestedCodexClientProtocol,
        private_root: str | Path,
        router_state_path: str | Path | None = None,
    ):
        self.policy_path = Path(policy_path)
        self.nested_codex_client = nested_codex_client
        self.private_root = Path(private_root).resolve()
        self.private_root.mkdir(parents=True, exist_ok=True)
        self.router_state_path = Path(router_state_path or (self.private_root / "router_state.json")).resolve()

    def bootstrap(self) -> TopLevelBootstrapReport:
        policy = load_model_reasoning_policy(self.policy_path)
        master_profile = policy.require_profile("master")
        leader_records: list[LeaderCreationRecord] = []

        router = self._init_router(master_profile)

        for agent_id, profile_id in TOP_LEVEL_LEADER_PROFILES.items():
            profile = policy.require_profile(profile_id)
            request = self._make_create_request(
                agent_id=agent_id,
                role_id=profile_id,
                model=profile.model,
                reasoning_budget=profile.reasoning_budget,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
            response = self.nested_codex_client.create_agent(request)
            response.assert_matches(request)

            router.register_agent(
                agent_id,
                TOP_LEVEL_DOMAIN_ID,
                agent_id,
                parent_id="master",
                capabilities=[profile_id, "top_level_leader"],
                metadata={
                    "dev_identity_keys": {self._identity_key_id(agent_id): self._identity_secret(agent_id)},
                    "nested_codex": response.to_dict(),
                    "model_policy": {
                        "policy_id": policy.policy_id,
                        "policy_version": policy.version,
                        "role_id": profile_id,
                        "resolved_model": profile.model,
                        "resolved_reasoning_budget": profile.reasoning_budget,
                        "fallback_used": False,
                        "dynamic_adjustment_used": False,
                    },
                },
            )
            leader_records.append(
                LeaderCreationRecord(
                    agent_id=agent_id,
                    role_id=profile_id,
                    model=profile.model,
                    reasoning_budget=profile.reasoning_budget,
                    nested_codex_status=response.status,
                    router_registered=True,
                )
            )

        route_checks = self._verify_top_level_routes(router)

        report = TopLevelBootstrapReport(
            report_id=f"top-level-bootstrap-{uuid4().hex}",
            status="top_level_nested_codex_creation_verified",
            policy_ref=str(self.policy_path),
            policy_version=policy.version,
            master_profile={
                "role_id": master_profile.role_id,
                "resolved_model": master_profile.model,
                "resolved_reasoning_budget": master_profile.reasoning_budget,
                "fallback_used": False,
                "dynamic_adjustment_used": False,
            },
            leader_records=leader_records,
            route_checks=route_checks,
            audit={
                "nested_codex_real_call_required_for_validate_real": True,
                "created_agent_count": len(leader_records),
                "router_domain": TOP_LEVEL_DOMAIN_ID,
                "topology_id": TOPOLOGY_ID,
                "dynamic_adjustment_used": False,
                "fallback_used": False,
            },
        )
        self._write_json(self.private_root / "top_level_bootstrap_report.json", report.to_dict())
        return report

    def _init_router(self, master_profile):
        from aegis_router import Router

        if self.router_state_path.exists():
            self.router_state_path.unlink()

        router = Router(self.router_state_path)
        router.create_domain(TOP_LEVEL_DOMAIN_ID, owner_agent_id="master", metadata={"topology_id": TOPOLOGY_ID})
        router.register_agent(
            "master",
            TOP_LEVEL_DOMAIN_ID,
            "master",
            capabilities=["master", "top_level_governance"],
            metadata={
                "dev_identity_keys": {self._identity_key_id("master"): self._identity_secret("master")},
                "model_policy": {
                    "role_id": "master",
                    "resolved_model": master_profile.model,
                    "resolved_reasoning_budget": master_profile.reasoning_budget,
                    "fallback_used": False,
                    "dynamic_adjustment_used": False,
                }
            },
        )
        return router

    def _make_create_request(
        self,
        *,
        agent_id: str,
        role_id: str,
        model: str,
        reasoning_budget: str,
        policy_id: str,
        policy_version: str,
    ) -> NestedCodexCreateRequest:
        display = {
            "debate": "Debate Leader",
            "execution": "Execution Leader",
            "test": "Test Leader",
            "final_review": "Final Review Leader",
        }[agent_id]
        return NestedCodexCreateRequest(
            agent_id=agent_id,
            role_id=role_id,
            display_name=display,
            model=model,
            reasoning_budget=reasoning_budget,
            parent_agent_id="master",
            scope=TOP_LEVEL_DOMAIN_ID,
            instructions=(
                f"You are {display} in Aegis. Obey the repository contracts, "
                "top-level route topology, and root model/reasoning policy. "
                "Do not self-select model or budget."
            ),
            metadata={
                "policy_id": policy_id,
                "policy_version": policy_version,
                "topology_id": TOPOLOGY_ID,
                "fallback_allowed": False,
                "dynamic_adjustment_allowed": False,
            },
        )

    def _verify_top_level_routes(self, router) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for sender, receiver in TOP_LEVEL_ROUTE_CHECKS:
            before = len(router.receive_messages(receiver))
            message = router.send_message(
                sender,
                receiver,
                "status_update",
                self._route_envelope(sender, receiver),
            )
            received = router.receive_messages(receiver)
            checks.append(
                {
                    "from": sender,
                    "to": receiver,
                    "message_type": "status_update",
                    "message_id": message["message_id"],
                    "receiver_inbox_count_before": before,
                    "receiver_inbox_count_after": len(received),
                    "verified": len(received) > before,
                }
            )
        return checks

    def _identity_key_id(self, agent_id: str) -> str:
        return f"{agent_id}-key"

    def _identity_secret(self, agent_id: str) -> str:
        return f"{agent_id}-secret"

    def _route_envelope(self, sender: str, receiver: str) -> dict[str, Any]:
        path = f"opaque-top-level-route-check:{sender}->{receiver}"
        nonce = f"{sender}-{receiver}-{uuid4().hex}"
        timestamp = datetime.now(timezone.utc).isoformat()
        material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
        signature = base64.b64encode(
            hmac.new(self._identity_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
        ).decode("ascii")
        return {
            "sender": sender,
            "receiver": receiver,
            "path": path,
            "auth": {
                "alg": DEV_HMAC_AUTH_ALG,
                "key_id": self._identity_key_id(sender),
                "nonce": nonce,
                "timestamp": timestamp,
                "signature": signature,
            },
        }

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
