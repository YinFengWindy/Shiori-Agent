"""Production MCP assembly: protocol effects, dependency calls and reload admission."""

import asyncio
import json
import sys
from pathlib import Path
import pytest
from agent.config_models import Config
from agent.plugin_host.dependencies import PluginDependencies
from agent.plugin_host.unload import PluginReloadTimeout
from bootstrap.app import AppRuntime, RuntimeFeatures
from plugins.proactive.backend.mcp_sources import McpClientPool
from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

PEER = r"""
import json, os, sys, time, threading
from pathlib import Path
lock = threading.Lock()
def send(value):
    with lock: print(json.dumps(value), flush=True)
def respond(req):
    method = req['method']; ident = req['id']
    if method == 'initialize':
        result = {}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'echo', 'description': 'Echo', 'inputSchema': {'type': 'object'}}]}
    else:
        args = req['params']['arguments']
        if set(args) - {'value', 'delay'}:
            send({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32602, 'message': 'unexpected arguments'}}); return
        if args.get('delay'):
            Path(os.environ['MARKER']).write_text('accepted')
            time.sleep(args['delay'])
        result = {'content': [{'type': 'text', 'text': json.dumps({'value': args.get('value', 'actual'), 'cwd': os.getcwd()})}]}
    send({'jsonrpc': '2.0', 'id': ident, 'result': result})
for line in sys.stdin:
    req=json.loads(line)
    if 'id' in req: threading.Thread(target=respond,args=(req,),daemon=True).start()
"""


async def wait_until(read, accepted):
    async with asyncio.timeout(10):
        while True:
            result = await read()
            if accepted(result):
                return result
            await asyncio.sleep(0.01)


async def test_real_source_and_chat_share_filter_and_gate_survives_failed_reload(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "plugins"
    stage_plugin_package(plugin_directory("mcp"), root / "mcp")
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
    workspace = tmp_path / "workspace"
    script = tmp_path / "peer.py"
    script.write_text(PEER, encoding="utf-8")
    marker = tmp_path / "accepted"
    app = AppRuntime(
        Config(
            provider="",
            model="",
            api_key="",
            model_registrations=[],
            plugins={"mcp": {"enabled": True}},
        ),
        workspace,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    await app.start()
    try:
        core = app.core
        assert core is not None and core.plugin_manager is not None
        manager = core.plugin_manager

        async def rpc(name, payload=None):
            resolved = core.plugin_rpc.resolve("mcp." + name)
            assert resolved is not None
            return await resolved[1](payload or {})

        await wait_until(
            lambda: rpc("servers.list"), lambda value: not value["loading"]
        )
        await rpc(
            "servers.save",
            {
                "server_id": "test",
                "config": {"transport": {"kind": "stdio", "cwd": str(tmp_path)}},
                "credentials": {
                    "command": {
                        "op": "replace",
                        "value": [sys.executable, "-u", str(script)],
                    },
                    "env": {
                        "op": "replace",
                        "value": {"MARKER": str(marker), "TOKEN": "unprintable-secret"},
                    },
                },
            },
        )
        await wait_until(
            lambda: rpc("servers.list"),
            lambda value: value["servers"][0]["status"] == "connected",
        )
        dependencies = PluginDependencies(
            (), manager._dependency_api, optional_declared=("mcp",)
        )
        source = McpClientPool(workspace, dependencies=lambda: dependencies)
        outcome = await source.call("test", "echo", {"value": "source"}, timeout=180)
        assert outcome == {"value": "source", "cwd": str(tmp_path)}
        core.tools.set_context(
            channel="desktop", role_id="mira", account_full_tools="true"
        )
        chat = json.loads(await core.tools.execute("mcp_test__echo", {"value": "chat"}))
        assert chat["value"] == "chat"
        old = core.tools.get_tool("mcp_test__echo")
        running = asyncio.create_task(source.call("test", "echo", {"delay": 0.3}))

        async def accepted():
            return marker.exists()

        await wait_until(accepted, bool)
        gate = manager._instances["mcp"].calls
        assert gate.in_flight == 1
        with pytest.raises(PluginReloadTimeout):
            await manager.reload(
                "mcp",
                values={"enabled": True},
                raw_values={"enabled": True},
                drain_timeout=0.02,
            )
        assert gate.open
        assert (await running)["value"] == "actual"
        assert gate.in_flight == 0
        assert (await source.call("test", "echo", {}))["value"] == "actual"
        await rpc(
            "servers.save",
            {
                "server_id": "test",
                "expected_revision": 1,
                "config": {"tools": {"mode": "selected", "names": []}},
            },
        )
        with pytest.raises(ValueError):
            await source.call("test", "echo", {})
        with pytest.raises(ValueError):
            await old.execute()
        await rpc(
            "servers.save",
            {
                "server_id": "test",
                "expected_revision": 2,
                "config": {"tools": {"mode": "all"}},
            },
        )
        await manager.reload(
            "mcp",
            values={"enabled": True},
            raw_values={"enabled": True},
            drain_timeout=5,
        )
        with pytest.raises(PluginRpcError):
            await old.execute()
        await wait_until(
            lambda: rpc("servers.list"),
            lambda value: bool(value["servers"])
            and value["servers"][0]["status"] == "connected",
        )
        assert (await source.call("test", "echo", {}))["value"] == "actual"
        assert "unprintable-secret" not in json.dumps(await rpc("servers.list"))
    finally:
        await app.shutdown()
