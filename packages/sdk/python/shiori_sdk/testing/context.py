"""A pure contract setup context whose host services are explicit test fakes."""

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, cast

from shiori_sdk.kernel import Context, Kernel, Key, PluginSpec, Scope, Veto
from shiori_sdk.kernel.events import OnHandler, WatchHandler
from shiori_sdk.runtime import Dispose
from .events import FakeEvents

_REMOVED_CAPABILITY_ATTRIBUTES = frozenset(
    {
        "accounts",
        "avatars",
        "background",
        "background_results",
        "channels",
        "config",
        "dependencies",
        "events",
        "external_turns",
        "http",
        "kv",
        "light_model",
        "light_provider",
        "memory",
        "models",
        "process_resources",
        "processes",
        "resources",
        "roles",
        "rpc",
        "runtime",
        "scene_observations",
        "services",
        "sessions",
        "storage",
        "tool_turn",
        "tools",
        "workspace",
    }
)
"""Context attributes the host removed in P4-4; plugins take these with ``require``.

``FakePluginContext`` refuses to hold them so a plugin still reading
``ctx.kv`` fails in its own tests exactly as it does in the host.
"""


def _removed_attribute(name: str) -> AttributeError:
    """The error for a removed capability attribute, naming the replacement."""
    return AttributeError(
        f"上下文属性 {name!r} 已删除：插件在 manifest inject 中声明 {name!r} 并用 "
        "ctx.require 取服务；测试用 ctx.serve(KEY, fake) 提供假对象"
    )


class FakePluginContext:
    """Records setup effects and exports without instantiating any host services.

    The kernel members (``provide`` / ``require`` / ``get``, ``on`` / ``watch``
    / ``emit``) run on a real ``Kernel``: ``kernel`` (a fresh one by default)
    with ``inject`` / ``optional_inject`` / ``provides`` as the manifest
    declares them. ``package_dir`` reads those three lists from that package's
    ``manifest.yaml`` instead. Provide core stubs on ``kernel`` before calling
    setup.

    ``require`` / ``get`` reject a key the declaration lacks with the kernel's
    ``undeclared_key`` error, as the host does. A declared key that ``kernel``
    has no provider for is answered by the fake given to ``serve``: the host
    builds those services per plugin (``kv``, ``rpc``, ``accounts`` ...).
    ``fake_events`` is served as ``events`` and is closed before the effects
    run, as the host closes a plugin's subscriptions first.

    Attributes named in ``_REMOVED_CAPABILITY_ATTRIBUTES`` can be neither set
    nor read, on this class or a subclass: the host context has none of them.
    """

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if clashes := _REMOVED_CAPABILITY_ATTRIBUTES.intersection(vars(cls)):
            raise TypeError(
                f"{cls.__name__} 定义了已删除的上下文属性 {sorted(clashes)}"
            )

    def __init__(
        self,
        plugin_id: str = "test_plugin",
        plugin_dir: Path = Path("."),
        *,
        kernel: Kernel | None = None,
        inject: tuple[str, ...] = (),
        optional_inject: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
        package_dir: Path | None = None,
    ) -> None:
        if package_dir is not None:
            if inject or optional_inject or provides:
                raise ValueError(
                    "package_dir 与 inject/optional_inject/provides 二选一"
                )
            inject, optional_inject, provides = read_manifest_keys(package_dir)
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.exported: object | None = None
        self.fake_events = FakeEvents()
        self._served: dict[str, object] = {"events": self.fake_events}
        self._effects: list[tuple[str, Dispose]] = []
        self._closed = False
        self.kernel = kernel if kernel is not None else Kernel()
        self._scope = Scope(plugin_id)
        self._inject = frozenset(inject)
        self._optional_inject = frozenset(optional_inject)
        spec = PluginSpec(
            plugin_id,
            _no_setup,
            requires=inject,
            optional=optional_inject,
            provides=provides,
        )
        self._kernel_context = Context(self.kernel, spec, self._scope)

    def __setattr__(self, name: str, value: object) -> None:
        if name in _REMOVED_CAPABILITY_ATTRIBUTES:
            raise _removed_attribute(name)
        super().__setattr__(name, value)

    if not TYPE_CHECKING:
        # Hidden from type checkers so unknown attributes still fail there.

        def __getattr__(self, name: str) -> object:
            if name in _REMOVED_CAPABILITY_ATTRIBUTES:
                raise _removed_attribute(name)
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            )

    def serve[T](self, key: Key[T], fake: T) -> None:
        """Answers ``require`` / ``get`` of a declared, unprovided ``key`` with ``fake``."""
        self._served[key.name] = fake

    def expose(self, api: object) -> None:
        """Records a plugin's public export."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        self.exported = api

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes ``impl`` on ``kernel`` under a declared ``provides`` key."""
        self._kernel_context.provide(key, impl)

    def require[T](self, key: Key[T]) -> T:
        """The provider of a declared ``inject`` key; see the class docstring."""
        if key.name in self._inject and self.kernel.get(key) is None:
            if key.name in self._served:
                return cast(T, self._served[key.name])
        return self._kernel_context.require(key)

    def get[T](self, key: Key[T]) -> T | None:
        """The provider of a declared ``optional_inject`` key, or None."""
        if key.name in self._optional_inject and self.kernel.get(key) is None:
            if key.name in self._served:
                return cast(T, self._served[key.name])
        return self._kernel_context.get(key)

    def on[E](self, event_type: type[E], handler: OnHandler[E]) -> None:
        """Joins ``kernel``'s ordered chain of ``event_type``."""
        self._kernel_context.on(event_type, handler)

    def watch[E](self, event_type: type[E], handler: WatchHandler[E]) -> None:
        """Listens read-only to ``event_type`` on ``kernel``."""
        self._kernel_context.watch(event_type, handler)

    async def emit[E](self, event: E) -> E | Veto:
        """Emits through ``kernel``."""
        return await self._kernel_context.emit(event)

    def effect(self, label: str, dispose: Dispose) -> None:
        """Records custom cleanup in registration order."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        self._effects.append((label, dispose))

    async def aclose(self) -> None:
        """Stops subscriptions, then runs all cleanup in reverse registration order."""
        self._closed = True
        self.fake_events.close()
        errors: list[Exception] = await self._scope.close()
        while self._effects:
            _, dispose = self._effects.pop()
            try:
                result = dispose()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Plugin cleanup failed", errors)


def read_manifest_keys(
    package_dir: Path,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """``inject``, ``optional_inject`` and ``provides`` of a package's manifest."""
    # PyYAML is the testing extra; the bare wheel still imports this module.
    import yaml

    manifest = package_dir / "manifest.yaml"
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"manifest.yaml 格式错误，期望 dict: {manifest}")
    values = cast(dict[str, object], raw)

    def names(field: str) -> tuple[str, ...]:
        value = values.get(field, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in cast(list[object], value)
        ):
            raise ValueError(f"{field} 必须是服务 Key 名称的列表: {manifest}")
        return tuple(cast(list[str], value))

    return names("inject"), names("optional_inject"), names("provides")


async def _no_setup(context: Context) -> None:
    """The fake's spec is never set up by the kernel; setup runs in the test."""
