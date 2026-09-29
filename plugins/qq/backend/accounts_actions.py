"""QQ target validation, fresh directory queries, and send receipts."""

from __future__ import annotations

import base64
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .onebot import OneBotDisconnected, OneBotError, OneBotSocket
from core.accounts.target_contract import UncertainDeliveryError

_QQ_ID = re.compile(r"^[1-9][0-9]*$")


def qq_number(value: object, label: str) -> str:
    """Validates an actual QQ number without accepting group chat prefixes."""
    number = str(value or "").strip()
    if not _QQ_ID.fullmatch(number):
        raise ValueError(f"{label}必须是 QQ 数字标识")
    return number


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
    host's file system view; a URL is fetched by NapCat itself.
    """
    source = image.strip()
    if source.startswith(("http://", "https://")):
        return f"[CQ:image,file={_cq_escape(source)}]"
    path = Path(source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"QQ 图片文件不存在: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"[CQ:image,file=base64://{encoded}]"


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
    ) -> None:
        self._socket_for = socket_for
        self._ensure_online = ensure_online

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
        content = message + "".join(qq_image_segment(image) for image in images)
        if kind == "private":
            action, params = "send_private_msg", {"user_id": number, "message": content}
        elif kind == "group":
            mentions = "".join(
                f"[CQ:at,qq={qq_number(member, '@ 成员')}] " for member in mention_ids
            )
            action, params = "send_group_msg", {
                "group_id": number,
                "message": mentions + content,
            }
        elif kind == "group_member":
            # NapCat reaches a non-friend group member through a temporary session.
            action, params = "send_private_msg", {
                "user_id": number,
                "group_id": int(qq_number(group_id, "群号")),
                "message": content,
            }
        else:
            raise ValueError("QQ 目标类型必须是 private、group 或 group_member")
        try:
            data = await socket.call(action, params)
        except OneBotDisconnected as exc:
            raise UncertainDeliveryError("NapCat 发送连接中断，结果不确定") from exc
        if not isinstance(data, dict):
            raise UncertainDeliveryError("NapCat 发送未返回回执")
        try:
            message_id = qq_number(data.get("message_id"), "消息回执")
        except ValueError as exc:
            raise UncertainDeliveryError("NapCat 发送未返回有效回执") from exc
        return {"message_id": message_id}
