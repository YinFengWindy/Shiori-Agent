from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from plugins.default_memory.backend.semantic.store import MemoryStore2


def test_store_time_range_filters_mixed_timezone_happened_at(tmp_path: Path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    tz = ZoneInfo("Asia/Shanghai")
    store.upsert_item(
        "event",
        "[2026-04-25 01:00] 本地凌晨事件",
        [1.0, 0.0],
        happened_at="2026-04-25T01:00:00",
    )
    store.upsert_item(
        "event",
        "[2026-04-25 01:30] UTC 存储的凌晨事件",
        [1.0, 0.0],
        happened_at="2026-04-24T17:30:00+00:00",
    )
    store.upsert_item(
        "event",
        "[2026-04-24 23:00] 前一天本地事件",
        [1.0, 0.0],
        happened_at="2026-04-24T23:00:00",
    )

    hits = store.list_events_by_time_range(
        datetime(2026, 4, 25, 0, 0, tzinfo=tz),
        datetime(2026, 4, 26, 0, 0, tzinfo=tz),
        limit=20,
    )

    summaries = [str(item["summary"]) for item in hits]
    assert summaries == [
        "[2026-04-25 01:00] 本地凌晨事件",
        "[2026-04-25 01:30] UTC 存储的凌晨事件",
    ]


def test_store_time_range_limit_keeps_latest_events_in_chronological_order(
    tmp_path: Path,
) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    tz = ZoneInfo("Asia/Shanghai")
    for hour in (9, 10, 11):
        store.upsert_item(
            "event",
            f"[2026-04-25 {hour:02d}:00] 用户处理第 {hour} 点事件",
            [1.0, 0.0],
            happened_at=f"2026-04-25T{hour:02d}:00:00",
        )

    hits = store.list_events_by_time_range(
        datetime(2026, 4, 25, 0, 0, tzinfo=tz),
        datetime(2026, 4, 26, 0, 0, tzinfo=tz),
        limit=2,
    )

    assert [item["summary"] for item in hits] == [
        "[2026-04-25 10:00] 用户处理第 10 点事件",
        "[2026-04-25 11:00] 用户处理第 11 点事件",
    ]


def test_store_keyword_search_respects_required_scope(tmp_path: Path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    store.upsert_item(
        "event",
        "用户在当前会话讨论支付问题",
        None,
        extra={"scope_channel": "telegram", "scope_chat_id": "chat-a"},
    )
    store.upsert_item(
        "event",
        "用户在其他会话讨论支付问题",
        None,
        extra={"scope_channel": "telegram", "scope_chat_id": "chat-b"},
    )

    hits = store.keyword_search_summary(
        ["支付"],
        limit=10,
        scope_channel="telegram",
        scope_chat_id="chat-a",
        require_scope_match=True,
    )

    assert [item["summary"] for item in hits] == ["用户在当前会话讨论支付问题"]


def test_store_keyword_time_filter_prefilters_before_candidate_limit(
    tmp_path: Path,
) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    tz = ZoneInfo("Asia/Shanghai")
    for index in range(1005):
        store.upsert_item(
            "event",
            f"[2026-04-24 10:00] DeepSeek margin 内旧事件 {index}",
            None,
            happened_at="2026-04-24T10:00:00",
        )
    store._db.execute(
        "UPDATE memory_items SET reinforcement=20 WHERE happened_at=?",
        ("2026-04-24T10:00:00",),
    )
    store._db.commit()
    store.upsert_item(
        "event",
        "[2026-04-25 09:00] DeepSeek 今日事件",
        None,
        happened_at="2026-04-25T09:00:00",
    )

    hits = store.keyword_search_summary(
        ["DeepSeek"],
        limit=5,
        time_start=datetime(2026, 4, 25, 0, 0, tzinfo=tz),
        time_end=datetime(2026, 4, 26, 0, 0, tzinfo=tz),
    )

    assert [item["summary"] for item in hits] == [
        "[2026-04-25 09:00] DeepSeek 今日事件"
    ]


def test_keyword_match_procedures_filters_memory_type(tmp_path: Path):
    store = MemoryStore2(tmp_path / "mem.db")
    try:
        store.upsert_consolidation_event(
            source_ref="r1", summary="Event A", embedding=[0.0, 1.0]
        )
        store.upsert_item(
            "procedure",
            "Use pacman",
            [1.0, 0.0],
            extra={
                "trigger_tags": {
                    "scope": "tool_triggered",
                    "tools": [],
                    "skills": [],
                    "keywords": ["pacman"],
                }
            },
        )

        hits = store.keyword_match_procedures(["shell", "pacman"])

        assert hits and hits[0]["memory_type"] == "procedure"
        assert store.list_by_type("event")
    finally:
        store.close()


def test_store_keyword_search_respects_time_range(tmp_path: Path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    tz = ZoneInfo("Asia/Shanghai")
    store.upsert_item(
        "event",
        "[2026-04-25 01:30] DeepSeek 今日事件",
        [1.0, 0.0],
        happened_at="2026-04-24T17:30:00+00:00",
    )
    store.upsert_item(
        "event",
        "[2026-04-24 23:00] DeepSeek 昨日事件",
        [1.0, 0.0],
        happened_at="2026-04-24T23:00:00",
    )

    start = datetime(2026, 4, 25, 0, 0, tzinfo=tz)
    end = datetime(2026, 4, 26, 0, 0, tzinfo=tz)
    keyword_hits = store.keyword_search_summary(
        ["DeepSeek"],
        memory_types=["event"],
        limit=5,
        time_start=start,
        time_end=end,
    )

    assert [item["summary"] for item in keyword_hits] == [
        "[2026-04-25 01:30] DeepSeek 今日事件"
    ]
