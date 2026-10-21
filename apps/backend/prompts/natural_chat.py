"""Minimal instant-chat context; the model chooses wording and message boundaries."""

NATURAL_CHAT_SEPARATOR = "<message-break/>"
NATURAL_CHAT_PROMPT = (
    "## 即时聊天\n"
    "你正在聊天软件里与对方交流。请按实际准备发送的独立消息组织回复，"
    "每条消息对应一个聊天气泡。\n"
    "内容、措辞、条数和结束时机由你根据角色与当前对话决定。"
    "一条消息足够时就发一条。\n"
    f"不同消息之间必须单独写一行 {NATURAL_CHAT_SEPARATOR}。"
    "同一条消息内部可以正常换行；普通换行不会产生新气泡。"
    "分隔符只放在非空消息之间，不要放进代码块。\n\n"
    "以下用日常对话演示消息格式；实际语气仍以你的角色为准，"
    "内容和条数不必照搬。示例中的标题和对方发言不属于回复。\n"
    "单条消息示例：\n"
    "对方：我先去吃饭，晚点聊。\n"
    "回复：\n"
    "好，晚点聊。\n\n"
    "多条消息示例：\n"
    "对方：本来想早点睡，结果又刷手机刷到现在。\n"
    "回复：\n"
    "你那个“再看五分钟”又续费了是吧\n"
    f"{NATURAL_CHAT_SEPARATOR}\n"
    "刷到什么了，这么舍不得睡"
)

# Proactive message_push is a generated reply draft, not the explicit-send tool.
NATURAL_CHAT_DRAFT_PROMPT = (
    NATURAL_CHAT_PROMPT + "\n将完整回复写入 message_push 的 message 草稿字段。"
)
