"""旁听记录按群整理（#541）：触发、产出与只推进旁听游标。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.provider import LLMProvider
from bus.event_bus import EventBus
from conversation.listening_store import GroupListeningStore
from conversation.service import desktop_thread_id, network_thread_id
from core.memory.events import ConsolidationCommitted
from core.memory.group_environment import GroupEnvironment
from core.memory.markdown import (
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MemoryLifecycleBindRequest,
)
from core.memory.member_profiles import MemberKey, MemberProfiles
from core.roles import RoleStore
from session.manager import SessionManager
from session.manager.models import consolidation_cursor

_GROUP = network_thread_id("mira", "qq", "g1")
_DAY = datetime(2026, 9, 29, 20, 0).astimezone()
_SOURCE = {"channel": "qq", "chat_id": "g1", "group_name": "猫猫群"}
_ENVIRONMENT_REPLY = json.dumps(
    {
        "recent_activity": "阿明在群里聊他的狗",
        "group_note": "## 氛围\n轻松",
        "members": {"555": {"profile": "## 印象\n喜欢狗", "brief": "阿明：爱狗"}},
    },
    ensure_ascii=False,
)


class _Provider:
    """按提示词种类返回固定结果，并记下各步收到的提示词。"""

    def __init__(self) -> None:
        self.user_layer_prompts: list[str] = []
        self.environment_prompts: list[str] = []

    async def chat(self, *, messages: list[dict[str, str]], **_kwargs: Any):
        prompt = messages[-1]["content"]
        if prompt.startswith("群环境整理"):
            self.environment_prompts.append(prompt)
            return SimpleNamespace(content=_ENVIRONMENT_REPLY)
        self.user_layer_prompts.append(prompt)
        return SimpleNamespace(
            content=(
                '{"history_entries": [{"summary": "[2026-09-29 20:00] 你说明天去面试",'
                ' "emotional_weight": 0}], "pending_items": []}'
            )
        )


def _setup(tmp_path: Path):
    """角色会话里已有桌面对话，旁听整理接上真实的旁听记录与群环境层。"""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "我喜欢猫", thread_id=desktop_thread_id("mira"))
    session.add_message("assistant", "猫很可爱", thread_id=desktop_thread_id("mira"))
    manager.save(session)
    store = manager.conversation_store
    store.upsert_thread(
        thread_id=_GROUP,
        role_id="mira",
        contact_id="contact:qq:g1",
        channel="qq",
        thread_kind="network",
        external_thread_id="g1",
        legacy_session_key="qq:g1",
    )
    store.listening.switches.set_enabled(_GROUP, True, operator="user")
    provider = _Provider()
    event_bus = EventBus()
    events: list[ConsolidationCommitted] = []
    event_bus.on(ConsolidationCommitted, lambda event: events.append(event))
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(LLMProvider, provider),
        model="test",
        keep_count=0,
        event_bus=event_bus,
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=manager.get_or_create,
            commit_consolidation=manager.commit_consolidation,
            group_environment=GroupEnvironment(tmp_path, store),
            runtime_roles=RoleStore(tmp_path),
        )
    )
    return manager, store.listening, provider, event_bus, events, maintenance


def _hear_friend(listening: GroupListeningStore, index: int, at: datetime) -> None:
    listening.hear(
        _GROUP,
        sender_id="555",
        content=f"阿明说我家狗第 {index} 次拆家",
        source={**_SOURCE, "sender_id": "555", "sender_name": "阿明"},
        external_message_id=f"m{index}",
        timestamp=at,
    )


@pytest.mark.asyncio
async def test_fifty_records_update_the_group_and_only_its_listening_cursor(
    tmp_path: Path,
):
    manager, listening, provider, event_bus, events, maintenance = _setup(tmp_path)
    session = manager.get_or_create("role:mira")
    cursors_before = (
        consolidation_cursor(session, "user"),
        consolidation_cursor(session, "external"),
        session.last_consolidated,
    )
    try:
        listening.hear(
            _GROUP,
            sender_id="902",
            content="我明天去面试",
            source={**_SOURCE, "sender_id": "902", "sender_is_user": True},
            external_message_id="mine",
            timestamp=_DAY,
        )
        for index in range(48):
            _hear_friend(listening, index, _DAY + timedelta(minutes=1 + index))
        # 49 条同一天的记录还不到整理的时候。
        early = await maintenance.listening.consolidate(_GROUP)
        assert early.trace == {"mode": "skipped"}
        assert provider.environment_prompts == []

        _hear_friend(listening, 48, _DAY + timedelta(minutes=49))
        result = await maintenance.listening.consolidate(_GROUP)
    finally:
        await event_bus.aclose()

    assert result.consolidated_count == 50
    # 群的最近动态、群笔记与群友的成员档案（含速记）都来自这批旁听。
    environment = GroupEnvironment(tmp_path, manager.conversation_store).read(
        "mira", _GROUP
    )
    assert environment.recent_activity == "阿明在群里聊他的狗"
    assert environment.group_note == "## 氛围\n轻松"
    profile = MemberProfiles(tmp_path).read("mira", MemberKey("qq", "555"))
    assert profile is not None and profile.brief == "阿明：爱狗"
    # 用户本人的旁听发言进用户层与引擎，群友的话不进。
    [user_layer_prompt] = provider.user_layer_prompts
    [event] = events
    for conversation in (user_layer_prompt, event.conversation):
        assert "USER（在群「猫猫群」里）: 我明天去面试" in conversation
        assert "拆家" not in conversation
    history = MarkdownMemoryStore(tmp_path / "roles" / "mira").read_history()
    assert "你说明天去面试" in history
    assert "拆家" not in history
    # 只推进该群的旁听游标，角色会话的整理游标不动。
    assert listening.cursors.get(_GROUP) == 50
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert (
        consolidation_cursor(reloaded, "user"),
        consolidation_cursor(reloaded, "external"),
        reloaded.last_consolidated,
    ) == cursors_before
