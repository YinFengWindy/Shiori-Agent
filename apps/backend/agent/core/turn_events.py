"""Emission of the core's turn events through the plugin kernel (#902).

Each turn stage projects its host frame into a ``shiori_sdk.core.conversation``
event and emits it through ``TurnEvents``: the generation's kernel runs the
plugins' ``on`` chain, the core checks and the watchers; the stage applies the
writable fields of the final event back to its frame, then the final event
fans out on the core event bus to core listeners (scene, progress reporting).
A turn without plugins emits through a bare kernel holding only the core
checks, so it passes them too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import cast

from bus.event_bus import EventBus
from shiori_sdk.kernel import Kernel, Veto


def install_core_checks(kernel: Kernel) -> None:
    """Adds the core's fixed post-chain checks to ``kernel`` (D11, §8.1).

    Every kernel the core emits through gets them: each plugin generation's
    (``PluginKernel``) and the bare one of a turn without plugins
    (``core_kernel``). P3-3 adds the minimal shell check on ``ToolCalling``,
    P3-4 the citation cleanup on ``ReasoningFinished``.
    """
    _ = kernel


def core_kernel() -> Kernel:
    """A kernel without plugins that runs only the core checks."""
    kernel = Kernel()
    install_core_checks(kernel)
    return kernel


class TurnEvents:
    """The event outlet of the turn stages: the current kernel, then the core bus.

    ``kernel`` returns the kernel to emit through and is read on every emit,
    so binding another plugin generation takes effect on the next stage; a
    turn without plugins passes ``core_kernel``-backed kernels. ``bus`` only
    receives the final events for core listeners.
    """

    def __init__(self, bus: EventBus, kernel: Callable[[], Kernel]) -> None:
        self._bus = bus
        self._kernel = kernel

    async def emit[E](
        self,
        event: E,
        apply: Callable[[E], None],
        vetoed: Callable[[Veto], None] | None = None,
    ) -> None:
        """Emits ``event``, applies the final one and fans it out to the core bus.

        ``apply`` writes the final event's writable fields back to the stage's
        frame. A veto reaches ``vetoed`` and fans nothing out; a stage that
        cannot stop passes no ``vetoed`` and a veto fails the turn.
        """
        result = await self._kernel().emit(event)
        if isinstance(result, Veto):
            if vetoed is None:
                name = type(event).__name__
                raise RuntimeError(f"{name} 不可否决，插件却否决了它: {result.reason}")
            vetoed(result)
            return
        apply(result)
        await self._bus.fanout(result)


def read_only[K, V](mapping: Mapping[K, V]) -> MappingProxyType[K, V]:
    """A read-only copy of ``mapping`` for an event field."""
    return MappingProxyType(dict(mapping))


def freeze_top_level(value: object) -> object:
    """``value`` for an event field of open type: a top-level container frozen.

    A dict becomes a read-only copy, a list a tuple and a set a frozenset;
    anything else passes as it is.
    """
    if isinstance(value, dict):
        return read_only(cast(dict[object, object], value))
    if isinstance(value, list):
        return tuple(cast(list[object], value))
    if isinstance(value, set):
        return frozenset(cast(set[object], value))
    return value
