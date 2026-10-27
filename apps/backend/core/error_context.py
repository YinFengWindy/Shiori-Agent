from __future__ import annotations

from contextvars import ContextVar

# 当前正在处理的会话 key。在每条消息/每个 proactive tick 的处理 task 起点设置。
# 宿主的 CRASH_REPORTING.session_key() 读取它；observe 的采集器只调用该协议，
# 不直接 import 这个 ContextVar。放在 core 层是为了让主循环与崩溃归因共享同一对象。
current_session_key: ContextVar[str | None] = ContextVar(
    "shiori_current_session_key", default=None
)
