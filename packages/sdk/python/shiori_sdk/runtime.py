"""Granted runtime interfaces; the SDK never creates host services or storage."""

from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Protocol, cast

from .kernel import Key, Veto
from .kernel.events import OnHandler, WatchHandler

type Dispose = Callable[[], Awaitable[None] | None]
type EventHandler[EventT] = Callable[[EventT], Awaitable[EventT | None] | EventT | None]


class CapabilityNotGranted(AttributeError):
    """The plugin tried to access a capability absent from its manifest."""


class HostServiceUnavailable(RuntimeError):
    """The manifest declared a capability, but the host lacks the service behind it.

    Distinct from ``CapabilityNotGranted``: the plugin asked correctly and the host
    is misassembled. The host raises it before calling ``setup`` and names the
    missing service. Deliberately not an ``AttributeError`` so ``getattr`` defaults
    and ``__getattr__`` fallbacks can never swallow it.
    """

    @classmethod
    def for_capability(
        cls, plugin_id: str, capability: str, services: Iterable[str]
    ) -> "HostServiceUnavailable":
        """Builds the shared message naming the declared capability and its services."""
        return cls(
            f"插件 {plugin_id} 声明了 capability {capability!r}，"
            f"但宿主未提供服务 {'、'.join(services)}"
        )


# manifest 只能声明这里列出的宿主能力；宿主 manifest 解析与 SDK 测试替身共用这一份。
KNOWN_CAPABILITIES = frozenset(
    {
        "services",
        "tools",
        "channels",
        "accounts",
        # 渠道发送者与群的头像缓存（#514）
        "avatars",
        # 插件为角色提交外部上下文回合（#721）
        "external_turns",
        "background_results",
        "process_resources",
        "events",
        "scene_observations",
        "kv",
        "config",
        "background",
        "diagnostics",
        "storage",
        "roles",
        "models",
        "sessions",
        "http",
        "resources",
        "processes",
        "tool_turn",
        "rpc",
        "dependencies",
        "runtime",
        # 直传宿主服务引用，供渠道/事件/记忆壳插件读取（#183）；这些字段没有
        # 装配/回滚语义，宿主直接透传同名服务，不各建 Capability 类。
        "workspace",
        "memory_engine",
        "memory",
        "session_manager",
        "light_provider",
        "light_model",
    }
)


def require_known_capabilities(names: Iterable[str], source: object) -> None:
    """Rejects capability names outside ``KNOWN_CAPABILITIES`` as the host does."""
    unknown = [name for name in names if name not in KNOWN_CAPABILITIES]
    if unknown:
        raise ValueError(f"manifest 声明了未知 capability {unknown}: {source}")


def parse_capabilities(value: object, source: object) -> tuple[str, ...]:
    """Validates a manifest ``capabilities`` value exactly as the host does.

    ``source`` names the manifest in messages. Raises ``ValueError`` when the list
    is missing, not a list, or names a capability outside ``KNOWN_CAPABILITIES``.
    """
    if value is None:
        raise ValueError(f"v2 manifest 缺少 capabilities 声明: {source}")
    if not isinstance(value, list):
        raise ValueError(f"capabilities 必须是列表: {source}")
    names = tuple(str(item) for item in cast(list[object], value))
    require_known_capabilities(names, source)
    return names


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
    """Public setup context. Undeclared capabilities raise CapabilityNotGranted.

    ``provide`` / ``require`` / ``get`` and ``on`` / ``watch`` / ``emit`` are the
    kernel ``Context`` members of the same names (``shiori_sdk.kernel``):
    service keys come from manifest ``provides`` / ``inject`` /
    ``optional_inject``, events from ``shiori_sdk.core``.
    """

    @property
    def plugin_id(self) -> str: ...

    @property
    def plugin_dir(self) -> Path: ...

    @property
    def granted(self) -> tuple[str, ...]: ...

    @property
    def events(self) -> EventsCapability: ...

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
