from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.memory import FakeMemoryRoles
from shiori_sdk.testing.memory_context import FakeMemoryPluginContext

from plugins.default_memory.backend.role_memory import register_role_semantic_memory
from plugins.default_memory.backend.semantic.store import MemoryStore2


@pytest.mark.asyncio
async def test_semantic_rpc_filters_role_status_and_page_and_rejects_cross_role_detail(
    tmp_path: Path,
    make_store,
) -> None:
    workspace = tmp_path / "workspace"
    roles = FakeMemoryRoles(("mira", "atlas"))
    store = make_store(tmp_path / "memory.db")
    try:
        first_id = store.upsert_item(
            "preference",
            "Mira tea",
            embedding=[1.0, 0.0],
            extra={"role_id": "mira", "memory_domain": "taste"},
        ).split(":", 1)[1]
        second_id = store.upsert_item(
            "preference",
            "Mira coffee",
            embedding=None,
            extra={"role_id": "mira", "memory_domain": "taste"},
        ).split(":", 1)[1]
        atlas_id = store.upsert_item(
            "preference",
            "Atlas coffee",
            embedding=None,
            extra={"role_id": "atlas", "memory_domain": "taste"},
        ).split(":", 1)[1]
        store.update_item_for_admin(second_id, status="superseded")
        engine = SimpleNamespace(
            describe=lambda: SimpleNamespace(name="default"),
            list_items_for_admin=store.list_items_for_admin,
            list_role_filter_values=store.list_role_filter_values,
            get_item_for_admin=store.get_item_for_admin,
        )
        ctx = FakeMemoryPluginContext(workspace, roles=roles, engine=engine)
        register_role_semantic_memory(ctx)
        list_method = "roles.memory.semantic.list"
        detail_method = "roles.memory.semantic.detail"
        assert ctx.rpc.concurrency[list_method] is Concurrency.READ_ONLY
        assert ctx.rpc.concurrency[detail_method] is Concurrency.READ_ONLY
        list_rpc = ctx.rpc.handlers[list_method]
        detail_rpc = ctx.rpc.handlers[detail_method]
        active = await list_rpc({"role_id": "mira", "page_size": 1})
        assert active is not None
        assert active["total"] == 1
        assert _listed(active, "id") == [first_id]
        active_items = active["items"]
        assert isinstance(active_items, list)
        assert isinstance(active_items[0], dict)
        assert "embedding" not in active_items[0]
        filtered = await list_rpc(
            {
                "role_id": "mira",
                "status": "all",
                "q": "Mira",
                "memory_type": "preference",
                "memory_domain": "taste",
                "page_size": 1,
            }
        )
        assert filtered is not None
        assert filtered["total"] == 2
        assert len(_listed(filtered, "id")) == 1
        assert atlas_id not in _listed(filtered, "id")
        second_page = await list_rpc(
            {
                "role_id": "mira",
                "status": "all",
                "page": 2,
                "page_size": 1,
            }
        )
        assert second_page is not None
        assert second_page["total"] == 2
        assert {_listed(filtered, "id")[0], _listed(second_page, "id")[0]} == {
            first_id,
            second_id,
        }
        detail = await detail_rpc({"role_id": "mira", "item_id": first_id})
        assert detail is not None
        extra = _detail(detail, "extra_json")
        assert isinstance(extra, dict)
        assert extra["role_id"] == "mira"
        item = detail["item"]
        assert isinstance(item, dict)
        assert "embedding" not in item
        with pytest.raises(ValueError, match="memory item not found"):
            await detail_rpc({"role_id": "mira", "item_id": atlas_id})
        with pytest.raises(ValueError, match="role not found"):
            await list_rpc({"role_id": "missing"})
        await ctx.aclose()
        assert list_method not in ctx.rpc.handlers
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_list_declares_role_facets_and_sorts_by_occurrence_time(
    tmp_path: Path,
    make_store,
) -> None:
    store = make_store(tmp_path / "memory.db")
    try:
        reader = _store_reader(tmp_path, store, "mira", "atlas")
        # Written in reverse occurrence order so record-time sorting cannot pass.
        future_id = store.upsert_item(
            "plan",
            "Mira trip",
            embedding=None,
            extra={"role_id": "mira"},
            happened_at="2999-01-01T00:00:00+00:00",
        ).split(":", 1)[1]
        # No occurrence time: the record time (now) stands in for it.
        recorded_id = store.upsert_item(
            "preference",
            "Mira tea",
            embedding=None,
            extra={"role_id": "mira", "memory_domain": " taste "},
        ).split(":", 1)[1]
        past_id = store.upsert_item(
            "event",
            "Mira moved",
            embedding=None,
            extra={"role_id": "mira", "memory_domain": "life"},
            happened_at="2000-01-01T00:00:00+00:00",
        ).split(":", 1)[1]
        store.update_item_for_admin(future_id, status="superseded")
        store.upsert_item(
            "profile",
            "Atlas only",
            embedding=None,
            extra={"role_id": "atlas", "memory_domain": "atlas-domain"},
        )
        newest = await reader.list({"role_id": "mira", "status": "all"})
        # Superseded items still contribute; other roles and blank domains do not.
        assert newest["filters"] == {
            "memory_type": ["event", "plan", "preference"],
            "memory_domain": ["life", "taste"],
            "status": ["active", "superseded", "all"],
        }
        assert _listed(newest, "id") == [
            future_id,
            recorded_id,
            past_id,
        ]
        oldest = await reader.list(
            {"role_id": "mira", "status": "all", "sort_order": "asc"}
        )
        assert _listed(oldest, "id") == [
            past_id,
            recorded_id,
            future_id,
        ]
        for legacy_sort in ("updated_at", "created_at", "happened_at"):
            with pytest.raises(ValueError, match="sort_by is not supported"):
                await reader.list({"role_id": "mira", "sort_by": legacy_sort})
        with pytest.raises(ValueError, match="invalid sort order"):
            await reader.list({"role_id": "mira", "sort_order": "newest"})
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_reads_report_disabled_engine_after_role_validation(
    tmp_path: Path,
) -> None:
    from plugins.default_memory.backend.role_memory import DefaultRoleMemoryReader

    roles = FakeMemoryRoles(("mira",))
    reader = DefaultRoleMemoryReader(roles, None)
    assert (await reader.list({"role_id": "mira"}))["status"] == "disabled"
    assert (await reader.detail({"role_id": "mira"}))["status"] == "disabled"
    with pytest.raises(ValueError, match="role not found"):
        await reader.list({"role_id": "atlas"})


