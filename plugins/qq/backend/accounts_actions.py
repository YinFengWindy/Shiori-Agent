"""QQ target validation, fresh directory queries, and send receipts."""

from __future__ import annotations

import base64
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .onebot import OneBotDisconnected, OneBotError, OneBotSocket
from shiori_sdk.accounts.targets import UncertainDeliveryError
from shiori_sdk.media import detect_image_mime_from_header

_QQ_ID = re.compile(r"^[1-9][0-9]*$")
# Image types NapCat sends as a QQ picture.
_IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}
)
# Text longer than this many characters, or with more lines than
# FORWARD_MAX_LINES, goes out as a merged forward instead of flooding the chat.
FORWARD_MAX_CHARS = 300
FORWARD_MAX_LINES = 10
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# NapCat's merged-forward action for each plain send action.
_FORWARD_ACTIONS = {
    "send_private_msg": "send_private_forward_msg",
    "send_group_msg": "send_group_forward_msg",
}


def qq_number(value: object, label: str) -> str:
    """Validates an actual QQ number without accepting group chat prefixes."""
    number = str(value or "").strip()
    if not _QQ_ID.fullmatch(number):
        raise ValueError(f"{label}必须是 QQ 数字标识")
    return number


def qq_sender_name(sender: object) -> str:
    """A NapCat sender's display name: group card first, then QQ nickname."""
    if not isinstance(sender, dict):
        return ""
    for field in ("card", "nickname"):
        value = sender.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


@dataclass(frozen=True)
class RepliedMessage:
    """The message a QQ message replies to, as NapCat ``get_msg`` returns it."""

    sender_id: str
    # The sender's group card or nickname; empty when NapCat reports neither.
    sender_name: str
    # The raw CQ-coded text, pictures and nested reply segments included.
    raw_content: str


def qq_chat_target(chat_id: str) -> tuple[str, str]:
    """Converts the QQ channel's private/group chat ID into a platform target."""
    if chat_id.startswith("gqq:"):
        return "group", qq_number(chat_id[4:], "群号")
    return "private", qq_number(chat_id, "QQ 号")


