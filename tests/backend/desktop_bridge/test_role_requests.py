from pathlib import Path
from conversation.listening import GroupListeningControl
from conversation.service import ConversationService
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from bus.event_bus import EventBus
from core.roles import RoleRelationshipRuntimeService, RoleStore
from core.roles.relationship_runtime.affection_prompts import (
    DEFAULT_AFFECTION_STAGE_PROMPTS,
)
from desktop_bridge.service import DesktopBridgeService
from desktop_bridge.role_requests import DesktopRoleRequestHandler
from desktop_bridge.role_card_export_service import DesktopRoleCardExportService
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager
from core.memory.group_environment import GroupEnvironment


def _write_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (20, 20), "white")
    for x in range(6, 14):
        for y in range(4, 17):
            image.putpixel((x, y), color)
    image.save(path)


@pytest.mark.asyncio
async def test_role_card_preview_forwards_the_full_payload_to_its_service() -> None:
    card_import = SimpleNamespace(
        preview=AsyncMock(return_value={"import_id": "preview-1"})
    )
    handler = DesktopRoleRequestHandler(
        role_service=SimpleNamespace(),
        role_presenter=SimpleNamespace(),
        card_import_service=card_import,
        publish_event=AsyncMock(),
    )

    result = await handler.handle(
        "roles.cardImport.preview",
        {"source": "C:/workspace/private_runtime/imports/role-cards/card.json"},
    )

    card_import.preview.assert_awaited_once_with(
        {"source": "C:/workspace/private_runtime/imports/role-cards/card.json"}
    )
    assert result == {"import_id": "preview-1"}


@pytest.mark.asyncio
async def test_role_card_export_routes_snapshot_lifecycle_without_mutating_roles(
    tmp_path,
):
    store = RoleStore(tmp_path)
    role = store.create_role(name="目标角色", system_prompt="规则")
    handler = DesktopRoleRequestHandler(
        role_service=SimpleNamespace(),
        role_presenter=SimpleNamespace(),
        publish_event=AsyncMock(),
        card_export_service=DesktopRoleCardExportService(store),
    )
    preview = await handler.handle(
        "roles.cardExport.preview", {"role_id": role.id, "format": "json"}
    )
    assert preview["name"] == role.name
    saved = await handler.handle(
        "roles.cardExport.read", {"export_id": preview["export_id"]}
    )
    assert saved["format"] == "json"
    await handler.handle(
        "roles.cardExport.release", {"export_id": preview["export_id"]}
    )
    with pytest.raises(ValueError, match="失效"):
        await handler.handle(
            "roles.cardExport.read", {"export_id": preview["export_id"]}
        )
    assert store.list_roles() == [role]


