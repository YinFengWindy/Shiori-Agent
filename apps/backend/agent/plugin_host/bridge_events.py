"""Namespaced plugin events and failures transported by the desktop boundary."""

from dataclasses import dataclass
from typing import Any


@dataclass
class PluginBridgeEvent:
    """One plugin-owned event, forwarded without domain-specific host routing."""

    method: str
    payload: dict[str, Any]
    registry: object
    dispatched: bool = False
