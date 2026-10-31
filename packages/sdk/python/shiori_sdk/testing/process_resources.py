"""Explicit process resources for isolated plugin tests, without host generations."""

from collections.abc import Callable
from typing import cast

from shiori_sdk.process_resources import ProcessResource


class FakeProcessResources:
    """Tests control publication through active; resources close with this fixture."""

    def __init__(self, *, active: bool = True) -> None:
        self.active = active
        self.resources: dict[str, ProcessResource] = {}
        self._published: dict[object, Callable[[], None]] = {}

    def acquire[T: ProcessResource](self, key: str, factory: Callable[[], T]) -> T:
        """Reuse one resource for an explicitly versioned plugin contract."""
        if key not in self.resources:
            self.resources[key] = factory()
        return cast(T, self.resources[key])

    def on_published(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Run ``callback`` now when active, else at the next ``publish``."""
        if self.active:
            callback()
            return lambda: None
        token = object()
        self._published[token] = callback

        def dispose() -> None:
            self._published.pop(token, None)

        return dispose

    def publish(self) -> None:
        """Mark the fixture's generation published and run waiting callbacks."""
        self.active = True
        callbacks = tuple(self._published.values())
        self._published.clear()
        for callback in callbacks:
            callback()

    async def close(self) -> None:
        """Stop every owned resource and prevent further active calls."""
        self.active = False
        self._published.clear()
        for resource in self.resources.values():
            await resource.close()