@pytest.mark.asyncio
async def test_role_create_persists_structured_profile(tmp_path: Path) -> None:
    role_store = RoleStore(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=(bridge_sessions := SessionManager(tmp_path)),
        group_listening=GroupListeningControl(
            ConversationService(bridge_sessions), lambda _channel: False
        ),
        group_environment=GroupEnvironment(
            tmp_path, bridge_sessions.conversation_store
        ),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )
    profile = {
        "character": {
            "profile": "A meticulous archivist.",
            "personality": "Calm and precise.",
            "behavior_rules": "Use concise answers and cite the archive.",
            "response_constraints": "Use short paragraphs.",
            "nickname": "",
        },
        "knowledge_base": {"enabled": True, "entries": [], "raw_source": {}},
    }

    response = await service.handle(
        {
            "id": "create-structured-role",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "A role",
                "system_prompt": profile["character"]["behavior_rules"],
                "profile": profile,
            },
        },
        emit_event=lambda _payload: None,
    )

    assert response.error is None
    assert response.payload["role"]["profile"] == {
        "version": 1,
        "character": profile["character"],
    }
    persisted = role_store.get_role(response.payload["role"]["id"])
    assert persisted is not None
    assert persisted.profile.to_dict() == {
        "version": 1,
        "character": profile["character"],
    }

    published = []
    service.add_event_listener(published.append)

    update = await service.handle(
        {
            "id": "update-role-knowledge",
            "method": "roles.update",
            "payload": {
                "role_id": response.payload["role"]["id"],
                "profile": {
                    "knowledge_base": {
                        "enabled": False,
                        "entries": [],
                    }
                },
            },
        },
        emit_event=lambda _payload: None,
    )

    assert update.error is None
    assert any(
        event["method"] == "roles.updated"
        and event["payload"]["role_id"] == persisted.id
        for event in published
    )
    assert update.payload["role"]["profile"]["character"] == profile["character"]
    assert "knowledge_base" not in update.payload["role"]["profile"]

    cleared_rules = await service.handle(
        {
            "id": "clear-role-behavior-rules",
            "method": "roles.update",
            "payload": {
                "role_id": response.payload["role"]["id"],
                "system_prompt": "",
                "profile": {"character": {"behavior_rules": ""}},
            },
        },
        emit_event=lambda _payload: None,
    )
    assert cleared_rules.error is None
    character = cleared_rules.payload["role"]["profile"]["character"]
    assert character["behavior_rules"] == ""
    assert character["response_constraints"] == "Use short paragraphs."
    assert character["profile"] == "A meticulous archivist."
    await service.aclose()


@pytest.mark.asyncio
async def test_the_core_bridge_no_longer_answers_pet_package_methods() -> None:
    """#181-D: pet package management belongs to the plugin that owns it.

    `handle` returning `None` is how this router says "not mine", which lets
    the plugin RPC dispatcher downstream pick the method up as
    `plugin.desktop_pet.pets.*`. If these branches came back, the core bridge
    would answer first and the plugin's copy would silently never run.
    """
    handler = DesktopRoleRequestHandler(
        role_service=SimpleNamespace(),
        role_presenter=SimpleNamespace(),
        card_import_service=SimpleNamespace(),
        publish_event=AsyncMock(),
    )

    for method in ("roles.pets.import", "roles.pets.remove", "roles.pets.select"):
        assert (
            await handler.handle(method, {"role_id": "mira", "package_id": "pet-1"})
            is None
        )


