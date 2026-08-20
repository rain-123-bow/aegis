from __future__ import annotations

import io
import json
import queue
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from experiments.codex_app_server_collaboration.app_server_client import (
    AppServerClient,
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
            self._thread_index += 1
            thread_id = f"thread-{self._thread_index}"
            self.stdout.push(
                {
                    "id": request_id,
                    "result": {
                        "thread": {"id": thread_id},
                        "model": "fake-model",
                        "reasoningEffort": "low",
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
                        "turn": {
                            "id": f"stale-{thread_id}",
                            "status": "completed",
                        },
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
        self.stdout.push(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "completedAtMs": 1,
                    "item": {
                        "id": f"item-{turn_id}",
                        "type": "agentMessage",
                        "text": output,
                    },
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
    def test_parallel_turns_are_correlated_by_thread_and_turn_id(self) -> None:
        process = _ScriptedProcess()
        client = AppServerClient(
            command=("fake-codex",),
            cwd=Path.cwd(),
            process_factory=lambda *args, **kwargs: process,
            request_timeout_seconds=2,
            turn_timeout_seconds=2,
        )

        with client:
            alpha = client.start_thread(ephemeral=True)
            beta = client.start_thread(ephemeral=True)
            with ThreadPoolExecutor(max_workers=2) as pool:
                alpha_future = pool.submit(client.run_turn, alpha.thread_id, "ALPHA")
                beta_future = pool.submit(client.run_turn, beta.thread_id, "BETA")
                alpha_result = alpha_future.result(timeout=3)
                beta_result = beta_future.result(timeout=3)

        self.assertEqual(alpha_result.final_message, "ALPHA_RESULT")
        self.assertEqual(beta_result.final_message, "BETA_RESULT")
        self.assertNotEqual(alpha_result.turn_id, beta_result.turn_id)
        self.assertLess(
            max(alpha_result.started_at, beta_result.started_at),
            min(alpha_result.completed_at, beta_result.completed_at),
        )


if __name__ == "__main__":
    unittest.main()