def _listed(result: dict[str, object], field: str) -> list[object]:
    """Read one field from every item of a semantic list response."""
    return [item[field] for item in cast(list[dict[str, object]], result["items"])]


def _detail(result: dict[str, object], field: str) -> object:
    """Read one field from the item of a semantic detail response."""
    return cast(dict[str, object], result["item"])[field]


def _store_reader(tmp_path: Path, store: MemoryStore2, *role_ids: str):
    """Build a reader over a real memory2 store with the given persisted roles."""
    from plugins.default_memory.backend.role_memory import DefaultRoleMemoryReader

    roles = FakeMemoryRoles(role_ids)
    engine = SimpleNamespace(
        list_items_for_admin=store.list_items_for_admin,
        list_role_filter_values=store.list_role_filter_values,
        get_item_for_admin=store.get_item_for_admin,
    )
    return DefaultRoleMemoryReader(roles, engine)


@pytest.mark.asyncio
async def test_semantic_list_matches_like_wildcards_literally(
    tmp_path: Path, make_store
) -> None:
    store = make_store(tmp_path / "memory.db")
    try:
        reader = _store_reader(tmp_path, store, "mira")
        for summary in ("Mira tea", "Mira 100% coffee", "Mira snake_case", "a\\b"):
            store.upsert_item(
                "preference", summary, embedding=None, extra={"role_id": "mira"}
            )

        percent = await reader.list({"role_id": "mira", "q": "%"})
        underscore = await reader.list({"role_id": "mira", "q": "_"})
        backslash = await reader.list({"role_id": "mira", "q": "\\"})

        assert _listed(percent, "summary") == ["Mira 100% coffee"]
        assert _listed(underscore, "summary") == ["Mira snake_case"]
        assert _listed(backslash, "summary") == ["a\\b"]
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_detail_accepts_items_the_list_shows_for_padded_role_id(
    tmp_path: Path,
    make_store,
) -> None:
    store = make_store(tmp_path / "memory.db")
    try:
        reader = _store_reader(tmp_path, store, "mira", "atlas")
        padded_id = store.upsert_item(
            "preference", "Mira tea", embedding=None, extra={"role_id": "  mira "}
        ).split(":", 1)[1]
        atlas_id = store.upsert_item(
            "preference", "Atlas tea", embedding=None, extra={"role_id": " atlas"}
        ).split(":", 1)[1]

        listed = await reader.list({"role_id": "mira"})
        detail = await reader.detail({"role_id": "mira", "item_id": padded_id})

        assert _listed(listed, "id") == [padded_id]
        assert _detail(detail, "id") == padded_id
        with pytest.raises(ValueError, match="memory item not found"):
            await reader.detail({"role_id": "mira", "item_id": atlas_id})
        with pytest.raises(ValueError, match="memory item not found"):
            await reader.detail({"role_id": "atlas", "item_id": padded_id})
    finally:
        store.close()