@pytest.mark.asyncio
async def test_role_update_commits_generic_plugin_draft_and_projects_its_owner(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Before", system_prompt="test")

    def write(role_id, draft, data):
        data[role_id] = draft

    store.extensions.register(
        "sample", write, lambda role_id, data: data.get(role_id, {})
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=store,
        session_manager=(bridge_sessions := SessionManager(tmp_path)),
        group_listening=GroupListeningControl(
            ConversationService(bridge_sessions), lambda _channel: False
        ),
        group_environment=GroupEnvironment(
            tmp_path, bridge_sessions.conversation_store
        ),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )
    response = await service.handle(
        {
            "id": "save",
            "method": "roles.update",
            "payload": {
                "role_id": "mira",
                "name": "After",
                "plugin_drafts": {"sample": {"enabled": True}},
            },
        },
        emit_event=lambda _payload: None,
    )
    assert response.error is None
    assert response.payload["role"]["plugin_state"] == {"sample": {"enabled": True}}
    assert store.get_role("mira").name == "After"
    assert "plugin_state" not in store.get_role("mira").to_dict()


@pytest.mark.asyncio
async def test_role_delete_first_deletes_its_accounts_through_their_plugins(
    tmp_path: Path,
) -> None:
    from shiori_sdk.accounts.models import AccountDeletionPlan
    from agent.scheduler import SchedulerService
    from tests.support.scheduler import make_job

    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    role_store.create_role(role_id="luna", name="Luna", system_prompt="Luna")
    accounts = role_store.accounts
    for role_id, account in (("mira", "101"), ("luna", "102")):
        accounts.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id=account,
            config_ref=f"ref-{account}",
            token="generation",
            role_id=role_id,
        )
    purged: list[str] = []
    failing = {"ref-101"}

    def plan(config_ref: str) -> AccountDeletionPlan:
        async def disconnect() -> None:
            return None

        async def purge() -> None:
            if config_ref in failing:
                failing.discard(config_ref)
                raise OSError("locked")
            purged.append(config_ref)

        return AccountDeletionPlan(disconnect, purge)

    accounts.set_delete_handler("chat", plan)
    scheduler = SchedulerService(tmp_path / "schedules.json", push_tool=AsyncMock())
    job = make_job(role_id="mira")
    scheduler.add_job(job)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=(bridge_sessions := SessionManager(tmp_path)),
        group_listening=GroupListeningControl(
            ConversationService(bridge_sessions), lambda _channel: False
        ),
        group_environment=GroupEnvironment(
            tmp_path, bridge_sessions.conversation_store
        ),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        scheduler=scheduler,
    )
    request = {"id": "delete", "method": "roles.delete", "payload": {"role_id": "mira"}}
    try:
        # A plugin that cannot clean up keeps both the role and its account.
        failed = await service.handle(request, emit_event=AsyncMock())
        assert failed.error is not None
        assert failed.error.message == "本地服务处理失败，请查看详情"
        assert "locked" in failed.error.details["detail"]
        assert role_store.get_role("mira") is not None
        assert [row.record.id for row in accounts.list(role_id="mira")] == ["chat:101"]
        assert scheduler.list_jobs() == [job]

        deleted = await service.handle(request, emit_event=AsyncMock())
        assert deleted.error is None
        assert deleted.payload["deleted_accounts"] == ["chat:101"]
        assert purged == ["ref-101"]
        assert role_store.get_role("mira") is None
        assert [row.record.id for row in accounts.list()] == ["chat:102"]
        assert scheduler.list_jobs() == []
        assert scheduler.store.load() == []
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_role_delete_schedule_cleanup_failure_is_visible_and_retryable(
    tmp_path: Path, monkeypatch
) -> None:
    from agent.scheduler import SchedulerService
    from tests.support.scheduler import make_job

    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    scheduler = SchedulerService(tmp_path / "schedules.json", push_tool=AsyncMock())
    job = make_job(role_id="mira")
    scheduler.add_job(job)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=(sessions := SessionManager(tmp_path)),
        group_listening=GroupListeningControl(
            ConversationService(sessions), lambda _channel: False
        ),
        group_environment=GroupEnvironment(tmp_path, sessions.conversation_store),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        scheduler=scheduler,
    )
    request = {"id": "delete", "method": "roles.delete", "payload": {"role_id": "mira"}}

    def fail_save(_jobs):
        raise OSError("schedule store locked")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(scheduler.store, "save", fail_save)
            failed = await service.handle(request, emit_event=AsyncMock())
        assert failed.error is not None
        assert "schedule store locked" in failed.error.details["detail"]
        assert role_store.get_role("mira") is not None
        assert scheduler.list_jobs() == [job]
        assert [saved.id for saved in scheduler.store.load()] == [job.id]

        deleted = await service.handle(request, emit_event=AsyncMock())
        assert deleted.error is None
        assert role_store.get_role("mira") is None
        assert scheduler.list_jobs() == []
        assert scheduler.store.load() == []
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_affection_history_pages_newest_first_through_the_bridge(
    tmp_path: Path,
) -> None:
    role_store = RoleStore(tmp_path)
    sessions = SessionManager(tmp_path)
    relationship = RoleRelationshipRuntimeService(
        tmp_path,
        role_store=role_store,
        session_manager=sessions,
        presence=PresenceStore(sessions._store),
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=sessions,
        group_listening=GroupListeningControl(
            ConversationService(sessions), lambda _channel: False
        ),
        group_environment=GroupEnvironment(tmp_path, sessions.conversation_store),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        relationship_runtime=relationship,
    )
    role_store.create_role(role_id="mira", name="Mira", system_prompt="规则")

    async def page(number: int) -> dict:
        response = await service.handle(
            {
                "id": f"affection-{number}",
                "method": "roles.affection.history",
                "payload": {"role_id": "mira", "page": number, "page_size": 2},
            },
            emit_event=lambda _payload: None,
        )
        assert response.error is None
        return response.payload

    assert await page(1) == {
        "role_id": "mira",
        "affection": None,
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 2,
    }

    relationship.affection.initialize("mira", value=30, reason="初始")
    relationship.affection.apply_delta("mira", delta=2, reason="夸奖", source="turn")
    relationship.affection.apply_delta("mira", delta=-1, reason="冷淡", source="turn")

    first, last = await page(1), await page(2)
    assert first["affection"] == {"value": 31, "stage": "熟悉", "progress": 11 / 19}
    assert [item["reason"] for item in first["items"]] == ["冷淡", "夸奖"]
    assert first["items"][0] | {"time": ""} == {
        "id": 2,
        "time": "",
        "before": 32,
        "after": 31,
        "delta": -1,
        "reason": "冷淡",
        "source": "turn",
    }
    assert [(item["id"], item["source"], item["after"]) for item in last["items"]] == [
        (0, "init", 30)
    ]
    assert first["total"] == last["total"] == 3
    await service.aclose()


