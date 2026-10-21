"""A bounded loopback-only HTTP endpoint; h11 owns HTTP framing and validation."""

import asyncio
import hmac
import json
import logging
from contextlib import suppress
from collections.abc import Awaitable, Callable

import h11

from .protocol import CallbackError

MAX_BODY_BYTES = 65536
MAX_CONNECTIONS = 16
REQUEST_TIMEOUT = 10.0
logger = logging.getLogger(__name__)
type Callback = Callable[[str, object], Awaitable[tuple[int, dict[str, object]]]]


class CallbackServer:
    """Serve one role's credential without exposing an unauthenticated router."""

    def __init__(self, connection_id: str, token: str, receive: Callback) -> None:
        self._prefix = f"/v1/connections/{connection_id}/"
        self._token = f"Bearer {token}".encode("ascii")
        self._receive = receive
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.port = 0

    async def start(self, port: int = 0) -> None:
        """Bind only IPv4 loopback, retaining no listener after failed setup."""
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._connected, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    def _connected(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if len(self._tasks) >= MAX_CONNECTIONS:
            writer.close()
            return
        task = asyncio.create_task(self._serve(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        """Close admission and cancel bounded in-flight socket work."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        connection = h11.Connection(h11.SERVER, max_incomplete_event_size=8192)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                operation, body = await self._request(connection, reader)
                status, result = await self._receive(operation, body)
        except CallbackError as error:
            status, result = error.status, {"error": error.reason}
        except (h11.RemoteProtocolError, UnicodeError, json.JSONDecodeError):
            status, result = 400, {"error": "请求格式无效"}
        except TimeoutError:
            status, result = 408, {"error": "请求超时，未确认接收"}
        except (ConnectionError, asyncio.CancelledError):
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            return
        except Exception as error:
            # The channel records its operational error. Never render request
            # bodies, credentials or arbitrary exception text to the caller.
            status, result = 500, {"error": "接收失败，结果未确认"}
            logger.error("Grok callback failed: %s", type(error).__name__)
        try:
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            writer.write(
                connection.send(
                    h11.Response(
                        status_code=status,
                        headers=[
                            (b"Content-Type", b"application/json; charset=utf-8"),
                            (b"Content-Length", str(len(body)).encode("ascii")),
                            (b"Connection", b"close"),
                        ],
                    )
                )
                or b""
            )
            writer.write(connection.send(h11.Data(data=body)) or b"")
            writer.write(connection.send(h11.EndOfMessage()) or b"")
            await writer.drain()
        except (ConnectionError, h11.LocalProtocolError):
            pass  # The client closed before reading its receipt.
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    async def _request(self, connection: h11.Connection, reader: asyncio.StreamReader):
        operation: str | None = None
        body = bytearray()
        while True:
            event = connection.next_event()
            if event is h11.NEED_DATA:
                data = await reader.read(8192)
                if not data:
                    raise CallbackError(400, "请求未完成")
                connection.receive_data(data)
            elif isinstance(event, h11.Request):
                headers = dict(event.headers)
                if event.method != b"POST" or b"origin" in headers:
                    raise CallbackError(405, "仅接受本机客户端 POST")
                if not hmac.compare_digest(
                    headers.get(b"authorization", b""), self._token
                ):
                    raise CallbackError(401, "回程认证失败")
                target = event.target.decode("ascii")
                if not target.startswith(self._prefix):
                    raise CallbackError(404, "连接不存在")
                operation = target.removeprefix(self._prefix)
                if operation not in {"messages", "handshake"}:
                    raise CallbackError(404, "操作不存在")
                if (
                    headers.get(b"content-type", b"").split(b";", 1)[0]
                    != b"application/json"
                ):
                    raise CallbackError(415, "需要 application/json")
            elif isinstance(event, h11.Data):
                body.extend(event.data)
                if len(body) > MAX_BODY_BYTES:
                    raise CallbackError(413, "消息过长")
            elif isinstance(event, h11.EndOfMessage):
                if operation is None:
                    raise CallbackError(400, "缺少请求头")
                return operation, json.loads(body.decode("utf-8"))
            else:
                raise CallbackError(400, "请求格式无效")
