"""In-memory event subscriptions with typed handlers and no host bus."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shiori_sdk.runtime import EventHandler


@dataclass
class _Subscription:
    event_type: type
    handler: object
    dispatch: Callable[[object], Awaitable[object]]


class FakeEvents:
    """Dispatches matching handlers sequentially, preserving replacement semantics."""

    def __init__(self) -> None:
        self._subscriptions: list[_Subscription] = []
        self._closed = False
        self._pending: list[asyncio.Task[None]] = []

    def on[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None:
        """Registers one typed handler."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")

        async def dispatch(event: object) -> object:
            if not isinstance(event, event_type):
                return event
            result = handler(event)
            if inspect.isawaitable(result):
                result = await result
            return event if result is None else result

        self._subscriptions.append(_Subscription(event_type, handler, dispatch))

    def off[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None:
        """Removes matching subscriptions, including duplicate registrations."""
        self._subscriptions[:] = [
            entry
            for entry in self._subscriptions
            if entry.event_type is not event_type or entry.handler is not handler
        ]

    async def emit[EventT](self, event: EventT) -> EventT:
        """Runs matching handlers and rejects an incompatible replacement value."""
        current = event
        for entry in tuple(self._subscriptions):
            if entry in self._subscriptions and type(event) is entry.event_type:
                result = await entry.dispatch(current)
                if not isinstance(result, type(event)):
                    raise TypeError("Event handlers must preserve the event type")
                current = result
        return current

    def close(self) -> None:
        """Unsubscribes the fake scope before custom cleanup runs."""
        self._closed = True
        self._subscriptions.clear()

    def enqueue(self, event: object) -> None:
        """Queues observation for tests that exercise post-response dispatch."""
        self._pending.append(asyncio.create_task(self.fanout(event)))

    async def fanout(self, event: object) -> None:
        """Runs fake observers deterministically."""
        for entry in tuple(self._subscriptions):
            if type(event) is entry.event_type:
                await entry.dispatch(event)

    async def drain(self) -> None:
        """Awaits queued observations."""
        while self._pending:
            pending, self._pending = self._pending, []
            await asyncio.gather(*pending)

    async def aclose(self) -> None:
        """Finishes observations before dropping subscriptions."""
        await self.drain()
        self.close()
