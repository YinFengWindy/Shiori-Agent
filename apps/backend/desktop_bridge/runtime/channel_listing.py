"""channels.list：渲染端的渠道发现与状态（#363）。

渠道来源有三类，按固定顺序列出：宿主自有的 ``desktop``、仍写死在宿主里的
内置渠道（QQ，迁为插件后删除）、各插件 manifest 的静态 ``channels``
声明。静态声明让插件停用、未信任或未填凭据时也能列出渠道；实际连接状态来自
当前运行代的 ``ChannelHost.snapshot()``。

``state`` 取值：

- ``active``：渠道已注册且没有失败记录；实现了 ``status()`` 的渠道另带 ``status``。
- ``not_configured``：插件已激活（或内置渠道已启用）但没有贡献这个渠道，通常是
  凭据未填。
- ``failed``：渠道构造、启动或状态读取失败，或者插件自身没能激活（冲突、未信任、
  依赖缺失、setup 失败）；``error`` 保留原因。
- ``plugin_disabled``：提供该渠道的插件在配置里被停用。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.plugin_host.kernel import PluginKernel
from agent.plugin_host.manifest import ChannelDeclaration
from bootstrap.app import AppRuntime
from bootstrap.channel_host import ChannelSnapshot

DESKTOP_CHANNEL = ChannelDeclaration(name="desktop", label="桌面端")

# 仍由 bootstrap/channels.py 硬编码构造的渠道；QQ 迁为插件后连同这里删除。
_BUILTIN_CHANNELS = (
    ChannelDeclaration(
        name="qq",
        label="QQ",
        contact_label="QQ 号",
        chat_id_label="会话 / 群组 ID",
        chat_id_hint="私聊填 QQ 号，群聊填 gqq:<群号>",
    ),
)


class RuntimeChannelListing:
    """Joins static channel declarations with the published generation's host state."""

    def __init__(self, app: AppRuntime, enabled: Callable[[str], bool]) -> None:
        self._app = app
        self._enabled = enabled

    def list(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Returns desktop, builtin and plugin-declared channels with their state."""
        host = self._app.channel_host
        snapshot = host.snapshot() if host is not None else {}
        plugin_rows = self._plugin_rows(snapshot)
        declared = {row["name"] for row in plugin_rows}
        rows = [
            _row(DESKTOP_CHANNEL, None, True, "active"),
            *(
                self._builtin_row(declaration, snapshot)
                for declaration in _BUILTIN_CHANNELS
                # 迁移后的同名插件接管这个渠道名
                if declaration.name not in declared
            ),
            *plugin_rows,
        ]
        return {"channels": rows}

    def _builtin_row(
        self, declaration: ChannelDeclaration, snapshot: dict[str, ChannelSnapshot]
    ) -> dict[str, Any]:
        qq = self._app.config.channels.qq
        configured = bool(qq and qq.bot_uin)
        entry = snapshot.get(declaration.name) if configured else None
        if entry is None:
            return _row(declaration, None, True, "not_configured")
        return _row(
            declaration,
            None,
            True,
            entry["state"],
            error=entry["error"],
            status=entry.get("status"),
        )

    def _plugin_rows(
        self, snapshot: dict[str, ChannelSnapshot]
    ) -> list[dict[str, Any]]:
        kernel = self._plugin_kernel()
        if kernel is None:
            return []
        states = {entry["candidate_id"]: entry for entry in kernel.states()}
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in kernel.discover():
            plugin_id = record.manifest.id
            enabled = self._enabled(plugin_id)
            state = states.get(record.candidate_id)
            plugin_state = (
                state["state"]
                if state
                else (record.admission.state if record.admission else "DISCOVERED")
            )
            plugin_error = (
                state["error"]
                if state
                else (record.admission.reason if record.admission else "")
            )
            for declaration in record.manifest.channels:
                # 同名声明只会出现在 CONFLICT 候选之间，第一条的诊断已列出全部声明方
                if declaration.name in seen:
                    continue
                seen.add(declaration.name)
                if not enabled:
                    rows.append(_row(declaration, plugin_id, False, "plugin_disabled"))
                elif plugin_state != "ACTIVE":
                    rows.append(
                        _row(
                            declaration,
                            plugin_id,
                            True,
                            "failed",
                            error=plugin_error or f"插件状态为 {plugin_state}",
                        )
                    )
                elif (entry := snapshot.get(declaration.name)) is None:
                    rows.append(_row(declaration, plugin_id, True, "not_configured"))
                else:
                    rows.append(
                        _row(
                            declaration,
                            plugin_id,
                            True,
                            entry["state"],
                            error=entry["error"],
                            status=entry.get("status"),
                        )
                    )
        return rows

    def _plugin_kernel(self) -> PluginKernel | None:
        core = self._app.core
        return core.plugin_manager if core is not None else None


def _row(
    declaration: ChannelDeclaration,
    plugin_id: str | None,
    plugin_enabled: bool,
    state: str,
    *,
    error: str = "",
    status: object = None,
) -> dict[str, Any]:
    return {
        **declaration.to_dict(),
        "plugin_id": plugin_id,
        "plugin_enabled": plugin_enabled,
        "state": state,
        "error": error,
        "status": status,
    }
