"""The ``scene_observations`` plugin capability over the shared demand (#901 P2).

``PluginSceneObservations`` is the ``host.scene_observations`` core service:
each plugin's view registers its observation demand into the generation's one
``SceneObservationDemand`` and revokes it when the plugin stops.
"""

from __future__ import annotations

from collections.abc import Callable

from agent.plugin_host.core_keys import PluginBinding
from core.roles.models import RoleRecord
from core.scene.demand import SceneObservationDemand


class PluginSceneObservations:
    """The ``host.scene_observations`` core service over one demand registry."""

    def __init__(self, demand: SceneObservationDemand) -> None:
        self._demand = demand

    def for_plugin(self, binding: PluginBinding) -> SceneObservationsCapability:
        """The scene observations capability of the plugin ``binding`` describes."""
        return SceneObservationsCapability(self._demand, binding)


class SceneObservationsCapability:
    """Lets a consumer request observations while its plugin effects remain alive."""

    def __init__(self, demand: SceneObservationDemand, binding: PluginBinding) -> None:
        self._demand = demand
        self._effects = binding.scope

    def request(self, predicate: Callable[[RoleRecord], bool]) -> None:
        """Adds one demand and automatically revokes it on unload or setup rollback."""
        dispose = self._demand.register(predicate)
        try:
            _ = self._effects.effect(dispose, "scene_observations")
        except BaseException:
            dispose()
            raise
