"""Real Windows browser acceptance through the kernel-loaded plugin and host processes."""

import asyncio
import base64
import ctypes
from ctypes import wintypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
from threading import Thread

import psutil
import pytest
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package
from shiori_sdk.tools import ToolResult

from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from scripts.browser_acceptance import BrowserAcceptanceEvidence
from tests.support.browser_acceptance import record_native_daemons
from tests.support.plugin_kernel import make_kernel


def _owned_descendants(baseline: set[int]) -> set[int]:
    """Processes the host spawned below this test process since ``baseline``."""
    children = psutil.Process().children(recursive=True)
    return {child.pid for child in children} - baseline


def _alive(pid: int) -> bool:
    """Whether ``pid`` still runs; exited processes with open handles do not count."""
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


def _text(result: str | ToolResult) -> str:
    """Textual MCP results arrive either as plain text or as a text-only ToolResult."""
    return result.text if isinstance(result, ToolResult) else result


def _json(result: str | ToolResult):
    """The agent-browser JSON document that leads the textual result."""
    return json.JSONDecoder().raw_decode(_text(result))[0]


def _agent_browser_pids(pids: set[int]) -> set[int]:
    """The plugin's daemon/MCP processes among the owned descendants."""
    found = set()
    for pid in pids:
        try:
            if psutil.Process(pid).name().lower() == "agent-browser.exe":
                found.add(pid)
        except psutil.NoSuchProcess:
            pass
    return found


@pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("SHIORI_BROWSER_USE_RUNTIME"),
    reason="explicit fixed Windows runtime acceptance only",
)
@pytest.mark.parametrize("scenario", ["complete", "recovery"])
async def test_fixed_runtime_local_page_multimodal_persistence_and_cancellation(
    tmp_path, monkeypatch, caplog, scenario
):
    # SHIORI_BROWSER_USE_RUNTIME points at <resources>/native/browser-use; only
    # the host resources capability is redirected, the plugin resolves it itself.
    native = Path(os.environ["SHIORI_BROWSER_USE_RUNTIME"]).resolve()
    assert native.parent.name == "native" and native.name == "browser-use", native
    monkeypatch.setattr(
        "agent.plugin_host.processes.resource_root", lambda: native.parent.parent
    )
    metadata = json.loads((native / "native-runtime.json").read_text(encoding="utf-8"))
    expected = json.loads(
        (plugin_directory("browser_use") / "native-runtime.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata == expected
    assert metadata["agentBrowser"]["version"] == "0.38.2"
    # Runtime evidence must describe the executable actually used by this test.
    with (native / "agent-browser.exe").open("rb") as executable:
        runtime_sha256 = hashlib.file_digest(executable, "sha256").hexdigest()
    assert runtime_sha256 == metadata["agentBrowser"]["sha256"]
    evidence = BrowserAcceptanceEvidence(
        Path(os.environ.get("SHIORI_BROWSER_USE_EVIDENCE", str(tmp_path / "evidence")))
        / scenario,
        metadata,
    )
    record_native_daemons(monkeypatch, evidence)
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
    report = evidence.report
    report["scenario"] = scenario
    report["runtime_sha256"] = runtime_sha256

    roots = tmp_path / "plugins"
    stage_plugin_package(plugin_directory("browser_use"), roots / "browser_use")
    registry = ToolRegistry()
    kernel = make_kernel(
        [roots],
        event_bus=EventBus(),
        tools=registry,
        workspace=tmp_path / "workspace",
        plugin_configs={"browser_use": {"enabled": True}},
    )
    unloaded = False
    baseline = _owned_descendants(set())

    def tool(name):
        registered = registry.get_tool("agent_browser_" + name)
        assert registered is not None
        return registered

    async def call(name, arguments):
        return await evidence.run(
            name,
            lambda: tool(name).execute(role_id="mira", **arguments),
            arguments,
        )

    async def unload():
        errors = await kernel.unload("browser_use")
        if errors:
            raise ExceptionGroup("Browser acceptance cleanup failed", errors)

    failure = None
    try:
        await evidence.run("load", kernel.load_all)
        assert kernel.loaded_count == 1
        await call("open", {"url": url})
        browser_pids = _agent_browser_pids(_owned_descendants(baseline))
        assert browser_pids
        if scenario == "complete":
            await _exercise_multimodal_page(
                call, url, evidence.directory, browser_pids, baseline
            )
        pids = _owned_descendants(baseline)
        await call("close", {})
        assert all(not _alive(pid) for pid in pids)

        await call("open", {"url": url})
        if scenario == "complete":
            persisted = _text(
                await call("eval", {"script": "localStorage.getItem('name')"})
            )
            assert "栞与小风" in persisted
        owned = _owned_descendants(baseline)
        pending = asyncio.create_task(call("wait_ms", {"ms": 10000}))
        await asyncio.sleep(0.2)
        queued = asyncio.create_task(call("open", {"url": url + "/must-not-run"}))
        await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        # The queued action is retired together with the cancelled generation.
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            await queued
        assert all(not _alive(pid) for pid in owned)
        assert "/must-not-run" not in requests
        report["cancelled_owned_pids"] = sorted(owned)
        report["owned_pids_exited"] = True
        report["late_action_observed"] = False

        await call("open", {"url": url})
        await call("tab_new", {"url": url + "/close-target"})
        current = _json(await call("tab_list", {}))["data"]["tabs"]
        target = next(
            tab["targetId"] for tab in current if tab["url"].endswith("/close-target")
        )
        await call("tab_close", {"tab": target})
        remaining = _json(await call("tab_list", {}))["data"]["tabs"]
        assert not any(tab["url"].endswith("/close-target") for tab in remaining)
        last = _owned_descendants(baseline)
        assert last
        unloaded = True
        await evidence.run("unload", unload)
        assert all(not _alive(pid) for pid in last)
    except BaseException as error:
        failure = error
        raise
    finally:
        try:
            if not unloaded:
                unloaded = True
                await evidence.run("unload", unload)
        except BaseException as error:
            # Teardown is recorded separately without replacing the original action.
            if failure is None:
                failure = error
                raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            report["remaining_owned_pids"] = sorted(_owned_descendants(baseline))
            report["warnings"] = [
                record.getMessage() for record in caplog.records if record.levelno >= 30
            ]
            if failure is None and report["remaining_owned_pids"]:
                error = AssertionError("Browser acceptance left owned processes alive")
                evidence.finish(error)
                raise error
            evidence.finish(failure)


async def _exercise_multimodal_page(call, url, evidence, browser_pids, baseline):
    snapshot = _text(await call("snapshot", {"interactive": True}))
    textbox = re.search(r'textbox "姓名" \[ref=(e\d+)\]', snapshot)
    button = re.search(r'button "保存" \[ref=(e\d+)\]', snapshot)
    assert textbox and button, snapshot
    await call("fill", {"selector": "@" + textbox[1], "text": "栞与小风"})
    await call("click", {"selector": "@" + button[1]})
    saved = _text(await call("get_text", {"selector": "#result"}))
    assert "已保存：栞与小风" in saved
    result = await call("screenshot", {})
    assert isinstance(result, ToolResult) and result.content_blocks
    image = result.content_blocks[0]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")
    (evidence / "browser-filled.png").write_bytes(
        base64.b64decode(image.split(",", 1)[1])
    )
    await call("scroll", {"direction": "down", "amount": 700})
    scrolled = _text(await call("eval", {"script": "window.scrollY > 0"}))
    assert "true" in scrolled
    await call("tab_new", {"url": url + "/second"})
    tabs = _json(await call("tab_list", {}))
    assert any(tab["url"].endswith("/second") for tab in tabs["data"]["tabs"])
    lifecycle = tabs["data"]["lifecycle"]
    assert not lifecycle["restartedBackground"] and not lifecycle["relaunchedBrowser"]
    # A new tab reuses the same owned daemon/MCP processes.
    assert _agent_browser_pids(_owned_descendants(baseline)) == browser_pids
    tab_data = tabs["data"]["tabs"]
    original = next(
        tab["tabId"] for tab in tab_data if not tab["url"].endswith("/second")
    )
    await call("tab_switch", {"tab": original})
    refreshed = _json(await call("tab_list", {}))["data"]["tabs"]
    assert next(tab for tab in refreshed if tab["tabId"] == original)["active"]
