from __future__ import annotations

from collections.abc import Iterable

# QQ group chats are addressed as ``gqq:<群号>``; a bare number is a private chat.
QQ_GROUP_PREFIX = "gqq:"


def normalize_chat_id(chat_id: str) -> str:
    """Normalize a transport chat identifier before role binding lookup."""
    return str(chat_id).strip()


def normalize_contact_ids(raw_contacts: Iterable[object]) -> list[str]:
    """Return a binding's contact IDs stripped, non-empty, unique and sorted.

    This is the single normalization of ``allow_from`` shared by the role model
    and every rule that compares a chat ID against its contacts.
    """
    return sorted({str(item).strip() for item in raw_contacts if str(item).strip()})


def normalize_qq_group_chat_id(group_id: str) -> str:
    """Return the canonical QQ group chat identifier used by the runtime."""
    clean_group_id = str(group_id).strip()
    return (
        clean_group_id
        if clean_group_id.startswith(QQ_GROUP_PREFIX)
        else f"{QQ_GROUP_PREFIX}{clean_group_id}"
    )


def is_bare_qq_group_chat_id(chat_id: str, contacts: Iterable[object]) -> bool:
    """Tell whether a ``qq`` binding names a group with a bare (non-``gqq:``) ID.

    A QQ private chat's ID is its sole contact's QQ number, so a bare ID that is
    not exactly that contact can only be a group. The transport would send such
    an ID as a private message, so it is never a valid binding: saving rejects
    it and the v6 manifest migration rewrites legacy ones to ``gqq:``.
    """
    clean_chat_id = normalize_chat_id(chat_id)
    return (
        bool(clean_chat_id)
        and not clean_chat_id.startswith(QQ_GROUP_PREFIX)
        and normalize_contact_ids(contacts) != [clean_chat_id]
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
