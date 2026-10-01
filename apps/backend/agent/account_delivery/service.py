"""Authorize account operations and delegate target work to the owning plugin."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from agent.account_delivery.turn_state import mark_account_delivery_sent
from core.accounts import (
    VIA_ACCOUNT_KEY,
    AccountAccess,
    AccountNotFoundError,
    AccountRegistry,
    AccountSnapshot,
    delivered_via_account,
)
from core.accounts.delivery_ledger import AccountDeliveryAttempt, AccountDeliveryLedger
from core.accounts.target_contract import (
    ACCOUNT_SEND_MEDIA_KEY,
    ACCOUNT_SEND_METHOD,
    ACCOUNT_TARGETS_METHOD,
    AccountTarget,
    UncertainDeliveryError,
)
from core.identity import IdentityChat, UserIdentityStore, identities_for_account

if TYPE_CHECKING:
    # The registry is injected; importing its package here initializes the kernel
    # and turn orchestration before AccountDelivery itself has been defined.
    from agent.plugin_host.rpc import PluginRpcRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountSendReceipt:
    """Selected target and platform receipt for one explicit send attempt.

    ``via_account`` is the sending plugin's ``ViaAccount`` snapshot, stored
    as-is with any message recorded for this send; None if it gave none or
    gave an invalid one (logged, never failing the completed send).
    """

    attempt_id: str
    account_id: str
    channel: str
    target_kind: str
    target_id: str
    platform_message_id: str
    ownership_current: bool
    via_account: dict[str, str] | None = None

    def message_metadata(self) -> dict[str, Any]:
        """The delivery facts stored with the session message recording this send."""
        return {
            "delivery_attempt_id": self.attempt_id,
            "delivery_account_id": self.account_id,
            "delivery_target_kind": self.target_kind,
            "delivery_target_id": self.target_id,
            **(
                {VIA_ACCOUNT_KEY: self.via_account}
                if self.via_account is not None
                else {}
            ),
        }


@dataclass(frozen=True)
class UserChatTarget:
    """Where the role reaches its user on one channel.

    ``target`` is the private target the plugin sends to (the bound platform
    user ID, as for proactive delivery); ``chat`` is the known private chat
    with the user through the role's account there, whose conversation thread
    a message sent this way belongs to.
    """

    chat: IdentityChat
    target: AccountTarget


class AccountDelivery:
    """Checks live ownership and records each plugin send independently of turns.

    Callers name a channel (the channel plugin's ID); the role's account there
    is looked up in the registry, since a role holds at most one per plugin.
    Errors meant for the model name the channel, never the account ID.
    ``identities`` are the desktop user's bindings, which name the user's
    private chat on a channel (``user_chat``).
    """

    def __init__(
        self,
        accounts: AccountRegistry,
        rpc: PluginRpcRegistry,
        ledger: AccountDeliveryLedger,
        identities: UserIdentityStore,
    ) -> None:
        self._accounts = accounts
        self._rpc = rpc
        self._ledger = ledger
        self._identities = identities

    def channel_account(self, channel: str, role_id: str) -> AccountSnapshot:
        """The role's account on ``channel``; raises when it has none loaded."""
        if not role_id:
            raise PermissionError("需要角色上下文")
        channel = channel.strip()
        if not channel:
            raise ValueError("渠道不能为空")
        for account in self._accounts.list(role_id=role_id):
            if account.record.plugin_id == channel:
                return account
        raise LookupError(
            f"当前角色在渠道 {channel} 没有可用账号（未添加账号或渠道插件未加载）"
        )

    def user_chat(self, channel: str, role_id: str) -> UserChatTarget:
        """The user's private chat through the role's account on ``channel``.

        Read from the current bindings: among those applying to the account,
        the first with a known private chat through it. Nothing is guessed
        from a bound ID alone, since the chat the send belongs to must be
        known. Raises LookupError when the user has no binding there or has
        no known private chat with this account yet.
        """
        account = self.channel_account(channel, role_id)
        record = account.record
        bound = identities_for_account(self._identities.list(), record)
        if not bound:
            raise LookupError(f"你的用户没有在渠道 {record.plugin_id} 绑定身份")
        for identity in bound:
            chat = identity.chat_for(record.id)
            if chat is not None:
                return UserChatTarget(chat, AccountTarget("private", identity.user_id))
        raise LookupError(
            f"你的用户在渠道 {record.plugin_id} 已绑定身份，但还没有私聊过当前角色"
            "在该渠道的账号，无法直接发给用户"
        )

    def _authorize(self, account: AccountSnapshot, role_id: str) -> AccountAccess:
        """Captures the ownership fence; an account removed since lookup is named
        by its channel only, the account ID goes to the log."""
        try:
            return self._accounts.authorize(account.record.id, role_id)
        except AccountNotFoundError:
            logger.warning("账号 %s 在发起操作前已被移除", account.record.id)
            raise LookupError(
                f"当前角色在渠道 {account.record.plugin_id} 的账号已不可用"
            ) from None

    async def _call(self, plugin_id: str, method: str, payload: dict[str, Any]):
        resolved = self._rpc.resolve(f"plugin.{plugin_id}.{method}")
        if resolved is None or resolved[0] != plugin_id:
            raise RuntimeError(f"插件 {plugin_id} 未提供此能力")
        return await resolved[1](payload)

    def list_channels(self, role_id: str) -> list[dict[str, object]]:
        """This role's loaded channels and live abilities, without account IDs."""
        if not role_id:
            raise PermissionError("需要角色上下文")
        return [
            {
                "channel": account.record.plugin_id,
                "platform": account.record.platform,
                "name": account.record.display_name,
                "online": account.runtime_active and account.connection == "online",
                "connection": account.connection,
                "capabilities": sorted(account.capabilities),
                "error": account.error,
            }
            for account in self._accounts.list(role_id=role_id)
        ]

    async def targets(
        self, channel: str, role_id: str, kind: str, group_id: str, member_id: str
    ) -> dict[str, Any]:
        """Return the plugin's actual directory coverage or lookup limitation."""
        account = self.channel_account(channel, role_id)
        account_id = account.record.id
        access = self._authorize(account, role_id)
        if not kind.strip():
            raise ValueError("查询类型不能为空")
        result = await self._call(
            account.record.plugin_id,
            ACCOUNT_TARGETS_METHOD,
            {
                "account_id": account_id,
                "kind": kind,
                "group_id": group_id,
                "member_id": member_id,
            },
        )
        if not self._accounts.validate_access(access):
            raise PermissionError("账号归属或连接状态已变化")
        if not isinstance(result, dict):
            raise RuntimeError("插件目标查询未返回有效结果")
        return result

    def _begin(
        self,
        *,
        role_id: str,
        account_id: str,
        channel: str,
        target: AccountTarget,
        source: str,
    ) -> AccountDeliveryAttempt:
        return self._ledger.begin(
            role_id=role_id,
            account_id=account_id,
            target_kind=target.kind,
            target_id=target.id,
            target_options={
                "channel": channel.strip(),
                "message_thread_id": target.message_thread_id,
                "group_id": target.group_id,
                "mention_ids": list(target.mention_ids),
            },
            source=source,
        )

    async def send(
        self,
        channel: str,
        role_id: str,
        target: AccountTarget,
        message: str,
        *,
        source: str = "passive_tool",
        media: list[str] | None = None,
    ) -> AccountSendReceipt:
        """Persist an attempt before sending, then record a real receipt or failure.

        ``media`` holds image attachments (local paths or http(s) URLs) that
        the plugin sends with the text; either may be empty, not both.

        Every attempt is recorded, including one the role has no account for
        on ``channel`` (with an empty account ID). Once the platform returns
        a receipt the send is recorded and returned as sent; an invalid
        plugin snapshot is only logged and left out.
        """
        try:
            account = self.channel_account(channel, role_id)
        except Exception as exc:
            rejected = self._begin(
                role_id=role_id,
                account_id="",
                channel=channel,
                target=target,
                source=source,
            )
            self._ledger.mark_failed(rejected.attempt_id, type(exc).__name__)
            raise
        account_id = account.record.id
        attempt = self._begin(
            role_id=role_id,
            account_id=account_id,
            channel=channel,
            target=target,
            source=source,
        )
        try:
            if not message.strip() and not media:
                raise ValueError("消息和图片不能都为空")
            access = self._authorize(account, role_id)
        except Exception as exc:
            self._ledger.mark_failed(attempt.attempt_id, type(exc).__name__)
            raise

        try:
            result = await self._call(
                account.record.plugin_id,
                ACCOUNT_SEND_METHOD,
                {
                    "account_id": account_id,
                    "message": message,
                    ACCOUNT_SEND_MEDIA_KEY: list(media or ()),
                    **target.to_payload(),
                },
            )
        except asyncio.CancelledError:
            mark_account_delivery_sent()
            self._ledger.mark_uncertain(attempt.attempt_id, "CancelledError")
            raise
        except (TimeoutError, ConnectionError, OSError, UncertainDeliveryError) as exc:
            # The platform may have accepted the payload before the link failed.
            mark_account_delivery_sent()
            self._ledger.mark_uncertain(attempt.attempt_id, type(exc).__name__)
            raise
        except Exception as exc:
            self._ledger.mark_failed(attempt.attempt_id, type(exc).__name__)
            raise
        if not isinstance(result, dict) or not (
            message_id := str(result.get("message_id") or "").strip()
        ):
            mark_account_delivery_sent()
            self._ledger.mark_uncertain(attempt.attempt_id, "MissingReceipt")
            raise RuntimeError("平台未返回回执，发送结果不确定")
        mark_account_delivery_sent()
        self._ledger.mark_sent(attempt.attempt_id, message_id)
        return AccountSendReceipt(
            attempt_id=attempt.attempt_id,
            account_id=account_id,
            channel=account.record.plugin_id,
            target_kind=target.kind,
            target_id=target.id,
            platform_message_id=message_id,
            ownership_current=self._accounts.validate_access(access),
            via_account=delivered_via_account(
                result.get(VIA_ACCOUNT_KEY), account.record
            ),
        )