@pytest.mark.asyncio
async def test_affection_stage_prompts_write_and_restore_through_the_bridge(
    tmp_path: Path,
) -> None:
    sessions = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=sessions,
        group_listening=GroupListeningControl(
            ConversationService(sessions), lambda _channel: False
        ),
        group_environment=GroupEnvironment(tmp_path, sessions.conversation_store),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="规则")

    async def call(method: str, **payload: object):
        response = await service.handle(
            {"id": method, "method": method, "payload": {"role_id": "mira", **payload}},
            emit_event=lambda _payload: None,
        )
        return response

    async def stages(
        method: str = "roles.affection.stagePrompts.get", **payload: object
    ):
        response = await call(method, **payload)
        assert response.error is None
        return {item["stage"]: item for item in response.payload["stages"]}

    def stored_overrides() -> dict[str, str]:
        role = RoleStore(tmp_path).get_role("mira")
        assert role is not None
        return role.affection_stage_prompts

    try:
        initial = await stages()
        assert list(initial) == list(DEFAULT_AFFECTION_STAGE_PROMPTS)
        assert all(
            item["prompt"] == item["default"] == DEFAULT_AFFECTION_STAGE_PROMPTS[stage]
            and not item["overridden"]
            for stage, item in initial.items()
        )

        written = await stages(
            "roles.affection.stagePrompts.set",
            prompts={"熟悉": "嘴硬心软。", "朋友": "  "},
        )
        assert written["熟悉"]["prompt"] == "嘴硬心软。"
        assert written["熟悉"]["overridden"]
        assert not written["朋友"]["overridden"]
        # Persisted in the role config: a later read still has it.
        assert (await stages())["熟悉"]["prompt"] == "嘴硬心软。"
        assert stored_overrides() == {"熟悉": "嘴硬心软。"}

        # Writing the default text, or null, restores the default.
        restored = await stages(
            "roles.affection.stagePrompts.set",
            prompts={"熟悉": DEFAULT_AFFECTION_STAGE_PROMPTS["熟悉"]},
        )
        assert restored["熟悉"] == initial["熟悉"]
        _ = await stages("roles.affection.stagePrompts.set", prompts={"挚爱": "黏人。"})
        assert not (
            await stages("roles.affection.stagePrompts.set", prompts={"挚爱": None})
        )["挚爱"]["overridden"]
        assert stored_overrides() == {}

        rejected = await call(
            "roles.affection.stagePrompts.set", prompts={"暧昧": "不存在的阶段"}
        )
        assert rejected.error is not None
    finally:
        await service.aclose()
