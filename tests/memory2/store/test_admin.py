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
