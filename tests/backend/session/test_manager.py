from __future__ import annotations

from pathlib import Path

import pytest

from agent.prompting import is_context_frame
from session.manager import (
    Session,
    SessionManager,
    _TOOL_RESULT_CHAR_BUDGET,
    _safe_filename,
)


def test_safe_filename_replaces_session_key_separator():
    assert _safe_filename("telegram:1") == "telegram_1"


def test_get_history_appends_meta_frame_for_proactive_and_media_turns():
    session = Session("telegram:1")
    session.add_message("user", "hi", media=["/tmp/a.png"])
    session.add_message(
        "assistant",
        "reply",
        proactive=True,
        state_summary_tag="tag",
        source_refs=[{"source_name": "Feed", "title": "T", "url": "https://x"}],
    )
    session.messages[-1]["tool_chain"] = [
        {"calls": [{"call_id": "1", "name": "tool", "arguments": {}, "result": "ok"}]}
    ]

    history = session.get_history()

    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[1] == {"role": "assistant", "content": "reply"}
    assert history[2]["role"] == "user"
    assert is_context_frame(str(history[2]["content"]))


@pytest.mark.asyncio
async def test_manager_persists_reloads_and_lists_sessions(tmp_path: Path):
    session = Session("telegram:1")
    session.add_message("user", "hi")
    manager = SessionManager(tmp_path)

    manager.save(session)
    loaded = manager.get_or_create("telegram:1")
    await manager.append_messages(session, [{"role": "user", "content": "next"}])

    assert loaded.key == "telegram:1"
    assert manager.list_sessions()
    assert manager.get_channel_metadata("telegram")[0]["chat_id"] == "1"

    manager.invalidate("telegram:1")


def test_manager_open_role_session_records_role_metadata(tmp_path: Path):
    manager = SessionManager(tmp_path)

    role_session = manager.open_role_session("mira", role_name="Mira")

    assert role_session.key == "role:mira"
    assert role_session.metadata["role_id"] == "mira"
    assert role_session.metadata["role_name"] == "Mira"


def test_get_history_returns_empty_when_window_is_zero():
    session = Session("cli:1")
    session.add_message("user", "hello")
    session.add_message("assistant", "world")

    assert session.get_history(max_messages=0) == []


def test_get_history_skips_cached_llm_frame_by_default():
    session = Session("cli:1")
    session.add_message("user", "old")
    session.add_message("assistant", "old reply")
    session.last_consolidated = 2
    user_content = "[当前消息时间: x]\nhello"
    session.add_message(
        "user",
        "hello",
        llm_context_frame=(
            '<system-reminder data-system-context-frame="true">'
            "\n\n## retrieved_memory\n旧记忆"
        ),
        llm_user_content=user_content,
    )
    session.add_message("assistant", "world")

    history = session.get_history(start_index=session.last_consolidated)

    assert history[0]["role"] == "user"
    assert history[0]["content"].startswith("[当前消息时间: x]\n")
    assert '"channel": null' in history[0]["content"]
    assert history[0]["content"].endswith("\nhello")
    assert "旧记忆" not in history[0]["content"]
    assert history[1] == {"role": "assistant", "content": "world"}


def test_get_history_replays_proactive_as_short_assistant_with_meta_frame():
    session = Session("cli:1")
    session.add_message(
        "assistant",
        "这是一条主动消息",
        proactive=True,
        source_refs=[
            {
                "source_name": "feed",
                "title": "标题",
                "url": "https://example.com/a",
            }
        ],
    )

    history = session.get_history()

    assert len(history) == 2
    assert history[0] == {"role": "assistant", "content": "这是一条主动消息"}
    assert history[1]["role"] == "user"
    content = str(history[1]["content"])
    assert is_context_frame(content)
    assert "recent_proactive_message_meta" in content
    assert "proactive_meta" in content


def test_get_history_allows_proactive_assistant_boundary():
    session = Session("cli:1")
    session.add_message("user", "old")
    session.add_message("assistant", "old reply")
    session.add_message("assistant", "主动消息", proactive=True)
    session.add_message("user", "刚才那个")
    session.last_consolidated = 2

    history = session.get_history(start_index=session.last_consolidated)

    assert len(history) == 3
    assert history[0] == {"role": "assistant", "content": "主动消息"}
    assert history[1]["role"] == "user"
    context = str(history[1]["content"])
    assert is_context_frame(context)
    assert "上一条 assistant 消息是系统主动推送" in context
    assert history[2]["role"] == "user"
    assert '"channel": null' in history[2]["content"]
    assert history[2]["content"].endswith("\n刚才那个")


