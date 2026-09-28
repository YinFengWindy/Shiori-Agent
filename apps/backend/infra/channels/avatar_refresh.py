"""Background avatar refreshes for multi-account channel plugins."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class AvatarRefreshTasks:
    """Runs at most one background avatar fetch per account key.

    ``fetch`` is the plugin's network boundary: it returns the avatar data URI,
    "" for none, or None when it could not be fetched (keep the stored one).
    Only a fetched value reaches ``apply``, which stores and registers it.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(
        self,
        key: str,
        fetch: Callable[[], Awaitable[str | None]],
        apply: Callable[[str], None],
    ) -> None:
        """Starts a refresh for ``key`` unless one is already running."""
        running = self._tasks.get(key)
        if running is not None and not running.done():
            return
        self._tasks[key] = asyncio.create_task(
            self._run(fetch, apply), name=f"avatar-refresh-{key}"
        )

    @staticmethod
    async def _run(
        fetch: Callable[[], Awaitable[str | None]], apply: Callable[[str], None]
    ) -> None:
        avatar = await fetch()
        if avatar is not None:
            apply(avatar)

    async def wait(self) -> None:
        """Waits for every running refresh; a failing ``apply`` raises here."""
        await asyncio.gather(*self._tasks.values())

    async def cancel(self, key: str) -> None:
        """Stops one account's refresh, e.g. before it is deleted."""
        task = self._tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        """Stops every refresh when the plugin's channel stops."""
        for key in list(self._tasks):
            await self.cancel(key)
