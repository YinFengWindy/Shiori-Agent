"""Exercise the stdio transport against a real, concurrent JSON-RPC peer."""

import asyncio
import logging
import sys
from unittest.mock import AsyncMock

import pytest

from shiori_mcp_client import StdioMcpSession, McpProtocolError
from shiori_mcp_client.stdio import _infer_cwd
from .processes import RecordingProcesses
from shiori_mcp_client import McpToolError
from shiori_sdk.tools import ToolResult


class SessionFixture(StdioMcpSession):
    """Keep process observations in the fixture, not the public session contract."""

    def __init__(self, *args, **kwargs):
        self.test_processes = RecordingProcesses()
        self.discovered = []
        super().__init__(*args, processes=self.test_processes, **kwargs)


def client_for(*args, **kwargs):
    return SessionFixture(*args, **kwargs)


_SERVER = r"""
import json, sys, threading, time, os
lock=threading.Lock()
def send(message):
    with lock:
        print(json.dumps({"jsonrpc":"2.0", **message}), flush=True)
def respond(request):
    ident=request['id']; method=request['method']; args=request.get('params',{})
    if method=='server/discover':
        send({'id':ident,'error':{'code':-32601,'message':'legacy'}}); return
    if method=='initialize':
        if os.environ.get('FAIL_INIT'):
            send({'id':ident,'error':{'code':-32042,'message':'init failed'}}); return
        send({'id':ident,'result':{'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'peer','version':'1'}}}); return
    if method=='tools/list':
        result={'tools':[{'name':'echo','description':'Echo','inputSchema':{'type':'object'}}]}
        if not args.get('cursor'): result['nextCursor']='second'
        else: result={'tools':[{'name':'image','description':'Image','inputSchema':{'type':'object'}}]}
        send({'id':ident,'result':result}); return
    name=args['name']; args=args['arguments']
    if name=='env':
        send({'id':ident,'result':{'content':[{'type':'text','text':os.environ.get('MCP_TEST_POLLUTION','clean')}]}}); return
    if name=='invalid_structured':
        send({'id':ident,'result':{'content':[],'structuredContent':[1,2]}}); return
    if name=='crash': os._exit(1)
    if name=='noise':
        for _ in range(100):
            send({'method':'notifications/message','params':{'level':'info','data':'progress'}}); time.sleep(.01)
    time.sleep(args.get('delay',0))
    if name=='rpc_error':
        send({'id':ident,'error':{'code':args.get('code',-32602),'message':'bad args','data':{'field':'q'}}})
        if args.get('close'): os._exit(0)
        return
    content=[{'type':'text','text':args.get('text','ok')}]
    if name=='image': content.append({'type':'image','mimeType':'image/png','data':'iVBORw0KGgo='})
    if name=='large_image': content.append({'type':'image','mimeType':'image/png','data':'AAAA'*1600000})
    send({'id':ident,'result':{'content':content,'isError':name=='tool_error'}})
for line in sys.stdin:
    request=json.loads(line)
    if 'id' in request:
        threading.Thread(target=respond,args=(request,),daemon=True).start()
"""


@pytest.fixture
async def client(tmp_path):
    script = tmp_path / "server.py"
    script.write_text(_SERVER, encoding="utf-8")
    result = client_for("test", [sys.executable, "-u", str(script)])
    result.discovered = await result.connect()
    yield result
    await result.disconnect()


async def test_stdio_discovery_text_images_and_out_of_order_replies(client):
    assert [tool.name for tool in client.discovered] == ["echo", "image"]
    first, second = await asyncio.gather(
        client.call("echo", {"text": "first", "delay": 0.1}),
        client.call("echo", {"text": "second"}),
    )
    assert (first, second) == ("first", "second")
    result = await client.call("image", {})
    assert isinstance(result, ToolResult)
    assert result.text == "ok"
    assert result.content_blocks == [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
        }
    ]


async def test_image_larger_than_previous_stream_limit(client):
    result = await client.call("large_image", {})
    assert isinstance(result, ToolResult)
    assert len(result.content_blocks[0]["image_url"]["url"]) > 4 * 1024 * 1024


@pytest.mark.parametrize("name", ["rpc_error", "tool_error"])
async def test_remote_failure_is_not_a_success(client, name):
    with pytest.raises(McpToolError) as error:
        await client.call(name, {"text": "operation failed"})
    assert error.value.server == "test"
    if name == "rpc_error":
        assert error.value.code == -32602
        assert error.value.data == {"field": "q"}
    assert await client.call("echo", {}) == "ok"


async def test_timeout_and_cancel_discard_late_responses(client):
    with pytest.raises(TimeoutError, match="超时"):
        await client.call("echo", {"delay": 0.15, "text": "expired"}, timeout=0.02)
    pending = asyncio.create_task(
        client.call("echo", {"delay": 0.15, "text": "cancelled"})
    )
    await asyncio.sleep(0.01)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert await client.call("echo", {"delay": 0.2, "text": "current"}) == "current"


async def test_notifications_do_not_extend_request_deadline(client):
    with pytest.raises(TimeoutError, match="超时"):
        await asyncio.wait_for(client.call("noise", {}, timeout=0.05), 0.3)


async def test_process_exit_fails_all_pending_and_future_requests(client):
    pending = asyncio.create_task(client.call("echo", {"delay": 2}))
    with pytest.raises(ConnectionError):
        await client.call("crash", {})
    with pytest.raises(ConnectionError):
        await pending
    with pytest.raises(ConnectionError):
        await client.call("echo", {})


