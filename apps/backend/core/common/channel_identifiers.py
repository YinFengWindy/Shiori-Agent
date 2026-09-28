from __future__ import annotations

# QQ group chats are addressed as ``gqq:<群号>``; a bare number is a private chat.
QQ_GROUP_PREFIX = "gqq:"


def normalize_sender_id(raw_sender: object) -> str:
    """Return one sender ID or alias stripped, without a leading ``@``.

    Users write Telegram usernames as ``@alice``; the platform reports
    ``alice``, so the marker never takes part in matching.
    """
    return str(raw_sender).strip().removeprefix("@").strip()
