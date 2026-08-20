from __future__ import annotations

import hashlib


class _Hash128:
    def __init__(self, data: bytes | bytearray | memoryview | str = b"") -> None:
        self._hash = hashlib.blake2b(digest_size=16)
        if data:
            self.update(data)

    def update(self, data: bytes | bytearray | memoryview | str) -> None:
        if isinstance(data, str):
            data = data.encode()
        self._hash.update(bytes(data))

    def digest(self) -> bytes:
        return self._hash.digest()

    def hexdigest(self) -> str:
        return self._hash.hexdigest()


def xxh3_128(data: bytes | bytearray | memoryview | str = b"") -> _Hash128:
    return _Hash128(data)


def xxh3_128_hexdigest(data: bytes | bytearray | memoryview | str = b"") -> str:
    return _Hash128(data).hexdigest()
