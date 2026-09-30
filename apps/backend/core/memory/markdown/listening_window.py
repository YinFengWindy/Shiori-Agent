"""旁听整理（#541）的窗口：何时整理哪一批旁听记录，以及它们喂给整理时的形状。

触发规则（按群、只看该群游标之后尚未整理的记录）：

- 满 ``LISTENING_BATCH_SIZE`` 条：整理最早的这一批；
- 跨天：不足一批时，整理本地日期（入库时记下的 ``day``）早于「今天」的记录，
  今天的留待下一批。「今天」取检查时的本地日期与最新一条记录的日期中较晚的
  那个（平台时间略超前时也不会把当天记录算成前一天）。检查发生在该群有记录
  入库时，以及定时的全量检查（``listening_trigger``），所以前一天剩下不足一批
  的记录不必等到这个群再有人说话。

旁听记录转换成与角色会话已存消息同样的字典（``listening_session_message``），
这样用户本人段 / 外部段的拆分、外部段按会话分组与渲染都直接复用角色会话整理
的那一套，不另写一条整理流程。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from conversation.listening_store import ListeningMessage

# 每群旁听记录满多少条整理一次，也是一次整理最多处理的条数。
LISTENING_BATCH_SIZE = 50


def select_listening_batch(
    pending: Sequence[ListeningMessage], *, today: date
) -> list[ListeningMessage]:
    """按触发规则从未整理的记录里选出这次要整理的一批；还不到时候为空。

    ``pending`` 是游标之后最早的至多 ``LISTENING_BATCH_SIZE`` 条记录（按 ``seq``）；
    不足一批时它就是全部未整理记录。``today`` 是检查时的本地日期。
    """
    if len(pending) >= LISTENING_BATCH_SIZE:
        return list(pending[:LISTENING_BATCH_SIZE])
    if not pending:
        return []
    # ``day`` 是 ISO 日期串，按字符串比较即按日期先后。
    current_day = max(today.isoformat(), pending[-1].day)
    return [message for message in pending if message.day < current_day]


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
