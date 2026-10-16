from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph


class State(TypedDict):
    message: str


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
        )

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


def build_graph(thread_a: str, thread_b: str):
    def node_a(state: State) -> State:
        return {"message": send_prompt_to_thread(thread_a, state["message"])}

    def node_b(state: State) -> State:
        return {"message": send_prompt_to_thread(thread_b, state["message"])}

    graph = StateGraph(State)
    graph.add_node("A", node_a)
    graph.add_node("B", node_b)
    graph.set_entry_point("A")
    graph.add_edge("A", "B")
    graph.add_edge("B", END)
    return graph.compile()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Legacy CLI forwarding demo; this does not run the Aegis governance workflow."
    )
    parser.add_argument("--thread-a", required=True, help="Explicitly authorized existing Codex thread")
    parser.add_argument("--thread-b", required=True, help="Explicitly authorized existing Codex thread")
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()
    result = build_graph(args.thread_a, args.thread_b).invoke({"message": args.prompt})
    output = result["message"]
    print(output, end="" if output.endswith("\n") else "\n")


if __name__ == "__main__":
    main()
