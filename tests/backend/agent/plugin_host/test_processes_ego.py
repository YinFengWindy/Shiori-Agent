"""Opt-in Windows acceptance against the user's installed ego browser."""

import asyncio
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

import pytest

from infra.process.plugin_capability import HostProcesses
from plugins.browser_use.backend.browser import BrowserSessions
from plugins.browser_use.backend.config import BrowserUseConfig
from plugins.browser_use.backend.ego_command import EgoCommand
from plugins.browser_use.backend.ego_command import EgoActionError
from plugins.browser_use.backend.ego_runtime import EgoRuntime
from plugins.browser_use.backend.ego_session import EgoSession
from plugins.browser_use.backend.ego_tool import ego_tools
from shiori_sdk.tools import ToolResult

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not os.environ.get("SHIORI_EGO_BROWSER"),
    reason="requires SHIORI_EGO_BROWSER pointing to an installed Windows ego client",
)


@pytest.fixture
def site():
    records = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/record"):
                records.append(self.path)
                self.send_response(204)
                self.end_headers()
                return
            delayed = self.path == "/delayed"
            timer = (
                "setTimeout(()=>document.querySelector('#late').disabled=false,4000);"
                "setTimeout(()=>fetch('/record?timer'),6000);"
                if delayed
                else ""
            )
            html = f"""<!doctype html><html><meta charset="utf-8"><title>Shiori native acceptance</title>
<body><h1>Shiori ego local test</h1><label>Name<input id="name"></label>
<button id="save" onclick="document.querySelector('#result').textContent=document.querySelector('#name').value">Save</button>
<p id="result">Empty</p><button id="late" {'disabled' if delayed else ''} onclick="fetch('/record?late')">Late</button>
<button id="arm" onclick="fetch('/record?armed')">Arm cancellation probe</button>
<div style="height:1800px"></div><p>End of page</p><script>{timer}</script></body></html>"""
            data = html.encode("utf8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_real_ego_role_isolation_images_and_cancelled_generations(
    tmp_path, site, monkeypatch
):
    url, records = site
    evidence = Path(os.environ.get("SHIORI_EGO_EVIDENCE", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    manager = BrowserSessions(
        tmp_path,
        BrowserUseConfig(backend="ego(lite)", timeout_seconds=10),
        processes=HostProcesses(),
        resources=tmp_path,
        ego_runtime=EgoRuntime(Path(os.environ["SHIORI_EGO_BROWSER"])),
    )
    tools = {
        tool.name.removeprefix("ego_browser_"): tool for tool in ego_tools(manager)
    }
    milestones = []
    version = subprocess.run(
        [os.environ["SHIORI_EGO_BROWSER"], "--version"],
        capture_output=True,
        text=True,
        encoding="utf8",
        check=True,
    )
    guide = subprocess.run(
        [os.environ["SHIORI_EGO_BROWSER"], "skill"],
        capture_output=True,
        text=True,
        encoding="utf8",
        check=True,
    )
    guide_version = re.search(
        r"\[ego-browser:skill\] end of guide (\S+)", guide.stdout + guide.stderr
    )
    assert guide_version
    versions = {
        "client": (version.stdout + version.stderr).strip(),
        "guide": guide_version[1],
    }

    async def call(role, operation, **arguments):
        result = await tools[operation].execute(role_id=role, **arguments)
        assert isinstance(result, str)
        return result

    try:
        assert "Empty" in await call("first", "open", url=url)
        assert "Empty" in await call("second", "open", url=url)
        result = await call(
            "first",
            "actions",
            actions=[
                {"action": "fill", "selector": "#name", "text": "角色一的中文"},
                {"action": "click", "selector": "#save"},
            ],
        )
        assert "角色一的中文" in result
        assert "角色一的中文" not in await call("second", "snapshot")
        milestones.append("role targets isolated; Chinese fill/click observed")

        image = await tools["screenshot"].execute(role_id="first", full_page=True)
        assert isinstance(image, ToolResult)
        encoded = image.content_blocks[0]["image_url"]["url"]
        assert encoded.startswith("data:image/png;base64,")
        raw = base64.b64decode(encoded.split(",", 1)[1])
        assert raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) > 1000
        (evidence / "ego-screenshot.png").write_bytes(raw)
        milestones.append("full-page screenshot reaches ToolResult as PNG")

        created = json.loads(await call("first", "tabs", action="new"))
        page = created["page"]
        assert page != "p1"
        assert "Empty" in await call("first", "open", page=page, url=url + "/second")
        await call("first", "tabs", action="close", page=page)
        assert "角色一的中文" in await call("first", "snapshot")
        await call(
            "first",
            "actions",
            actions=[{"action": "scroll", "x": 300, "y": 250, "delta_y": 1700}],
        )
        assert "End of page" in await call("first", "snapshot")
        milestones.append("managed tabs and scrolling observed")

        await call("second", "handoff")
        assert "Empty" in await call("second", "resume")
        milestones.append("handoff/resume retains the same test page")

        await call("first", "open", url=url + "/delayed")
        pending = asyncio.create_task(
            call(
                "first",
                "actions",
                actions=[
                    {"action": "click", "selector": "#arm"},
                    {"action": "click", "selector": "#late"},
                ],
            )
        )
        queued = asyncio.create_task(
            call("first", "actions", actions=[{"action": "click", "selector": "#save"}])
        )
        async with asyncio.timeout(5):
            while "/record?armed" not in records:
                await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            await queued
        await asyncio.sleep(6.5)
        assert records == ["/record?armed"], records
        assert "Empty" in await call("second", "snapshot")
        assert "Empty" in await call("first", "open", url=url)
        milestones.append(
            "cancel stops pending click, queued action and page timer; other role survives"
        )

        original = EgoCommand.run
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_ack(command, request):
            response = await original(command, request)
            if request["operation"] == "start":
                started.set()
                await release.wait()
            return response

        monkeypatch.setattr(EgoCommand, "run", delayed_ack)
        startup = asyncio.create_task(call("startup", "open", url=url))
        await asyncio.wait_for(started.wait(), 10)
        startup.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await startup
        monkeypatch.setattr(EgoCommand, "run", original)
        assert "Empty" in await call("startup", "open", url=url)
        milestones.append(
            "cancel before startup receipt closes late-created Space and allows new generation"
        )

        # Once handed off, the browser's task is a user resource. Plugin shutdown
        # must preserve it; reclaim only this test-created Space to inspect and
        # clean up the fixture after proving preservation.
        await call("second", "handoff")
        handed_off = manager._sessions["second"]
        assert isinstance(handed_off, EgoSession)
        state = json.loads((handed_off.root / "space.json").read_text(encoding="utf8"))
        await call("second", "close")
        receipt = evidence / "preserved-page.txt"
        script = evidence / "inspect-preserved-test-space.mjs"
        script.write_text(
            f"const task = await takeOverTaskSpace({state['id']});\n"
            f"const fs = await import('node:fs/promises');\n"
            f"await fs.writeFile({json.dumps(receipt.as_posix())}, await task.page('p1').snapshot(), 'utf8');\n"
            "await task.finish({keep: []});\n",
            encoding="utf8",
        )
        inspection = await asyncio.create_subprocess_exec(
            os.environ["SHIORI_EGO_BROWSER"],
            "nodejs",
            "-e",
            f"await import('{script.as_uri()}')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, errors = await asyncio.wait_for(inspection.communicate(), 10)
        assert inspection.returncode == 0, errors
        assert "Empty" in receipt.read_text(encoding="utf8")
        milestones.append(
            "handed-off user task survives plugin close and can be reclaimed"
        )
    finally:
        await manager.close()
        (evidence / "acceptance.json").write_text(
            json.dumps(
                {
                    "versions": versions,
                    "milestones": milestones,
                    "observed_requests": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf8",
        )
    assert not manager._sessions


async def test_real_early_helper_timeout_retires_space_but_stale_refs_recover(
    tmp_path, site
):
    url, records = site
    manager = BrowserSessions(
        tmp_path,
        BrowserUseConfig(backend="ego(lite)", timeout_seconds=10),
        processes=HostProcesses(),
        resources=tmp_path,
        ego_runtime=EgoRuntime(Path(os.environ["SHIORI_EGO_BROWSER"])),
    )
    try:
        await manager.call("role", "ego_browser_open", {"url": url})
        original = manager._sessions["role"]
        with pytest.raises(EgoActionError) as stale:
            await manager.call(
                "role",
                "ego_browser_actions",
                {"actions": [{"action": "click", "selector": "@999999"}]},
            )
        assert stale.value.recoverable
        snapshot = await manager.call("role", "ego_browser_snapshot", {})
        assert isinstance(snapshot, str) and "Empty" in snapshot
        assert manager._sessions["role"] is original

        await manager.call("role", "ego_browser_handoff", {})
        with pytest.raises(EgoActionError) as paused:
            await manager.call("role", "ego_browser_snapshot", {})
        assert (
            paused.value.details.get("error_code") == "EGO_TASK_SPACE_USER_IN_CONTROL"
        )
        assert paused.value.recoverable
        assert manager._sessions["role"] is original
        resumed = await manager.call("role", "ego_browser_resume", {})
        assert isinstance(resumed, str) and "Empty" in resumed

        active = asyncio.create_task(
            manager.call(
                "role",
                "ego_browser_actions",
                {
                    "actions": [
                        {"action": "click", "selector": "#arm"},
                        {"action": "press", "selector": "#missing", "key": "Enter"},
                    ]
                },
            )
        )
        async with asyncio.timeout(5):
            while "/record?armed" not in records:
                await asyncio.sleep(0.02)
        queued = asyncio.create_task(
            manager.call(
                "role",
                "ego_browser_actions",
                {"actions": [{"action": "click", "selector": "#late"}]},
            )
        )
        with pytest.raises(EgoActionError) as timeout:
            # Installed press() defaults to 3000ms; the Python deadline is 10s.
            await asyncio.wait_for(active, 7)
        assert timeout.value.details.get("name") == "ElementResolutionError"
        assert timeout.value.details.get("kind") == "transient"
        assert not timeout.value.recoverable
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            await queued
        assert records == ["/record?armed"]
        assert "role" not in manager._sessions
        result = await manager.call("role", "ego_browser_open", {"url": url})
        assert isinstance(result, str) and "Empty" in result
    finally:
        await manager.close()
