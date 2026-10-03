from __future__ import annotations

import json

import pytest
from types import SimpleNamespace
from typing import Any, cast

from conversation.context_scope import (
    UserContextThreads,
    belongs_to_user,
    role_context_views,
)
from conversation.service import desktop_thread_id
from shiori_sdk.channels.threads import network_thread_id
from session.manager import Session

from core.memory.markdown import (
    build_consolidation_source_ref,
    format_conversation_for_consolidation,
    _format_pending_items,
    _parse_consolidation_payload,
    _select_consolidation_window,
)


def _window_session() -> SimpleNamespace:
    return SimpleNamespace(
        key="telegram:1",
        last_consolidated=0,
        messages=[
            {"role": "user", "content": "u1", "timestamp": "2025-01-01T10:00:00"},
            {"role": "assistant", "content": "a1", "timestamp": "2025-01-01T10:01:00"},
            {"role": "tool", "content": "skip", "timestamp": "2025-01-01T10:02:00"},
            {
                "role": "assistant",
                "content": "skip proactive",
                "timestamp": "2025-01-01T10:03:00",
                "proactive": True,
            },
        ],
    )


def test_format_pending_items_dedups_and_drops_unknown_shapes():
    assert _format_pending_items("x") == ""
    assert (
        _format_pending_items(
            [
                {"tag": "preference", "content": "喜欢 A"},
                {"tag": "preference", "content": "喜欢 A"},
                {"tag": "bad", "content": "忽略"},
                "x",
            ]
        )
        == "- [preference] 喜欢 A"
    )


def test_parse_consolidation_payload_reads_json_object():
    assert _parse_consolidation_payload('{"x":1}') == {"x": 1}


def test_select_consolidation_window_requires_enough_new_messages():
    session = _window_session()
    assert (
        _select_consolidation_window(
            session,
            keep_count=5,
            consolidation_min_new_messages=10,
            archive_all=False,
        )
        is None
    )

    enough = SimpleNamespace(
        key="telegram:2",
        last_consolidated=0,
        messages=[{"role": "user", "content": "u", "timestamp": "2025-01-01T10:00:00"}]
        * 16,
    )
    assert (
        _select_consolidation_window(
            enough,
            keep_count=5,
            consolidation_min_new_messages=10,
            archive_all=False,
        )
        is not None
    )
    assert (
        _select_consolidation_window(
            enough,
            keep_count=5,
            consolidation_min_new_messages=12,
            archive_all=False,
        )
        is None
    )


def test_select_consolidation_window_archive_all_takes_whole_history():
    window = _select_consolidation_window(
        _window_session(),
        keep_count=2,
        consolidation_min_new_messages=10,
        archive_all=True,
    )
    assert window and window.consolidate_up_to == 4


def test_select_consolidation_window_uses_required_range_without_message_threshold():
    session = SimpleNamespace(
        key="telegram:tokens",
        last_consolidated=0,
        messages=[
            {"role": "user", "content": "x" * 600},
            {"role": "assistant", "content": "y" * 600},
            {"role": "user", "content": "z"},
        ],
    )
    window = _select_consolidation_window(
        session,
        keep_count=1,
        consolidation_min_new_messages=99,
        archive_all=False,
        through_index=2,
    )

    assert window is not None
    assert len(window.old_messages) == 2
    assert window.keep_count == 1


def test_select_consolidation_window_archives_small_session_when_only_turn_is_huge():
    session = SimpleNamespace(
        key="telegram:huge",
        last_consolidated=0,
        messages=[{"role": "user", "content": "x" * 600}],
    )
    window = _select_consolidation_window(
        session,
        keep_count=20,
        consolidation_min_new_messages=10,
        archive_all=False,
        through_index=1,
    )

    assert window is not None
    assert window.consolidate_up_to == 1
    assert window.keep_count == 0


def test_build_consolidation_source_ref_keeps_only_messages_with_ids():
    window = SimpleNamespace(
        old_messages=[
            {"id": "telegram:1:0"},
            {"id": "telegram:1:1"},
            {"content": "missing id"},
        ]
    )
    assert json.loads(
        build_consolidation_source_ref(cast(Any, window).old_messages)
    ) == [
        "telegram:1:0",
        "telegram:1:1",
    ]


def test_format_conversation_for_consolidation_skips_tool_and_proactive_turns():
    conversation = format_conversation_for_consolidation(_window_session().messages)
    assert conversation.count("USER") == 1


@pytest.mark.parametrize("archive_all", [False, True])
def test_consolidation_window_does_not_reclassify_pre_binding_messages(
    archive_all: bool,
):
    desktop = desktop_thread_id("mira")
    bound = network_thread_id("mira", "qq", "902")
    group = network_thread_id("mira", "qq", "group:7")
    threads = UserContextThreads(
        "mira",
        frozenset({desktop, bound}),
        context_since={bound: "2026-01-01T00:00:10+00:00"},
    )
    session = Session("role:mira")
    for thread, content, timestamp in (
        (bound, "excluded old DM", "2026-01-01T00:00:09+00:00"),
        (desktop, "existing desktop", "2026-01-01T00:00:00+00:00"),
        (bound, "new DM", "2026-01-01T00:00:10+00:00"),
        (group, "group chatter", "2026-01-01T00:00:00+00:00"),
    ):
        session.add_message("user", content, thread_id=thread, timestamp=timestamp)

    window = _select_consolidation_window(
        session,
        keep_count=0,
        consolidation_min_new_messages=5,
        archive_all=archive_all,
        force=True,
        views=role_context_views(threads),
    )

    assert window is not None
    assert [message["content"] for message in window.old_messages] == [
        "existing desktop",
        "new DM",
        "group chatter",
    ]
    assert window.consolidate_up_to == 4
    assert window.scopes == ("user", "external")
    # Filtering model/maintenance input does not rewrite raw history or identity.
    assert len(session.messages) == 4
    assert belongs_to_user(session.messages[0], threads)
