from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import asdict, dataclass
from typing import Annotated, Any, Mapping, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from experiments.codex_app_server_collaboration.app_server_client import (
    AppServerClient,
    AppServerProtocolError,
)


PRODUCER = "producer"
REVIEWER_BOUNDARY = "reviewer_boundary"
REVIEWER_EVIDENCE = "reviewer_evidence"
AGGREGATOR = "aggregator"


@dataclass(frozen=True)
class AgentExecution:
    role: str
    codex_thread_id: str
    codex_turn_id: str
    status: str
    payload: dict[str, Any]
    started_at: float
    completed_at: float
    model: str | None
    reasoning_effort: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class RoleExecutor(Protocol):
    def execute(
        self,
        *,
        role: str,
        prompt: str,
        output_schema: dict[str, Any],
        client_message_id: str,
    ) -> AgentExecution: ...


class CollaborationState(TypedDict, total=False):
    graph_run_id: str
    handoff_token: str
    producer: dict[str, Any]
    reviews: Annotated[list[dict[str, Any]], operator.add]
    final: dict[str, Any]


class CodexRoleExecutor:
    def __init__(self, client: AppServerClient, *, persistent_threads: bool) -> None:
        self._client = client
        self._persistent_threads = persistent_threads

    def execute(
        self,
        *,
        role: str,
        prompt: str,
        output_schema: dict[str, Any],
        client_message_id: str,
    ) -> AgentExecution:
        thread = self._client.start_thread(
            ephemeral=not self._persistent_threads,
            developer_instructions=(
                f"You are the isolated {role} role in a deterministic orchestration "
                "probe. Never call tools. Never modify files. Return only one JSON "
                "object matching the supplied output schema."
            ),
        )
        turn = self._client.run_turn(
            thread.thread_id,
            prompt,
            output_schema=output_schema,
            client_message_id=client_message_id,
        )
        try:
            payload = json.loads(turn.final_message)
        except json.JSONDecodeError as error:
            raise AppServerProtocolError(
                f"role {role} returned non-JSON output: {turn.final_message!r}"
            ) from error
        if not isinstance(payload, dict):
            raise AppServerProtocolError(
                f"role {role} output must be a JSON object: {payload!r}"
            )
        return AgentExecution(
            role=role,
            codex_thread_id=thread.thread_id,
            codex_turn_id=turn.turn_id,
            status=turn.status,
            payload=payload,
            started_at=turn.started_at,
            completed_at=turn.completed_at,
            model=thread.model,
            reasoning_effort=thread.reasoning_effort,
        )


def run_collaboration(
    executor: RoleExecutor, *, graph_run_id: str
) -> CollaborationState:
    if not graph_run_id or graph_run_id.strip() != graph_run_id:
        raise ValueError("graph_run_id must be a non-empty normalized string")
    handoff_token = _token(graph_run_id, "producer-handoff")
    review_receipts = {
        REVIEWER_BOUNDARY: _token(graph_run_id, REVIEWER_BOUNDARY),
        REVIEWER_EVIDENCE: _token(graph_run_id, REVIEWER_EVIDENCE),
    }

    def producer_node(state: CollaborationState) -> CollaborationState:
        schema = _producer_schema(graph_run_id, handoff_token)
        execution = executor.execute(
            role=PRODUCER,
            prompt=(
                "Synthetic frozen case:\n"
                "- Red and Blue are independent modules.\n"
                "- Both call one shared Common module.\n"
                "- Only Red changed. Common and Blue did not change.\n"
                "- Red's focused test failed.\n"
                "Propose the smallest defensible retest scope. Preserve the supplied "
                f"graph_run_id and handoff_token. graph_run_id={graph_run_id}; "
                f"handoff_token={handoff_token}."
            ),
            output_schema=schema,
            client_message_id=f"{graph_run_id}:{PRODUCER}",
        )
        _validate_execution(execution, schema)
        return {"producer": execution.as_dict()}

    def reviewer_node(role: str, focus: str):
        def review(state: CollaborationState) -> CollaborationState:
            producer = state.get("producer")
            if not isinstance(producer, dict):
                raise RuntimeError(f"{role} started without the producer artifact")
            producer_payload = producer.get("payload")
            if not isinstance(producer_payload, dict):
                raise RuntimeError("producer payload is missing")
            schema = _review_schema(
                graph_run_id,
                role,
                handoff_token,
                review_receipts[role],
            )
            execution = executor.execute(
                role=role,
                prompt=(
                    f"Review focus: {focus}\n"
                    "Read the complete frozen producer artifact below. Do not propose "
                    "changes outside this synthetic case. Return PASS or FAIL and all "
                    "findings found in this scan. Echo the supplied identifiers.\n"
                    f"PRODUCER_ARTIFACT={json.dumps(producer_payload, sort_keys=True)}\n"
                    f"review_receipt={review_receipts[role]}"
                ),
                output_schema=schema,
                client_message_id=f"{graph_run_id}:{role}",
            )
            _validate_execution(execution, schema)
            return {"reviews": [execution.as_dict()]}

        return review

    def aggregator_node(state: CollaborationState) -> CollaborationState:
        producer = state.get("producer")
        reviews = state.get("reviews")
        if not isinstance(producer, dict) or not isinstance(reviews, list):
            raise RuntimeError("aggregator started without complete upstream artifacts")
        sorted_reviews = sorted(reviews, key=lambda value: str(value.get("role")))
        actual_roles = {review.get("role") for review in sorted_reviews}
        expected_roles = {REVIEWER_BOUNDARY, REVIEWER_EVIDENCE}
        if actual_roles != expected_roles or len(sorted_reviews) != 2:
            raise RuntimeError(
                f"aggregator requires both independent reviews: {actual_roles!r}"
            )
        expected_receipts = [
            review_receipts[REVIEWER_BOUNDARY],
            review_receipts[REVIEWER_EVIDENCE],
        ]
        schema = _aggregator_schema(
            graph_run_id, handoff_token, expected_receipts
        )
        review_payloads = [review["payload"] for review in sorted_reviews]
        execution = executor.execute(
            role=AGGREGATOR,
            prompt=(
                "Aggregate the producer artifact and both complete independent reviews. "
                "PASS only if the proposal is accepted by both reviews; otherwise FAIL. "
                "Echo both reviewer receipts in the schema-defined order.\n"
                f"PRODUCER={json.dumps(producer['payload'], sort_keys=True)}\n"
                f"REVIEWS={json.dumps(review_payloads, sort_keys=True)}"
            ),
            output_schema=schema,
            client_message_id=f"{graph_run_id}:{AGGREGATOR}",
        )
        _validate_execution(execution, schema)
        if execution.payload.get("reviewer_receipts") != expected_receipts:
            raise RuntimeError("aggregator did not preserve both reviewer receipts")
        return {"final": execution.as_dict()}

    graph = StateGraph(CollaborationState)
    graph.add_node(PRODUCER, producer_node)
    graph.add_node(
        REVIEWER_BOUNDARY,
        reviewer_node(
            REVIEWER_BOUNDARY,
            "module-boundary assumptions and retest-scope correctness",
        ),
    )
    graph.add_node(
        REVIEWER_EVIDENCE,
        reviewer_node(
            REVIEWER_EVIDENCE,
            "evidence invalidation and unsupported causal claims",
        ),
    )
    graph.add_node(AGGREGATOR, aggregator_node)
    graph.add_edge(START, PRODUCER)
    graph.add_edge(PRODUCER, REVIEWER_BOUNDARY)
    graph.add_edge(PRODUCER, REVIEWER_EVIDENCE)
    graph.add_edge([REVIEWER_BOUNDARY, REVIEWER_EVIDENCE], AGGREGATOR)
    graph.add_edge(AGGREGATOR, END)
    compiled = graph.compile()
    return compiled.invoke(
        {
            "graph_run_id": graph_run_id,
            "handoff_token": handoff_token,
            "reviews": [],
        }
    )


