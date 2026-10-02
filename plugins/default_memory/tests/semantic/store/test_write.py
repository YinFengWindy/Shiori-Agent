from __future__ import annotations

from pathlib import Path


def test_upsert_consolidation_event_fills_missing_happened_at_on_duplicate(
    tmp_path, make_store
):
    store = make_store(tmp_path / "memory2.db")

    store.upsert_consolidation_event(
        source_ref="session@1",
        summary="[2026-03-08 12:00] same",
        embedding=[0.1, 0.2, 0.3],
    )
    store.upsert_consolidation_event(
        source_ref="session@2",
        summary="[2026-03-08 12:00] same",
        embedding=[0.1, 0.2, 0.3],
        happened_at="2026-03-08T12:00:00",
    )

    items = store.list_by_type("event")
    assert len(items) == 1
    assert items[0]["happened_at"] == "2026-03-08T12:00:00"


def test_upsert_item_reinforces_equivalent_summaries(tmp_path: Path, make_store):
    store = make_store(tmp_path / "mem.db")
    try:
        first = store.upsert_item(
            "procedure", "Hello   world", [1.0, 0.0], source_ref="s1"
        )
        assert first.startswith("new:")
        item_id = first.split(":", 1)[1]

        assert store.upsert_item("procedure", "hello world", [1.0, 0.0]).startswith(
            "reinforced:"
        )
        # 标记 superseded 之后仍应命中同一条目并加固，而不是新建重复项
        store.mark_superseded(item_id)
        assert store.upsert_item("procedure", "hello world", [1.0, 0.0]).startswith(
            "reinforced:"
        )

        store.mark_superseded_batch([item_id])
        assert store.get_all_with_embedding(include_superseded=True)
        assert store.has_item_by_source_ref("s1", "procedure") is True
        assert store.delete_by_source_ref("s1") >= 1
    finally:
        store.close()


def test_upsert_consolidation_event_is_idempotent_per_source_ref(
    tmp_path: Path, make_store
):
    store = make_store(tmp_path / "mem.db")
    try:
        created = store.upsert_consolidation_event(
            source_ref="r1", summary="Event A", embedding=[0.0, 1.0]
        )
        repeated = store.upsert_consolidation_event(
            source_ref="r1", summary="Event A", embedding=[0.0, 1.0]
        )

        assert created.startswith("new:")
        assert repeated.startswith("skipped:")
    finally:
        store.close()


def test_record_replacements_keeps_both_summaries_and_extras(
    tmp_path: Path, make_store
):
    store = make_store(tmp_path / "mem.db")
    try:
        old_res = store.upsert_item(
            "procedure",
            "旧流程：查 Steam 时直接用 web_search",
            [1.0, 0.0],
            source_ref="old-rule",
            extra={"tool_requirement": "web_search"},
        )
        new_res = store.upsert_item(
            "procedure",
            "新流程：查 Steam 时必须先用 steam_mcp",
            [0.9, 0.1],
            source_ref="new-rule",
            extra={"tool_requirement": "steam_mcp"},
        )
        old_item = store.get_items_by_ids([old_res.split(":", 1)[1]])[0]
        new_item = store.get_items_by_ids([new_res.split(":", 1)[1]])[0]

        recorded = store.record_replacements(
            old_items=[old_item],
            new_item=new_item,
            source_ref="test@replace",
        )

        assert recorded == 1
        replacements = store.list_replacements()
        assert replacements[0]["old_summary"] == "旧流程：查 Steam 时直接用 web_search"
        assert replacements[0]["new_summary"] == "新流程：查 Steam 时必须先用 steam_mcp"
        assert replacements[0]["old_extra_json"]["tool_requirement"] == "web_search"
        assert replacements[0]["new_extra_json"]["tool_requirement"] == "steam_mcp"
    finally:
        store.close()
