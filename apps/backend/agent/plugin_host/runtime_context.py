"""插件作用域运行时上下文：只暴露 manifest 声明的 capability，取代旧上帝对象。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.plugin_host.effects import Dispose, EffectScope
from agent.plugin_host.manifest import PluginManifest


class CapabilityNotGranted(AttributeError):
    """插件访问了 manifest 未声明的 capability。"""


class PluginRuntimeContext:
    """v2 插件在 setup(ctx) 中拿到的唯一句柄。

    通过属性访问已授予的 capability（ctx.tools / ctx.events / ctx.kv / ...）；
    未声明的能力访问时抛 CapabilityNotGranted，而不是拿到 None。
    """

    def __init__(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        manifest: PluginManifest,
        effects: EffectScope,
        capabilities: dict[str, Any],
        publish_api: Any = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.manifest = manifest
        self._effects = effects
        self._capabilities = capabilities
        self._publish_api = publish_api

    def expose(self, api: object) -> None:
        """Publishes this plugin's API for declared dependents in the same generation."""
        if self._publish_api is None:
            raise RuntimeError("插件导出接口不可用")
        self._publish_api(api)

    @property
    def granted(self) -> tuple[str, ...]:
        """Returns granted capability names, for diagnostics."""
        return tuple(sorted(self._capabilities))

    def effect(self, label: str, dispose: Dispose) -> None:
        """登记资源清理；卸载先停用/退订 ctx.events.on，再逆序撤销其它 effect。

        disposer 可同步或异步；单项失败仍继续清理。事件订阅与 effect 的登记
        先后不影响退订优先规则；开始清理后拒绝新登记。
        """
        self._effects.add(f"custom:{label}", dispose)

    def __getattr__(self, name: str) -> Any:
        try:
            capabilities = object.__getattribute__(self, "_capabilities")
        except AttributeError as e:  # 构造未完成时保持原始 AttributeError 语义
            raise AttributeError(name) from e
        if name in capabilities:
            return capabilities[name]
        raise CapabilityNotGranted(
            f"插件 {self.plugin_id} 未声明 capability {name!r}；"
            f"已授予: {', '.join(self.granted) or '无'}"
        )
