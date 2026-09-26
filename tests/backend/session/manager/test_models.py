from session.manager.models import Session


def test_history_retains_per_message_origin_without_replaying_context():
    session = Session(key="role:mira")
    sources = [
        ("telegram", "-1001", "group", "11"),
        ("telegram", "-1001", "group", "22"),
        ("desktop", "role:mira", "desktop", "desktop"),
        ("qq", "gqq:1002", "group", "11"),
    ]
    for channel, chat, chat_type, sender in sources:
        session.add_message(
            "user",
            "hello",
            metadata={
                "transport_channel": channel,
                "transport_chat_id": chat,
                "chat_type": chat_type,
                "sender_id": sender,
            },
            llm_user_content="[当前消息时间: original]\nhello",
            llm_context_frame="old retrieved memory must not replay",
        )
    history = session.get_history()
    for item, (channel, chat, chat_type, sender) in zip(history, sources):
        content = item["content"]
        assert f'"sender_id": "{sender}"' in content
        assert f'"chat_id": "{chat}"' in content
        assert f'"channel": "{channel}"' in content
        assert f'"chat_type": "{chat_type}"' in content
        assert '"session_key": "role:mira"' in content
        assert content.startswith("[当前消息时间: original]\n[消息来源: ")
        assert content.endswith("\nhello")
        assert content.count("[消息来源: ") == 1
        assert "old retrieved memory" not in content


def test_legacy_history_marks_missing_origin_unknown():
    session = Session(key="role:mira", metadata={"transport_channel": "desktop"})
    session.add_message("user", "old message")
    content = session.get_history()[0]["content"]
    assert '"channel": null' in content
    assert '"sender_id": null' in content
    assert "desktop" not in content


def test_history_preserves_cached_multimodal_blocks_and_adds_source_once():
    session = Session(key="role:mira")
    blocks = [
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
        {"type": "text", "text": "[当前消息时间: original]\ncaption"},
    ]
    session.add_message(
        "user",
        "caption",
        metadata={
            "transport_channel": "qq",
            "transport_chat_id": "gqq:123",
            "chat_type": "group",
            "sender_id": "42",
        },
        llm_user_content=blocks,
    )

    for _ in range(2):
        content = session.get_history()[0]["content"]
        assert content[0] == blocks[0]
        assert content[1]["text"].startswith("[当前消息时间: original]\n")
        assert '"sender_id": "42"' in content[1]["text"]
        assert content[1]["text"].endswith("\ncaption")
        assert content[1]["text"].count("[消息来源: ") == 1
    assert blocks[1]["text"] == "[当前消息时间: original]\ncaption"


def _assistant(calls: list[dict[str, object]], **extra: object) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": "ok",
        "tool_chain": [{"text": "", "calls": calls}],
        **extra,
    }


def test_get_history_tool_names_collects_called_and_unlocked_tools_in_order():
    session = Session(
        key="s",
        messages=[
            {"role": "user", "content": "a"},
            _assistant(
                [
                    {"call_id": "1", "name": "tool_search", "unlocked": ["open"]},
                    {"call_id": "2", "name": "open"},
                ]
            ),
            {"role": "user", "content": "b"},
            _assistant(
                [
                    {"call_id": "3", "name": "click"},
                    {"call_id": "4", "name": "open"},
                ]
            ),
        ],
    )

    assert session.get_history_tool_names() == ["tool_search", "open", "click"]


def test_get_history_tool_names_drops_tools_consolidated_out_of_window():
    session = Session(
        key="s",
        messages=[
            {"role": "user", "content": "old"},
            _assistant([{"call_id": "1", "name": "old_tool"}]),
            {"role": "user", "content": "new"},
            _assistant([{"call_id": "2", "name": "new_tool"}]),
        ],
    )

    assert session.get_history_tool_names(start_index=2) == ["new_tool"]


def test_get_history_tool_names_skips_proactive_tool_chain():
    """主动消息的工具链不进入 LLM 历史，所以也不应让工具保持可见。"""
    session = Session(
        key="s",
        messages=[
            _assistant([{"call_id": "1", "name": "proactive_tool"}], proactive=True),
            {"role": "user", "content": "hi"},
        ],
    )

    assert session.get_history_tool_names() == []
