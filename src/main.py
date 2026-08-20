from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, TypeAlias

from langgraph.graph import END, START, StateGraph

from langgraph_contract import (
    CONTROL_FILES,
    NODE_A,
    NODE_B,
    NODE_C,
    NODE_D,
    NODE_E,
    NODE_F,
    ROUTE_END,
    before_author_hashes,
    fail_state,
    gate_author,
    gate_executor,
    gate_final_reviewer,
    gate_report_writer,
    gate_reviewer,
    prepare_node_input,
    strict_json_object,
    validate_agent_output,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_REGISTRY_PATH = PROJECT_ROOT / "config" / "agent_registry.json"
NODE_MESSAGE_SCHEMA_PATH = PROJECT_ROOT / "config" / "node_message_schema.json"
QUALITY_LAW_PATH = PROJECT_ROOT / "skills" / "aegis_global_quality_law" / "SKILL.md"
NODE_TIMEOUT_SECONDS = int(os.environ.get("AEGIS_NODE_TIMEOUT_SECONDS", "1800"))


State: TypeAlias = dict[str, Any]
TEST_PLAN_AUTHOR_ROLE = "TEST_PLAN_AUTHOR"
TEST_PLAN_REVIEWER_ROLE = "TEST_PLAN_REVIEWER"
TEST_EXECUTOR_ROLE = "TEST_EXECUTOR"
TEST_RESULT_REVIEWER_ROLE = "TEST_RESULT_REVIEWER"
TEST_REPORT_WRITER_ROLE = "TEST_REPORT_WRITER"
FINAL_REVIEWER_ROLE = "FINAL_REVIEWER"


def load_agent_thread_map(config_path: Path = AGENT_REGISTRY_PATH) -> dict[str, str]:
    registry = json.loads(config_path.read_text(encoding="utf-8"))
    return {agent["role_key"]: agent["thread_id"] for agent in registry["agents"]}


def load_agent_config(role_key: str, config_path: Path = AGENT_REGISTRY_PATH) -> dict[str, Any]:
    registry = json.loads(config_path.read_text(encoding="utf-8"))
    for agent in registry["agents"]:
        if agent["role_key"] == role_key:
            return dict(agent)
    raise KeyError(f"agent role not found: {role_key}")


def load_node_message_schema(config_path: Path = NODE_MESSAGE_SCHEMA_PATH) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def initialize_state(
    schema_path: Path = NODE_MESSAGE_SCHEMA_PATH,
    *,
    current_node: str = "START",
    initial_values: dict[str, Any] | None = None,
) -> State:
    schema = load_node_message_schema(schema_path)
    values = initial_values or {}
    agent_config = load_agent_config(TEST_PLAN_AUTHOR_ROLE)
    state: State = {
        field_name: values.get(field_name)
        for field_name in schema.get("properties", {})
    }
    if state.get("artifact_path") is None:
        state["artifact_path"] = agent_config.get("artifact_path")
    if state.get("quality_law_path") is None:
        state["quality_law_path"] = str(QUALITY_LAW_PATH)
    if state.get("reasoning_ledger_context_pack") is None and state.get("artifact_path"):
        state["reasoning_ledger_context_pack"] = str(
            Path(state["artifact_path"]) / "REASONING_LEDGER_CONTEXT_PACK.json"
        )
    state.update(
        {
            "current_node": current_node,
            "status": values.get("status", True),
            "gate_status": values.get("gate_status", True),
            "gate_route": values.get("gate_route"),
            "control_files": values.get("control_files", CONTROL_FILES),
            "open_blockers": values.get("open_blockers", []),
            "blocker_history": values.get("blocker_history", []),
            "same_blocker_counts": values.get("same_blocker_counts", {}),
            "test_plan_author_review_failures": values.get("test_plan_author_review_failures", 0),
            "test_plan_author_gate_failures": values.get("test_plan_author_gate_failures", 0),
            "test_execution_review_failures": values.get("test_execution_review_failures", 0),
            "max_test_plan_review_failures": values.get(
                "max_test_plan_review_failures",
                int(os.environ.get("AEGIS_MAX_TEST_PLAN_REVIEW_FAILURES", "5")),
            ),
            "max_test_result_review_failures": values.get(
                "max_test_result_review_failures",
                int(os.environ.get("AEGIS_MAX_TEST_RESULT_REVIEW_FAILURES", "5")),
            ),
            "review_pass_score": values.get(
                "review_pass_score",
                int(os.environ.get("AEGIS_REVIEW_PASS_SCORE", "90")),
            ),
            "stop_reason": values.get("stop_reason"),
            "gate_violations": values.get("gate_violations", []),
        }
    )
    return state


def resolve_codex_command() -> str:
    command = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    if command is None:
        raise RuntimeError("codex command was not found on PATH")
    return command


def send_prompt_to_thread(thread_id: str, prompt: str) -> str:
    output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as output_file:
            output_path = Path(output_file.name)

        try:
            completed = subprocess.run(
                [
                    resolve_codex_command(),
                    "exec",
                    "resume",
                    "--output-last-message",
                    str(output_path),
                    thread_id,
                    prompt,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=NODE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "codex exec resume timed out "
                f"after {NODE_TIMEOUT_SECONDS}s for thread_id={thread_id}"
            ) from exc

        if completed.returncode != 0:
            raise RuntimeError(
                "codex exec resume failed "
                f"with exit_code={completed.returncode}, "
                f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
            )

        return output_path.read_text(encoding="utf-8")
    finally:
        if output_path is not None:
            output_path.unlink(missing_ok=True)


def log_node_event(node_name: str, event: str) -> None:
    print(f"[aegis] node={node_name} event={event}", file=sys.stderr, flush=True)


def build_node_prompt(node_input: State) -> str:
    schema = load_node_message_schema()
    payload = {
        field_name: node_input.get(field_name)
        for field_name in schema.get("properties", {})
        if field_name in node_input
    }
    return json.dumps(payload, ensure_ascii=False)


def invoke_codex_node(state: State, *, node_name: str, role_key: str) -> tuple[State, State]:
    log_node_event(node_name, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = prepare_node_input(state, node_name=node_name)
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[role_key], prompt)
    node_output = strict_json_object(response, source=node_name)
    validate_agent_output(node_input, node_output, node_name=node_name)
    log_node_event(node_name, "done")
    return node_input, node_output


def fail_closed_node(state: State, *, node_name: str, exc: Exception) -> State:
    node_input = prepare_node_input(state, node_name=node_name)
    return fail_state(node_input, node_name, reason=str(exc), route=ROUTE_END)


def test_plan_author_node(state: State) -> State:
    try:
        node_input = prepare_node_input(state, node_name=NODE_A)
        before_hashes = before_author_hashes(node_input)
        _node_input, node_output = invoke_codex_node(node_input, node_name=NODE_A, role_key=TEST_PLAN_AUTHOR_ROLE)
        return gate_author(node_input, node_output, before_hashes=before_hashes)
    except Exception as exc:
        return fail_closed_node(state, node_name=NODE_A, exc=exc)


def test_plan_reviewer_node(state: State) -> State:
    try:
        node_input, node_output = invoke_codex_node(state, node_name=NODE_B, role_key=TEST_PLAN_REVIEWER_ROLE)
        return gate_reviewer(node_input, node_output, node_name=NODE_B)
    except Exception as exc:
        return fail_closed_node(state, node_name=NODE_B, exc=exc)


def test_executor_node(state: State) -> State:
    try:
        node_input, node_output = invoke_codex_node(state, node_name=NODE_C, role_key=TEST_EXECUTOR_ROLE)
        return gate_executor(node_input, node_output)
    except Exception as exc:
        return fail_closed_node(state, node_name=NODE_C, exc=exc)


def test_result_reviewer_node(state: State) -> State:
    try:
        node_input, node_output = invoke_codex_node(state, node_name=NODE_D, role_key=TEST_RESULT_REVIEWER_ROLE)
        return gate_reviewer(node_input, node_output, node_name=NODE_D)
    except Exception as exc:
        return fail_closed_node(state, node_name=NODE_D, exc=exc)


def test_report_writer_node(state: State) -> State:
    try:
        node_input, node_output = invoke_codex_node(state, node_name=NODE_E, role_key=TEST_REPORT_WRITER_ROLE)
        return gate_report_writer(node_input, node_output)
    except Exception as exc:
        return fail_closed_node(state, node_name=NODE_E, exc=exc)


def final_reviewer_node(state: State) -> State:
    try:
        node_input, node_output = invoke_codex_node(state, node_name=NODE_F, role_key=FINAL_REVIEWER_ROLE)
        return gate_final_reviewer(node_input, node_output)
    except Exception as exc:
        return fail_closed_node(state, node_name=NODE_F, exc=exc)


def route_by_gate(state: State) -> str:
    route = state.get("gate_route")
    if route in {NODE_A, NODE_B, NODE_C, NODE_D, NODE_E, NODE_F, ROUTE_END}:
        return str(route)
    return ROUTE_END


def create_graph():
    graph = StateGraph(State)

    graph.add_node(NODE_A, test_plan_author_node)
    graph.add_node(NODE_B, test_plan_reviewer_node)
    graph.add_node(NODE_C, test_executor_node)
    graph.add_node(NODE_D, test_result_reviewer_node)
    graph.add_node(NODE_E, test_report_writer_node)
    graph.add_node(NODE_F, final_reviewer_node)

    graph.add_edge(START, NODE_A)
    graph.add_conditional_edges(
        NODE_A,
        route_by_gate,
        {
            NODE_A: NODE_A,
            NODE_B: NODE_B,
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_B,
        route_by_gate,
        {
            NODE_A: NODE_A,
            NODE_C: NODE_C,
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_C,
        route_by_gate,
        {
            NODE_D: NODE_D,
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_D,
        route_by_gate,
        {
            NODE_C: NODE_C,
            NODE_E: NODE_E,
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_E,
        route_by_gate,
        {
            NODE_F: NODE_F,
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_F,
        route_by_gate,
        {
            ROUTE_END: END,
        },
    )
    return graph.compile()


def main() -> dict[str, Any]:
    state = initialize_state(initial_values={"status": True})
    graph = create_graph()
    return graph.invoke(state)


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
