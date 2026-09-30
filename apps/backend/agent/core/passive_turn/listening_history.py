"""群回合前文里的旁听部分（#539）。

群回合的前文以本群最近原文为主体：角色会话里本群的对话（@ 或回复角色的消息与
角色的回复）照常取整理游标之后的历史窗口，本群旁听记录（没有叫角色的群消息）
取最近 ``LISTENING_PROMPT_LIMIT`` 条、合计约 ``LISTENING_PROMPT_CHAR_LIMIT`` 字，
单条超过 ``LISTENING_MESSAGE_CHAR_LIMIT`` 字截断。两部分按时间合并：旁听消息按
先后成段插在对话之间，每段是一条带标记的 user 消息，不改动对话本身。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.common.message_source import USER_SENDER_LABEL, MessageSource
from session.manager.helpers import truncate_text

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike
    from conversation.listening_store import GroupListeningStore, ListeningMessage

# 旁听部分的条数与字数上限，以及单条的截断长度。
LISTENING_PROMPT_LIMIT = 30
LISTENING_PROMPT_CHAR_LIMIT = 3000
LISTENING_MESSAGE_CHAR_LIMIT = 200
# 每段旁听消息开头的标记，告诉模型这些消息没有叫角色。
HEARD_SEGMENT_HEADER = "[旁听：群里没有 @ 或回复我的消息，我只是看到了]"


@dataclass(frozen=True)
class HeardLine:
    """进入提示词的一条旁听消息：时间、来源与渲染好的一行。"""

    at: datetime
    source: MessageSource
    text: str


def local_time(value: str) -> datetime:
    """消息记录的 ISO 时间；不带时区的旧记录按本地时区理解。"""
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.astimezone()


def heard_for_prompt(
    listening: "GroupListeningStore", thread_id: str
) -> list[HeardLine]:
    """群 ``thread_id`` 进入本回合提示词的旁听消息，旧的在前。

    从最新的一条往前取，至多 ``LISTENING_PROMPT_LIMIT`` 条；每条截到
    ``LISTENING_MESSAGE_CHAR_LIMIT`` 字，放不进 ``LISTENING_PROMPT_CHAR_LIMIT``
    字的预算时更早的都不取。没有旁听记录的会话（未开旁听的群、陌生私聊）为空。
    """
    lines: list[HeardLine] = []
    budget = LISTENING_PROMPT_CHAR_LIMIT
    for heard in reversed(listening.recent(thread_id, limit=LISTENING_PROMPT_LIMIT)):
        line = _heard_line(heard)
        if len(line.text) + 1 > budget:
            break
        budget -= len(line.text) + 1
        lines.append(line)
    lines.reverse()
    return lines


def merge_heard_into_history(
    session: "SessionLike",
    window: Sequence[dict[str, Any]],
    heard: Sequence[HeardLine],
) -> list[dict[str, Any]]:
    """把旁听消息按时间并入历史窗口 ``window``（原始消息），返回 LLM 消息。

    窗口按轮切段（每段从一条 user 或主动消息起），旁听消息插在比它晚的第一段
    之前；比整段窗口都晚的放在最后，紧挨着本回合的消息。
    """
    out: list[dict[str, Any]] = []
    pending = list(heard)
    for turn in _turns(window):
        started_at = local_time(str(turn[0]["timestamp"]))
        # ``pending`` 旧的在前，早于这一轮的是它的一段前缀。
        cut = next(
            (index for index, line in enumerate(pending) if line.at >= started_at),
            len(pending),
        )
        if cut:
            out.append(_heard_segment(pending[:cut]))
            pending = pending[cut:]
        out.extend(session.render_history(turn))
    if pending:
        out.append(_heard_segment(pending))
    return out


def _turns(window: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """把原始消息按轮切开：user 消息与主动消息各起一轮。"""
    turns: list[list[dict[str, Any]]] = []
    for message in window:
        if not turns or _starts_turn(message):
            turns.append([])
        turns[-1].append(message)
    return turns


def _starts_turn(message: Mapping[str, Any]) -> bool:
    role = message.get("role")
    return role == "user" or (role == "assistant" and bool(message.get("proactive")))


def _heard_line(heard: "ListeningMessage") -> HeardLine:
    source = MessageSource.from_metadata(
        {"message_source": heard.source}, session_key=""
    )
    sender = USER_SENDER_LABEL if source.sender_is_user else source.sender_name
    speaker = f"{sender or '群友'}（ID {heard.sender_id}）"
    mentions = (
        f"（@ ID {'、'.join(source.mentioned_ids)}）" if source.mentioned_ids else ""
    )
    at = local_time(heard.timestamp)
    content = truncate_text(heard.content.strip(), LISTENING_MESSAGE_CHAR_LIMIT)
    return HeardLine(
        at=at,
        source=source,
        text=f"[{at.strftime('%m-%d %H:%M')}] {speaker}{mentions}：{content}",
    )


def _heard_segment(lines: Sequence[HeardLine]) -> dict[str, Any]:
    return {
        "role": "user",
        "content": "\n".join([HEARD_SEGMENT_HEADER, *(line.text for line in lines)]),
    }
