from __future__ import annotations

# QQ group chats are addressed as ``gqq:<群号>``; a bare number is a private chat.
QQ_GROUP_PREFIX = "gqq:"


def normalize_chat_id(chat_id: str) -> str:
    """Normalize a transport chat identifier before role binding lookup."""
    return str(chat_id).strip()


def normalize_qq_group_chat_id(group_id: str) -> str:
    """Return the canonical QQ group chat identifier used by the runtime."""
    clean_group_id = str(group_id).strip()
    return (
        clean_group_id
        if clean_group_id.startswith(QQ_GROUP_PREFIX)
        else f"{QQ_GROUP_PREFIX}{clean_group_id}"
    )


def chat_ids_equal(channel: str, left: str, right: str) -> bool:
    """Compare role and runtime chat IDs exactly within ``channel``.

    No channel has cross-form aliases. In particular bare and ``gqq:`` QQ IDs
    are distinct: the transport sends a bare ID as a private message, so
    treating it as the group would authorize a send that can never reach the
    bound group. ``channel`` stays in the signature so every call site names
    the namespace it compares in.
    """
    _ = channel
    return normalize_chat_id(left) == normalize_chat_id(right)
