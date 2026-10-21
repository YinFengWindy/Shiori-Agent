"""Persist completed background work independently of its cancellable role report."""

from typing import Any

from core.common.cancellation import finish_started
from session.manager import SessionManager
from session.manager.models import build_session_message


async def commit_background_fact(
    manager: SessionManager,
    session_key: str,
    *,
    metadata: dict[str, Any],
    call_id: str,
    name: str,
    arguments: dict[str, Any],
    result: str,
) -> None:
    """Keep the original result as a tool fact; no unseen assistant text is stored."""
    fact = build_session_message(
        "assistant",
        "",
        metadata=metadata,
        tool_chain=[
            {
                "text": "",
                "calls": [
                    {
                        "call_id": call_id,
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                    }
                ],
            }
        ],
    )
    await finish_started(
        manager.append_messages(
            manager.get_or_create(session_key),
            [fact],
            pending_messages=True,
        )
    )
