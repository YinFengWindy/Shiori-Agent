"""Selection and consolidation rollback rules for persisted passive turns."""

from typing import Any

from shiori_sdk.prompting import is_context_frame


def _is_context_frame_message(message: dict[str, Any]) -> bool:
    if message.get("role") != "user":
        return False
    return is_context_frame(str(message.get("content") or ""))


def _is_real_user_message(message: dict[str, Any]) -> bool:
    return message.get("role") == "user" and not _is_context_frame_message(message)


def _is_passive_assistant_message(message: dict[str, Any]) -> bool:
    return message.get("role") == "assistant" and not bool(message.get("proactive"))


def _find_last_passive_turn(
    messages: list[dict[str, Any]],
) -> tuple[list[int], int, int] | None:
    for assistant_index in range(len(messages) - 1, -1, -1):
        if not _is_passive_assistant_message(messages[assistant_index]):
            continue
        user_index = assistant_index - 1
        while user_index >= 0 and _is_context_frame_message(messages[user_index]):
            user_index -= 1
        if user_index < 0 or not _is_real_user_message(messages[user_index]):
            continue
        delete_indices = list(range(user_index, assistant_index + 1))
        context_index = user_index - 1
        while context_index >= 0 and _is_context_frame_message(messages[context_index]):
            delete_indices.insert(0, context_index)
            context_index -= 1
        return delete_indices, user_index, assistant_index
    return None


def _compute_rollback_index(
    messages: list[dict[str, Any]],
    *,
    delete_indices: list[int],
    old_last_consolidated: int,
    rollback_source_ids: list[str],
) -> int:
    if not delete_indices:
        return min(old_last_consolidated, len(messages))
    rollback_index = min(delete_indices)
    if rollback_index >= old_last_consolidated:
        return min(old_last_consolidated, len(messages) - len(delete_indices))
    source_ids = {
        str(item).strip() for item in rollback_source_ids if str(item).strip()
    }
    for index, message in enumerate(messages):
        msg_id = str(message.get("id") or "").strip()
        if msg_id and msg_id in source_ids:
            rollback_index = min(rollback_index, index)
    return max(0, min(rollback_index, old_last_consolidated))
