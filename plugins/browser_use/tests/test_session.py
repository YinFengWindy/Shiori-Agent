"""Real Windows browser acceptance and owned-session resource failure boundaries."""

import asyncio
import base64
import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
from threading import Thread
from unittest.mock import AsyncMock, Mock

import pytest

from agent.tools.base import ToolResult
from plugins.browser_use.backend.config import BrowserUseConfig
from plugins.browser_use.backend.runtime import BrowserRuntime
from plugins.browser_use.backend.session import BrowserSession


async def test_cleanup_releases_profile_even_when_job_fails(tmp_path):
    session = BrowserSession(
        tmp_path,
        "role",
        BrowserUseConfig(),
        BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    session._client = AsyncMock()
    session._daemon = AsyncMock()
    session._daemon.close.side_effect = RuntimeError("job failure")
    lease = Mock()
    session._lease = lease
    with pytest.raises(RuntimeError, match="job failure"):
        await session.close()
    lease.close.assert_called_once()


def _owned_pids(job):
    kernel = job._kernel
    kernel.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    data = (ctypes.c_size_t * 1025)()
    assert kernel.QueryInformationJobObject(
        job._handle, 3, ctypes.byref(data), ctypes.sizeof(data), None
    )
    count = ctypes.cast(data, ctypes.POINTER(wintypes.DWORD))[1]
    return list(data[1 : count + 1])


def _alive(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("SHIORI_BROWSER_USE_RUNTIME"),
    reason="explicit fixed Windows runtime acceptance only",
)
async def test_fixed_runtime_local_page_multimodal_persistence_and_cancellation(
    tmp_path,
):
    native = Path(os.environ["SHIORI_BROWSER_USE_RUNTIME"])
    metadata = json.loads((native / "native-runtime.json").read_text(encoding="utf-8"))
    assert metadata["agentBrowser"]["version"] == "0.38.1"
    runtime = BrowserRuntime(
        native / "agent-browser.exe", native / "chrome-win64" / "chrome.exe"
    )
    evidence = Path(
        os.environ.get("SHIORI_BROWSER_USE_EVIDENCE", str(tmp_path / "evidence"))
    )
    evidence.mkdir(parents=True, exist_ok=True)
    requests = []
    html = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>Shiori 浏览器验收</title>
    <style>body{font:24px sans-serif;margin:48px;background:#f6f4ef;color:#202432}input,button{font:inherit;padding:12px;margin:12px}#space{height:1800px}</style>
    <h1>Shiori · Browser Use</h1><label>姓名<input aria-label="姓名" id="name"></label>
    <button onclick="localStorage.setItem('name',document.querySelector('#name').value);document.querySelector('#result').textContent='已保存：'+localStorage.getItem('name')">保存</button>
    <p id="result">等待填写</p><div id="space"></div><p>页面底部</p></html>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    sessions = []
    report = {"versions": metadata, "steps": []}

    async def call(session, name, arguments):
        result = await session.call("agent_browser_" + name, arguments)
        report["steps"].append(
            {
                "tool": name,
                "text": result.text if isinstance(result, ToolResult) else result,
                "image_blocks": (
                    len(result.content_blocks) if isinstance(result, ToolResult) else 0
                ),
            }
        )
        return result

    try:
        session = BrowserSession(
            tmp_path / "browser", "mira", BrowserUseConfig(), runtime
        )
        sessions.append(session)
        await call(session, "open", {"url": url})
        daemon_pid = session._daemon._process.pid
        assert session._daemon._process.returncode is None
        snapshot = await call(session, "snapshot", {"interactive": True})
        assert isinstance(snapshot, str)
        textbox = re.search(r'textbox "姓名" \[ref=(e\d+)\]', snapshot)
        button = re.search(r'button "保存" \[ref=(e\d+)\]', snapshot)
        assert textbox and button, snapshot
        await call(session, "fill", {"selector": "@" + textbox[1], "text": "栞与小风"})
        await call(session, "click", {"selector": "@" + button[1]})
        saved = await call(session, "get_text", {"selector": "#result"})
        assert isinstance(saved, str) and "已保存：栞与小风" in saved
        result = await call(session, "screenshot", {})
        assert isinstance(result, ToolResult) and result.content_blocks
        image = result.content_blocks[0]["image_url"]["url"]
        assert image.startswith("data:image/png;base64,")
        (evidence / "browser-filled.png").write_bytes(
            base64.b64decode(image.split(",", 1)[1])
        )
        await call(session, "scroll", {"direction": "down", "amount": 700})
        scrolled = await call(session, "eval", {"script": "window.scrollY > 0"})
        assert isinstance(scrolled, str) and "true" in scrolled
        await call(session, "tab_new", {"url": url + "/second"})
        tabs = await call(session, "tab_list", {})
        assert isinstance(tabs, str) and "/second" in tabs
        lifecycle = json.loads(tabs)["data"]["lifecycle"]
        assert (
            not lifecycle["restartedBackground"] and not lifecycle["relaunchedBrowser"]
        )
        assert session._daemon._process.pid == daemon_pid
        assert session._daemon._process.returncode is None
        tab_data = json.loads(tabs)["data"]["tabs"]
        original = next(
            tab["tabId"] for tab in tab_data if not tab["url"].endswith("/second")
        )
        await call(session, "tab_switch", {"tab": original})
        refreshed = json.loads(await call(session, "tab_list", {}))["data"]["tabs"]
        assert next(tab for tab in refreshed if tab["tabId"] == original)["active"]
        pids = _owned_pids(session._daemon._job) + _owned_pids(session._client._job)
        await session.close(graceful=True)
        assert all(not _alive(pid) for pid in pids)
        second = BrowserSession(
            tmp_path / "browser", "mira", BrowserUseConfig(), runtime
        )
        sessions.append(second)
        await call(second, "open", {"url": url})
        persisted = await call(
            second, "eval", {"script": "localStorage.getItem('name')"}
        )
        assert isinstance(persisted, str) and "栞与小风" in persisted
        owned = _owned_pids(second._daemon._job) + _owned_pids(second._client._job)
        pending = asyncio.create_task(
            second.call("agent_browser_wait_ms", {"ms": 10000})
        )
        await asyncio.sleep(0.2)
        queued = asyncio.create_task(
            second.call("agent_browser_open", {"url": url + "/must-not-run"})
        )
        await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        with pytest.raises(RuntimeError, match="已停止"):
            await queued
        assert all(not _alive(pid) for pid in owned)
        assert "/must-not-run" not in requests
        report["cancelled_owned_pids"] = owned
        report["owned_pids_exited"] = True
        report["late_action_observed"] = False
        third = BrowserSession(
            tmp_path / "browser", "mira", BrowserUseConfig(), runtime
        )
        sessions.append(third)
        await call(third, "open", {"url": url})
        await call(third, "tab_new", {"url": url + "/close-target"})
        current = json.loads(await call(third, "tab_list", {}))["data"]["tabs"]
        target = next(
            tab["targetId"] for tab in current if tab["url"].endswith("/close-target")
        )
        await call(third, "tab_close", {"tab": target})
        remaining = json.loads(await call(third, "tab_list", {}))["data"]["tabs"]
        assert not any(tab["url"].endswith("/close-target") for tab in remaining)
    finally:
        for session in sessions:
            await session.close()
        server.shutdown()
        server.server_close()
        thread.join()
        (evidence / "acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


@pytest.mark.parametrize("phase", ["initialize", "tools/list"])
async def test_mcp_startup_errors_release_profile_and_native_resources(
    tmp_path, monkeypatch, phase
):
    from agent.mcp.client import McpClient, McpToolError
    from plugins.browser_use.backend.daemon import BrowserDaemon
    from plugins.browser_use.backend.profile import ProfileLease

    daemon_close = AsyncMock()
    disconnect = AsyncMock()
    operation = AsyncMock()
    error = McpToolError(
        server="browser_use", tool_name=phase, message="controlled init failure"
    )
    monkeypatch.setattr(BrowserDaemon, "start", AsyncMock())
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(McpClient, "connect", AsyncMock(side_effect=error))
    monkeypatch.setattr(McpClient, "disconnect", disconnect)
    monkeypatch.setattr(McpClient, "call", operation)
    session = BrowserSession(
        tmp_path,
        "role",
        BrowserUseConfig(),
        BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    with pytest.raises(McpToolError) as raised:
        await session.call("agent_browser_open", {})
    assert raised.value is error
    assert session.closed and session._lease is None
    assert session._client is session._daemon is None
    daemon_close.assert_awaited_once()
    disconnect.assert_awaited_once()
    operation.assert_not_awaited()
    lease = ProfileLease(session.profile)
    lease.close()


async def test_completed_tool_error_keeps_established_page_and_profile(
    tmp_path, monkeypatch
):
    from agent.mcp.client import McpClient, McpToolError
    from plugins.browser_use.backend.daemon import BrowserDaemon

    daemon_close = AsyncMock()
    disconnect = AsyncMock()
    error = McpToolError(
        server="browser_use", tool_name="agent_browser_click", message="stale ref"
    )
    remote = AsyncMock(side_effect=["opened", error, "fresh snapshot", "closed"])
    monkeypatch.setattr(BrowserDaemon, "start", AsyncMock())
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(McpClient, "connect", AsyncMock())
    monkeypatch.setattr(McpClient, "disconnect", disconnect)
    monkeypatch.setattr(McpClient, "call", remote)
    session = BrowserSession(
        tmp_path,
        "role",
        BrowserUseConfig(),
        BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    await session.call("agent_browser_open", {})
    client = session._client
    with pytest.raises(McpToolError, match="stale ref"):
        await session.call("agent_browser_click", {"selector": "@old"})
    assert not session.closed and session._lease is not None
    assert session._client is client
    daemon_close.assert_not_awaited()
    disconnect.assert_not_awaited()
    assert await session.call("agent_browser_snapshot", {}) == "fresh snapshot"
    await session.close(graceful=True)
