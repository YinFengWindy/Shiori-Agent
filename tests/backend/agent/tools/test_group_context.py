"""Group notes and summaries are available on demand without exposing raw history."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from agent.tools.group_context import LookupGroupContextTool
from agent.tools.registry import ToolRegistry
from conversation.models import ThreadRecord
from conversation.service import ConversationService, LegacySessionDescriptor
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from session.manager import SessionManager

_OLD = datetime.fromisoformat("2020-01-02T03:04:05+08:00")


def _runtime(tmp_path: Path):
    manager = SessionManager(tmp_path)
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    tools = ToolRegistry()
    tools.register(
        LookupGroupContextTool(environment, ConversationService(manager)),
    )
    return manager, environment, tools


def _thread(
    manager: SessionManager,
    chat_id: str,
    *,
    role_id: str = "mira",
    channel: str = "qq",
    name: str = "买房群",
    chat_type: str = "group",
) -> ThreadRecord:
    conversations = ConversationService(manager)
    thread = conversations.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key=f"{role_id}:{channel}:{chat_id}",
            role_id=role_id,
            channel=channel,
            chat_id=chat_id,
        )
    )
    conversations.remember_contact_name(thread, name)
    session = manager.get_or_create(f"role:{role_id}")
    session.add_message(
        "user",
        f"RAW-CHAT-{chat_id}",
        metadata={"thread_id": thread.id, "chat_type": chat_type},
    )
    manager.save(session)
    return thread


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,channel", [("external", "qq"), ("user", "desktop")])
async def test_user_turn_can_find_and_read_another_channels_old_group_context(
    tmp_path: Path, scope: str, channel: str
) -> None:
    manager, environment, tools = _runtime(tmp_path)
    current = _thread(manager, "current")
    target = _thread(manager, "target", channel="telegram", chat_type="supergroup")
    environment.apply(
        "mira",
        GroupEnvironmentUpdate(target.id, "旧群名", "讨论首付", "大家正在看房"),
        updated_at=_OLD,
    )
    listening = manager.conversation_store.listening
    _ = listening.switches.set_enabled(target.id, True, operator="user")
    assert (
        listening.hear(
            target.id,
            sender_id="555",
            content="RAW-LISTENING-SECRET",
            source={"chat_type": "group"},
            external_message_id="heard-1",
            timestamp=_OLD,
        )
        is not None
    )
    context = {
        "role_id": "mira",
        "context_scope": scope,
        "channel": channel,
        "thread_id": current.id,
        "sender_is_user": "true",
    }
    state_before = manager.conversation_store.get_thread_state(target.id)
    note_path = environment.note_path("mira", target.id)
    note_before = (note_path.read_bytes(), note_path.stat().st_mtime_ns)

    found = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"name": "买房"}, context=context
            )
        )
    )
    assert found["total"] == 2
    assert {item["channel"] for item in found["candidates"]} == {"qq", "telegram"}
    assert all("group_note" not in item for item in found["candidates"])
    result = await tools.execute(
        "lookup_group_context", {"group_thread_id": target.id}, context=context
    )

    assert json.loads(str(result)) == {
        "group_thread_id": target.id,
        "channel": "telegram",
        "name": "买房群",
        "group_note": "大家正在看房",
        "summary": "讨论首付",
        "summary_updated_at": _OLD.isoformat(),
    }
    assert "RAW-" not in str(result)
    assert manager.conversation_store.get_thread_state(target.id) == state_before
    assert (note_path.read_bytes(), note_path.stat().st_mtime_ns) == note_before


@pytest.mark.asyncio
@pytest.mark.parametrize("note,summary", [("只记笔记", ""), ("", "只有摘要"), ("", "")])
async def test_groups_with_partial_or_no_context_still_appear_and_read(
    tmp_path: Path, note: str, summary: str
) -> None:
    manager, environment, tools = _runtime(tmp_path)
    group = _thread(manager, "g")
    environment.apply(
        "mira", GroupEnvironmentUpdate(group.id, "群", summary, note), updated_at=_OLD
    )
    context = {"role_id": "mira"}

    listing = json.loads(
        str(await tools.execute("lookup_group_context", {}, context=context))
    )
    result = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"group_thread_id": group.id}, context=context
            )
        )
    )

    assert listing["total"] == 1
    assert listing["candidates"][0]["group_thread_id"] == group.id
    assert result["group_note"] == note
    assert result["summary"] == summary
    assert result["summary_updated_at"] == (_OLD.isoformat() if summary else "")


@pytest.mark.asyncio
async def test_listing_and_reading_exclude_other_roles_private_and_archived_threads(
    tmp_path: Path,
) -> None:
    manager, environment, tools = _runtime(tmp_path)
    group = _thread(manager, "valid")
    foreign = _thread(manager, "foreign", role_id="nova")
    private = _thread(manager, "private", chat_type="private")
    unknown = _thread(manager, "unknown", chat_type="unknown")
    archived = _thread(manager, "archived")
    _ = manager.conversation_store.archive_thread_and_release_legacy_session_key(
        archived.id
    )
    desktop = ConversationService(manager).ensure_desktop_thread("mira")
    scheduler = manager.conversation_store.upsert_thread(
        thread_id="thread:mira:scheduler:job",
        role_id="mira",
        contact_id=desktop.contact_id,
        channel="scheduler",
        thread_kind="scheduler",
        external_thread_id="job",
        legacy_session_key="scheduler:job",
    )
    forbidden = [foreign, private, unknown, archived, desktop, scheduler]
    for thread in forbidden:
        environment.apply(
            thread.role_id,
            GroupEnvironmentUpdate(thread.id, "秘密", "SECRET-SUMMARY", "SECRET-NOTE"),
            updated_at=_OLD,
        )
    context = {"role_id": "mira", "context_scope": "external", "thread_id": group.id}

    # Even a model-supplied role override cannot alter candidate ownership.
    listing = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"role_id": "nova"}, context=context
            )
        )
    )
    assert [item["group_thread_id"] for item in listing["candidates"]] == [group.id]
    for thread in forbidden:
        result = await tools.execute(
            "lookup_group_context",
            {"group_thread_id": thread.id, "role_id": thread.role_id},
            context=context,
        )
        assert "找不到当前角色所属的群会话" in str(result)
        assert "SECRET" not in str(result)
    for context_without_role in ({}, {"role_id": ""}):
        result = await tools.execute(
            "lookup_group_context",
            {"role_id": "nova", "group_thread_id": foreign.id},
            context=context_without_role,
        )
        assert "当前回合没有角色" in str(result)


@pytest.mark.asyncio
async def test_pagination_reaches_every_group_and_name_search_is_case_insensitive(
    tmp_path: Path,
) -> None:
    manager, _, tools = _runtime(tmp_path)
    groups = [
        _thread(manager, f"g{index:02}", name=f"Housing {index}") for index in range(23)
    ]
    context = {"role_id": "mira", "thread_id": groups[0].id, "channel": "qq"}

    first = json.loads(
        str(await tools.execute("lookup_group_context", {}, context=context))
    )
    second = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"page": first["next_page"]}, context=context
            )
        )
    )
    matched = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"name": "hOUSing 22"}, context=context
            )
        )
    )
    absent = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"name": "不存在"}, context=context
            )
        )
    )

    assert first["total"] == second["total"] == 23
    assert first["next_page"] == 2 and second["next_page"] is None
    assert [
        item["group_thread_id"] for item in first["candidates"] + second["candidates"]
    ] == [group.id for group in groups]
    assert matched["candidates"] == [
        {"group_thread_id": groups[-1].id, "channel": "qq", "name": "Housing 22"}
    ]
    assert absent == {"total": 0, "page": 1, "next_page": None, "candidates": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [0, -1, True, "2", 1.5])
async def test_invalid_pages_are_rejected(tmp_path: Path, page: object) -> None:
    _, _, tools = _runtime(tmp_path)
    result = await tools.execute(
        "lookup_group_context", {"page": page}, context={"role_id": "mira"}
    )
    assert "page 必须是从 1 开始的整数" in str(result)


@pytest.mark.asyncio
async def test_read_target_cannot_be_combined_with_a_name_or_page(
    tmp_path: Path,
) -> None:
    manager, _, tools = _runtime(tmp_path)
    group = _thread(manager, "g")
    for extra in ({"name": "买房"}, {"page": 2}):
        result = await tools.execute(
            "lookup_group_context",
            {"group_thread_id": group.id, **extra},
            context={"role_id": "mira"},
        )
        assert "不能同时按群名查找或翻页" in str(result)
