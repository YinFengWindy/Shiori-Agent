from __future__ import annotations

import json

from plugins.feishu.backend.formatting import (
    CARD_TEXT_LIMIT,
    LIVE_ELEMENT_ID,
    closing_settings,
    extract_card_text,
    extract_post,
    extract_text,
    live_text,
    markdown_card,
    split_markdown,
    streaming_card,
)


def test_text_mentions_are_replaced_by_names() -> None:
    content = {"text": "@_user_1 帮我看看 @_user_2"}
    mentions = [{"key": "@_user_1", "name": "Shiori"}, {"key": "@_user_2"}]

    assert extract_text(content, mentions) == "@Shiori 帮我看看"


def test_post_is_flattened_with_images_in_both_payload_shapes() -> None:
    received = {
        "title": "周报",
        "content": [
            [
                {"tag": "text", "text": "完成 "},
                {"tag": "a", "text": "链接", "href": "x"},
            ],
            [{"tag": "img", "image_key": "img_a"}],
            [{"tag": "at", "user_name": "小明"}, {"tag": "md", "text": " **加粗**"}],
        ],
    }
    fetched = {"zh_cn": received}

    for payload in (received, fetched):
        assert extract_post(payload) == ("周报\n完成 链接\n@小明 **加粗**", ["img_a"])


def test_card_text_walks_nested_card_bodies() -> None:
    card = {
        "title": "标题",
        "elements": [
            [{"tag": "text", "text": "第一段"}],
            [{"tag": "md", "content": "二"}],
        ],
    }

    assert extract_card_text(card) == "标题\n第一段\n二"


def test_split_markdown_keeps_lines_and_hard_splits_long_lines() -> None:
    text = "a" * 5 + "\n" + "b" * 12 + "\n" + "c"

    chunks = split_markdown(text, limit=8)

    assert "".join(chunks) == text
    assert all(len(chunk) <= 8 for chunk in chunks)
    assert split_markdown("short") == ["short"]


def test_live_text_keeps_the_head_so_updates_extend_the_previous_text() -> None:
    long = "字" * (CARD_TEXT_LIMIT + 50)

    assert live_text("  开头  ") == "开头"
    assert live_text(long).startswith("字" * 100)
    assert len(live_text(long)) == CARD_TEXT_LIMIT


def test_streaming_card_is_a_shared_json2_card_in_streaming_mode() -> None:
    card = json.loads(streaming_card())

    assert card["schema"] == "2.0"
    assert card["config"]["streaming_mode"] is True
    assert card["config"]["update_multi"] is True
    assert card["body"]["elements"][0]["element_id"] == LIVE_ELEMENT_ID
    assert len(LIVE_ELEMENT_ID) <= 20


def test_static_and_closing_cards_carry_a_chat_list_summary() -> None:
    static = json.loads(markdown_card("# 标题\n正文"))
    closing = json.loads(closing_settings("x" * 100))

    assert static["body"]["elements"] == [
        {"tag": "markdown", "content": "# 标题\n正文"}
    ]
    assert static["config"]["summary"]["content"] == "# 标题 正文"
    assert closing["config"]["streaming_mode"] is False
    assert len(closing["config"]["summary"]["content"]) == 60
