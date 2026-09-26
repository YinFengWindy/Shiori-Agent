"""One host channel with independently connected QQBot applications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .accounts import QQBotAccountStore, resolve_secret
from .account_commands import _AccountCommandsMixin
from .account_sending import _AccountSendingMixin
from .account_identity import QQBotAccountIdentity
from .account_dispatch import _AccountDispatchMixin
from .channel import QQBotChannel
from .formatting import CHANNEL, PUSH_TARGET_HINT

if TYPE_CHECKING:
    from core.common.channel_chat_types import ChatTypeDeclaration
    from infra.channels.contract import ChannelContext
    from agent.plugin_host.runtime_context import PluginRuntimeContext


class QQBotAccountsChannel(
    _AccountCommandsMixin, _AccountSendingMixin, _AccountDispatchMixin
):
    """Route host events by application while each child owns its gateway/token."""

    name = CHANNEL

    def __init__(
        self,
        ctx: PluginRuntimeContext,
        store: QQBotAccountStore,
        chat_types: tuple[ChatTypeDeclaration, ...],
    ) -> None:
        self._store = store
        self._chat_types = chat_types
        self._channels: dict[str, QQBotChannel] = {}
        self._identity = QQBotAccountIdentity(ctx, store)
        self._runtime: ChannelContext | None = None

    @property
    def configuration_key(self) -> object:
        """Do not reuse an adapter whose account-report generation has retired."""
        return self

    def _make_channel(self, row: dict[str, Any]) -> QQBotChannel:
        app_id = row["app_id"]
        return QQBotChannel(
            app_id,
            resolve_secret(row["client_secret"]),
            self._chat_types,
            scoped=not row.get("legacy", False),
            account_id=self._identity.account_id(app_id),
            on_status=lambda state, error, name, bot_id: self._identity.report(
                app_id, state, error, name, bot_id
            ),
            on_target=lambda openid: self._store.observe(app_id, openid),
        )

    async def start(self, ctx: ChannelContext) -> None:
        """Register one public channel, then start each configured gateway."""
        from bus.events_lifecycle import StreamDeltaReady, TurnCancelled, TurnStarted

        self._runtime = ctx
        ctx.push_tool.register_channel(
            CHANNEL,
            text=self.send,
            stream_text=self.send_stream,
            image=self.send_image,
            description=PUSH_TARGET_HINT,
        )
        ctx.bus.subscribe_outbound(CHANNEL, self._on_response)
        for event_type, handler in (
            (TurnStarted, self._on_turn_started),
            (StreamDeltaReady, self._on_stream_delta),
            (TurnCancelled, self._on_turn_cancelled),
        ):
            ctx.event_bus.on(event_type, handler)
        for row in self._store.list():
            if row.get("connected", True):
                await self._connect(row)
            else:
                self._identity.report(row["app_id"], "offline", "", "")

    async def stop(self) -> None:
        """Stop only gateways owned by this plugin instance."""
        from bus.events_lifecycle import StreamDeltaReady, TurnCancelled, TurnStarted

        for channel in tuple(self._channels.values()):
            await channel.stop()
        self._channels.clear()
        if self._runtime is not None:
            ctx = self._runtime
            ctx.bus.unsubscribe_outbound(CHANNEL, self._on_response)
            ctx.push_tool.unregister_channel(CHANNEL, text=self.send)
            for event_type, handler in (
                (TurnStarted, self._on_turn_started),
                (StreamDeltaReady, self._on_stream_delta),
                (TurnCancelled, self._on_turn_cancelled),
            ):
                ctx.event_bus.off(event_type, handler)
            self._runtime = None
        self._identity.unregister_all()

    def pause_intake(self) -> None:
        """Pause every application before a host settings handover."""
        for channel in self._channels.values():
            channel.pause_intake()

    def resume_intake(self) -> None:
        """Resume all application intakes after a rejected handover."""
        for channel in self._channels.values():
            channel.resume_intake()

    async def _connect(self, row: dict[str, Any]) -> QQBotChannel | None:
        app_id = row["app_id"]
        if not resolve_secret(row["client_secret"]):
            self._identity.report(
                app_id, "login_required", "App Secret 环境变量未设置", ""
            )
            return None
        channel = self._make_channel(row)
        self._channels[app_id] = channel
        if self._runtime is not None:
            await channel.start(self._runtime, public_hooks=False)
        return channel
