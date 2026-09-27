from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import cast
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


def _listed(result: dict[str, object], field: str) -> list[object]:
    """Read one field from every item of a semantic list response."""
    return [item[field] for item in cast(list[dict[str, object]], result["items"])]


def _detail(result: dict[str, object], field: str) -> object:
    """Read one field from the item of a semantic detail response."""
    return cast(dict[str, object], result["item"])[field]


def _akasha_reader(
    tmp_path: Path,
    store: AkashaStore,
    messages: list[tuple[str, int, str]],
    *,
    persisted: set[tuple[str, int]] | None = None,
):
    """Index role messages into Akasha and persist the chosen ones as source text.

    ``messages`` holds ``(role_id, seq, content)``; ``persisted`` limits which
    of them also land in sessions.db (all by default).
    """
    from plugins.akasha.backend.role_memory import AkashaRoleMemoryReader

    roles = RoleStore(tmp_path)
    for role_id in sorted({role_id for role_id, _, _ in messages}):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    sessions_path = tmp_path / "sessions.db"
    with closing(sqlite3.connect(sessions_path)) as db:
        db.execute(
            "CREATE TABLE messages "
            "(id TEXT, session_key TEXT, seq INTEGER, role TEXT, content TEXT)"
        )
        for role_id, seq, content in messages:
            message = SourceMessage(
                id=f"role:{role_id}:{seq}",
                session_key=f"role:{role_id}",
                seq=seq,
                role="user",
                content=content,
                ts="2026-01-01T00:00:00+00:00",
            )
            store.upsert_message_node(message, [1.0, 0.0])
            if persisted is None or (role_id, seq) in persisted:
                db.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                    (message.id, message.session_key, seq, "user", content),
                )
        db.commit()
    engine = object.__new__(AkashaMemoryEngine)
    engine._store = store
    engine._session_db_path = sessions_path
    engine._akasha_config = AkashaConfig()
    return AkashaRoleMemoryReader(roles, engine)


@pytest.mark.asyncio
async def test_semantic_list_matches_like_wildcards_literally(tmp_path: Path) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        reader = _akasha_reader(
            tmp_path,
            store,
            [
                ("mira", 0, "plain tea"),
                ("mira", 2, "100% coffee"),
                ("mira", 4, "snake_case"),
                ("mira", 6, "a\\b"),
            ],
        )

        percent = await reader.list({"role_id": "mira", "q": "%"})
        underscore = await reader.list({"role_id": "mira", "q": "_"})
        backslash = await reader.list({"role_id": "mira", "q": "\\"})

        assert _listed(percent, "summary") == ["100% coffee"]
        assert _listed(underscore, "summary") == ["snake_case"]
        assert _listed(backslash, "summary") == ["a\\b"]
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_list_pages_same_time_items_without_gaps(
    tmp_path: Path,
) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        # 倒序写入，使 rowid 顺序与 key 顺序相反；同一 ts 让主排序键全部相等。
        seqs = [16, 14, 12, 10, 8, 6, 4, 2, 0]
        reader = _akasha_reader(
            tmp_path, store, [("mira", seq, f"text {seq}") for seq in seqs]
        )

        for sort_order in ("asc", "desc"):
            ids: list[object] = []
            for page in range(1, 6):
                result = await reader.list(
                    {
                        "role_id": "mira",
                        "sort_by": "happened_at",
                        "sort_order": sort_order,
                        "page": page,
                        "page_size": 2,
                    }
                )
                assert result["total"] == len(seqs)
                ids.extend(_listed(result, "id"))
            assert ids == sorted(f"role:mira:{seq}" for seq in seqs)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_items_without_source_text_have_empty_summary(
    tmp_path: Path,
) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        reader = _akasha_reader(
            tmp_path,
            store,
            [("mira", 0, "kept"), ("mira", 2, "lost")],
            persisted={("mira", 0)},
        )

        listed = await reader.list({"role_id": "mira", "sort_order": "asc"})
        detail = await reader.detail({"role_id": "mira", "item_id": "role:mira:2"})

        assert list(zip(_listed(listed, "id"), _listed(listed, "summary"))) == [
            ("role:mira:0", "kept"),
            ("role:mira:2", ""),
        ]
        assert _detail(detail, "summary") == ""
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_reads_isolate_two_roles(tmp_path: Path) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        reader = _akasha_reader(
            tmp_path,
            store,
            [("mira", 0, "shared word"), ("atlas", 0, "shared word")],
        )

        mira = await reader.list({"role_id": "mira", "q": "shared"})
        atlas = await reader.list({"role_id": "atlas"})

        assert _listed(mira, "id") == ["role:mira:0"]
        assert _listed(atlas, "id") == ["role:atlas:0"]
        detail = await reader.detail({"role_id": "atlas", "item_id": "role:atlas:0"})
        assert (
            cast(dict[str, object], _detail(detail, "extra_json"))["role_id"] == "atlas"
        )
        with pytest.raises(ValueError, match="memory item not found"):
            await reader.detail({"role_id": "atlas", "item_id": "role:mira:0"})
        with pytest.raises(ValueError, match="memory item not found"):
            await reader.detail({"role_id": "mira", "item_id": "role:atlas:0"})
    finally:
        store.close()


@pytest.mark.asyncio
async def test_semantic_reads_report_disabled_engine_after_role_validation(
    tmp_path: Path,
) -> None:
    from plugins.akasha.backend.role_memory import AkashaRoleMemoryReader

    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    reader = AkashaRoleMemoryReader(roles, None)

    listed = await reader.list({"role_id": "mira"})
    detail = await reader.detail({"role_id": "mira", "item_id": "role:mira:0"})

    assert listed == {"role_id": "mira", "status": "disabled", "items": [], "total": 0}
    assert detail == {"role_id": "mira", "status": "disabled", "item": None}
    with pytest.raises(ValueError, match="role not found"):
        await reader.list({"role_id": "atlas"})
    with pytest.raises(ValueError, match="role not found"):
        await reader.detail({"role_id": "atlas"})
