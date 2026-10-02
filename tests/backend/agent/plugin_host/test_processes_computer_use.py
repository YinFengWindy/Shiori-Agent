"""A fixed real Windows Driver, loaded through the kernel, changes only a test app."""

import asyncio
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psutil
import pytest
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package
from shiori_sdk.tools import ToolResult

from agent.tools.registry import ToolRegistry
from agent.tools.turn_scope import tool_turn
from bus.event_bus import EventBus
from tests.backend.agent.plugin_host.conftest import make_kernel


def _driver_pids() -> list[int]:
    """Driver processes the host spawned below this test process."""
    return [
        child.pid
        for child in psutil.Process().children(recursive=True)
        if child.name().lower().startswith("cua-driver")
    ]


@pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("SHIORI_COMPUTER_USE_RUNTIME"),
    reason="Explicit opt-in is required to create the controlled native test window",
)
async def test_real_controlled_window(tmp_path, monkeypatch):
    # SHIORI_COMPUTER_USE_RUNTIME points at <resources>/native/computer-use; only
    # the host resources capability is redirected, the plugin resolves it itself.
    native = Path(os.environ["SHIORI_COMPUTER_USE_RUNTIME"]).resolve()
    assert native.parent.name == "native" and native.name == "computer-use", native
    monkeypatch.setattr(
        "agent.plugin_host.processes.resource_root", lambda: native.parent.parent
    )
    evidence = Path(
        os.environ.get("SHIORI_COMPUTER_USE_EVIDENCE", str(tmp_path / "evidence"))
    )
    evidence.mkdir(parents=True, exist_ok=True)
    state_path = tmp_path / "app.json"
    title = "Shiori Computer Use Acceptance " + uuid4().hex[:8]
    app = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path(__file__).with_name("controlled_app.ps1")),
            "-StatePath",
            str(state_path),
            "-WindowTitle",
            title,
        ],
        creationflags=0x08000000,
    )
    roots = tmp_path / "plugins"
    stage_plugin_package(plugin_directory("computer_use"), roots / "computer_use")
    registry = ToolRegistry()
    kernel = make_kernel(
        [roots],
        event_bus=EventBus(),
        tools=registry,
        workspace=tmp_path / "workspace",
        plugin_configs={"computer_use": {"enabled": True}},
    )
    await kernel.load_all()
    assert kernel.loaded_count == 1
    records = []
    driver_pids: list[int] = []

    async def actual(predicate):
        for _ in range(100):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if predicate(state):
                    return state
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            await asyncio.sleep(0.05)
        raise AssertionError("Controlled application state did not change as expected")

    async def call(name, **arguments):
        tool = registry.get_tool("computer_" + name)
        assert tool is not None
        result = await tool.execute(role_id="acceptance", **arguments)
        records.append(
            {
                "tool": name,
                "arguments": arguments,
                "result": (
                    result.structured_content
                    if isinstance(result, ToolResult)
                    else result
                ),
            }
        )
        return result

    @tool_turn
    async def exercise():
        app_state = await actual(lambda state: state["pid"] == app.pid)
        target = {"pid": app.pid, "window_id": app_state["window_id"]}
        windows = await call("list_windows", pid=app.pid)
        assert title in (windows.text if isinstance(windows, ToolResult) else windows)
        snapshot = await call("get_window_state", **target)
        assert isinstance(snapshot, ToolResult) and snapshot.structured_content
        first = snapshot.structured_content
        assert first["pid"] == app.pid and first["window_id"] == target["window_id"]
        assert snapshot.content_blocks
        assert "base64" not in snapshot.text
        (evidence / "controlled-window.png").write_bytes(
            base64.b64decode(
                snapshot.content_blocks[0]["image_url"]["url"].split(",", 1)[1]
            )
        )
        records.append({"physical_bounds": first["window_bounds"]})
        edit = next(e for e in first["elements"] if e["label"] == "验收输入")
        button = next(e for e in first["elements"] if e["label"] == "验证按钮")
        await call(
            "type_text",
            **target,
            snapshot_id=first["snapshot_id"],
            observation_id=first["observation_id"],
            element_token=edit["element_token"],
            text="你好，Shiori 中文验收",
        )
        await actual(lambda state: state["text"] == "你好，Shiori 中文验收")
        await call(
            "click",
            **target,
            snapshot_id=first["snapshot_id"],
            observation_id=first["observation_id"],
            element_token=button["element_token"],
        )
        await actual(lambda state: state["clicks"] == 1)
        fresh_result = await call("get_window_state", **target)
        fresh = fresh_result.structured_content
        with pytest.raises(ValueError, match="snapshot_id 已失效"):
            await call(
                "click",
                **target,
                snapshot_id=first["snapshot_id"],
                observation_id=first["observation_id"],
                element_token=button["element_token"],
            )
        button = next(e for e in fresh["elements"] if e["label"] == "验证按钮")
        frame, bounds = button["frame"], fresh["window_bounds"]
        await call(
            "click",
            **target,
            snapshot_id=fresh["snapshot_id"],
            observation_id=fresh["observation_id"],
            x=frame["x"] + frame["w"] / 2 - bounds["x"],
            y=frame["y"] + frame["h"] / 2 - bounds["y"],
        )
        await actual(lambda state: state["clicks"] == 2)
        with pytest.raises(ValueError, match="foreground"):
            await call(
                "hotkey",
                **target,
                snapshot_id=fresh["snapshot_id"],
                observation_id=fresh["observation_id"],
                keys=["ctrl", "shift", "k"],
            )
        unchanged = await actual(lambda state: state["text"] == "你好，Shiori 中文验收")
        assert unchanged["shortcut"] is False
        records.append({"background_shortcut_refused_before_input": unchanged})
        await call(
            "hotkey",
            **target,
            snapshot_id=fresh["snapshot_id"],
            observation_id=fresh["observation_id"],
            keys=["ctrl", "shift", "k"],
            delivery_mode="foreground",
        )
        state = await actual(lambda state: state["shortcut"] is True)
        assert state["text"] == "你好，Shiori 中文验收"
        assert state["clicks"] == 2
        records.append({"actual_application_state": state})
        final_observation = await call("get_window_state", **target)
        (evidence / "controlled-window-final.png").write_bytes(
            base64.b64decode(
                final_observation.content_blocks[0]["image_url"]["url"].split(",", 1)[1]
            )
        )
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        previous_dpi = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        original = wintypes.RECT()
        user.GetWindowRect(target["window_id"], ctypes.byref(original))
        width = user.GetSystemMetrics(0)
        records.append(
            {
                "monitor_count": user.GetSystemMetrics(80),
                "primary_physical_size": [width, user.GetSystemMetrics(1)],
            }
        )
        try:
            for label, x in (("straddling", width - 50), ("off_primary", width + 100)):
                assert user.SetWindowPos(
                    target["window_id"], None, x, 100, 600, 360, 0x0014
                )
                with pytest.raises(ValueError, match="主显示器") as error:
                    await call("get_window_state", **target)
                records.append(
                    {"layout": label, "requested_x": x, "refusal": str(error.value)}
                )
            # Maximize only after the owned window is back on primary.
            user.ShowWindow(target["window_id"], 9)
            assert user.SetWindowPos(
                target["window_id"],
                None,
                original.left,
                original.top,
                original.right - original.left,
                original.bottom - original.top,
                0x0014,
            )
            user.ShowWindow(target["window_id"], 3)
            maximized = await call("get_window_state", **target)
            max_data = maximized.structured_content
            max_button = next(
                e for e in max_data["elements"] if e["label"] == "验证按钮"
            )
            max_frame, max_bounds = max_button["frame"], max_data["window_bounds"]
            await call(
                "click",
                **target,
                snapshot_id=max_data["snapshot_id"],
                observation_id=max_data["observation_id"],
                x=(max_frame["x"] + max_frame["w"] / 2 - max_bounds["x"])
                * max_data["screenshot_width"]
                / max_bounds["width"],
                y=(max_frame["y"] + max_frame["h"] / 2 - max_bounds["y"])
                * max_data["screenshot_height"]
                / max_bounds["height"],
            )
            scaled_state = await actual(lambda state: state["clicks"] == 3)
            records.append({"scaled_screenshot_coordinate_click": scaled_state})
            records.append(
                {
                    "maximized_primary": max_bounds,
                    "snapshot_id": maximized.structured_content["snapshot_id"],
                }
            )
        finally:
            user.ShowWindow(target["window_id"], 9)
            user.SetWindowPos(
                target["window_id"],
                None,
                original.left,
                original.top,
                original.right - original.left,
                original.bottom - original.top,
                0x0014,
            )
            user.SetThreadDpiAwarenessContext(previous_dpi)
        restored = await call("get_window_state", **target)
        (evidence / "controlled-window-final.png").write_bytes(
            base64.b64decode(
                restored.content_blocks[0]["image_url"]["url"].split(",", 1)[1]
            )
        )
        # A forged PID and unsupported target cannot silently select another app.
        with pytest.raises(ValueError, match="身份不匹配"):
            await call(
                "get_window_state", pid=app.pid + 1, window_id=target["window_id"]
            )
        with pytest.raises(ValueError, match="不支持"):
            await call(
                "click",
                **target,
                snapshot_id=fresh["snapshot_id"],
                observation_id=fresh["observation_id"],
                target={"kind": "desktop", "display_id": "secondary"},
                x=10,
                y=10,
            )
        driver_pids.extend(_driver_pids())
        assert driver_pids

    try:
        await exercise()
        assert app.poll() is None
        assert all(not psutil.pid_exists(pid) for pid in driver_pids)
        records.append(
            {"owned_driver_pids_exited": driver_pids, "target_app_preserved": True}
        )
    finally:
        await kernel.unload("computer_use")
        app.terminate()
        app.wait(timeout=10)
        (evidence / "acceptance.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
