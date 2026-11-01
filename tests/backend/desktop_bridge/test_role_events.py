"""``RoleCreated`` leaves the bridge on the same bus as ``RoleDeleted``."""

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
async def test_bridge_publishes_role_created(tmp_path):
    roles = RoleStore(tmp_path)
    sessions = SessionManager(tmp_path)
    bus = EventBus()
    seen: list[object] = []
    bus.on(RoleCreated, lambda event: seen.append(event))
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
    finally:
        await bridge.aclose()
        await bus.aclose()


@pytest.mark.asyncio
async def test_bridge_publishes_proactive_switch_only_when_it_changes(tmp_path):
    roles = RoleStore(tmp_path)
    sessions = SessionManager(tmp_path)
    bus = EventBus()
    seen: list[object] = []
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
        assert seen == []
        bridge.role_service.update_role("mira", proactive={"enabled": True})
        await bus.drain()
        assert seen == [RoleProactiveChanged("mira", True)]
        bridge.role_service.update_role("mira", proactive={"enabled": True})
        await bus.drain()
        assert seen == [RoleProactiveChanged("mira", True)]
        roles.write_plugin_proactive("mira", {"enabled": False})
        await bus.drain()
        assert seen == [
            RoleProactiveChanged("mira", True),
            RoleProactiveChanged("mira", False),
        ]
    finally:
        await bridge.aclose()
        await bus.aclose()
