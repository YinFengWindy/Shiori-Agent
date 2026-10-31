"""Plugin-owned resources that survive configuration generations in one process."""

from collections.abc import Callable
from typing import Protocol


class ProcessResource(Protocol):
    """Stop monitoring and release local resources; must be safe before first use."""

    async def close(self) -> None: ...


class PluginProcessResources(Protocol):
    """A candidate may attach resources without changing the published generation.

    Keys are plugin-private, versioned contracts (for example ``tasks-v1``).
    Factories must only construct idle resources and must not retain generation
    capabilities. The host closes removed resources after publication, closes
    unused provisional resources on rollback, and closes everything on shutdown.
    Objects are never persisted or reconstructed after application restart.
    """

    @property
    def active(self) -> bool:
        """Whether this attachment belongs to the currently published generation."""
        ...

    def acquire[T: ProcessResource](self, key: str, factory: Callable[[], T]) -> T:
        """Attach to the existing contract or construct it once for this process."""
        ...

    def on_published(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Call ``callback`` once this attachment's generation is published.

        ``active`` is already true when ``callback`` runs. In a generation that
        is already published (an in-generation reload or enable),
        ``callback`` runs before this returns and its exception propagates to
        the caller. Otherwise the host calls it synchronously on the event
        loop while it publishes the generation; there an exception is logged
        and neither publication nor the other callbacks are affected. Each
        callback runs at most once. The returned function cancels a callback
        that has not run; a generation that is discarded or retires unpublished
        drops its callbacks when its attachment closes.
        """
        ...
