"""Windows Job Object containment for cancellable process trees."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
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


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _windows_error(function_name: str) -> OSError:
    code = ctypes.get_last_error()
    detail = ctypes.FormatError(code).strip() if code else "unknown Windows error"
    return OSError(code, f"{function_name} failed: {detail}")


def _kernel32():
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
    return kernel32


class WindowsKillOnCloseJob:
    """Own a Job Object whose associated process tree dies on handle close."""

    def __init__(self, kernel32, handle):
        self._kernel32 = kernel32
        self._handle = handle

    @classmethod
    def _attach_handle(cls, process_handle):
        if os.name != "nt":
            return None

        kernel32 = _kernel32()
        job_handle = kernel32.CreateJobObjectW(None, None)
        if not job_handle:
            raise _windows_error("CreateJobObjectW")

        try:
            limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(
                job_handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ):
                raise _windows_error("SetInformationJobObject")

            if not kernel32.AssignProcessToJobObject(job_handle, process_handle):
                raise _windows_error("AssignProcessToJobObject")
        except Exception:
            kernel32.CloseHandle(job_handle)
            raise

        return cls(kernel32, job_handle)

    @classmethod
    def attach(cls, process):
        """Assign an already-started Windows subprocess to a kill-on-close job."""
        if os.name != "nt":
            return None
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise RuntimeError("subprocess does not expose a Windows process handle")
        return cls._attach_handle(wintypes.HANDLE(int(process_handle)))

    @classmethod
    def attach_current_process(cls):
        """Contain the current worker before it is allowed to spawn descendants.

        The returned object should remain referenced for the entire worker
        lifetime. Managed workers intentionally do not explicitly close this
        handle: the operating system closes it when the worker process exits,
        and KILL_ON_JOB_CLOSE then terminates any descendants still alive.
        """
        if os.name != "nt":
            return None
        kernel32 = _kernel32()
        current_process = kernel32.GetCurrentProcess()
        if not current_process:
            raise _windows_error("GetCurrentProcess")
        return cls._attach_handle(current_process)

    def close(self) -> None:
        """Close the last owned job handle, terminating lingering descendants."""
        handle = self._handle
        if not handle:
            return
        self._handle = None
        if not self._kernel32.CloseHandle(handle):
            raise _windows_error("CloseHandle(job)")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.close()
