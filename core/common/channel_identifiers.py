from __future__ import annotations


def normalize_chat_id(channel: str, chat_id: str) -> str:
    """Normalize transport chat identifiers before role binding lookup."""
    clean_channel = str(channel).strip()
    clean_chat_id = str(chat_id).strip()
    if clean_channel == "qq" and clean_chat_id.startswith("gqq:"):
        return f"gqq:{clean_chat_id[4:]}"
    return clean_chat_id


def normalize_qq_group_chat_id(group_id: str) -> str:
    """Return the canonical QQ group chat identifier used by the runtime."""
    clean_group_id = str(group_id).strip()
    return clean_group_id if clean_group_id.startswith("gqq:") else f"gqq:{clean_group_id}"


def chat_ids_equal(channel: str, left: str, right: str) -> bool:
    """Compare role and runtime chat IDs, accepting legacy bare QQ group IDs."""
    normalized_left = normalize_chat_id(channel, left)
    normalized_right = normalize_chat_id(channel, right)
    if channel == "qq" and (
        normalized_left.startswith("gqq:") or normalized_right.startswith("gqq:")
    ):
        return normalized_left.removeprefix("gqq:") == normalized_right.removeprefix("gqq:")
    return normalized_left == normalized_right
