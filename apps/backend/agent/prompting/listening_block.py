"""群回合的旁听块（#539）。

群回合的前文以本群最近原文为主体：对话历史只含本会话的对话（@ 或回复角色的消息
与角色的回复），本群旁听记录（没有叫角色的群消息）不插进历史，而是整块放在本回合
的 context frame 里，紧挨当前消息。这样系统提示词与对话历史在回合之间保持字节
稳定，旁听窗口滑动不会打断提示词缓存的前缀。

旁听块取最近 ``LISTENING_PROMPT_LIMIT`` 条、合计约 ``LISTENING_PROMPT_CHAR_LIMIT``
字（从最新的往前取），单条超过 ``LISTENING_MESSAGE_CHAR_LIMIT`` 字截断；块内按时间
先后排列，每行带时间。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from shiori_sdk.channels.message_source import USER_SENDER_LABEL, MessageSource
from core.common.text import truncate_text
from core.common.timekit import parse_local_iso

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from conversation.listening_store import GroupListeningStore, ListeningMessage
    from session.manager import SessionManager

# 旁听部分的条数与字数上限，以及单条的截断长度。
LISTENING_PROMPT_LIMIT = 30
LISTENING_PROMPT_CHAR_LIMIT = 3000
LISTENING_MESSAGE_CHAR_LIMIT = 200
# 旁听块的标题，告诉模型这些消息是听到的，没有叫角色。
HEARD_BLOCK_TITLE = "## 群里最近的其他消息（旁听：没有 @ 或回复我，我只是看到了）"


@dataclass(frozen=True)
class HeardLine:
    """进入提示词的一条旁听消息：时间、来源与渲染好的一行。"""

    at: datetime
    source: MessageSource
    text: str


def turn_heard(
    sessions: "SessionManager", view: "ContextView | None"
) -> list[HeardLine]:
    """回合视图 ``view`` 的旁听消息：外部回合取所在会话的，其余为空。

    成员来源（速记）与回合前的预算估算经由这里，只有外部回合才读 ``sessions``
    的旁听记录。
    """
    if view is None or not view.is_external:
        return []
    return heard_for_prompt(sessions.conversation_store.listening, view.thread_id)


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


def render_heard_block(lines: Sequence[HeardLine]) -> str:
    """旁听块的文本：标题加按时间先后排列的各行；没有旁听消息时为空串。"""
    if not lines:
        return ""
    return "\n".join([HEARD_BLOCK_TITLE, *(line.text for line in lines)])


def _heard_line(heard: "ListeningMessage") -> HeardLine:
    source = heard.message_source()
    sender = USER_SENDER_LABEL if source.sender_is_user else source.sender_name
    # 发送者昵称是插件可选上报的快照，没报时只写成员 ID，不编一个称呼。
    speaker = f"{sender}（ID {heard.sender_id}）" if sender else f"ID {heard.sender_id}"
    mentions = (
        f"（@ ID {'、'.join(source.mentioned_ids)}）" if source.mentioned_ids else ""
    )
    at = parse_local_iso(heard.timestamp)
    content = truncate_text(heard.content.strip(), LISTENING_MESSAGE_CHAR_LIMIT)
    return HeardLine(
        at=at,
        source=source,
        text=f"[{at.strftime('%m-%d %H:%M')}] {speaker}{mentions}：{content}",
    )
