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


type ReloadRefusal = Literal["disabled", "failed", "retired", "channels", "hot_unload"]
"""Why an in-generation reload was refused before anything changed.

``disabled``: the target is disabled; storing its config needs no reload.
``failed``: the target exists but is not ACTIVE (failed, blocked, untrusted…);
only a generation swap can retry it. ``retired``: this generation has been
terminated. ``channels``: the closure contributes or declares channels, whose
connections only a generation swap hands over. ``hot_unload``: the closure
declares ``supports_hot_unload: false``.
"""


class PluginReloadUnsupported(RuntimeError):
    """Refuses an in-generation reload before any plugin is touched.

    Except for ``disabled``, callers fall back to a full generation swap,
    which applies its own rules (for example ``PluginRestartRequired``).
    """

    code = "plugin_reload_unsupported"

    def __init__(self, plugin_ids: list[str], reason: ReloadRefusal) -> None:
        self.plugin_ids = tuple(sorted(set(plugin_ids)))
        self.reason: ReloadRefusal = reason
        super().__init__(
            f"插件 {', '.join(self.plugin_ids)} 无法在当前运行时内单独重载（{reason}）"
        )


class PluginReloadTimeout(RuntimeError):
    """In-flight work did not drain in time; the reload was abandoned unchanged.

    Every closure plugin admits calls again with its old instance and config.
    ``busy`` lists the plugins whose calls or ``on_drain`` callbacks were still
    running when the timeout expired. ``on_drain`` of dependents drained
    before the timeout has already run (it only waits, so nothing changed),
    and an ``on_drain`` in progress may still finish in the background.

    Also reported in ``PluginReloadFailed.cleanup_errors`` when new instances
    discarded by a rollback did not finish their calls in time.
    """

    code = "plugin_reload_timeout"

    def __init__(self, busy: tuple[str, ...], timeout: float) -> None:
        self.busy = busy
        self.timeout = timeout
        super().__init__(
            f"插件 {', '.join(busy)} 的进行中调用未在 {timeout:g} 秒内结束，本次重载已放弃"
        )


class PluginReloadFailed(RuntimeError):
    """New configuration failed to activate; the previous configuration was restored.

    ``failed`` maps each plugin that did not become ACTIVE with the new values
    to its setup error, in load order; ``__cause__`` is the first of them.
    ``restore_failed`` maps those that also failed to come back with the old
    values (normally empty); they stay FAILED like any setup failure.
    ``cleanup_errors`` are disposal and process-resource close failures met
    along the way.
    """

    code = "plugin_reload_failed"

    def __init__(
        self,
        plugin_id: str,
        *,
        failed: dict[str, BaseException],
        restore_failed: dict[str, BaseException],
        cleanup_errors: tuple[BaseException, ...],
    ) -> None:
        self.plugin_id = plugin_id
        self.failed = failed
        self.restore_failed = restore_failed
        self.cleanup_errors = cleanup_errors
        super().__init__(
            f"插件 {plugin_id} 的新配置未能生效（{', '.join(failed)} 启动失败），已恢复原配置"
            if not restore_failed
            else f"插件 {plugin_id} 的新配置未能生效，且 {', '.join(restore_failed)} 未能按原配置恢复"
        )
