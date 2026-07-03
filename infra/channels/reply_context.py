from __future__ import annotations


def build_inbound_text_with_reply_context(
    *,
    user_text: str,
    reply_text: str,
    reply_sender: str = "",
) -> str:
    """Build the inbound text that lets the agent see a referenced message."""

    current_text = str(user_text or "").strip()
    referenced_text = str(reply_text or "").strip()
    if not referenced_text:
        return current_text

    sender_label = str(reply_sender or "").strip()
    reply_header = f"被回复消息（来自 {sender_label}）：" if sender_label else "被回复消息："
    return (
        "【你正在回复一条历史消息】\n"
        f"{reply_header}\n"
        f"{referenced_text}\n\n"
        "【你当前新消息】\n"
        f"{current_text}"
    ).strip()
