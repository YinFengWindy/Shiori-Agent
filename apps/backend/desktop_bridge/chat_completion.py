from __future__ import annotations

from bus.events_lifecycle import TurnCommitted
from desktop_bridge.models import BridgeEvent


def build_chat_terminal_event(
    *,
    request_id: str,
    turn_id: str,
    session_key: str,
    role_id: str,
    committed: TurnCommitted | None = None,
    failure_message: str = "",
    failure_detail: str = "",
) -> BridgeEvent:
    """Completes an uncommitted turn as an error without inventing a persisted reply.

    `failure_detail` is an optional user-safe summary of the cause (exception
    type and one scrubbed line) that the desktop shows behind 「详情」.
    """

    payload = {"session_key": session_key, "turn_id": turn_id}
    if committed is None:
        return BridgeEvent(
            id=request_id,
            type="event",
            method="chat.error",
            payload={
                **payload,
                "message": failure_message or "回合未完成，请重试。",
                **({"detail": failure_detail} if failure_detail else {}),
            },
        )
    return BridgeEvent(
        id=request_id,
        type="event",
        method="chat.done",
        payload={
            **payload,
            "role_id": role_id,
            "reply": committed.assistant_response,
            "thinking": committed.thinking,
            "tools_used": list(committed.tools_used),
            "total_tokens": committed.total_tokens,
            "thinking_duration_ms": committed.thinking_duration_ms,
        },
    )
