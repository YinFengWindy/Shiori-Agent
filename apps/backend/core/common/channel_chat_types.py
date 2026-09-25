"""Session types a channel declares, and the chat IDs each type accepts.

A channel plugin's manifest may list the session types its chat IDs name
(private chat, group chat), each with an optional internal prefix such as QQ's
``gqq:``. Role bindings store the chosen type next to the chat ID; the
declarations let the core check that the two agree without knowing any channel
by name.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

# Every role binding names one of these; the host-owned desktop session is private.
ChatType = Literal["private", "group"]
CHAT_TYPE_PRIVATE: ChatType = "private"
CHAT_TYPE_GROUP: ChatType = "group"
CHAT_TYPES: tuple[ChatType, ...] = (CHAT_TYPE_PRIVATE, CHAT_TYPE_GROUP)


def parse_chat_type(value: object, field_name: str) -> ChatType:
    """Returns ``value`` as a session type; raises ``ValueError`` naming ``field_name``.

    The single check shared by manifest declarations and role bindings.
    """
    for chat_type in CHAT_TYPES:
        if value == chat_type:
            return chat_type
    raise ValueError(f"{field_name} 必须是 {' / '.join(CHAT_TYPES)} 之一")


@dataclass(frozen=True)
class ChatTypeDeclaration:
    """One session type a channel supports, as declared in its plugin manifest.

    ``prefix`` is prepended to the user-entered number to form the stored chat
    ID (``gqq:`` + group number); ``None`` stores the number as is.
    ``chat_id_label`` / ``chat_id_hint`` only feed the binding form.
    """

    type: ChatType
    label: str
    chat_id_label: str
    chat_id_hint: str | None = None
    prefix: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Returns the JSON-compatible bridge representation."""
        return {
            "type": self.type,
            "label": self.label,
            "chat_id_label": self.chat_id_label,
            "chat_id_hint": self.chat_id_hint,
            "prefix": self.prefix,
        }


# Channel name -> declared session types; channels without declarations are absent.
ChatTypeDeclarations = Mapping[str, tuple[ChatTypeDeclaration, ...]]


def validate_chat_id_for_type(
    chat_id: str,
    chat_type: ChatType,
    declarations: tuple[ChatTypeDeclaration, ...],
) -> None:
    """Rejects a chat ID that does not match its binding's declared session type.

    The selected type must be declared. A declared prefix must lead the chat ID
    exactly once and be followed by a non-empty remainder (an ID in whatever
    form the channel uses, not necessarily digits) that itself carries no
    declared prefix, so a pasted ``gqq:gqq:123`` is refused. A chat ID carrying
    another declared type's prefix names that other type. ``chat_id`` is
    already stripped. Raises ``ValueError`` with the expected form.
    """
    selected = next((item for item in declarations if item.type == chat_type), None)
    if selected is None:
        supported = "、".join(item.label for item in declarations)
        raise ValueError(f"该渠道不支持此会话类型，可选：{supported}")
    if selected.prefix is not None:
        remainder = chat_id[len(selected.prefix) :].strip()
        if (
            not chat_id.startswith(selected.prefix)
            or not remainder
            or any(
                item.prefix is not None and remainder.startswith(item.prefix)
                for item in declarations
            )
        ):
            raise ValueError(
                f"{selected.label}会话 ID 必须是 {selected.prefix}<{selected.chat_id_label}>"
                "，前缀只写一次"
            )
    # Manifest parsing rejects prefixes nested in one another, so a match here
    # can only mean the chat ID names the other type.
    for other in declarations:
        if (
            other is not selected
            and other.prefix is not None
            and chat_id.startswith(other.prefix)
        ):
            raise ValueError(
                f"会话 ID {chat_id} 是{other.label}格式，与所选的{selected.label}不符"
            )
