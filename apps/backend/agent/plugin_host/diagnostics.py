"""Host-only plugin failures; the shared failure contract lives in ``shiori_sdk.kernel``.

``PluginDiagnostic``, ``PackageContractError`` and ``RendererActivationError``
are kernel types (D13a), so lifecycle event payloads never import the host.
"""

from __future__ import annotations

from shiori_sdk.kernel import PluginDiagnostic


class ChannelDeclarationError(Exception):
    """``ctx.channels.add`` 贡献了 manifest ``channels`` 未声明的渠道名。

    setup 期间抛出，内核按普通 setup 失败回滚为 ``FAILED``；诊断的 ``state``
    与回滚后的真实状态一致，因此 ``PluginHandle`` 可以直接展示它。
    """

    def __init__(self, plugin_id: str, channel: str, declared: frozenset[str]):
        names = ", ".join(sorted(declared)) or "（无）"
        self.diagnostic = PluginDiagnostic(
            code="undeclared_channel",
            stage="setup",
            field="channels",
            reason=(
                f"插件 {plugin_id} 贡献了未在 manifest channels 中声明的渠道 "
                f"{channel}；已声明: {names}"
            ),
            state="FAILED",
        )
        super().__init__(self.diagnostic.reason)
