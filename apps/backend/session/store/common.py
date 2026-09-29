"""Session store 共享的消息列投影与筛选条件。"""

from __future__ import annotations

from collections.abc import Collection

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
