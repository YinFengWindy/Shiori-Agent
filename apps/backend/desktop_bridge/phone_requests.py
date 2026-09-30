"""Bridge commands behind the role's phone: its channel conversations."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Callable, Collection, Iterable
from typing import Any, Protocol

from conversation.context_scope import user_context_threads
from conversation.listening import GroupListeningControl
from conversation.models import ThreadRecord
from conversation.service import ConversationService
from core.accounts import AccountRegistry, account_for_channel
from core.channel_avatars import AvatarIndex, ChannelAvatarStore
from core.common.message_source import MessageSource
from core.identity import BoundUserSenders, UserIdentity, UserIdentityStore
from desktop_bridge.session_presenter import MESSAGE_PAGE_SIZE, message_preview
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
        limit: int = MESSAGE_PAGE_SIZE,
    ) -> dict[str, Any]: ...


def _message_time(message: dict[str, Any]) -> datetime:
    """When a stored message was sent; a naive legacy time is local time."""
    return datetime.fromisoformat(str(message["timestamp"])).astimezone()


def required_text(payload: dict[str, Any], key: str) -> str:
    """A required, non-blank string field of a request payload."""
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} 不能为空")
    return value


def role_bound_senders(
    role_id: str, *, accounts: AccountRegistry, identities: Iterable[UserIdentity]
) -> BoundUserSenders:
    """The bindings ``identities`` (as read once) over the role's accounts."""
    return BoundUserSenders(
        identities=tuple(identities),
        accounts=tuple(account.record for account in accounts.list(role_id=role_id)),
    )


def phone_message(
    message: dict[str, Any],
    *,
    session_key: str,
    is_user: Callable[[str | None], bool],
    avatars: AvatarIndex,
    listened: bool = False,
) -> dict[str, Any]:
    """One conversation message as the phone's chat page shows it.

    ``sender`` is ``role`` for the role's own messages and ``other`` for
    anyone else in the chat. For others, ``sender_id`` and ``sender_name``
    are the platform ID and the name snapshot stored with the message (None
    when unrecorded), and ``sender_is_user`` is ``is_user(sender_id)``: whether
    that sender is the desktop user under the bindings as they are now (like
    the context split, #482), not the flag stored when the message arrived.
    ``sender_avatar_abs`` is the sender's cached platform avatar file (#514),
    None for the role or when none is cached. ``listened`` marks a row of the
    group's listening records (#538) rather than of the role's conversation.
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
        "sender_is_user": not from_role and is_user(source.sender_id),
        "sender_avatar_abs": (
            None if from_role else avatars.sender(source.channel, source.sender_id)
        ),
        "content": str(message.get("content") or ""),
        "media": [str(item) for item in message.get("media") or []],
        "timestamp": str(message.get("timestamp") or ""),
        "listened": listened,
    }


class DesktopPhoneRequestHandler:
    """Reads one role's channel conversations for the phone panel.

    ``phone.conversations.list`` with ``role_id`` returns ``{"conversations":
    [...]}``, newest message first. Each row names its thread, the role's
    account that carries it (``account_id`` is None when the role no longer
    has an account on that platform), channel, ``chat_type`` (``group`` /
    ``private`` as the thread's messages recorded it, None when none did),
    the contact's ``display_name`` (group name for a group,
    the sender's name for a private chat), ``avatar_abs`` (the cached group
    avatar, or the other person's for a private chat; None when none is
    cached), whether it is the bound user's private chat, whether it is a
    group that can be listened to (``listening_supported``: its channel's
    plugin declares support, #538), and a ``last_message`` preview. Threads
    with no stored message are left out; the desktop conversation never
    appears.

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
        avatars: ChannelAvatarStore,
        listening: GroupListeningControl,
    ) -> None:
        self._conversations = conversations
        self._accounts = accounts
        self._identities = identities
        self._messages = messages
        self._avatars = avatars
        self._listening = listening

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one phone request; None for methods it does not own."""
        if method == "phone.conversations.list":
            role_id = required_text(payload, "role_id")
            return {
                "conversations": self._conversation_rows(
                    role_id, self._conversations.list_network_threads(role_id)
                )
            }
        if method == "phone.conversation.messages":
            role_id, thread = self.role_thread(payload)
            before_seq = payload.get("before_seq")
            return self._messages_page(
                role_id,
                thread,
                before_seq=int(before_seq) if before_seq is not None else None,
                limit=int(payload.get("limit") or MESSAGE_PAGE_SIZE),
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
                "messages": self.phone_messages(role_id, thread, by_thread[thread.id]),
            }
            for thread in threads
        ]

    def role_thread(self, payload: dict[str, Any]) -> tuple[str, ThreadRecord]:
        """The request's ``role_id`` and ``thread_id``, one of the role's channel conversations."""
        role_id = required_text(payload, "role_id")
        thread = self._role_thread(role_id, required_text(payload, "thread_id"))
        if thread is None:
            raise ValueError("会话不属于该角色")
        return role_id, thread

    def _role_thread(self, role_id: str, thread_id: str) -> ThreadRecord | None:
        return self._conversations.role_channel_thread(role_id, thread_id)

    def phone_messages(
        self,
        role_id: str,
        thread: ThreadRecord,
        messages: Iterable[dict[str, Any]],
        *,
        listened: bool = False,
    ) -> list[dict[str, Any]]:
        """``messages`` of ``thread`` (stored-message shape) as ``phone_message`` rows.

        The user's messages are those whose sender a current binding
        recognises on the role's account carrying the thread; with no such
        account, none are. The bindings and the avatar index are read once
        for all rows.
        """
        session_key = role_session_key(role_id)
        bound = role_bound_senders(
            role_id, accounts=self._accounts, identities=self._identities.list()
        )
        avatars = self._avatars.index()

        def is_user(sender_id: str | None) -> bool:
            return sender_id is not None and bound.recognises(thread.channel, sender_id)

        return [
            phone_message(
                message,
                session_key=session_key,
                is_user=is_user,
                avatars=avatars,
                listened=listened,
            )
            for message in messages
        ]

    def _messages_page(
        self, role_id: str, thread: ThreadRecord, *, before_seq: int | None, limit: int
    ) -> dict[str, Any]:
        page = self._messages.thread_messages_page(
            role_session_key(role_id), thread.id, before_seq=before_seq, limit=limit
        )
        return {
            "thread_id": thread.id,
            "messages": self.phone_messages(role_id, thread, page["messages"]),
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
        avatars = self._avatars.index()
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
            account = account_for_channel(
                (item.record for item in accounts), thread.channel
            )
            rows.append(
                (
                    _message_time(message),
                    {
                        "thread_id": thread.id,
                        "account_id": account.id if account else None,
                        "channel": thread.channel,
                        "chat_type": chat_types[thread.id],
                        "display_name": contact.display_name,
                        "avatar_abs": avatars.chat(
                            thread.channel, thread.external_thread_id
                        ),
                        "is_user_chat": thread.id in user_threads.bound_chat_thread_ids,
                        "listening_supported": self._listening.supports(
                            thread.channel, chat_types[thread.id]
                        ),
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
