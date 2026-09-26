"""Observe successful Bot polling, including empty update batches."""

from collections.abc import Callable
from typing import Any

from telegram.ext import ExtBot


class ObservedBot(ExtBot):
    """Report successful getUpdates calls to this Bot instance's channel."""

    __slots__ = ("_on_poll_success",)

    def __init__(self, token: str, on_poll_success: Callable[[], None]) -> None:
        super().__init__(token=token)
        self._on_poll_success = on_poll_success

    async def get_updates(self, *args: Any, **kwargs: Any):
        """The Updater may recover on an empty batch with no inbound message."""
        updates = await super().get_updates(*args, **kwargs)
        self._on_poll_success()
        return updates
