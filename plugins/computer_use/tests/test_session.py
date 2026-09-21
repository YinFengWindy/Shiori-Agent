"""A fixed real Windows Driver observes and changes only a controlled test app."""

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

from agent.tools.base import ToolResult
from agent.tools.turn_scope import tool_turn
from plugins.computer_use.backend.config import ComputerUseConfig
from plugins.computer_use.backend.desktop import ComputerDesktop
from plugins.computer_use.backend.tool import computer_tools
from plugins.computer_use.backend.windows import inspect_window


@pytest.fixture
def native_boundary(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from plugins.computer_use.backend.session import DesktopSession

    lease = SimpleNamespace(closed=False)

    def close_lease():
        lease.closed = True

    lease.close = close_lease
    client = SimpleNamespace(
        connect=AsyncMock(), call=AsyncMock(return_value="done"), disconnect=AsyncMock()
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.resolve_driver",
        lambda: tmp_path / "driver.exe",
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.DesktopLease", lambda: lease
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.driver_client", lambda *_: client
    )
    session = DesktopSession(tmp_path, ComputerUseConfig())
    session._targets = Mock(validate=Mock(return_value=None))
    return session, client, lease


async def test_stop_prevents_queued_input_and_retains_lease_until_disconnect(
    native_boundary,
):
    session, client, lease = native_boundary
    entered, disconnecting, finish = (asyncio.Event() for _ in range(3))

    async def blocked(*_args, **_kwargs):
        entered.set()
        await asyncio.Future()

    async def disconnect():
        disconnecting.set()
        await finish.wait()

    client.call.side_effect = blocked
    client.disconnect.side_effect = disconnect
    active = asyncio.create_task(session.call("click", {}))
    await entered.wait()
    queued = asyncio.create_task(session.call("type_text", {}))
    await asyncio.sleep(0)
    assert client.call.await_count == 1
    session.stop()
    active.cancel()
    results = await asyncio.gather(active, queued, return_exceptions=True)
    assert isinstance(results[0], asyncio.CancelledError)
    assert isinstance(results[1], RuntimeError)
    closing = asyncio.create_task(session.close())
    await disconnecting.wait()
    assert not lease.closed
    finish.set()
    await closing
    assert lease.closed and client.call.await_count == 1


async def test_startup_protocol_failure_releases_native_resources(
    native_boundary, tmp_path
):
    from agent.mcp.client import McpToolError

    _session, client, lease = native_boundary
    client.connect.side_effect = McpToolError(
        server="test", tool_name="initialize", message="startup failed"
    )
    manager = ComputerDesktop(tmp_path, ComputerUseConfig())

    @tool_turn
    async def run():
        with pytest.raises(McpToolError, match="startup failed"):
            await manager.call("role", "list_windows", {})
        with pytest.raises(RuntimeError, match="已停止"):
            await manager.call("role", "click", {})

    await run()
    assert lease.closed
    client.disconnect.assert_awaited_once()
    client.call.assert_not_awaited()


@pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("SHIORI_COMPUTER_USE_RUNTIME"),
    reason="Explicit opt-in is required to create the controlled native test window",
)
async def test_real_controlled_window(tmp_path, monkeypatch):
    native = Path(os.environ["SHIORI_COMPUTER_USE_RUNTIME"])
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.resolve_driver",
        lambda: native / "cua-driver.exe",
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
    desktop = ComputerDesktop(tmp_path / "plugin-data", ComputerUseConfig())
    tools = {tool.name: tool for tool in computer_tools(desktop)}
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
        result = await tools["computer_" + name].execute(
            role_id="acceptance", **arguments
        )
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
        identity = inspect_window(**target)
        records.append({"physical_bounds": identity.bounds, "dpi": identity.dpi})
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
                    "maximized_primary": inspect_window(**target).bounds,
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
        session = desktop._session
        assert (
            session is not None
            and session._client is not None
            and session._client._process is not None
        )
        process = psutil.Process(session._client._process.pid)
        driver_pids.extend(
            [process.pid, *(child.pid for child in process.children(recursive=True))]
        )

    try:
        await exercise()
        assert app.poll() is None
        assert all(not psutil.pid_exists(pid) for pid in driver_pids)
        records.append(
            {"owned_driver_pids_exited": driver_pids, "target_app_preserved": True}
        )
    finally:
        await desktop.close()
        app.terminate()
        app.wait(timeout=10)
        (evidence / "acceptance.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
