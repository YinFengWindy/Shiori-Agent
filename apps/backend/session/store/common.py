"""Session store 共享的消息列投影。"""

_MESSAGE_SELECT_COLUMNS = (
    "id, session_key, seq, role, content, tool_chain, extra, ts, "
    "thread_id, sender_role, media, external_message_id, delivery_status"
)