def _producer_schema(graph_run_id: str, handoff_token: str) -> dict[str, Any]:
    return _object_schema(
        {
            "graph_run_id": {"type": "string", "enum": [graph_run_id]},
            "role": {"type": "string", "enum": [PRODUCER]},
            "handoff_token": {"type": "string", "enum": [handoff_token]},
            "proposal": {"type": "string", "minLength": 1},
        }
    )


def _review_schema(
    graph_run_id: str,
    role: str,
    handoff_token: str,
    review_receipt: str,
) -> dict[str, Any]:
    return _object_schema(
        {
            "graph_run_id": {"type": "string", "enum": [graph_run_id]},
            "role": {"type": "string", "enum": [role]},
            "handoff_token": {"type": "string", "enum": [handoff_token]},
            "review_receipt": {"type": "string", "enum": [review_receipt]},
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "findings": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )


def _aggregator_schema(
    graph_run_id: str, handoff_token: str, reviewer_receipts: list[str]
) -> dict[str, Any]:
    return _object_schema(
        {
            "graph_run_id": {"type": "string", "enum": [graph_run_id]},
            "role": {"type": "string", "enum": [AGGREGATOR]},
            "handoff_token": {"type": "string", "enum": [handoff_token]},
            "reviewer_receipts": {
                "type": "array",
                "items": {"type": "string", "enum": reviewer_receipts},
                "minItems": 2,
                "maxItems": 2,
            },
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "summary": {"type": "string", "minLength": 1},
        }
    )


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _validate_execution(
    execution: AgentExecution, schema: Mapping[str, Any]
) -> None:
    if execution.status != "completed":
        raise RuntimeError(
            f"role {execution.role} returned non-completed status {execution.status!r}"
        )
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        raise RuntimeError("invalid local output schema")
    missing = [name for name in required if name not in execution.payload]
    if missing:
        raise RuntimeError(f"role {execution.role} omitted fields: {missing!r}")
    extras = set(execution.payload) - set(properties)
    if extras:
        raise RuntimeError(f"role {execution.role} added fields: {sorted(extras)!r}")
    for name, property_schema in properties.items():
        if isinstance(property_schema, Mapping):
            enum = property_schema.get("enum")
            if isinstance(enum, list) and len(enum) == 1 and execution.payload.get(
                name
            ) != enum[0]:
                raise RuntimeError(
                    f"role {execution.role} returned invalid fixed field {name!r}"
                )


def _token(graph_run_id: str, purpose: str) -> str:
    digest = hashlib.sha256(f"{graph_run_id}:{purpose}".encode("utf-8")).hexdigest()
    return digest[:24]
