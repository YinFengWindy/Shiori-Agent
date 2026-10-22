"""Automatic CG reaches the chat that produced the scene, through account delivery."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.role_events import SceneObservationCommitted
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.account_delivery import AccountDelivery
from agent.plugin_host import HostServices, PluginKernel
from bootstrap.plugin_core import plugin_core_modules
from agent.provider import LLMResponse, ToolCall
from agent.tools.account_delivery import AccountSendTool
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.turns.turn_pushes import current_turn_pushes
from bootstrap.runtime.generations import RuntimeCandidate
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from conversation.push_sync import ExternalPushSyncService
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.common.runtime_scope import bind_runtime
from core.identity import IdentityChat, UserIdentityStore
from core.roles.store import RoleStore
from session.manager import SessionManager


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


async def test_cg_reaches_the_bound_qq_chat_through_account_delivery(
    tmp_path: Path,
) -> None:
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.update(
        "novelai", lambda data: data.update({"mira": {"auto_scene_cg_enabled": True}})
    )
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    record = accounts.register(
        plugin_id="qq",
        platform="qq",
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
        chat=IdentityChat(record.id, "qq", "902"),
    )
    send = AsyncMock(return_value={"message_id": "cg-receipt"})
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(
        accounts,
        SimpleNamespace(resolve=lambda _: ("qq", send)),
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
        core=plugin_core_modules(),
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
                    channel="qq",
                    chat_id="902",
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
        assert stored["thread_id"] == network_thread_id("mira", "qq", "902")
        assert stored["media"] == [image]
        assert stored.get("proactive", False) is False
        assert sessions._store.get_presence("role:mira") == presence_before
        assert stored["metadata"]["external_message_id"] == "cg-receipt"
        [attempt] = ledger.list_for_role("mira")
        assert attempt.status == "sent"
    finally:
        await lease.release()
        await kernel.unload("novelai")
