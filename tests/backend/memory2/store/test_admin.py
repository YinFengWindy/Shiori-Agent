from memory2.store import MemoryStore2


def test_invalidate_role_memories_only_supersedes_target_role(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        mira_id = store.upsert_item(
            "preference",
            "你喜欢拿铁",
            embedding=None,
            extra={"role_id": "mira"},
        ).split(":", 1)[1]
        atlas_id = store.upsert_item(
            "preference",
            "你喜欢红茶",
            embedding=None,
            extra={"role_id": "atlas"},
        ).split(":", 1)[1]

        assert store.invalidate_role_memories("mira") == 1

        assert store.get_item_for_admin(mira_id)["status"] == "superseded"
        assert store.get_item_for_admin(atlas_id)["status"] == "active"
    finally:
        store.close()


def test_invalidate_role_memories_requires_role_id(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        try:
            store.invalidate_role_memories("  ")
        except ValueError as exc:
            assert str(exc) == "role_id required for memory invalidation"
        else:
            raise AssertionError("missing role_id must fail")
    finally:
        store.close()


def test_list_role_filter_values_counts_only_the_role_and_skips_blank_domains(
    tmp_path,
) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        store.upsert_item(
            "preference",
            "你喜欢拿铁",
            embedding=None,
            extra={"role_id": "mira", "memory_domain": "taste"},
        )
        store.upsert_item(
            "event", "你搬家了", embedding=None, extra={"role_id": "mira"}
        )
        store.upsert_item(
            "profile",
            "你是图书管理员",
            embedding=None,
            extra={"role_id": "atlas", "memory_domain": "work"},
        )

        assert store.list_role_filter_values("mira") == {
            "memory_type": ["event", "preference"],
            "memory_domain": ["taste"],
        }
        assert store.list_role_filter_values("nobody") == {
            "memory_type": [],
            "memory_domain": [],
        }
    finally:
        store.close()


def test_list_items_for_admin_sorts_occurred_at_with_record_time_fallback(
    tmp_path,
) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        later = store.upsert_item(
            "event",
            "未来的旅行",
            embedding=None,
            happened_at="2999-01-01T00:00:00+00:00",
        ).split(":", 1)[1]
        undated = store.upsert_item(
            "event", "没有发生时间", embedding=None, happened_at=""
        ).split(":", 1)[1]
        earlier = store.upsert_item(
            "event",
            "很久以前",
            embedding=None,
            happened_at="2000-01-01T00:00:00+00:00",
        ).split(":", 1)[1]

        items, _ = store.list_items_for_admin(sort_by="occurred_at", sort_order="asc")

        assert [item["id"] for item in items] == [earlier, undated, later]
    finally:
        store.close()
