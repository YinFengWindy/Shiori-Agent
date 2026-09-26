"""QQ account lifecycle and platform actions over isolated OneBot sockets."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from bus.events import InboundMessage, OutboundMessage
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake

from .accounts_actions import QQAccountActions, qq_number
from .accounts_inbound import inbound_message
from .accounts_store import QQAccountsStore, QQConnectionConfig
from .channel.formatting import PUSH_TARGET_HINT
from .channel.compat import download_to_temp, extract_cq_images
from .channel.group_filter import strip_at_segments
from .onebot import OneBotAuthError, OneBotError, OneBotSocket

logger = logging.getLogger(__name__)
_CAPABILITIES = frozenset({"friends", "groups", "group_members", "send"})


def _endpoint(uri: str) -> str:
    parsed = urlsplit(uri)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("NapCat 地址必须是 ws:// 或 wss:// WebSocket 地址")
    return uri


class QQAccountsRuntime:
    """Owns independently replaceable QQ connections and their host snapshots."""

    name = "qq"

    def __init__(self, store: QQAccountsStore, accounts: Any) -> None:
        self._store = store
        self._accounts = accounts
        self._generation_key = uuid4().hex
        self._configs = store.load()
        self._states: dict[str, tuple[str, str]] = {}
        self._ids: dict[str, str] = {}
        self._sockets: dict[str, OneBotSocket] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._ctx: ChannelContext | None = None
        self._stopping = False
        self._intakes: dict[str, ChannelIntake] = {}
        self._actions = QQAccountActions(self._socket_for)
        for ref, config in self._configs.items():
            if config.verified and config.expected_uin:
                snapshot = self._accounts.register(
                    platform="qq",
                    platform_account_id=config.expected_uin,
                    config_ref=ref,
                    display_name=config.display_name or None,
                )
                self._ids[ref] = snapshot.record.id

    @property
    def configuration_key(self) -> tuple[str, str]:
        """Rebuilds the channel when RPC handlers bind a new plugin generation."""
        return ("qq-accounts", self._generation_key)

    async def start(self, ctx: ChannelContext) -> None:
        """Starts saved accounts without blocking the rest of the host startup."""
        self._ctx = ctx
        self._stopping = False
        for ref in self._configs:
            self._start_intake(ref)
        ctx.bus.subscribe_outbound(self.name, self._on_response)
        ctx.push_tool.register_channel(
            self.name,
            text=self._send_legacy,
            text_with_metadata=self._send_with_metadata,
            description=PUSH_TARGET_HINT,
        )
        for ref, config in self._configs.items():
            if config.auto_connect:
                self._schedule(ref)

    async def stop(self) -> None:
        """Closes only this plugin's sockets, preserving private settings."""
        self._stopping = True
        for intake in self._intakes.values():
            await intake.close()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for socket in list(self._sockets.values()):
            await socket.close()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._sockets.clear()
        self._intakes.clear()
        if self._ctx is not None:
            self._ctx.bus.unsubscribe_outbound(self.name, self._on_response)
            self._ctx.push_tool.unregister_channel(self.name)
            self._ctx = None

    def pause_intake(self) -> None:
        """Buffers incoming messages during host generation replacement."""
        for intake in self._intakes.values():
            intake.pause()

    def resume_intake(self) -> None:
        """Resumes incoming messages after host generation replacement."""
        for intake in self._intakes.values():
            intake.resume()

    def _start_intake(self, ref: str) -> None:
        if ref in self._intakes:
            return

        async def send_notice(chat_id: str, message: str) -> str:
            kind = "group" if chat_id.startswith("gqq:") else "private"
            target = chat_id[4:] if kind == "group" else chat_id
            return (
                await self._actions.send_target(self._ids[ref], kind, target, message)
            )["message_id"]

        intake = ChannelIntake(self._accept_inbound, send_notice)
        intake.start(paused=self._ctx.intake_paused if self._ctx else False)
        self._intakes[ref] = intake

    def status(self) -> dict[str, bool | str]:
        """Legacy channel status only; account rows carry the detailed state."""
        return {"connected": any(not sock.closed for sock in self._sockets.values())}

    def settings(
        self, account_id: str | None = None, ref: str | None = None
    ) -> dict[str, Any]:
        """Returns safe editable fields without returning an access token."""
        if account_id is None and ref is None:
            return {
                "accounts": [
                    self._public_config(key, row) for key, row in self._configs.items()
                ]
            }
        selected = self._ref_for(account_id) if account_id else str(ref)
        return {"account": self._public_config(selected, self._configs[selected])}

    def _public_config(self, ref: str, config: QQConnectionConfig) -> dict[str, Any]:
        connection, error = self._states.get(ref, ("offline", ""))
        return {**config.public_dict(), "connection": connection, "error": error}

    def _ref_for(self, account_id: str) -> str:
        try:
            return next(ref for ref, known in self._ids.items() if known == account_id)
        except StopIteration as exc:
            raise KeyError(f"QQ 账号不存在: {account_id}") from exc

    def _schedule(self, ref: str) -> None:
        if ref not in self._tasks or self._tasks[ref].done():
            self._tasks[ref] = asyncio.create_task(
                self._reconnect(ref), name=f"qq-account-{ref}"
            )

    async def _reconnect(self, ref: str) -> None:
        delay = 1.0
        while (
            not self._stopping
            and ref in self._configs
            and self._configs[ref].auto_connect
        ):
            if ref in self._ids:
                self._accounts.report(self._ids[ref], connection="connecting")
            self._states[ref] = ("connecting", "")
            try:
                async with self._locks.setdefault(ref, asyncio.Lock()):
                    socket, identity = await self._verified_socket(
                        ref, self._configs[ref]
                    )
                    try:
                        self._activate(ref, self._configs[ref], socket, identity)
                    except BaseException:
                        await socket.close()
                        raise
                await socket.wait_closed()
                if not self._stopping:
                    self._states[ref] = ("offline", "")
                    self._accounts.report(self._ids[ref], connection="offline")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state = "login_required" if _is_auth_failure(exc) else "error"
                self._states[ref] = (state, str(exc))
                if ref in self._ids:
                    self._accounts.report(
                        self._ids[ref], connection=state, error=str(exc)
                    )
                logger.warning("[qq] 账号 %s 连接失败: %s", ref, exc)
            if not self._stopping:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)

    async def _verified_socket(
        self, ref: str, config: QQConnectionConfig
    ) -> tuple[OneBotSocket, dict[str, Any]]:
        socket = OneBotSocket(
            _endpoint(config.ws_uri),
            config.ws_token,
            config.timeout_seconds,
            lambda event: self._on_socket_event(ref, socket, event),
        )
        await socket.open()
        try:
            try:
                identity = await socket.call("get_login_info")
            except OneBotError as exc:
                raise OneBotAuthError(f"NapCat 登录身份查询失败: {exc}") from exc
            if not isinstance(identity, dict):
                raise OneBotAuthError("NapCat 未返回登录身份")
            actual = qq_number(identity.get("user_id"), "登录 QQ 号")
            if config.expected_uin and actual != config.expected_uin:
                raise OneBotError(
                    f"NapCat 登录的是 {actual}，账号记录要求 {config.expected_uin}"
                )
            status = await socket.call("get_status")
            if not isinstance(status, dict) or status.get("online") is not True:
                raise OneBotAuthError("NapCat 已连接但 QQ 尚未登录")
            return socket, identity
        except BaseException:
            await socket.close()
            raise

    def _activate(
        self,
        ref: str,
        config: QQConnectionConfig,
        socket: OneBotSocket,
        identity: dict[str, Any],
    ) -> str:
        uin = qq_number(identity["user_id"], "登录 QQ 号")
        if any(
            other != ref and row.expected_uin == uin
            for other, row in self._configs.items()
        ):
            raise ValueError("这个 QQ 号已配置为另一个账号")
        saved = replace(
            config,
            expected_uin=uin,
            display_name=str(identity.get("nickname") or ""),
            auto_connect=True,
            verified=True,
        )
        snapshot = self._accounts.register(
            platform="qq",
            platform_account_id=uin,
            config_ref=ref,
            display_name=saved.display_name,
        )
        self._store.save({**self._configs, ref: saved})
        try:
            self._accounts.report(
                snapshot.record.id, connection="online", capabilities=_CAPABILITIES
            )
        except BaseException:
            self._store.save(self._configs)
            raise
        self._configs[ref] = saved
        self._ids[ref] = snapshot.record.id
        self._sockets[ref] = socket
        self._states[ref] = ("online", "")
        self._start_intake(ref)
        return snapshot.record.id

    async def save_draft(self, payload: dict[str, Any]) -> dict[str, str]:
        """Persists a draft without changing the current live connection."""
        account_id = str(payload.get("account_id") or "")
        supplied_ref = str(payload.get("ref") or "")
        ref = (
            self._ref_for(account_id)
            if account_id
            else supplied_ref or self._store.new_ref()
        )
        if supplied_ref and supplied_ref not in self._configs:
            raise KeyError("QQ 配置引用不存在")
        if account_id and supplied_ref and supplied_ref != ref:
            raise ValueError("QQ 账号与配置引用不匹配")
        if not account_id and supplied_ref and self._configs[ref].verified:
            raise PermissionError("已验证 QQ 账号必须按账号 ID 编辑")
        old = self._configs.get(ref)
        uri = _endpoint(str(payload.get("ws_uri") or "").strip())
        token = (
            ""
            if payload.get("clear_token") is True
            else str(payload.get("ws_token") or (old.ws_token if old else ""))
        )
        timeout = float(payload.get("timeout_seconds", 5.0))
        if timeout <= 0:
            raise ValueError("连接超时必须大于零")
        config = QQConnectionConfig(
            ref,
            uri,
            token,
            expected_uin=old.expected_uin if old else "",
            display_name=old.display_name if old else "",
            timeout_seconds=timeout,
            auto_connect=False,
            verified=old.verified if old else False,
        )
        async with self._locks.setdefault(ref, asyncio.Lock()):
            self._store.save({**self._configs, ref: config})
            self._configs[ref] = config
            if ref not in self._sockets:
                task = self._tasks.pop(ref, None)
                if task is not None:
                    task.cancel()
                if ref in self._ids:
                    self._accounts.report(self._ids[ref], connection="offline")
                self._states[ref] = ("offline", "")
            return {"ref": ref}

    async def connect_saved(self, ref: str) -> dict[str, str]:
        """Verifies a saved draft, then atomically replaces that account's socket."""
        if ref not in self._configs:
            raise KeyError("QQ 配置引用不存在")
        async with self._locks.setdefault(ref, asyncio.Lock()):
            config = self._configs[ref]
            try:
                socket, identity = await self._verified_socket(ref, config)
            except Exception as exc:
                if ref not in self._sockets:
                    state = "login_required" if _is_auth_failure(exc) else "error"
                    self._states[ref] = (state, str(exc))
                    if ref in self._ids:
                        self._accounts.report(
                            self._ids[ref], connection=state, error=str(exc)
                        )
                raise
            try:
                previous = self._sockets.get(ref)
                result_id = self._activate(ref, config, socket, identity)
            except BaseException:
                await socket.close()
                raise
            task = self._tasks.get(ref)
            if task is not None:
                task.cancel()
            self._tasks[ref] = asyncio.create_task(
                self._watch(ref, socket), name=f"qq-account-{ref}"
            )
            if previous is not None:
                try:
                    await previous.close()
                except Exception:
                    logger.exception("[qq] 旧账号连接关闭失败 ref=%s", ref)
            return {"account_id": result_id}

    async def _watch(self, ref: str, socket: OneBotSocket) -> None:
        failure: Exception | None = None
        try:
            await socket.wait_closed()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = exc
        if self._stopping or self._sockets.get(ref) is not socket:
            return
        self._sockets.pop(ref, None)
        state = (
            "offline"
            if failure is None
            else ("login_required" if _is_auth_failure(failure) else "error")
        )
        error = str(failure) if failure is not None else ""
        self._states[ref] = (state, error)
        self._accounts.report(self._ids[ref], connection=state, error=error)
        if failure is not None:
            logger.warning("[qq] 账号 %s 连接中断: %s", ref, failure)
            try:
                await socket.close()
            except Exception:
                logger.exception("[qq] 账号 %s 故障连接关闭失败", ref)
        if self._configs[ref].auto_connect:
            await self._reconnect(ref)

    async def disconnect(self, account_id: str) -> None:
        """Stops one socket and retains its saved QQ identity and credentials."""
        ref = self._ref_for(account_id)
        config = replace(self._configs[ref], auto_connect=False)
        self._store.save({**self._configs, ref: config})
        self._configs[ref] = config
        task = self._tasks.pop(ref, None)
        if task is not None:
            task.cancel()
        socket = self._sockets.pop(ref, None)
        if socket is not None:
            await socket.close()
        self._states[ref] = ("offline", "")
        self._accounts.report(account_id, connection="offline")

    async def remove_draft(self, ref: str) -> None:
        """Discards only an unverified, stopped connection draft."""
        config = self._configs[ref]
        if ref == "legacy":
            raise PermissionError("旧 QQ 配置仍在宿主设置中，不能删除迁移记录")
        if config.verified or config.auto_connect or ref in self._sockets:
            raise PermissionError("已验证或运行中的 QQ 账号不能作为草稿删除")
        self._store.save({key: row for key, row in self._configs.items() if key != ref})
        del self._configs[ref]
        self._states.pop(ref, None)
        intake = self._intakes.pop(ref, None)
        if intake is not None:
            await intake.close()
        self._locks.pop(ref, None)

    def _socket_for(self, account_id: str) -> OneBotSocket:
        ref = self._ref_for(account_id)
        socket = self._sockets.get(ref)
        if socket is None or socket.closed:
            raise OneBotError("QQ 账号不在线")
        return socket

    async def discover(
        self, account_id: str, kind: str, group_id: str = ""
    ) -> dict[str, Any]:
        """Dispatches a fresh target query through this account's socket."""
        return await self._actions.discover(account_id, kind, group_id)

    async def send_target(
        self, account_id: str, kind: str, target_id: str, message: str
    ) -> dict[str, str]:
        """Dispatches a target send through this account's socket."""
        return await self._actions.send_target(account_id, kind, target_id, message)

    async def _send_legacy(self, chat_id: str, message: str) -> str:
        if len(self._configs) != 1:
            raise OneBotError("QQ 多账号发送需要明确指定账号")
        online = [ref for ref, socket in self._sockets.items() if not socket.closed]
        if len(online) != 1:
            raise OneBotError("QQ 账号不在线")
        kind = "group" if chat_id.startswith("gqq:") else "private"
        target = chat_id[4:] if kind == "group" else chat_id
        return (
            await self._actions.send_target(self._ids[online[0]], kind, target, message)
        )["message_id"]

    async def _send_with_metadata(
        self, chat_id: str, message: str, metadata: dict[str, object]
    ) -> str:
        account_id = str(metadata.get("account_id") or "")
        if not account_id:
            return await self._send_legacy(chat_id, message)
        kind = "group" if chat_id.startswith("gqq:") else "private"
        target = chat_id[4:] if kind == "group" else chat_id
        return (await self.send_target(account_id, kind, target, message))["message_id"]

    async def _on_response(self, msg: OutboundMessage) -> None:
        try:
            message_id = await self._send_with_metadata(
                msg.chat_id, msg.content, msg.metadata
            )
        except Exception:
            self._mark_delivery(msg, "failed")
            raise
        self._mark_delivery(msg, "sent", message_id)

    def _mark_delivery(
        self, msg: OutboundMessage, status: str, message_id: str = ""
    ) -> None:
        hub = self._ctx.channel_hub if self._ctx else None
        if hub is not None:
            hub.mark_delivery(
                msg,
                default_channel=self.name,
                delivery_status=status,
                external_message_id=message_id,
            )

    async def _on_event(self, ref: str, event: dict[str, Any]) -> None:
        if ref not in self._ids:
            return
        message = inbound_message(
            account_id=self._ids[ref],
            expected_uin=self._configs[ref].expected_uin,
            event=event,
        )
        if message is not None:
            await self._intakes[ref].submit(message)

    async def _on_socket_event(
        self, ref: str, socket: OneBotSocket, event: dict[str, Any]
    ) -> None:
        if self._sockets.get(ref) is socket:
            await self._on_event(ref, event)

    async def _accept_inbound(self, message: InboundMessage) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        hub = ctx.channel_hub
        if hub is not None:
            if not hub.is_sender_allowed(
                channel=self.name, chat_id=message.chat_id, sender_id=message.sender
            ):
                return
        raw = (
            strip_at_segments(message.content)
            if message.metadata.get("chat_type") == "group"
            else message.content
        )
        text, image_urls = extract_cq_images(raw)
        media = (
            await download_to_temp(
                image_urls, ctx.http_resources.external_default, ctx.attachment_store
            )
            if image_urls
            else []
        )
        message = replace(message, content=text, media=media)
        if hub is not None:
            message = hub.route_inbound(message)
        if not message.metadata.get("conversation_duplicate"):
            await ctx.bus.publish_inbound(message)


def _is_auth_failure(error: Exception) -> bool:
    status = getattr(getattr(error, "response", None), "status_code", None)
    return isinstance(error, OneBotAuthError) or status in {401, 403}
