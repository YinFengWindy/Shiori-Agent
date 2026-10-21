"""Minimal instant-chat context; the model chooses wording and message boundaries."""

FINISH_REPLY_TOOL_NAME = "finish_reply"


def natural_chat_prompt(tool_name: str = FINISH_REPLY_TOOL_NAME) -> str:
    """Use the same message-list protocol for passive replies and proactive drafts."""
    return (
        "## 即时聊天\n"
        "你正在聊天软件里和对方交流。保持角色的性格和语气，直接说想说的话；"
        "日常交流不必表演动作或描写镜头，不必每次把话说满，需要解释时正常展开。\n"
        "内容、措辞、条数、分条位置和结束时机由你根据当前对话决定。"
        "一条消息足够时就发一条，同一条消息内部可以正常换行。\n"
        f"正式回复通过 {tool_name} 的 messages 列表提交，"
        "每项是一条实际要发送的独立消息；不要在普通正文里另发一份。"
        "需要业务工具时先获取结果，再单独完成回复。"
        "发送协议不属于聊天话题，无需向对方解释。"
    )


NATURAL_CHAT_PROMPT = natural_chat_prompt()
# Proactive message_push is a generated reply draft, not the explicit-send tool.
NATURAL_CHAT_DRAFT_PROMPT = natural_chat_prompt("message_push")
