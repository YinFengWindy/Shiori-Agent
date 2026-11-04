"""Renderer cleanup the plugin host requests from its owning transport."""

from typing import Literal, Protocol

CommunicationEndReason = Literal[
    "context_disposed", "plugin_disabled", "plugin_reloading"
]
"""Why the plugin host withdraws a renderer owner."""


class RendererCommunication(Protocol):
    """Withdraw renderer registrations when their plugin instance ends."""

    def remove_plugin(
        self, plugin_id: str, *, reason: CommunicationEndReason = "context_disposed"
    ) -> None:
        """Cancel pending calls and remove registrations belonging to the plugin."""
        ...