def test_get_history_rewinds_consolidated_index_to_user_boundary():
    session = Session("cli:1")
    session.add_message("user", "hello")
    session.add_message("assistant", "world")
    session.last_consolidated = 1

    history = session.get_history(start_index=session.last_consolidated)

    assert history[0]["role"] == "user"
    assert history[0]["content"].endswith("\nhello")


def test_get_history_keeps_full_consolidated_tail():
    session = Session("cli:1")
    for i in range(5):
        session.add_message("user", f"u{i}")

    history = session.get_history(max_messages=2, start_index=0)

    assert session.consolidation_requested is False
    assert [message["role"] for message in history] == ["user"] * 5
    assert [message["content"].rsplit("\n", 1)[-1] for message in history] == [
        "u0",
        "u1",
        "u2",
        "u3",
        "u4",
    ]


def test_get_history_assistant_only_returns_empty():
    session = Session("cli:1")
    session.add_message("assistant", "a1")
    session.add_message("assistant", "a2")

    assert session.get_history(start_index=0) == []


def test_get_history_skips_legacy_context_frame_by_default():
    session = Session("cli:1")
    session.add_message(
        "user",
        "hello",
        llm_context_frame="[SYSTEM_CONTEXT_FRAME]\n\n## recent_context\n旧内容",
        llm_user_content="hello",
    )

    history = session.get_history(start_index=0)

    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"].endswith("\nhello")
    assert "recent_context" not in history[0]["content"]


def test_get_history_does_not_inject_inference_tag():
    session = Session("cli:1")
    session.add_message("user", "hello")
    session.add_message("assistant", "world")

    history = session.get_history()

    assert history[-1] == {"role": "assistant", "content": "world"}


def test_get_history_keeps_reasoning_content():
    session = Session("cli:1")
    session.add_message("user", "hello")
    session.add_message(
        "assistant",
        "world",
        reasoning_content="先想一下",
    )
    session.messages[-1]["tool_chain"] = [
        {
            "text": "",
            "reasoning_content": "准备调用工具",
            "calls": [
                {
                    "call_id": "call-1",
                    "name": "dummy",
                    "arguments": {},
                    "result": "ok",
                }
            ],
        }
    ]

    history = session.get_history()

    assert history[1]["reasoning_content"] == "准备调用工具"
    assert history[-1]["reasoning_content"] == "先想一下"


def test_get_history_keeps_short_tool_results_after_consolidation_tail():
    session = Session("cli:1")
    session.last_consolidated = 0
    for i in range(3):
        session.add_message("user", f"u{i}")
        session.add_message("assistant", f"a{i}")
        session.messages[-1]["tool_chain"] = [
            {
                "text": "",
                "calls": [
                    {
                        "call_id": f"call-{i}",
                        "name": "dummy",
                        "arguments": {},
                        "result": f"result-{i}",
                    }
                ],
            }
        ]

    history = session.get_history(start_index=session.last_consolidated)
    tool_contents = [m["content"] for m in history if m.get("role") == "tool"]

    assert tool_contents == ["result-0", "result-1", "result-2"]


def test_get_history_truncates_long_tool_results_in_middle():
    session = Session("cli:1")
    long_result = "head-" + "x" * (_TOOL_RESULT_CHAR_BUDGET + 200) + "-tail"
    session.add_message("user", "u")
    session.add_message("assistant", "a")
    session.messages[-1]["tool_chain"] = [
        {
            "text": "",
            "calls": [
                {
                    "call_id": "call-1",
                    "name": "dummy",
                    "arguments": {},
                    "result": long_result,
                }
            ],
        }
    ]

    history = session.get_history()
    tool_content = next(m["content"] for m in history if m.get("role") == "tool")

    assert tool_content.startswith("Total output lines: 1\n\nhead-")
    assert "chars truncated" in tool_content
    assert tool_content.endswith("-tail")
    assert len(tool_content) < len(long_result)
