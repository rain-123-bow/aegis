"""Length-bounded loopback JSON control protocol for TraceRelay v1."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from typing import Any

from .config import CONTROL_HOST, CONTROL_MESSAGE_LIMIT, CONTROL_PORT


class ControlProtocolError(ValueError):
    pass


class ControlClient:
    def __init__(
        self,
        host: str = CONTROL_HOST,
        port: int = CONTROL_PORT,
        timeout: float = 10.0,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            raise ValueError("control timeout must be a positive number")
        self.host = host
        self.port = port
        self.timeout = float(timeout)

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = _encode_message(request)
        with socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        ) as connection:
            connection.settimeout(self.timeout)
            connection.sendall(payload)
            response = _read_message(connection)
        return response


class ControlServer:
    def __init__(
        self,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        host: str = CONTROL_HOST,
        port: int = CONTROL_PORT,
        after_response: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
    ) -> None:
        if host != CONTROL_HOST:
            raise ValueError(f"control host must be {CONTROL_HOST}")
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 <= port <= 65_535
        ):
            raise ValueError("control port must be an integer between 0 and 65535")
        self._handler = handler
        self._after_response = after_response
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self._listener.setsockopt(
                    socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                )
            self._listener.bind((host, port))
            self._listener.listen(8)
            self._listener.settimeout(0.25)
        except BaseException:
            self._listener.close()
            raise
        address = self._listener.getsockname()
        self.host = str(address[0])
        self.port = int(address[1])

    def serve_forever(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _address = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                raise
            with connection:
                connection.settimeout(10.0)
                request: dict[str, Any] | None = None
                try:
                    request = _read_message(connection)
                    response = self._handler(request)
                except (ControlProtocolError, TimeoutError, OSError) as error:
                    response = {
                        "ok": False,
                        "command": None,
                        "state": "UNKNOWN",
                        "error": str(error),
                    }
                try:
                    connection.sendall(_encode_message(response))
                except OSError:
                    pass
                if self._after_response is not None and request is not None:
                    self._after_response(request, response)

    def close(self) -> None:
        self._stop.set()
        try:
            self._listener.close()
        except OSError:
            pass


def _encode_message(value: dict[str, Any]) -> bytes:
    if not isinstance(value, dict):
        raise ControlProtocolError("control message must be a JSON object")
    try:
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ControlProtocolError(
            f"control message is not JSON serializable: {error}"
        ) from error
    if len(payload) > CONTROL_MESSAGE_LIMIT:
        raise ControlProtocolError("control message exceeds 64 KiB")
    return payload


def _read_message(connection: socket.socket) -> dict[str, Any]:
    buffer = bytearray()
    while b"\n" not in buffer:
        remaining = CONTROL_MESSAGE_LIMIT + 1 - len(buffer)
        if remaining <= 0:
            raise ControlProtocolError("control message exceeds 64 KiB")
        chunk = connection.recv(min(4096, remaining))
        if not chunk:
            raise ControlProtocolError("control connection closed before newline")
        buffer.extend(chunk)
        if len(buffer) > CONTROL_MESSAGE_LIMIT:
            raise ControlProtocolError("control message exceeds 64 KiB")
    line, _separator, trailing = bytes(buffer).partition(b"\n")
    if trailing.strip():
        raise ControlProtocolError("only one control request is allowed per connection")
    if not line:
        raise ControlProtocolError("control message is empty")
    try:
        value = json.loads(
            line.decode("utf-8", errors="strict"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ControlProtocolError(f"invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise ControlProtocolError("control message must be a JSON object")
    return value


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")
