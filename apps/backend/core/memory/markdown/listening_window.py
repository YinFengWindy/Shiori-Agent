"""旁听整理（#541）的窗口：何时整理哪一批旁听记录，以及它们喂给整理时的形状。

触发规则（按群、只看该群游标之后尚未整理的记录）：

- 满 ``LISTENING_BATCH_SIZE`` 条：整理最早的这一批；
- 跨天：未整理记录里最早一条与最新一条的本地日期不同（即入库时的 ``day``，
  消息时间换算到本地时区的日期），就整理最新那天之前各天的记录，最新那天的
  记录留待下一批。换言之，一天结束后、这个群下一次有消息入库时，前一天剩下
  不足一批的记录被整理。

旁听记录转换成与角色会话已存消息同样的字典（``listening_session_message``），
这样用户本人段 / 外部段的拆分、外部段按会话分组与渲染都直接复用角色会话整理
的那一套，不另写一条整理流程。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from conversation.listening_store import ListeningMessage

# 每群旁听记录满多少条整理一次，也是一次整理最多处理的条数。
LISTENING_BATCH_SIZE = 50


def listening_day(message: ListeningMessage) -> date:
    """记录入库时的本地日期：时间戳本身带入库时的本地时区，取其日期。"""
    return datetime.fromisoformat(message.timestamp).date()


def select_listening_batch(
    pending: Sequence[ListeningMessage],
) -> list[ListeningMessage]:
    """按触发规则从未整理的记录里选出这次要整理的一批；还不到时候为空。

    ``pending`` 是游标之后最早的至多 ``LISTENING_BATCH_SIZE`` 条记录（按 ``seq``）。
    不足一批时它就是全部未整理记录，最后一条是最新的，据此判断跨天。
    """
    if len(pending) >= LISTENING_BATCH_SIZE:
        return list(pending[:LISTENING_BATCH_SIZE])
    if not pending:
        return []
    newest_day = listening_day(pending[-1])
    return [message for message in pending if listening_day(message) < newest_day]


def listening_session_message(message: ListeningMessage) -> dict[str, Any]:
    """一条旁听记录在整理里的形状：与角色会话里群友发来的一条已存消息相同。

    发送者、群名与是否用户本人都在来源快照里，``belongs_to_user`` 与成员判定
    据此工作；角色从不出现在旁听记录里，所以都是 ``user`` 消息。
    """
    return {
        "id": message.id,
        "role": "user",
        "content": message.content,
        "timestamp": message.timestamp,
        "thread_id": message.thread_id,
        "metadata": {"message_source": dict(message.source)},
    }
