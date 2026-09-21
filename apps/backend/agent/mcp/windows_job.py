"""Windows job ownership for MCP servers that spawn detached input-capable workers."""

import ctypes
from ctypes import wintypes
import sys
import time
from typing import Any


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class WindowsJob:
    """Kills only an assigned process and descendants when closed or the host exits."""

    def __init__(self, pid: int, *, resume: bool = False) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Owned native MCP processes require Windows")
        kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel = kernel
        self._handle = kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        process = None
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(
                self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            process = kernel.OpenProcess(0x0100 | 0x0001, False, pid)
            if not process or not kernel.AssignProcessToJobObject(
                self._handle, process
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if resume:
                self._resume(pid)
        except BaseException:
            self.close()
            raise
        finally:
            if process:
                kernel.CloseHandle(process)

    def close(self) -> None:
        """Waits for owned descendants to exit before a profile lease can be released."""
        if not self._handle:
            return
        kernel = self._kernel
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        try:
            if not kernel.TerminateJobObject(self._handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
            # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGERs,
            # followed by page faults, total processes, active processes, terminated.
            counters = (wintypes.DWORD * 12)()
            deadline = time.monotonic() + 5
            while True:
                if not kernel.QueryInformationJobObject(
                    self._handle,
                    1,
                    ctypes.byref(counters),
                    ctypes.sizeof(counters),
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if counters[10] == 0:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Owned MCP process tree did not exit")
                time.sleep(0.01)
        finally:
            kernel.CloseHandle(self._handle)
            self._handle = None

    def _resume(self, pid: int) -> None:
        """Resumes the initial thread only after the suspended child belongs to this job."""

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("usage", wintypes.DWORD),
                ("tid", wintypes.DWORD),
                ("pid", wintypes.DWORD),
                ("priority", wintypes.LONG),
                ("delta", wintypes.LONG),
                ("flags", wintypes.DWORD),
            ]

        kernel = self._kernel
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = kernel.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.pid == pid:
                    thread = kernel.OpenThread(2, False, entry.tid)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        kernel.CloseHandle(thread)
                found = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise RuntimeError(
                f"MCP initial thread missing for suspended process {pid}"
            )
        finally:
            kernel.CloseHandle(snapshot)
