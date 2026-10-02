from collections.abc import Mapping
from typing import Any

import pytest

from session.manager.models import Session, message_thread_id, whole_session


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
    history = session.get_history(include=whole_session)
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
    content = session.get_history(include=whole_session)[0]["content"]
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
        content = session.get_history(include=whole_session)[0]["content"]
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


def _thread_session(key: str) -> Session:
    session = Session(key)
    for index, thread in enumerate(["a", "b", "a", "b", "a"]):
        session.add_message("user", f"m{index}", thread_id=thread)
    return session


def _in_thread_a(message: Mapping[str, Any]) -> bool:
    return message_thread_id(message) == "a"


def test_history_window_filters_before_taking_the_last_messages():
    session = _thread_session("cli:1")

    window = session.history_window(2, include=_in_thread_a)

    # The limit counts visible messages: two of thread a, not the last two rows.
    assert [message["content"] for message in window] == ["m2", "m4"]


def test_role_session_history_needs_an_explicit_filter():
    session = _thread_session("role:mira")

    with pytest.raises(ValueError, match="上下文筛选"):
        session.get_history()
    assert len(session.history_window(500, include=whole_session)) == 5


def test_message_thread_id_reads_stored_or_in_memory_threads():
    assert message_thread_id({"thread_id": " t1 "}) == "t1"
    assert message_thread_id({"metadata": {"thread_id": "t2"}}) == "t2"
    assert message_thread_id({"metadata": "not a dict"}) == ""


def test_native_tool_history_survives_reopen_as_a_complete_exchange(tmp_path):
    from session.manager import SessionManager

    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:native")
    call = {
        "id": "native-call",
        "type": "function",
        "function": {"name": "write_file", "arguments": '{"path":"report.txt"}'},
    }
    session.add_message("user", "write report")
    session.add_message("assistant", "", tool_calls=[call])
    session.add_message("tool", "report saved", tool_call_id="native-call")
    session.add_message("assistant", "completed")
    manager.save(session)
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    history = reloaded.get_history(start_index=0)
    assert [item["role"] for item in history] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert history[1]["tool_calls"] == [call]
    assert history[2] == {
        "role": "tool",
        "tool_call_id": "native-call",
        "content": "report saved",
    }
    assert reloaded.get_history_tool_names(start_index=0) == ["write_file"]
