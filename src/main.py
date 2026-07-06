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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_REGISTRY_PATH = PROJECT_ROOT / "config" / "agent_registry.json"
NODE_MESSAGE_SCHEMA_PATH = PROJECT_ROOT / "config" / "node_message_schema.json"
QUALITY_LAW_PATH = PROJECT_ROOT / "skills" / "aegis_global_quality_law" / "SKILL.md"
NODE_TIMEOUT_SECONDS = int(os.environ.get("AEGIS_NODE_TIMEOUT_SECONDS", "1800"))


State: TypeAlias = dict[str, Any]
TEST_PLAN_AUTHOR_ROLE = "TEST_PLAN_AUTHOR"
TEST_PLAN_AUTHOR_NODE = "A"
TEST_PLAN_REVIEWER_ROLE = "TEST_PLAN_REVIEWER"
TEST_PLAN_REVIEWER_NODE = "B"
TEST_EXECUTOR_ROLE = "TEST_EXECUTOR"
TEST_EXECUTOR_NODE = "C"
TEST_RESULT_REVIEWER_ROLE = "TEST_RESULT_REVIEWER"
TEST_RESULT_REVIEWER_NODE = "D"
TEST_REPORT_WRITER_ROLE = "TEST_REPORT_WRITER"
TEST_REPORT_WRITER_NODE = "E"
FINAL_REVIEWER_ROLE = "FINAL_REVIEWER"
FINAL_REVIEWER_NODE = "F"


def load_agent_thread_map(config_path: Path = AGENT_REGISTRY_PATH) -> dict[str, str]:
    registry = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        agent["role_key"]: agent["thread_id"]
        for agent in registry["agents"]
    }


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
    state["current_node"] = current_node
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


def require_node_success(node_name: str, node_output: State) -> None:
    if node_output.get("status") is False:
        raise RuntimeError(f"{node_name} returned status=false")


def log_node_event(node_name: str, event: str) -> None:
    print(f"[aegis] node={node_name} event={event}", file=sys.stderr, flush=True)


def build_node_prompt(node_input: State) -> str:
    schema = load_node_message_schema()
    payload = {
        field_name: node_input.get(field_name)
        for field_name in schema.get("properties", {})
    }
    return json.dumps(payload, ensure_ascii=False)


def test_plan_author_node(state: State) -> State:
    log_node_event(TEST_PLAN_AUTHOR_NODE, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_PLAN_AUTHOR_NODE
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[TEST_PLAN_AUTHOR_ROLE], prompt)
    node_output = json.loads(response)
    require_node_success(TEST_PLAN_AUTHOR_NODE, node_output)
    log_node_event(TEST_PLAN_AUTHOR_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_PLAN_AUTHOR_NODE,
    }


def test_plan_reviewer_node(state: State) -> State:
    log_node_event(TEST_PLAN_REVIEWER_NODE, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_PLAN_REVIEWER_NODE
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[TEST_PLAN_REVIEWER_ROLE], prompt)
    node_output = json.loads(response)
    log_node_event(TEST_PLAN_REVIEWER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_PLAN_REVIEWER_NODE,
    }


def test_executor_node(state: State) -> State:
    log_node_event(TEST_EXECUTOR_NODE, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_EXECUTOR_NODE
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[TEST_EXECUTOR_ROLE], prompt)
    node_output = json.loads(response)
    require_node_success(TEST_EXECUTOR_NODE, node_output)
    log_node_event(TEST_EXECUTOR_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_EXECUTOR_NODE,
    }


def test_result_reviewer_node(state: State) -> State:
    log_node_event(TEST_RESULT_REVIEWER_NODE, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_RESULT_REVIEWER_NODE
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[TEST_RESULT_REVIEWER_ROLE], prompt)
    node_output = json.loads(response)
    log_node_event(TEST_RESULT_REVIEWER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_RESULT_REVIEWER_NODE,
    }


def test_report_writer_node(state: State) -> State:
    log_node_event(TEST_REPORT_WRITER_NODE, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_REPORT_WRITER_NODE
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[TEST_REPORT_WRITER_ROLE], prompt)
    node_output = json.loads(response)
    log_node_event(TEST_REPORT_WRITER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_REPORT_WRITER_NODE,
    }


def final_reviewer_node(state: State) -> State:
    log_node_event(FINAL_REVIEWER_NODE, "start")
    agent_thread_map = load_agent_thread_map()
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = FINAL_REVIEWER_NODE
    prompt = build_node_prompt(node_input)
    response = send_prompt_to_thread(agent_thread_map[FINAL_REVIEWER_ROLE], prompt)
    node_output = json.loads(response)
    log_node_event(FINAL_REVIEWER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": FINAL_REVIEWER_NODE,
    }


def route_by_status(state: State) -> bool:
    return bool(state["status"])


def create_graph():
    graph = StateGraph(State)
    
    graph.add_node(TEST_PLAN_AUTHOR_NODE, test_plan_author_node)
    graph.add_node(TEST_PLAN_REVIEWER_NODE, test_plan_reviewer_node)
    graph.add_node(TEST_EXECUTOR_NODE, test_executor_node)
    graph.add_node(TEST_RESULT_REVIEWER_NODE, test_result_reviewer_node)
    graph.add_node(TEST_REPORT_WRITER_NODE, test_report_writer_node)
    graph.add_node(FINAL_REVIEWER_NODE, final_reviewer_node)

    graph.add_edge(START, TEST_PLAN_AUTHOR_NODE)
    graph.add_edge(TEST_PLAN_AUTHOR_NODE, TEST_PLAN_REVIEWER_NODE)
    graph.add_edge(TEST_EXECUTOR_NODE, TEST_RESULT_REVIEWER_NODE)
    graph.add_edge(TEST_REPORT_WRITER_NODE, FINAL_REVIEWER_NODE)
    graph.add_edge(FINAL_REVIEWER_NODE, END)
    graph.add_conditional_edges(
        TEST_PLAN_REVIEWER_NODE,
        route_by_status,
        {
            True: TEST_EXECUTOR_NODE,
            False: TEST_PLAN_AUTHOR_NODE,
        },
    )
    graph.add_conditional_edges(
        TEST_RESULT_REVIEWER_NODE,
        route_by_status,
        {
            True: TEST_REPORT_WRITER_NODE,
            False: TEST_EXECUTOR_NODE,
        },
    )
    return graph.compile()



def main() -> dict[str, Any]:
    state = initialize_state(initial_values={"status": True})
    graph = create_graph()
    return graph.invoke(state)


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
