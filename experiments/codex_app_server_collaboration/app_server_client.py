from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class AppServerError(RuntimeError):
    """Base failure raised by the isolated App Server probe."""


class AppServerProtocolError(AppServerError):
    """The App Server stream violated the expected JSONL protocol."""


class AppServerRequestError(AppServerError):
    """The App Server returned an error response for one request."""


class AppServerTurnError(AppServerError):
    """A Codex turn did not finish successfully."""


@dataclass(frozen=True)
class ThreadHandle:
    thread_id: str
    model: str | None
    reasoning_effort: str | None


@dataclass(frozen=True)
class TurnResult:
    thread_id: str
    turn_id: str
    status: str
    messages: tuple[str, ...]
    started_at: float
    completed_at: float
    turn: Mapping[str, Any]

    @property
    def final_message(self) -> str:
        if not self.messages:
            raise AppServerTurnError(
                f"turn {self.turn_id} completed without an agent message"
            )
        return self.messages[-1]


@dataclass
class _PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


@dataclass
class _TurnState:
    thread_id: str
    started_at: float | None = None
    completed_at: float | None = None
    status: str | None = None
    messages: list[str] = field(default_factory=list)
    turn: dict[str, Any] = field(default_factory=dict)


ProcessFactory = Callable[..., Any]


def resolve_codex_command() -> str:
    command = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which(
        "codex"
    )
    if command is None:
        raise AppServerError("codex command was not found on PATH")
    return command


def default_app_server_command() -> tuple[str, ...]:
    return (resolve_codex_command(), "app-server", "--listen", "stdio://")


