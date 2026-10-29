"""插件 setup 上下文：内核 ``Context``，加上本插件才有的对象。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from shiori_sdk.kernel import Context, Key, Scope, Veto
from shiori_sdk.kernel.events import OnHandler, WatchHandler
from shiori_sdk.runtime import Dispose, HostServiceUnavailable
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.core_keys import (
    HostBuilt,
    PER_PLUGIN_PUBLIC_KEYS,
    PluginBinding,
    PluginViewBinder,
)
from agent.plugin_host.kv import PluginKVStore
from shiori_sdk.extensions import ConfigValues, Dependencies, PrivateStorage
from shiori_sdk.plugin_services import RuntimeLifecycle
from shiori_sdk.services import PluginServices
from shiori_sdk.core import services as keys


class PluginRuntimeContext:
    """v2 / api: 4 插件在 setup(ctx) 中拿到的句柄。

    ``provide`` / ``require`` / ``get`` 与 ``on`` / ``watch`` / ``emit`` 转给
    内核。``require`` / ``get`` 在内核结果上展开 per-plugin 视图，并把
    ``HostBuilt`` 换成 setup 时为这个插件建好的对象。服务来自 manifest
    ``inject`` / ``optional_inject``，不再有 capability 属性。
    """

    def __init__(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        manifest: PluginManifest,
        effects: Scope,
        kernel_context: Context,
        binding: PluginBinding,
        publish_api: Callable[[object], None] | None = None,
        config: ConfigValues | None = None,
        dependencies: Dependencies | None = None,
        storage: PrivateStorage | None = None,
        kv: PluginKVStore | None = None,
        runtime: RuntimeLifecycle | None = None,
        services: PluginServices | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.manifest = manifest
        self._effects = effects
        self._kernel_context = kernel_context
        self._binding = binding
        self._publish_api = publish_api
        self._views: dict[str, Any] = {}
        # The objects ``require`` returns for ``HostBuilt``
        # (``core_keys.HOST_BUILT_KEYS``).
        self._host_built: dict[str, Any] = {
            keys.CONFIG.name: config,
            keys.KV.name: kv,
            keys.DEPENDENCIES.name: dependencies,
            keys.RUNTIME.name: runtime,
            keys.SERVICES.name: services,
            keys.STORAGE.name: storage,
        }

    def expose(self, api: object) -> None:
        """Publishes this plugin's API for declared dependents in the same generation."""
        if self._publish_api is None:
            raise RuntimeError("插件导出接口不可用")
        self._publish_api(api)

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes ``impl`` under a key declared in manifest ``provides``."""
        self._kernel_context.provide(key, impl)

    def require[T](self, key: Key[T]) -> T:
        """The current provider of a key declared in manifest ``inject``."""
        return self._present(key.name, self._kernel_context.require(key))

    def get[T](self, key: Key[T]) -> T | None:
        """The current provider of a key declared in ``optional_inject``, or None."""
        value = self._kernel_context.get(key)
        if value is None:
            return None
        return self._present(key.name, value)

    def _present[T](self, name: str, value: T) -> T:
        """The object a plugin calls: a per-plugin view, or its own host-built one."""
        if isinstance(value, HostBuilt):
            local = self._host_built.get(name)
            if local is None:
                raise HostServiceUnavailable(
                    f"插件 {self.plugin_id} 注入了 {name}，但宿主没有为它准备实例"
                )
            return cast(T, local)
        if name in PER_PLUGIN_PUBLIC_KEYS:
            cached = self._views.get(name)
            if cached is None:
                binder = cast(PluginViewBinder[Any], value)
                cached = binder.for_plugin(self._binding)
                self._views[name] = cached
            return cast(T, cached)
        return value

    def on[E](self, event_type: type[E], handler: OnHandler[E]) -> None:
        """Joins the ordered chain; return the (replaced) event or ``Veto``."""
        self._kernel_context.on(event_type, handler)

    def watch[E](self, event_type: type[E], handler: WatchHandler[E]) -> None:
        """Listens read-only to the final event, serially, without delaying emit."""
        self._kernel_context.watch(event_type, handler)

    async def emit[E](self, event: E) -> E | Veto:
        """Emits through the kernel: ``on`` chain, core checks, then watchers."""
        return await self._kernel_context.emit(event)

    def effect(self, label: str, dispose: Dispose) -> None:
        """登记资源清理；卸载先停用订阅和任务，再逆序撤销其它 effect。

        disposer 可同步或异步；单项失败仍继续清理。开始清理后拒绝新登记。
        """
        _ = self._effects.effect(dispose, f"custom:{label}")
