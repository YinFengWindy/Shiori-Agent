from __future__ import annotations

from dataclasses import replace
import mimetypes

from shiori_sdk.messages import InboundMessage
from shiori_sdk.channels.message_source import (
    PERSISTED_USER_CONTENT_KEY,
    REPLY_TO_CONTENT_KEY,
    REPLY_TO_MEDIA_KEY,
    REPLY_TO_SENDER_ID_KEY,
    REPLY_TO_SENDER_IS_USER_KEY,
    REPLY_TO_SENDER_NAME_KEY,
    USER_SENDER_LABEL,
)

# How the turn names a quoted message the role itself sent.
SELF_REPLY_SENDER_LABEL = "你自己"
# The quoted text the turn shows for a quoted message that is only pictures.
QUOTED_IMAGE_PLACEHOLDER = "[图片]"


def build_inbound_text_with_reply_context(
    *,
    user_text: str,
    reply_text: str,
    reply_sender: str = "",
) -> str:
    """Build the inbound text that lets the agent see a referenced message."""

    current_text = str(user_text or "").strip()
    referenced_text = str(reply_text or "").strip()
    if not referenced_text:
        return current_text

    sender_label = str(reply_sender or "").strip()
    reply_header = (
        f"被回复消息（来自 {sender_label}）：" if sender_label else "被回复消息："
    )
    return (
        "【你正在回复一条历史消息】\n"
        f"{reply_header}\n"
        f"{referenced_text}\n\n"
        "【你当前新消息】\n"
        f"{current_text}"
    ).strip()


def _reply_sender_label(message: InboundMessage, own_id: str, sender_name: str) -> str:
    """「来自 X」: the role itself, the desktop user, else 「昵称（ID …）」 / 「ID …」."""
    sender_id = str(message.metadata.get(REPLY_TO_SENDER_ID_KEY) or "").strip()
    if not sender_id:
        return ""
    if sender_id == own_id:
        return SELF_REPLY_SENDER_LABEL
    if message.metadata.get(REPLY_TO_SENDER_IS_USER_KEY) is True:
        return USER_SENDER_LABEL
    return f"{sender_name}（ID {sender_id}）" if sender_name else f"ID {sender_id}"


def with_reply_quote(
    message: InboundMessage,
    *,
    own_id: str,
    text: str,
    sender_name: str,
    media: list[str],
    has_pictures: bool = False,
) -> InboundMessage:
    """``message``, as routed to a turn, with the message it quotes (#555).

    The turn sees the quoted ``text`` (never truncated) wrapped around the
    message's own by ``build_inbound_text_with_reply_context``, and the quoted
    attachments ``media`` (local files) ahead of its own. The session stores
    only the message's own text and attachments; the quote is kept in metadata
    (``REPLY_TO_CONTENT_KEY``, ``REPLY_TO_SENDER_NAME_KEY``,
    ``REPLY_TO_MEDIA_KEY``) beside the quoted sender's ID
    (``REPLY_TO_SENDER_ID_KEY``) the plugin set before routing. ``own_id`` is
    the receiving account's platform ID: a quote of it is the role's own.
    ``has_pictures`` says the quoted message had pictures even when none of
    them could be fetched into ``media``: the quote then still reads 「[图片]」.
    A quote with neither text nor pictures leaves the message as it is.
    """
    text = text.strip()
    sender_name = sender_name.strip()
    if not text and not media and not has_pictures:
        return message
    metadata = {
        **message.metadata,
        # Pictures that could not be fetched still show as 「[图片]」.
        REPLY_TO_CONTENT_KEY: text or ("" if media else QUOTED_IMAGE_PLACEHOLDER),
        PERSISTED_USER_CONTENT_KEY: message.content,
    }
    if sender_name:
        metadata[REPLY_TO_SENDER_NAME_KEY] = sender_name
    image_count = sum(
        (mimetypes.guess_type(path)[0] or "").startswith("image/") for path in media
    )
    file_count = len(media) - image_count
    placeholder = "[附件]" if image_count and file_count else "[文件]"
    reply_text = text or (placeholder if file_count else QUOTED_IMAGE_PLACEHOLDER)
    if media:
        metadata[REPLY_TO_MEDIA_KEY] = list(media)
        # The quoted files lead the turn's attachments; say so, or the model
        # cannot tell them from the message's own.
        if file_count:
            counts = ([f"{image_count} 张图片"] if image_count else []) + [
                f"{file_count} 个文件"
            ]
            reply_text += (
                f"\n（被回复消息附带 {'、'.join(counts)}，"
                f"即本条附件中的前 {len(media)} 项）"
            )
        else:
            reply_text += (
                f"\n（被回复消息附带 {len(media)} 张图片，"
                f"即本条附件中的前 {len(media)} 张）"
            )
    return replace(
        message,
        content=build_inbound_text_with_reply_context(
            user_text=message.content,
            reply_text=reply_text,
            reply_sender=_reply_sender_label(message, own_id, sender_name),
        ),
        media=[*media, *message.media],
        metadata=metadata,
    )
