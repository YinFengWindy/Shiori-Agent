from __future__ import annotations

from collections.abc import Iterable

# QQ group chats are addressed as ``gqq:<群号>``; a bare number is a private chat.
QQ_GROUP_PREFIX = "gqq:"


def normalize_chat_id(chat_id: str) -> str:
    """Normalize a transport chat identifier before role binding lookup."""
    return str(chat_id).strip()


def normalize_sender_id(raw_sender: object) -> str:
    """Return one sender ID or alias stripped, without a leading ``@``.

    Users write Telegram usernames as ``@alice``; the platform reports
    ``alice``, so the marker never takes part in matching.
    """
    return str(raw_sender).strip().removeprefix("@").strip()


def normalize_sender_ids(raw_senders: Iterable[object]) -> list[str]:
    """Return sender IDs normalized by ``normalize_sender_id``, non-empty, unique, sorted.

    The single normalization of a group binding's ``blocked_senders``, also
    applied to the pre-v8 ``allow_from`` contacts the upgrade rules read.
    """
    return sorted({normalize_sender_id(item) for item in raw_senders} - {""})


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

    Before v6 a QQ private chat's ID was its sole contact's QQ number, so a bare
    ID that is not exactly that contact can only be a legacy group. The
    transport sends such an ID as a private message; the v6 manifest migration
    rewrites these to ``gqq:``. Upgrade-only: since v7 bindings carry an
    explicit ``chat_type`` checked against the channel's declaration.
    """
    clean_chat_id = normalize_chat_id(chat_id)
    return (
        bool(clean_chat_id)
        and not clean_chat_id.startswith(QQ_GROUP_PREFIX)
        and normalize_sender_ids(contacts) != [clean_chat_id]
    )


def bound_qq_group_for_bare_id(chat_id: str, qq_chat_ids: Iterable[str]) -> str | None:
    """Return the bound ``gqq:`` group a bare QQ ID was meant to name, if any.

    Before v6 a bare number compared equal to its ``gqq:`` group, so config and
    proactive targets may still name a bound group by its bare number. Returns
    ``gqq:<id>`` when ``chat_id`` is bare and that group is among the role's
    ``qq`` binding chat IDs; otherwise ``None``. Callers decide whether a bare
    ID that is also a bound private chat should still count.
    """
    clean_chat_id = normalize_chat_id(chat_id)
    if not clean_chat_id or clean_chat_id.startswith(QQ_GROUP_PREFIX):
        return None
    group_chat_id = normalize_qq_group_chat_id(clean_chat_id)
    bound = {normalize_chat_id(item) for item in qq_chat_ids}
    return group_chat_id if group_chat_id in bound else None


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
