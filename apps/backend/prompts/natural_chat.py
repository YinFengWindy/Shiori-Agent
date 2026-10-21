"""Minimal instant-chat context; the model chooses wording and message boundaries."""

NATURAL_CHAT_SEPARATOR = "<message-break/>"
NATURAL_CHAT_PROMPT = (
    "## 即时聊天\n"
    "你正在即时聊天，可以按需要发送一条或多条消息。"
    "内容、措辞、条数和结束时机由你根据角色与当前对话决定。\n"
    f"需要另发一条消息时，在两条消息之间单独写一行 {NATURAL_CHAT_SEPARATOR}。"
    "普通换行仍属于同一条消息；分隔符只放在非空消息之间，"
    "不要放进代码块。"
)
