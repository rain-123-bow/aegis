from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import threading
from ctypes import wintypes


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
JOB_OBJECT_BASIC_PROCESS_ID_LIST_CLASS = 3
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_SET_ATTRIBUTES = 0x0002
PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF
ERROR_ALREADY_EXISTS = 183


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _raise_last_windows_error(operation: str) -> None:
    error = ctypes.get_last_error()
    raise OSError(error, f"{operation} failed", None, error)


def _query_job_member_pids(job: int) -> tuple[int, ...]:
    """Return one authoritative Job membership snapshot."""

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    capacity = 256
    header_size = 8
    buffer = ctypes.create_string_buffer(
        header_size + capacity * ctypes.sizeof(ctypes.c_size_t)
    )
    returned = wintypes.DWORD()
    if not kernel32.QueryInformationJobObject(
        job,
        JOB_OBJECT_BASIC_PROCESS_ID_LIST_CLASS,
        buffer,
        len(buffer),
        ctypes.byref(returned),
    ):
        _raise_last_windows_error("QueryInformationJobObject(process IDs)")
    assigned = int.from_bytes(buffer.raw[0:4], "little")
    included = int.from_bytes(buffer.raw[4:8], "little")
    if assigned != included or included > capacity:
        raise RuntimeError("Windows Job membership snapshot was incomplete")
    array_type = ctypes.c_size_t * included
    values = array_type.from_buffer_copy(buffer.raw, header_size)
    members = tuple(sorted(int(value) for value in values))
    if not members or len(set(members)) != len(members):
        raise RuntimeError("Windows Job membership snapshot was invalid")
    return members


def _freeze_named_job_members(job_name: str, *, runner_pid: int) -> tuple[int, ...]:
    """Block new children, suspend managed members, then snapshot membership.

    The runner remains runnable so its parent-death thread can close the Job.
    Every other stable member is suspended. With the active-process limit fixed
    at the current member count, no member can create a successor before crash.
    """

    if re.fullmatch(r"Local\\Aegis-[0-9a-f]{32}", job_name) is None:
        raise ValueError("invalid Windows Job Object name")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    kernel32.OpenJobObjectW.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.OpenJobObjectW.restype = wintypes.HANDLE
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtSuspendProcess.restype = wintypes.LONG
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = wintypes.LONG

    job = kernel32.OpenJobObjectW(
        JOB_OBJECT_QUERY | JOB_OBJECT_SET_ATTRIBUTES, False, job_name
    )
    if not job:
        _raise_last_windows_error("OpenJobObjectW")
    suspended: dict[int, int] = {}
    complete = False
    try:
        members = _query_job_member_pids(int(job))
        if runner_pid not in members or len(members) < 2:
            raise RuntimeError("Windows Job has no runner/managed-process membership")
        information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        returned = wintypes.DWORD()
        if not kernel32.QueryInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ctypes.byref(returned),
        ):
            _raise_last_windows_error("QueryInformationJobObject(limits)")
        information.BasicLimitInformation.LimitFlags |= (
            JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        information.BasicLimitInformation.ActiveProcessLimit = len(members)
        if not kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            _raise_last_windows_error("SetInformationJobObject(freeze creation)")

        for _attempt in range(16):
            members = _query_job_member_pids(int(job))
            for pid in members:
                if pid == runner_pid or pid in suspended:
                    continue
                process = kernel32.OpenProcess(
                    PROCESS_SUSPEND_RESUME
                    | PROCESS_QUERY_LIMITED_INFORMATION
                    | SYNCHRONIZE,
                    False,
                    pid,
                )
                if not process:
                    _raise_last_windows_error(f"OpenProcess(Job member {pid})")
                status = int(ntdll.NtSuspendProcess(process))
                if status < 0:
                    kernel32.CloseHandle(process)
                    raise OSError(status, f"NtSuspendProcess failed for PID {pid}")
                suspended[pid] = int(process)
            stable = _query_job_member_pids(int(job))
            if stable != members:
                continue
            if set(stable) != {runner_pid, *suspended}:
                continue
            if any(
                kernel32.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT
                for handle in suspended.values()
            ):
                continue
            complete = True
            return stable
        raise RuntimeError("Windows Job membership did not stabilize while frozen")
    finally:
        if not complete:
            for handle in suspended.values():
                ntdll.NtResumeProcess(handle)
        for handle in suspended.values():
            kernel32.CloseHandle(handle)
        kernel32.CloseHandle(job)


def _create_kill_on_close_job(
    *,
    job_name: str,
    active_process_limit: int,
    job_memory_limit_bytes: int,
    process_time_limit_100ns: int,
) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    ctypes.set_last_error(0)
    job = kernel32.CreateJobObjectW(None, job_name)
    if not job:
        _raise_last_windows_error("CreateJobObjectW")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(job)
        raise RuntimeError("Windows Job Object name already exists")
    information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    information.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_JOB_MEMORY
        | JOB_OBJECT_LIMIT_PROCESS_TIME
    )
    information.BasicLimitInformation.ActiveProcessLimit = active_process_limit
    information.BasicLimitInformation.PerProcessUserTimeLimit = process_time_limit_100ns
    information.JobMemoryLimit = job_memory_limit_bytes
    if not kernel32.SetInformationJobObject(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        _raise_last_windows_error("SetInformationJobObject")
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        _raise_last_windows_error("AssignProcessToJobObject")
    return int(job)


def _open_verified_parent_process(
    *, parent_pid: int, parent_creation_time_100ns: int
) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    parent = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
        False,
        parent_pid,
    )
    if not parent:
        _raise_last_windows_error("OpenProcess(parent)")
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            parent,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            _raise_last_windows_error("GetProcessTimes(parent)")
        actual_creation_time = (int(creation.dwHighDateTime) << 32) | int(
            creation.dwLowDateTime
        )
        if actual_creation_time != parent_creation_time_100ns:
            raise RuntimeError("parent process creation time does not match")
        if kernel32.WaitForSingleObject(parent, 0) != WAIT_TIMEOUT:
            raise RuntimeError("parent process exited before managed child launch")
        return int(parent)
    except BaseException:
        kernel32.CloseHandle(parent)
        raise


