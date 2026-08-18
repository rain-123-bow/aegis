from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def _relaunch_isolated_if_needed() -> None:
    if __name__ != "__main__":
        return
    if sys.flags.isolated and sys.flags.dont_write_bytecode and sys.pycache_prefix:
        return
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is required for isolated Aegis startup")
    cache_parent = os.path.join(local_app_data, "Aegis", "isolated-pycache")
    os.makedirs(cache_parent, exist_ok=True)
    prefix = os.path.join(cache_parent, "disabled")
    os.makedirs(prefix, exist_ok=True)
    if os.listdir(prefix):
        raise RuntimeError("isolated Aegis pycache prefix is not empty")
    os.environ["AEGIS_ISOLATED_PYCACHE_PREFIX"] = prefix
    source_directory = os.path.dirname(os.path.abspath(__file__))
    bootstrap = (
        "sys=__import__('sys');runpy=__import__('runpy');"
        f"sys.path.insert(0,{source_directory!r});"
        f"runpy.run_path({os.path.abspath(__file__)!r},run_name='__main__')"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            f"pycache_prefix={prefix}",
            "-c",
            bootstrap,
            *sys.argv[1:],
        ],
        check=False,
    )
    raise SystemExit(completed.returncode)


_relaunch_isolated_if_needed()

sys.dont_write_bytecode = True

from pathlib import Path
from typing import Any, TypeAlias

from langgraph.graph import END, START, StateGraph

from aegis_runtime import (
    RuntimeCoordinator,
    TraceRelayClient,
    active_runtime_coordinator,
    initialize_runtime_authority,
    load_run_state,
    new_run_id,
    open_graph_checkpointer,
    parse_loopback_proxy_port,
    resolve_tracerelay_command,
)
from project_seal_store import (
    hold_verified_project_git_runtime,
    load_project_seal_chain,
    verify_expected_project_seal,
)
from final_review_confirmation import record_final_review_confirmation
from mutation_accountability import record_frozen_input_mutation_reason
from remote_seal_witness import assert_remote_witness_not_published
from skill_binding import all_role_skill_bindings, load_role_skill_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_REGISTRY_PATH = PROJECT_ROOT / "config" / "agent_registry.json"
NODE_MESSAGE_SCHEMA_PATH = PROJECT_ROOT / "config" / "node_message_schema.json"
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
GRAPH_NODE_CHOICES = (
    TEST_PLAN_AUTHOR_NODE,
    TEST_PLAN_REVIEWER_NODE,
    TEST_EXECUTOR_NODE,
    TEST_RESULT_REVIEWER_NODE,
    TEST_REPORT_WRITER_NODE,
    FINAL_REVIEWER_NODE,
)
PLANNING_APP_SERVER_ROLES = {
    TEST_PLAN_AUTHOR_ROLE,
    TEST_PLAN_REVIEWER_ROLE,
}
EXECUTION_APP_SERVER_ROLES = {
    TEST_EXECUTOR_ROLE,
    TEST_RESULT_REVIEWER_ROLE,
    TEST_REPORT_WRITER_ROLE,
    FINAL_REVIEWER_ROLE,
}


def load_agent_thread_map(config_path: Path = AGENT_REGISTRY_PATH) -> dict[str, str]:
    del config_path
    raise RuntimeError("real thread IDs are available only in the dynamic registry")


def load_agent_config(
    role_key: str, config_path: Path = AGENT_REGISTRY_PATH
) -> dict[str, Any]:
    registry = json.loads(config_path.read_text(encoding="utf-8"))
    for agent in registry["agents"]:
        if agent["role_key"] == role_key:
            return dict(agent)
    raise KeyError(f"agent role not found: {role_key}")


