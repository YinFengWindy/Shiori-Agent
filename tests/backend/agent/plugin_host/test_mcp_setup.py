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


async def test_stdio_credentials_are_redacted_without_corrupting_source_json(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    """Real errors reach the host logger and model; ordinary env flags stay data."""
    from agent.plugin_host.call_gate import PluginCallGate
    from agent.plugin_host.core_keys import PluginBinding
    from agent.plugin_host.manifest import load_manifest
    from agent.tools.mcp_registration import HostMcpToolRegistration
    from agent.tools.registry import ToolRegistry
    from infra.process.plugin_capability import HostProcesses
    from plugins.mcp.backend.registry import McpServerRegistry
    from shiori_sdk.kernel import Scope
    from shiori_sdk.testing.extensions import FakeDependencies

    peer = tmp_path / "credential_peer.py"
    peer.write_text(
        """import argparse,json,os,sys
args=argparse.ArgumentParser()
args.add_argument('--token'); args.add_argument('--client-secret'); args.add_argument('--format')
options=args.parse_args()
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    if request['method']=='initialize': result={}
    elif request['method']=='tools/list': result={'tools':[{'name':'context','description':'JSON context','inputSchema':{'type':'object','properties':{'format':{'type':'string','enum':['json']}}}}]}
    elif request['params']['arguments'].get('error'):
        result={'isError':True,'content':[{'type':'text','text':'Credential rejected: '+options.token+' '+options.client_secret+' '+os.environ['MCP_API_KEY']}]}
    else:
        result={'content':[{'type':'text','text':json.dumps({'n':1,'format':options.format,'nested':[1,'json'],'echo':options.token,'embedded':json.dumps({'token':'business-token'})})}]}
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
""",
        encoding="utf-8",
    )
    values = ("inline-credential-995", "separate-credential-995", "env-credential-995")
    tools = ToolRegistry()
    scope = Scope("mcp")
    manifest = load_manifest(plugin_directory("mcp"))
    assert manifest is not None
    registration = HostMcpToolRegistration(tools).for_plugin(
        PluginBinding("mcp", "credential-stdio", manifest, scope, PluginCallGate("mcp"))
    )
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json",
        processes=HostProcesses(),
        registration=registration,
    )
    try:
        await registry.add(
            "credentials",
            [
                sys.executable,
                "-u",
                str(peer),
                "--token=" + values[0],
                "--client-secret",
                values[1],
                "--format",
                "json",
            ],
            env={"DEBUG": "1", "FORMAT": "json", "MCP_API_KEY": values[2]},
        )
        tool = tools.get_tool("mcp_credentials__context")
        assert tool is not None
        assert tool.parameters["properties"]["format"]["enum"] == ["json"]
        source = McpClientPool(dependencies=lambda: FakeDependencies({"mcp": registry}))
        assert await source.call("credentials", "context", {}) == {
            "n": 1,
            "format": "json",
            "nested": [1, "json"],
            "echo": "[已隐藏]",
            "embedded": json.dumps({"token": "business-token"}),
        }
        with caplog.at_level("ERROR", logger="agent.tools.registry"):
            output = await tools.execute(tool.name, {"error": True})
        assert isinstance(output, str) and "Credential rejected" in output
        assert "Credential rejected" in caplog.text
        assert all(value not in output and value not in caplog.text for value in values)
    finally:
        await registry.shutdown()
        assert await scope.close() == []


async def test_stdio_business_tokens_roundtrip_without_launch_credentials(
    tmp_path: Path,
):
    """Opaque cursors/handles returned to both callers must work in the next call."""
    from agent.plugin_host.call_gate import PluginCallGate
    from agent.plugin_host.core_keys import PluginBinding
    from agent.plugin_host.manifest import load_manifest
    from agent.tools.mcp_registration import HostMcpToolRegistration
    from agent.tools.registry import ToolRegistry
    from infra.process.plugin_capability import HostProcesses
    from plugins.mcp.backend.registry import McpServerRegistry
    from shiori_sdk.kernel import Scope
    from shiori_sdk.testing.extensions import FakeDependencies
    from shiori_sdk.tools import ToolResult

    peer = tmp_path / "business_token_peer.py"
    peer.write_text(
        """import json,sys
cursor='opaque-page-2'
element='s00000001:1'
embedded=json.dumps({'token':'opaque-operation-token'})
for line in sys.stdin:
    req=json.loads(line)
    if 'id' not in req: continue
    if req['method']=='initialize': result={}
    elif req['method']=='tools/list':
        result={'tools':[{'name':name,'description':name,'inputSchema':{'type':'object'}} for name in ['page','state','click']]}
    else:
        name=req['params']['name']; args=req['params']['arguments']
        if name=='page':
            if not args: result={'structuredContent':{'items':['first'],'next_page_token':cursor}}
            elif args.get('page_token')==cursor: result={'structuredContent':{'items':['second']}}
            else: result={'isError':True,'content':[{'type':'text','text':'Invalid page cursor'}]}
        elif name=='state':
            result={'content':[{'type':'text','text':json.dumps({'elements':[{'element_token':element}],'embedded':embedded,'token':'opaque-operation-token'})}]}
        elif args=={'element_token':element,'token':'opaque-operation-token','embedded':embedded}:
            result={'content':[{'type':'text','text':'clicked'}]}
        else: result={'isError':True,'content':[{'type':'text','text':'Invalid action handles'}]}
    print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}),flush=True)
""",
        encoding="utf-8",
    )
    tools = ToolRegistry()
    scope = Scope("mcp")
    manifest = load_manifest(plugin_directory("mcp"))
    assert manifest is not None
    registration = HostMcpToolRegistration(tools).for_plugin(
        PluginBinding("mcp", "business-tokens", manifest, scope, PluginCallGate("mcp"))
    )
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json",
        processes=HostProcesses(),
        registration=registration,
    )
    try:
        await registry.add("handles", [sys.executable, "-u", str(peer)])
        first = await tools.execute("mcp_handles__page", {})
        assert isinstance(first, ToolResult)
        emitted = json.loads(first.text)
        second = await tools.execute(
            "mcp_handles__page", {"page_token": emitted["next_page_token"]}
        )
        assert isinstance(second, ToolResult)
        assert second.structured_content == {"items": ["second"]}
        source = McpClientPool(dependencies=lambda: FakeDependencies({"mcp": registry}))
        source_first = await source.call("handles", "page", {})
        assert await source.call(
            "handles", "page", {"page_token": source_first["next_page_token"]}
        ) == {"items": ["second"]}
        raw_state = await tools.execute("mcp_handles__state", {})
        assert isinstance(raw_state, str)
        state = json.loads(raw_state)
        action = await tools.execute(
            "mcp_handles__click",
            {
                "element_token": state["elements"][0]["element_token"],
                "token": state["token"],
                "embedded": state["embedded"],
            },
        )
        assert action == "clicked"
    finally:
        await registry.shutdown()
        assert await scope.close() == []