def _exit_when_parent_exits(parent_process: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    result = kernel32.WaitForSingleObject(parent_process, INFINITE)
    os._exit(71 if result == WAIT_OBJECT_0 else 72)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) < 12:
        print(
            "usage: windows_job_runner.py --job-name NAME --active-process-limit N "
            "--job-memory-limit-bytes N --process-time-limit-100ns N "
            "--parent-pid N --parent-creation-time-100ns N -- COMMAND [ARG ...]",
            file=sys.stderr,
        )
        return 64
    try:
        separator = arguments.index("--")
        options = arguments[:separator]
        command = arguments[separator + 1 :]
        parsed = dict(zip(options[::2], options[1::2], strict=True))
        if set(parsed) != {
            "--job-name",
            "--active-process-limit",
            "--job-memory-limit-bytes",
            "--process-time-limit-100ns",
            "--parent-pid",
            "--parent-creation-time-100ns",
        } or not command:
            raise ValueError
        active_process_limit = int(parsed["--active-process-limit"])
        job_name = parsed["--job-name"]
        job_memory_limit_bytes = int(parsed["--job-memory-limit-bytes"])
        process_time_limit_100ns = int(parsed["--process-time-limit-100ns"])
        parent_pid = int(parsed["--parent-pid"])
        parent_creation_time_100ns = int(parsed["--parent-creation-time-100ns"])
        if (
            not 2 <= active_process_limit <= 256
            or not isinstance(job_name, str)
            or re.fullmatch(r"Local\\Aegis-[0-9a-f]{32}", job_name) is None
            or not 64 * 1024 * 1024 <= job_memory_limit_bytes <= 64 * 1024**3
            or not 10_000_000 <= process_time_limit_100ns <= 7_200 * 10_000_000
            or parent_pid <= 0
            or parent_creation_time_100ns <= 0
        ):
            raise ValueError
    except (ValueError, TypeError):
        print("invalid Windows Job Object limits", file=sys.stderr)
        return 64
    if sys.platform != "win32":
        print("windows_job_runner.py requires Windows", file=sys.stderr)
        return 69

    parent_process = _open_verified_parent_process(
        parent_pid=parent_pid,
        parent_creation_time_100ns=parent_creation_time_100ns,
    )
    # Both handles intentionally remain open for this process lifetime. If the
    # runner is terminated, Windows closes it and kills every process in the job.
    _job_handle = _create_kill_on_close_job(
        job_name=job_name,
        active_process_limit=active_process_limit,
        job_memory_limit_bytes=job_memory_limit_bytes,
        process_time_limit_100ns=process_time_limit_100ns,
    )
    parent_watch = threading.Thread(
        target=_exit_when_parent_exits,
        args=(parent_process,),
        name="aegis-parent-death-watch",
        daemon=True,
    )
    parent_watch.start()
    try:
        child = subprocess.Popen(command)
    except OSError as error:
        print(f"cannot start managed child: {error}", file=sys.stderr)
        return 70
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
