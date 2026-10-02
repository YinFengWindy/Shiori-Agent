"""Avatar capability fake records plugin fetches without cache policy or persistence."""

import asyncio

from shiori_sdk.channels.avatars import AvatarFetch


class FakeAvatars:
    """Execute explicitly provided fetches and retain bytes for platform URL assertions."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.images: dict[tuple[str, str, str], bytes | None] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self._errors: list[BaseException] = []

    def refresh(
        self, kind: str, channel: str, subject_id: str, fetch: AvatarFetch
    ) -> asyncio.Task[None]:
        """Run a platform fetch without reproducing the host's cache implementation."""
        key = (kind, channel, subject_id)
        self.calls.append(key)

        async def run():
            self.images[key] = await fetch()

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task[None]) -> None:
        # Release completed task/results immediately, but report every failure at drain/close.
        self.tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            self._errors.append(error)

    async def drain(self) -> None:
        """Observe pending and already-completed failures exactly once."""
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if self._errors:
            errors, self._errors = self._errors, []
            raise BaseExceptionGroup("Avatar fixture downloads failed", errors)

    async def aclose(self) -> None:
        """Cancel and await pending fixture work."""
        pending = tuple(self.tasks)
        for task in pending:
            task.cancel()
        await self.drain()
