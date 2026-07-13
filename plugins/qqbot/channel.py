"""官方 QQBot 渠道的 Gateway 和 REST 适配。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import httpx
import websockets

from agent.looping.interrupt import InterruptController
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import StreamDeltaReady, TurnStarted
from bus.queue import MessageBus
from core.channels import ChannelHub
from infra.channels.contract import ChannelContext
from infra.channels.session_key import resolve_outbound_session_key

if TYPE_CHECKING:
    from .plugin import QQBotGroupConfigModel

logger = logging.getLogger(__name__)

_CHANNEL = "qqbot"
_API_BASE = "https://api.sgroup.qq.com"
_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
_LIVE_STREAM_MIN_CHARS = 120
_LIVE_STREAM_MIN_INTERVAL_S = 1.5
_LIVE_MAX_FAILURES = 3
_REPLY_LIVE_TAIL = 900


@dataclass
class _TokenCache:
    token: str
    expires_at: float


@dataclass
class _LiveStreamState:
    openid: str
    msg_id: str
    msg_seq: int
    stream_msg_id: str = ""
    index: int = 0
    completed: bool = False


class QQBotChannel:
    """Connects the official QQBot C2C API to the shared message bus."""

    name = _CHANNEL

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        allow_from: list[str] | None = None,
        groups: list["QQBotGroupConfigModel"] | None = None,
    ) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._allow_from = {
            str(value).strip()
            for value in (allow_from or [])
            if str(value).strip()
        }
        self._groups = {str(group.group_openid): group for group in (groups or [])}
        self._bus: MessageBus | None = None
        self._interrupt_controller: InterruptController | None = None
        self._channel_hub: ChannelHub | None = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token: _TokenCache | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._outbound_bound = False
        self._events_bound = False
        self._last_c2c_msg_id: dict[str, str] = {}
        self._live_states: dict[str, _LiveStreamState] = {}
        self._reply_buffers: dict[str, str] = {}
        self._live_next_at: dict[str, float] = {}
        self._live_last_lengths: dict[str, int] = {}
        self._live_failures: dict[str, int] = {}
        self._live_disabled: set[str] = set()
        self._live_locks: dict[str, asyncio.Lock] = {}
        self._live_tasks: set[asyncio.Task[None]] = set()
        self._live_tasks_by_session: dict[str, set[asyncio.Task[None]]] = {}

    async def start(self, ctx: ChannelContext) -> None:
        """Registers runtime hooks and starts the official Gateway loop."""
        self._bus = ctx.bus
        self._interrupt_controller = ctx.interrupt_controller
        self._channel_hub = ctx.channel_hub
        if not self._events_bound:
            ctx.event_bus.on(TurnStarted, self._on_turn_started)
            ctx.event_bus.on(StreamDeltaReady, self._on_stream_delta)
            self._events_bound = True
        ctx.push_tool.register_channel(
            self.name,
            text=self.send_proactive,
            stream_text=self.send_stream,
        )
        self._stopped.clear()
        self._task = asyncio.create_task(self._gateway_loop(), name="qqbot_gateway")
        if not self._outbound_bound:
            ctx.bus.subscribe_outbound(_CHANNEL, self._on_response)
            self._outbound_bound = True
        logger.info("[qqbot] 官方 QQBot 通道已启动")

    async def stop(self) -> None:
        """Stops Gateway tasks, pending stream updates, and the HTTP client."""
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._drain_live_tasks()
        await self._client.aclose()
        logger.info("[qqbot] 官方 QQBot 通道已停止")

    async def _gateway_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                token = await self._get_access_token()
                gateway = await self._api_request("GET", "/gateway", token=token)
                await self._run_gateway(str(gateway["url"]), token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[qqbot] Gateway 连接失败: %s", exc)
                await asyncio.sleep(5)

    async def _run_gateway(self, url: str, token: str) -> None:
        last_seq: int | None = None
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            async with websockets.connect(url) as websocket:
                async for raw in websocket:
                    payload = json.loads(raw)
                    op = payload.get("op")
                    raw_data = payload.get("d")
                    data = cast(dict[str, Any], raw_data) if isinstance(raw_data, dict) else {}
                    event_type = str(payload.get("t") or "")
                    if isinstance(payload.get("s"), int):
                        last_seq = int(payload["s"])
                    if op == 10:
                        heartbeat_task = asyncio.create_task(
                            self._heartbeat(
                                websocket,
                                int(data["heartbeat_interval"]),
                                lambda: last_seq,
                            ),
                            name="qqbot_heartbeat",
                        )
                        await websocket.send(json.dumps({
                            "op": 2,
                            "d": {
                                "token": f"QQBot {token}",
                                "intents": self._intents(),
                                "shard": [0, 1],
                            },
                        }))
                    elif op == 0:
                        await self._handle_dispatch(event_type, data)
                    elif op == 7:
                        break
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _heartbeat(
        self,
        websocket: Any,
        heartbeat_ms: int,
        seq_fn: Callable[[], int | None],
    ) -> None:
        while True:
            await asyncio.sleep(max(1, heartbeat_ms / 1000))
            await websocket.send(json.dumps({"op": 1, "d": seq_fn()}))

    def _intents(self) -> int:
        return 1 << 25

    async def _handle_dispatch(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "C2C_MESSAGE_CREATE":
            await self._handle_c2c(data)
        elif event_type.startswith("GROUP_"):
            logger.debug("[qqbot] 当前仅启用私聊模式，忽略群事件 event=%s", event_type)

    async def _handle_c2c(self, data: dict[str, Any]) -> None:
        author = _as_dict(data.get("author"))
        user_openid = str(author.get("user_openid") or data.get("user_openid") or "").strip()
        if not user_openid:
            return
        if self._allow_from and user_openid not in self._allow_from:
            logger.warning("[qqbot] 拒绝未授权私聊用户 user_openid=%s", user_openid)
            return
        content = str(data.get("content") or "").strip()
        message_id = str(data.get("id") or "").strip()
        if message_id:
            self._last_c2c_msg_id[user_openid] = message_id
            await self._send_input_notify(user_openid, message_id)
        chat_id = f"c2c:{user_openid}"
        logger.info("[qqbot] 收到私聊消息 user_openid=%s msg_id=%s", user_openid, message_id)
        if content == "/stop":
            await self._handle_stop(chat_id, user_openid)
            return
        await self._publish_inbound(
            InboundMessage(
                channel=_CHANNEL,
                sender=user_openid,
                chat_id=chat_id,
                content=content,
                metadata={
                    "chat_type": "private",
                    "user_openid": user_openid,
                    "message_id": message_id,
                    "external_message_id": message_id,
                },
            )
        )

    async def _publish_inbound(self, message: InboundMessage) -> None:
        if self._channel_hub is not None:
            if not self._channel_hub.is_sender_allowed(
                channel=message.channel,
                chat_id=message.chat_id,
                sender_id=message.sender,
            ):
                logger.warning("[qqbot] 拒绝未绑定渠道或未授权用户 chat_id=%s", message.chat_id)
                return
            message = self._channel_hub.route_inbound(message)
        if message.metadata.get("conversation_duplicate"):
            return
        await self._require_bus().publish_inbound(message)

    async def _handle_stop(self, chat_id: str, sender: str) -> None:
        if self._interrupt_controller is None:
            await self.send(chat_id, "当前未启用中断功能。")
            return
        session_key = (
            self._channel_hub.resolve_runtime_session_key(_CHANNEL, chat_id)
            if self._channel_hub is not None
            else f"{_CHANNEL}:{chat_id}"
        )
        result = self._interrupt_controller.request_interrupt(
            session_key=session_key,
            sender=sender,
            command="/stop",
        )
        await self.send(chat_id, result.message)

    async def _on_response(self, msg: OutboundMessage) -> None:
        session_key = resolve_outbound_session_key(msg, default_channel=_CHANNEL)
        sent_as_stream = False
        send_failed = False
        try:
            if session_key in self._live_states:
                await self._cancel_live_tasks(session_key)
                if msg.content.strip():
                    sent_as_stream = await self._send_live_stream(
                        session_key,
                        msg.chat_id,
                        msg.content,
                        terminal=True,
                    )
                else:
                    await self._delete_live_preview(session_key)
                self._clear_live_session(session_key)
            if msg.content.strip() and not sent_as_stream:
                await self.send(msg.chat_id, msg.content)
        except Exception:
            send_failed = True
            self._record_delivery_status(msg, "failed")
            raise
        finally:
            if not send_failed:
                self._record_delivery_status(msg, "sent")

    def _record_delivery_status(self, msg: OutboundMessage, status: str) -> None:
        if self._channel_hub is None:
            return
        self._channel_hub.mark_delivery(
            msg,
            default_channel=_CHANNEL,
            delivery_status=status,
            external_message_id=str(msg.metadata.get("external_message_id") or ""),
        )

    async def send_proactive(self, chat_id: str, message: str) -> None:
        """Sends a proactive C2C text message through the official API."""
        await self.send(chat_id, message)

    async def send(self, chat_id: str, message: str) -> None:
        """Sends a normal Markdown message to a C2C target."""
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        token = await self._get_access_token()
        await self._api_request(
            "POST",
            f"/v2/users/{target}/messages",
            self._build_message_body(message),
            token,
        )

    async def send_stream(self, chat_id: str, message: str) -> None:
        """Sends a complete proactive response using the official stream API."""
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        msg_id = self._last_c2c_msg_id.get(target)
        if not msg_id:
            await self.send(chat_id, message)
            return
        try:
            await self._send_stream_c2c(target, msg_id, message)
        except Exception as exc:
            logger.warning("[qqbot] 私聊流式发送失败，回退普通发送: %s", exc)
            await self.send(chat_id, message)

    async def _send_stream_c2c(self, openid: str, msg_id: str, message: str) -> None:
        token = await self._get_access_token()
        msg_seq = self._next_msg_seq()
        stream_msg_id = ""
        chunks = _iter_stream_chunks(message)
        for index, content in enumerate(chunks):
            body: dict[str, Any] = {
                "input_mode": "replace",
                "input_state": 10 if index == len(chunks) - 1 else 1,
                "content_type": "markdown",
                "content_raw": content,
                "event_id": msg_id,
                "msg_id": msg_id,
                "msg_seq": msg_seq,
                "index": index,
            }
            if stream_msg_id:
                body["stream_msg_id"] = stream_msg_id
            result = await self._api_request(
                "POST",
                f"/v2/users/{openid}/stream_messages",
                body,
                token,
            )
            stream_msg_id = str(result.get("id") or stream_msg_id)

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel != _CHANNEL:
            return
        await self._cancel_live_tasks(event.session_key)
        self._clear_live_session(event.session_key)

    async def _on_stream_delta(self, event: StreamDeltaReady) -> None:
        if event.channel != _CHANNEL or not event.content_delta:
            return
        reply = self._reply_buffers.get(event.session_key, "") + event.content_delta
        self._reply_buffers[event.session_key] = reply
        now = asyncio.get_running_loop().time()
        last_len = self._live_last_lengths.get(event.session_key, 0)
        next_at = self._live_next_at.get(event.session_key, 0.0)
        if now < next_at and len(reply) - last_len < _LIVE_STREAM_MIN_CHARS:
            return
        self._live_next_at[event.session_key] = now + _LIVE_STREAM_MIN_INTERVAL_S
        self._live_last_lengths[event.session_key] = len(reply)
        self._start_live_task(
            event.session_key,
            self._sync_live_message(event.session_key, event.chat_id),
        )

    async def _sync_live_message(self, session_key: str, chat_id: str) -> None:
        text = _format_turn_live(self._reply_buffers.get(session_key, ""))
        if text:
            await self._send_live_stream(session_key, chat_id, text, terminal=False)

    async def _delete_live_preview(self, session_key: str) -> None:
        state = self._live_states.get(session_key)
        if state is None or not state.stream_msg_id:
            return
        try:
            await self._delete_message(state.openid, state.stream_msg_id)
        except Exception as exc:
            logger.debug("[qqbot] 临时流式消息撤回失败，忽略: %s", exc)

    async def _send_live_stream(
        self,
        session_key: str,
        chat_id: str,
        text: str,
        *,
        terminal: bool,
    ) -> bool:
        if session_key in self._live_disabled:
            return False
        kind, openid = self._parse_chat_id(chat_id)
        if kind != "c2c":
            return False
        msg_id = self._last_c2c_msg_id.get(openid)
        if not msg_id:
            return False
        lock = self._live_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            if session_key in self._live_disabled:
                return False
            state = self._live_states.setdefault(
                session_key,
                _LiveStreamState(openid=openid, msg_id=msg_id, msg_seq=self._next_msg_seq()),
            )
            if state.completed:
                return False
            try:
                token = await self._get_access_token()
                body: dict[str, Any] = {
                    "input_mode": "replace",
                    "input_state": 10 if terminal else 1,
                    "content_type": "markdown",
                    "content_raw": text,
                    "event_id": state.msg_id,
                    "msg_id": state.msg_id,
                    "msg_seq": state.msg_seq,
                    "index": state.index,
                }
                if state.stream_msg_id:
                    body["stream_msg_id"] = state.stream_msg_id
                result = await self._api_request(
                    "POST",
                    f"/v2/users/{state.openid}/stream_messages",
                    body,
                    token,
                )
            except Exception as exc:
                failures = self._live_failures.get(session_key, 0) + 1
                self._live_failures[session_key] = failures
                status_code = _http_status_code(exc)
                if (status_code is not None and status_code != 429) or (
                    failures >= _LIVE_MAX_FAILURES
                ):
                    self._live_disabled.add(session_key)
                logger.warning(
                    "[qqbot] 临时流式刷新失败 session=%s failures=%d err=%s",
                    session_key,
                    failures,
                    exc,
                )
                return False
            self._live_failures[session_key] = 0
            state.stream_msg_id = str(result.get("id") or state.stream_msg_id)
            state.index += 1
            state.completed = terminal
            return True

    def _start_live_task(self, session_key: str, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._live_tasks.add(task)
        self._live_tasks_by_session.setdefault(session_key, set()).add(task)
        task.add_done_callback(lambda done: self._on_live_task_done(session_key, done))

    def _on_live_task_done(self, session_key: str, task: asyncio.Task[None]) -> None:
        self._live_tasks.discard(task)
        tasks = self._live_tasks_by_session.get(session_key)
        if tasks is not None:
            tasks.discard(task)
            if not tasks:
                self._live_tasks_by_session.pop(session_key, None)
        if not task.cancelled() and task.exception() is not None:
            logger.debug("[qqbot] 临时流式状态刷新失败: %s", task.exception())

    async def _cancel_live_tasks(self, session_key: str) -> None:
        tasks = list(self._live_tasks_by_session.get(session_key, set()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _drain_live_tasks(self) -> None:
        tasks = [task for task in self._live_tasks if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _clear_live_session(self, session_key: str) -> None:
        self._live_states.pop(session_key, None)
        self._reply_buffers.pop(session_key, None)
        self._live_next_at.pop(session_key, None)
        self._live_last_lengths.pop(session_key, None)
        self._live_failures.pop(session_key, None)
        self._live_disabled.discard(session_key)
        self._live_locks.pop(session_key, None)

    async def _send_input_notify(self, openid: str, msg_id: str) -> None:
        try:
            token = await self._get_access_token()
            await self._api_request(
                "POST",
                f"/v2/users/{openid}/messages",
                {
                    "msg_type": 6,
                    "input_notify": {"input_type": 1, "input_second": 60},
                    "msg_seq": self._next_msg_seq(),
                    "msg_id": msg_id,
                },
                token,
            )
        except Exception as exc:
            logger.debug("[qqbot] 发送输入中提示失败: %s", exc)

    async def _delete_message(self, openid: str, message_id: str) -> None:
        token = await self._get_access_token()
        await self._api_request(
            "DELETE",
            f"/v2/users/{openid}/messages/{message_id}",
            token=token,
        )

    def _build_message_body(self, message: str) -> dict[str, Any]:
        return {
            "markdown": {"content": message},
            "msg_type": 2,
            "msg_seq": self._next_msg_seq(),
        }

    def _next_msg_seq(self) -> int:
        return int(time.time() * 1000) % 65536

    def _parse_chat_id(self, chat_id: str) -> tuple[str, str]:
        value = chat_id.strip()
        if value.startswith("qqbot:"):
            value = value[len("qqbot:"):]
        if ":" not in value:
            return "c2c", value
        kind, target = value.split(":", 1)
        if kind not in {"c2c", "group"} or not target:
            raise ValueError(f"无效的 QQBot chat_id: {chat_id!r}")
        return kind, target

    async def _get_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token.expires_at - 300:
            return self._token.token
        response = await self._client.post(
            _TOKEN_URL,
            json={"appId": self._app_id, "clientSecret": self._client_secret},
        )
        response.raise_for_status()
        data = response.json()
        token = str(data["access_token"])
        expires_in = int(data.get("expires_in") or 7200)
        self._token = _TokenCache(token=token, expires_at=now + expires_in)
        return token

    async def _api_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        access_token = token or await self._get_access_token()
        kwargs: dict[str, Any] = {
            "headers": {
                "Authorization": f"QQBot {access_token}",
                "Content-Type": "application/json",
            }
        }
        if body is not None:
            kwargs["json"] = body
        response = await self._client.request(method, f"{_API_BASE}{path}", **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        data = response.json()
        return cast(dict[str, Any], data) if isinstance(data, dict) else {}

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("QQBotChannel 尚未启动")
        return self._bus


def _as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _http_status_code(error: Exception) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def _iter_stream_chunks(text: str, limit: int = 160) -> list[str]:
    if not text:
        return [""]
    return [text[:end] for end in range(limit, len(text) + limit, limit)]


def _format_turn_live(reply: str) -> str:
    return _tail_text(reply.strip(), _REPLY_LIVE_TAIL)


def _tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "..." + text[-(limit - 3):]
