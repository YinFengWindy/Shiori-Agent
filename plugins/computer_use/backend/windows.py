"""Read-only Win32 target validation in physical screenshot coordinates."""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

import psutil


class TargetError(ValueError):
    """An observation must be refreshed; no input has been started."""


@dataclass(frozen=True)
class WindowIdentity:
    """A process incarnation, HWND, physical bounds and DPI captured together."""

    pid: int
    window_id: int
    created: float
    bounds: tuple[int, int, int, int]
    dpi: int


def inspect_window(pid: int, window_id: int) -> WindowIdentity:
    """Rejects stale/minimized/off-primary targets before the Driver sees input."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    dwm.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dwm.DwmGetWindowAttribute.restype = ctypes.c_long
    user.GetDpiForWindow.argtypes = [wintypes.HWND]
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    actual_pid = wintypes.DWORD()
    if not user.IsWindow(window_id):
        raise TargetError("窗口引用已失效，请重新发现窗口")
    user.GetWindowThreadProcessId(window_id, ctypes.byref(actual_pid))
    if actual_pid.value != pid:
        raise TargetError("窗口与进程身份不匹配，拒绝重新定位")
    if user.IsIconic(window_id):
        raise TargetError("Computer Use 不支持最小化窗口，请先恢复窗口")
    previous = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        rect = wintypes.RECT()
        # GetWindowRect includes invisible resize borders (negative for a
        # maximized window). DWM reports the visible frame in physical pixels.
        status = dwm.DwmGetWindowAttribute(
            window_id, 9, ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if status != 0:
            raise OSError(f"无法取得窗口物理边界：DwmGetWindowAttribute={status}")
        width, height = user.GetSystemMetrics(0), user.GetSystemMetrics(1)
        # v0.28.2 only has a portable primary-display contract. Refuse other
        # displays and straddling windows rather than guess a coordinate offset.
        if rect.left < 0 or rect.top < 0 or rect.right > width or rect.bottom > height:
            raise TargetError(
                "Computer Use 首版仅支持完整位于主显示器的窗口；不支持跨屏或其他显示器目标"
            )
        return WindowIdentity(
            pid,
            window_id,
            psutil.Process(pid).create_time(),
            (rect.left, rect.top, rect.right, rect.bottom),
            user.GetDpiForWindow(window_id),
        )
    finally:
        user.SetThreadDpiAwarenessContext(previous)
