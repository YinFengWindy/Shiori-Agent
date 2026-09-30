"""The role turns group listening on or off: any group from the user context,
only the current group when the user calls on it in a group (#540)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools.group_listening import SetGroupListeningTool
from agent.tools.registry import ToolRegistry
from conversation.listening import GroupListeningControl
from conversation.service import (
    ConversationService,
    LegacySessionDescriptor,
    desktop_thread_id,
)
from session.manager import SessionManager


def _groups(
    tmp_path: Path,
) -> tuple[ToolRegistry, GroupListeningControl, dict[str, str]]:
    """Role ``mira`` in QQ groups g1 (「猫猫群」) and g2; only QQ supports listening."""
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    session = manager.get_or_create("role:mira")
    threads: dict[str, str] = {}
    for chat_id in ("g1", "g2"):
        thread = conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"qq:{chat_id}",
                role_id="mira",
                channel="qq",
                chat_id=chat_id,
            )
        )
        session.add_message(
            "user", "hi", metadata={"thread_id": thread.id, "chat_type": "group"}
        )
        threads[chat_id] = thread.id
        if chat_id == "g1":
            conversation.remember_contact_name(thread, "猫猫群")
    manager.save(session)
    listening = GroupListeningControl(conversation, {"qq"}.__contains__)
    tools = ToolRegistry()
    tools.register(SetGroupListeningTool(listening), risk="write")
    return tools, listening, threads


@pytest.mark.asyncio
async def test_user_context_switches_any_group_logged_as_the_role(
    tmp_path: Path,
) -> None:
    tools, listening, threads = _groups(tmp_path)
    desktop = {
        "role_id": "mira",
        "thread_id": desktop_thread_id("mira"),
        "context_scope": "user",
        "sender_is_user": "true",
        "channel": "desktop",
        "chat_id": "role:mira",
    }

    # 桌面上没指明群：不是可旁听的群，报错列出候选。
    missing = await tools.execute(
        "set_group_listening", {"enabled": True}, context=desktop
    )
    assert "猫猫群（channel=qq, chat_id=g1）：未旁听" in str(missing)

    _ = await tools.execute(
        "set_group_listening",
        {"channel": "qq", "chat_id": "g2", "enabled": True},
        context=desktop,
    )

    switches = listening.store.switches
    assert switches.settings(threads["g2"]).enabled is True
    assert [
        (item.enabled, item.operator) for item in switches.toggles(threads["g2"])
    ] == [(True, "role")]


@pytest.mark.asyncio
async def test_the_user_in_a_group_switches_only_that_group(tmp_path: Path) -> None:
    tools, listening, threads = _groups(tmp_path)
    in_g1 = {
        "role_id": "mira",
        "thread_id": threads["g1"],
        "context_scope": "external",
        "sender_is_user": "true",
        "channel": "qq",
        "chat_id": "g1",
    }

    other = await tools.execute(
        "set_group_listening",
        {"channel": "qq", "chat_id": "g2", "enabled": True},
        context=in_g1,
    )
    here = await tools.execute("set_group_listening", {"enabled": True}, context=in_g1)

    switches = listening.store.switches
    assert "只能设置当前这个群" in str(other)
    assert switches.settings(threads["g2"]).enabled is False
    assert '"listening": true' in str(here)
    assert switches.settings(threads["g1"]).enabled is True


@pytest.mark.parametrize(
    "turn",
    [
        # 群友在群里触发的回合。
        {"context_scope": "external", "sender_is_user": "false"},
        # 上下文判定不了的回合（非角色会话、后台回传）。
        {"context_scope": "", "sender_is_user": "false"},
        {},
    ],
)
@pytest.mark.asyncio
async def test_turns_that_are_not_the_user_cannot_switch_listening(
    tmp_path: Path, turn: dict[str, str]
) -> None:
    tools, listening, threads = _groups(tmp_path)
    context = {"role_id": "mira", "thread_id": threads["g1"], **turn}

    result = await tools.execute(
        "set_group_listening",
        {"channel": "qq", "chat_id": "g1", "enabled": True},
        context=context,
    )

    assert "只有你的用户能让你设置旁听" in str(result)
    assert listening.store.switches.settings(threads["g1"]).enabled is False
