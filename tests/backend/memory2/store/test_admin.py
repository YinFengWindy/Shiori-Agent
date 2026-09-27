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


def test_list_items_for_admin_matches_like_wildcards_literally(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        store.upsert_item("preference", "plain tea", embedding=None, source_ref="ref")
        store.upsert_item(
            "preference", "100% coffee", embedding=None, source_ref="ref_1"
        )

        by_summary, summary_total = store.list_items_for_admin(q="%")
        by_ref, ref_total = store.list_items_for_admin(source_ref="_")

        assert summary_total == ref_total == 1
        assert [item["summary"] for item in by_summary] == ["100% coffee"]
        assert [item["summary"] for item in by_ref] == ["100% coffee"]
    finally:
        store.close()


def test_get_item_for_admin_normalizes_role_id_like_role_filter(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        item_id = store.upsert_item(
            "preference", "你喜欢拿铁", embedding=None, extra={"role_id": "  mira "}
        ).split(":", 1)[1]

        listed, _ = store.list_items_for_admin(role_id="mira")
        detail = store.get_item_for_admin(item_id)

        assert [item["id"] for item in listed] == [item_id]
        assert detail is not None
        assert detail["role_id"] == "mira"
        assert detail["extra_json"] == {"role_id": "  mira "}
    finally:
        store.close()
