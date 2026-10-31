"""Role lifecycle events leave the bridge on the same bus as ``RoleDeleted``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from conversation.listening import GroupListeningControl
from conversation.service import ConversationService
from core.memory.group_environment import GroupEnvironment
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager
from shiori_sdk.role_events import RoleCreated, RoleProactiveChanged
from tests.support.generation_getters import bound_affection


@pytest.mark.asyncio
async def test_bridge_publishes_role_created_and_the_proactive_switch(tmp_path):
    roles = RoleStore(tmp_path)
    sessions = SessionManager(tmp_path)
    bus = EventBus()
    seen: list[object] = []
    bus.on(RoleCreated, lambda event: seen.append(event))
    bus.on(RoleProactiveChanged, lambda event: seen.append(event))
    bridge = DesktopBridgeService(
        workspace=tmp_path,
        affection=bound_affection(),
        role_store=roles,
        session_manager=sessions,
        agent_loop=cast(AgentLoop, SimpleNamespace()),
        event_bus=bus,
        group_environment=GroupEnvironment(tmp_path, sessions.conversation_store),
        group_listening=GroupListeningControl(
            ConversationService(sessions), lambda _channel: False
        ),
        presence=sessions.presence,
    )
    try:
        bridge.role_service.create_role(
            role_id="mira", name="Mira", system_prompt="mira"
        )
        await bus.drain()
        assert seen == [RoleCreated("mira")]
        bridge.role_store.update_role(
            "mira", proactive={"enabled": True, "profile": "daily"}
        )
        bridge.role_store.update_role("mira", description="edited")
        await bus.drain()
        assert seen == [RoleCreated("mira"), RoleProactiveChanged("mira", True)]
        bridge.role_store.write_plugin_proactive(
            "mira", {"enabled": False, "profile": "daily"}
        )
        await bus.drain()
        assert seen[-1] == RoleProactiveChanged("mira", False)
    finally:
        await bridge.aclose()
        bridge.role_store.update_role(
            "mira", proactive={"enabled": True, "profile": "daily"}
        )
        await bus.drain()
        await bus.aclose()
    assert seen[-1] == RoleProactiveChanged("mira", False)
