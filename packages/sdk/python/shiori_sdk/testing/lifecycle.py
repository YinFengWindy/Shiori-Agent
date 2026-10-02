"""Inspectable lifecycle registrations for tests of a plugin's own modules."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from shiori_sdk.lifecycle import LifecycleModule, require_phase_slot


@dataclass
class FakeFrame:
    """Shared slots for running a plugin module without constructing a host phase."""

    slots: dict[str, object] = field(default_factory=dict)


class FakeLifecycle:
    """Records contributions; host phase ordering remains covered by host tests."""

    def __init__(self) -> None:
        self.modules: dict[str, list[LifecycleModule]] = {}
        self._closed = False

    def contribute(self, slot: str, modules: Sequence[LifecycleModule]) -> None:
        """Adds modules in registration order; unknown phase slots fail like the host."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        require_phase_slot(slot)
        self.modules.setdefault(slot, []).extend(modules)

    def close(self) -> None:
        """Withdraws every contribution when the fake scope closes."""
        self._closed = True
        self.modules.clear()
