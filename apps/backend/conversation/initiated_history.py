"""Recent history attached to ``InitiatedMessageCommitted``.

Scene used to ask ``SCENE_HOST.proactive_history`` for this window. The
publisher fills it instead, with the same external-context rule and the same
six-message limit the scene plugin compacted to.
"""

from __future__ import annotations

from pathlib import Path

from agent.core.passive_support import to_history_messages
from conversation.context_scope import history_filter, session_context_view
from shiori_sdk.core.conversation import ConversationMessage

_HISTORY_LIMIT = 6


def initiated_history(
    sessions: object,
    *,
    session_key: str,
    role_id: str,
    thread_id: str,
    limit: int = _HISTORY_LIMIT,
) -> tuple[ConversationMessage, ...] | None:
    """Recent messages, or ``None`` when the thread is external context.

    ``sessions`` is a session manager: ``workspace``, ``get_or_create`` and
    ``history_window``.
    """
    workspace = Path(sessions.workspace)  # type: ignore[attr-defined]
    view = session_context_view(
        workspace,
        session_key=session_key,
        role_id=role_id,
        thread_id=thread_id,
    )
    if view is not None and view.is_external:
        return None
    session = sessions.get_or_create(session_key)  # type: ignore[attr-defined]
    messages = to_history_messages(
        session.history_window(limit, include=history_filter(view))
    )
    return tuple(
        ConversationMessage(
            role=item.role,
            content=item.content,
            tools_used=tuple(item.tools_used),
        )
        for item in messages
    )
