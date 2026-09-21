"""Exercise the stdio transport against a real, concurrent JSON-RPC peer."""

import asyncio
import logging
import sys
from unittest.mock import AsyncMock

import pytest

from agent.mcp.client import McpClient, McpToolError, _infer_cwd
from agent.tools.base import ToolResult

_SERVER = r"""
import json, sys, threading, time, os
lock=threading.Lock()
def send(message):
    with lock:
        print(json.dumps(message), flush=True)
def respond(request):
    ident=request['id']; method=request['method']; args=request.get('params',{})
    if method=='initialize':
        if os.environ.get('FAIL_INIT'):
            send({'id':ident,'error':{'code':-32000,'message':'init failed'}}); return
        send({'id':ident,'result':{}}); return
    if method=='tools/list':
        result={'tools':[{'name':'echo','description':'Echo','inputSchema':{'type':'object'}}]}
        if not args.get('cursor'): result['nextCursor']='second'
        else: result={'tools':[{'name':'image','description':'Image','inputSchema':{'type':'object'}}]}
        send({'id':ident,'result':result}); return
    name=args['name']; args=args['arguments']
    if name=='env':
        send({'id':ident,'result':{'content':[{'type':'text','text':os.environ.get('MCP_TEST_POLLUTION','clean')}]}}); return
    if name=='crash': os._exit(1)
    if name=='noise':
        for _ in range(100):
            send({'method':'notification'}); time.sleep(.01)
    time.sleep(args.get('delay',0))
    if name=='rpc_error':
        send({'id':ident,'error':{'code':-32602,'message':'bad args','data':{'field':'q'}}}); return
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
    result = McpClient("test", [sys.executable, "-u", str(script)])
    await result.connect()
    yield result
    await result.disconnect()


async def test_stdio_discovery_text_images_and_out_of_order_replies(client):
    assert [tool.name for tool in client.tool_infos] == ["echo", "image"]
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
    with pytest.raises(TimeoutError, match="tools/call"):
        await client.call("echo", {"delay": 0.15, "text": "expired"}, timeout=0.02)
    pending = asyncio.create_task(
        client.call("echo", {"delay": 0.15, "text": "cancelled"})
    )
    await asyncio.sleep(0.01)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert await client.call("echo", {"delay": 0.2, "text": "current"}) == "current"
    assert not client._pending


async def test_notifications_do_not_extend_request_deadline(client):
    with pytest.raises(TimeoutError, match="expected_id="):
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
    tasks = (client._reader_task, client._stderr_task)
    pending = asyncio.create_task(client.call("echo", {"delay": 2}))
    await asyncio.sleep(0.02)
    await client.disconnect()
    with pytest.raises(ConnectionError):
        await pending
    assert all(task.done() for task in tasks)
    assert client._reader_task is client._stderr_task is None
    assert client.tool_infos == []
    with pytest.raises(ConnectionError):
        await client.call("echo", {})


async def test_initialize_error_reclaims_process(tmp_path):
    script = tmp_path / "server.py"
    script.write_text(_SERVER, encoding="utf-8")
    client = McpClient("bad", [sys.executable, str(script)], env={"FAIL_INIT": "1"})
    with pytest.raises(McpToolError, match="init failed"):
        await client.connect()
    assert client._process is client._reader_task is client._stderr_task is None


async def test_disconnect_cleans_tasks_even_when_process_wait_fails(
    client, monkeypatch
):
    process = client._process
    assert process is not None
    original_wait = process.wait
    monkeypatch.setattr(
        process, "wait", AsyncMock(side_effect=[TimeoutError(), TimeoutError()])
    )
    with pytest.raises(TimeoutError):
        await client.disconnect()
    assert client._reader_task is client._stderr_task is None
    await original_wait()


async def test_stderr_invalid_bytes_and_failure_are_visible(caplog):
    reader = asyncio.StreamReader()
    reader.feed_data(b"\xff\xfe\nafter\n")
    reader.feed_eof()
    client = McpClient("test", [sys.executable])
    await client._drain_stderr(reader)
    assert list(client._recent_stderr)[-1] == "after"
    reader = asyncio.StreamReader()
    reader.set_exception(OSError("stream closed"))
    with caplog.at_level(logging.WARNING):
        await client._drain_stderr(reader)
    assert "stream closed" in caplog.text


def test_inferred_cwd(tmp_path):
    script = tmp_path / "server.py"
    script.write_text("", encoding="utf-8")
    assert _infer_cwd(["python", str(script)]) == str(tmp_path)
    assert _infer_cwd(["python", "relative.py"]) is None


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
    client = McpClient(
        "isolated", [sys.executable, str(script)], env=env, inherit_env=False
    )
    try:
        await client.connect()
        assert await client.call("env", {}) == "clean"
    finally:
        await client.disconnect()


async def test_job_failure_still_reaps_process_and_protocol_tasks(client):
    from unittest.mock import Mock

    process = client._process
    job = Mock()
    job.close.side_effect = RuntimeError("job close failed")
    client._job = job
    with pytest.raises(RuntimeError, match="job close failed"):
        await client.disconnect()
    assert process.returncode is not None
    assert client._reader_task is client._stderr_task is client._job is None


@pytest.mark.parametrize("cancel", [False, True])
async def test_backpressure_cannot_block_timeout_or_cancellation(tmp_path, cancel):
    script = tmp_path / "blocked_stdin.py"
    script.write_text(
        """import json,sys,time
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    result={'tools':[]} if request['method']=='tools/list' else {}
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
    if request['method']=='tools/list':
        time.sleep(30)
""",
        encoding="utf-8",
    )
    client = McpClient("backpressure", [sys.executable, str(script)])
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
            await asyncio.wait_for(pending, 1)
    finally:
        await client.disconnect()
