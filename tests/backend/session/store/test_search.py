"""Thread-limited reads of the session search mixin."""

from pathlib import Path

from session.store import SessionStore


def _store(tmp_path: Path) -> SessionStore:
    """role:mira has seq 0 unthreaded, 1/3 desktop, 2 group; role:other has one group row."""
    store = SessionStore(tmp_path / "sessions.db")
    rows = {
        "role:mira": [None, "desktop", "group", "desktop"],
        "role:other": ["other-group"],
        "legacy": [None],
    }
    for key, threads in rows.items():
        store.create_session(key=key, metadata={})
        for seq, thread_id in enumerate(threads):
            store.insert_message(
                key,
                role="user",
                content=f"天气 {key} {seq}",
                ts="2026-09-29T12:00:00",
                seq=seq,
                thread_id=thread_id,
            )
    return store


def test_thread_ids_by_session_lists_each_prefixed_session(tmp_path: Path):
    store = _store(tmp_path)
    try:
        assert store.thread_ids_by_session("role:") == {
            "role:mira": ["", "desktop", "group"],
            "role:other": ["other-group"],
        }
    finally:
        store.close()


def test_fetch_message_around_sees_only_the_threads_of_its_session(tmp_path: Path):
    store = _store(tmp_path)
    asked: list[str] = []

    def desktop(session_key: str) -> set[str]:
        asked.append(session_key)
        return {"", "desktop"}

    try:
        around = store.fetch_message_around(
            "role:mira:1", context=1, thread_ids_for_session=desktop
        )
        hidden = store.fetch_message_around(
            "role:mira:2", thread_ids_for_session=desktop
        )
        missing = store.fetch_message_around(
            "role:mira:9", thread_ids_for_session=desktop
        )

        assert [message["seq"] for message in around["messages"]] == [0, 1, 3]
        assert around["total_count"] == 3
        assert hidden["messages"] == []
        assert missing["messages"] == []
        # A missing target is not found without consulting the thread filter.
        assert asked == ["role:mira", "role:mira"]
    finally:
        store.close()


def test_search_limits_hits_by_thread_and_session_prefix(tmp_path: Path):
    store = _store(tmp_path)
    try:
        hits, total = store.search_message_previews(
            "天气", thread_ids={"", "desktop"}, session_prefix="role:"
        )

        assert sorted(hit["id"] for hit in hits) == [
            "role:mira:0",
            "role:mira:1",
            "role:mira:3",
        ]
        assert total == 3
    finally:
        store.close()
