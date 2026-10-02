"""Lifecycle boundaries for compaction of persisted, complete conversation turns."""

from __future__ import annotations

from typing import Any

from session.manager.helpers import starts_turn


def retention_stop(
    messages: list[dict[str, Any]], members: list[int], keep_turns: int
) -> tuple[int, int]:
    """Select a complete-turn prefix, keeping interrupted exchanges and inputs whole.

    A persisted tool_chain belongs to its final assistant reply. Native tool calls
    additionally require all matching results before a final reply closes the turn.
    Consecutive user inputs before that completion remain one lifecycle. Internal
    recovery prompts only occur in the protected in-memory request suffix.
    """
    completed: list[tuple[int, int]] = []
    current: int | None = None
    complete = False
    pending_tools: set[str] = set()
    for index in members:
        message = messages[index]
        if starts_turn(message) and (current is None or complete):
            if current is not None:
                completed.append((current, index))
            current = index
            complete = False
        if message.get("tool_calls"):
            pending_tools.update(str(call["id"]) for call in message["tool_calls"])
            complete = False
        if message.get("role") == "tool":
            pending_tools.discard(str(message.get("tool_call_id", "")))
        if message.get("role") == "assistant" and not message.get("tool_calls"):
            complete = not pending_tools and not bool(
                (message.get("metadata") or {}).get("interrupted_turn")
            )
    if current is not None and complete:
        completed.append((current, len(messages)))
    if not completed:
        return (members[0] if members else len(messages)), 0
    retained = min(keep_turns, len(completed))
    return (completed[-retained][0] if retained else completed[-1][1]), retained
