"""One host channel with independently connected QQBot applications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .accounts import QQBotAccountStore, resolve_secret
from .account_commands import _AccountCommandsMixin
from .channel import QQBotChannel
from .formatting import CHANNEL, PUSH_TARGET_HINT, SYSTEM_PROMPT_HINT

if TYPE_CHECKING:
    from core.common.channel_chat_types import ChatTypeDeclaration
    from infra.channels.contract import ChannelContext
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_CAPABILITIES = frozenset({"private", "c2c", "known_targets", "send"})


class QQBotAccountsChannel(_AccountCommandsMixin):
    """Route host events by application while each child owns its gateway/token."""

    name = CHANNEL

    def __init__(
        self,
        ctx: PluginRuntimeContext,
        store: QQBotAccountStore,
        chat_types: tuple[ChatTypeDeclaration, ...],
    ) -> None:
        self._ctx = ctx
        self._store = store
        self._chat_types = chat_types
        self._channels: dict[str, QQBotChannel] = {}
        self._account_ids: dict[str, str] = {}
        self._runtime: ChannelContext | None = None
        for row in store.list():
            self._register(row)

    @property
    def configuration_key(self) -> object:
        """Do not reuse an adapter whose account-report generation has retired."""
        return self

    def _register(self, row: dict[str, Any], name: str = "") -> str:
        app_id = row["app_id"]
        snapshot = self._ctx.accounts.register(
            platform="qqbot",
            platform_account_id=app_id,
            config_ref=f"app:{app_id}",
            display_name=name or row.get("bot_name") or None,
        )
        self._account_ids[app_id] = snapshot.record.id
        return snapshot.record.id

    def _status(
        self, app_id: str, state: str, error: str, name: str, bot_id: str = ""
    ) -> None:
        if name or bot_id:
            row = self._store.get(app_id)
            self._store.save(
                {
                    **row,
                    "bot_name": name or row.get("bot_name", ""),
                    "bot_id": bot_id or row.get("bot_id", ""),
                }
            )
            self._register(row, name)
        self._ctx.accounts.report(
            self._account_ids[app_id],
            connection=state,
            capabilities=_CAPABILITIES if state == "online" else frozenset(),
            error=error,
        )

    def _make_channel(self, row: dict[str, Any]) -> QQBotChannel:
        app_id = row["app_id"]
        return QQBotChannel(
            app_id,
            resolve_secret(row["client_secret"]),
            self._chat_types,
            scoped=not row.get("legacy", False),
            account_id=self._account_ids[app_id],
            on_status=lambda state, error, name, bot_id: self._status(
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
                self._status(row["app_id"], "offline", "", "")

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
        for account_id in self._account_ids.values():
            self._ctx.accounts.unregister(account_id)

    def pause_intake(self) -> None:
        for channel in self._channels.values():
            channel.pause_intake()

    def resume_intake(self) -> None:
        for channel in self._channels.values():
            channel.resume_intake()

    async def _connect(self, row: dict[str, Any]) -> None:
        app_id = row["app_id"]
        if not resolve_secret(row["client_secret"]):
            self._status(app_id, "login_required", "App Secret 环境变量未设置", "")
            return
        channel = self._make_channel(row)
        self._channels[app_id] = channel
        if self._runtime is not None:
            await channel.start(self._runtime, public_hooks=False)

    def _for_chat(self, chat_id: str) -> QQBotChannel:
        kind, target = QQBotChannel._split_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("QQBot 当前仅支持 C2C 私聊")
        app_id = target.split(":", 1)[0]
        channel = self._channels.get(app_id)
        if channel is not None and channel._scoped:
            return channel
        if ":" in target:
            raise RuntimeError("QQBot 目标所属应用账号未连接")
        legacy = [item for item in self._channels.values() if not item._scoped]
        if len(legacy) == 1:
            return legacy[0]
        raise ValueError("QQBot 目标缺少有效应用账号作用域")

    async def send(self, chat_id: str, message: str) -> str | None:
        return await self._for_chat(chat_id).send(chat_id, message)

    async def send_proactive(self, chat_id: str, message: str) -> str | None:
        return await self.send(chat_id, message)

    async def send_image(self, chat_id: str, image: str) -> str | None:
        return await self._for_chat(chat_id).send_image(chat_id, image)

    async def send_stream(self, chat_id: str, message: str) -> str | None:
        return await self._for_chat(chat_id).send_stream(chat_id, message)

    def supports_stream_events(self, chat_id: str) -> bool:
        try:
            return self._for_chat(chat_id).supports_stream_events(chat_id)
        except (RuntimeError, ValueError):
            return False

    def system_prompt_hint(self, chat_id: str) -> str:
        return SYSTEM_PROMPT_HINT

    async def _on_response(self, message: Any) -> None:
        await self._for_chat(message.chat_id)._on_response(message)

    async def _on_turn_started(self, event: Any) -> None:
        if event.channel == CHANNEL:
            await self._for_chat(event.chat_id)._on_turn_started(event)

    async def _on_stream_delta(self, event: Any) -> None:
        if event.channel == CHANNEL:
            await self._for_chat(event.chat_id)._on_stream_delta(event)

    async def _on_turn_cancelled(self, event: Any) -> None:
        if event.channel == CHANNEL:
            await self._for_chat(event.chat_id)._on_turn_cancelled(event)
