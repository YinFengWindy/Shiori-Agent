from __future__ import annotations

from infra.channels.reply_context import build_inbound_text_with_reply_context


def test_build_inbound_text_with_reply_context_adds_sender_label():
    text = build_inbound_text_with_reply_context(
        user_text="再展开一点",
        reply_text="她沉默了很久。",
        reply_sender="Mira",
    )

    assert text == (
        "【你正在回复一条历史消息】\n"
        "被回复消息（来自 Mira）：\n"
        "她沉默了很久。\n\n"
        "【你当前新消息】\n"
        "再展开一点"
    )


def test_build_inbound_text_with_reply_context_returns_user_text_without_reply():
    assert build_inbound_text_with_reply_context(user_text="  hi  ", reply_text="") == "hi"
