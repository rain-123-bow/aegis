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
        self.root = Path(os.path.abspath(os.fspath(root)))
        self._events: list[FileSystemEvent] = []
        self._events_lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._handle: int | None = None
        self._guard_handles: list[int] = []
        self._locked_file_handles: list[int] = []
        self._fallback_file_descriptors: list[int] = []
        self._stop_event: int | None = None
        self._error: BaseException | None = None
        self._listening = False
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
            self._listening = True
            return
        self._thread = threading.Thread(
            target=self._watch_windows,
            name="aegis-frozen-input-watcher",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=10):
            try:
                self.stop()
            except FrozenInputWatcherError:
                pass
            raise FrozenInputWatcherError("frozen input watcher did not become ready")
        if self._error is not None:
            raise FrozenInputWatcherError(
                f"frozen input watcher failed to start: {self._error}"
            ) from self._error

    @property
    def listening(self) -> bool:
        """True only after the first change request is successfully armed."""

        return self._listening

    def stop(self) -> tuple[FileSystemEvent, ...]:
        try:
            return self.drain()
        finally:
            self.close()

    def drain(self) -> tuple[FileSystemEvent, ...]:
        """Stop and drain notifications while retaining path rename guards."""

        if sys.platform != "win32":
            before = self._fallback_snapshot
            self._fallback_snapshot = None
            self._listening = False
            if before is not None:
                after = self._snapshot()
                for path in sorted(set(before) | set(after)):
                    if before.get(path) != after.get(path):
                        self._events.append(
                            FileSystemEvent(
                                "boundary_changed",
                                Path(os.path.abspath(os.path.join(self.root, path))),
                            )
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

    def close(self) -> None:
        """Release directory and ancestor path locks after boundary validation."""

        if sys.platform != "win32":
            descriptors = self._fallback_file_descriptors
            self._fallback_file_descriptors = []
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            return
        drain_error: BaseException | None = None
        if self._thread is not None:
            try:
                self.drain()
            except BaseException as error:
                drain_error = error
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        file_handles = self._locked_file_handles
        self._locked_file_handles = []
        for file_handle in reversed(file_handles):
            kernel32.CloseHandle(file_handle)
        handle = self._handle
        self._handle = None
        if handle is not None:
            kernel32.CloseHandle(handle)
        guard_handles = self._guard_handles
        self._guard_handles = []
        for guard_handle in reversed(guard_handles):
            kernel32.CloseHandle(guard_handle)
        if drain_error is not None:
            raise drain_error

    def lock_files(self, paths: list[Path]) -> None:
        """Hold file-object locks that deny writes/deletes through any hardlink."""

        if not self.listening:
            raise FrozenInputWatcherError(
                "cannot lock frozen files before the directory listener is ready"
            )
        unique = {
            os.path.normcase(os.fspath(Path(os.path.abspath(os.fspath(path))))): Path(
                os.path.abspath(os.fspath(path))
            )
            for path in paths
        }
        if sys.platform != "win32":
            opened: list[int] = []
            try:
                for path in unique.values():
                    opened.append(
                        os.open(
                            path,
                            os.O_RDONLY
                            | getattr(os, "O_BINARY", 0)
                            | getattr(os, "O_NOFOLLOW", 0),
                        )
                    )
            except BaseException:
                for descriptor in reversed(opened):
                    os.close(descriptor)
                raise
            self._fallback_file_descriptors.extend(opened)
            return

        import ctypes
        from ctypes import wintypes

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
        kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetFileAttributesW.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.GetFinalPathNameByHandleW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
            _fields_ = [
                ("FileAttributes", wintypes.DWORD),
                ("ReparseTag", wintypes.DWORD),
            ]

        kernel32.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
        invalid_handle = ctypes.c_void_p(-1).value
        opened_handles: list[int] = []
        try:
            for path in unique.values():
                attributes = int(kernel32.GetFileAttributesW(str(path)))
                if attributes == 0xFFFFFFFF:
                    raise OSError(
                        ctypes.get_last_error(),
                        f"GetFileAttributesW failed for frozen file: {path}",
                    )
                if attributes & 0x00000400 or attributes & 0x00000010:
                    raise FrozenInputWatcherError(
                        f"frozen file lock rejects reparse/directory path: {path}"
                    )
                handle = kernel32.CreateFileW(
                    str(path),
                    0x80000000,
                    0x00000001,
                    None,
                    3,
                    0x00200000,
                    None,
                )
                if handle == invalid_handle:
                    raise OSError(
                        ctypes.get_last_error(),
                        f"CreateFileW(frozen file lock) failed: {path}",
                    )
                info = FILE_ATTRIBUTE_TAG_INFO()
                if not kernel32.GetFileInformationByHandleEx(
                    handle,
                    9,
                    ctypes.byref(info),
                    ctypes.sizeof(info),
                ):
                    kernel32.CloseHandle(handle)
                    raise OSError(
                        ctypes.get_last_error(),
                        f"GetFileInformationByHandleEx failed for frozen file: {path}",
                    )
                if (
                    int(info.FileAttributes) & 0x00000400
                    or int(info.FileAttributes) & 0x00000010
                ):
                    kernel32.CloseHandle(handle)
                    raise FrozenInputWatcherError(
                        f"frozen file lock opened a reparse/directory object: {path}"
                    )
                opened_handles.append(int(handle))
        except BaseException:
            for handle in reversed(opened_handles):
                kernel32.CloseHandle(handle)
            raise
        self._locked_file_handles.extend(opened_handles)

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
        kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetFileAttributesW.restype = wintypes.DWORD
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
        class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
            _fields_ = [
                ("FileAttributes", wintypes.DWORD),
                ("ReparseTag", wintypes.DWORD),
            ]

        kernel32.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel32.GetFinalPathNameByHandleW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        invalid_handle = ctypes.c_void_p(-1).value
        invalid_attributes = 0xFFFFFFFF

        def reject_reparse_directory(path: Path) -> None:
            attributes = int(kernel32.GetFileAttributesW(str(path)))
            if attributes == invalid_attributes:
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetFileAttributesW failed: {path}",
                )
            if attributes & 0x00000400:
                raise FrozenInputWatcherError(
                    f"frozen input rename guard rejects reparse directory: {path}"
                )

        def validate_directory_handle(handle: int, path: Path) -> None:
            info = FILE_ATTRIBUTE_TAG_INFO()
            if not kernel32.GetFileInformationByHandleEx(
                handle,
                9,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetFileInformationByHandleEx failed: {path}",
                )
            if (
                int(info.FileAttributes) & 0x00000400
                or not int(info.FileAttributes) & 0x00000010
            ):
                raise FrozenInputWatcherError(
                    f"frozen input guard opened an invalid/reparse directory: {path}"
                )
            final_buffer = ctypes.create_unicode_buffer(32768)
            final_size = int(
                kernel32.GetFinalPathNameByHandleW(
                    handle,
                    final_buffer,
                    len(final_buffer),
                    0,
                )
            )
            if final_size == 0 or final_size >= len(final_buffer):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetFinalPathNameByHandleW failed: {path}",
                )
            final_name = final_buffer.value
            if final_name.startswith("\\\\?\\UNC\\"):
                final_name = "\\\\" + final_name[8:]
            elif final_name.startswith("\\\\?\\"):
                final_name = final_name[4:]
            expected_name = os.path.normcase(os.path.abspath(os.fspath(path)))
            if os.path.normcase(os.path.abspath(final_name)) != expected_name:
                raise FrozenInputWatcherError(
                    f"frozen input guard opened a different directory: {path}"
                )

        guard_handles: list[int] = []
        ancestor = self.root.parent
        ancestors: list[Path] = []
        while ancestor.parent != ancestor:
            ancestors.append(ancestor)
            ancestor = ancestor.parent
        for protected_directory in reversed(ancestors):
            try:
                reject_reparse_directory(protected_directory)
            except BaseException as error:
                self._error = error
                for opened_handle in reversed(guard_handles):
                    kernel32.CloseHandle(opened_handle)
                self._ready.set()
                return
            guard_handle = kernel32.CreateFileW(
                str(protected_directory),
                0,
                0x00000001 | 0x00000002,
                None,
                3,
                0x02000000 | 0x00200000,
                None,
            )
            if guard_handle == invalid_handle:
                self._error = OSError(
                    ctypes.get_last_error(),
                    f"CreateFileW(rename guard) failed: {protected_directory}",
                )
                for opened_handle in reversed(guard_handles):
                    kernel32.CloseHandle(opened_handle)
                self._ready.set()
                return
            try:
                validate_directory_handle(int(guard_handle), protected_directory)
            except BaseException as error:
                kernel32.CloseHandle(guard_handle)
                self._error = error
                for opened_handle in reversed(guard_handles):
                    kernel32.CloseHandle(opened_handle)
                self._ready.set()
                return
            guard_handles.append(int(guard_handle))
        try:
            reject_reparse_directory(self.root)
        except BaseException as error:
            self._error = error
            for opened_handle in reversed(guard_handles):
                kernel32.CloseHandle(opened_handle)
            self._ready.set()
            return
        handle = kernel32.CreateFileW(
            str(self.root),
            0x0001,
            0x00000001 | 0x00000002,
            None,
            3,
            0x02000000 | 0x00200000 | 0x40000000,
            None,
        )
        if handle == invalid_handle:
            self._error = OSError(
                ctypes.get_last_error(), "CreateFileW(FILE_LIST_DIRECTORY) failed"
            )
            for opened_handle in reversed(guard_handles):
                kernel32.CloseHandle(opened_handle)
            self._ready.set()
            return
        try:
            validate_directory_handle(int(handle), self.root)
        except BaseException as error:
            kernel32.CloseHandle(handle)
            self._error = error
            for opened_handle in reversed(guard_handles):
                kernel32.CloseHandle(opened_handle)
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
            for opened_handle in reversed(guard_handles):
                kernel32.CloseHandle(opened_handle)
            self._ready.set()
            return
        self._handle = int(handle)
        self._guard_handles = list(guard_handles)
        self._stop_event = int(stop_event)
        buffer = ctypes.create_string_buffer(64 * 1024)
        bytes_returned = wintypes.DWORD()
        notify_filter = 0x00000001 | 0x00000002 | 0x00000008 | 0x00000010 | 0x00000040
        wait_handles = (wintypes.HANDLE * 2)(stop_event, change_event)

        def record_completed_buffer(limit: int) -> None:
            if limit == 0:
                with self._events_lock:
                    self._events.append(
                        FileSystemEvent("journal_overflow", self.root)
                    )
                return
            offset = 0
            while offset < limit:
                next_offset = int.from_bytes(buffer[offset : offset + 4], "little")
                action = int.from_bytes(buffer[offset + 4 : offset + 8], "little")
                name_length = int.from_bytes(
                    buffer[offset + 8 : offset + 12], "little"
                )
                name = bytes(
                    buffer[offset + 12 : offset + 12 + name_length]
                ).decode("utf-16-le", errors="strict")
                event_path = Path(
                    os.path.abspath(os.path.join(str(self.root), name))
                )
                if os.path.commonpath((str(self.root), str(event_path))).casefold() != str(
                    self.root
                ).casefold():
                    raise FrozenInputWatcherError(
                        "directory journal returned a path outside its lexical root"
                    )
                event = FileSystemEvent(
                    _ACTION_NAMES.get(action, f"action_{action}"),
                    event_path,
                )
                with self._events_lock:
                    self._events.append(event)
                if next_offset == 0:
                    break
                offset += next_offset

        try:
            first_request = True
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
                if first_request:
                    self._listening = True
                    self._ready.set()
                    first_request = False
                wait_result = kernel32.WaitForMultipleObjects(
                    2, wait_handles, False, 0xFFFFFFFF
                )
                if wait_result == 0:
                    kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
                    completed = kernel32.GetOverlappedResult(
                        handle,
                        ctypes.byref(overlapped),
                        ctypes.byref(bytes_returned),
                        True,
                    )
                    if completed:
                        record_completed_buffer(bytes_returned.value)
                    elif ctypes.get_last_error() != 995:
                        raise OSError(
                            ctypes.get_last_error(),
                            "GetOverlappedResult during watcher stop failed",
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
                record_completed_buffer(bytes_returned.value)
        except BaseException as error:
            self._error = error
            self._ready.set()
        finally:
            self._listening = False
            self._ready.set()
            self._stop_event = None
            kernel32.CloseHandle(change_event)
            kernel32.CloseHandle(stop_event)

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