class AppServerClient:
    """Thread-safe JSONL client for one version-pinned Codex App Server process."""

    def __init__(
        self,
        *,
        cwd: Path,
        command: Sequence[str] | None = None,
        process_factory: ProcessFactory = subprocess.Popen,
        request_timeout_seconds: float = 30.0,
        turn_timeout_seconds: float = 300.0,
    ) -> None:
        self.cwd = cwd.resolve()
        self.command = tuple(command or default_app_server_command())
        self._process_factory = process_factory
        self._request_timeout_seconds = request_timeout_seconds
        self._turn_timeout_seconds = turn_timeout_seconds
        self._process: Any | None = None
        self._request_ids = itertools.count(1)
        self._pending: dict[int, _PendingRequest] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._turn_condition = threading.Condition()
        self._turns: dict[str, _TurnState] = {}
        self._stream_error: BaseException | None = None
        self._closing = False
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=100)

    def __enter__(self) -> "AppServerClient":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()

    def start(self) -> None:
        if self._process is not None:
            raise AppServerError("App Server client is already started")
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = self._process_factory(
            list(self.command),
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            creationflags=creation_flags,
        )
        if (
            self._process.stdin is None
            or self._process.stdout is None
            or self._process.stderr is None
        ):
            self.close()
            raise AppServerError("App Server process pipes were not created")
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="codex-app-server-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop,
            name="codex-app-server-stderr",
            daemon=True,
        )
        self._reader_thread.start()
        self._stderr_thread.start()
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "aegis_collaboration_poc",
                    "title": "Aegis Collaboration PoC",
                    "version": "0.1.0",
                }
            },
        )
        self.notify("initialized", {})

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        self._closing = True
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except (subprocess.TimeoutExpired, TimeoutError):
                    process.kill()
                    process.wait(timeout=5)
        finally:
            self._fail_waiters(AppServerError("App Server client closed"))
            if self._reader_thread is not None:
                self._reader_thread.join(timeout=5)
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=5)
            self._process = None

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"method": method, "params": dict(params)})

    def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        self._require_running()
        request_id = next(self._request_ids)
        pending = _PendingRequest()
        with self._pending_lock:
            self._pending[request_id] = pending
        try:
            self._send(
                {"method": method, "id": request_id, "params": dict(params)}
            )
            timeout = (
                self._request_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            )
            if not pending.event.wait(timeout):
                raise AppServerRequestError(
                    f"App Server request timed out: method={method!r}, "
                    f"timeout_seconds={timeout}, stderr={self.stderr_tail!r}"
                )
            if pending.error is not None:
                raise pending.error
            return pending.result
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def start_thread(
        self,
        *,
        ephemeral: bool,
        model: str | None = None,
        developer_instructions: str | None = None,
    ) -> ThreadHandle:
        params: dict[str, Any] = {
            "cwd": str(self.cwd),
            "ephemeral": ephemeral,
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "developerInstructions": developer_instructions
            or (
                "This is an isolated orchestration probe. Do not call tools, do not "
                "modify files, and return only the requested response."
            ),
        }
        if model is not None:
            params["model"] = model
        result = self.request("thread/start", params)
        if not isinstance(result, dict):
            raise AppServerProtocolError("thread/start result must be an object")
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise AppServerProtocolError("thread/start did not return thread.id")
        return ThreadHandle(
            thread_id=thread["id"],
            model=_optional_string(result.get("model")),
            reasoning_effort=_optional_string(result.get("reasoningEffort")),
        )

    def resume_thread(self, thread_id: str) -> ThreadHandle:
        result = self.request(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": str(self.cwd),
                "sandbox": "read-only",
                "approvalPolicy": "never",
            },
        )
        if not isinstance(result, dict):
            raise AppServerProtocolError("thread/resume result must be an object")
        thread = result.get("thread")
        if not isinstance(thread, dict) or thread.get("id") != thread_id:
            raise AppServerProtocolError("thread/resume returned a different thread.id")
        return ThreadHandle(
            thread_id=thread_id,
            model=_optional_string(result.get("model")),
            reasoning_effort=_optional_string(result.get("reasoningEffort")),
        )

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        result = self.request(
            "thread/read", {"threadId": thread_id, "includeTurns": True}
        )
        if not isinstance(result, dict):
            raise AppServerProtocolError("thread/read result must be an object")
        return result

    def run_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        output_schema: Mapping[str, Any] | None = None,
        client_message_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> TurnResult:
        submitted_at = time.monotonic()
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if output_schema is not None:
            params["outputSchema"] = dict(output_schema)
        if client_message_id is not None:
            params["clientUserMessageId"] = client_message_id
        result = self.request("turn/start", params)
        if not isinstance(result, dict):
            raise AppServerProtocolError("turn/start result must be an object")
        turn = result.get("turn")
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
            raise AppServerProtocolError("turn/start did not return turn.id")
        turn_id = turn["id"]
        timeout = self._turn_timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = time.monotonic() + timeout
        with self._turn_condition:
            state = self._turns.setdefault(turn_id, _TurnState(thread_id=thread_id))
            if state.thread_id != thread_id:
                raise AppServerProtocolError(
                    f"turn {turn_id} was associated with two different threads"
                )
            if state.started_at is None:
                state.started_at = submitted_at
            while state.completed_at is None:
                if self._stream_error is not None:
                    raise self._stream_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._turn_condition.wait(remaining)
            if state.completed_at is None:
                self._interrupt_best_effort(thread_id, turn_id)
                raise AppServerTurnError(
                    f"turn timed out: thread_id={thread_id}, turn_id={turn_id}, "
                    f"timeout_seconds={timeout}"
                )
            snapshot = TurnResult(
                thread_id=thread_id,
                turn_id=turn_id,
                status=state.status or "unknown",
                messages=tuple(state.messages),
                started_at=state.started_at,
                completed_at=state.completed_at,
                turn=dict(state.turn),
            )
        if snapshot.status != "completed":
            error = snapshot.turn.get("error")
            raise AppServerTurnError(
                f"turn did not complete successfully: status={snapshot.status!r}, "
                f"thread_id={thread_id}, turn_id={turn_id}, error={error!r}"
            )
        if not snapshot.messages:
            raise AppServerTurnError(
                f"completed turn returned no agent message: turn_id={turn_id}"
            )
        return snapshot

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr_tail)

    def _require_running(self) -> None:
        if self._process is None or self._process.poll() is not None:
            raise AppServerError("App Server process is not running")
        if self._stream_error is not None:
            raise self._stream_error

    def _send(self, message: Mapping[str, Any]) -> None:
        self._require_running()
        assert self._process is not None and self._process.stdin is not None
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            with self._write_lock:
                self._process.stdin.write(line)
                self._process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            failure = AppServerError(f"cannot write to App Server: {error}")
            self._fail_waiters(failure)
            raise failure from error

    def _reader_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                line = self._process.stdout.readline()
                if line == "":
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as error:
                    raise AppServerProtocolError(
                        f"App Server emitted invalid JSON: {line!r}"
                    ) from error
                if not isinstance(message, dict):
                    raise AppServerProtocolError(
                        f"App Server message must be an object: {message!r}"
                    )
                self._handle_message(message)
        except BaseException as error:
            self._fail_waiters(error)
            return
        if not self._closing:
            self._fail_waiters(
                AppServerError(
                    f"App Server stdout closed unexpectedly; stderr={self.stderr_tail!r}"
                )
            )

    def _stderr_loop(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                line = self._process.stderr.readline()
                if line == "":
                    return
                self._stderr_tail.append(line.rstrip("\r\n"))
        except (OSError, ValueError):
            return

    def _handle_message(self, message: dict[str, Any]) -> None:
        if "method" in message:
            if "id" in message:
                self._reject_server_request(message)
            else:
                self._handle_notification(message)
            return
        if "id" not in message:
            raise AppServerProtocolError(f"unclassifiable App Server message: {message!r}")
        request_id = message["id"]
        if not isinstance(request_id, int):
            raise AppServerProtocolError(
                f"App Server response id must be an integer: {request_id!r}"
            )
        with self._pending_lock:
            pending = self._pending.get(request_id)
        if pending is None:
            return
        if "error" in message:
            pending.error = AppServerRequestError(
                f"App Server request failed: {message['error']!r}"
            )
        elif "result" in message:
            pending.result = message["result"]
        else:
            pending.error = AppServerProtocolError(
                f"App Server response has neither result nor error: {message!r}"
            )
        pending.event.set()

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        self._send(
            {
                "id": message["id"],
                "error": {
                    "code": -32601,
                    "message": (
                        "Aegis collaboration PoC does not accept App Server "
                        f"requests: {message.get('method')!r}"
                    ),
                },
            }
        )

    def _handle_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(params, dict):
            return
        if method == "turn/started":
            turn = params.get("turn")
            thread_id = params.get("threadId")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str) and isinstance(
                thread_id, str
            ):
                with self._turn_condition:
                    state = self._turns.setdefault(
                        turn["id"], _TurnState(thread_id=thread_id)
                    )
                    self._require_turn_thread(state, thread_id, turn["id"])
                    state.started_at = state.started_at or time.monotonic()
                    self._turn_condition.notify_all()
            return
        if method == "item/completed":
            turn_id = params.get("turnId")
            thread_id = params.get("threadId")
            item = params.get("item")
            if (
                isinstance(turn_id, str)
                and isinstance(thread_id, str)
                and isinstance(item, dict)
                and item.get("type") == "agentMessage"
                and isinstance(item.get("text"), str)
            ):
                with self._turn_condition:
                    state = self._turns.setdefault(
                        turn_id, _TurnState(thread_id=thread_id)
                    )
                    self._require_turn_thread(state, thread_id, turn_id)
                    state.messages.append(item["text"])
                    self._turn_condition.notify_all()
            return
        if method == "turn/completed":
            turn = params.get("turn")
            thread_id = params.get("threadId")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str) and isinstance(
                thread_id, str
            ):
                turn_id = turn["id"]
                with self._turn_condition:
                    state = self._turns.setdefault(
                        turn_id, _TurnState(thread_id=thread_id)
                    )
                    self._require_turn_thread(state, thread_id, turn_id)
                    state.started_at = state.started_at or time.monotonic()
                    state.completed_at = time.monotonic()
                    state.status = str(turn.get("status", "unknown"))
                    state.turn = dict(turn)
                    self._turn_condition.notify_all()

    def _require_turn_thread(
        self, state: _TurnState, thread_id: str, turn_id: str
    ) -> None:
        if state.thread_id != thread_id:
            raise AppServerProtocolError(
                f"turn {turn_id} changed thread identity from "
                f"{state.thread_id!r} to {thread_id!r}"
            )

    def _interrupt_best_effort(self, thread_id: str, turn_id: str) -> None:
        try:
            self.request(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout_seconds=min(5.0, self._request_timeout_seconds),
            )
        except AppServerError:
            return

    def _fail_waiters(self, error: BaseException) -> None:
        with self._pending_lock:
            pending_requests = tuple(self._pending.values())
        for pending in pending_requests:
            pending.error = error
            pending.event.set()
        with self._turn_condition:
            self._stream_error = error
            self._turn_condition.notify_all()


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
