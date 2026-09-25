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

# Every role binding names one of these; the host-owned desktop session is private.
CHAT_TYPE_PRIVATE = "private"
CHAT_TYPE_GROUP = "group"
CHAT_TYPES = (CHAT_TYPE_PRIVATE, CHAT_TYPE_GROUP)


@dataclass(frozen=True)
class ChatTypeDeclaration:
    """One session type a channel supports, as declared in its plugin manifest.

    ``prefix`` is prepended to the user-entered number to form the stored chat
    ID (``gqq:`` + group number); ``None`` stores the number as is.
    ``chat_id_label`` / ``chat_id_hint`` only feed the binding form.
    """

    type: str
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
    chat_type: str,
    declarations: tuple[ChatTypeDeclaration, ...],
) -> None:
    """Rejects a chat ID that does not match its binding's declared session type.

    The selected type must be declared; a declared prefix must lead the chat ID
    and be followed by a number; a chat ID carrying another declared type's
    prefix names that other type. ``chat_id`` is already stripped. Raises
    ``ValueError`` with the expected form.
    """
    selected = next((item for item in declarations if item.type == chat_type), None)
    if selected is None:
        supported = "、".join(item.label for item in declarations)
        raise ValueError(f"该渠道不支持此会话类型，可选：{supported}")
    if selected.prefix is not None:
        number = chat_id[len(selected.prefix) :]
        if not chat_id.startswith(selected.prefix) or not number.strip():
            raise ValueError(
                f"{selected.label}会话 ID 必须是 {selected.prefix}<{selected.chat_id_label}>"
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
