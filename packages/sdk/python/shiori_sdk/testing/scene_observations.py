"""Explicit role scene-demand fixtures."""

from collections.abc import Callable
from shiori_sdk.roles import RoleView


class FakeSceneObservations:
    """Retain observation predicates as fixture-visible contributions."""

    def __init__(self):
        self.predicates: list[Callable[[RoleView], bool]] = []

    def request(self, predicate: Callable[[RoleView], bool]) -> None:
        """Record demand without starting a scene observer."""
        self.predicates.append(predicate)
