"""The role looks up member profiles: by name among every nickname, by ID (#540)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.tools.member_lookup import LookupMemberTool
from agent.tools.registry import ToolRegistry
from conversation.service import ConversationService, LegacySessionDescriptor
from core.memory.member_profiles import MemberKey, MemberProfileUpdate, MemberProfiles
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_name_matches_old_nicknames_and_id_returns_the_profile(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group = conversation.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:g1", role_id="mira", channel="qq", chat_id="g1"
        )
    )
    members = MemberProfiles(tmp_path)
    # 555 从「阿明」改名「明哥」；另一个渠道的同名成员不算本渠道。
    members.apply(
        "mira",
        MemberProfileUpdate(MemberKey("qq", "555"), "g1", ("阿明",), profile="爱狗"),
    )
    members.apply("mira", MemberProfileUpdate(MemberKey("qq", "555"), "g1", ("明哥",)))
    members.apply(
        "mira", MemberProfileUpdate(MemberKey("telegram", "9"), "t1", ("阿明",))
    )
    tools = ToolRegistry()
    tools.register(LookupMemberTool(members, conversation), external_allowed=True)
    in_group = {
        "role_id": "mira",
        "thread_id": group.id,
        "context_scope": "external",
        "channel": "qq",
    }

    by_name = json.loads(
        str(await tools.execute("lookup_member", {"name": "阿明"}, context=in_group))
    )
    by_id = json.loads(
        str(
            await tools.execute("lookup_member", {"member_id": "555"}, context=in_group)
        )
    )
    other_channel = await tools.execute(
        "lookup_member", {"name": "阿明", "channel": "telegram"}, context=in_group
    )

    assert by_name["candidates"] == [
        {"member_id": "555", "name": "明哥", "nicknames": ["阿明", "明哥"]}
    ]
    assert "profile" not in by_name["candidates"][0]
    assert by_id["name"] == "明哥" and by_id["profile"] == "爱狗"
    assert "只能查当前渠道" in str(other_channel)
