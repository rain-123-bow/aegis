from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


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


def _create_kill_on_close_job(
    *, active_process_limit: int, job_memory_limit_bytes: int, process_time_limit_100ns: int
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

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        _raise_last_windows_error("CreateJobObjectW")
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


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) < 8:
        print(
            "usage: windows_job_runner.py --active-process-limit N "
            "--job-memory-limit-bytes N --process-time-limit-100ns N -- COMMAND [ARG ...]",
            file=sys.stderr,
        )
        return 64
    try:
        separator = arguments.index("--")
        options = arguments[:separator]
        command = arguments[separator + 1 :]
        parsed = dict(zip(options[::2], options[1::2], strict=True))
        if set(parsed) != {
            "--active-process-limit",
            "--job-memory-limit-bytes",
            "--process-time-limit-100ns",
        } or not command:
            raise ValueError
        active_process_limit = int(parsed["--active-process-limit"])
        job_memory_limit_bytes = int(parsed["--job-memory-limit-bytes"])
        process_time_limit_100ns = int(parsed["--process-time-limit-100ns"])
        if (
            not 2 <= active_process_limit <= 256
            or not 64 * 1024 * 1024 <= job_memory_limit_bytes <= 64 * 1024**3
            or not 10_000_000 <= process_time_limit_100ns <= 7_200 * 10_000_000
        ):
            raise ValueError
    except (ValueError, TypeError):
        print("invalid Windows Job Object limits", file=sys.stderr)
        return 64
    if sys.platform != "win32":
        print("windows_job_runner.py requires Windows", file=sys.stderr)
        return 69

    # The handle intentionally remains open for this process lifetime. If the
    # runner is terminated, Windows closes it and kills every process in the job.
    _job_handle = _create_kill_on_close_job(
        active_process_limit=active_process_limit,
        job_memory_limit_bytes=job_memory_limit_bytes,
        process_time_limit_100ns=process_time_limit_100ns,
    )
    try:
        child = subprocess.Popen(command)
    except OSError as error:
        print(f"cannot start managed child: {error}", file=sys.stderr)
        return 70
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
