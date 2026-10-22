"""Effect-scoped access to the shared core scene observation demand."""

from collections.abc import Callable

from shiori_sdk.kernel import Scope
from core.roles.models import RoleRecord
from core.scene.demand import SceneObservationDemand


class SceneObservationsCapability:
    """Lets a consumer request observations while its plugin effects remain alive."""

    def __init__(self, demand: SceneObservationDemand, effects: Scope) -> None:
        self._demand = demand
        self._effects = effects

    def request(self, predicate: Callable[[RoleRecord], bool]) -> None:
        """Adds one demand and automatically revokes it on unload or setup rollback."""
        dispose = self._demand.register(predicate)
        try:
            _ = self._effects.effect(dispose, "scene_observations")
        except BaseException:
            dispose()
            raise
