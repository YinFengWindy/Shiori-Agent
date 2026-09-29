"""Bridge commands behind the role's phone: its channel conversations."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Collection
from typing import Any, Protocol

from conversation.context_scope import user_context_threads
from conversation.models import ThreadRecord
from conversation.service import ConversationService
from core.accounts import AccountRegistry, AccountSnapshot, account_serves_channel
from core.common.message_source import MessageSource
from core.identity import UserIdentityStore
from desktop_bridge.session_presenter import message_preview
from session.manager.helpers import role_session_key


class ThreadMessages(Protocol):
    """Reads the newest stored message of each thread (the session presenter)."""

    def newest_thread_messages(
        self, session_key: str, thread_ids: Collection[str]
    ) -> dict[str, dict[str, Any]]: ...


def _message_time(message: dict[str, Any]) -> datetime:
    """When a stored message was sent; a naive legacy time is local time."""
    return datetime.fromisoformat(str(message["timestamp"])).astimezone()


def _account_for(
    accounts: list[AccountSnapshot], thread: ThreadRecord
) -> AccountSnapshot | None:
    """The role's account whose plugin carries ``thread``'s channel, if any."""
    return next(
        (
            account
            for account in accounts
            if account_serves_channel(account.record, thread.channel)
        ),
        None,
    )


class DesktopPhoneRequestHandler:
    """Lists one role's channel conversations for the phone panel.

    ``phone.conversations.list`` with ``role_id`` returns ``{"conversations":
    [...]}``, newest message first. Each row names its thread, the role's
    account that carries it (``account_id`` is None when the role no longer
    has an account on that platform), channel, ``chat_type`` (``group`` /
    ``private`` as the thread's messages recorded it, None when none did),
    the contact's ``display_name`` (group name for a group,
    the sender's name for a private chat), whether it is the bound user's
    private chat, and a ``last_message`` preview. Threads with no stored
    message are left out; the desktop conversation never appears.
    """

    def __init__(
        self,
        *,
        conversations: ConversationService,
        accounts: AccountRegistry,
        identities: UserIdentityStore,
        messages: ThreadMessages,
    ) -> None:
        self._conversations = conversations
        self._accounts = accounts
        self._identities = identities
        self._messages = messages

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one phone request; None for methods it does not own."""
        if method == "phone.conversations.list":
            role_id = str(payload.get("role_id") or "").strip()
            if not role_id:
                raise ValueError("role_id 不能为空")
            return {"conversations": self._list_conversations(role_id)}
        return None

    def _list_conversations(self, role_id: str) -> list[dict[str, Any]]:
        session_key = role_session_key(role_id)
        accounts = self._accounts.list(role_id=role_id)
        user_threads = user_context_threads(role_id, self._identities.list())
        threads = self._conversations.list_network_threads(role_id)
        thread_ids = [thread.id for thread in threads]
        # Newest messages, contacts and chat types are each read in one query.
        newest = self._messages.newest_thread_messages(session_key, thread_ids)
        contacts = self._conversations.contacts_by_id(role_id)
        chat_types = self._conversations.thread_chat_types(thread_ids)
        rows: list[tuple[datetime, dict[str, Any]]] = []
        for thread in threads:
            message = newest.get(thread.id)
            if message is None:
                continue
            contact = contacts.get(thread.contact_id)
            if contact is None:
                raise LookupError(f"会话 {thread.id} 缺少联系人 {thread.contact_id}")
            source = MessageSource.from_metadata(
                message.get("metadata") or {}, session_key=session_key
            )
            account = _account_for(accounts, thread)
            rows.append(
                (
                    _message_time(message),
                    {
                        "thread_id": thread.id,
                        "account_id": account.record.id if account else None,
                        "channel": thread.channel,
                        "chat_type": chat_types[thread.id],
                        "display_name": contact.display_name,
                        "is_user_chat": thread.id in user_threads.bound_chat_thread_ids,
                        "last_message": {
                            **message_preview(message),
                            "sender_name": (
                                source.sender_name
                                if message.get("role") == "user"
                                else None
                            ),
                        },
                    },
                )
            )
        rows.sort(key=lambda row: row[0], reverse=True)
        return [row for _, row in rows]
