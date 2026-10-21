"""One role's channel, callback listener and fixed Grok Bot conversation."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import httpx
from shiori_sdk.accounts import ConnectionState, ViaAccount, account_id_for
from shiori_sdk.accounts.conversation import AccountConversation
from shiori_sdk.accounts.targets import UncertainDeliveryError
from shiori_sdk.channels import ChannelContext, ChannelStatus
from shiori_sdk.channels.errors import NonRetryableDeliveryError
from shiori_sdk.channels.services import ChannelIntake
from shiori_sdk.channel_events import TurnCancelled
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.storage import KeyValueStore

from .callback_server import CallbackServer
from .config import CHANNEL, PROTOCOL, ConnectionConfig
from .exchange import ExchangeJournal
from .protocol import BotMessage, CallbackError
from .store import write_private_json
from .transport import WebhookRejectedError, WebhookTransport

logger = logging.getLogger(__name__)
type ConfigChanged = Callable[[ConnectionConfig], None]
type StatusChanged = Callable[[ConnectionState, str], None]


class GrokConnection:
    """A host-owned transport with no network effects before ``start``."""

    default_chat_type = "private"

    def __init__(
        self,
        config: ConnectionConfig,
        kv: KeyValueStore,
        data_dir: Path,
        client_path: Path,
        *,
        config_changed: ConfigChanged,
        status_changed: StatusChanged,
        transport: httpx.AsyncBaseTransport | None = None,
        webhook_key: str | None = None,
    ) -> None:
        self.config = config
        self.name = config.channel_name
        self.account_id = account_id_for(CHANNEL, config.connection_id)
        self.client_file = data_dir / config.connection_id / "client.json"
        self.client_path = client_path
        self.journal = ExchangeJournal(kv, config.connection_id, config.peer_id)
        self._config_changed = config_changed
        self._status_changed = status_changed
        self._transport = WebhookTransport(
            config.webhook_url, webhook_key or config.webhook_key, transport=transport
        )
        self._server = CallbackServer(
            config.connection_id, config.callback_token, self.receive
        )
        self._ctx: ChannelContext | None = None
        self._intake: ChannelIntake | None = None
        self._paused = True
        self._owns_file = False
        self._sending = asyncio.Lock()
        self._receiving = asyncio.Lock()
        self._submitted: set[str] = set()
        self._recovery: asyncio.Task[None] | None = None
        self.last_error = ""
        self._outbound = self._on_response
        self._committed = self._on_committed
        self._cancelled = self._on_cancelled

    @property
    def configuration_key(self) -> object:
        """A new plugin generation must not retain retired account callbacks."""
        return self

    def via_account(self) -> dict[str, str]:
        """Keep the role endpoint distinct from the external Bot's identity."""
        return ViaAccount(
            platform=CHANNEL,
            platform_account_id=self.config.connection_id,
            display_name="Grok Bot 连接",
            prefix="Grok Bot 连接",
        ).to_metadata()

    @property
    def callback_url(self) -> str:
        """A local address without a credential in its URL."""
        return f"http://127.0.0.1:{self._server.port}/v1/connections/{self.config.connection_id}/"

    def _write_client_file(self) -> None:
        write_private_json(
            self.client_file,
            {
                "protocol": PROTOCOL,
                "callback_url": self.callback_url,
                "token": self.config.callback_token,
            },
        )
        self._owns_file = True

    def _update(self, **changes: object) -> None:
        self.config = self.config.model_copy(update=changes)
        self._config_changed(self.config)

    def _report(self) -> None:
        state: ConnectionState = (
            "offline" if self._ctx is None or not self.config.enabled else "online"
        )
        self._status_changed(state, "")

    async def start(self, ctx: ChannelContext) -> None:
        """Start the authenticated local endpoint and subscribe exactly once."""
        if self._ctx is not None:
            return
        self._ctx = ctx
        self._intake = ctx.intake_factory(self._accept, self._retry_notice)
        self._paused = ctx.intake_paused
        self._intake.start(paused=ctx.intake_paused)
        self._transport.start()
        try:
            await self._server.start(self.config.callback_port)
            if self.config.callback_port != self._server.port:
                self._update(callback_port=self._server.port)
            self._write_client_file()
            ctx.bus.subscribe_outbound(self.name, self._outbound)
            ctx.event_bus.on(TurnCommitted, self._committed)
            ctx.event_bus.on(TurnCancelled, self._cancelled)
            self._report()
            if not self._paused:
                self._recover()
        except BaseException:
            await self.stop()
            self._status_changed("error", "回程监听启动失败，请检查本机端口")
            raise

    async def stop(self) -> None:
        """Stop admission before draining channel work and releasing resources."""
        self.pause_intake()
        await self._server.stop()
        if self._recovery is not None:
            self._recovery.cancel()
            await asyncio.gather(self._recovery, return_exceptions=True)
            self._recovery = None
        try:
            if self._intake is not None:
                await self._intake.close()
        finally:
            self._intake = None
            try:
                async with self._sending:
                    await self._transport.stop()
            finally:
                if self._ctx is not None:
                    self._ctx.bus.unsubscribe_outbound(self.name, self._outbound)
                    self._ctx.event_bus.off(TurnCommitted, self._committed)
                    self._ctx.event_bus.off(TurnCancelled, self._cancelled)
                    self._ctx = None
                    self._submitted.clear()
                    self._report()
                if self._owns_file:
                    self.client_file.unlink(missing_ok=True)
                    self._owns_file = False

    def pause_intake(self) -> None:
        """Refuse new callbacks during the host's generation handover."""
        self._paused = True
        if self._intake is not None:
            self._intake.pause()

    def resume_intake(self) -> None:
        """Resume the published generation and recover previously queued input."""
        self._paused = False
        if self._intake is not None:
            self._intake.resume()
        self._recover()

    def _recover(self) -> None:
        if (
            self._ctx is not None
            and not self._paused
            and (self._recovery is None or self._recovery.done())
        ):
            self._recovery = asyncio.create_task(self._replay())

    async def _replay(self) -> None:
        async with self._receiving:
            for message in self.journal.pending():
                if self._paused or self._intake is None:
                    break
                if message.message_id in self._submitted:
                    continue
                try:
                    await self._intake.submit(self._inbound(message))
                except Exception:
                    self.last_error = "待处理消息恢复失败"
                    self._report()
                    logger.exception("Grok 连接的待处理消息恢复失败")
                    break

    async def receive(
        self, operation: str, payload: object
    ) -> tuple[int, dict[str, object]]:
        """Handle authenticated input; role and sender come only from this binding."""
        if self._ctx is None or self._paused or not self.config.enabled:
            raise CallbackError(409, "连接已暂停或正在切换")
        if operation != "messages":
            raise CallbackError(404, "操作不存在")
        message = BotMessage.parse(payload)
        async with self._receiving:
            if not self.journal.begin(message, "in", self.config.max_messages):
                receipt = self.journal.state.messages[message.message_id]
                if message.message_id in self._submitted or receipt.state != "queued":
                    return 200, {
                        "status": "duplicate",
                        "message_id": message.message_id,
                    }
            assert self._intake is not None
            try:
                await self._intake.submit(self._inbound(message))
            except Exception:
                self.last_error = "入站消息未能确认入队，请保留原消息 ID"
                self._report()
                raise
        return 202, {"status": "accepted", "message_id": message.message_id}

    def _inbound(self, message: BotMessage) -> InboundMessage:
        return InboundMessage(
            channel=self.name,
            sender=self.config.peer_id,
            chat_id=self.config.chat_id,
            content=message.text,
            metadata={
                "account_id": self.account_id,
                "chat_type": "private",
                "external_message_id": message.message_id,
                "sender_name": self.config.peer_name,
                "via_account": self.via_account(),
            },
        )

    async def _accept(self, message: InboundMessage) -> None:
        assert self._ctx is not None
        hub = self._ctx.channel_hub
        if hub is None:
            raise RuntimeError("渠道路由服务不可用")
        routed = hub.route_account_inbound(message)
        message_id = str(message.metadata["external_message_id"])
        if routed is None:
            self.journal.finish(message_id, "failed", "角色响应规则拒收")
            raise CallbackError(403, "角色响应规则拒收")
        if routed.metadata.get("conversation_duplicate"):
            self.journal.finish(message_id, "complete", "消息已在角色会话中")
            return
        await self._ctx.bus.publish_inbound(routed)
        self._submitted.add(message_id)

    async def _retry_notice(self, chat_id: str, text: str) -> None:
        # A transport-control notice must not wake the Bot into a new chat loop.
        self.last_error = text
        self._report()

    def _on_committed(self, event: TurnCommitted) -> None:
        if event.channel == self.name and event.chat_id == self.config.chat_id:
            # A committed response may still be queued for channel delivery.
            # Keep its parent protected from retention until that send settles.
            if not event.assistant_response:
                self.journal.complete_parent(event.external_message_id)
                self._submitted.discard(event.external_message_id)

    def _on_cancelled(self, event: TurnCancelled) -> None:
        if event.channel != self.name or event.chat_id != self.config.chat_id:
            return
        receipt = self.journal.state.messages.get(event.external_message_id)
        if receipt is not None and receipt.direction == "in":
            self._submitted.discard(event.external_message_id)
            self.journal.finish(event.external_message_id, "failed", "角色处理已取消")
            self.last_error = "角色处理已取消"
            self._report()

    async def send(self, message: BotMessage) -> dict[str, object]:
        """Submit one direct or reply message and return explicit transport acceptance."""
        async with self._sending:
            message = BotMessage.parse(
                {
                    "message_id": message.message_id,
                    "text": message.text,
                    "reply_to": message.reply_to,
                }
            )
            if self._ctx is None or not self.config.enabled:
                raise RuntimeError("Grok 连接未就绪")
            fresh = self.journal.begin(message, "out", self.config.max_messages)
            if fresh:
                try:
                    await self._transport.post(
                        {
                            "protocol": PROTOCOL,
                            "type": "message",
                            "message_id": message.message_id,
                            "exchange_id": self.journal.state.messages[
                                message.message_id
                            ].exchange_id,
                            "role_id": self.config.role_id,
                            "text": message.text,
                            "reply_to": message.reply_to,
                            "callback_client": str(self.client_path),
                            "connection_file": str(self.client_file),
                        }
                    )
                except (asyncio.CancelledError, UncertainDeliveryError):
                    self.journal.finish(
                        message.message_id, "uncertain", "发送结果不确定"
                    )
                    self.last_error = "发送结果不确定，请勿自动重发"
                    self._report()
                    raise
                except Exception as error:
                    self.journal.finish(
                        message.message_id, "failed", "Webhook 拒绝发送"
                    )
                    self.last_error = (
                        str(error)
                        if isinstance(error, WebhookRejectedError)
                        else "Webhook 发送失败"
                    )
                    self._report()
                    raise
                self.journal.finish(
                    message.message_id, "accepted", "Grok 已接收，等待回复"
                )
                self.journal.complete_parent(message.reply_to)
                self.last_error = ""
                self._report()
            return {
                "accepted": True,
                "conversation": AccountConversation(
                    self.name, self.config.chat_id
                ).to_payload(),
                "via_account": self.via_account(),
            }

    async def _on_response(self, message: OutboundMessage) -> None:
        assert self._ctx is not None
        hub = self._ctx.channel_hub
        if hub is None:
            raise RuntimeError("渠道路由服务不可用")
        status = "failed"
        try:
            if message.chat_id != self.config.chat_id or message.media:
                raise ValueError("Grok 仅支持当前 Bot 的文字私聊")
            await self.send(
                BotMessage(
                    "shiori:" + (message.committed_message_id or uuid4().hex),
                    message.content,
                    str(message.metadata.get("external_message_id") or ""),
                )
            )
            status = "sent"
        except Exception as error:
            raise NonRetryableDeliveryError(
                str(error)
                if isinstance(
                    error, (WebhookRejectedError, UncertainDeliveryError, CallbackError)
                )
                else "Grok 回复未能确认送达，请检查连接状态"
            ) from error
        finally:
            parent_id = str(message.metadata.get("external_message_id") or "")
            self.journal.complete_parent(parent_id)
            self._submitted.discard(parent_id)
            hub.mark_delivery(
                message,
                default_channel=self.name,
                delivery_status=status,
                via_account=self.via_account() if status == "sent" else None,
            )

    def status(self) -> ChannelStatus:
        """Expose actual callback readiness and transport state without credentials."""
        return {
            "connected": self._ctx is not None and self.config.enabled,
            "account": self.config.peer_name,
            "detail": "",
        }

    def system_prompt_hint(self, chat_id: str) -> str:
        """Normal turn replies already go to this Bot; use the account tool to initiate."""
        return "这是与 Grok Bot 的私聊；本轮正文会直接发给对方，不要再用 account_send 重复发送。交流结束时可以不再回复。"
