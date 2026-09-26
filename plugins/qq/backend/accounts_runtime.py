"""QQ account lifecycle and platform actions over isolated OneBot sockets."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any
from uuid import uuid4

from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake

from .accounts_actions import QQAccountActions, qq_number
from .accounts_inbound_adapter import QQInboundAdapter
from .accounts_outbound_adapter import QQOutboundAdapter
from .accounts_settings import QQAccountSettings, validate_endpoint
from .accounts_store import QQAccountsStore, QQConnectionConfig
from .channel.formatting import PUSH_TARGET_HINT
from .onebot import OneBotAuthError, OneBotError, OneBotSocket

logger = logging.getLogger(__name__)
_CAPABILITIES = frozenset({"friends", "groups", "group_members", "send"})
STATUS_CHECK_INTERVAL_SECONDS = 5.0


class QQAccountsRuntime(QQAccountSettings, QQInboundAdapter, QQOutboundAdapter):
    """Owns independently replaceable QQ connections and their host snapshots."""

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
        self._actions = QQAccountActions(self._socket_for, self._ensure_online)
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
                await self._monitor_socket(ref, socket)
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
            validate_endpoint(config.ws_uri),
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

    async def connect_saved(self, ref: str) -> dict[str, str]:
        """Verifies a saved draft, then atomically replaces that account's socket."""
        if ref not in self._configs:
            raise KeyError("QQ 配置引用不存在")
        async with self._locks.setdefault(ref, asyncio.Lock()):
            config = self._configs[ref]
            pending = config.pending
            candidate = (
                replace(
                    config,
                    ws_uri=pending.ws_uri,
                    ws_token=pending.ws_token,
                    timeout_seconds=pending.timeout_seconds,
                    pending=None,
                )
                if pending is not None
                else config
            )
            try:
                socket, identity = await self._verified_socket(ref, candidate)
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
                result_id = self._activate(ref, candidate, socket, identity)
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
            await self._monitor_socket(ref, socket)
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

    def _socket_for(self, account_id: str) -> OneBotSocket:
        ref = self._ref_for(account_id)
        socket = self._sockets.get(ref)
        if (
            socket is None
            or socket.closed
            or self._states.get(ref, ("offline", ""))[0] != "online"
        ):
            raise OneBotError("QQ 账号不在线")
        return socket

    async def _ensure_online(self, account_id: str) -> None:
        ref = self._ref_for(account_id)
        socket = self._socket_for(account_id)
        await self._check_online(ref, socket)

    async def _check_online(self, ref: str, socket: OneBotSocket) -> None:
        try:
            status = await socket.call("get_status")
            if not isinstance(status, dict) or status.get("online") is not True:
                raise OneBotAuthError("NapCat 已连接但 QQ 尚未登录")
            try:
                identity = await socket.call("get_login_info")
            except OneBotError as exc:
                raise OneBotAuthError(f"NapCat 登录身份查询失败: {exc}") from exc
            if (
                not isinstance(identity, dict)
                or qq_number(identity.get("user_id"), "登录 QQ 号")
                != self._configs[ref].expected_uin
            ):
                raise OneBotError("NapCat 当前 QQ 身份与账号记录不匹配")
        except Exception as exc:
            if self._sockets.get(ref) is socket:
                state = "login_required" if _is_auth_failure(exc) else "error"
                self._states[ref] = (state, str(exc))
                self._accounts.report(self._ids[ref], connection=state, error=str(exc))
            raise
        if self._sockets.get(ref) is socket and self._states[ref][0] != "online":
            self._states[ref] = ("online", "")
            self._accounts.report(
                self._ids[ref], connection="online", capabilities=_CAPABILITIES
            )

    async def _monitor_socket(self, ref: str, socket: OneBotSocket) -> None:
        closed = asyncio.create_task(socket.wait_closed())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {closed}, timeout=STATUS_CHECK_INTERVAL_SECONDS
                )
                if done:
                    await closed
                    return
                try:
                    await self._check_online(ref, socket)
                except Exception:
                    try:
                        await socket.close()
                    except Exception:
                        logger.exception("[qq] 账号 %s 状态故障连接关闭失败", ref)
                    raise
        finally:
            if not closed.done():
                closed.cancel()
                await asyncio.gather(closed, return_exceptions=True)

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


def _is_auth_failure(error: Exception) -> bool:
    status = getattr(getattr(error, "response", None), "status_code", None)
    return isinstance(error, OneBotAuthError) or status in {401, 403}
