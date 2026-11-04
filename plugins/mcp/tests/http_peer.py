"""A real loopback MCP peer with controllable wire failures and response framing."""

import asyncio
import json
from collections import Counter
from contextlib import suppress


class HttpPeer:
    """Serve JSON/SSE over actual sockets; count tool calls to detect replay."""

    def __init__(self, *, sse=False, modern=False):
        self.sse, self.modern = sse, modern
        self.status = 200
        self.calls = Counter()
        self.requests = []
        self.tasks = set()
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.names = [
            "echo",
            "image",
            "structured",
            "rpc_error",
            "tool_error",
            "wait",
            "drop",
            "json_list",
            "json_scalar",
            "json_null",
        ]

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/mcp?filter=read&key=query-canary"
        return self

    async def __aexit__(self, *_args):
        self.server.close()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        await self.server.wait_closed()

    def _accept(self, reader, writer):
        task = asyncio.create_task(self._handle(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _handle(self, reader, writer):
        try:
            first = (await reader.readline()).decode().split()
            if not first:
                return
            method, target, _version = first
            headers = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                name, value = line.decode().split(":", 1)
                headers[name.lower()] = value.strip()
            body = await reader.readexactly(int(headers.get("content-length", 0)))
            self.requests.append((method, target, headers))
            if self.status != 200:
                await self._reply(
                    writer, self.status, b"private-bearer private-header query-canary"
                )
                return
            if method != "POST":
                await self._reply(writer, 200 if method == "DELETE" else 405, b"")
                return
            request = json.loads(body)
            if "id" not in request:
                await self._reply(writer, 202, b"")
                return
            result = await self._rpc(request)
            if result is None:
                return
            envelope = {"jsonrpc": "2.0", "id": request["id"], **result}
            encoded = json.dumps(envelope).encode()
            if self.sse:
                encoded = b"event: message\ndata: " + encoded + b"\n\n"
            await self._reply(writer, 200, encoded, sse=self.sse)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    async def _rpc(self, request):
        method = request["method"]
        params = request.get("params", {})
        if method == "server/discover":
            if not self.modern:
                return {"error": {"code": -32601, "message": "Unknown method"}}
            return {
                "result": {
                    "supportedVersions": ["2026-07-28"],
                    "capabilities": {"tools": {}},
                    "ttlMs": 0,
                    "cacheScope": "private",
                    "resultType": "complete",
                }
            }
        if method == "initialize":
            return {
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            }
        if method == "tools/list":
            names = self.names[2:] if params.get("cursor") else self.names[:2]
            result = {
                "tools": [
                    {
                        "name": name,
                        "description": name,
                        "inputSchema": {"type": "object"},
                    }
                    for name in names
                ]
            }
            if not params.get("cursor"):
                result["nextCursor"] = "next"
            if self.modern:
                result.update(ttlMs=0, cacheScope="private", resultType="complete")
            return {"result": result}
        name = params["name"]
        self.calls[name] += 1
        if name == "drop":
            return None
        if name == "wait":
            self.waiting.set()
            await self.release.wait()
        if name == "rpc_error":
            return {"error": {"code": -32042, "message": "private-bearer"}}
        result = {
            "content": [{"type": "text", "text": "hello"}],
            "isError": name == "tool_error",
        }
        if name == "image":
            result["content"] = [
                {"type": "image", "mimeType": "image/png", "data": "aGVsbG8="}
            ]
        if name == "structured":
            result["structuredContent"] = {"records": [1, 2]}
        if name == "tool_error":
            result["content"] = [
                {"type": "text", "text": "private-bearer private-header query-canary"}
            ]
        if name.startswith("json_"):
            value = {"json_list": [1, 2], "json_scalar": 42, "json_null": None}[name]
            result["structuredContent"] = value
            result["content"] = (
                [{"type": "text", "text": json.dumps(value)}]
                if name == "json_list"
                else []
            )
        if self.modern:
            result["resultType"] = "complete"
        return {"result": result}

    async def _reply(self, writer, status, body, *, sse=False):
        content_type = "text/event-stream" if sse else "application/json"
        response = (
            f"HTTP/1.1 {status} Response\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\nConnection: close\r\nMcp-Session-Id: fixture-session\r\n\r\n".encode()
            + body
        )
        writer.write(response)
        await writer.drain()
