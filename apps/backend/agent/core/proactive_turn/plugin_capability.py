"""The ``proactive_gates`` plugin capability (#901 P2; deleted in P3, D19).

``PluginProactiveGates`` is the ``host.proactive_gates`` core service: each
plugin's gates, read back for the active plugins in kernel order on every
proactive tick.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.core.proactive_turn.gates import ProactiveGate
from agent.plugin_host.capabilities import ContributionsByPlugin, contribute_to_list
from agent.plugin_host.core_keys import HOST_PROACTIVE_GATES, PluginBinding

if TYPE_CHECKING:
    from agent.plugin_host import PluginKernel


class PluginProactiveGates(ContributionsByPlugin[ProactiveGate]):
    """The ``host.proactive_gates`` core service of one plugin kernel generation."""

    def for_plugin(self, binding: PluginBinding) -> ProactiveGatesCapability:
        """The proactive gates capability of the plugin ``binding`` describes."""
        return ProactiveGatesCapability(self.of(binding.plugin_id), binding)


def active_plugin_proactive_gates(kernel: PluginKernel) -> list[ProactiveGate]:
    """The gates the generation's active plugins contributed, in kernel order."""
    source = kernel.core_service(HOST_PROACTIVE_GATES)
    return list(source.active(kernel.active_plugin_ids))


class ProactiveGatesCapability:
    """贡献参与主动 tick 准入的 gate；不允许直接投递消息。"""

    def __init__(self, gates: list[ProactiveGate], binding: PluginBinding) -> None:
        self._gates = gates
        self._effects = binding.scope

    def add(self, gate: ProactiveGate) -> None:
        """Joins ``gate`` to the proactive tick admission until the plugin stops."""
        contribute_to_list(
            self._gates,
            gate,
            effects=self._effects,
            label=f"proactive_gate:{getattr(gate, 'name', gate)}",
        )
