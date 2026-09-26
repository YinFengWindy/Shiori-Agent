"""QQ target validation, fresh directory queries, and send receipts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from .onebot import OneBotError, OneBotSocket

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
        self, account_id: str, kind: str, target_id: str, message: str
    ) -> dict[str, str]:
        """Sends via one verified account and requires NapCat's real receipt."""
        await self._ensure_online(account_id)
        socket = self._socket_for(account_id)
        if not message.strip():
            raise ValueError("消息不能为空")
        number = int(qq_number(target_id, "目标 ID"))
        if kind == "private":
            action, params = "send_private_msg", {"user_id": number, "message": message}
        elif kind == "group":
            action, params = "send_group_msg", {"group_id": number, "message": message}
        else:
            raise ValueError("QQ 目标类型必须是 private 或 group")
        data = await socket.call(action, params)
        if not isinstance(data, dict):
            raise OneBotError("NapCat 发送未返回回执")
        message_id = qq_number(data.get("message_id"), "消息回执")
        return {"message_id": message_id}
