"""One bounded loopback callback, owned by an explicit login operation."""

import asyncio
from contextlib import suppress
from urllib.parse import parse_qs, urlsplit

from mcp.shared.auth import AuthorizationCodeResult
from .models import LoginRequired


class OAuthCallback:
    """Bind IPv4 loopback only; SDK validates state, issuer and PKCE."""

    def __init__(self, port: int):
        self.port = port
        self.result: asyncio.Future[AuthorizationCodeResult] = (
            asyncio.get_running_loop().create_future()
        )
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Acquire the stable registered URI before asking a browser to visit it."""
        self.server = await asyncio.start_server(
            self._accept, "127.0.0.1", self.port, limit=16384
        )

    def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.create_task(self._handle(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            async with asyncio.timeout(5):
                request = (await reader.readuntil(b"\r\n\r\n")).decode("ascii")
                method, target, _ = request.split("\r\n", 1)[0].split()
                parsed = urlsplit(target)
                if method != "GET" or parsed.path != "/callback" or self.result.done():
                    response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                else:
                    query = parse_qs(parsed.query)

                    def value(name: str) -> str | None:
                        values = query.get(name, [])
                        return values[0] if len(values) == 1 else None

                    if value("error"):
                        self.result.set_exception(LoginRequired())
                    else:
                        self.result.set_result(
                            AuthorizationCodeResult(
                                code=value("code") or "",
                                state=value("state"),
                                iss=value("iss"),
                            )
                        )
                    body = b"You may close this window and return to Shiori."
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: "
                        + str(len(body)).encode()
                        + b"\r\n\r\n"
                        + body
                    )
                writer.write(response)
                await writer.drain()
        except (
            ValueError,
            OSError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    async def wait(self) -> AuthorizationCodeResult:
        """Bound human interaction as well as partial HTTP requests."""
        return await asyncio.wait_for(asyncio.shield(self.result), 180)

    async def close(self) -> None:
        """Always dispose listener and accepted requests, even after cancellation."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if not self.result.done():
            self.result.cancel()
        elif not self.result.cancelled():
            self.result.exception()
