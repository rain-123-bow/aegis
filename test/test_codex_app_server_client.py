from __future__ import annotations

import io
import json
import queue
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from codex_app_server_client import (  # noqa: E402
    AppServerClient,
    AppServerTurnError,
)


class _QueueReader:
    def __init__(self) -> None:
        self._lines: queue.Queue[str] = queue.Queue()

    def push(self, message: dict[str, Any]) -> None:
        self._lines.put(json.dumps(message, separators=(",", ":")) + "\n")

    def readline(self) -> str:
        return self._lines.get(timeout=5)

    def close(self) -> None:
        self._lines.put("")


class _ScriptedInput:
    def __init__(self, process: "_ScriptedProcess") -> None:
        self._process = process

    def write(self, value: str) -> int:
        for line in value.splitlines():
            if line:
                self._process.handle(json.loads(line))
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _ScriptedProcess:
    def __init__(self) -> None:
        self.stdout = _QueueReader()
        self.stderr = io.StringIO("")
        self.stdin = _ScriptedInput(self)
        self.pid = 4242
        self.returncode: int | None = None
        self._thread_index = 0
        self._turn_index = 0
        self._workers: list[threading.Thread] = []
        self._turn_history: dict[str, dict[str, Any]] = {}
        self.thread_start_params: list[dict[str, Any]] = []

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        for worker in self._workers:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            worker.join(remaining)
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0
        self.stdout.close()

    def kill(self) -> None:
        self.returncode = -9
        self.stdout.close()

    def handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            self.stdout.push({"id": request_id, "result": {"userAgent": "fake"}})
            return
        if method == "initialized":
            return
        if method == "thread/start":
            self.thread_start_params.append(dict(message["params"]))
            self._thread_index += 1
            thread_id = f"thread-{self._thread_index}"
            self.stdout.push(
                {
                    "id": request_id,
                    "result": {
                        "thread": {"id": thread_id},
                        "model": "fake-model",
                        "reasoningEffort": "high",
                    },
                }
            )
            return
        if method == "thread/resume":
            thread_id = message["params"]["threadId"]
            self.stdout.push(
                {
                    "id": request_id,
                    "result": {
                        "thread": {"id": thread_id},
                        "model": "fake-model",
                        "reasoningEffort": "high",
                    },
                }
            )
            return
        if method == "thread/read":
            thread_id = message["params"]["threadId"]
            turns = [
                turn
                for turn in self._turn_history.values()
                if turn["thread_id"] == thread_id
            ]
            self.stdout.push(
                {
                    "id": request_id,
                    "result": {
                        "thread": {
                            "id": thread_id,
                            "turns": [turn["read_payload"] for turn in turns],
                        }
                    },
                }
            )
            return
        if method == "turn/start":
            self._turn_index += 1
            turn_id = f"turn-{self._turn_index}"
            thread_id = message["params"]["threadId"]
            prompt = message["params"]["input"][0]["text"]
            output = "ALPHA_RESULT" if "ALPHA" in prompt else "BETA_RESULT"
            delay = 0.06 if "ALPHA" in prompt else 0.03
            self.stdout.push(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {"id": f"stale-{thread_id}", "status": "completed"},
                    },
                }
            )
            self.stdout.push(
                {
                    "id": request_id,
                    "result": {
                        "turn": {"id": turn_id, "status": "inProgress", "items": []}
                    },
                }
            )
            self.stdout.push(
                {
                    "method": "turn/started",
                    "params": {
                        "threadId": thread_id,
                        "turn": {"id": turn_id, "status": "inProgress", "items": []},
                    },
                }
            )
            worker = threading.Thread(
                target=self._complete_turn,
                args=(thread_id, turn_id, output, delay),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()
            return
        if method == "turn/interrupt":
            self.stdout.push({"id": request_id, "result": {}})
            return
        self.stdout.push(
            {
                "id": request_id,
                "error": {"code": -32601, "message": f"unsupported: {method}"},
            }
        )

    def _complete_turn(
        self, thread_id: str, turn_id: str, output: str, delay: float
    ) -> None:
        time.sleep(delay)
        item = {
            "id": f"item-{turn_id}",
            "type": "agentMessage",
            "text": output,
        }
        self._turn_history[turn_id] = {
            "thread_id": thread_id,
            "read_payload": {
                "id": turn_id,
                "status": "completed",
                "items": [item],
            },
        }
        self.stdout.push(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": item,
                },
            }
        )
        self.stdout.push(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": thread_id,
                    "turn": {"id": turn_id, "status": "completed", "items": []},
                },
            }
        )


class AppServerClientTests(unittest.TestCase):
    def make_client(self, process: _ScriptedProcess) -> AppServerClient:
        return AppServerClient(
            command=("fake-codex",),
            cwd=Path.cwd(),
            process_factory=lambda *args, **kwargs: process,
            request_timeout_seconds=2,
            turn_timeout_seconds=2,
        )

    def test_split_turn_api_exposes_id_before_completion_and_correlates_parallel_turns(
        self,
    ) -> None:
        process = _ScriptedProcess()
        client = self.make_client(process)

        with client:
            alpha = client.start_thread(
                ephemeral=False,
                sandbox="danger-full-access",
                developer_instructions="author",
            )
            beta = client.start_thread(
                ephemeral=False,
                sandbox="danger-full-access",
                developer_instructions="reviewer",
            )
            alpha_turn = client.start_turn(alpha.thread_id, "ALPHA")
            beta_turn = client.start_turn(beta.thread_id, "BETA")
            self.assertEqual(alpha_turn.turn_id, "turn-1")
            self.assertEqual(beta_turn.turn_id, "turn-2")
            with ThreadPoolExecutor(max_workers=2) as pool:
                alpha_future = pool.submit(client.wait_turn, alpha_turn)
                beta_future = pool.submit(client.wait_turn, beta_turn)
                alpha_result = alpha_future.result(timeout=3)
                beta_result = beta_future.result(timeout=3)

        self.assertEqual(alpha_result.final_message, "ALPHA_RESULT")
        self.assertEqual(beta_result.final_message, "BETA_RESULT")
        self.assertNotEqual(alpha_result.turn_id, beta_result.turn_id)
        self.assertEqual(process.thread_start_params[0]["sandbox"], "danger-full-access")
        self.assertEqual(process.thread_start_params[0]["developerInstructions"], "author")

    def test_same_thread_is_single_flight_until_wait_finishes(self) -> None:
        process = _ScriptedProcess()
        client = self.make_client(process)

        with client:
            thread = client.start_thread(ephemeral=False)
            turn = client.start_turn(thread.thread_id, "ALPHA")
            with self.assertRaisesRegex(AppServerTurnError, "already has an active turn"):
                client.start_turn(thread.thread_id, "BETA")
            client.wait_turn(turn)
            second = client.start_turn(thread.thread_id, "BETA")
            self.assertEqual(client.wait_turn(second).final_message, "BETA_RESULT")

    def test_completed_turn_can_be_recovered_from_thread_read(self) -> None:
        process = _ScriptedProcess()
        client = self.make_client(process)

        with client:
            thread = client.start_thread(ephemeral=False)
            turn = client.start_turn(thread.thread_id, "ALPHA")
            expected = client.wait_turn(turn)
            recovered = client.recover_turn(thread.thread_id, turn.turn_id)

        self.assertEqual(recovered.turn_id, expected.turn_id)
        self.assertEqual(recovered.status, "completed")
        self.assertEqual(recovered.final_message, "ALPHA_RESULT")


if __name__ == "__main__":
    unittest.main()
