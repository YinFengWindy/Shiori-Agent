"""Observe transport provenance without taking over the SDK's request dispatch."""

from contextvars import ContextVar
from dataclasses import dataclass, field

import anyio
from mcp.client._transport import ReadStream, WriteStream, TransportStreams
from mcp.shared.message import SessionMessage
from mcp_types import JSONRPCError, JSONRPCRequest


@dataclass
class CallObservation:
    """A call's error response takes precedence over a subsequent pipe closure."""

    received_error: bool = False
    ids: set[str] = field(default_factory=set)


CURRENT_CALL: ContextVar[CallObservation | None] = ContextVar(
    "shiori_mcp_call_observation", default=None
)


class TransportObservation:
    """Track local closure and error delivery; the SDK still correlates all results."""

    def __init__(self):
        self.failed = False
        self.calls: dict[str, CallObservation] = {}

    def streams(self, streams: TransportStreams) -> TransportStreams:
        return _Read(streams[0], self), _Write(streams[1], self)

    def release(self, call: CallObservation) -> None:
        for key in call.ids:
            self.calls.pop(key, None)


class _Read:
    def __init__(
        self,
        stream: ReadStream[SessionMessage | Exception],
        owner: TransportObservation,
    ):
        self.stream, self.owner = stream, owner

    @property
    def last_context(self):
        # Streamable HTTP carries the sender's context through this documented
        # stream attribute. Dropping it loses per-call auth/status diagnostics.
        return getattr(self.stream, "last_context", None)

    async def receive(self) -> SessionMessage | Exception:
        try:
            item = await self.stream.receive()
        except (
            anyio.EndOfStream,
            anyio.ClosedResourceError,
            anyio.BrokenResourceError,
            OSError,
        ):
            self.owner.failed = True
            raise
        if isinstance(item, Exception):
            self.owner.failed = True
        elif isinstance(item.message, JSONRPCError):
            call = self.owner.calls.get(str(item.message.id))
            if call is not None:
                # HTTP may synthesize a JSONRPCError for an abandoned request.
                # Its origin is unproven, so it must never authorize replay.
                call.received_error = True
        return item

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None

    async def aclose(self):
        await self.stream.aclose()

    async def __aenter__(self):
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.stream.__aexit__(exc_type, exc_val, exc_tb)


class _Write:
    def __init__(
        self, stream: WriteStream[SessionMessage], owner: TransportObservation
    ):
        self.stream, self.owner = stream, owner

    async def send(self, item: SessionMessage, /) -> None:
        call = CURRENT_CALL.get()
        message = item.message
        if (
            call is not None
            and isinstance(message, JSONRPCRequest)
            and message.method == "tools/call"
        ):
            key = str(message.id)
            call.ids.add(key)
            self.owner.calls[key] = call
        try:
            await self.stream.send(item)
        except (anyio.ClosedResourceError, anyio.BrokenResourceError, OSError):
            self.owner.failed = True
            raise

    async def aclose(self):
        await self.stream.aclose()

    async def __aenter__(self):
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.stream.__aexit__(exc_type, exc_val, exc_tb)
