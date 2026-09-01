from __future__ import annotations

from pathlib import Path

from session.store import SessionStore


def test_fetch_session_messages_preserves_media_path(tmp_path: Path) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    current_image = workspace / "private_runtime" / "novelai" / "output.png"
    current_image.parent.mkdir(parents=True)
    current_image.write_bytes(b"png")
    store = SessionStore(workspace / "sessions.db")
    store.create_session(key="role:mira", metadata={})
    store.insert_message(
        "role:mira",
        role="assistant",
        content="image",
        ts="2026-07-13T12:00:00+08:00",
        seq=0,
        media=[str(current_image)],
    )

    messages = store.fetch_session_messages("role:mira")

    assert messages[0]["media"] == [str(current_image)]
    store.close()


def test_fetch_messages_page_uses_seq_cursor_and_preserves_order(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    store.create_session(key="role:mira", metadata={})
    for seq in (0, 2, 5, 8):
        store.insert_message(
            "role:mira",
            role="assistant",
            content=f"m{seq}",
            ts=f"2026-07-13T12:00:0{seq % 10}+08:00",
            seq=seq,
        )

    latest = store.fetch_messages_page("role:mira", limit=2)
    assert [message["seq"] for message in latest["messages"]] == [5, 8]
    assert latest["has_more"] is True
    assert latest["next_before_seq"] == 5
    assert latest["oldest_seq"] == 5
    assert latest["newest_seq"] == 8
    assert latest["session_oldest_seq"] == 0
    assert latest["session_newest_seq"] == 8
    assert store.fetch_messages_page("role:mira", limit=1000)["limit"] == 100

    earlier = store.fetch_messages_page(
        "role:mira", before_seq=latest["messages"][0]["seq"], limit=2
    )
    assert [message["seq"] for message in earlier["messages"]] == [0, 2]
    assert earlier["has_more"] is False
    store.close()


def test_fetch_image_history_omits_message_content_and_non_media_rows(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    store.create_session(key="role:mira", metadata={})
    store.insert_message(
        "role:mira",
        role="assistant",
        content="不应传给图片历史的正文",
        ts="2026-07-13T12:00:00+08:00",
        seq=0,
    )
    store.insert_message(
        "role:mira",
        role="assistant",
        content="也不应传给图片历史的正文",
        ts="2026-07-13T12:01:00+08:00",
        seq=2,
        media=["old.png", "attachment.txt"],
    )

    assert store.fetch_image_history("role:mira") == [{
        "id": "role:mira:2",
        "seq": 2,
        "timestamp": "2026-07-13T12:01:00+08:00",
        "media": ["old.png", "attachment.txt"],
    }]
    store.close()


def test_fetch_message_around_locates_by_id_with_seq_holes(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    store.create_session(key="role:mira", metadata={})
    for seq in (1, 4, 9):
        store.insert_message(
            "role:mira",
            role="assistant",
            content=f"m{seq}",
            ts="2026-07-13T12:00:00+08:00",
            seq=seq,
        )

    around = store.fetch_message_around("role:mira:4", context=1)
    assert [message["seq"] for message in around["messages"]] == [1, 4, 9]
    assert [message["id"] for message in around["messages"] if message["is_target"]] == [
        "role:mira:4"
    ]
    assert around["has_more_before"] is False
    assert around["has_more_after"] is False
    store.close()


def test_search_message_previews_omit_heavy_fields(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    store.create_session(key="role:mira", metadata={})
    store.insert_message(
        "role:mira",
        role="assistant",
        content="天气很好" + "x" * 100,
        ts="2026-07-13T12:00:00+08:00",
        seq=0,
        tool_chain=[{"calls": [{"call_id": "c1", "name": "tool"}]}],
        media=["image.png"],
    )

    results, total = store.search_message_previews("天气", preview_length=40)
    assert total == 1
    assert results[0]["id"] == "role:mira:0"
    assert results[0]["preview"].endswith("...")
    assert "content" not in results[0]
    assert "tool_chain" not in results[0]
    assert "media" not in results[0]
    store.close()
