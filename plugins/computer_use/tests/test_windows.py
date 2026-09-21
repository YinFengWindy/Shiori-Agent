"""Read-only target checks use visible physical bounds and restore thread DPI."""

import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest

from plugins.computer_use.backend.windows import inspect_window


@pytest.fixture
def win32(monkeypatch):
    state = SimpleNamespace(
        pid=42,
        exists=True,
        minimized=False,
        bounds=(100, 100, 700, 460),
        dpi=144,
        contexts=[],
    )

    def get_pid(_hwnd, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = state.pid

    def get_rect(_hwnd, attribute, pointer, _size):
        assert attribute == 9
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = state.bounds
        return 0

    def set_dpi(value):
        state.contexts.append(value)
        return 42

    user = SimpleNamespace(
        IsWindow=lambda _: state.exists,
        IsIconic=lambda _: state.minimized,
        GetWindowThreadProcessId=get_pid,
        DwmGetWindowAttribute=get_rect,
        GetDpiForWindow=lambda _: state.dpi,
        SetThreadDpiAwarenessContext=set_dpi,
        GetSystemMetrics=lambda metric: {0: 1920, 1: 1080}[metric],
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kw: user, raising=False)
    monkeypatch.setattr(
        "plugins.computer_use.backend.windows.psutil.Process",
        lambda _: SimpleNamespace(create_time=lambda: 123.0),
    )
    return state


def test_physical_bounds_and_per_window_dpi_are_preserved(win32):
    result = inspect_window(42, 81)
    assert result.bounds == (100, 100, 700, 460)
    assert result.dpi == 144 and result.created == 123.0
    assert win32.contexts[-1] == 42


def test_maximized_visible_frame_on_primary_is_supported(win32):
    win32.bounds = (0, 0, 1920, 1040)
    assert inspect_window(42, 81).bounds == win32.bounds


@pytest.mark.parametrize(
    "bounds",
    [
        (-100, 100, 300, 460),
        (1900, 100, 2300, 460),
        (2000, 100, 2400, 460),
        (100, -10, 700, 460),
    ],
)
def test_cross_screen_and_non_primary_bounds_fail_explicitly(win32, bounds):
    win32.bounds = bounds
    with pytest.raises(ValueError, match="主显示器"):
        inspect_window(42, 81)
    assert win32.contexts[-1] == 42


@pytest.mark.parametrize(
    "field,value", [("pid", 43), ("exists", False), ("minimized", True)]
)
def test_stale_foreign_and_minimized_windows_are_not_retargeted(win32, field, value):
    setattr(win32, field, value)
    with pytest.raises(ValueError):
        inspect_window(42, 81)
