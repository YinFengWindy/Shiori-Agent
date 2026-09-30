from __future__ import annotations

from datetime import datetime, timedelta

from agent.core.passive_turn.helpers import (
    get_history_since_consolidated,
    get_window_sources_since_consolidated,
)
from agent.prompting.listening_block import HeardLine
from conversation.context_scope import ContextView, UserContextThreads
from conversation.service import desktop_thread_id, network_thread_id
from core.common.message_source import MessageSource
from session.manager.models import Session


def test_window_sources_are_the_external_members_seen_since_consolidation() -> None:
    group = network_thread_id("mira", "qq", "g1")
    session = Session(key="role:mira")
    for sender_id, thread_id, is_user in (
        ("111", group, False),
        ("555", group, False),
        ("902", group, True),
        ("", desktop_thread_id("mira"), False),
        ("666", group, False),
    ):
        session.add_message(
            "user",
            "hi",
            thread_id=thread_id,
            metadata={
                "message_source": {
                    "channel": "qq",
                    "sender_id": sender_id,
                    **({"sender_is_user": True} if is_user else {}),
                }
            },
        )
        session.add_message("assistant", "ok", thread_id=thread_id)
    session.last_consolidated = 2
    user_threads = UserContextThreads(
        role_id="mira", bound_chat_thread_ids=frozenset({desktop_thread_id("mira")})
    )

    external = get_window_sources_since_consolidated(
        session, 50, ContextView(scope="external", user_threads=user_threads)
    )
    user = get_window_sources_since_consolidated(
        session, 50, ContextView(scope="user", user_threads=user_threads)
    )

    # 整理过的与用户本人的消息都不在其中；按时间先后排列。
    assert [source.sender_id for source in external] == ["555", "666"]
    assert user == ()


def test_window_sources_start_from_the_external_cursor() -> None:
    """成员来源与历史同一窗口：外部游标领先时不取已整理的来源（#523）。"""
    group = network_thread_id("mira", "qq", "g1")
    session = Session(key="role:mira")
    for sender_id in ("111", "555", "666"):
        session.add_message(
            "user",
            f"我是 {sender_id}",
            thread_id=group,
            metadata={"message_source": {"channel": "qq", "sender_id": sender_id}},
        )
        session.add_message("assistant", "ok", thread_id=group)
    session.last_consolidated = 0
    session.context_cursors = {"user": 0, "external": 4}
    view = ContextView(
        scope="external",
        user_threads=UserContextThreads(
            role_id="mira",
            bound_chat_thread_ids=frozenset({desktop_thread_id("mira")}),
        ),
    )

    sources = get_window_sources_since_consolidated(session, 50, view)
    history = get_history_since_consolidated(session, 50, view)

    assert [source.sender_id for source in sources] == ["666"]
    user_turns = [m["content"] for m in history if m["role"] == "user"]
    assert len(user_turns) == 1 and user_turns[0].endswith("我是 666")


def test_window_sources_merge_the_heard_members_by_time() -> None:
    """并入前文的旁听消息同样给出成员来源（#539）；被 @ 的成员由此得到速记。"""
    group = network_thread_id("mira", "qq", "g1")
    start = datetime(2026, 9, 30, 9, 0).astimezone()
    session = Session(key="role:mira")
    session.add_message(
        "user",
        "hi",
        thread_id=group,
        metadata={"message_source": {"channel": "qq", "sender_id": "111"}},
    )
    session.messages[-1]["timestamp"] = (start + timedelta(minutes=10)).isoformat()
    heard = [
        HeardLine(
            at=start + timedelta(minutes=minute),
            source=MessageSource(
                channel="qq",
                sender_id=sender_id,
                sender_is_user=sender_id == "902",
                mentioned_ids=mentioned,
            ),
            text="",
        )
        for minute, sender_id, mentioned in (
            (5, "222", ("888",)),
            (12, "902", ()),
            (15, "333", ()),
        )
    ]
    view = ContextView(
        scope="external",
        user_threads=UserContextThreads(
            role_id="mira",
            bound_chat_thread_ids=frozenset({desktop_thread_id("mira")}),
        ),
        thread_id=group,
    )

    sources = get_window_sources_since_consolidated(session, 50, view, heard)

    # 用户本人的旁听发言不算；旁听里被 @ 到的 888 随来源进入窗口。
    assert [source.sender_id for source in sources] == ["222", "111", "333"]
    assert sources[0].mentioned_ids == ("888",)
