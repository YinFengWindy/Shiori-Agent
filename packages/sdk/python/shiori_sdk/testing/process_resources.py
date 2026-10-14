"""Explicit process resources for isolated plugin tests, without host generations."""

from collections.abc import Callable
from typing import cast

from shiori_sdk.process_resources import ProcessResource


class FakeProcessResources:
    """Tests control publication through active; resources close with this fixture."""

    def __init__(self) -> None:
        self.active = True
        self.resources: dict[str, ProcessResource] = {}

    def acquire[T: ProcessResource](self, key: str, factory: Callable[[], T]) -> T:
        """Reuse one resource for an explicitly versioned plugin contract."""
        if key not in self.resources:
            self.resources[key] = factory()
        return cast(T, self.resources[key])

    async def close(self) -> None:
        """Stop every owned resource and prevent further active calls."""
        self.active = False
        for resource in self.resources.values():
            await resource.close()
