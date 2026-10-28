"""Granted runtime interfaces; the SDK never creates host services or storage."""

from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Protocol, cast

from .kernel import Key, Veto
from .kernel.events import OnHandler, WatchHandler

type Dispose = Callable[[], Awaitable[None] | None]
type EventHandler[EventT] = Callable[[EventT], Awaitable[EventT | None] | EventT | None]


class HostServiceUnavailable(RuntimeError):
    """The manifest asked for a service the host did not assemble.

    Raised while building that plugin's setup context, and the message names
    the missing service. Deliberately not an ``AttributeError`` so ``getattr``
    defaults can never swallow it.
    """

    @classmethod
    def for_capability(
        cls, plugin_id: str, capability: str, services: Iterable[str]
    ) -> "HostServiceUnavailable":
        """Builds the shared message naming the declared service and what is missing."""
        return cls(
            f"插件 {plugin_id} 声明了 capability {capability!r}，"
            f"但宿主未提供服务 {'、'.join(services)}"
        )


def parse_capabilities(value: object, source: object) -> tuple[str, ...]:
    """Validates an api: 2 manifest ``capabilities`` list.

    ``source`` names the manifest in messages. Raises ``ValueError`` when the
    list is missing or not a list. Names are not a grant: plugins take services
    with ``ctx.require``. P4-5 is what rejects a non-``api: 4`` package.
    """
    if value is None:
        raise ValueError(f"v2 manifest 缺少 capabilities 声明: {source}")
    if not isinstance(value, list):
        raise ValueError(f"capabilities 必须是列表: {source}")
    return tuple(str(item) for item in cast(list[object], value))


class EventsCapability(Protocol):
    """Scoped typed subscriptions and sequential event dispatch."""

    def on[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None: ...

    def off[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None: ...

    async def emit[EventT](self, event: EventT) -> EventT: ...


class PluginRuntimeContext(Protocol):
    """Public setup context.

    ``provide`` / ``require`` / ``get`` and ``on`` / ``watch`` / ``emit`` are the
    kernel ``Context`` members of the same names (``shiori_sdk.kernel``):
    service keys come from manifest ``provides`` / ``inject`` /
    ``optional_inject``. ``effect`` takes a label the host records with the
    disposer.
    """

    @property
    def plugin_id(self) -> str: ...

    @property
    def plugin_dir(self) -> Path: ...

    def expose(self, api: object) -> None: ...

    def effect(self, label: str, dispose: Dispose) -> None: ...

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes ``impl`` under a key declared in manifest ``provides``."""
        ...

    def require[T](self, key: Key[T]) -> T:
        """The current provider of a key declared in manifest ``inject``."""
        ...

    def get[T](self, key: Key[T]) -> T | None:
        """The current provider of a key declared in ``optional_inject``, or None."""
        ...

    def on[E](self, event_type: type[E], handler: OnHandler[E]) -> None:
        """Joins the ordered chain; return the (replaced) event or ``Veto``."""
        ...

    def watch[E](self, event_type: type[E], handler: WatchHandler[E]) -> None:
        """Listens read-only to the final event, serially, without delaying emit."""
        ...

    async def emit[E](self, event: E) -> E | Veto:
        """Emits through the kernel: ``on`` chain, core checks, then watchers."""
        ...
