from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class AppServerError(RuntimeError):
    pass


class AppServerProtocolError(AppServerError):
    pass


class AppServerRequestError(AppServerError):
    pass


class AppServerTurnError(AppServerError):
    pass


@dataclass(frozen=True, slots=True)
class ThreadHandle:
    thread_id: str
    model: str | None
    reasoning_effort: str | None


@dataclass(frozen=True, slots=True)
class TurnHandle:
    thread_id: str
    turn_id: str
    started_at: float


@dataclass(frozen=True, slots=True)
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


def read_codex_cli_version(command: str) -> str:
    try:
        completed = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise AppServerError(f"cannot read Codex CLI version: {error}") from error
    version = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 or not version:
        raise AppServerError(
            f"cannot read Codex CLI version: exit_code={completed.returncode}"
        )
    return version


class AppServerClient:
    """Thread-safe JSONL client for one Codex App Server process."""

    def __init__(
        self,
        *,
        cwd: Path,
        command: Sequence[str] | None = None,
        process_factory: ProcessFactory = subprocess.Popen,
        request_timeout_seconds: float = 30.0,
        turn_timeout_seconds: float = 1_800.0,
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
        self._active_threads: set[str] = set()
        self._active_threads_lock = threading.Lock()
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
        self._closing = False
        self._stream_error = None
        self._process = self._process_factory(
            list(self.command),
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
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
        try:
            self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "aegis_runtime",
                        "title": "Aegis Runtime",
                        "version": "0.1.0",
                    }
                },
            )
            self.notify("initialized", {})
        except BaseException:
            self.close()
            raise

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
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
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
            self._send({"method": method, "id": request_id, "params": dict(params)})
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
        sandbox: str = "read-only",
        approval_policy: str = "never",
        developer_instructions: str | None = None,
    ) -> ThreadHandle:
        params: dict[str, Any] = {
            "cwd": str(self.cwd),
            "ephemeral": ephemeral,
            "sandbox": sandbox,
            "approvalPolicy": approval_policy,
        }
        if developer_instructions is not None:
            params["developerInstructions"] = developer_instructions
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

    def resume_thread(
        self,
        thread_id: str,
        *,
        sandbox: str = "read-only",
        approval_policy: str = "never",
    ) -> ThreadHandle:
        result = self.request(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": str(self.cwd),
                "sandbox": sandbox,
                "approvalPolicy": approval_policy,
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

    def start_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        output_schema: Mapping[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> TurnHandle:
        with self._active_threads_lock:
            if thread_id in self._active_threads:
                raise AppServerTurnError(
                    f"thread {thread_id} already has an active turn"
                )
            self._active_threads.add(thread_id)
        submitted_at = time.monotonic()
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if output_schema is not None:
            params["outputSchema"] = dict(output_schema)
        if client_message_id is not None:
            params["clientUserMessageId"] = client_message_id
        try:
            result = self.request("turn/start", params)
            if not isinstance(result, dict):
                raise AppServerProtocolError("turn/start result must be an object")
            turn = result.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                raise AppServerProtocolError("turn/start did not return turn.id")
            turn_id = turn["id"]
            with self._turn_condition:
                state = self._turns.setdefault(
                    turn_id, _TurnState(thread_id=thread_id)
                )
                self._require_turn_thread(state, thread_id, turn_id)
                state.started_at = state.started_at or submitted_at
            return TurnHandle(thread_id, turn_id, state.started_at)
        except BaseException:
            with self._active_threads_lock:
                self._active_threads.discard(thread_id)
            raise

    def wait_turn(
        self,
        turn_handle: TurnHandle,
        *,
        timeout_seconds: float | None = None,
    ) -> TurnResult:
        timeout = self._turn_timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = time.monotonic() + timeout
        terminal = False
        with self._turn_condition:
            state = self._turns.setdefault(
                turn_handle.turn_id,
                _TurnState(
                    thread_id=turn_handle.thread_id,
                    started_at=turn_handle.started_at,
                ),
            )
            self._require_turn_thread(
                state, turn_handle.thread_id, turn_handle.turn_id
            )
            while state.completed_at is None:
                if self._stream_error is not None:
                    raise self._stream_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._interrupt_best_effort(
                        turn_handle.thread_id, turn_handle.turn_id
                    )
                    raise AppServerTurnError(
                        f"turn timed out: thread_id={turn_handle.thread_id}, "
                        f"turn_id={turn_handle.turn_id}, timeout_seconds={timeout}"
                    )
                self._turn_condition.wait(remaining)
            terminal = True
            snapshot = TurnResult(
                thread_id=turn_handle.thread_id,
                turn_id=turn_handle.turn_id,
                status=state.status or "unknown",
                messages=tuple(state.messages),
                started_at=state.started_at or turn_handle.started_at,
                completed_at=state.completed_at,
                turn=dict(state.turn),
            )
        if terminal:
            with self._active_threads_lock:
                self._active_threads.discard(turn_handle.thread_id)
        self._validate_result(snapshot)
        return snapshot

    def run_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        output_schema: Mapping[str, Any] | None = None,
        client_message_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> TurnResult:
        handle = self.start_turn(
            thread_id,
            prompt,
            output_schema=output_schema,
            client_message_id=client_message_id,
        )
        return self.wait_turn(handle, timeout_seconds=timeout_seconds)

    def recover_turn(self, thread_id: str, turn_id: str) -> TurnResult:
        result = self.read_thread(thread_id)
        thread = result.get("thread")
        if not isinstance(thread, dict) or thread.get("id") != thread_id:
            raise AppServerProtocolError("thread/read returned a different thread.id")
        turns = thread.get("turns")
        if not isinstance(turns, list):
            raise AppServerProtocolError("thread/read did not return thread.turns")
        for turn in turns:
            if not isinstance(turn, dict) or turn.get("id") != turn_id:
                continue
            status = turn.get("status")
            items = turn.get("items")
            messages = tuple(
                item["text"]
                for item in items
                if isinstance(item, dict)
                and item.get("type") == "agentMessage"
                and isinstance(item.get("text"), str)
            ) if isinstance(items, list) else ()
            recovered = TurnResult(
                thread_id=thread_id,
                turn_id=turn_id,
                status=str(status or "unknown"),
                messages=messages,
                started_at=0.0,
                completed_at=0.0,
                turn=dict(turn),
            )
            self._validate_result(recovered)
            return recovered
        raise AppServerTurnError(
            f"thread/read did not contain turn: thread_id={thread_id}, turn_id={turn_id}"
        )

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr_tail)

    def _validate_result(self, result: TurnResult) -> None:
        if result.status != "completed":
            raise AppServerTurnError(
                f"turn did not complete successfully: status={result.status!r}, "
                f"thread_id={result.thread_id}, turn_id={result.turn_id}, "
                f"error={result.turn.get('error')!r}"
            )
        if not result.messages:
            raise AppServerTurnError(
                f"completed turn returned no agent message: turn_id={result.turn_id}"
            )

    def _require_running(self) -> None:
        if self._process is None or self._process.poll() is not None:
            failure = self._managed_process_failure()
            if failure is not None:
                raise failure
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
        except (BrokenPipeError, OSError, UnicodeError) as error:
            failure = self._managed_process_failure() or AppServerError(
                f"cannot write to App Server: {error}"
            )
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
                self._managed_process_failure()
                or AppServerError(
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
        except (OSError, UnicodeError, ValueError):
            return

    def _handle_message(self, message: dict[str, Any]) -> None:
        if "method" in message:
            if "id" in message:
                self._reject_server_request(message)
            else:
                self._handle_notification(message)
            return
        if "id" not in message:
            raise AppServerProtocolError(
                f"unclassifiable App Server message: {message!r}"
            )
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
                    "message": f"Aegis runtime does not accept App Server requests: {message.get('method')!r}",
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
            if (
                isinstance(turn, dict)
                and isinstance(turn.get("id"), str)
                and isinstance(thread_id, str)
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
            if (
                isinstance(turn, dict)
                and isinstance(turn.get("id"), str)
                and isinstance(thread_id, str)
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

    def _managed_process_failure(self) -> BaseException | None:
        process = self._process
        failure_reader = getattr(process, "failure", None)
        if not callable(failure_reader):
            return None
        failure = failure_reader()
        return failure if isinstance(failure, BaseException) else None

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