def load_node_message_schema(
    config_path: Path = NODE_MESSAGE_SCHEMA_PATH,
) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def initialize_state(
    schema_path: Path = NODE_MESSAGE_SCHEMA_PATH,
    *,
    current_node: str = "START",
    initial_values: dict[str, Any] | None = None,
) -> State:
    schema = load_node_message_schema(schema_path)
    values = initial_values or {}
    state: State = {
        field_name: values.get(field_name)
        for field_name in schema.get("properties", {})
    }
    if state.get("reasoning_ledger_context_pack") is None and state.get(
        "artifact_path"
    ):
        state["reasoning_ledger_context_pack"] = str(
            Path(state["artifact_path"]) / "REASONING_LEDGER_CONTEXT_PACK.json"
        )
    state["current_node"] = current_node
    return state


def resolve_codex_command() -> str:
    command = (
        shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    )
    if command is None:
        raise RuntimeError("codex command was not found on PATH")
    return command


def send_prompt_to_thread(thread_id: str, prompt: str) -> str:
    output_path: Path | None = None
    retain_output = False
    try:
        coordinator = active_runtime_coordinator()
        if coordinator is None:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".txt",
                delete=False,
            ) as output_file:
                output_path = Path(output_file.name)
        else:
            output_path = coordinator.new_response_path()
            retain_output = True

        command = [
            resolve_codex_command(),
            "exec",
            "resume",
            "--output-last-message",
            str(output_path),
            thread_id,
            prompt,
        ]
        try:
            if coordinator is None:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                    timeout=NODE_TIMEOUT_SECONDS,
                )
            else:
                completed = coordinator.run_codex_process(
                    command, timeout_seconds=NODE_TIMEOUT_SECONDS
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
        if output_path is not None and not retain_output:
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


def build_planning_prompt(node_input: State, control: dict[str, object]) -> str:
    schema_name = control.get("schema")
    if not isinstance(schema_name, str) or not schema_name:
        raise RuntimeError("planning control has no schema identifier")
    return json.dumps(
        {
            "node_message": json.loads(build_node_prompt(node_input)),
            schema_name: control,
        },
        ensure_ascii=False,
    )


def planning_review_output_schema() -> dict[str, Any]:
    schema = json.loads(json.dumps(load_node_message_schema()))
    properties = schema.setdefault("properties", {})
    properties.update(
        {
            "reviewed_plan_sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "error_count": {"type": "integer", "minimum": 0},
            "warning_count": {"type": "integer", "minimum": 0},
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "semantic_issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "semantic_issue_id",
                        "premises",
                        "inference",
                        "conclusion",
                        "missing_evidence",
                        "alternative_explanations",
                        "closure_conditions",
                        "predecessor_issue_ids",
                    ],
                    "properties": {
                        "semantic_issue_id": {"type": "string", "minLength": 1},
                        "premises": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "inference": {"type": "string", "minLength": 1},
                        "conclusion": {"type": "string", "minLength": 1},
                        "missing_evidence": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                        "alternative_explanations": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                        "closure_conditions": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "predecessor_issue_ids": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
            "prior_issue_assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "prior_semantic_issue_id",
                        "disposition",
                        "current_semantic_issue_ids",
                        "rationale",
                        "evidence",
                    ],
                    "properties": {
                        "prior_semantic_issue_id": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "disposition": {
                            "type": "string",
                            "enum": [
                                "REPEATED_UNRESOLVED",
                                "RESOLVED",
                                "SUPERSEDED",
                            ],
                        },
                        "current_semantic_issue_ids": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "rationale": {"type": "string", "minLength": 1},
                        "evidence": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        }
    )
    required = list(schema.setdefault("required", []))
    for field_name in (
        "reviewed_plan_sha256",
        "score",
        "error_count",
        "warning_count",
        "verdict",
        "semantic_issues",
        "prior_issue_assessments",
    ):
        if field_name not in required:
            required.append(field_name)
    schema["required"] = required
    return schema


def build_planning_role_instructions(agent_config: dict[str, Any]) -> str:
    role_key = agent_config.get("role_key", "unknown")
    description = agent_config.get("role_description", "")
    boundary = (
        f"You are the persistent {role_key} role in a coordinator-controlled test "
        f"planning stage. {description}\n"
        "Read the JSON node message and the artifact folder's README.md before acting. "
        "Write durable work products into artifact_path. Return only JSON matching the "
        "provided output schema. Treat coordinator-provided paths and identifiers as "
        "accepted control facts; independently verify claims made by another role. "
        "Do not communicate directly with other agent threads. Do not trade correctness "
        "or coverage for speed."
    )
    return load_role_skill_bundle(str(role_key), agent_config).compose(boundary)


def build_execution_role_instructions(agent_config: dict[str, Any]) -> str:
    role_key = agent_config.get("role_key", "unknown")
    description = agent_config.get("role_description", "")
    boundary = (
        f"You are the persistent {role_key} role in a coordinator-controlled test "
        f"execution stage. {description}\n"
        "Read the JSON node message and the artifact folder's README.md before acting. "
        "Write durable work products and raw evidence into artifact_path. Return only "
        "JSON matching the provided output schema. Treat coordinator-provided paths as "
        "accepted control facts; independently verify claims made by another role. "
        "Do not communicate directly with other agent threads. Do not trade correctness "
        "or coverage for speed."
    )
    return load_role_skill_bundle(str(role_key), agent_config).compose(boundary)


def send_planning_prompt(
    role_key: str,
    prompt: str,
    *,
    output_schema: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> str:
    if role_key not in PLANNING_APP_SERVER_ROLES:
        raise ValueError(f"unsupported planning role: {role_key}")
    agent_config = {**load_agent_config(role_key), "role_key": role_key}
    coordinator = active_runtime_coordinator()
    if coordinator is None:
        raise RuntimeError("planning roles require an active RuntimeCoordinator")
    return coordinator.run_planning_agent(
        role_key,
        prompt,
        output_schema=output_schema or load_node_message_schema(),
        developer_instructions=build_planning_role_instructions(agent_config),
        job_id=job_id,
    )


def send_execution_prompt(role_key: str, prompt: str) -> str:
    if role_key not in EXECUTION_APP_SERVER_ROLES:
        raise ValueError(f"unsupported execution role: {role_key}")
    agent_config = {**load_agent_config(role_key), "role_key": role_key}
    coordinator = active_runtime_coordinator()
    if coordinator is None:
        raise RuntimeError("execution roles require an active RuntimeCoordinator")
    return coordinator.run_execution_agent(
        role_key,
        prompt,
        output_schema=load_node_message_schema(),
        developer_instructions=build_execution_role_instructions(agent_config),
        timeout_seconds=NODE_TIMEOUT_SECONDS,
    )


def require_control_envelope_unchanged(
    node_name: str, node_input: State, node_output: State
) -> None:
    for field_name in ("artifact_path", "reasoning_ledger_context_pack"):
        expected = node_input.get(field_name)
        actual = node_output.get(field_name)
        if not isinstance(expected, str) or not isinstance(actual, str):
            raise RuntimeError(f"{node_name} returned an invalid {field_name}")
        if Path(actual).resolve() != Path(expected).resolve():
            raise RuntimeError(f"{node_name} changed coordinator-owned {field_name}")
    if not isinstance(node_output.get("status"), bool):
        raise RuntimeError(f"{node_name} returned a non-boolean status")


def test_plan_author_node(state: State) -> State:
    log_node_event(TEST_PLAN_AUTHOR_NODE, "start")
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_PLAN_AUTHOR_NODE
    coordinator = active_runtime_coordinator()
    control: dict[str, object] | None = None
    if coordinator is not None:
        context_path = node_input.get("reasoning_ledger_context_pack")
        if not isinstance(context_path, str) or not context_path:
            raise RuntimeError("A requires reasoning_ledger_context_pack")
        control = coordinator.prepare_planning_author(context_path)
        if control.get("skip_turn") is True:
            log_node_event(TEST_PLAN_AUTHOR_NODE, "recovered_frozen_round")
            return node_input
    prompt = (
        build_planning_prompt(node_input, control)
        if control is not None
        else build_node_prompt(node_input)
    )
    response = send_planning_prompt(
        TEST_PLAN_AUTHOR_ROLE,
        prompt,
        job_id=str(control["job_id"]) if control is not None else None,
    )
    node_output = json.loads(response)
    require_node_success(TEST_PLAN_AUTHOR_NODE, node_output)
    if coordinator is not None:
        require_control_envelope_unchanged(
            TEST_PLAN_AUTHOR_NODE, node_input, node_output
        )
        assert control is not None
        coordinator.freeze_planning_plan(str(control["round_id"]))
    log_node_event(TEST_PLAN_AUTHOR_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_PLAN_AUTHOR_NODE,
    }


def test_plan_reviewer_node(state: State) -> State:
    log_node_event(TEST_PLAN_REVIEWER_NODE, "start")
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_PLAN_REVIEWER_NODE
    coordinator = active_runtime_coordinator()
    control: dict[str, object] | None = None
    if coordinator is not None:
        control = coordinator.prepare_planning_review()
        if control.get("skip_turn") is True:
            accepted = control.get("accepted") is True
            node_output = {"status": accepted}
        else:
            prompt = build_planning_prompt(node_input, control)
            response = send_planning_prompt(
                TEST_PLAN_REVIEWER_ROLE,
                prompt,
                output_schema=planning_review_output_schema(),
                job_id=str(control["job_id"]),
            )
            node_output = json.loads(response)
            require_control_envelope_unchanged(
                TEST_PLAN_REVIEWER_NODE, node_input, node_output
            )
            accepted = coordinator.record_planning_review(
                str(control["round_id"]), node_output
            )
            node_output = {
                field_name: node_output[field_name]
                for field_name in load_node_message_schema().get("properties", {})
                if field_name in node_output
            }
            node_output["status"] = accepted
        if accepted:
            coordinator.complete_planning_stage()
    else:
        prompt = build_node_prompt(node_input)
        response = send_planning_prompt(TEST_PLAN_REVIEWER_ROLE, prompt)
        node_output = json.loads(response)
    log_node_event(TEST_PLAN_REVIEWER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_PLAN_REVIEWER_NODE,
    }


def test_executor_node(state: State) -> State:
    log_node_event(TEST_EXECUTOR_NODE, "start")
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_EXECUTOR_NODE
    coordinator = active_runtime_coordinator()
    if coordinator is None or not hasattr(coordinator, "test_execution_control"):
        prompt = build_node_prompt(node_input)
    else:
        prompt = json.dumps(
            {
                "node_message": json.loads(build_node_prompt(node_input)),
                "test_execution_control": coordinator.test_execution_control(),
            },
            ensure_ascii=False,
        )
    response = send_execution_prompt(TEST_EXECUTOR_ROLE, prompt)
    node_output = json.loads(response)
    require_control_envelope_unchanged(TEST_EXECUTOR_NODE, node_input, node_output)
    require_node_success(TEST_EXECUTOR_NODE, node_output)
    log_node_event(TEST_EXECUTOR_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_EXECUTOR_NODE,
    }


def test_result_reviewer_node(state: State) -> State:
    log_node_event(TEST_RESULT_REVIEWER_NODE, "start")
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_RESULT_REVIEWER_NODE
    coordinator = active_runtime_coordinator()
    if coordinator is None or not hasattr(coordinator, "execution_node_control"):
        prompt = build_node_prompt(node_input)
    else:
        prompt = json.dumps(
            {
                "node_message": json.loads(build_node_prompt(node_input)),
                "execution_control": coordinator.execution_node_control(),
            },
            ensure_ascii=False,
        )
    response = send_execution_prompt(TEST_RESULT_REVIEWER_ROLE, prompt)
    node_output = json.loads(response)
    require_control_envelope_unchanged(
        TEST_RESULT_REVIEWER_NODE, node_input, node_output
    )
    log_node_event(TEST_RESULT_REVIEWER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_RESULT_REVIEWER_NODE,
    }


def test_report_writer_node(state: State) -> State:
    log_node_event(TEST_REPORT_WRITER_NODE, "start")
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = TEST_REPORT_WRITER_NODE
    coordinator = active_runtime_coordinator()
    if coordinator is None or not hasattr(coordinator, "execution_node_control"):
        prompt = build_node_prompt(node_input)
    else:
        prompt = json.dumps(
            {
                "node_message": json.loads(build_node_prompt(node_input)),
                "execution_control": coordinator.execution_node_control(),
            },
            ensure_ascii=False,
        )
    response = send_execution_prompt(TEST_REPORT_WRITER_ROLE, prompt)
    node_output = json.loads(response)
    require_control_envelope_unchanged(TEST_REPORT_WRITER_NODE, node_input, node_output)
    log_node_event(TEST_REPORT_WRITER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": TEST_REPORT_WRITER_NODE,
    }


def final_reviewer_node(state: State) -> State:
    log_node_event(FINAL_REVIEWER_NODE, "start")
    node_input = dict(state)
    node_input["status"] = True
    node_input["current_node"] = FINAL_REVIEWER_NODE
    coordinator = active_runtime_coordinator()
    if coordinator is None or not hasattr(coordinator, "execution_node_control"):
        prompt = build_node_prompt(node_input)
    else:
        prompt = json.dumps(
            {
                "node_message": json.loads(build_node_prompt(node_input)),
                "execution_control": coordinator.execution_node_control(),
            },
            ensure_ascii=False,
        )
    response = send_execution_prompt(FINAL_REVIEWER_ROLE, prompt)
    node_output = json.loads(response)
    require_control_envelope_unchanged(FINAL_REVIEWER_NODE, node_input, node_output)
    log_node_event(FINAL_REVIEWER_NODE, "done")
    return {
        **node_input,
        **node_output,
        "current_node": FINAL_REVIEWER_NODE,
    }


def route_by_status(state: State) -> bool:
    return bool(state["status"])


def create_graph(
    start_node: str = TEST_PLAN_AUTHOR_NODE,
    *,
    checkpointer: Any | None = None,
    coordinator: RuntimeCoordinator | None = None,
):
    if start_node not in GRAPH_NODE_CHOICES:
        raise ValueError(f"unsupported start node: {start_node}")

    graph = StateGraph(State)

    def managed_node(node_name: str, operation: Any) -> Any:
        if coordinator is None:
            return operation

        def run(state: State) -> State:
            return coordinator.execute_node(node_name, operation, state)

        return run

    graph.add_node(
        TEST_PLAN_AUTHOR_NODE,
        managed_node(TEST_PLAN_AUTHOR_NODE, test_plan_author_node),
    )
    graph.add_node(
        TEST_PLAN_REVIEWER_NODE,
        managed_node(TEST_PLAN_REVIEWER_NODE, test_plan_reviewer_node),
    )
    graph.add_node(
        TEST_EXECUTOR_NODE,
        managed_node(TEST_EXECUTOR_NODE, test_executor_node),
    )
    graph.add_node(
        TEST_RESULT_REVIEWER_NODE,
        managed_node(TEST_RESULT_REVIEWER_NODE, test_result_reviewer_node),
    )
    graph.add_node(
        TEST_REPORT_WRITER_NODE,
        managed_node(TEST_REPORT_WRITER_NODE, test_report_writer_node),
    )
    graph.add_node(
        FINAL_REVIEWER_NODE,
        managed_node(FINAL_REVIEWER_NODE, final_reviewer_node),
    )

    graph.add_edge(START, start_node)
    graph.add_edge(TEST_PLAN_AUTHOR_NODE, TEST_PLAN_REVIEWER_NODE)
    graph.add_edge(TEST_EXECUTOR_NODE, TEST_RESULT_REVIEWER_NODE)
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
    graph.add_conditional_edges(
        TEST_REPORT_WRITER_NODE,
        route_by_status,
        {
            True: FINAL_REVIEWER_NODE,
            False: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)


def resolve_project_runtime_root(
    project_root: str | Path,
    configured_runtime_root: str | Path | None,
) -> Path:
    project = Path(project_root).resolve()
    if configured_runtime_root is not None:
        runtime_root = Path(configured_runtime_root).resolve()
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise RuntimeError(
                "LOCALAPPDATA is unavailable; provide --runtime-root explicitly"
            )
        project_id = load_project_seal_chain(project).records[-1].project_id.hex()
        runtime_root = (
            Path(local_app_data).resolve() / "Aegis" / "runtime" / project_id
        )
    project_aegis = project / ".aegis"
    try:
        runtime_root.relative_to(project_aegis)
    except ValueError:
        return runtime_root
    raise RuntimeError("runtime root must stay outside the project .aegis directory")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Aegis A-F test workflow.")
    parser.add_argument(
        "--start-node",
        choices=GRAPH_NODE_CHOICES,
        default=None,
        help="Graph node to start from. Use C to rerun tests and continue with D/E/F.",
    )
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project whose runtime behavior and reasoning ledger are governed.",
    )
    parser.add_argument(
        "--runtime-root",
        help=(
            "Project-specific local runtime root. Defaults to "
            "%%LOCALAPPDATA%%/Aegis/runtime/<project-id>."
        ),
    )
    parser.add_argument(
        "--artifact-path",
        help=(
            "Compatibility check only. Must equal "
            "<runtime-root>/runs/<workflow-run-id>/artifacts."
        ),
    )
    parser.add_argument(
        "--reasoning-ledger-context-pack",
        help="Override reasoning ledger context pack path passed to graph nodes.",
    )
    parser.add_argument(
        "--engineering-input-manifest",
        help=(
            "Master-authored manifest that freezes requirement and implementation-plan "
            "documents for this workflow run."
        ),
    )
    parser.add_argument(
        "--reuse-planning-from-run-id",
        help=(
            "For a new C-start run, reuse the approved test plan from this terminal "
            "run after proving engineering inputs are unchanged."
        ),
    )
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument(
        "--run-id",
        help="Optional caller-provided ID for a new run; a unique ID is generated otherwise.",
    )
    run_group.add_argument(
        "--resume-run-id",
        help="Resume the existing LangGraph checkpoint for this run ID.",
    )
    parser.add_argument(
        "--tracerelay-command",
        help="Absolute path to the installed tracerelay.exe.",
    )
    parser.add_argument(
        "--tracerelay-upstream-port",
        type=int,
        help="Loopback HTTP proxy port used as TraceRelay's upstream.",
    )
    arguments = parser.parse_args(argv)
    if arguments.resume_run_id and arguments.start_node is not None:
        parser.error("--start-node cannot be used with --resume-run-id")
    if arguments.resume_run_id and (
        arguments.engineering_input_manifest
        or arguments.reuse_planning_from_run_id
        or arguments.reasoning_ledger_context_pack
    ):
        parser.error(
            "resume uses saved frozen inputs; input and planning-reuse options are forbidden"
        )
    return arguments


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise RuntimeError(f"project root is not a directory: {project_root}")
    runtime_root = resolve_project_runtime_root(project_root, args.runtime_root)

    prior_state: dict[str, object] | None = None
    planning_reuse_state: dict[str, object] | None = None
    if args.resume_run_id:
        run_id = args.resume_run_id
        prior_state = load_run_state(runtime_root, run_id)
        if prior_state.get("status") in {"completed", "terminated"}:
            raise RuntimeError(f"Aegis run is already terminal: {run_id}")
        stored_root = prior_state.get("project_root")
        if (
            not isinstance(stored_root, str)
            or Path(stored_root).resolve() != project_root
        ):
            raise RuntimeError("resume project root does not match the saved run")
        stored_start_node = prior_state.get("start_node")
        if stored_start_node not in GRAPH_NODE_CHOICES:
            raise RuntimeError("saved run contains an invalid start node")
        start_node = str(stored_start_node)
        stored_artifact_path = prior_state.get("artifact_path")
        if not isinstance(stored_artifact_path, str) or not stored_artifact_path:
            raise RuntimeError("saved run has no artifact path")
        artifact_path = Path(stored_artifact_path).resolve()
        if args.artifact_path and Path(args.artifact_path).resolve() != artifact_path:
            raise RuntimeError("resume artifact path does not match the saved run")
        graph_input: State | None = None
    else:
        run_id = args.run_id or new_run_id()
        start_node = args.start_node or TEST_PLAN_AUTHOR_NODE
        if start_node not in {TEST_PLAN_AUTHOR_NODE, TEST_EXECUTOR_NODE}:
            raise RuntimeError("a new run may start only at A or C")
        if not args.engineering_input_manifest:
            raise RuntimeError("a new run requires --engineering-input-manifest")
        if start_node == TEST_EXECUTOR_NODE:
            if not args.reuse_planning_from_run_id:
                raise RuntimeError(
                    "a new C-start run requires --reuse-planning-from-run-id"
                )
            if not args.reasoning_ledger_context_pack:
                raise RuntimeError(
                    "a new C-start run requires --reasoning-ledger-context-pack"
                )
            if args.reuse_planning_from_run_id == run_id:
                raise RuntimeError("a run cannot reuse its own planning result")
            planning_reuse_state = load_run_state(
                runtime_root, args.reuse_planning_from_run_id
            )
        elif args.reuse_planning_from_run_id:
            raise RuntimeError("planning reuse is valid only with --start-node C")
        artifact_path = runtime_root / "runs" / run_id / "artifacts"
        if args.artifact_path and Path(args.artifact_path).resolve() != artifact_path:
            raise RuntimeError(
                "artifact path must equal the run-scoped path under runtime root"
            )
        initial_values: dict[str, Any] = {
            "status": True,
            "artifact_path": str(artifact_path),
        }
        if args.reasoning_ledger_context_pack:
            initial_values["reasoning_ledger_context_pack"] = (
                args.reasoning_ledger_context_pack
            )
        state = initialize_state(initial_values=initial_values)
        graph_input = state

    upstream_port = args.tracerelay_upstream_port
    if upstream_port is None:
        proxy_url = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
        )
        if not proxy_url:
            raise RuntimeError(
                "TraceRelay requires --tracerelay-upstream-port or a loopback HTTP proxy"
            )
        upstream_port = parse_loopback_proxy_port(proxy_url)

    relay_command = resolve_tracerelay_command(args.tracerelay_command)
    relay_client = TraceRelayClient(command=relay_command)
    role_configs = {
        role_key: load_agent_config(role_key)
        for role_key in (
            TEST_PLAN_AUTHOR_ROLE,
            TEST_PLAN_REVIEWER_ROLE,
            TEST_EXECUTOR_ROLE,
            TEST_RESULT_REVIEWER_ROLE,
            TEST_REPORT_WRITER_ROLE,
            FINAL_REVIEWER_ROLE,
        )
    }
    coordinator = RuntimeCoordinator(
        project_root=project_root,
        artifact_path=artifact_path,
        runtime_root=runtime_root,
        run_id=run_id,
        upstream_port=upstream_port,
        relay_client=relay_client,
        start_node=start_node,
        prior_state=prior_state,
        role_skill_bindings=all_role_skill_bindings(role_configs),
        role_runtime_profiles={
            role_key: {
                "model": str(config["model"]),
                "reasoning_effort": str(config["reasoning_effort"]),
            }
            for role_key, config in role_configs.items()
        },
        require_remote_witness=True,
        engineering_input_manifest_path=args.engineering_input_manifest,
        planning_reuse_run_id=args.reuse_planning_from_run_id,
        planning_reuse_state=planning_reuse_state,
        planning_reuse_context_pack_path=args.reasoning_ledger_context_pack,
    )
    coordinator.preflight()

    config = {"configurable": {"thread_id": run_id}}
    try:
        if (
            start_node in {TEST_PLAN_AUTHOR_NODE, TEST_PLAN_REVIEWER_NODE}
            and coordinator.planning_stage_status != "completed"
        ):
            coordinator.prepare_planning_agents(
                {
                    role_key: build_planning_role_instructions(
                        load_agent_config(role_key)
                    )
                    for role_key in (
                        TEST_PLAN_AUTHOR_ROLE,
                        TEST_PLAN_REVIEWER_ROLE,
                    )
                }
            )
        with open_graph_checkpointer(runtime_root) as checkpointer:
            graph = create_graph(
                start_node=start_node,
                checkpointer=checkpointer,
                coordinator=coordinator,
            )
            result = graph.invoke(
                graph_input,
                config=config,
                durability="sync",
            )
        coordinator.complete(result)
    except BaseException as error:
        coordinator.fail(error)
        raise
    return result


def entrypoint(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "ledger":
        from reasoning_ledger.cli import main as ledger_main

        return ledger_main(arguments[1:])
    if arguments and arguments[0] == "confirm-f-failure":
        parser = argparse.ArgumentParser(
            description="Record Master's review of a terminal F failure."
        )
        parser.add_argument("--runtime-root", required=True)
        parser.add_argument("--run-id", required=True)
        parser.add_argument(
            "--decision", required=True, choices=("CONFIRMED", "DISPUTED")
        )
        parser.add_argument("--master-review", required=True)
        parser.add_argument("--evidence", action="append", default=[])
        confirmation_args = parser.parse_args(arguments[1:])
        result = record_final_review_confirmation(
            confirmation_args.runtime_root,
            confirmation_args.run_id,
            decision=confirmation_args.decision,
            master_review_path=confirmation_args.master_review,
            evidence_paths=confirmation_args.evidence,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if arguments and arguments[0] == "initialize-runtime-authority":
        parser = argparse.ArgumentParser(
            description="Initialize the witnessed external runtime authority."
        )
        parser.add_argument("--project-root", type=Path, required=True)
        parser.add_argument("--runtime-root", type=Path, default=None)
        authority_args = parser.parse_args(arguments[1:])
        project_root = authority_args.project_root.resolve()
        with hold_verified_project_git_runtime(project_root) as git_command:
            seal = verify_expected_project_seal(
                project_root,
                git_executable=git_command,
                git_runtime_lock_held=True,
            )
            assert_remote_witness_not_published(
                project_root,
                git_executable=git_command,
                git_runtime_lock_held=True,
            )
            runtime_root = resolve_project_runtime_root(
                project_root, authority_args.runtime_root
            )
            initialize_runtime_authority(
                runtime_root,
                project_id_hex=seal.project_id.hex(),
                runtime_authority_id=seal.runtime_authority_id,
            )
        print(
            json.dumps(
                {
                    "runtime_root": str(runtime_root),
                    "project_id_hex": seal.project_id.hex(),
                    "runtime_authority_id": seal.runtime_authority_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if arguments and arguments[0] == "record-mutation-reason":
        parser = argparse.ArgumentParser(
            description="Record the user's reason for an A-F frozen-input mutation."
        )
        parser.add_argument("--runtime-root", required=True)
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--reason-file", required=True)
        parser.add_argument("--user-confirmation-id", required=True)
        reason_args = parser.parse_args(arguments[1:])
        result = record_frozen_input_mutation_reason(
            reason_args.runtime_root,
            reason_args.run_id,
            reason_path=reason_args.reason_file,
            user_confirmation_id=reason_args.user_confirmation_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(main(arguments), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(entrypoint())
