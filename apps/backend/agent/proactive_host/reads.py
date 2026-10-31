"""Host facts a proactive tick reads through ``PROACTIVE_HOST``.

Candidate chats and the last user message per thread feed target selection;
the role session's history feeds the tick's context and duplicate check.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from conversation.context_scope import user_context_view
from conversation.service import desktop_chat_id
from core.common.channel_directory import DESKTOP_CHANNEL
from core.roles.bound_chats import role_bound_chats
from session.manager.helpers import role_session_key
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.core.proactive_host import (
    CandidateChat,
    ProactiveHistoryMessage,
    RecentTurnMessage,
)
from shiori_sdk.prompting import is_context_frame


def candidate_chats(core: Any, role_id: str) -> tuple[CandidateChat, ...]:
    """Desktop first, then private chats with the bound user.

    Does not consult the proactive switch. A missing role raises ``KeyError``.
    """
    store = core.role_runtime_registry.repository.store
    if store.get_role(role_id) is None:
        raise KeyError(f"角色不存在: {role_id}")
    return (
        CandidateChat(channel=DESKTOP_CHANNEL, chat_id=desktop_chat_id(role_id)),
        *(
            CandidateChat(channel=chat.channel, chat_id=chat.chat_id)
            for _, _, chat in role_bound_chats(store, role_id)
        ),
    )


def last_user_message_at(
    core: Any, role_id: str, channel: str, chat_id: str
) -> datetime | None:
    """When the user last wrote in that chat, or None.

    A naive legacy timestamp was written in local time and is converted.
    """
    raw = core.session_manager.conversation_store.last_user_message_at(
        network_thread_id(role_id, channel, chat_id)
    )
    if raw is None:
        return None
    return datetime.fromisoformat(raw).astimezone()


def recent_messages(
    core: Any, role_id: str, *, limit: int
) -> tuple[RecentTurnMessage, ...]:
    """Recent user-context turns on the role session, oldest first."""
    session = core.session_manager.get_or_create(role_session_key(role_id))
    view = user_context_view(core.session_manager.workspace, role_id)
    results: list[RecentTurnMessage] = []
    for message in session.history_window(limit, include=view.includes):
        if message.get("role") not in ("user", "assistant"):
            continue
        if not message.get("content"):
            continue
        content = str(message.get("content", ""))
        if is_context_frame(content):
            continue
        results.append(
            RecentTurnMessage(
                role=str(message["role"]),
                content=content[:200],
                timestamp=str(message.get("timestamp", "")),
            )
        )
    return tuple(results)


def recent_proactive_messages(
    core: Any, role_id: str, *, limit: int
) -> tuple[ProactiveHistoryMessage, ...]:
    """The role session's recent proactive messages, oldest first."""
    session = core.session_manager.get_or_create(role_session_key(role_id))
    found: list[ProactiveHistoryMessage] = []
    for message in reversed(session.messages):
        if message.get("role") != "assistant":
            continue
        if not message.get("proactive") or not message.get("content"):
            continue
        found.append(
            ProactiveHistoryMessage(
                content=str(message["content"]),
                timestamp=_parse_timestamp(message.get("timestamp")),
            )
        )
        if len(found) >= limit:
            break
    return tuple(reversed(found))


def _parse_timestamp(raw: object) -> datetime | None:
    """ISO timestamp, or None. A naive legacy value was local time."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed
