"""Background capability keeps a runtime generation alive for NovelAI's auto CG.

The plugin is loaded through the real ``PluginKernel``; the CG task is reached
only through a published ``SceneObservationCommitted`` and the registered
``generate_image`` tool, so the host's ``spawn_runtime`` lease is exercised
without importing plugin internals. Controller scheduling rules live in
``plugins/novelai/tests/test_auto_cg_controller.py``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.role_events import SceneObservationCommitted
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.provider import LLMResponse, ToolCall
from agent.tools.message_push import MessagePushTool
from tests.support.push import allow_every_role_target
from agent.tools.registry import ToolRegistry
from agent.tools.account_delivery import AccountSendTool
from agent.account_delivery import AccountDelivery
from agent.turns.turn_pushes import current_turn_pushes
from bootstrap.runtime.generations import RuntimeCandidate
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from conversation.push_sync import ExternalPushSyncService
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.identity import IdentityChat, UserIdentityStore
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.roles.store import RoleStore
from session.manager import SessionManager
from shiori_sdk.channels.threads import network_thread_id


def _prompt_provider() -> SimpleNamespace:
    """Light model that always submits one scene prompt."""
    return SimpleNamespace(
        chat=AsyncMock(
            return_value=LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        "cg",
                        "submit_scene_image_prompt",
                        {
                            "prompt": "1girl, rain",
                            "negative_prompt": "blurry",
                            "size_preset": "portrait",
                        },
                    )
                ],
            )
        )
    )


@pytest.mark.asyncio
async def test_cg_task_holds_generation_until_image_work_finishes(tmp_path: Path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.update(
        "novelai", lambda data: data.update({"mira": {"auto_scene_cg_enabled": True}})
    )
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    event_bus, registry = EventBus(), ToolRegistry()
    push_image = AsyncMock(return_value=None)
    push_tool = MessagePushTool(role_target_validator=allow_every_role_target)
    push_tool.register_channel("desktop", image_with_metadata=push_image)
    registry.register(push_tool)
    stage_plugin_package(plugin_directory("novelai"), tmp_path / "plugins/novelai")
    kernel = PluginKernel(
        [tmp_path / "plugins"],
        services=HostServices(
            http=FakeHttp(),
            light_provider=_prompt_provider(),
            light_model="light",
            event_bus=event_bus,
            tool_registry=registry,
            workspace=tmp_path,
            role_store=roles,
            session_manager=sessions,
            plugin_configs={"novelai": {"enabled": True, "token": "novel-token"}},
        ),
    )
    await kernel.load_all()
    generate_tool = registry.get_tool("generate_image")
    assert generate_tool is not None
    started, finish = asyncio.Event(), asyncio.Event()
    observed: list[int] = []
    image = str(tmp_path / "cg.png")

    async def generate(**_kwargs: object) -> str:
        observed.append(current_runtime_lease().generation)
        started.set()
        await finish.wait()
        return json.dumps({"output_paths": [image]})

    generate_tool.execute = generate
    core = SimpleNamespace(
        stop=AsyncMock(), memory_runtime=SimpleNamespace(aclose=AsyncMock())
    )
    generation = RuntimeCandidate(3, core, SimpleNamespace())
    parent = generation.acquire()
    with bind_runtime(parent):
        await event_bus.fanout(
            SceneObservationCommitted(
                session_key="role:mira",
                channel="desktop",
                chat_id="role:mira",
                role_id="mira",
                source="passive",
                transition="started",
                scene_key="rain",
                visual_key="rain-standing",
                visual_description="少女站在雨里",
            )
        )
    await parent.release()
    await generation.retire()
    await asyncio.wait_for(started.wait(), timeout=2)
    core.stop.assert_not_awaited()
    finish.set()
    await asyncio.wait_for(generation.drained.wait(), timeout=2)
    assert observed == [3]
    push_image.assert_awaited_once()
    assert push_image.await_args.args[:2] == ("role:mira", image)
    core.stop.assert_awaited_once()
    assert await kernel.unload("novelai") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin_id,transport,chat_id",
    [
        ("qq", "qq", "902"),
        ("qqbot", "qqbot", "c2c:101:902"),
        ("telegram", "telegram_mira", "dm:902"),
    ],
)
async def test_cg_reaches_original_bound_chat_through_real_account_delivery(
    tmp_path: Path, plugin_id: str, transport: str, chat_id: str
):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.update(
        "novelai", lambda data: data.update({"mira": {"auto_scene_cg_enabled": True}})
    )
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    record = accounts.register(
        plugin_id=plugin_id,
        platform=plugin_id,
        platform_account_id="101",
        config_ref="101",
        token="live",
        role_id="mira",
    ).record
    accounts.report(record.id, "live", connection="online")
    identities = UserIdentityStore(tmp_path)
    identities.pair(
        identities.create_pairing_code().code,
        record=record,
        user_id="902",
        scope="account",
        chat=IdentityChat(record.id, transport, chat_id),
    )
    send = AsyncMock(return_value={"message_id": "cg-receipt"})
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(
        accounts,
        SimpleNamespace(resolve=lambda _: (plugin_id, send)),
        ledger,
        identities,
    )
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    bus, registry = EventBus(), ToolRegistry()
    synced = asyncio.Event()
    bus.on(ProactiveMessageCommitted, lambda _: synced.set())
    _ = ExternalPushSyncService(
        session_manager=sessions, event_bus=bus, live_turn_pushes=current_turn_pushes
    )
    registry.register(AccountSendTool(delivery, bus))
    # Production policy rejects any role-owned external message_push call.
    registry.register(MessagePushTool(role_target_validator=lambda *_: False))
    stage_plugin_package(plugin_directory("novelai"), tmp_path / "plugins/novelai")
    kernel = PluginKernel(
        [tmp_path / "plugins"],
        services=HostServices(
            http=FakeHttp(),
            light_provider=_prompt_provider(),
            light_model="light",
            event_bus=bus,
            tool_registry=registry,
            workspace=tmp_path,
            role_store=roles,
            session_manager=sessions,
            plugin_configs={"novelai": {"enabled": True, "token": "novel-token"}},
        ),
    )
    await kernel.load_all()
    generate = registry.get_tool("generate_image")
    assert generate is not None
    sessions._store.update_presence(
        "role:mira", last_proactive_at="2026-10-20T12:00:00+00:00"
    )
    presence_before = sessions._store.get_presence("role:mira")
    image = "https://example.test/cg.png"
    generate.execute = AsyncMock(return_value=json.dumps({"output_paths": [image]}))
    core = SimpleNamespace(
        stop=AsyncMock(), memory_runtime=SimpleNamespace(aclose=AsyncMock())
    )
    generation = RuntimeCandidate(3, core, SimpleNamespace())
    lease = generation.acquire()
    try:
        with bind_runtime(lease):
            await bus.fanout(
                SceneObservationCommitted(
                    session_key="role:mira",
                    channel=transport,
                    chat_id=chat_id,
                    role_id="mira",
                    source="passive",
                    transition="started",
                    scene_key="rain",
                    visual_key="standing",
                    visual_description="少女站在雨里",
                )
            )
        await asyncio.wait_for(synced.wait(), timeout=2)
        send.assert_awaited_once()
        assert send.await_args.args[0]["target_id"] == "902"
        assert send.await_args.args[0]["media"] == [image]
        [stored] = sessions._store.fetch_session_messages("role:mira")
        assert stored["thread_id"] == network_thread_id("mira", transport, chat_id)
        assert stored["media"] == [image]
        assert stored.get("proactive", False) is False
        assert sessions._store.get_presence("role:mira") == presence_before
        assert stored["metadata"]["external_message_id"] == "cg-receipt"
        [attempt] = ledger.list_for_role("mira")
        assert attempt.status == "sent"
    finally:
        await lease.release()
        await kernel.unload("novelai")
