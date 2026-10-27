from __future__ import annotations

import json
from pathlib import Path


from plugins.default_memory.backend.engine import DefaultMemoryEngine
from plugins.default_memory.backend.semantic.store import MemoryStore2


def _item_id_admin_undo(result: str) -> str:
    return result.split(":", 1)[1]


def _engine_admin_undo(store: MemoryStore2) -> DefaultMemoryEngine:
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    engine._v2_store = store
    return engine


def test_rollback_turn_marks_direct_source_memory_superseded(
    tmp_path: Path, make_store
):
    store = make_store(tmp_path / "memory2.db")
    try:
        engine = _engine_admin_undo(store)
        item_id = _item_id_admin_undo(
            store.upsert_item(
                memory_type="preference",
                summary="用户喜欢简短回复",
                embedding=[0.1, 0.2],
                source_ref="cli:1:1",
            )
        )

        result = engine.rollback_turn("cli:1:1", ("cli:1:1", "cli:1:2"))

        assert result.affected_ids == (item_id,)
        assert store.get_items_by_ids([item_id])[0]["status"] == "superseded"
    finally:
        store.close()


def test_rollback_turn_marks_consolidation_window_memory_superseded(
    tmp_path: Path, make_store
):
    store = make_store(tmp_path / "memory2.db")
    try:
        engine = _engine_admin_undo(store)
        base = json.dumps(["cli:1:0", "cli:1:1", "cli:1:2"], ensure_ascii=False)
        history_id = _item_id_admin_undo(
            store.upsert_item(
                memory_type="event",
                summary="用户完成了压缩前的一轮任务",
                embedding=[0.1, 0.2],
                source_ref=f"{base}#h:abc",
            )
        )
        profile_id = _item_id_admin_undo(
            store.upsert_item(
                memory_type="profile",
                summary="用户在测试 undo",
                embedding=[0.2, 0.3],
                source_ref=f"{base}#profile",
            )
        )

        result = engine.rollback_turn("cli:1:1", ("cli:1:1",))

        assert set(result.affected_ids) == {history_id, profile_id}
        assert result.rollback_source_ids == ("cli:1:0", "cli:1:1", "cli:1:2")
        rows = store.get_items_by_ids([history_id, profile_id])
        assert [row["status"] for row in rows] == ["superseded", "superseded"]
    finally:
        store.close()


def test_rollback_turn_covers_a_window_holding_only_the_turns_reply(
    tmp_path: Path, make_store
):
    """A turn cut across two windows: the later one has only tool and reply ids."""
    store = make_store(tmp_path / "memory2.db")
    try:
        engine = _engine_admin_undo(store)
        windows = (
            ["cli:1:1", "cli:1:2", "cli:1:3"],
            ["cli:1:4", "cli:1:5", "cli:1:6"],
        )
        ids = [
            _item_id_admin_undo(
                store.upsert_item(
                    memory_type="event",
                    summary=f"窗口 {index}",
                    embedding=[0.1, 0.2],
                    source_ref=json.dumps(window) + "#h:abc",
                )
            )
            for index, window in enumerate(windows)
        ]

        # 这一轮：上下文帧 2、用户 3、工具 4、助手 5。
        result = engine.rollback_turn(
            "cli:1:3", ("cli:1:2", "cli:1:3", "cli:1:4", "cli:1:5")
        )

        assert set(result.affected_ids) == set(ids)
        assert result.rollback_source_ids == tuple(f"cli:1:{n}" for n in range(1, 7))
        rows = store.get_items_by_ids(ids)
        assert [row["status"] for row in rows] == ["superseded", "superseded"]
    finally:
        store.close()


def test_rollback_turn_restores_old_memory_replaced_by_affected_new_memory(
    tmp_path: Path, make_store
):
    store = make_store(tmp_path / "memory2.db")
    try:
        engine = _engine_admin_undo(store)
        old_id = _item_id_admin_undo(
            store.upsert_item(
                memory_type="preference",
                summary="旧偏好",
                embedding=[0.1, 0.2],
                source_ref="cli:1:old",
            )
        )
        new_id = _item_id_admin_undo(
            store.upsert_item(
                memory_type="preference",
                summary="新偏好",
                embedding=[0.2, 0.3],
                source_ref="cli:1:4",
            )
        )
        old_item = store.get_items_by_ids([old_id])[0]
        new_item = store.get_items_by_ids([new_id])[0]
        store.mark_superseded_batch([old_id])
        store.record_replacements(
            old_items=[old_item], new_item=new_item, source_ref="cli:1:4"
        )

        result = engine.rollback_turn("cli:1:4", ("cli:1:4",))

        assert result.affected_ids == (new_id,)
        assert result.restored_ids == (old_id,)
        old_row, new_row = store.get_items_by_ids([old_id, new_id])
        assert old_row["status"] == "active"
        assert new_row["status"] == "superseded"
    finally:
        store.close()
