from __future__ import annotations

from pathlib import Path
from typing import Any

from bus.events import InboundMessage, OutboundMessage
from core.common.channel_directory import ChannelDirectory
from core.common.channel_identifiers import chat_ids_equal, normalize_sender_id
from core.accounts import AccountRegistry
from conversation.service import ConversationService, LegacySessionDescriptor
from core.roles.services import RoleAggregateService
from core.roles.store import RoleStore
from core.roles.role_runtime import RoleExecutionContext


class ChannelHub:
    """Coordinates role-bound channel routing and delivery bookkeeping."""

    def __init__(
        self,
        service: RoleAggregateService,
        *,
        channel_directory: ChannelDirectory | None = None,
        accounts: AccountRegistry | None = None,
    ) -> None:
        self._service = service
        self._channel_directory = channel_directory or ChannelDirectory()
        self._accounts = accounts or service.repository.store.accounts
        self._conversation = ConversationService(
            service.sessions._session_manager,
            binding_resolver=service.bindings.resolve_role_id,
        )

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        *,
        session_manager,
        channel_directory: ChannelDirectory | None = None,
        role_store: RoleStore | None = None,
    ) -> "ChannelHub":
        """Builds a hub from the current workspace and shared session manager."""
        return cls(
            RoleAggregateService.from_runtime(
                workspace=workspace,
                role_store=role_store or RoleStore(workspace),
                session_manager=session_manager,
            ),
            channel_directory=channel_directory,
        )

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        """Maps a bound channel message onto the role session and source thread."""
        metadata = dict(message.metadata or {})
        if message.channel == "desktop":
            return message
        if "account_id" in metadata:
            routed = self.route_account_inbound(message)
            if routed is None:
                raise PermissionError("接收账号未授权此消息")
            return routed
        if not str(message.sender or "").strip():
            raise ValueError("渠道消息缺少 sender_id")

        resolved_role_id = self._service.bindings.resolve_role_id(
            message.channel,
            message.chat_id,
        )
        role_id = str(metadata.get("role_id") or "").strip()
        if role_id and role_id != resolved_role_id:
            raise ValueError("渠道消息角色与绑定角色不匹配")
        role_id = resolved_role_id
        return self._route_for_role(message, role_id, metadata)

    def route_account_inbound(self, message: InboundMessage) -> InboundMessage | None:
        """Admits only an owned, live receiving account under its response rules."""
        metadata = dict(message.metadata or {})
        account_id = str(metadata.get("account_id") or "").strip()
        if not account_id or not str(message.sender or "").strip():
            return None
        try:
            account = self._accounts.get(account_id)
        except KeyError:
            return None
        role_id = account.record.role_id
        if (
            not role_id
            or not account.plugin_enabled
            or not account.runtime_active
            or account.connection != "online"
            or account.record.platform != message.channel.split(":", 1)[0]
        ):
            return None
        rules = account.record.response_rules
        chat_type = str(metadata.get("chat_type") or "private").lower()
        group = chat_type in {"group", "supergroup"}
        if group:
            override = next(
                (item for item in rules.group_rules if item.chat_id == message.chat_id),
                None,
            )
            if not rules.group_enabled or (
                override is not None and not override.enabled
            ):
                return None
            require_mention = (
                override.require_mention
                if override is not None
                else rules.require_mention
            )
            blocked = rules.blocked_sender_ids + (
                override.blocked_sender_ids if override is not None else ()
            )
            if require_mention and not metadata.get("mentioned"):
                return None
        else:
            if not rules.private_enabled:
                return None
            blocked = rules.blocked_sender_ids
        alias = normalize_sender_id(str(metadata.get("username") or "")).lower()
        if message.sender in blocked or (
            alias
            and any(alias == normalize_sender_id(item).lower() for item in blocked)
        ):
            return None
        claimed_role = str(metadata.get("role_id") or "").strip()
        if claimed_role and claimed_role != role_id:
            return None
        metadata["source"] = "role_account"
        return self._route_for_role(message, role_id, metadata)

    def _route_for_role(
        self, message: InboundMessage, role_id: str, metadata: dict[str, Any]
    ) -> InboundMessage:
        role = self._service.repository.get_required(role_id)
        thread = self._conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{message.channel}:{message.chat_id}",
                role_id=role_id,
                channel=message.channel,
                chat_id=message.chat_id,
                metadata=metadata,
            )
        )
        session_key = self._service.sessions.derive_session_key(role.id)
        self._service.sessions.open_by_role(role)
        external_message_id = str(
            metadata.get("external_message_id") or metadata.get("message_id") or ""
        ).strip()
        if external_message_id:
            metadata["external_message_id"] = external_message_id
            if self._conversation.has_external_message(thread.id, external_message_id):
                metadata["conversation_duplicate"] = True
        metadata["role_id"] = role_id
        metadata["thread_id"] = thread.id
        metadata["session_key_override"] = session_key
        metadata.setdefault("context_channel", message.channel)
        metadata.setdefault("context_chat_id", message.chat_id)
        metadata["transport_channel"] = message.channel
        metadata["transport_chat_id"] = message.chat_id
        metadata["sender_id"] = message.sender
        if "chat_type" not in metadata:
            metadata["chat_type"] = self._channel_directory.default_chat_type(
                message.channel
            )
        metadata.setdefault("source", "role_channel_binding")
        context = RoleExecutionContext.create(
            role=role,
            thread_id=thread.id,
            transport_channel=message.channel,
            transport_chat_id=message.chat_id,
            source=str(metadata["source"]),
            work_kind="passive_turn",
            request_id=external_message_id,
        )
        metadata.update(context.to_metadata())
        return InboundMessage(
            channel=message.channel,
            sender=message.sender,
            chat_id=message.chat_id,
            content=message.content,
            timestamp=message.timestamp,
            media=list(message.media),
            metadata=metadata,
        )

    def is_sender_allowed(
        self,
        *,
        channel: str,
        chat_id: str,
        sender_id: str,
        sender_alias: str = "",
        account_id: str = "",
    ) -> bool:
        """Admits a sender of a bound session unless its binding blacklists them.

        Unbound sessions are rejected. A private chat's sender is its partner,
        and private bindings carry no blacklist, so they are always admitted.
        A blacklist entry matches the sender ID exactly, or ``sender_alias``
        (a Telegram username) case-insensitively; a leading ``@`` is ignored
        on both sides.
        """
        if account_id:
            try:
                account = self._accounts.get(account_id)
            except KeyError:
                return False
            if (
                not account.record.role_id
                or not account.plugin_enabled
                or not account.runtime_active
                or account.connection != "online"
                or account.record.platform != channel.split(":", 1)[0]
            ):
                return False
            rules = account.record.response_rules
            alias = normalize_sender_id(sender_alias).lower()
            return sender_id not in rules.blocked_sender_ids and not (
                alias
                and any(
                    alias == normalize_sender_id(item).lower()
                    for item in rules.blocked_sender_ids
                )
            )
        binding = self._service.bindings.get_binding(channel, chat_id)
        if binding is None:
            return False
        role = self._service.repository.get_required(binding.role_id)
        config = next(
            item
            for item in role.channel_bindings
            if item.channel == channel
            and chat_ids_equal(channel, item.chat_id, chat_id)
        )
        if sender_id in config.blocked_senders:
            return False
        alias = normalize_sender_id(sender_alias).lower()
        return not (
            alias and any(alias == entry.lower() for entry in config.blocked_senders)
        )

    def is_sender_blocked(
        self,
        *,
        channel: str,
        chat_id: str,
        sender_id: str,
        sender_alias: str = "",
    ) -> bool:
        """Whether a bound session's blacklist names this sender.

        Unlike ``is_sender_allowed`` an unbound session blocks nobody: the only
        caller is ``/chatid``, which must answer before a session is bound.
        """
        return self.has_binding(channel, chat_id) and not self.is_sender_allowed(
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_alias=sender_alias,
        )

    def has_binding(self, channel: str, chat_id: str) -> bool:
        """Returns whether a channel session belongs to any role."""
        return self._service.bindings.get_binding(channel, chat_id) is not None

    def resolve_runtime_session_key(self, channel: str, chat_id: str) -> str:
        """Resolves a channel control action to its bound role session."""

        role_id = self._service.bindings.resolve_role_id(channel, chat_id)
        return self._service.sessions.derive_session_key(role_id)

    def resolve_account_runtime_session_key(self, account_id: str) -> str:
        """Resolves account control actions through the current live owner."""
        account = self._accounts.get(account_id)
        role_id = account.record.role_id
        if (
            not role_id
            or not account.plugin_enabled
            or not account.runtime_active
            or account.connection != "online"
        ):
            raise PermissionError("接收账号未授权控制会话")
        return self._service.sessions.derive_session_key(role_id)

    def mark_delivery(
        self,
        message: OutboundMessage,
        *,
        default_channel: str,
        delivery_status: str,
        external_message_id: str = "",
    ) -> dict[str, Any] | None:
        """Writes delivery state to the message this outbound was committed as.

        An outbound without a committed message id returns early without
        touching or validating anything: there is no row to mark, so the
        source-thread validation below never applies to it. Everything else
        is validated against its source thread before the write.
        """
        committed_message_id = str(message.committed_message_id or "").strip()
        if not committed_message_id:
            # 兜底/降级出站消息（如错误提示、重试失败通知）从未落库，没有对应的
            # 已提交消息可打标记；不能退化成"猜线程内最新一条 assistant 消息"，
            # 否则会把投递状态错误地写到一条完全无关的历史消息上。
            # 提前到所有 thread 校验之前：没有 id 就没什么可标记的，那些校验
            # 不该对着一条从未落库的消息执行——调用方（渠道 outbound 的
            # finally 块）没有 try 包裹，这里抛出的 ValueError 会直接冒泡。
            return None
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        role_id = str(metadata.get("role_id") or "").strip()
        if not role_id:
            try:
                role_id = self._service.bindings.resolve_role_id(
                    default_channel,
                    message.chat_id,
                )
            except KeyError:
                return None
        session_key = self._service.sessions.derive_session_key(role_id)
        override = str(metadata.get("session_key_override") or "").strip()
        if override and override != session_key:
            raise ValueError("出站消息不能使用渠道独立运行时会话")
        thread_id = str(metadata.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("出站消息缺少 thread_id")
        thread = self._conversation.get_thread(thread_id)
        if thread is None or thread.role_id != role_id:
            raise ValueError("出站消息 thread_id 不属于当前角色")
        if (
            thread.channel != message.channel
            or thread.external_thread_id != message.chat_id
        ):
            raise ValueError("出站消息 transport target 与 thread_id 不匹配")
        return self._service.sessions.mark_message_delivery(
            session_key,
            message_id=committed_message_id,
            thread_id=thread_id,
            delivery_status=delivery_status,
            external_message_id=external_message_id,
        )
