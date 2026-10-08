"""Plain-text danmaku extracted from ``DANMU_MSG`` commands.

Field positions (blivedm ``models/web.py`` ``DanmakuMessage.from_command`` and
a 2026-10 capture from a live room): ``info[1]`` text, ``info[2][0]`` sender
uid, ``info[2][1]`` sender name, ``info[0][12]`` danmaku type (0 plain text,
1 emoticon, 2 voice) and ``info[0][15].extra`` a JSON string whose ``id_str``
is the platform's message id. ``id_str`` is the dedupe key: it is the same
on a repeated delivery or a reconnect replay and differs between messages
even when their text is equal.

Only ``DANMU_MSG`` itself is a viewer message of this room; suffixed variants
(``DANMU_MSG:4:0:2:2:2:0``) are the same command, while ``DANMU_MSG_MIRROR``
mirrors another room and is ignored. A sender uid of 0 with a masked name
(``"ab***"``) is what an anonymous connection receives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_DANMU_CMD = "DANMU_MSG"
_PLAIN_TEXT_TYPE = 0


class DanmakuFormatError(ValueError):
    """A ``DANMU_MSG`` whose fields are not where the protocol puts them."""


class AnonymousDanmaku(DanmakuFormatError):
    """The sender identity was masked: the connection is not logged in."""


@dataclass(frozen=True)
class Danmaku:
    """One viewer's plain-text message; ``message_id`` is the platform id."""

    message_id: str
    uid: int
    uname: str
    text: str


def parse_danmaku(command: dict[str, Any]) -> Danmaku | None:
    """Return the plain-text danmaku of ``command``, or ``None`` for anything else.

    Raises ``DanmakuFormatError`` when a ``DANMU_MSG`` is malformed and
    ``AnonymousDanmaku`` when its sender identity is masked.
    """
    cmd = command.get("cmd")
    if not isinstance(cmd, str) or cmd.partition(":")[0] != _DANMU_CMD:
        return None
    try:
        info = command["info"]
        meta, text, user = info[0], info[1], info[2]
        if meta[12] != _PLAIN_TEXT_TYPE:
            return None
        extra = json.loads(meta[15]["extra"])
        message_id, uid, uname = extra["id_str"], user[0], user[1]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise DanmakuFormatError(f"弹幕格式无法识别: {error!r}") from error
    if not isinstance(text, str) or not text.strip():
        return None
    if not isinstance(message_id, str) or not message_id.strip():
        raise DanmakuFormatError("弹幕缺少 id_str")
    if not isinstance(uid, int) or not isinstance(uname, str) or not uname.strip():
        raise DanmakuFormatError("弹幕发送者信息无效")
    if uid == 0:
        raise AnonymousDanmaku("弹幕发送者身份被匿名化，B 站登录未生效")
    return Danmaku(message_id=message_id, uid=uid, uname=uname, text=text)
