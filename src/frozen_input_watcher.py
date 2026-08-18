from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


class FrozenInputWatcherError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FileSystemEvent:
    action: str
    path: Path


_ACTION_NAMES = {
    1: "added",
    2: "removed",
    3: "modified",
    4: "renamed_from",
    5: "renamed_to",
}


class FrozenInputWatcher:
    """Windows recursive directory change journal for one node execution."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._events: list[FileSystemEvent] = []
        self._events_lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._handle: int | None = None
        self._stop_event: int | None = None
        self._error: BaseException | None = None
        self._fallback_snapshot: dict[str, tuple[int, int]] | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise FrozenInputWatcherError("frozen input watcher already started")
        if not self.root.is_dir():
            raise FrozenInputWatcherError(
                f"frozen input watch root is missing: {self.root}"
            )
        if sys.platform != "win32":
            self._fallback_snapshot = self._snapshot()
            return
        self._thread = threading.Thread(
            target=self._watch_windows,
            name="aegis-frozen-input-watcher",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise FrozenInputWatcherError("frozen input watcher did not become ready")
        if self._error is not None:
            raise FrozenInputWatcherError(
                f"frozen input watcher failed to start: {self._error}"
            ) from self._error

    def stop(self) -> tuple[FileSystemEvent, ...]:
        if sys.platform != "win32":
            before = self._fallback_snapshot
            self._fallback_snapshot = None
            if before is not None:
                after = self._snapshot()
                for path in sorted(set(before) | set(after)):
                    if before.get(path) != after.get(path):
                        self._events.append(
                            FileSystemEvent("boundary_changed", self.root / path)
                        )
            return tuple(self._events)
        thread = self._thread
        self._thread = None
        stop_event = self._stop_event
        if stop_event is not None:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.SetEvent.argtypes = [ctypes.c_void_p]
            kernel32.SetEvent.restype = ctypes.c_int
            kernel32.SetEvent(stop_event)
        if thread is not None:
            thread.join(timeout=10)
            if thread.is_alive():
                raise FrozenInputWatcherError("frozen input watcher did not stop")
        if self._error is not None:
            raise FrozenInputWatcherError(
                f"frozen input watcher failed: {self._error}"
            ) from self._error
        with self._events_lock:
            return tuple(self._events)

    def events(self) -> tuple[FileSystemEvent, ...]:
        with self._events_lock:
            return tuple(self._events)

    def _watch_windows(self) -> None:
        import ctypes
        from ctypes import wintypes

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_size_t),
                ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.ReadDirectoryChangesW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        kernel32.ReadDirectoryChangesW.restype = wintypes.BOOL
        kernel32.GetOverlappedResult.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(OVERLAPPED),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL,
        ]
        kernel32.GetOverlappedResult.restype = wintypes.BOOL
        kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        kernel32.CancelIoEx.restype = wintypes.BOOL
        kernel32.CreateEventW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
        kernel32.ResetEvent.restype = wintypes.BOOL
        kernel32.WaitForMultipleObjects.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.WaitForMultipleObjects.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        invalid_handle = ctypes.c_void_p(-1).value
        handle = kernel32.CreateFileW(
            str(self.root),
            0x0001,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            3,
            0x02000000 | 0x40000000,
            None,
        )
        if handle == invalid_handle:
            self._error = OSError(
                ctypes.get_last_error(), "CreateFileW(FILE_LIST_DIRECTORY) failed"
            )
            self._ready.set()
            return
        change_event = kernel32.CreateEventW(None, True, False, None)
        stop_event = kernel32.CreateEventW(None, True, False, None)
        if not change_event or not stop_event:
            self._error = OSError(
                ctypes.get_last_error(), "CreateEventW failed"
            )
            if change_event:
                kernel32.CloseHandle(change_event)
            if stop_event:
                kernel32.CloseHandle(stop_event)
            kernel32.CloseHandle(handle)
            self._ready.set()
            return
        self._handle = int(handle)
        self._stop_event = int(stop_event)
        self._ready.set()
        buffer = ctypes.create_string_buffer(64 * 1024)
        bytes_returned = wintypes.DWORD()
        notify_filter = 0x00000001 | 0x00000002 | 0x00000008 | 0x00000010 | 0x00000040
        wait_handles = (wintypes.HANDLE * 2)(stop_event, change_event)
        try:
            while True:
                overlapped = OVERLAPPED()
                overlapped.hEvent = change_event
                kernel32.ResetEvent(change_event)
                bytes_returned.value = 0
                success = kernel32.ReadDirectoryChangesW(
                    handle,
                    buffer,
                    len(buffer),
                    True,
                    notify_filter,
                    ctypes.byref(bytes_returned),
                    ctypes.byref(overlapped),
                    None,
                )
                if not success and ctypes.get_last_error() != 997:
                    error_code = ctypes.get_last_error()
                    raise OSError(error_code, "ReadDirectoryChangesW failed")
                wait_result = kernel32.WaitForMultipleObjects(
                    2, wait_handles, False, 0xFFFFFFFF
                )
                if wait_result == 0:
                    kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
                    kernel32.GetOverlappedResult(
                        handle,
                        ctypes.byref(overlapped),
                        ctypes.byref(bytes_returned),
                        True,
                    )
                    break
                if wait_result != 1:
                    raise OSError(
                        ctypes.get_last_error(),
                        f"WaitForMultipleObjects returned {wait_result}",
                    )
                if not kernel32.GetOverlappedResult(
                    handle,
                    ctypes.byref(overlapped),
                    ctypes.byref(bytes_returned),
                    False,
                ):
                    error_code = ctypes.get_last_error()
                    if error_code == 995:
                        break
                    raise OSError(error_code, "GetOverlappedResult failed")
                offset = 0
                limit = bytes_returned.value
                while offset < limit:
                    next_offset = int.from_bytes(buffer[offset : offset + 4], "little")
                    action = int.from_bytes(buffer[offset + 4 : offset + 8], "little")
                    name_length = int.from_bytes(
                        buffer[offset + 8 : offset + 12], "little"
                    )
                    name = bytes(
                        buffer[offset + 12 : offset + 12 + name_length]
                    ).decode("utf-16-le", errors="strict")
                    event = FileSystemEvent(
                        _ACTION_NAMES.get(action, f"action_{action}"),
                        (self.root / name).resolve(),
                    )
                    with self._events_lock:
                        self._events.append(event)
                    if next_offset == 0:
                        break
                    offset += next_offset
        except BaseException as error:
            self._error = error
        finally:
            self._handle = None
            self._stop_event = None
            kernel32.CloseHandle(change_event)
            kernel32.CloseHandle(stop_event)
            kernel32.CloseHandle(handle)

    def _snapshot(self) -> dict[str, tuple[int, int]]:
        snapshot: dict[str, tuple[int, int]] = {}
        for path in self.root.rglob("*"):
            try:
                if path.is_file():
                    status = path.stat()
                    snapshot[path.relative_to(self.root).as_posix()] = (
                        int(status.st_size),
                        int(status.st_mtime_ns),
                    )
            except OSError:
                continue
        return snapshot
