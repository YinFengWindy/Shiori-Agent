from __future__ import annotations

from conversation.service import ConversationService
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager


def test_session_presenter_keeps_sanitized_turn_metrics(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "完成。",
        metadata={
            "turn_metrics": {
                "total_tokens": 2438,
                "thinking_duration_ms": 6200,
                "internal": "ignored",
            }
        },
    )

    payload = DesktopSessionPresenter(ConversationService(manager)).serialize(session)

    assert payload["messages"][0]["metadata"]["turn_metrics"] == {
        "total_tokens": 2438,
        "thinking_duration_ms": 6200,
    }


def test_session_presenter_serializes_sanitized_tool_chain(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "查到了。",
        tool_chain=[
            {
                "text": "我来查一下",
                "reasoning_content": "需要搜索",
                "calls": [
                    {
                        "call_id": "call-1",
                        "name": "web_search",
                        "status": "success",
                        "arguments": {"query": "天气"},
                        "final_arguments": {"query": "上海天气"},
                        "result": "晴，28°C",
                        "pre_hook_trace": [{"reason": "internal"}],
                        "post_hook_trace": [{"reason": "internal"}],
                    }
                ],
            }
        ],
    )
    conversation = ConversationService(manager)

    payload = DesktopSessionPresenter(conversation).serialize(session)

    assert payload["messages"][0]["tool_chain"] == [
        {
            "text": "我来查一下",
            "reasoning_content": "需要搜索",
            "calls": [
                {
                    "call_id": "call-1",
                    "name": "web_search",
                    "status": "success",
                    "arguments": {"query": "天气"},
                    "final_arguments": {"query": "上海天气"},
                    "result": "晴，28°C",
                }
            ],
        }
    ]


def test_session_presenter_truncates_results_and_skips_unidentified_tools(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "完成。",
        tool_chain=[
            {
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
            }
        ],
    )

    payload = DesktopSessionPresenter(ConversationService(manager)).serialize(session)

    calls = payload["messages"][0]["tool_chain"][0]["calls"]
    assert [call["call_id"] for call in calls] == ["call-1"]
    assert len(calls[0]["result"]) == 2000
    assert calls[0]["result"].endswith("...")


def test_session_presenter_page_and_summary_use_store_projection(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("user", "旧消息")
    session.add_message("assistant", "新消息")
    manager.save(session)
    presenter = DesktopSessionPresenter(ConversationService(manager))

    summary = presenter.serialize_summary(session)
    page = presenter.serialize_page(session, limit=1)

    assert summary["key"] == "role:mira"
    assert "messages" not in summary
    assert [message["role"] for message in page["messages"]] == ["assistant"]
    assert page["messages"][0]["seq"] == 1
    assert page["messages"][0]["session_key"] == "role:mira"


def test_session_presenter_search_and_around_serialize_light_results(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("assistant", "请搜索天气")
    manager.save(session)
    presenter = DesktopSessionPresenter(ConversationService(manager))

    search = presenter.serialize_search("天气", session_key="role:mira")
    around = presenter.serialize_around("role:mira:0", context=0)

    assert search["total_count"] == 1
    assert search["results"][0]["id"] == "role:mira:0"
    assert search["results"][0]["preview"] == "请搜索天气"
    assert "tool_chain" not in search["results"][0]
    assert around["messages"][0]["is_target"] is True
    assert "is_target" not in around["messages"][0]["metadata"]
    assert around["messages"][0]["seq"] == 0


def test_session_presenter_image_history_excludes_chat_content(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("assistant", "很长的聊天正文", media=["old.png"])
    manager.save(session)
    presenter = DesktopSessionPresenter(ConversationService(manager))

    history = presenter.serialize_image_history(session.key)

    assert history == {
        "session_key": "role:mira",
        "messages": [
            {
                "id": "role:mira:0",
                "seq": 0,
                "timestamp": session.messages[0]["timestamp"],
                "media": ["old.png"],
            }
        ],
    }


def test_session_presenter_last_message_preview_reads_the_newest_row(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("user", "早上好")
    session.add_message("assistant", "早呀" * 150, media=["photo.png"])
    manager.save(session)
    presenter = DesktopSessionPresenter(ConversationService(manager))

    preview = presenter.last_message_preview("role:mira")

    assert preview is not None
    assert preview["role"] == "assistant"
    assert preview["content"] == ("早呀" * 150)[:200]
    assert preview["has_media"] is True
    assert preview["timestamp"]


def test_session_presenter_last_message_preview_is_none_for_empty_sessions(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    presenter = DesktopSessionPresenter(ConversationService(manager))

    assert presenter.last_message_preview("role:nobody") is None


def test_session_presenter_reads_only_the_desktop_conversation(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    for content, thread_id, media in [
        ("旧的天气", "", None),
        ("桌面天气", "thread:mira:desktop", ["desk.png"]),
        ("群里天气", "thread:mira:qq:group-1", ["group.png"]),
        ("提醒天气", "thread:mira:scheduler:job-1", None),
        ("最新群消息", "thread:mira:qq:group-1", None),
    ]:
        session.add_message(
            "user",
            content,
            media=media,
            metadata={"thread_id": thread_id} if thread_id else None,
        )
    manager.save(session)
    other = manager.get_or_create("role:other")
    other.add_message(
        "user", "别人的群天气", metadata={"thread_id": "thread:other:qq:g"}
    )
    manager.save(other)
    presenter = DesktopSessionPresenter(ConversationService(manager))

    page = presenter.serialize_page(session)
    around = presenter.serialize_around("role:mira:1", context=1)
    role_search = presenter.serialize_search("天气", session_key="role:mira")
    all_search = presenter.serialize_search("天气")
    images = presenter.serialize_image_history("role:mira")
    preview = presenter.last_message_preview("role:mira")

    assert [message["seq"] for message in page["messages"]] == [0, 1, 3]
    assert [message["seq"] for message in around["messages"]] == [0, 1, 3]
    assert presenter.serialize_around("role:mira:2")["messages"] == []
    assert sorted(hit["seq"] for hit in role_search["results"]) == [0, 1, 3]
    assert sorted(hit["id"] for hit in all_search["results"]) == [
        "role:mira:0",
        "role:mira:1",
        "role:mira:3",
    ]
    assert [item["media"] for item in images["messages"]] == [["desk.png"]]
    assert preview is not None and preview["content"] == "提醒天气"
    assert [
        message["content"]
        for message in presenter.desktop_messages("role:mira", session.messages)
    ] == ["旧的天气", "桌面天气", "提醒天气"]
