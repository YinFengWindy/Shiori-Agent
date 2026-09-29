"""Session store 共享的消息列投影与筛选条件。"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, Literal

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

# 角色会话按上下文的整理游标存在 sessions 表的这两列，只由整理提交、撤销与整段
# 重写消息写入，普通的会话保存（upsert_session）不碰它们。``last_consolidated`` 列
# 是其中的较小值，即“此前一定已整理”的低水位。两列都为 NULL 表示旧会话尚未迁移，
# 各上下文的游标都取 ``last_consolidated``。
CONTEXT_CURSOR_COLUMNS: dict[ContextScope, str] = {
    "user": "user_cursor",
    "external": "external_cursor",
}


def row_context_cursors(row: Mapping[str, Any]) -> dict[ContextScope, int] | None:
    """sessions 行里的按上下文游标；未迁移（全为 NULL）时返回 None。

    只有一部分列有值说明数据已损坏，直接报错，不静默回退。
    """
    values: dict[ContextScope, Any] = {
        scope: row[column] for scope, column in CONTEXT_CURSOR_COLUMNS.items()
    }
    if all(value is None for value in values.values()):
        return None
    if any(value is None for value in values.values()):
        raise ValueError(f"会话整理游标不完整: {values!r}")
    cursors: dict[ContextScope, int] = {
        scope: int(value) for scope, value in values.items()
    }
    return cursors


def context_cursor_values(
    cursors: Mapping[ContextScope, int] | None,
) -> tuple[int | None, ...]:
    """按 ``CONTEXT_CURSOR_COLUMNS`` 顺序给出要写入的列值；None 表示未迁移。"""
    return tuple(
        None if cursors is None else int(cursors[scope])
        for scope in CONTEXT_CURSOR_COLUMNS
    )


# UPDATE 语句里写入全部按上下文游标列的片段，参数见 ``context_cursor_values``。
CONTEXT_CURSOR_ASSIGNMENTS = ", ".join(
    f"{column} = ?" for column in CONTEXT_CURSOR_COLUMNS.values()
)
