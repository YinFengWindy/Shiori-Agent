"""An OS lease spans plugin generations and independent Shiori processes."""

import ctypes
from ctypes import wintypes


class DesktopLease:
    """Exclusively owns the interactive Windows session until driver teardown."""

    def __init__(self) -> None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateSemaphoreW.argtypes = [
            ctypes.c_void_p,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.LPCWSTR,
        ]
        kernel.CreateSemaphoreW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseSemaphore.argtypes = [
            wintypes.HANDLE,
            wintypes.LONG,
            ctypes.c_void_p,
        ]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateSemaphoreW(
            None, 1, 1, "Local\\Shiori.ComputerUse.Desktop"
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        status = kernel.WaitForSingleObject(handle, 0)
        if status != 0:
            kernel.CloseHandle(handle)
            if status == 258:
                raise RuntimeError(
                    "Computer Use 桌面正由其他任务或运行代占用，请稍后重试"
                )
            raise ctypes.WinError(ctypes.get_last_error())
        self._kernel, self._handle = kernel, handle

    def close(self) -> None:
        """Releases only this plugin's lease; never touches a target application."""
        if self._handle is not None:
            if not self._kernel.ReleaseSemaphore(self._handle, 1, None):
                raise ctypes.WinError(ctypes.get_last_error())
            self._kernel.CloseHandle(self._handle)
            self._handle = None
