from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.method_policy import Concurrency
from plugins.akasha.backend.config import AkashaConfig
from plugins.akasha.backend.engine import AkashaMemoryEngine
from plugins.akasha.backend.store import AkashaStore, SourceMessage


@pytest.mark.asyncio
async def test_semantic_rpc_filters_akasha_store_by_role_before_paging_and_detail(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    stage_plugin_package(Path(__file__).resolve().parents[1], plugin_root / "akasha")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    roles = RoleStore(workspace)
    for role_id in ("mira", "atlas"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    store = AkashaStore(tmp_path / "akasha.db")
    sessions_path = tmp_path / "sessions.db"
    with sqlite3.connect(sessions_path) as db:
        db.execute(
            "CREATE TABLE messages (id TEXT, session_key TEXT, seq INTEGER, role TEXT, content TEXT)"
        )
    try:
        for role_id, seq in (("mira", 0), ("mira", 2), ("atlas", 0)):
            session_key = f"role:{role_id}"
            message = SourceMessage(
                id=f"{session_key}:{seq}",
                session_key=session_key,
                seq=seq,
                role="user",
                content=f"{role_id} text {seq}",
                ts="2026-01-01T00:00:00+00:00",
            )
            store.upsert_message_node(message, [1.0, 0.0])
            with sqlite3.connect(sessions_path) as db:
                db.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                    (
                        message.id,
                        message.session_key,
                        message.seq,
                        message.role,
                        message.content,
                    ),
                )
        engine = object.__new__(AkashaMemoryEngine)
        engine._store = store
        engine._session_db_path = sessions_path
        engine._akasha_config = AkashaConfig()
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
        list_method = "plugin.akasha.roles.memory.semantic.list"
        detail_method = "plugin.akasha.roles.memory.semantic.detail"
        assert kernel.rpc.policy_for(list_method).concurrency is Concurrency.READ_ONLY
        assert kernel.rpc.policy_for(detail_method).concurrency is Concurrency.READ_ONLY
        list_rpc = kernel.rpc.resolve(list_method)[1]
        detail_rpc = kernel.rpc.resolve(detail_method)[1]
        first = await list_rpc({"role_id": "mira", "page_size": 1})
        second = await list_rpc({"role_id": "mira", "page": 2, "page_size": 1})
        assert first["total"] == second["total"] == 2
        assert len(first["items"]) == len(second["items"]) == 1
        assert "status" not in first["items"][0]
        assert "status" not in second["items"][0]
        assert {first["items"][0]["id"], second["items"][0]["id"]} == {
            "role:mira:0",
            "role:mira:2",
        }
        assert (await list_rpc({"role_id": "mira", "q": "atlas text"}))["total"] == 0
        search = await list_rpc({"role_id": "mira", "q": "mira text 2"})
        assert search["total"] == 1
        assert search["items"][0]["summary"] == "mira text 2"
        detail = await detail_rpc({"role_id": "mira", "item_id": "role:mira:0"})
        assert detail["item"]["extra_json"]["role_id"] == "mira"
        assert detail["item"]["summary"] == "mira text 0"
        assert "status" not in detail["item"]
        assert "embedding" not in detail["item"]
        assert store.get_item_for_admin("role:mira:0")["status"] == "active"
        with pytest.raises(ValueError, match="memory item not found"):
            await detail_rpc({"role_id": "mira", "item_id": "role:atlas:0"})
        await kernel.unload("akasha")
        assert kernel.rpc.resolve(list_method) is None
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_list_sorts_by_turn_time_and_declares_no_structured_filters(
    tmp_path: Path,
) -> None:
    from plugins.akasha.backend.role_memory import AkashaRoleMemoryReader

    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        # Insertion order differs from turn time so the sort cannot pass by accident.
        for seq, ts in (
            (0, "2026-01-02T00:00:00+00:00"),
            (2, "2026-01-03T00:00:00+00:00"),
            (4, "2026-01-01T00:00:00+00:00"),
        ):
            store.upsert_message_node(
                SourceMessage(
                    id=f"role:mira:{seq}",
                    session_key="role:mira",
                    seq=seq,
                    role="user",
                    content=f"text {seq}",
                    ts=ts,
                ),
                [1.0, 0.0],
            )
        engine = object.__new__(AkashaMemoryEngine)
        engine._store = store
        engine._session_db_path = tmp_path / "missing-sessions.db"
        engine._akasha_config = AkashaConfig()
        reader = AkashaRoleMemoryReader(roles, engine)

        newest = await reader.list({"role_id": "mira"})
        assert newest["filters"] == {}
        assert _item_ids(newest) == [
            "role:mira:2",
            "role:mira:0",
            "role:mira:4",
        ]
        oldest = await reader.list({"role_id": "mira", "sort_order": "asc"})
        assert _item_ids(oldest) == [
            "role:mira:4",
            "role:mira:0",
            "role:mira:2",
        ]
        for key in ("memory_type", "memory_domain", "status"):
            with pytest.raises(ValueError, match=f"akasha does not filter by: {key}"):
                await reader.list({"role_id": "mira", key: "turn"})
        with pytest.raises(ValueError, match="sort_by is not supported"):
            await reader.list({"role_id": "mira", "sort_by": "updated_at"})
    finally:
        store.close()


def _item_ids(response: dict[str, object]) -> list[object]:
    """Read item IDs in response order from a direct reader call."""
    items = response["items"]
    assert isinstance(items, list)
    ids: list[object] = []
    for item in items:
        assert isinstance(item, dict)
        ids.append(item["id"])
    return ids
