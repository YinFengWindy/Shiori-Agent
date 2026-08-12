from __future__ import annotations

from conversation.service import ConversationService
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager


def test_session_presenter_serializes_formal_thread(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("user", "hello")
    manager.save(session)
    conversation = ConversationService(manager)
    thread = conversation.sync_session_messages_to_thread(
        session.key,
        role_id="mira",
        channel="desktop",
        chat_id="self",
    )

    payload = DesktopSessionPresenter(conversation).serialize(session)

    assert "thread" not in payload
    assert thread.id == "thread:mira:desktop"
    assert payload["messages"][0]["content"] == "hello"


def test_session_presenter_serializes_sanitized_tool_chain(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "查到了。",
        tool_chain=[{
            "text": "我来查一下",
            "reasoning_content": "需要搜索",
            "calls": [{
                "call_id": "call-1",
                "name": "web_search",
                "status": "success",
                "arguments": {"query": "天气"},
                "final_arguments": {"query": "上海天气"},
                "result": "晴，28°C",
                "pre_hook_trace": [{"reason": "internal"}],
                "post_hook_trace": [{"reason": "internal"}],
            }],
        }],
    )
    conversation = ConversationService(manager)

    payload = DesktopSessionPresenter(conversation).serialize(session)

    assert payload["messages"][0]["tool_chain"] == [{
        "text": "我来查一下",
        "reasoning_content": "需要搜索",
        "calls": [{
            "call_id": "call-1",
            "name": "web_search",
            "status": "success",
            "arguments": {"query": "天气"},
            "final_arguments": {"query": "上海天气"},
            "result": "晴，28°C",
        }],
    }]


def test_session_presenter_truncates_results_and_skips_unidentified_tools(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "完成。",
        tool_chain=[{
            "text": "执行工具",
            "calls": [
                {
                    "call_id": "call-1",
                    "name": "read_file",
                    "status": "success",
                    "result": "x" * 2500,
                },
                {"call_id": "", "name": "shell", "result": "ignored"},
                {"call_id": "call-3", "name": "", "result": "ignored"},
            ],
        }],
    )

    payload = DesktopSessionPresenter(ConversationService(manager)).serialize(session)

    calls = payload["messages"][0]["tool_chain"][0]["calls"]
    assert [call["call_id"] for call in calls] == ["call-1"]
    assert len(calls[0]["result"]) == 2000
    assert calls[0]["result"].endswith("...")
