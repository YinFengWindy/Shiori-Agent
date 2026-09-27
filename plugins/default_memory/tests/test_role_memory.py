from __future__ import annotations

from pathlib import Path
from typing import cast
from types import SimpleNamespace

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.method_policy import Concurrency
from memory2.store import MemoryStore2


@pytest.mark.asyncio
async def test_semantic_rpc_filters_role_status_and_page_and_rejects_cross_role_detail(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    stage_plugin_package(
        Path(__file__).resolve().parents[1], plugin_root / "default_memory"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    roles = RoleStore(workspace)
    for role_id in ("mira", "atlas"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    store = MemoryStore2(tmp_path / "memory.db")
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
            get_item_for_admin=store.get_item_for_admin,
        )
        kernel = PluginKernel(
            [plugin_root],
            services=HostServices(
                event_bus=EventBus(),
                workspace=workspace,
                role_store=roles,
                memory_engine=engine,
            ),
        )
        await kernel.load_all()
        list_method = "plugin.default_memory.roles.memory.semantic.list"
        detail_method = "plugin.default_memory.roles.memory.semantic.detail"
        assert kernel.rpc.policy_for(list_method).concurrency is Concurrency.READ_ONLY
        assert kernel.rpc.policy_for(detail_method).concurrency is Concurrency.READ_ONLY
        list_rpc = kernel.rpc.resolve(list_method)[1]
        detail_rpc = kernel.rpc.resolve(detail_method)[1]

        active = await list_rpc({"role_id": "mira", "page_size": 1})
        assert active["total"] == 1
        assert [item["id"] for item in active["items"]] == [first_id]
        assert "embedding" not in active["items"][0]
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
        assert filtered["total"] == 2
        assert len(filtered["items"]) == 1
        assert all(item["id"] != atlas_id for item in filtered["items"])
        second_page = await list_rpc(
            {
                "role_id": "mira",
                "status": "all",
                "page": 2,
                "page_size": 1,
            }
        )
        assert second_page["total"] == 2
        assert {filtered["items"][0]["id"], second_page["items"][0]["id"]} == {
            first_id,
            second_id,
        }
        detail = await detail_rpc({"role_id": "mira", "item_id": first_id})
        assert detail["item"]["extra_json"]["role_id"] == "mira"
        assert "embedding" not in detail["item"]
        with pytest.raises(ValueError, match="memory item not found"):
            await detail_rpc({"role_id": "mira", "item_id": atlas_id})
        with pytest.raises(ValueError, match="role not found"):
            await list_rpc({"role_id": "missing"})
        await kernel.unload("default_memory")
        assert kernel.rpc.resolve(list_method) is None
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_reads_report_disabled_engine_after_role_validation(
    tmp_path: Path,
) -> None:
    from plugins.default_memory.backend.role_memory import DefaultRoleMemoryReader

    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
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

    roles = RoleStore(tmp_path)
    for role_id in role_ids:
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    engine = SimpleNamespace(
        list_items_for_admin=store.list_items_for_admin,
        get_item_for_admin=store.get_item_for_admin,
    )
    return DefaultRoleMemoryReader(roles, engine)


@pytest.mark.asyncio
async def test_semantic_list_matches_like_wildcards_literally(tmp_path: Path) -> None:
    store = MemoryStore2(tmp_path / "memory.db")
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
) -> None:
    store = MemoryStore2(tmp_path / "memory.db")
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
