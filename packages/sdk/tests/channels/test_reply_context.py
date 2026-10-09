from __future__ import annotations

import pytest

from shiori_sdk.messages import InboundMessage
from shiori_sdk.channels.reply_context import (
    build_inbound_text_with_reply_context,
    with_reply_quote,
)


def _quoting(sender_id: str, **metadata: object) -> InboundMessage:
    return InboundMessage(
        channel="qq",
        sender="902",
        chat_id="gqq:777",
        content="这是啥",
        media=["own.png"],
        metadata={"reply_to_sender_id": sender_id, **metadata},
    )


@pytest.mark.parametrize(
    ("message", "sender_name", "label"),
    [
        (_quoting("202"), "Mira", "你自己"),
        (_quoting("100", reply_to_sender_is_user=True), "主人", "你的用户"),
        (_quoting("303"), "阿花", "阿花（ID 303）"),
        (_quoting("303"), "", "ID 303"),
    ],
)
def test_quote_names_its_sender_for_the_turn(message, sender_name, label):
    turn = with_reply_quote(
        message, own_id="202", text="看", sender_name=sender_name, media=[]
    )
    assert f"被回复消息（来自 {label}）：\n看\n" in turn.content


def test_quote_leads_the_turn_but_the_message_keeps_its_own_text():
    turn = with_reply_quote(
        _quoting("303"), own_id="202", text="看", sender_name="阿花", media=["q.png"]
    )
    assert turn.content.endswith(
        "看\n（被回复消息附带 1 张图片，即本条附件中的前 1 张）\n\n"
        "【你当前新消息】\n这是啥"
    )
    assert turn.media == ["q.png", "own.png"]
    assert {
        key: turn.metadata[key]
        for key in (
            "persisted_user_content",
            "reply_to_content",
            "reply_to_sender_name",
            "reply_to_media",
        )
    } == {
        "persisted_user_content": "这是啥",
        "reply_to_content": "看",
        "reply_to_sender_name": "阿花",
        "reply_to_media": ["q.png"],
    }


def test_pictures_only_quote_stays_when_its_pictures_cannot_be_fetched():
    turn = with_reply_quote(
        _quoting("303"),
        own_id="202",
        text="",
        sender_name="阿花",
        media=[],
        has_pictures=True,
    )
    assert "被回复消息（来自 阿花（ID 303））：\n[图片]\n\n" in turn.content
    assert turn.media == ["own.png"]
    # The phone shows the same placeholder in the quote block.
    assert turn.metadata["reply_to_content"] == "[图片]"
    assert "reply_to_media" not in turn.metadata


@pytest.mark.parametrize(
    "media,expected",
    [
        (["文章.txt"], "[文件]\n（被回复消息附带 1 个文件，即本条附件中的前 1 项）"),
        (
            ["图.png", "文章.md"],
            "[附件]\n（被回复消息附带 1 张图片、1 个文件，即本条附件中的前 2 项）",
        ),
    ],
)
def test_file_quotes_keep_attachment_order_and_do_not_claim_files_are_images(
    media, expected
):
    turn = with_reply_quote(
        _quoting("303"), own_id="202", text="", sender_name="阿花", media=media
    )
    assert expected in turn.content
    assert turn.media == [*media, "own.png"]
    assert turn.metadata["reply_to_media"] == media
    assert turn.metadata["persisted_user_content"] == "这是啥"


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
    assert (
        build_inbound_text_with_reply_context(user_text="  hi  ", reply_text="") == "hi"
    )