def _cq_escape(value: str) -> str:
    """Escapes a CQ code parameter value (OneBot 11 string message format)."""
    return (
        value.replace("&", "&amp;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace(",", "&#44;")
    )


def qq_image_segment(image: str) -> str:
    """The CQ image code of a local image path or an http(s) URL.

    A local file travels inline as ``base64://`` so NapCat need not share the
    host's file system view; a URL is fetched by NapCat itself. Raises
    ValueError for a missing, unreadable or non-image local file; it runs
    while the message is built, before anything is sent.
    """
    source = image.strip()
    if source.startswith(("http://", "https://")):
        return f"[CQ:image,file={_cq_escape(source)}]"
    path = Path(source).expanduser()
    if not path.is_file():
        raise ValueError(f"QQ 图片文件不存在: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"QQ 图片文件无法读取: {path}") from exc
    if detect_image_mime_from_header(data[:4096]) not in _IMAGE_MIME_TYPES:
        raise ValueError(f"QQ 图片仅支持 PNG、JPEG、WebP、GIF 和 BMP: {path}")
    encoded = base64.b64encode(data).decode("ascii")
    return f"[CQ:image,file=base64://{encoded}]"


def _needs_forward(message: str) -> bool:
    """Whether the text passes the merged-forward threshold.

    Counts the text's characters and its lines (``str.splitlines``); image
    segments are not part of the text and do not count.
    """
    lines = len(message.splitlines())
    return len(message) > FORWARD_MAX_CHARS or lines > FORWARD_MAX_LINES


def _forward_nodes(
    message: str, images: str, sender: tuple[str, str]
) -> list[dict[str, Any]]:
    """Merged-forward nodes: one per blank-line separated paragraph.

    Every node is sent as the account itself (``sender`` is its QQ number
    and name); the image segments go in the last node.
    """
    paragraphs = _PARAGRAPH_BREAK.split(message.strip())
    paragraphs[-1] += images
    user_id, nickname = sender
    return [
        {
            "type": "node",
            "data": {"user_id": user_id, "nickname": nickname, "content": text},
        }
        for text in paragraphs
    ]


async def _send_with_receipt(
    socket: OneBotSocket, action: str, params: dict[str, Any]
) -> str:
    """Sends one NapCat message and returns its real receipt's message ID."""
    try:
        data = await socket.call(action, params)
    except OneBotDisconnected as exc:
        raise UncertainDeliveryError("NapCat 发送连接中断，结果不确定") from exc
    if not isinstance(data, dict):
        raise UncertainDeliveryError("NapCat 发送未返回回执")
    try:
        # A merged forward also returns res_id/forward_id; the message ID is
        # the receipt for the forward message in the chat.
        return qq_number(data.get("message_id"), "消息回执")
    except ValueError as exc:
        raise UncertainDeliveryError("NapCat 发送未返回有效回执") from exc


def _rows(data: object, action: str) -> list[dict[str, Any]]:
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise OneBotError(f"NapCat {action} 返回了无效列表")
    return data


class QQAccountActions:
    """Per-account NapCat actions with no shared target or response cache."""

    def __init__(
        self,
        socket_for: Callable[[str], OneBotSocket],
        ensure_online: Callable[[str], Awaitable[None]],
        sender_for: Callable[[str], tuple[str, str]],
    ) -> None:
        """``sender_for`` gives an account's QQ number and display name."""
        self._socket_for = socket_for
        self._ensure_online = ensure_online
        self._sender_for = sender_for

    async def discover(
        self, account_id: str, kind: str, group_id: str = ""
    ) -> dict[str, Any]:
        """Returns fresh platform IDs and an explicit complete-result boundary."""
        await self._ensure_online(account_id)
        socket = self._socket_for(account_id)
        if kind == "friends":
            action, params, id_field, name_field = (
                "get_friend_list",
                {},
                "user_id",
                "nickname",
            )
        elif kind == "groups":
            action, params, id_field, name_field = (
                "get_group_list",
                {},
                "group_id",
                "group_name",
            )
        elif kind == "members":
            action = "get_group_member_list"
            params = {"group_id": int(qq_number(group_id, "群号"))}
            id_field, name_field = "user_id", "card"
        else:
            raise ValueError("未知 QQ 目标查询类型")
        rows = _rows(await socket.call(action, params), action)
        return {
            "items": [
                {
                    "id": qq_number(row.get(id_field), "目标 ID"),
                    "name": str(row.get(name_field) or row.get("nickname") or ""),
                }
                for row in rows
            ],
            "complete": True,
            "source": "napcat",
        }

    async def group_name(self, account_id: str, group_id: str) -> str:
        """The group's current name from NapCat ``get_group_info``.

        Used while a message from that group is being received, so the
        account's socket is already online and no status check is made.
        """
        socket = self._socket_for(account_id)
        data = await socket.call(
            "get_group_info", {"group_id": int(qq_number(group_id, "群号"))}
        )
        if not isinstance(data, dict) or not isinstance(data.get("group_name"), str):
            raise OneBotError("NapCat get_group_info 未返回群名")
        return data["group_name"]

    async def replied_message(self, account_id: str, message_id: str) -> RepliedMessage:
        """Message ``message_id``'s sender and text, from one NapCat ``get_msg``.

        Used while a message replying to it is being received, so the
        account's socket is already online and no status check is made.
        """
        socket = self._socket_for(account_id)
        data = await socket.call("get_msg", {"message_id": int(message_id)})
        sender = data.get("sender") if isinstance(data, dict) else None
        if not isinstance(sender, dict):
            raise OneBotError("NapCat get_msg 未返回发送者")
        try:
            sender_id = qq_number(sender.get("user_id"), "被回复消息的发送者")
        except ValueError as exc:
            raise OneBotError("NapCat get_msg 未返回有效发送者") from exc
        raw = data.get("raw_message")
        return RepliedMessage(
            sender_id=sender_id,
            sender_name=qq_sender_name(sender),
            raw_content=raw if isinstance(raw, str) else "",
        )

    async def send_target(
        self,
        account_id: str,
        kind: str,
        target_id: str,
        message: str,
        *,
        group_id: str = "",
        mention_ids: tuple[str, ...] = (),
        images: tuple[str, ...] = (),
    ) -> dict[str, str]:
        """Sends via one verified account and requires NapCat's real receipt.

        ``group`` messages start with an @ of each ``mention_ids`` member;
        ``group_member`` is a group temporary session with ``target_id`` in
        group ``group_id``. ``images`` (local paths or http(s) URLs) follow
        the text in the same QQ message, so one receipt covers both.

        Text over the forward threshold goes out as one merged forward
        instead; a group's @s then go first as their own message, and the
        forward's receipt is returned.
        """
        await self._ensure_online(account_id)
        socket = self._socket_for(account_id)
        if not message.strip() and not images:
            raise ValueError("消息和图片不能都为空")
        number = int(qq_number(target_id, "目标 ID"))
        if mention_ids and kind != "group":
            raise ValueError("QQ 只有群消息可以 @ 成员")
        if group_id and kind != "group_member":
            raise ValueError("QQ 只有群临时会话需要群号")
        image_segments = "".join(qq_image_segment(image) for image in images)
        mentions = ""
        if kind == "private":
            action, params = "send_private_msg", {"user_id": number}
        elif kind == "group":
            mentions = " ".join(
                f"[CQ:at,qq={qq_number(member, '@ 成员')}]" for member in mention_ids
            )
            action, params = "send_group_msg", {"group_id": number}
        elif kind == "group_member":
            # NapCat reaches a non-friend group member through a temporary
            # session; its forward action takes the same user and group IDs.
            action, params = "send_private_msg", {
                "user_id": number,
                "group_id": int(qq_number(group_id, "群号")),
            }
        else:
            raise ValueError("QQ 目标类型必须是 private、group 或 group_member")
        if not _needs_forward(message):
            content = message + image_segments
            if mentions:
                content = f"{mentions} {content}"
            message_id = await _send_with_receipt(
                socket, action, {**params, "message": content}
            )
            return {"message_id": message_id}
        nodes = _forward_nodes(message, image_segments, self._sender_for(account_id))
        if mentions:
            # A forward cannot @ anyone, so the @s go first on their own; if
            # that send fails the whole send fails.
            await _send_with_receipt(socket, action, {**params, "message": mentions})
        message_id = await _send_with_receipt(
            socket, _FORWARD_ACTIONS[action], {**params, "messages": nodes}
        )
        return {"message_id": message_id}
