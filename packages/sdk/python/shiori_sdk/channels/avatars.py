"""Host-injected sender and chat avatar caching."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

type AvatarFetch = Callable[[], Awaitable[bytes | None]]


class AvatarsCapability(Protocol):
    """Schedule due avatar refreshes; the host owns validation, storage and cancellation."""

    def refresh(
        self, kind: str, channel: str, subject_id: str, fetch: AvatarFetch
    ) -> asyncio.Task[None] | None: ...
