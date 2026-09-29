"""Session store 共享的消息列投影与筛选条件。"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

_MESSAGE_SELECT_COLUMNS = (
    "id, session_key, seq, role, content, tool_chain, extra, ts, "
    "thread_id, sender_role, media, external_message_id, delivery_status"
)


def thread_filter_sql(
    thread_ids: Collection[str] | None, column: str = "thread_id"
) -> tuple[str, list[str]]:
    """把消息限定在 ``thread_ids`` 这些会话里的 SQL 条件及其参数。

    None 表示不限定；空字符串代表没有 thread 的旧消息；空集合不匹配任何消息。
    """
    if thread_ids is None:
        return "1", []
    named = sorted({thread_id for thread_id in thread_ids if thread_id})
    clauses = [f"{column} IN ({','.join('?' for _ in named)})"] if named else []
    if "" in thread_ids:
        clauses.append(f"({column} IS NULL OR {column} = '')")
    return (f"({' OR '.join(clauses)})" if clauses else "0"), named


# 角色会话的两类上下文，划分规则见 ``conversation.context_scope``。每类各持一个
# 整理游标（#523），会话存储、提交与撤销都按它存取，所以定义在会话层。
ContextScope = Literal["user", "external"]
CONTEXT_SCOPES: tuple[ContextScope, ...] = ("user", "external")

# 角色会话按上下文的整理游标存在会话元数据的这个键下，
# 值为 {上下文: 游标}。``last_consolidated`` 列始终等于其中的最小值，即“此前一定
# 已整理”的低水位。旧会话没有这个键时，各上下文的游标都取 ``last_consolidated``。
CONTEXT_CURSORS_METADATA_KEY = "context_cursors"