async def test_disconnect_reaps_readers_and_rejects_old_tools(client):
    pending = asyncio.create_task(client.call("echo", {"delay": 2}))
    await asyncio.sleep(0.02)
    await client.disconnect()
    with pytest.raises(ConnectionError):
        await pending
    assert client._owner.done()
    assert client.test_processes.process.returncode is not None
    assert not [
        task for task in asyncio.all_tasks() if task.get_name().startswith("mcp-pipe:")
    ]
    with pytest.raises(ConnectionError):
        await client.call("echo", {})


async def test_initialize_error_reclaims_process(tmp_path):
    script = tmp_path / "server.py"
    script.write_text(_SERVER, encoding="utf-8")
    client = client_for("bad", [sys.executable, str(script)], env={"FAIL_INIT": "1"})
    with pytest.raises(McpProtocolError):
        await client.connect()
    assert client.test_processes.process.returncode is not None
    assert client._owner.done()


async def test_disconnect_cleans_tasks_even_when_process_wait_fails(
    client, monkeypatch
):
    process = client.test_processes.process
    original_wait = process.wait
    monkeypatch.setattr(
        process, "wait", AsyncMock(side_effect=[TimeoutError(), TimeoutError()])
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        await client.disconnect()
    assert not [
        task for task in asyncio.all_tasks() if task.get_name().startswith("mcp-pipe:")
    ]
    await original_wait()
    client._cleanup_error = None


async def test_stderr_invalid_bytes_are_drained_without_secret_logs(tmp_path, caplog):
    script = tmp_path / "server.py"
    script.write_text(
        "import sys\nsys.stderr.buffer.write(b'\\xff\\xfe stderr-secret')\nsys.stderr.flush()\n"
        + _SERVER,
        encoding="utf-8",
    )
    client = client_for("stderr", [sys.executable, str(script)])
    with caplog.at_level(logging.DEBUG):
        try:
            await client.connect()
            assert await client.call("echo", {}) == "ok"
        finally:
            await client.disconnect()
    assert "MCP stderr" in caplog.text
    assert "stderr-secret" not in caplog.text


def test_inferred_cwd(tmp_path):
    script = tmp_path / "server.py"
    script.write_text("", encoding="utf-8")
    assert _infer_cwd(["python", str(script)]) == str(tmp_path)
    assert _infer_cwd([str(script)]) == str(tmp_path)
    assert _infer_cwd(["python", "relative.py"]) == __import__("os").getcwd()


async def test_complete_environment_does_not_restore_filtered_values(
    tmp_path, monkeypatch
):
    import os

    monkeypatch.setenv("MCP_TEST_POLLUTION", "must-not-inherit")
    script = tmp_path / "server.py"
    script.write_text(_SERVER, encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items() if key != "MCP_TEST_POLLUTION"
    }
    client = client_for(
        "isolated", [sys.executable, str(script)], env=env, inherit_env=False
    )
    try:
        await client.connect()
        assert await client.call("env", {}) == "clean"
    finally:
        await client.disconnect()


async def test_owner_failure_still_reaps_process_and_protocol_tasks(client):
    client.test_processes.owner.fail = True
    with pytest.raises(RuntimeError, match="cleanup"):
        await client.disconnect()
    assert client.test_processes.process.returncode is not None
    assert client._owner.done()
    assert not [
        task for task in asyncio.all_tasks() if task.get_name().startswith("mcp-pipe:")
    ]
    client._cleanup_error = None


@pytest.mark.parametrize("cancel", [False, True])
async def test_backpressure_cannot_block_timeout_or_cancellation(tmp_path, cancel):
    script = tmp_path / "blocked_stdin.py"
    script.write_text(
        """import json,sys,time
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    method=request['method']
    if method=='server/discover':
        print(json.dumps({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'legacy'}}),flush=True);continue
    result={'tools':[]} if method=='tools/list' else {'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'peer','version':'1'}}
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
    if request['method']=='tools/list':
        time.sleep(30)
""",
        encoding="utf-8",
    )
    client = client_for("backpressure", [sys.executable, str(script)])
    try:
        await client.connect()
        pending = asyncio.create_task(
            client.call(
                "echo", {"text": "x" * 4000000}, timeout=0.05 if not cancel else 10
            )
        )
        if cancel:
            await asyncio.sleep(0.02)
            pending.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await asyncio.wait_for(pending, 8)
    finally:
        await client.disconnect()


async def test_stdio_nonobject_structured_result_remains_a_protocol_failure(client):
    with pytest.raises(McpProtocolError):
        await client.call("invalid_structured", {})
    assert await client.call("echo", {}) == "ok"


async def test_connect_cancellation_reaps_the_started_child(tmp_path):
    script = tmp_path / "silent.py"
    script.write_text("import time; time.sleep(30)", encoding="utf-8")
    client = client_for("cancel-start", [sys.executable, str(script)])
    connecting = asyncio.create_task(client.connect())
    async with asyncio.timeout(3):
        while client.test_processes.process is None:
            await asyncio.sleep(0.01)
    connecting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await connecting
    assert client.test_processes.process.returncode is not None
    assert client._owner.done()


@pytest.mark.parametrize("code", [-32000, -32001])
async def test_remote_reserved_error_codes_keep_business_error_provenance(client, code):
    with pytest.raises(McpToolError) as caught:
        await client.call("rpc_error", {"code": code})
    assert (caught.value.code, caught.value.message, caught.value.data) == (
        code,
        "bad args",
        {"field": "q"},
    )
    assert await client.call("echo", {}) == "ok"
    assert client._observation.calls == {}


async def test_remote_error_before_eof_is_not_mistaken_for_a_retryable_disconnect(
    client,
):
    with pytest.raises(McpToolError) as caught:
        await client.call("rpc_error", {"code": -32000, "close": True})
    assert caught.value.message == "bad args"
    assert caught.value.data == {"field": "q"}
    with pytest.raises(ConnectionError):
        await client.call("echo", {})
    assert client._observation.calls == {}
