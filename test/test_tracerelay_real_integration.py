from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tracerelay_client import TraceRelayClient


class OneShotHttpServer:
    def __init__(self, *, respond: bool) -> None:
        self.respond = respond
        self.received = bytearray()
        self.accepted = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._listener.settimeout(10)
        self.port = int(self._listener.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> OneShotHttpServer:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._listener.close()
        self._thread.join(timeout=2)

    def _serve(self) -> None:
        try:
            connection, _address = self._listener.accept()
        except OSError:
            return
        self.accepted.set()
        with connection:
            connection.settimeout(5)
            while b"\r\n\r\n" not in self.received:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                self.received.extend(chunk)
            if self.respond:
                connection.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
                )


@unittest.skipUnless(
    os.environ.get("TRACERELAY_COMMAND"),
    "set TRACERELAY_COMMAND to run the installed TraceRelay integration",
)
class RealTraceRelayIntegrationTests(unittest.TestCase):
    def test_hostile_proxy_environment_cannot_bypass_registered_relay(self) -> None:
        command = str(Path(os.environ["TRACERELAY_COMMAND"]).resolve())
        client = TraceRelayClient(command=command, monitor_interval_seconds=0.05)
        owned = False
        try:
            started = client.start()
            if started.get("started") is not True:
                self.skipTest("TraceRelay was already running; test will not take ownership")
            owned = True
            with OneShotHttpServer(respond=True) as upstream, OneShotHttpServer(
                respond=False
            ) as direct_origin:
                target = f"http://127.0.0.1:{direct_origin.port}/probe"
                child = [
                    sys.executable,
                    "-I",
                    "-S",
                    "-c",
                    (
                        "import urllib.request; "
                        f"assert urllib.request.urlopen({target!r}, timeout=10).read() == b'OK'"
                    ),
                ]
                hostile_environment = dict(os.environ)
                hostile_environment.update(
                    NO_PROXY="*",
                    no_proxy="*",
                    ALL_PROXY="http://127.0.0.1:1",
                    all_proxy="http://127.0.0.1:2",
                )
                result = client.run_process(
                    child,
                    upstream_port=upstream.port,
                    timeout_seconds=30,
                    base_environment=hostile_environment,
                )

            self.assertEqual(result.completed.returncode, 0, result.completed.stderr)
            self.assertEqual(result.verification["status"], "VALID_COMPLETE")
            observed = result.verification["observed_bytes"]
            self.assertGreater(observed["client_to_upstream"], 0)
            self.assertGreater(observed["upstream_to_client"], 0)
            self.assertTrue(upstream.accepted.is_set())
            self.assertIn(target.encode("ascii"), bytes(upstream.received))
            self.assertFalse(direct_origin.accepted.is_set())
        finally:
            if owned:
                subprocess.run(
                    [command, "stop"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                    timeout=30,
                )


if __name__ == "__main__":
    unittest.main()
