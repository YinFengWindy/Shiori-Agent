"""Granted runtime interfaces; the SDK never creates host services or storage."""

from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Protocol, cast

from .lifecycle import LifecycleCapability

type Dispose = Callable[[], Awaitable[None] | None]
type EventHandler[EventT] = Callable[[EventT], Awaitable[EventT | None] | EventT | None]


class CapabilityNotGranted(AttributeError):
    """The plugin tried to access a capability absent from its manifest."""


# manifest 只能声明这里列出的宿主能力；宿主 manifest 解析与 SDK 测试替身共用这一份。
KNOWN_CAPABILITIES = frozenset(
    {
        "tools",
        "lifecycle",
        "tool_hooks",
        "proactive_gates",
        "channels",
        "accounts",
        # 渠道发送者与群的头像缓存（#514）
        "avatars",
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
        "bot_commands",
        "rpc",
        "dependencies",
        "runtime",
        "role_runtime_registry",
        # 直传宿主服务引用，供渠道/事件/记忆壳插件读取（#183）；这些字段没有
        # 装配/回滚语义，宿主直接透传同名服务，不各建 Capability 类。
        "workspace",
        # 共享宿主那一个 RoleStore 实例：写锁按实例持有，插件自建实例会丢更新。
        "role_store",
        "memory_engine",
        "memory",
        "session_manager",
        "light_provider",
        "light_model",
        "relationship_runtime",
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
    """Public setup context. Undeclared capabilities raise CapabilityNotGranted."""

    @property
    def plugin_id(self) -> str: ...

    @property
    def plugin_dir(self) -> Path: ...

    @property
    def granted(self) -> tuple[str, ...]: ...

    @property
    def lifecycle(self) -> LifecycleCapability: ...

    @property
    def events(self) -> EventsCapability: ...

    def expose(self, api: object) -> None: ...

    def effect(self, label: str, dispose: Dispose) -> None: ...
