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
