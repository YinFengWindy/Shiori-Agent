"""Public failures of plugin unload, replacement and in-generation reload."""

from typing import Literal


class PluginRestartRequired(RuntimeError):
    """Rejects a hot transition before any affected plugin is disposed."""

    code = "plugin_restart_required"

    def __init__(self, plugin_ids: list[str]) -> None:
        self.plugin_ids = tuple(sorted(set(plugin_ids)))
        super().__init__(
            f"插件 {', '.join(self.plugin_ids)} 不支持热卸载；本次更改未保存；请退出应用后修改配置，再重新启动。"
        )

    def to_details(self) -> dict[str, object]:
        """Exposes affected identities through the shared runtime error envelope."""
        return {"plugin_ids": list(self.plugin_ids), "restart_required": True}


type ReloadRefusal = Literal["inactive", "channels", "hot_unload"]
"""Why an in-generation transition was refused before anything changed.

``inactive``: the target is not an ACTIVE plugin of this generation.
``channels``: the closure contributes or declares channels, whose connections
only a generation swap hands over. ``hot_unload``: the closure declares
``supports_hot_unload: false``.
"""


class PluginReloadUnsupported(RuntimeError):
    """Refuses an in-generation unload/reload before any plugin is touched.

    Callers fall back to a full generation swap, which applies its own rules
    (for example ``PluginRestartRequired``).
    """

    code = "plugin_reload_unsupported"

    def __init__(self, plugin_ids: list[str], reason: ReloadRefusal) -> None:
        self.plugin_ids = tuple(sorted(set(plugin_ids)))
        self.reason: ReloadRefusal = reason
        super().__init__(
            f"插件 {', '.join(self.plugin_ids)} 无法在当前运行时内单独重载（{reason}）"
        )


class PluginReloadFailed(RuntimeError):
    """New configuration failed to activate; the previous configuration was restored.

    ``failed`` lists the plugins that did not become ACTIVE with the new
    values. ``restore_failed`` lists those that also failed to come back with
    the old values (normally empty); they stay FAILED like any setup failure.
    The first setup error is chained as ``__cause__``.
    """

    code = "plugin_reload_failed"

    def __init__(
        self,
        plugin_id: str,
        *,
        failed: tuple[str, ...],
        restore_failed: tuple[str, ...],
    ) -> None:
        self.plugin_id = plugin_id
        self.failed = failed
        self.restore_failed = restore_failed
        super().__init__(
            f"插件 {plugin_id} 的新配置未能生效（{', '.join(failed)} 启动失败），已恢复原配置"
            if not restore_failed
            else f"插件 {plugin_id} 的新配置未能生效，且 {', '.join(restore_failed)} 未能按原配置恢复"
        )
