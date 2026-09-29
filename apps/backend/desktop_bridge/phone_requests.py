"""Bridge commands behind the role's phone: its channel conversations."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Collection, Iterable
from typing import Any, Protocol

from conversation.context_scope import user_context_threads
from conversation.models import ThreadRecord
from conversation.service import ConversationService
from core.accounts import AccountRegistry, AccountSnapshot, account_serves_channel
from core.common.message_source import MessageSource
from core.identity import UserIdentityStore
from desktop_bridge.session_presenter import message_preview
from session.manager.helpers import role_session_key
from session.manager.models import message_thread_id

# Bridge event carrying messages newly committed to one of a role's conversations.
PHONE_CONVERSATION_UPDATED = "phone.conversation.updated"


class ThreadMessages(Protocol):
    """Reads a role session's stored messages by thread (the session presenter)."""

    def newest_thread_messages(
        self, session_key: str, thread_ids: Collection[str]
    ) -> dict[str, dict[str, Any]]: ...

    def thread_messages_page(
        self,
        session_key: str,
        thread_id: str,
        *,
        before_seq: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]: ...


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


def _required(payload: dict[str, Any], key: str) -> str:
    """A required, non-blank string field of a request payload."""
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} 不能为空")
    return value


def phone_message(message: dict[str, Any], *, session_key: str) -> dict[str, Any]:
    """One conversation message as the phone's chat page shows it.

    ``sender`` is ``role`` for the role's own messages and ``other`` for
    anyone else in the chat. For others, ``sender_id`` and ``sender_name``
    are the platform ID and the name snapshot stored with the message (None
    when unrecorded), and ``sender_is_user`` whether that sender was the
    desktop user's bound identity when the message arrived.
    """
    from_role = message.get("role") == "assistant"
    source = MessageSource.from_metadata(
        message.get("metadata") or {}, session_key=session_key
    )
    seq = message.get("seq")
    return {
        "id": str(message.get("id") or ""),
        "seq": int(seq) if seq is not None else None,
        "sender": "role" if from_role else "other",
        "sender_id": None if from_role else source.sender_id,
        "sender_name": None if from_role else source.sender_name,
        "sender_is_user": not from_role and source.sender_is_user,
        "content": str(message.get("content") or ""),
        "media": [str(item) for item in message.get("media") or []],
        "timestamp": str(message.get("timestamp") or ""),
    }


class DesktopPhoneRequestHandler:
    """Reads one role's channel conversations for the phone panel.

    ``phone.conversations.list`` with ``role_id`` returns ``{"conversations":
    [...]}``, newest message first. Each row names its thread, the role's
    account that carries it (``account_id`` is None when the role no longer
    has an account on that platform), channel, ``chat_type`` (``group`` /
    ``private`` as the thread's messages recorded it, None when none did),
    the contact's ``display_name`` (group name for a group,
    the sender's name for a private chat), whether it is the bound user's
    private chat, and a ``last_message`` preview. Threads with no stored
    message are left out; the desktop conversation never appears.

    ``phone.conversation.messages`` with ``role_id``, ``thread_id`` and
    optional ``before_seq`` / ``limit`` returns one page of that
    conversation (``phone_message`` rows, oldest first) with ``has_more``
    and the ``next_before_seq`` cursor for the older page. Only the role's
    current channel conversations can be read.
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
            role_id = _required(payload, "role_id")
            return {
                "conversations": self._conversation_rows(
                    role_id, self._conversations.list_network_threads(role_id)
                )
            }
        if method == "phone.conversation.messages":
            role_id = _required(payload, "role_id")
            thread = self._role_thread(role_id, _required(payload, "thread_id"))
            if thread is None:
                raise ValueError("会话不属于该角色")
            before_seq = payload.get("before_seq")
            return self._messages_page(
                role_id,
                thread.id,
                before_seq=int(before_seq) if before_seq is not None else None,
                limit=int(payload.get("limit") or 50),
            )
        return None

    def conversation_updates(
        self, role_id: str, messages: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """``phone.conversation.updated`` payloads for newly committed messages.

        ``messages`` are the exact rows a commit wrote to the role's session;
        those in the role's current channel conversations are grouped by
        conversation, each with its refreshed list row. Rows of any other
        thread (the desktop conversation, scheduled tasks) are ignored.
        """
        session_key = role_session_key(role_id)
        by_thread: dict[str, list[dict[str, Any]]] = {}
        for message in messages:
            by_thread.setdefault(message_thread_id(message), []).append(message)
        threads = [
            thread
            for thread_id in by_thread
            if (thread := self._role_thread(role_id, thread_id)) is not None
        ]
        if not threads:
            return []
        rows = {
            row["thread_id"]: row for row in self._conversation_rows(role_id, threads)
        }
        return [
            {
                "role_id": role_id,
                "thread_id": thread.id,
                "conversation": rows[thread.id],
                "messages": [
                    phone_message(message, session_key=session_key)
                    for message in by_thread[thread.id]
                ],
            }
            for thread in threads
        ]

    def _role_thread(self, role_id: str, thread_id: str) -> ThreadRecord | None:
        """``thread_id`` when it is one of the role's current channel conversations."""
        if not thread_id:
            return None
        thread = self._conversations.get_thread(thread_id)
        if (
            thread is None
            or thread.role_id != role_id
            or thread.thread_kind != "network"
            or thread.archived
        ):
            return None
        return thread

    def _messages_page(
        self, role_id: str, thread_id: str, *, before_seq: int | None, limit: int
    ) -> dict[str, Any]:
        session_key = role_session_key(role_id)
        page = self._messages.thread_messages_page(
            session_key, thread_id, before_seq=before_seq, limit=limit
        )
        return {
            "thread_id": thread_id,
            "messages": [
                phone_message(message, session_key=session_key)
                for message in page["messages"]
            ],
            "has_more": page["has_more"],
            "next_before_seq": page["next_before_seq"],
        }

    def _conversation_rows(
        self, role_id: str, threads: list[ThreadRecord]
    ) -> list[dict[str, Any]]:
        """List rows of ``threads`` that have messages, newest message first."""
        session_key = role_session_key(role_id)
        accounts = self._accounts.list(role_id=role_id)
        user_threads = user_context_threads(role_id, self._identities.list())
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
